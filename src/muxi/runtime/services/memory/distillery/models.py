# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Distillery Registry Models - Registered Distillery Table
# Description:  SQLAlchemy model for registered on-prem distilleries
# Role:         Persistence for the distillery trust registry (Phase 3b)
# Usage:        Registered with Base.metadata and created alongside all tables
# Author:       Muxi Framework Team
#
# Memory Distillery (Memory Platform Phase 3b). A "distillery" is an
# on-premises distillation server that ships signed batches of pre-distilled
# memory events to POST /v1/memories/distilled. Before it can send anything
# it must be registered by a formation administrator: registration stores
# the distillery's Ed25519 public key and its write scope (which user_ids,
# which event types, daily volume and batch-size ceilings).
#
# Trust model notes:
# - The distillery acts as a SYSTEM-LEVEL principal (GBAC cross-reference):
#   its authority comes from this registration, not from per-user
#   memory.write grants. Every event it ships still lands USER-SCOPED under
#   the event's own user_id -- shared visibility stays governed by the
#   formation's groups at retrieval time, exactly like every other memory.
# - trust_level "provisional" caps source_confidence on every event; an
#   admin promotes the registration to "verified" once output is trusted.
# - Revocation is a soft state (status="revoked"): subsequent batches get
#   410 Gone, previously ingested events are kept (explicit user.deletion
#   is the purge path, mirroring the substrate's forgetting model).
# =============================================================================

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint

from ....datatypes.json_type import JSONType
from ....utils.datetime_utils import utc_now_naive
from ....utils.id_generator import get_default_nanoid
from ...db import AsyncModelMixin, Base

# Trust levels (PRD "Trust Level and Source Confidence").
TRUST_VERIFIED = "verified"
TRUST_PROVISIONAL = "provisional"
TRUST_LEVELS = {TRUST_VERIFIED, TRUST_PROVISIONAL}

# source_confidence ceiling applied to every event from a provisional
# distillery, regardless of what the payload declares.
PROVISIONAL_CONFIDENCE_CAP = 0.7

# Registration lifecycle states.
STATUS_ACTIVE = "active"
STATUS_REVOKED = "revoked"

# Quota counters older than this many days are pruned opportunistically on
# the consume path (see DistilleryQuotaStore.try_consume) -- only today's
# row is ever read, so the window is pure debugging headroom.
QUOTA_RETENTION_DAYS = 7


class RegisteredDistillery(Base, AsyncModelMixin):
    """One registered on-prem distillery (public key + write scope)."""

    __tablename__ = "memory_distilleries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Nano ID exposed as the X-Distillery-ID header value.
    public_id = Column(String(21), nullable=False, unique=True, default=get_default_nanoid)
    formation_id = Column(String(255), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)

    # Ed25519 public key as registered ("ed25519:" + base64 DER/raw bytes).
    public_key = Column(String(512), nullable=False)

    # Write scope: {"user_ids": "all"|"pattern:<glob>"|[...],
    #               "event_types": [...],
    #               "max_events_per_day": int, "max_batch_size": int}
    scope = Column(JSONType, nullable=False, default={})

    trust_level = Column(String(20), nullable=False, default=TRUST_PROVISIONAL)
    status = Column(String(20), nullable=False, default=STATUS_ACTIVE)

    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("idx_memory_distilleries_formation", "formation_id", "status"),)

    def to_dict(self) -> dict:
        """Return a plain-dict representation used by storage consumers."""
        return {
            "id": self.id,
            "distillery_id": self.public_id,
            "formation_id": self.formation_id,
            "name": self.name,
            "description": self.description,
            "public_key": self.public_key,
            "scope": self.scope or {},
            "trust_level": self.trust_level,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }


class DistilleryQuotaCounter(Base, AsyncModelMixin):
    """One (distillery, UTC day) accepted-event counter.

    Durable replacement for the old in-process daily-count dict: the quota
    guard increments this row with a single guarded upsert
    (increment-if-under-limit), so counts survive restarts and stay
    correct across replicas sharing the database. Per-day rollover comes
    free from the quota_date key; rows older than QUOTA_RETENTION_DAYS are
    pruned opportunistically on the consume path.
    """

    __tablename__ = "distillery_quota_counters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    formation_id = Column(String(255), nullable=False)
    # The distillery's public id (the X-Distillery-ID header value).
    distillery_id = Column(String(21), nullable=False)
    # UTC day bucket, "YYYY-MM-DD".
    quota_date = Column(String(10), nullable=False)
    count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, default=utc_now_naive)

    __table_args__ = (
        UniqueConstraint(
            "formation_id",
            "distillery_id",
            "quota_date",
            name="uq_distillery_quota_counters_day",
        ),
    )
