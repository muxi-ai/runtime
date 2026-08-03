# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Event Storage - Append-Only Log Persistence
# Description:  SQLAlchemy-backed storage for the memory event substrate
# Role:         Event appends, idempotency, replay reads, and checkpoints
# Usage:        Used by MemoryEventService
# Author:       Muxi Framework Team
#
# Backend-agnostic persistence layer for the memory event log. The same ORM
# models and queries run on PostgreSQL and SQLite through the shared
# DatabaseManager async session factory. All rows are scoped by
# (user_id, formation_id) exactly like the projection tables.
#
# Immutability contract: this class exposes append, read, soft-delete, and
# hard-purge -- never update. An appended event's type, payload, source, and
# timestamps are permanent; the only mutable columns are the soft-delete
# pair, and hard purge physically removes rows only after the retention
# grace period.
#
# Idempotency (PRD "Write Path"): when ``source_id`` is provided, a second
# append with the same (formation, user, source, source_id) returns the
# existing event instead of writing a duplicate. A partial unique index
# backs this check so concurrent appenders cannot race past it.
# =============================================================================

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.exc import IntegrityError

from ....utils.datetime_utils import utc_now_naive
from ..scopes import validate_scope
from .models import (
    DECAY_RATES,
    DECAY_STATIC,
    SCOPE_TYPE_USER,
    MemoryEvent,
    ProjectionCheckpoint,
    validate_event_payload,
)


