# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Sync Scheduler - Remote Knowledge Sources
# Description:  Periodic re-sync + manual sync triggers for remote sources
# Role:         Phase 3 of the remote knowledge PRD (scheduling & automation)
# Usage:        Overlord creates one KnowledgeSyncService per formation and
#               registers it with the SchedulerService's periodic-task loop
# Author:       Muxi Framework Team
#
# This is NOT a second scheduler loop. Like the proactive heartbeat, the
# service registers with the existing SchedulerService via
# ``register_periodic_task``; the scheduler's worker cycle dispatches
# ``tick()`` onto the main event loop, and the service applies per-source
# cron gating itself (croniter, the same parser the scheduler and config
# validation already use).
#
# Guarantees:
# - Per-source locking: overlapping syncs for the same source are skipped
#   (KNOWLEDGE_SYNC_SKIPPED), whether triggered by schedule or manually.
# - Retry with exponential backoff on total sync failure (PRD section 9):
#   initial_delay * base^attempt, capped at max_delay, up to max_attempts;
#   exhausted retries fall back to the next cron fire.
# - Failure isolation: a scheduled sync failure emits events and degrades
#   to stale content - it can never break chat, job processing, or the
#   scheduler loop (tick() never raises).
# - Incremental re-embedding: after a sync that changed the mirror, only
#   the changed/deleted files are re-embedded via
#   ``KnowledgeHandler.refresh_remote_source``.
# =============================================================================

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .....services import observability
from .handler import (
    DEFAULT_RETRY_EXPONENTIAL_BASE,
    DEFAULT_RETRY_INITIAL_DELAY,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_RETRY_MAX_DELAY,
    SourceConfig,
)
from .sync import SyncManager, SyncResult

# Cron aliases accepted for ``schedule`` (config validation mirrors this
# set). ``@startup`` means "sync at formation startup only" - it is valid
# config but never periodic.
SCHEDULE_ALIASES = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
}
STARTUP_ONLY_SCHEDULE = "@startup"


def resolve_cron_expression(schedule: Optional[str]) -> Optional[str]:
    """Map a source ``schedule`` to a cron expression (None -> not periodic).

    Sources without a schedule, or with ``@startup``, sync only at
    formation startup (Phase 1 behavior preserved).
    """
    if not schedule or not isinstance(schedule, str):
        return None
    schedule = schedule.strip()
    if schedule == STARTUP_ONLY_SCHEDULE:
        return None
    return SCHEDULE_ALIASES.get(schedule, schedule)


@dataclass
class RetryPolicy:
    """Exponential backoff policy for failed scheduled syncs (PRD sec. 9)."""

    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    initial_delay: float = DEFAULT_RETRY_INITIAL_DELAY
    max_delay: float = DEFAULT_RETRY_MAX_DELAY
    exponential_base: float = DEFAULT_RETRY_EXPONENTIAL_BASE

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "RetryPolicy":
        return cls(
            max_attempts=int(config.get("max_attempts", DEFAULT_RETRY_MAX_ATTEMPTS)),
            initial_delay=float(config.get("initial_delay", DEFAULT_RETRY_INITIAL_DELAY)),
            max_delay=float(config.get("max_delay", DEFAULT_RETRY_MAX_DELAY)),
            exponential_base=float(config.get("exponential_base", DEFAULT_RETRY_EXPONENTIAL_BASE)),
        )

    def delay_for_attempt(self, attempt: int) -> float:
        """Backoff delay in seconds after the ``attempt``-th failure (1-based)."""
        delay = self.initial_delay * (self.exponential_base ** max(0, attempt - 1))
        return min(delay, self.max_delay)


@dataclass
class ScheduledSource:
    """Per-source scheduling state."""

    agent_id: str
    raw_source: Dict[str, Any]
    source_id: str
    cron: Optional[str]  # None -> manual-only (no periodic re-sync)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    next_fire: Optional[datetime] = None
    failed_attempts: int = 0


