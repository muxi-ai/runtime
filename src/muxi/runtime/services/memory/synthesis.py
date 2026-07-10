# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Synthesis Service - Hot/Warm/Cold Cadences
# Description:  Batched synthesis over the event substrate (PRD cadence table)
# Role:         Entity resolution, pattern extraction, weekly re-synthesis
# Usage:        Registered with SchedulerService.register_periodic_task by the
#               Overlord when memory.ingestion is configured
# Author:       Muxi Framework Team
#
# Memory Ingestion maturation, PRD "Synthesis Scheduling": synthesis is
# never real-time -- it runs batched at hot/warm/cold intervals on the
# scheduler's existing worker loop (the same register_periodic_task
# extension point the proactive heartbeat and remote knowledge sync use;
# no new loop). ``tick()`` applies per-cadence interval gating and never
# raises; every per-user step is failure-isolated, so synthesis can never
# break chat or ingestion.
#
#   hot (5 min):      entity resolution for users with new ingestion /
#                     graph events since the hot cursor
#   warm (hourly):    preference + domain-expertise pattern facts for
#                     users with new events since the warm cursor
#   cold (nightly):   full pass -- schedule pattern + entity resolution
#                     over the whole graph
#   cold_cold (weekly): full re-synthesis FROM THE EVENT LOG -- per-user
#                     projection rebuild (reset -> replay -> checkpoint via
#                     MemoryEventService.rebuild, the substrate machinery
#                     from the projections/rebuild phase), then the full
#                     synthesis pass. This is what makes extraction-logic
#                     improvements retroactive: replay re-derives history,
#                     recorded entity.resolved decisions replay verbatim.
#
# Cursors: hot/warm/cold keep durable per-user cursors in the substrate's
# projection_checkpoints table (names "synthesis_hot" etc.), so restarts
# never reprocess settled history; the checkpoint names are not registered
# projectors, so the incremental applier and rebuild never touch them.
# Interval gating is in-memory and initialized to "now" at construction
# (heartbeat convention: a restart must not fire a burst of passes).
#
# Pattern extraction (v1, PRD "basic"): deterministic aggregation only, no
# LLM. Derived pattern facts ride the substrate as fact.extracted events
# (source "synthesis", decay_rate "decaying") keyed per (kind, ISO week),
# so re-running a cadence within the same week is a no-op -- idempotent by
# the same (source, source_id) index every other writer leans on.
# =============================================================================

from __future__ import annotations

import calendar
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import observability
from .events.models import (
    DECAY_DECAYING,
    EVENT_FACT_EXTRACTED,
    EVENT_GRAPH_EXTRACTED,
    EVENT_INTERACTION_TURN,
    EVENT_MEMORY_INGESTED,
    SOURCE_SYNTHESIS,
)
from .events.projectors import apply_fact_event
from .graph.extractor import USER_ENTITY_NAME, USER_ENTITY_TYPE
from .ingest.config import ResolutionSettings, SynthesisSettings

CADENCE_HOT = "hot"
CADENCE_WARM = "warm"
CADENCE_COLD = "cold"
CADENCE_COLD_COLD = "cold_cold"
CADENCES = (CADENCE_HOT, CADENCE_WARM, CADENCE_COLD, CADENCE_COLD_COLD)

# Durable per-user cursor names (projection_checkpoints.projection_name).
CURSOR_NAMES = {
    CADENCE_HOT: "synthesis_hot",
    CADENCE_WARM: "synthesis_warm",
    CADENCE_COLD: "synthesis_cold",
}

# Pattern kinds (v1). Each maps to one deterministic builder.
PATTERN_SCHEDULE = "schedule"
PATTERN_PREFERENCES = "preferences"
PATTERN_EXPERTISE = "expertise"

# Cap on events aggregated per user for the schedule pattern.
SCHEDULE_EVENT_LIMIT = 5000

# Event types that gate the hot cadence (new high-priority events).
HOT_TRIGGER_EVENT_TYPES = [EVENT_MEMORY_INGESTED, EVENT_GRAPH_EXTRACTED]


class MemorySynthesisService:
    """Owns the synthesis cadences; registered as a scheduler periodic task."""

    def __init__(
        self,
        overlord,
        settings: SynthesisSettings,
        resolution_settings: ResolutionSettings,
    ):
        """
        Args:
            overlord: The formation overlord (memory services resolved
                lazily so late-initialized services are picked up).
            settings: Validated SynthesisSettings (cadence table).
            resolution_settings: Validated ResolutionSettings for the
                resolution passes this service drives.
        """
        self.overlord = overlord
        self.settings = settings
        self.resolution_settings = resolution_settings
        # First run fires one full interval after startup (heartbeat
        # convention): a frequently restarting formation must not turn
        # synthesis into a startup stampede -- cold_cold especially.
        now = datetime.now(timezone.utc)
        self._last_run: Dict[str, datetime] = {cadence: now for cadence in CADENCES}
        self._running = False
        self._resolver = None

    # ------------------------------------------------------------------
    # Service resolution (lazy; the overlord wires services after init)
    # ------------------------------------------------------------------

    @property
    def memory_events(self):
        return getattr(self.overlord, "memory_events", None)

    @property
    def knowledge_graph(self):
        return getattr(self.overlord, "knowledge_graph", None)

    @property
    def entity_resolver(self):
        if self._resolver is None:
            memory_events = self.memory_events
            knowledge_graph = self.knowledge_graph
            if memory_events is None or knowledge_graph is None:
                return None
            from .graph.resolution import EntityResolver

            self._resolver = EntityResolver(
                knowledge_graph, memory_events, self.resolution_settings
            )
        return self._resolver

    # ------------------------------------------------------------------
    # Scheduler hook
    # ------------------------------------------------------------------

    async def tick(self, now: Optional[datetime] = None) -> None:
        """
        Scheduler-cycle hook: run every cadence whose interval elapsed.

        Never raises; cadences run coarsest-first so a due cold_cold
        re-synthesis is not preceded by redundant hot/warm work in the
        same cycle.
        """
        try:
            now = now or datetime.now(timezone.utc)
            if self._running or not self.settings.enabled:
                return
            self._running = True
            try:
                for cadence in reversed(CADENCES):
                    cadence_settings = self.settings.cadence(cadence)
                    if not cadence_settings.enabled:
                        continue
                    elapsed = (now - self._last_run[cadence]).total_seconds()
                    if elapsed < cadence_settings.interval_seconds:
                        continue
                    self._last_run[cadence] = now
                    await self.run_cadence(cadence, now=now)
            finally:
                self._running = False
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_SYNTHESIS_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "error_type": type(e).__name__, "phase": "tick"},
                description=f"Memory synthesis tick failed (isolated): {e}",
            )

    # ------------------------------------------------------------------
    # Cadence passes
    # ------------------------------------------------------------------

    async def run_cadence(self, cadence: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Run one cadence pass over every eligible user, bypassing interval
        gating (used by tick(), tests, and operational drivers).

        Per-user failures are isolated; the pass always returns a report:
        {"cadence", "users", "merged", "flagged", "patterns", "rebuilt",
        "failed"}.
        """
        if cadence not in CADENCES:
            raise ValueError(f"Unknown synthesis cadence {cadence!r}; expected one of {CADENCES}")
        now = now or datetime.now(timezone.utc)
        report: Dict[str, Any] = {
            "cadence": cadence,
            "users": 0,
            "merged": 0,
            "flagged": 0,
            "patterns": 0,
            "rebuilt": 0,
            "failed": 0,
        }
        memory_events = self.memory_events
        if memory_events is None or not getattr(memory_events, "enabled", False):
            return report  # inert without the substrate

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_SYNTHESIS_STARTED,
            level=observability.EventLevel.DEBUG,
            data={"cadence": cadence},
            description=f"Memory synthesis {cadence} pass started",
        )
        try:
            for user_id in await memory_events.storage.list_event_user_ids():
                try:
                    user_report = await self._run_user(cadence, user_id, now)
                    if user_report is None:
                        continue  # nothing new for this user (cursor gate)
                    report["users"] += 1
                    for key in ("merged", "flagged", "patterns", "rebuilt"):
                        report[key] += user_report.get(key, 0)
                except Exception as e:
                    report["failed"] += 1
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_SYNTHESIS_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "cadence": cadence,
                            "user_id": user_id,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                        description=f"Memory synthesis {cadence} failed for user (isolated): {e}",
                    )
        except Exception as e:
            report["failed"] += 1
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_SYNTHESIS_FAILED,
                level=observability.EventLevel.WARNING,
                data={"cadence": cadence, "error": str(e), "error_type": type(e).__name__},
                description=f"Memory synthesis {cadence} pass failed (isolated): {e}",
            )
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_SYNTHESIS_COMPLETED,
            level=(
                observability.EventLevel.INFO if report["users"] else observability.EventLevel.DEBUG
            ),
            data=dict(report),
            description=(
                f"Memory synthesis {cadence} pass completed "
                f"({report['users']} user(s), {report['failed']} failure(s))"
            ),
        )
        return report

    async def _run_user(
        self, cadence: str, user_id: str, now: datetime
    ) -> Optional[Dict[str, int]]:
        """One cadence pass for one user; None when the cursor gate skips.

        The hot/warm/cold cursor is only advanced after the pass succeeds,
        so a failed pass is retried on the next interval.
        """
        memory_events = self.memory_events
        cursor_name = CURSOR_NAMES.get(cadence)
        tail = None
        if cursor_name is not None:
            checkpoint = await memory_events.storage.get_checkpoint(cursor_name, user_id)
            after_id = checkpoint["last_event_id"] if checkpoint else None
            trigger_types = HOT_TRIGGER_EVENT_TYPES if cadence == CADENCE_HOT else None
            pending = await memory_events.storage.list_events(
                user_id, event_types=trigger_types, after_id=after_id, limit=1
            )
            if not pending:
                return None
            tail = await memory_events.storage.max_event_id(user_id)

        result = {"merged": 0, "flagged": 0, "patterns": 0, "rebuilt": 0}

        if cadence == CADENCE_COLD_COLD:
            # Weekly full re-synthesis: replay the event log through the
            # substrate's rebuild machinery (reset -> replay -> checkpoint,
            # per-user cursors handled inside), then synthesize on the
            # freshly rebuilt projections.
            await memory_events.rebuild(user_id)
            result["rebuilt"] = 1

        if cadence in (CADENCE_HOT, CADENCE_COLD, CADENCE_COLD_COLD):
            resolver = self.entity_resolver
            if resolver is not None:
                resolution = await resolver.resolve_user(user_id)
                result["merged"] = resolution.get("merged", 0)
                result["flagged"] = resolution.get("flagged", 0)

        if self.settings.patterns.enabled:
            if cadence == CADENCE_WARM:
                kinds = [PATTERN_PREFERENCES, PATTERN_EXPERTISE]
            elif cadence in (CADENCE_COLD, CADENCE_COLD_COLD):
                kinds = [PATTERN_SCHEDULE, PATTERN_PREFERENCES, PATTERN_EXPERTISE]
            else:
                kinds = []
            for kind in kinds:
                if await self._extract_pattern(user_id, kind, now):
                    result["patterns"] += 1

        if cursor_name is not None and tail is not None:
            await memory_events.storage.set_checkpoint(cursor_name, user_id, last_event_id=tail)
        return result

    # ------------------------------------------------------------------
    # Pattern extraction (v1: deterministic aggregation, no LLM)
    # ------------------------------------------------------------------

    async def _extract_pattern(self, user_id: str, kind: str, now: datetime) -> bool:
        """Derive and record one pattern fact; returns True when written."""
        if kind == PATTERN_SCHEDULE:
            rendered = await self._schedule_pattern(user_id)
            collection = "activities"
        elif kind == PATTERN_PREFERENCES:
            rendered = await self._preference_pattern(user_id)
            collection = "preferences"
        elif kind == PATTERN_EXPERTISE:
            rendered = await self._expertise_pattern(user_id)
            collection = "context"
        else:
            return False
        if not rendered:
            return False
        return await self._record_pattern(user_id, kind, rendered, collection, now)

    async def _schedule_pattern(self, user_id: str) -> Optional[str]:
        """Behavioral schedule from aggregated event timestamps (UTC)."""
        events = await self.memory_events.storage.list_events(
            user_id,
            event_types=[EVENT_INTERACTION_TURN, EVENT_MEMORY_INGESTED],
            limit=SCHEDULE_EVENT_LIMIT,
        )
        if len(events) < self.settings.patterns.min_events:
            return None
        hours: Counter = Counter()
        days: Counter = Counter()
        for event in events:
            occurred_at = event.get("occurred_at")
            if isinstance(occurred_at, str):
                try:
                    occurred_at = datetime.fromisoformat(occurred_at)
                except ValueError:
                    continue
            if not isinstance(occurred_at, datetime):
                continue
            hours[occurred_at.hour] += 1
            days[calendar.day_name[occurred_at.weekday()]] += 1
        if not hours:
            return None
        # Deterministic ordering: count desc, then hour/day ascending.
        top_hours = sorted(hours.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        day_order = {name: i for i, name in enumerate(calendar.day_name)}
        top_days = sorted(days.items(), key=lambda kv: (-kv[1], day_order[kv[0]]))[:2]
        hours_text = ", ".join(f"{hour:02d}:00" for hour, _ in sorted(top_hours))
        days_text = " and ".join(day for day, _ in top_days)
        return (
            f"Typically active around {hours_text} UTC, most often on {days_text} "
            f"(observed across {len(events)} events)"
        )

    async def _preference_pattern(self, user_id: str) -> Optional[str]:
        """Preference profile from the user's graph (prefers/interested_in)."""
        knowledge_graph = self.knowledge_graph
        if knowledge_graph is None:
            return None
        storage = knowledge_graph.storage
        user_entity = await storage.get_entity(user_id, USER_ENTITY_TYPE, USER_ENTITY_NAME)
        if user_entity is None:
            return None
        top_k = self.settings.patterns.top_k
        prefers = await self._related_names(storage, user_id, user_entity["id"], "prefers", top_k)
        interests = await self._related_names(
            storage, user_id, user_entity["id"], "interested_in", top_k
        )
        parts = []
        if prefers:
            parts.append(f"prefers {', '.join(prefers)}")
        if interests:
            parts.append(f"is interested in {', '.join(interests)}")
        if not parts:
            return None
        return f"Preference profile (synthesized): the user {'; '.join(parts)}"

    async def _expertise_pattern(self, user_id: str) -> Optional[str]:
        """Domain expertise proxy: the most-reinforced topic entities."""
        knowledge_graph = self.knowledge_graph
        if knowledge_graph is None:
            return None
        topics = await knowledge_graph.storage.list_entities(
            user_id, entity_type="topic", limit=100
        )
        if not topics:
            return None
        # Reinforcement proxy: provenance count (how many events touched
        # the topic), then confidence, then name for determinism.
        topics.sort(
            key=lambda t: (
                -len(t.get("derived_from_event_ids") or []),
                -(t.get("confidence") or 0.0),
                t["name"].lower(),
            )
        )
        names = [topic["name"] for topic in topics[: self.settings.patterns.top_k]]
        return f"Frequently engaged topics (synthesized): {', '.join(names)}"

    @staticmethod
    async def _related_names(storage, user_id, from_entity_id, rel_type, top_k) -> List[str]:
        """Target entity names for one relationship type, strongest first."""
        relationships = await storage.list_relationships(
            user_id, rel_type=rel_type, from_entity_id=from_entity_id, limit=top_k
        )
        if not relationships:
            return []
        entities = await storage.get_entities_by_ids([rel["to_entity_id"] for rel in relationships])
        names_by_id = {entity["id"]: entity["name"] for entity in entities}
        return [
            names_by_id[rel["to_entity_id"]]
            for rel in relationships
            if rel["to_entity_id"] in names_by_id
        ]

    async def _record_pattern(
        self, user_id: str, kind: str, rendered: str, collection: str, now: datetime
    ) -> bool:
        """Write one pattern fact event-first, keyed per (kind, ISO week).

        Idempotent within the period through the substrate's
        (source, source_id) index; pattern facts decay (decay_rate
        "decaying") so a stale week's synthesis sinks without deletion.
        """
        memory_events = self.memory_events
        iso = now.isocalendar()
        period = f"{iso[0]}-W{iso[1]:02d}"
        source_id = f"pattern/{kind}/{period}"
        existing = await memory_events.storage.find_by_source_id(
            user_id, SOURCE_SYNTHESIS, source_id
        )
        if existing is not None:
            return False

        payload = {
            "memory": rendered,
            "collection": collection,
            "metadata": {"source": SOURCE_SYNTHESIS, "pattern": kind, "period": period},
        }
        event = await memory_events.record(
            user_id=user_id,
            event_type=EVENT_FACT_EXTRACTED,
            payload=payload,
            source=SOURCE_SYNTHESIS,
            source_id=source_id,
            decay_rate=DECAY_DECAYING,
        )
        if event is None:
            return False
        if getattr(memory_events, "event_first", False):
            await memory_events.apply_event(event)
        else:
            long_term_memory = getattr(self.overlord, "long_term_memory", None)
            if long_term_memory is None:
                return False
            await apply_fact_event(long_term_memory, user_id, payload, event_id=event["id"])
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_PATTERN_EXTRACTED,
            level=observability.EventLevel.INFO,
            data={
                "user_id": user_id,
                "pattern": kind,
                "period": period,
                "collection": collection,
                "memory_event_id": event["id"],
            },
            description=f"Synthesized {kind} pattern for period {period}",
        )
        return True
