# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Distillery Registry - Registration Storage
# Description:  Register, look up, list, and revoke distilleries
# Role:         Persistence for the distillery trust registry (Phase 3b)
# Usage:        Used by MemoryDistilleryService and the admin routes
# Author:       Muxi Framework Team
#
# Backend-agnostic persistence for registered distilleries, following the
# memory event storage pattern: same ORM model and queries on PostgreSQL
# and SQLite through the shared DatabaseManager async session factory, all
# rows scoped by formation_id.
# =============================================================================

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from ....utils.datetime_utils import utc_now_naive
from .models import (
    STATUS_ACTIVE,
    STATUS_REVOKED,
    TRUST_LEVELS,
    TRUST_PROVISIONAL,
    RegisteredDistillery,
)
from .verification import parse_public_key


class DistilleryRegistry:
    """Persistence layer for the distillery trust registry."""

    def __init__(self, db_manager, formation_id: str):
        """
        Initialize the registry bound to a formation.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all rows.
        """
        self.db_manager = db_manager
        self.formation_id = formation_id

    async def register(
        self,
        name: str,
        public_key: str,
        scope: Dict[str, Any],
        trust_level: str = TRUST_PROVISIONAL,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register one distillery; returns its record (with distillery_id).

        Raises:
            ValueError: On a missing name, an unparseable Ed25519 public
                key, or an unknown trust level.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("'name' is required and must be a non-empty string")
        if trust_level not in TRUST_LEVELS:
            raise ValueError(
                f"Invalid trust_level {trust_level!r}; expected one of {sorted(TRUST_LEVELS)}"
            )
        # Reject unusable key material at registration time (fail-closed:
        # a registration that cannot verify anything must not exist).
        parse_public_key(public_key)

        async with self.db_manager.get_async_session() as session:
            distillery = RegisteredDistillery(
                formation_id=self.formation_id,
                name=name.strip(),
                description=description,
                public_key=public_key.strip(),
                scope=dict(scope),
                trust_level=trust_level,
                status=STATUS_ACTIVE,
            )
            session.add(distillery)
            await session.flush()
            return distillery.to_dict()

    async def get(self, distillery_id: str) -> Optional[Dict[str, Any]]:
        """Return the distillery with the given public id, or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(RegisteredDistillery).filter_by(
                public_id=str(distillery_id), formation_id=self.formation_id
            )
            row = (await session.execute(stmt)).scalars().first()
            return row.to_dict() if row else None

    async def list(self, include_revoked: bool = True) -> List[Dict[str, Any]]:
        """List this formation's distilleries (newest first)."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(RegisteredDistillery).filter_by(formation_id=self.formation_id)
            if not include_revoked:
                stmt = stmt.filter_by(status=STATUS_ACTIVE)
            stmt = stmt.order_by(RegisteredDistillery.id.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    async def revoke(self, distillery_id: str) -> Optional[Dict[str, Any]]:
        """
        Revoke a distillery registration (idempotent).

        Subsequent batches from it are rejected with 410 Gone; previously
        ingested events are NOT removed (explicit user.deletion events are
        the purge path). Returns the updated record, or None if unknown.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = select(RegisteredDistillery).filter_by(
                public_id=str(distillery_id), formation_id=self.formation_id
            )
            row = (await session.execute(stmt)).scalars().first()
            if row is None:
                return None
            if row.status != STATUS_REVOKED:
                row.status = STATUS_REVOKED
                row.revoked_at = utc_now_naive()
                await session.flush()
            return row.to_dict()
