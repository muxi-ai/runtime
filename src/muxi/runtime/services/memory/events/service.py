# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Event Service - Substrate Coordination
# Description:  Failure-isolated event recording, projection, rebuild, GDPR
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
# 3. Incremental projection (Phase 2b): per-(projection, user) cursors in
#    ``projection_checkpoints``. ``apply_event`` projects one event on the
#    event-first write path; ``project_pending`` catches a cursor up to the
#    log tail (crash recovery / background applier). Both are idempotent at
#    the cursor level: an event behind the cursor is never re-applied.
# 4. Event-first cutover (Phase C groundwork, flag-gated, DEFAULT OFF):
#    with ``memory.events.event_first: true`` the write paths append the
#    event and skip their direct projection write; projections are derived
#    exclusively through the projectors. Dual-write remains the default
#    until cutover.
# 5. Rebuild: full re-projection per user -- wipe the projection, replay
#    its events in append order through the same upsert code the live path
#    uses, then checkpoint. This is the PRD's replay promise.
# 6. Provenance (Phase 2c): ``provenance_chain`` walks caused_by links so
#    "why do you think X?" resolves any projection row to the interaction
#    (or ingestion) that produced it.
# 7. Selective forgetting / GDPR: ``forget_source`` soft-deletes every live
#    event from a source and records the user.deletion audit event; replay
#    skips soft-deleted events, so a rebuild recomputes projections as if
#    the source never existed. The maintenance loop expires volatile
#    events, hard-purges soft-deleted events past the retention grace
#    period, and raises the per-user event-log size-cap alert.
# 8. Legacy backfill (Phase B): ``backfill_user`` asks each projector to
#    synthesize ``source='legacy'`` events for pre-event-log rows so old
#    data becomes replayable and provenance-complete. Bounded per pass
#    (BACKFILL_MAX_ROWS_PER_PASS in projectors.py) with persisted resume
#    cursors -- large legacy tables need multiple passes.
# =============================================================================

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ... import observability
from .decay import DecaySettings
from .models import DECAY_STATIC, DECAY_VOLATILE, EVENT_USER_DELETION, SOURCE_USER_EDIT
from .projectors import contradiction_payloads
from .storage import MemoryEventStorage

# PRD defaults (Configuration Reference -> memory.events.retention).
DEFAULT_GRACE_PERIOD_DAYS = 30

# Maintenance cadence (volatile expiry + hard purge + size-cap check).
# Volatile TTLs default to 24h, so an hourly sweep keeps expiry timely;
# purgeable rows only appear after the multi-day grace period.
MAINTENANCE_INTERVAL_SECONDS = 3600.0

# Incremental applier defaults (memory.projections in the formation YAML).
DEFAULT_APPLY_INTERVAL_SECONDS = 5.0
DEFAULT_LAG_ALERT_THRESHOLD_SECONDS = 300.0
# Max events applied per lock acquisition in ``project_pending``. The
# projection lock is released and reacquired between chunks so a long
# catch-up batch never starves concurrent event-first writers
# (``apply_event`` shares the same lock). Cursor correctness across the
# release: each chunk re-reads its checkpoint under the lock before
# listing events, so work done by an interleaved apply_event is never
# re-applied and no event is skipped.
DEFAULT_PROJECT_BATCH_SIZE = 500