class KnowledgeSyncService:
    """Scheduled + manual re-sync of remote knowledge sources.

    Created by the overlord when any agent declares remote (url-based)
    knowledge sources; registered as a SchedulerService periodic task only
    when at least one source has a periodic schedule. Manual triggers
    (admin API) work either way.
    """

    def __init__(
        self,
        overlord: Any,
        agent_sources: Dict[str, List[Dict[str, Any]]],
        formation_id: str = "default-formation",
    ):
        """
        Args:
            overlord: The overlord (used to resolve agents lazily at sync
                time, so agent replacement never leaves a stale reference)
            agent_sources: agent_id -> list of raw remote source dicts
            formation_id: Formation id (mirror path resolution)
        """
        self.overlord = overlord
        self.formation_id = formation_id
        self._sources: List[ScheduledSource] = []
        self._locks: Dict[Tuple[str, str], asyncio.Lock] = {}

        now = datetime.now(timezone.utc)
        for agent_id, sources in agent_sources.items():
            for raw_source in sources:
                config = SourceConfig.from_dict(raw_source)
                cron = resolve_cron_expression(raw_source.get("schedule"))
                entry = ScheduledSource(
                    agent_id=agent_id,
                    raw_source=raw_source,
                    source_id=config.source_id,
                    cron=cron,
                    retry=RetryPolicy.from_dict(config.retry),
                )
                if cron is not None:
                    # Startup already synced this source (prepare_sources),
                    # so the first periodic fire is the next cron slot.
                    entry.next_fire = self._next_cron_fire(cron, now)
                self._sources.append(entry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def has_scheduled_sources(self) -> bool:
        """Whether any source re-syncs periodically."""
        return any(entry.cron is not None for entry in self._sources)

    @property
    def scheduled_source_count(self) -> int:
        return sum(1 for entry in self._sources if entry.cron is not None)

    def sources_for_agent(self, agent_id: str) -> List[ScheduledSource]:
        return [entry for entry in self._sources if entry.agent_id == agent_id]

    async def tick(self, now: Optional[datetime] = None) -> None:
        """Scheduler-cycle hook: re-sync every source whose schedule is due.

        Never raises. Sources are processed sequentially; the per-source
        locks make concurrent ticks (or manual triggers) skip rather than
        overlap.
        """
        try:
            now = now or datetime.now(timezone.utc)
            for entry in self._sources:
                if entry.next_fire is None or now < entry.next_fire:
                    continue
                await self._run_scheduled_sync(entry, now)
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SYNC_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Knowledge sync tick failed (isolated): {e}",
                data={"error": str(e), "error_type": type(e).__name__, "phase": "tick"},
            )

    async def sync_now(
        self, agent_id: str, source_id: Optional[str] = None, trigger: str = "manual"
    ) -> List[Dict[str, Any]]:
        """Manually trigger a sync for an agent's remote sources.

        Args:
            agent_id: Agent whose sources to sync
            source_id: Optional single source id; None syncs all of the
                agent's remote sources
            trigger: Trigger label for observability events

        Returns:
            One summary dict per source (status "skipped" when a sync for
            that source was already in flight)

        Raises:
            KeyError: unknown agent_id/source_id combination
        """
        entries = self.sources_for_agent(agent_id)
        if source_id is not None:
            entries = [entry for entry in entries if entry.source_id == source_id]
        if not entries:
            if source_id is not None:
                raise KeyError(
                    f"No remote knowledge source '{source_id}' registered "
                    f"for agent '{agent_id}'"
                )
            raise KeyError(f"No remote knowledge sources registered for agent '{agent_id}'")

        results: List[Dict[str, Any]] = []
        for entry in entries:
            result = await self._sync_and_reingest(entry, trigger=trigger)
            if result is None:
                results.append(
                    {
                        "source_id": entry.source_id,
                        "url": entry.raw_source.get("url", ""),
                        "status": "skipped",
                        "reason": "sync already in progress",
                    }
                )
            else:
                results.append(
                    {
                        "source_id": result.source_id,
                        "url": result.url,
                        "status": result.status,
                        "files_added": result.files_added,
                        "files_modified": result.files_modified,
                        "files_deleted": result.files_deleted,
                        "files_failed": result.files_failed,
                        "bytes_downloaded": result.bytes_downloaded,
                        "duration_ms": result.duration_ms,
                        "error": result.error,
                    }
                )
        return results

    # ------------------------------------------------------------------
    # Scheduling internals
    # ------------------------------------------------------------------

    async def _run_scheduled_sync(self, entry: ScheduledSource, now: datetime) -> None:
        """Run one due scheduled sync and update the entry's schedule state."""
        result = await self._sync_and_reingest(entry, trigger="scheduled")
        if result is None:
            # Lock contention: leave next_fire as-is; the in-flight sync
            # owns this slot and the next tick re-evaluates.
            return

        if result.status == "failed":
            entry.failed_attempts += 1
            if entry.failed_attempts < entry.retry.max_attempts:
                delay = entry.retry.delay_for_attempt(entry.failed_attempts)
                entry.next_fire = now + timedelta(seconds=delay)
                observability.observe(
                    event_type=observability.ErrorEvents.KNOWLEDGE_SYNC_FAILED,
                    level=observability.EventLevel.WARNING,
                    description=(
                        f"Scheduled knowledge sync failed - retrying in {delay:.0f}s "
                        f"(attempt {entry.failed_attempts}/{entry.retry.max_attempts})"
                    ),
                    data={
                        "source_id": entry.source_id,
                        "agent_id": entry.agent_id,
                        "attempt": entry.failed_attempts,
                        "max_attempts": entry.retry.max_attempts,
                        "retry_in_seconds": delay,
                        "retry_at": entry.next_fire.isoformat(),
                        "phase": "retry_scheduled",
                    },
                )
                return
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SYNC_FAILED,
                level=observability.EventLevel.ERROR,
                description=(
                    "Scheduled knowledge sync retries exhausted - waiting for next "
                    "scheduled run (stale content remains served)"
                ),
                data={
                    "source_id": entry.source_id,
                    "agent_id": entry.agent_id,
                    "attempts": entry.failed_attempts,
                    "phase": "retries_exhausted",
                },
            )

        entry.failed_attempts = 0
        entry.next_fire = self._next_cron_fire(entry.cron, now)

    async def _sync_and_reingest(
        self, entry: ScheduledSource, trigger: str
    ) -> Optional[SyncResult]:
        """Lock-guarded sync + incremental re-embed for one source.

        Returns None when the source's lock is already held (overlapping
        syncs are skipped, PRD section 7).
        """
        lock = self._locks.setdefault((entry.agent_id, entry.source_id), asyncio.Lock())
        if lock.locked():
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SYNC_SKIPPED,
                level=observability.EventLevel.INFO,
                description="Knowledge sync skipped - previous sync still running",
                data={
                    "source_id": entry.source_id,
                    "agent_id": entry.agent_id,
                    "trigger": trigger,
                },
            )
            return None

        async with lock:
            sync_manager = SyncManager(agent_id=entry.agent_id, formation_id=self.formation_id)
            result = await sync_manager.sync_source(dict(entry.raw_source), trigger=trigger)
            if result.status != "failed" and result.has_changes:
                await self._reingest_changes(entry, sync_manager, result)
            return result

    async def _reingest_changes(
        self, entry: ScheduledSource, sync_manager: SyncManager, result: SyncResult
    ) -> None:
        """Re-embed only the files this sync changed (failure isolated)."""
        try:
            agent = getattr(self.overlord, "agents", {}).get(entry.agent_id)
            handler = getattr(agent, "knowledge_handler", None) if agent else None
            if handler is None:
                return
            config = SourceConfig.from_dict(entry.raw_source)
            source_config = sync_manager.synthetic_local_source(config, result)
            changed = [os.path.join(result.content_dir, rel) for rel in result.changed_paths]
            deleted = [os.path.join(result.content_dir, rel) for rel in result.deleted_paths]
            await handler.refresh_remote_source(source_config, changed, deleted)
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SYNC_FAILED,
                level=observability.EventLevel.ERROR,
                description=(
                    "Re-embedding synced knowledge changes failed - previously "
                    f"embedded content remains served: {e}"
                ),
                data={
                    "source_id": entry.source_id,
                    "agent_id": entry.agent_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "phase": "reingest",
                },
            )

    @staticmethod
    def _next_cron_fire(cron: Optional[str], now: datetime) -> Optional[datetime]:
        """Next fire time for a cron expression after ``now`` (UTC)."""
        if not cron:
            return None
        from croniter import croniter

        return croniter(cron, now).get_next(datetime)
