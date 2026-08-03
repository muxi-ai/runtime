# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Distillery Quota Store - Durable Daily Counters
# Description:  DB-backed increment-if-under-limit daily quota counters
# Role:         Replica-safe quota enforcement for distilled-batch intake
# Usage:        Used by MemoryDistilleryService's accept path
# Author:       Muxi Framework Team
#
# Durable replacement for the old in-process daily-count dict. The whole
# check-and-consume is ONE guarded upsert per backend:
#
#   INSERT ... ON CONFLICT (formation_id, distillery_id, quota_date)
#   DO UPDATE SET count = count + n WHERE count + n <= limit
#
# - PostgreSQL: ON CONFLICT DO UPDATE takes a row lock on the conflicting
#   counter row, so concurrent consumers (across replicas) serialize on it
#   and re-evaluate the WHERE against the committed count. rowcount == 0
#   means the guard rejected the increment.
# - SQLite: writers are serialized at the database level, so the same
#   statement is equally race-free; rowcount reporting matches.
#
# Either way there is no check-then-act window: a batch of N events
# consumes N atomically or not at all. Per-day rollover comes free from
# the quota_date key, and rows older than QUOTA_RETENTION_DAYS are pruned
# in the same transaction as a successful consume (no maintenance loop).
#
# Crash healing: a process that dies between reserve and settle leaves the
# counter durably inflated. The counter is a cache over ground truth (the
# memory_events table IS the count of accepted distilled events), so each
# process reconciles a (distillery, day) bucket downward to that truth
# before its first consume of the bucket (ensure_reconciled).
# =============================================================================

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Set, Tuple

from sqlalchemy import case, delete, func, select, update

from ....utils.datetime_utils import utc_now_naive
from ..events.models import MemoryEvent
from .models import QUOTA_RETENTION_DAYS, SOURCE_DISTILLERY, DistilleryQuotaCounter


