# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Event Models - Immutable Event Log Tables
# Description:  SQLAlchemy models for memory_events and projection_checkpoints
# Role:         Defines the append-only substrate underneath every memory layer
# Usage:        Registered with Base.metadata and created alongside all tables
# Author:       Muxi Framework Team
#
# Memory Event Substrate (Memory Platform Phase 2). Every memory-producing
# write first becomes a row in ``memory_events``; projections (knowledge
# graph, captain's log + lessons, flat facts) are derived state that can be
# rebuilt from the log. The schema is identical on PostgreSQL and SQLite:
#
# - Integer primary keys double as the replay cursor: ids are assigned in
#   append order, so ``ORDER BY id`` is the canonical event ordering. This
#   follows the kg_entities convention (Integer PK + String(21) ``public_id``
#   Nano ID for external exposure) instead of the UUIDv7 TEXT key sketched
#   in the PRD -- same time-ordered property, portable across both backends.
# - ``scope_type`` / ``scope_id`` record the event's memory scope in the
#   shape the memory-namespaces plan expects. Scoping is not built yet, so
#   every event carries the implicit user scope (scope_type='user',
#   scope_id=user_id); richer scopes can be added later without
#   re-ingestion or schema changes.
# - Events are immutable: the storage layer exposes no update path. The
#   only mutation is the soft-delete pair (``deleted_at``/``deleted_reason``)
#   that powers GDPR-style selective forgetting.
# - ``EVENT_SCHEMAS`` is the versioned payload registry validated at write
#   time. Adding a projection (e.g. the deferred Knowledge Index) means
#   registering its event types here and its projector with the service --
#   no schema migration.
# =============================================================================

from typing import Any, Dict

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, text

from ....datatypes.json_type import JSONType
from ....utils.datetime_utils import utc_now_naive
from ....utils.id_generator import get_default_nanoid
from ...db import AsyncModelMixin, Base

# ---------------------------------------------------------------------------
# Event type vocabulary (PRD "Event Types", restricted to the write paths
# that exist today). Each type maps event_version -> payload schema.
# ---------------------------------------------------------------------------

# One conversation turn as seen by the extraction coordinator. Not consumed
# by any projector today; recorded so future extraction logic can be replayed
# over raw interactions and so downstream events can carry a causation link.
EVENT_INTERACTION_TURN = "interaction.turn"

# One flat fact extracted by the MemoryExtractor (vector-DB projection).
EVENT_FACT_EXTRACTED = "fact.extracted"

# One validated knowledge-graph extraction batch (entities + relationships).
EVENT_GRAPH_EXTRACTED = "graph.extracted"

# One captain's log digest result for a (user, date) entry.
EVENT_LOG_ENTRY = "log.entry"

# One lesson written through the digest or the record_lesson tool.
EVENT_LESSON_RECORDED = "lesson.recorded"

# A user-initiated deletion request (the audit-trail event; the referenced
# events are soft-deleted, not removed).
EVENT_USER_DELETION = "user.deletion"

# Versioned payload schemas. "required" keys must be present; keys outside
# required + optional are rejected -- schema evolution happens by adding a
# new version, never by silently widening an existing one.
EVENT_SCHEMAS: Dict[str, Dict[int, Dict[str, tuple]]] = {
    EVENT_INTERACTION_TURN: {
        1: {
            "required": ("user_message",),
            "optional": ("agent_response", "session_id"),
        }
    },
    EVENT_FACT_EXTRACTED: {
        1: {
            "required": ("memory", "collection"),
            "optional": ("metadata",),
        }
    },
    EVENT_GRAPH_EXTRACTED: {
        1: {
            "required": ("entities", "relationships"),
            "optional": (),
        }
    },
    EVENT_LOG_ENTRY: {
        1: {
            "required": ("date", "summary"),
            "optional": ("decisions", "projects", "context", "sources"),
        }
    },
    EVENT_LESSON_RECORDED: {
        1: {
            "required": ("agent_id", "rule"),
            "optional": ("context", "confidence", "source_log_date"),
        }
    },
    EVENT_USER_DELETION: {
        1: {
            "required": ("reason",),
            "optional": ("source", "target_event_ids"),
        }
    },
}

# Payload keys that must be lists when present (shape checks beyond presence).
_LIST_KEYS = {"entities", "relationships", "decisions", "projects", "sources", "target_event_ids"}

# Decay rates declared at write time (PRD "Decay Model"). Query-time decay
# weighting is a later phase; the substrate records the declaration so old
# events benefit when it lands.
DECAY_STATIC = "static"
DECAY_DECAYING = "decaying"
DECAY_VOLATILE = "volatile"
DECAY_RATES = {DECAY_STATIC, DECAY_DECAYING, DECAY_VOLATILE}

# Source vocabulary used by the internal writers that exist today. External
# ingestion sources (gmail, osint, ...) join this vocabulary in Phase 3.
SOURCE_INTERACTION = "interaction"  # real-time chat-turn extraction passes
SOURCE_PERIODIC = "periodic"  # the knowledge graph's periodic deep pass
SOURCE_CAPTAINS_LOG = "captains_log"  # digest-derived writes (entries, lessons, graph facts)
SOURCE_TOOL = "tool"  # the record_lesson agent tool
SOURCE_USER_EDIT = "user_edit"  # user-initiated corrections/deletions

# Scope shape recorded for forward compatibility with memory namespaces.
from ..base import SCOPE_TYPE_USER  # noqa: E402 -- canonical scope constants


