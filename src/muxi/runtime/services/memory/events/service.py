# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Event Service - Substrate Coordination
# Description:  Failure-isolated event recording, projector registry, rebuild
# Role:         Formation-level service owning the memory event substrate
# Usage:        Created in formation initialization, driven by the Overlord
# Author:       Muxi Framework Team
#
# Memory Event Substrate. Coordinates:
#
# 1. Recording: ``record`` is the failure-isolated append every memory write
#    path calls alongside its existing direct projection write (the PRD's
#    Phase A dual-write posture). An append failure is logged and swallowed
#    -- the projection write and the chat turn are never affected.
# 2. Projector registry: projections register a projector (apply + reset +
#    event_types); the registry is the extension point for later
#    projections (Knowledge Index) without event-schema changes.
# 3. Rebuild: full re-projection per user -- wipe the projection, replay
#    its events in append order through the same upsert code the live path
#    uses, then checkpoint. This is the PRD's replay promise.
# 4. Selective forgetting: ``forget_source`` soft-deletes every live event
#    from a source and records the user.deletion audit event; a background
#    hard-purge loop (Phase 1 lifecycle pattern: started by the Overlord
#    next to the scheduler, cancelled on shutdown) removes soft-deleted
#    events after the retention grace period.
# =============================================================================

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ... import observability
from .models import DECAY_STATIC, EVENT_USER_DELETION, SOURCE_USER_EDIT
from .storage import MemoryEventStorage

# PRD defaults (Configuration Reference -> memory.events.retention).
DEFAULT_GRACE_PERIOD_DAYS = 30

# Hard-purge cadence. Soft-deleted events only become purgeable after the
# multi-day grace period, so a daily sweep is more than frequent enough.
PURGE_INTERVAL_SECONDS = 86400.0


