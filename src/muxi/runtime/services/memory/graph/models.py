# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Graph Models - Entity and Relationship Tables
# Description:  SQLAlchemy models for the structured knowledge graph
# Role:         Defines the kg_entities and kg_relationships tables
# Usage:        Registered with Base.metadata and created alongside all tables
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 1 (Knowledge Graph Foundation). Structured entities and
# relationships extracted from conversations, stored alongside (not replacing)
# the existing flat-fact collections. The schema is identical on PostgreSQL
# and SQLite:
#
# - Integer primary keys double as the integer node/edge identity required by
#   graph algorithm backends (pgRouting needs bigint ids; NetworkX is
#   indifferent). This follows the existing ``users`` table convention
#   (Integer PK + String(21) ``public_id`` Nano ID for external exposure)
#   instead of the UUID + BIGSERIAL pair sketched in the PRD -- same
#   properties, portable across both backends.
# - ``user_id`` stores the external user identifier as a string (the same
#   convention identities use throughout the runtime).
# - ``status`` / ``contradicted_by`` / ``superseded_by`` implement the PRD's
#   contradiction-detection model: conflicting facts are cross-referenced and
#   retained, never silently overwritten.
# =============================================================================

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint

from ....datatypes.json_type import JSONType
from ....utils.datetime_utils import utc_now_naive
from ....utils.id_generator import get_default_nanoid
from ...db import AsyncModelMixin, Base

# Entity type vocabulary (PRD "Entity Types"). Used to steer the extraction
# prompt; storage accepts any lowercase string so the vocabulary can grow
# without a migration.
ENTITY_TYPES = {
    "person": "A person (name, role, relationship to the user)",
    "company": "A company or organization",
    "project": "A project or product",
    "location": "A place (city, country, region)",
    "preference": "A user preference (category and value)",
    "topic": "A topic of interest",
}

# Relationship type vocabulary (PRD "Relationship Types").
RELATIONSHIP_TYPES = {
    "works_at": "Person works at Company",
    "founded": "Person founded Company",
    "building": "Person or Company is building Project",
    "lives_in": "Person lives in Location",
    "prefers": "User prefers Preference",
    "knows": "Person knows Person",
    "interested_in": "User is interested in Topic",
    "part_of": "Entity is part of Entity",
}

# Relationship types where one subject holds at most one active object.
# A new object for the same (subject, type) pair triggers contradiction
# detection instead of coexisting (PRD example: lives_in London vs Berlin).
EXCLUSIVE_RELATIONSHIP_TYPES = {"lives_in", "works_at"}

# Fact lifecycle states (PRD "Contradiction Detection").
STATUS_ACTIVE = "active"
STATUS_CONFLICTED = "conflicted"
STATUS_SUPERSEDED = "superseded"

# Entity resolved as a duplicate identity (Memory Ingestion maturation,
# PRD "Entity resolution"). The row is retained with ``superseded_by``
# pointing at the canonical entity; upserts by the merged name redirect
# to the canonical row so the duplicate never silently revives.
STATUS_MERGED = "merged"

# Confidence delta above which a new fact auto-supersedes a conflicting old
# fact instead of flagging both as conflicted (PRD: ">0.3 delta").
SUPERSEDE_CONFIDENCE_DELTA = 0.3


class KGEntity(Base, AsyncModelMixin):
    """A structured entity extracted from conversations.

    One row per (user, formation, type, name). Upserts merge attributes and
    keep the highest confidence seen.
    """

    __tablename__ = "kg_entities"

    # Integer identity used directly by graph algorithms (pgRouting node id).
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Nano ID for external exposure, matching the users table convention.
    public_id = Column(String(21), nullable=False, unique=True, default=get_default_nanoid)
    user_id = Column(String(255), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    attributes = Column(JSONType, nullable=False, default={})
    confidence = Column(Float, nullable=False, default=0.5)
    status = Column(String(20), nullable=False, default=STATUS_ACTIVE)
    # Cross-references into this table (plain integers, not FKs, so conflict
    # bookkeeping never fights the schema over insertion order).
    contradicted_by = Column(Integer, nullable=True)
    superseded_by = Column(Integer, nullable=True)
    # Provenance bridge (Memory Event Substrate): the memory_events ids this
    # row was derived from, appended on every contributing upsert.
    derived_from_event_ids = Column(JSONType, nullable=False, default=[])
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "formation_id", "type", "name", name="uq_kg_entity_scope_type_name"
        ),
        Index("idx_kg_entities_user_type", "user_id", "type"),
        Index("idx_kg_entities_user_name", "user_id", "name"),
    )

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "public_id": self.public_id,
            "user_id": self.user_id,
            "formation_id": self.formation_id,
            "type": self.type,
            "name": self.name,
            "attributes": self.attributes or {},
            "confidence": self.confidence,
            "status": self.status,
            "contradicted_by": self.contradicted_by,
            "superseded_by": self.superseded_by,
            "derived_from_event_ids": self.derived_from_event_ids or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KGRelationship(Base, AsyncModelMixin):
    """A directed, typed edge between two knowledge graph entities."""

    __tablename__ = "kg_relationships"

    # Integer identity used directly by graph algorithms (pgRouting edge id).
    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String(21), nullable=False, unique=True, default=get_default_nanoid)
    user_id = Column(String(255), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False, index=True)
    from_entity_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=False)
    to_entity_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=False)
    type = Column(String(50), nullable=False)
    attributes = Column(JSONType, nullable=False, default={})
    confidence = Column(Float, nullable=False, default=0.5)
    status = Column(String(20), nullable=False, default=STATUS_ACTIVE)
    contradicted_by = Column(Integer, nullable=True)
    superseded_by = Column(Integer, nullable=True)
    # Provenance bridge (Memory Event Substrate): the memory_events ids this
    # row was derived from, appended on every contributing upsert.
    derived_from_event_ids = Column(JSONType, nullable=False, default=[])
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        Index("idx_kg_relationships_user_type", "user_id", "type"),
        Index("idx_kg_relationships_from", "from_entity_id"),
        Index("idx_kg_relationships_to", "to_entity_id"),
    )

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "public_id": self.public_id,
            "user_id": self.user_id,
            "formation_id": self.formation_id,
            "from_entity_id": self.from_entity_id,
            "to_entity_id": self.to_entity_id,
            "type": self.type,
            "attributes": self.attributes or {},
            "confidence": self.confidence,
            "status": self.status,
            "contradicted_by": self.contradicted_by,
            "superseded_by": self.superseded_by,
            "derived_from_event_ids": self.derived_from_event_ids or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
