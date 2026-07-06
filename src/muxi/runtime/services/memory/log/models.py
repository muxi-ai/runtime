# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Captain's Log Models - Narrative Memory and Lessons Tables
# Description:  SQLAlchemy models for captains_log, captains_log_sources, lessons
# Role:         Defines the temporal-narrative and self-improvement schema
# Usage:        Registered with Base.metadata and created alongside all tables
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 2 (Captain's Log). Three tables:
#
# - ``captains_log``: one narrative entry per (user, formation, date) with
#   structured sections (summary, decisions, projects, context).
# - ``captains_log_sources``: source lineage for each entry. Rows referencing
#   buffer turns or vector chunks are terminal evidence pointers; rows with
#   source_type 'log_entry' form the directed acyclic derivation graph
#   between entries (summaries derived from earlier summaries) that
#   ``GraphAlgorithms.topological_sort`` orders.
# - ``lessons``: prescriptive rules of thumb the agent has learned, scoped
#   per (user, agent, formation) and deduplicated by a hash of the
#   normalized rule text.
#
# Conventions follow Phase 1 (kg_entities / kg_relationships): integer
# primary keys, String(21) Nano ID ``public_id`` for external exposure,
# string ``user_id`` / ``formation_id`` scoping on every row.
# =============================================================================

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from ....datatypes.json_type import JSONType
from ....utils.datetime_utils import utc_now_naive
from ....utils.id_generator import get_default_nanoid
from ...db import AsyncModelMixin, Base

# Source lineage vocabulary (PRD "captains_log_sources").
SOURCE_TYPE_BUFFER_ITEM = "buffer_item"
SOURCE_TYPE_VECTOR_CHUNK = "vector_chunk"
# A log entry derived from an earlier log entry. These rows form the DAG
# ordered by GraphAlgorithms.topological_sort (source_id holds the integer
# id of the source entry as text, matching the TEXT source_id column).
SOURCE_TYPE_LOG_ENTRY = "log_entry"

SOURCE_TYPES = {SOURCE_TYPE_BUFFER_ITEM, SOURCE_TYPE_VECTOR_CHUNK, SOURCE_TYPE_LOG_ENTRY}


class CaptainsLogEntry(Base, AsyncModelMixin):
    """One narrative log entry per (user, formation, date)."""

    __tablename__ = "captains_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Nano ID for external exposure, matching the users table convention.
    public_id = Column(String(21), nullable=False, unique=True, default=get_default_nanoid)
    user_id = Column(String(255), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False, index=True)
    date = Column(Date, nullable=False)
    summary = Column(Text, nullable=True)
    decisions = Column(JSONType, nullable=False, default=[])
    projects = Column(JSONType, nullable=False, default=[])
    context = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint("user_id", "formation_id", "date", name="uq_captains_log_scope_date"),
        Index("idx_captains_log_user_date", "user_id", "date"),
    )

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "public_id": self.public_id,
            "user_id": self.user_id,
            "formation_id": self.formation_id,
            "date": self.date.isoformat() if self.date else None,
            "summary": self.summary,
            "decisions": self.decisions or [],
            "projects": self.projects or [],
            "context": self.context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CaptainsLogSource(Base, AsyncModelMixin):
    """Source lineage row linking a log entry to the material it derives from."""

    __tablename__ = "captains_log_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_id = Column(Integer, ForeignKey("captains_log.id"), nullable=False)
    source_type = Column(String(20), nullable=False)
    # Buffer timestamp key, vector DB chunk id, or a source log entry's
    # integer id rendered as text (source_type 'log_entry').
    source_id = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)

    __table_args__ = (
        UniqueConstraint("log_id", "source_type", "source_id", name="uq_captains_log_source"),
        Index("idx_captains_log_sources_log", "log_id"),
    )

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "log_id": self.log_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Lesson(Base, AsyncModelMixin):
    """A prescriptive rule of thumb learned by an agent for a user."""

    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String(21), nullable=False, unique=True, default=get_default_nanoid)
    user_id = Column(String(255), nullable=False)
    agent_id = Column(String(255), nullable=False)
    formation_id = Column(String(255), nullable=False)
    rule = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    # Hex sha256 of the normalized rule text. The PRD sketches BYTEA; a hex
    # string is byte-identical in semantics and portable across both
    # backends without a dialect-specific type.
    rule_hash = Column(String(64), nullable=False)
    source_log_id = Column(Integer, ForeignKey("captains_log.id"), nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    hits = Column(Integer, nullable=False, default=1)
    last_applied_at = Column(DateTime, nullable=True)
    # When the decay job last touched this row. Kept separate from
    # updated_at so decay bookkeeping is explicit and idempotent.
    decayed_at = Column(DateTime, nullable=True)
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "agent_id", "formation_id", "rule_hash", name="uq_lesson_rule_hash"
        ),
        Index("idx_lessons_scope", "user_id", "agent_id", "formation_id"),
        Index("idx_lessons_active_confidence", "archived", "confidence"),
    )

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "public_id": self.public_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "formation_id": self.formation_id,
            "rule": self.rule,
            "context": self.context,
            "rule_hash": self.rule_hash,
            "source_log_id": self.source_log_id,
            "confidence": self.confidence,
            "hits": self.hits,
            "last_applied_at": (self.last_applied_at.isoformat() if self.last_applied_at else None),
            "decayed_at": self.decayed_at.isoformat() if self.decayed_at else None,
            "archived": self.archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