class MemoryEventService:
    """Owns the memory event log, projector registry, and rebuild path."""

    def __init__(self, db_manager, formation_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the memory event service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all event rows.
            config: The ``memory.events`` formation config section.
        """
        config = config or {}
        retention = config.get("retention") or {}

        self.formation_id = formation_id
        self.enabled = config.get("enabled", True)
        self.grace_period_days = int(retention.get("grace_period_days", DEFAULT_GRACE_PERIOD_DAYS))

        self.db_manager = db_manager
        self.storage = MemoryEventStorage(db_manager, formation_id)
        self.projectors: Dict[str, Any] = {}
        self._purge_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Projector registry
    # ------------------------------------------------------------------

    def register_projector(self, projector) -> None:
        """Register a projection builder under its ``name``."""
        self.projectors[projector.name] = projector

    # ------------------------------------------------------------------
    # Recording (failure-isolated dual-write append)
    # ------------------------------------------------------------------

    async def record(
        self,
        user_id: Any,
        event_type: str,
        payload: Dict[str, Any],
        source: str,
        source_id: Optional[str] = None,
        source_confidence: float = 1.0,
        occurred_at: Optional[datetime] = None,
        caused_by: Optional[int] = None,
        decay_rate: str = DECAY_STATIC,
        expires_at: Optional[datetime] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Append one event to the log; never raises.

        Returns the event dict (existing one on an idempotent duplicate),
        or None when the substrate is disabled or the append failed. A
        None return must never affect the caller's own write path.
        """
        if not self.enabled:
            return None
        try:
            event, created = await self.storage.append(
                user_id=str(user_id),
                event_type=event_type,
                payload=payload,
                source=source,
                source_id=source_id,
                source_confidence=source_confidence,
                occurred_at=occurred_at,
                caused_by=caused_by,
                decay_rate=decay_rate,
                expires_at=expires_at,
                agent_id=agent_id,
                conversation_id=conversation_id,
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_EVENT_APPEND_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "user_id": str(user_id),
                    "memory_event_type": event_type,
                    "source": source,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Memory event append failed: {e}",
            )
            return None

        if created:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_EVENT_APPENDED,
                level=observability.EventLevel.DEBUG,
                data={
                    "user_id": str(user_id),
                    "memory_event_id": event["id"],
                    "memory_event_type": event_type,
                    "source": source,
                },
                description=f"Memory event appended: {event_type}",
            )
        else:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_EVENT_IDEMPOTENT_SKIP,
                level=observability.EventLevel.DEBUG,
                data={
                    "user_id": str(user_id),
                    "memory_event_id": event["id"],
                    "memory_event_type": event_type,
                    "source": source,
                    "source_id": source_id,
                },
                description=f"Duplicate memory event skipped: {event_type}",
            )
        return event

    # ------------------------------------------------------------------
    # Rebuild (full re-projection from the event log)
    # ------------------------------------------------------------------

    async def rebuild(
        self,
        user_id: Any,
        projection: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Rebuild one or all projections for a user from the event log.

        For each target projection: wipe the user's derived state, replay
        the projection's events in append order through the same upsert
        path the live dual-write uses, and record the checkpoint. With
        ``dry_run`` the projection is untouched and only the event counts
        that would be replayed are reported.

        Returns:
            {projection_name: {"events": n, "applied": n, "failed": n}}

        Raises:
            ValueError: When the substrate is disabled or the requested
                projection is unknown.
        """
        if not self.enabled:
            raise ValueError("Memory event substrate is disabled for this formation")
        user_id = str(user_id)

        if projection is not None and projection not in self.projectors:
            raise ValueError(
                f"Unknown projection {projection!r}; registered: {sorted(self.projectors)}"
            )
        names = [projection] if projection else sorted(self.projectors)

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_REBUILD_STARTED,
            level=observability.EventLevel.INFO,
            data={"user_id": user_id, "projections": names, "dry_run": dry_run},
            description=f"Memory projection rebuild started for {', '.join(names)}",
        )

        report: Dict[str, Dict[str, Any]] = {}
        for name in names:
            projector = self.projectors[name]
            events = await self.storage.list_events(
                user_id, event_types=list(projector.event_types)
            )
            if dry_run:
                report[name] = {"events": len(events), "applied": 0, "failed": 0, "dry_run": True}
                continue

            await projector.reset(user_id)
            await self.storage.reset_checkpoint(name, user_id)

            applied = 0
            failed = 0
            for event in events:
                try:
                    await projector.apply(event)
                    applied += 1
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_PROJECTION_APPLIED,
                        level=observability.EventLevel.DEBUG,
                        data={
                            "user_id": user_id,
                            "projection": name,
                            "memory_event_id": event["id"],
                            "memory_event_type": event["event_type"],
                        },
                        description=f"Replayed event {event['id']} into {name}",
                    )
                except Exception as e:
                    failed += 1
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_PROJECTION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "user_id": user_id,
                            "projection": name,
                            "memory_event_id": event["id"],
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                        description=f"Replay of event {event['id']} into {name} failed: {e}",
                    )
            if events:
                await self.storage.set_checkpoint(name, user_id, last_event_id=events[-1]["id"])
            report[name] = {"events": len(events), "applied": applied, "failed": failed}

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_REBUILD_COMPLETED,
            level=observability.EventLevel.INFO,
            data={"user_id": user_id, "report": report, "dry_run": dry_run},
            description="Memory projection rebuild completed",
        )
        return report

    # ------------------------------------------------------------------
    # Selective forgetting (GDPR groundwork)
    # ------------------------------------------------------------------

    async def forget_source(
        self, user_id: Any, source: str, reason: str = "user_request"
    ) -> Dict[str, Any]:
        """
        Soft-delete every live event from a source for a user.

        Records the ``user.deletion`` audit event, marks the targets
        deleted, and reports which projections should be rebuilt for the
        forgetting to take effect in derived state.
        """
        user_id = str(user_id)
        events = await self.storage.list_events(user_id, source=source)
        target_ids = [event["id"] for event in events]
        deleted = await self.storage.soft_delete_events(user_id, target_ids, reason)
        await self.record(
            user_id=user_id,
            event_type=EVENT_USER_DELETION,
            payload={"reason": reason, "source": source, "target_event_ids": target_ids},
            source=SOURCE_USER_EDIT,
        )
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_DELETION_REQUESTED,
            level=observability.EventLevel.INFO,
            data={
                "user_id": user_id,
                "source": source,
                "reason": reason,
                "deleted_events": deleted,
            },
            description=f"Soft-deleted {deleted} memory events from source {source!r}",
        )
        return {
            "deleted_events": deleted,
            "rebuild_required": sorted(self.projectors),
        }

    # ------------------------------------------------------------------
    # Hard-purge background loop (Phase 1 lifecycle pattern)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic hard-purge loop for soft-deleted events."""
        if not self.enabled:
            return
        if self._purge_task is not None and not self._purge_task.done():
            return
        self._purge_task = asyncio.create_task(self._purge_loop())

    async def stop(self) -> None:
        """Cancel the hard-purge loop, if running."""
        if self._purge_task is not None:
            self._purge_task.cancel()
            try:
                await self._purge_task
            except asyncio.CancelledError:
                pass
            self._purge_task = None

    async def _purge_loop(self) -> None:
        """Sleep-run loop for the retention hard purge."""
        while True:
            await asyncio.sleep(PURGE_INTERVAL_SECONDS)
            try:
                await self.run_hard_purge()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "error_type": type(e).__name__, "pass": "hard_purge"},
                    description=f"Memory event hard purge failed: {e}",
                )

    async def run_hard_purge(self) -> int:
        """Hard-delete soft-deleted events past the grace period."""
        purged = await self.storage.hard_purge(self.grace_period_days)
        if purged:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_DELETION_HARD_PURGED,
                level=observability.EventLevel.INFO,
                data={"purged_events": purged, "grace_period_days": self.grace_period_days},
                description=f"Hard-purged {purged} soft-deleted memory events",
            )
        return purged

    # ------------------------------------------------------------------
    # Read surface (event listing for tests / provenance drill-down)
    # ------------------------------------------------------------------

    async def list_events(self, user_id: Any, **kwargs) -> List[Dict[str, Any]]:
        """List a user's events in append order (see storage.list_events)."""
        return await self.storage.list_events(str(user_id), **kwargs)