def validate_event_payload(event_type: str, payload: Any, event_version: int = 1) -> None:
    """
    Validate an event payload against the versioned schema registry.

    Raises:
        ValueError: On unknown event type/version, non-dict payload,
            missing required keys, unknown keys, or mis-typed list fields.
    """
    versions = EVENT_SCHEMAS.get(event_type)
    if versions is None:
        raise ValueError(f"Unknown memory event type: {event_type!r}")
    schema = versions.get(event_version)
    if schema is None:
        raise ValueError(f"Unknown version {event_version} for event type {event_type!r}")
    if not isinstance(payload, dict):
        raise ValueError(f"Payload for {event_type!r} must be a dict, got {type(payload).__name__}")

    missing = [key for key in schema["required"] if key not in payload]
    if missing:
        raise ValueError(f"Payload for {event_type!r} is missing required keys: {missing}")

    allowed = set(schema["required"]) | set(schema["optional"])
    unknown = [key for key in payload if key not in allowed]
    if unknown:
        raise ValueError(f"Payload for {event_type!r} has unknown keys: {unknown}")

    for key in _LIST_KEYS:
        if key in payload and not isinstance(payload[key], list):
            raise ValueError(f"Payload key {key!r} for {event_type!r} must be a list")


def append_event_id(current, event_id) -> list:
    """
    Return a ``derived_from_event_ids`` provenance list with ``event_id``
    appended (idempotent; a None event_id or an already-present id leaves
    the list unchanged).

    Shared by every projection storage layer that maintains the provenance
    bridge back into ``memory_events``.
    """
    ids = list(current or [])
    if event_id is not None and event_id not in ids:
        ids.append(event_id)
    return ids


class MemoryEvent(Base, AsyncModelMixin):
    """One immutable row in the append-only memory event log."""

    __tablename__ = "memory_events"

    # Integer identity assigned in append order: the replay cursor.
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Nano ID for external exposure, matching the users table convention.
    public_id = Column(String(21), nullable=False, unique=True, default=get_default_nanoid)
    user_id = Column(String(255), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False, index=True)

    # Forward-compatible scope columns (memory-namespaces cross-reference).
    # Today every event is user-scoped; scope_id mirrors user_id.
    scope_type = Column(String(20), nullable=False, default=SCOPE_TYPE_USER)
    scope_id = Column(String(255), nullable=False)

    # When the event happened vs when MUXI received it (differs on backfill).
    occurred_at = Column(DateTime, nullable=False, default=utc_now_naive)
    ingested_at = Column(DateTime, nullable=False, default=utc_now_naive)

    event_type = Column(String(50), nullable=False)
    event_version = Column(Integer, nullable=False, default=1)
    payload = Column(JSONType, nullable=False, default={})

    # Source tracking (what produced this event).
    source = Column(String(50), nullable=False)
    source_id = Column(String(255), nullable=True)
    source_confidence = Column(Float, nullable=False, default=1.0)

    # Causation link into this table (plain integer, not an FK, following
    # the kg_entities cross-reference convention).
    caused_by = Column(Integer, nullable=True)

    # Decay declaration (applied at query time in a later phase).
    decay_rate = Column(String(20), nullable=False, default=DECAY_STATIC)
    expires_at = Column(DateTime, nullable=True)

    # Soft delete for GDPR + selective forgetting. Replay skips soft-deleted
    # events; a periodic hard-purge removes them after the grace period.
    deleted_at = Column(DateTime, nullable=True)
    deleted_reason = Column(String(50), nullable=True)

    # Producing agent (NULL = overlord) and originating conversation.
    agent_id = Column(String(255), nullable=True)
    conversation_id = Column(String(255), nullable=True)

    __table_args__ = (
        # Idempotency: the same (source, source_id) cannot be written twice
        # for a scope while live. Partial unique index works on both
        # backends; soft-deleting an event re-allows its source_id.
        Index(
            "idx_memory_events_idempotency",
            "formation_id",
            "user_id",
            "source",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("source_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        # Dominant access patterns (PRD "Multi-Tenancy & Performance").
        Index("idx_memory_events_user_time", "formation_id", "user_id", "occurred_at"),
        Index("idx_memory_events_user_type", "formation_id", "user_id", "event_type"),
        Index("idx_memory_events_user_source", "formation_id", "user_id", "source"),
        Index("idx_memory_events_caused_by", "caused_by"),
        Index(
            "idx_memory_events_expires",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
            sqlite_where=text("expires_at IS NOT NULL"),
        ),
    )

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "public_id": self.public_id,
            "user_id": self.user_id,
            "formation_id": self.formation_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "payload": self.payload or {},
            "source": self.source,
            "source_id": self.source_id,
            "source_confidence": self.source_confidence,
            "caused_by": self.caused_by,
            "decay_rate": self.decay_rate,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "deleted_reason": self.deleted_reason,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
        }


class ProjectionCheckpoint(Base, AsyncModelMixin):
    """Per-(projection, user) cursor into the memory event log."""

    __tablename__ = "projection_checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projection_name = Column(String(50), nullable=False)
    formation_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    last_event_id = Column(Integer, nullable=False)
    last_applied_at = Column(DateTime, nullable=False, default=utc_now_naive)
    schema_version = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index(
            "idx_projection_checkpoints_scope",
            "projection_name",
            "formation_id",
            "user_id",
            unique=True,
        ),
    )

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "projection_name": self.projection_name,
            "formation_id": self.formation_id,
            "user_id": self.user_id,
            "last_event_id": self.last_event_id,
            "last_applied_at": (self.last_applied_at.isoformat() if self.last_applied_at else None),
            "schema_version": self.schema_version,
        }