class DistilleryQuotaStore:
    """Durable per-(distillery, UTC day) quota counters."""

    def __init__(self, db_manager, formation_id: str):
        """
        Initialize the store bound to a formation.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all rows.
        """
        self.db_manager = db_manager
        self.formation_id = formation_id
        # Buckets this process has already reconciled against ground truth
        # (crash healing runs once per bucket per process; see
        # ensure_reconciled).
        self._reconciled: Set[Tuple[str, str]] = set()
        self._reconcile_lock = asyncio.Lock()

    @staticmethod
    def today() -> str:
        """The current UTC day bucket ("YYYY-MM-DD")."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _insert(self):
        """The dialect-specific INSERT construct (both support upserts)."""
        if self.db_manager.database_type == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            return pg_insert(DistilleryQuotaCounter)
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert(DistilleryQuotaCounter)

    async def ensure_reconciled(self, distillery_id: str, quota_date: str) -> None:
        """Heal crash-leaked reservations, once per bucket per process.

        A process that dies after reserving but before settling leaves the
        counter durably inflated, which would starve the distillery with
        429s until day rollover. The memory_events table is ground truth
        for accepted distilled events, so before this process's first
        consume of a bucket the counter is capped at the day's actual
        live distilled-event count (a downward-only conditional update:
        it can shrink a leaked counter, never invent headroom beyond the
        real accepted count).

        Ordering makes this safe against in-flight reservations: it runs
        before this process's first consume of the bucket (so this process
        has none), and later calls are no-ops.

        Distilled rows do not record which distillery shipped them, so
        ground truth is the formation-wide distilled count: exact for the
        common single-distillery formation, a conservative upper bound
        (leak may persist) when several distilleries share a formation.
        """
        key = (distillery_id, quota_date)
        if key in self._reconciled:
            return
        async with self._reconcile_lock:
            if key in self._reconciled:
                return
            truth = await self._accepted_on_day(quota_date)
            async with self.db_manager.get_async_session() as session:
                await session.execute(
                    update(DistilleryQuotaCounter)
                    .where(
                        DistilleryQuotaCounter.formation_id == self.formation_id,
                        DistilleryQuotaCounter.distillery_id == distillery_id,
                        DistilleryQuotaCounter.quota_date == quota_date,
                        DistilleryQuotaCounter.count > truth,
                    )
                    .values(count=truth, updated_at=utc_now_naive())
                )
            self._reconciled.add(key)

    async def _accepted_on_day(self, quota_date: str) -> int:
        """Ground truth: live distilled events accepted on one UTC day."""
        day_start = datetime.strptime(quota_date, "%Y-%m-%d")
        day_end = day_start + timedelta(days=1)
        stmt = (
            select(func.count())
            .select_from(MemoryEvent)
            .where(
                MemoryEvent.formation_id == self.formation_id,
                MemoryEvent.source == SOURCE_DISTILLERY,
                MemoryEvent.deleted_at.is_(None),
                MemoryEvent.ingested_at >= day_start,
                MemoryEvent.ingested_at < day_end,
            )
        )
        async with self.db_manager.get_async_session() as session:
            return int((await session.execute(stmt)).scalar_one() or 0)

    async def try_consume(
        self, distillery_id: str, quota_date: str, count: int, limit: int
    ) -> bool:
        """Atomically consume ``count`` slots if the day stays within ``limit``.

        The check and the increment are one guarded upsert (see module
        docstring), so concurrent consumers -- other async tasks or other
        replicas sharing the database -- can never overshoot the limit.

        Returns:
            True when the slots were consumed, False when consuming would
            exceed the limit (nothing is consumed in that case).
        """
        if count <= 0:
            return True
        if count > limit:
            return False
        now = utc_now_naive()
        # inline() suppresses the implicit RETURNING id, so rowcount comes
        # from the plain command tag on both backends (0 when the guard
        # rejects the increment, 1 when the insert or update lands).
        stmt = (
            self._insert()
            .inline()
            .values(
                formation_id=self.formation_id,
                distillery_id=distillery_id,
                quota_date=quota_date,
                count=count,
                updated_at=now,
            )
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["formation_id", "distillery_id", "quota_date"],
            set_={
                "count": DistilleryQuotaCounter.count + count,
                "updated_at": now,
            },
            where=DistilleryQuotaCounter.count + count <= limit,
        )
        async with self.db_manager.get_async_session() as session:
            result = await session.execute(stmt)
            consumed = bool(result.rowcount)
            if consumed:
                # Retention rides the consume path: drop day buckets older
                # than the retention window in the same transaction, so the
                # table stays tiny without a dedicated maintenance loop.
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(days=QUOTA_RETENTION_DAYS)
                ).strftime("%Y-%m-%d")
                await session.execute(
                    delete(DistilleryQuotaCounter).where(
                        DistilleryQuotaCounter.formation_id == self.formation_id,
                        DistilleryQuotaCounter.quota_date < cutoff,
                        # Never drop the bucket just consumed, whatever its date.
                        DistilleryQuotaCounter.quota_date != quota_date,
                    )
                )
            return consumed

    async def release(self, distillery_id: str, quota_date: str, count: int) -> None:
        """Return ``count`` reserved-but-unused slots (floored at zero).

        Used when a reservation made for net-new events turns out larger
        than the events actually created (append-time duplicates).
        """
        if count <= 0:
            return
        stmt = (
            update(DistilleryQuotaCounter)
            .where(
                DistilleryQuotaCounter.formation_id == self.formation_id,
                DistilleryQuotaCounter.distillery_id == distillery_id,
                DistilleryQuotaCounter.quota_date == quota_date,
            )
            .values(
                count=case(
                    (
                        DistilleryQuotaCounter.count > count,
                        DistilleryQuotaCounter.count - count,
                    ),
                    else_=0,
                ),
                updated_at=utc_now_naive(),
            )
        )
        async with self.db_manager.get_async_session() as session:
            await session.execute(stmt)

    async def used(self, distillery_id: str, quota_date: str) -> int:
        """The consumed count for one (distillery, day), 0 when absent."""
        stmt = select(DistilleryQuotaCounter.count).where(
            DistilleryQuotaCounter.formation_id == self.formation_id,
            DistilleryQuotaCounter.distillery_id == distillery_id,
            DistilleryQuotaCounter.quota_date == quota_date,
        )
        async with self.db_manager.get_async_session() as session:
            value = (await session.execute(stmt)).scalar_one_or_none()
            return int(value or 0)