class MemoryEventService:
    """Owns the memory event log, projector registry, and rebuild path."""

    def __init__(
        self,
        db_manager,
        formation_id: str,
        config: Optional[Dict[str, Any]] = None,
        projections_config: Optional[Dict[str, Any]] = None,
        decay: Optional[DecaySettings] = None,
    ):
        """
        Initialize the memory event service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all event rows.
            config: The ``memory.events`` formation config section.
            projections_config: The ``memory.projections`` section
                (incremental applier interval + lag alert threshold).
            decay: Validated ``memory.decay`` settings (built in formation
                init; a default instance is created when omitted).

        Raises:
            ValueError: On invalid configuration (fail-fast policy).
        """
        config = config or {}
        retention = config.get("retention") or {}
        projections_config = projections_config or {}

        self.formation_id = formation_id
        self.enabled = config.get("enabled", True)
        self.event_first = bool(config.get("event_first", False))
        self.grace_period_days = int(retention.get("grace_period_days", DEFAULT_GRACE_PERIOD_DAYS))
        if self.grace_period_days < 0:
            raise ValueError("memory.events.retention.grace_period_days must be >= 0")
        self.max_events_per_user = _optional_positive_int(
            retention.get("max_events_per_user"), "memory.events.retention.max_events_per_user"
        )
        self.apply_interval_seconds = _positive_float(
            projections_config.get("apply_interval_seconds", DEFAULT_APPLY_INTERVAL_SECONDS),
            "memory.projections.apply_interval_seconds",
        )
        self.lag_alert_threshold_seconds = _positive_float(
            projections_config.get(
                "lag_alert_threshold_seconds", DEFAULT_LAG_ALERT_THRESHOLD_SECONDS
            ),
            "memory.projections.lag_alert_threshold_seconds",
        )
        self.project_batch_size = _positive_int(
            projections_config.get("batch_size", DEFAULT_PROJECT_BATCH_SIZE),
            "memory.projections.batch_size",
        )
        self.decay = decay if decay is not None else DecaySettings()

        self.db_manager = db_manager
        self.storage = MemoryEventStorage(db_manager, formation_id)
        self.projectors: Dict[str, Any] = {}
        self._maintenance_task: Optional[asyncio.Task] = None
        self._applier_task: Optional[asyncio.Task] = None
        # Serializes projection application (incremental vs applier vs
        # rebuild) so one event is never applied twice concurrently.
        self._projection_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Projector registry
    # ------------------------------------------------------------------

    def register_projector(self, projector) -> None:
        """Register a projection builder under its ``name``."""
        self.projectors[projector.name] = projector

    def _projector_for_event(self, event_type: str):
        """The registered projector consuming ``event_type``, or None."""
        for projector in self.projectors.values():
            if event_type in projector.event_types:
                return projector
        return None

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
        event_version: int = 1,
        occurred_at: Optional[datetime] = None,
        caused_by: Optional[int] = None,
        decay_rate: str = DECAY_STATIC,
        expires_at: Optional[datetime] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Append one event to the log; never raises.

        ``scope_type`` / ``scope_id`` record the memory namespace of the
        projection write (shared-scope writes pass their true scope so
        replay reproduces scoped rows); None keeps the implicit user scope.
        Volatile events without an explicit ``expires_at`` default to
        occurred_at + memory.decay.volatile_default_ttl_hours.

        Returns the event dict (existing one on an idempotent duplicate),
        or None when the substrate is disabled or the append failed. A
        None return must never affect the caller's own write path.
        """
        if not self.enabled:
            return None
        if decay_rate == DECAY_VOLATILE and expires_at is None:
            from ....utils.datetime_utils import utc_now_naive

            base = occurred_at or utc_now_naive()
            expires_at = base + timedelta(hours=self.decay.volatile_ttl_hours)
        try:
            event, created = await self.storage.append(
                user_id=str(user_id),
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
    # Incremental projection (Phase 2b: cursors + event-first apply)
    # ------------------------------------------------------------------

    async def apply_event(self, event: Dict[str, Any]):
        """
        Project one just-appended event on the event-first write path.

        Failure-isolated: an apply failure is logged and the cursor is NOT
        advanced, leaving the event pending for the background applier's
        next ``project_pending`` pass. Contradictions detected during the
        apply are recorded as fact.contradicted audit events.

        Returns the projector's apply result on success (True when the
        event type has no projector or the cursor already passed it), or
        None on failure.
        """
        projector = self._projector_for_event(event["event_type"])
        if projector is None:
            return True
        name = projector.name
        user_id = str(event["user_id"])
        try:
            async with self._projection_lock:
                checkpoint = await self.storage.get_checkpoint(name, user_id)
                if checkpoint is not None and checkpoint["last_event_id"] >= event["id"]:
                    return True  # already applied (cursor-level idempotency)
                result = await projector.apply(event)
                await self.storage.set_checkpoint(name, user_id, last_event_id=event["id"])
            await self.record_contradictions(event, result)
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_PROJECTION_APPLIED,
                level=observability.EventLevel.DEBUG,
                data={
                    "user_id": user_id,
                    "projection": name,
                    "memory_event_id": event["id"],
                    "memory_event_type": event["event_type"],
                },
                description=f"Applied event {event['id']} to {name}",
            )
            return result if result is not None else True
        except Exception as e:
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
                description=f"Applying event {event['id']} to {name} failed: {e}",
            )
            return None

    async def project_pending(self, user_id: Optional[Any] = None) -> Dict[str, Dict[str, Any]]:
        """
        Catch every projection cursor up to the event-log tail.

        For each registered projector (and each user, unless one is
        given): read the cursor, apply the projector's live events past
        it in append order, advance the cursor. A missing cursor means
        "from the start" -- ``start()`` snapshots cursors to the log tail
        before enabling the event-first applier, so dual-written history
        is never re-applied. Per-event failures are logged and skipped
        (the cursor still advances; a rebuild reconciles), keeping one
        poison event from wedging the projection forever.

        Lock hold discipline: events are applied in chunks of at most
        ``memory.projections.batch_size`` per lock acquisition, with the
        checkpoint advanced at the end of every chunk. The lock is
        released between chunks so a long catch-up batch never stalls
        concurrent event-first writers, and a crash between chunks
        resumes from the last checkpointed chunk boundary -- every chunk
        re-reads its cursor under the lock, so no event is skipped or
        re-applied across the boundary.

        Returns {projection: {user: {"events": n, "applied": n, "failed": n}}}.
        """
        users = [str(user_id)] if user_id is not None else await self.storage.list_event_user_ids()
        report: Dict[str, Dict[str, Any]] = {}
        for name in sorted(self.projectors):
            projector = self.projectors[name]
            per_user: Dict[str, Any] = {}
            for uid in users:
                totals = {"events": 0, "applied": 0, "failed": 0}
                while True:
                    chunk_size = await self._project_pending_chunk(name, projector, uid, totals)
                    if chunk_size < self.project_batch_size:
                        break
                if totals["events"]:
                    per_user[uid] = totals
            if per_user:
                report[name] = per_user
        return report

    async def _project_pending_chunk(
        self, name: str, projector, uid: str, totals: Dict[str, int]
    ) -> int:
        """Apply one bounded chunk of pending events under the lock.

        Reads the cursor, applies at most ``project_batch_size`` events
        past it, and checkpoints the chunk tail -- all while holding the
        projection lock, which is released when this returns so writers
        can interleave between chunks. Returns the number of events the
        chunk contained (a short chunk means the cursor reached the log
        tail).
        """
        async with self._projection_lock:
            checkpoint = await self.storage.get_checkpoint(name, uid)
            after_id = checkpoint["last_event_id"] if checkpoint else None
            events = await self.storage.list_events(
                uid,
                event_types=list(projector.event_types),
                after_id=after_id,
                limit=self.project_batch_size,
            )
            for event in events:
                try:
                    result = await projector.apply(event)
                    totals["applied"] += 1
                except Exception as e:
                    totals["failed"] += 1
                    result = None
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_PROJECTION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "user_id": uid,
                            "projection": name,
                            "memory_event_id": event["id"],
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                        description=f"Applying event {event['id']} to {name} failed: {e}",
                    )
                if result:
                    await self.record_contradictions(event, result)
            if events:
                await self.storage.set_checkpoint(name, uid, last_event_id=events[-1]["id"])
        totals["events"] += len(events)
        return len(events)

    async def record_contradictions(
        self, event: Dict[str, Any], result: Optional[Dict[str, Any]]
    ) -> None:
        """Record fact.contradicted audit events from one apply result.

        Live-path only (never called on rebuild replay): the conflict
        marking itself is part of the deterministic apply, so these events
        are provenance, not state. Idempotent through a per-pair
        source_id.
        """
        from .models import EVENT_FACT_CONTRADICTED

        for payload in contradiction_payloads(result):
            source_id = (
                "contradiction/"
                f"{payload.get('existing_relationship_public_id')}/"
                f"{payload.get('new_relationship_public_id')}"
            )
            await self.record(
                user_id=event["user_id"],
                event_type=EVENT_FACT_CONTRADICTED,
                payload=payload,
                source=event["source"],
                source_id=source_id,
                caused_by=event["id"],
            )
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_FACT_CONTRADICTED,
                level=observability.EventLevel.INFO,
                data={"user_id": str(event["user_id"]), **payload},
                description=(
                    f"Contradiction on {payload.get('relationship_type')!r}: "
                    f"{payload.get('detection')}"
                ),
            )

    async def snapshot_cursors_to_tail(self) -> None:
        """Initialize missing cursors to the current log tail.

        Event-first cutover guard: every event already in the log was
        dual-written directly to its projection, so the applier must not
        replay it (the flat-fact projection would duplicate rows).
        Cursors that already exist are left alone.
        """
        tail = await self.storage.max_event_id()
        for uid in await self.storage.list_event_user_ids():
            for name in self.projectors:
                if await self.storage.get_checkpoint(name, uid) is None:
                    await self.storage.set_checkpoint(name, uid, last_event_id=tail)

    async def _applier_loop(self) -> None:
        """Background incremental applier (event-first mode only)."""
        while True:
            await asyncio.sleep(self.apply_interval_seconds)
            try:
                await self.project_pending()
                await self._check_projection_lag()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "error_type": type(e).__name__, "pass": "applier"},
                    description=f"Memory projection applier pass failed: {e}",
                )

    async def _check_projection_lag(self) -> None:
        """Alert when a projection cursor falls behind the event tail."""
        from ....utils.datetime_utils import utc_now_naive

        now = utc_now_naive()
        for uid in await self.storage.list_event_user_ids():
            for name, projector in self.projectors.items():
                checkpoint = await self.storage.get_checkpoint(name, uid)
                after_id = checkpoint["last_event_id"] if checkpoint else None
                pending = await self.storage.list_events(
                    uid, event_types=list(projector.event_types), after_id=after_id, limit=1
                )
                if not pending:
                    continue
                oldest = pending[0]
                ingested_at = oldest.get("ingested_at")
                if isinstance(ingested_at, str):
                    try:
                        ingested_at = datetime.fromisoformat(ingested_at)
                    except ValueError:
                        continue
                if ingested_at is None:
                    continue
                lag = (now - ingested_at).total_seconds()
                if lag >= self.lag_alert_threshold_seconds:
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_PROJECTION_LAGGING,
                        level=observability.EventLevel.WARNING,
                        data={
                            "user_id": uid,
                            "projection": name,
                            "oldest_pending_event_id": oldest["id"],
                            "lag_seconds": round(lag, 1),
                            "threshold_seconds": self.lag_alert_threshold_seconds,
                        },
                        description=(
                            f"Projection {name} is {lag:.0f}s behind the event log "
                            f"for user {uid}"
                        ),
                    )

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
            async with self._projection_lock:
                events = await self.storage.list_events(
                    user_id, event_types=list(projector.event_types)
                )
                if dry_run:
                    report[name] = {
                        "events": len(events),
                        "applied": 0,
                        "failed": 0,
                        "dry_run": True,
                    }
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
    # Legacy backfill (Phase B: synthetic events for pre-event-log rows)
    # ------------------------------------------------------------------

    async def backfill_user(self, user_id: Any) -> Dict[str, Dict[str, Any]]:
        """
        Synthesize legacy events for a user's pre-event-log projection rows.

        Each projector that supports backfill scans its projection for
        rows without event provenance and appends ``source='legacy'``
        events keyed per row, so re-running is idempotent. Graph, log,
        and artifact rows are stamped in place; flat-fact rows become
        provenance-complete on the next rebuild (their write path inserts
        rather than upserts).

        BOUNDED PER PASS: each projector scans at most
        ``BACKFILL_MAX_ROWS_PER_PASS`` rows per table per call (see
        projectors.py), persisting a resume cursor in
        ``projection_checkpoints``. A projection whose report says
        ``complete: false`` still has unscanned rows -- call again until
        every projection reports ``complete: true``.

        Returns {projection_name: {"synthesized": n, "complete": bool}}.

        Raises:
            ValueError: When the substrate is disabled.
        """
        if not self.enabled:
            raise ValueError("Memory event substrate is disabled for this formation")
        user_id = str(user_id)
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_BACKFILL_STARTED,
            level=observability.EventLevel.INFO,
            data={"user_id": user_id, "projections": sorted(self.projectors)},
            description=f"Legacy memory backfill started for user {user_id}",
        )
        report: Dict[str, Dict[str, Any]] = {}
        for name in sorted(self.projectors):
            backfill = getattr(self.projectors[name], "backfill", None)
            if backfill is None:
                continue
            report[name] = await backfill(user_id, self)
        incomplete = sorted(name for name, entry in report.items() if not entry["complete"])
        if incomplete:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_BACKFILL_COMPLETED,
                level=observability.EventLevel.WARNING,
                data={"user_id": user_id, "report": report, "incomplete": incomplete},
                description=(
                    f"Legacy memory backfill pass hit its per-pass row bound for "
                    f"{', '.join(incomplete)}; run another pass to continue"
                ),
            )
        else:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_BACKFILL_COMPLETED,
                level=observability.EventLevel.INFO,
                data={"user_id": user_id, "report": report},
                description=f"Legacy memory backfill completed for user {user_id}",
            )
        return report

    # ------------------------------------------------------------------
    # Provenance (Phase 2c: "why do you think X?")
    # ------------------------------------------------------------------

    async def provenance_chain(
        self, user_id: Any, event_id: int, max_depth: int = 10
    ) -> List[Dict[str, Any]]:
        """
        The causation chain for one event, root-first.

        Walks ``caused_by`` links up to ``max_depth`` ancestors (cycles
        and cross-user references are cut). The returned list ends with
        the requested event; earlier entries are its causes, so the first
        entry is the origin (typically the interaction.turn or raw
        ingestion event).
        """
        user_id = str(user_id)
        chain: List[Dict[str, Any]] = []
        seen = set()
        current: Optional[int] = event_id
        while current is not None and current not in seen and len(chain) < max_depth:
            seen.add(current)
            event = await self.storage.get_event(current)
            if event is None or str(event["user_id"]) != user_id:
                break
            chain.append(event)
            current = event.get("caused_by")
        chain.reverse()
        return chain

    # ------------------------------------------------------------------
    # Selective forgetting (GDPR)
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
    # Background loops (Phase 1 lifecycle pattern)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the maintenance loop (and, event-first, the applier)."""
        if not self.enabled:
            return
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        if self.event_first and (self._applier_task is None or self._applier_task.done()):
            self._applier_task = asyncio.create_task(self._start_applier())

    async def _start_applier(self) -> None:
        """Snapshot cursors past dual-written history, then apply forever."""
        try:
            await self.snapshot_cursors_to_tail()
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "error_type": type(e).__name__, "pass": "cursor_snapshot"},
                description=f"Projection cursor snapshot failed: {e}",
            )
        await self._applier_loop()

    async def stop(self) -> None:
        """Cancel the background loops, if running."""
        for attribute in ("_maintenance_task", "_applier_task"):
            task = getattr(self, attribute)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, attribute, None)

    async def _maintenance_loop(self) -> None:
        """Sleep-run loop: volatile expiry, hard purge, size-cap alert."""
        while True:
            await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
            try:
                await self.run_maintenance()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "error_type": type(e).__name__, "pass": "maintenance"},
                    description=f"Memory event maintenance failed: {e}",
                )

    async def run_maintenance(self) -> Dict[str, int]:
        """One maintenance pass; returns {"expired": n, "purged": n}."""
        expired = await self.run_volatile_expiry()
        purged = await self.run_hard_purge()
        await self._check_size_caps()
        return {"expired": expired, "purged": purged}

    async def run_volatile_expiry(self) -> int:
        """Soft-delete volatile events past their expiry."""
        expired = await self.storage.expire_volatile()
        if expired:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_EVENT_EXPIRED,
                level=observability.EventLevel.INFO,
                data={"expired_events": expired},
                description=f"Expired {expired} volatile memory events",
            )
        return expired

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

    async def _check_size_caps(self) -> None:
        """Alert on users whose event logs exceed the configured cap.

        The PRD's SQLite posture (open question 1): a single event table
        with a size-cap ALERT -- the substrate never blocks writes or
        prunes silently; capacity policy is the operator's call.
        """
        if self.max_events_per_user is None:
            return
        for uid in await self.storage.list_event_user_ids():
            count = await self.storage.count_events(uid)
            if count > self.max_events_per_user:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_EVENT_SIZE_CAP_EXCEEDED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "user_id": uid,
                        "events": count,
                        "max_events_per_user": self.max_events_per_user,
                    },
                    description=(
                        f"Memory event log for user {uid} has {count} events "
                        f"(cap {self.max_events_per_user})"
                    ),
                )

    # ------------------------------------------------------------------
    # Read surface (event listing for tests / provenance drill-down)
    # ------------------------------------------------------------------

    async def list_events(self, user_id: Any, **kwargs) -> List[Dict[str, Any]]:
        """List a user's events in append order (see storage.list_events)."""
        return await self.storage.list_events(str(user_id), **kwargs)


def _optional_positive_int(value: Any, label: str) -> Optional[int]:
    """None passes through; anything else must be a positive integer."""
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive integer or null, got {value!r}")
    if number <= 0:
        raise ValueError(f"{label} must be a positive integer or null, got {value!r}")
    return number


def _positive_int(value: Any, label: str) -> int:
    """Coerce a config value to a positive integer, failing fast otherwise."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive integer, got {value!r}")
    if number <= 0:
        raise ValueError(f"{label} must be a positive integer, got {value!r}")
    return number


def _positive_float(value: Any, label: str) -> float:
    """Coerce a config value to a positive float, failing fast otherwise."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive number, got {value!r}")
    if number <= 0:
        raise ValueError(f"{label} must be a positive number, got {value!r}")
    return number