class MemoryEventStorage:
    """Persistence layer for the append-only memory event log."""

    def __init__(self, db_manager, formation_id: str):
        """
        Initialize event storage bound to a formation.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier used to scope all rows.
        """
        self.db_manager = db_manager
        self.formation_id = formation_id

    # ------------------------------------------------------------------
    # Append (the only write)
    # ------------------------------------------------------------------

    async def append(
        self,
        user_id: str,
        event_type: str,
        payload: Dict[str, Any],
        source: str,
        source_id: Optional[str] = None,
        source_confidence: float = 1.0,
        event_version: int = 1,
        occurred_at: Optional[datetime] = None,
        caused_by: Optional[int] = None,
        decay_rate: str = DECAY_STATIC,
        expires_at: Optional[datetime] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Append one event to the log after validating its payload.

        ``scope_type`` / ``scope_id`` record the memory namespace the
        projection write carries (memory namespaces Phases 2+3): shared-
        scope writes pass their true scope so replay reproduces scoped
        rows. Default (None) is the implicit user scope with scope_id
        mirroring user_id -- byte-identical to the substrate's Phase 1
        shape.

        ``request_id`` links the event to the observability request that
        produced it (``RequestContext.id``); None for events with no
        originating request. It is not part of the idempotency key: a
        duplicate (source, source_id) append returns the existing event
        regardless of the request that retried it.

        Returns:
            (event dict, created) -- created is False when an idempotent
            duplicate was detected and the existing event is returned.

        Raises:
            ValueError: On schema validation failure, invalid decay rate,
                or an invalid scope.
        """
        user_id = str(user_id)
        validate_event_payload(event_type, payload, event_version)
        if decay_rate not in DECAY_RATES:
            raise ValueError(f"Invalid decay_rate {decay_rate!r}; expected one of {DECAY_RATES}")
        if not source or not str(source).strip():
            raise ValueError("Memory events require a non-empty source")

        if scope_type is None:
            scope_type, scope_id = SCOPE_TYPE_USER, user_id
        else:
            validate_scope(scope_type, scope_id)
            if scope_type == SCOPE_TYPE_USER:
                scope_id = user_id
            elif scope_id is None:  # formation scope defaults to this formation
                scope_id = self.formation_id

        if source_id is not None:
            existing = await self.find_by_source_id(user_id, source, source_id)
            if existing is not None:
                return existing, False

        try:
            return await self._insert(
                user_id=user_id,
                event_type=event_type,
                payload=payload,
                source=source,
                source_id=source_id,
                source_confidence=source_confidence,
                event_version=event_version,
                occurred_at=occurred_at,
                caused_by=caused_by,
                decay_rate=decay_rate,
                expires_at=expires_at,
                agent_id=agent_id,
                conversation_id=conversation_id,
                scope_type=scope_type,
                scope_id=scope_id,
                request_id=request_id,
            )
        except IntegrityError:
            # Lost an idempotency race: another appender inserted the same
            # (source, source_id) between our check and our insert.
            if source_id is not None:
                existing = await self.find_by_source_id(user_id, source, source_id)
                if existing is not None:
                    return existing, False
            raise

    async def _insert(self, user_id: str, **fields) -> Tuple[Dict[str, Any], bool]:
        """Insert one event row; returns (event dict, True)."""
        occurred_at = fields.pop("occurred_at") or utc_now_naive()
        async with self.db_manager.get_async_session() as session:
            # Memory namespaces contract: whatever scope the projection
            # write carries is recorded here unchanged, so replay can
            # reproduce scoped rows. ``append`` resolved the default
            # (user scope, scope_id = user_id) before delegating here.
            event = MemoryEvent(
                user_id=user_id,
                formation_id=self.formation_id,
                occurred_at=occurred_at,
                **fields,
            )
            session.add(event)
            await session.flush()
            return event.to_dict(), True

    async def find_by_source_id(
        self, user_id: str, source: str, source_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return the live event matching the idempotency key, or None.

        Public so writers with pre-append accounting (e.g. the distillery
        quota gate) can resolve duplicates read-only before deciding to
        append; ``append`` itself uses the same lookup for its idempotent
        return path.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(MemoryEvent)
                .filter_by(
                    user_id=user_id,
                    formation_id=self.formation_id,
                    source=source,
                    source_id=source_id,
                )
                .filter(MemoryEvent.deleted_at.is_(None))
            )
            event = (await session.execute(stmt)).scalars().first()
            return event.to_dict() if event else None

    # ------------------------------------------------------------------
    # Reads (replay + provenance)
    # ------------------------------------------------------------------

    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Return the event with the given integer id, or None."""
        async with self.db_manager.get_async_session() as session:
            event = await session.get(MemoryEvent, event_id)
            if event is None or event.formation_id != self.formation_id:
                return None
            return event.to_dict()

    async def get_event_by_public_id(
        self, user_id: str, public_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return the user's event with the given public id, or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(MemoryEvent).filter_by(
                user_id=str(user_id), formation_id=self.formation_id, public_id=public_id
            )
            event = (await session.execute(stmt)).scalars().first()
            return event.to_dict() if event else None

    async def list_event_user_ids(self) -> List[str]:
        """Distinct user ids with events in this formation's log."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(MemoryEvent.user_id).filter_by(formation_id=self.formation_id).distinct()
            return [str(row[0]) for row in (await session.execute(stmt)).all()]

    async def count_events(self, user_id: str, include_deleted: bool = True) -> int:
        """Number of events in a user's log (size-cap accounting)."""
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(func.count())
                .select_from(MemoryEvent)
                .filter_by(user_id=str(user_id), formation_id=self.formation_id)
            )
            if not include_deleted:
                stmt = stmt.filter(MemoryEvent.deleted_at.is_(None))
            return int((await session.execute(stmt)).scalar() or 0)

    async def max_event_id(self, user_id: Optional[str] = None) -> int:
        """Highest event id in the log (0 when empty); optionally per user."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(func.max(MemoryEvent.id)).filter_by(formation_id=self.formation_id)
            if user_id is not None:
                stmt = stmt.filter_by(user_id=str(user_id))
            return int((await session.execute(stmt)).scalar() or 0)

    async def list_events(
        self,
        user_id: str,
        event_types: Optional[List[str]] = None,
        source: Optional[str] = None,
        after_id: Optional[int] = None,
        limit: Optional[int] = None,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return events in append order (the canonical replay ordering).

        Soft-deleted events are excluded unless ``include_deleted`` is set,
        so replaying the default listing yields the post-forgetting state.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = select(MemoryEvent).filter_by(
                user_id=str(user_id), formation_id=self.formation_id
            )
            if event_types:
                stmt = stmt.filter(MemoryEvent.event_type.in_(list(event_types)))
            if source:
                stmt = stmt.filter_by(source=source)
            if after_id is not None:
                stmt = stmt.filter(MemoryEvent.id > after_id)
            if not include_deleted:
                stmt = stmt.filter(MemoryEvent.deleted_at.is_(None))
            stmt = stmt.order_by(MemoryEvent.id.asc())
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    # ------------------------------------------------------------------
    # Soft delete + hard purge (GDPR / selective forgetting)
    # ------------------------------------------------------------------

    async def soft_delete_events(self, user_id: str, event_ids: List[int], reason: str) -> int:
        """Soft-delete the given events for a user; returns count marked."""
        if not event_ids:
            return 0
        now = utc_now_naive()
        marked = 0
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(MemoryEvent)
                .filter_by(user_id=str(user_id), formation_id=self.formation_id)
                .filter(MemoryEvent.id.in_(event_ids), MemoryEvent.deleted_at.is_(None))
            )
            for event in (await session.execute(stmt)).scalars().all():
                event.deleted_at = now
                event.deleted_reason = reason
                marked += 1
            await session.flush()
        return marked

    async def expire_volatile(self, now: Optional[datetime] = None) -> int:
        """
        Soft-delete live volatile events past their ``expires_at``.

        The expiry worker's write half (PRD "Decay Model"): once expired,
        a volatile event is filtered from replay listings exactly like a
        forgotten event, so the next rebuild drops whatever it projected.
        The soft-delete keeps the audit trail until the retention hard
        purge removes the row. Returns the number of events expired.
        """
        now = now or utc_now_naive()
        expired = 0
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(MemoryEvent)
                .filter_by(formation_id=self.formation_id)
                .filter(
                    MemoryEvent.expires_at.is_not(None),
                    MemoryEvent.expires_at <= now,
                    MemoryEvent.deleted_at.is_(None),
                )
            )
            for event in (await session.execute(stmt)).scalars().all():
                event.deleted_at = now
                event.deleted_reason = "expired"
                expired += 1
            await session.flush()
        return expired

    async def hard_purge(self, grace_period_days: int) -> int:
        """
        Physically remove soft-deleted events older than the grace period.

        Returns the number of rows purged.
        """
        cutoff = utc_now_naive() - timedelta(days=grace_period_days)
        async with self.db_manager.get_async_session() as session:
            stmt = (
                sql_delete(MemoryEvent)
                .where(MemoryEvent.formation_id == self.formation_id)
                .where(MemoryEvent.deleted_at.is_not(None))
                .where(MemoryEvent.deleted_at < cutoff)
            )
            result = await session.execute(stmt)
            return int(result.rowcount or 0)

    # ------------------------------------------------------------------
    # Projection checkpoints
    # ------------------------------------------------------------------

    async def get_checkpoint(self, projection_name: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Return the checkpoint for (projection, user), or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(ProjectionCheckpoint).filter_by(
                projection_name=projection_name,
                formation_id=self.formation_id,
                user_id=str(user_id),
            )
            checkpoint = (await session.execute(stmt)).scalar_one_or_none()
            return checkpoint.to_dict() if checkpoint else None

    async def set_checkpoint(
        self,
        projection_name: str,
        user_id: str,
        last_event_id: int,
        schema_version: int = 1,
    ) -> Dict[str, Any]:
        """Upsert the checkpoint cursor for (projection, user)."""
        user_id = str(user_id)
        now = utc_now_naive()
        async with self.db_manager.get_async_session() as session:
            stmt = select(ProjectionCheckpoint).filter_by(
                projection_name=projection_name,
                formation_id=self.formation_id,
                user_id=user_id,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                existing.last_event_id = last_event_id
                existing.last_applied_at = now
                existing.schema_version = schema_version
                await session.flush()
                return existing.to_dict()

            checkpoint = ProjectionCheckpoint(
                projection_name=projection_name,
                formation_id=self.formation_id,
                user_id=user_id,
                last_event_id=last_event_id,
                last_applied_at=now,
                schema_version=schema_version,
            )
            session.add(checkpoint)
            await session.flush()
            return checkpoint.to_dict()

    async def reset_checkpoint(self, projection_name: str, user_id: str) -> None:
        """Remove the checkpoint for (projection, user), if present."""
        async with self.db_manager.get_async_session() as session:
            stmt = (
                sql_delete(ProjectionCheckpoint)
                .where(ProjectionCheckpoint.projection_name == projection_name)
                .where(ProjectionCheckpoint.formation_id == self.formation_id)
                .where(ProjectionCheckpoint.user_id == str(user_id))
            )
            await session.execute(stmt)
