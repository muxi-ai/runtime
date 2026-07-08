# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Artifact Memory Models - Produced-Work Persistence Tables
# Description:  SQLAlchemy models for artifacts and system_config
# Role:         Defines the answer-persistence schema for produced work
# Usage:        Registered with Base.metadata and created alongside all tables
# Author:       Muxi Framework Team
#
# Artifact Memory Phase 1 (capture). Two tables:
#
# - ``artifacts``: one row per captured artifact version. Everything an
#   agent produces (generate_file outputs today; save_artifact / RCE
#   capture later) is persisted as a gzipped, encrypted blob in artifact
#   storage with its metadata here. Versioning is chained through
#   ``parent_id`` with ``is_latest`` marking the head of each chain.
# - ``system_config``: tiny key/value table holding immutable runtime
#   identity, currently just ``formation_instance_id`` -- the HKDF input
#   keying material for per-user artifact encryption (PRD "Encryption Key
#   Derivation"). Created once at first boot and never changed.
#
# Conventions follow the merged memory tables (kg_entities, captains_log,
# memory_events): integer primary keys, String(21) Nano ID ``public_id``
# for external exposure (instead of the UUID TEXT key sketched in the
# PRD), string ``user_id`` / ``formation_id`` scoping on every row, and
# naive-UTC DateTime columns portable across PostgreSQL and SQLite.
# =============================================================================

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, text

from ....datatypes.json_type import JSONType
from ....utils.datetime_utils import utc_now_naive
from ....utils.id_generator import get_default_nanoid
from ...db import AsyncModelMixin, Base

# system_config key holding the immutable formation instance UUID used as
# the HKDF input keying material for artifact encryption.
FORMATION_INSTANCE_ID_KEY = "formation_instance_id"


class SystemConfig(Base, AsyncModelMixin):
    """Immutable runtime identity key/value store (PRD system_config)."""

    __tablename__ = "system_config"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {"key": self.key, "value": self.value}


class Artifact(Base, AsyncModelMixin):
    """One captured artifact version (metadata row; blob lives in storage)."""

    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Nano ID for external exposure, matching the users table convention.
    public_id = Column(String(21), nullable=False, unique=True, default=get_default_nanoid)
    user_id = Column(String(255), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False, index=True)
    # Producing agent (NULL = overlord) and originating conversation.
    agent_id = Column(String(255), nullable=True)
    conversation_id = Column(String(255), nullable=True)

    # Versioning: new captures with the same (user, name) extend the chain.
    version = Column(Integer, nullable=False, default=1)
    parent_id = Column(Integer, nullable=True)  # previous version's integer id
    is_latest = Column(Boolean, nullable=False, default=True)

    # Descriptive
    name = Column(String(512), nullable=False)
    content_type = Column(String(255), nullable=False)
    category = Column(String(50), nullable=True)
    # Capture-time summary. Phase 1 stores a deterministic description;
    # LLM summarization + embedding land with the retrieval phase.
    summary = Column(Text, nullable=False)
    tags = Column(JSONType, nullable=False, default=[])

    # Storage (blob pipeline: gzip -> encrypt -> write -> checksum)
    storage_ref = Column(String(512), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    compressed_bytes = Column(Integer, nullable=False)  # gzipped size
    checksum_sha256 = Column(String(64), nullable=False)  # over the stored blob

    # Lifecycle
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)
    last_accessed_at = Column(DateTime, nullable=False, default=utc_now_naive)
    expires_at = Column(DateTime, nullable=True)  # NULL = forever

    # Soft delete: metadata is retained for audit, the blob is removed.
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # Chain-head integrity: at most one live latest version per
        # (formation, user, name). This is the multi-process backstop for
        # the version chain -- the service serializes same-chain writes
        # in-process, but two runtime processes can both read the current
        # head before either commits; the loser hits this index and the
        # storage layer retries against the re-read head. A partial
        # unique index is required here (uniqueness over the
        # is_latest=TRUE subset cannot be expressed as a plain composite
        # index because demoted versions repeat the key), and both
        # backends support the WHERE clause -- following the
        # idx_memory_events_idempotency precedent rather than the plain
        # composite conversions the namespaces work applied to
        # non-unique indexes. Soft-deleted heads are excluded so a swept
        # name can be captured fresh.
        Index(
            "idx_artifacts_chain_head",
            "formation_id",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("is_latest AND deleted_at IS NULL"),
            sqlite_where=text("is_latest AND deleted_at IS NULL"),
        ),
        Index("idx_artifacts_user", "formation_id", "user_id"),
        Index("idx_artifacts_user_latest", "formation_id", "user_id", "is_latest"),
        Index("idx_artifacts_user_name", "formation_id", "user_id", "name"),
        Index("idx_artifacts_agent", "agent_id"),
        Index("idx_artifacts_parent", "parent_id"),
        Index(
            "idx_artifacts_expires",
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
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "version": self.version,
            "parent_id": self.parent_id,
            "is_latest": bool(self.is_latest),
            "name": self.name,
            "content_type": self.content_type,
            "category": self.category,
            "summary": self.summary,
            "tags": self.tags or [],
            "storage_ref": self.storage_ref,
            "size_bytes": self.size_bytes,
            "compressed_bytes": self.compressed_bytes,
            "checksum_sha256": self.checksum_sha256,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_accessed_at": (
                self.last_accessed_at.isoformat() if self.last_accessed_at else None
            ),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }
