# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Captain's Log Service - Narrative Memory Coordination
# Description:  Periodic summarization, lessons lifecycle, and log queries
# Role:         Formation-level service owning the captain's log lifecycle
# Usage:        Created in formation initialization, driven by the Overlord
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 2 (Captain's Log). Coordinates:
#
# 1. Turn intake: conversation turns are queued per user by the extraction
#    coordinator (no LLM work in the chat path).
# 2. Periodic summarization: a background loop (Phase 1 lifecycle pattern:
#    started by the Overlord next to the scheduler, cancelled on shutdown)
#    digests each user's pending turns into the (user, date) log entry,
#    writes source lineage, upserts extracted lessons, and feeds the same
#    digest's graph facts to the Phase 1 knowledge graph.
# 3. Lesson lifecycle: record_lesson (agent tool write path), session-stable
#    prompt-block injection, confidence decay, and consolidation.
# 4. Queries: recent-entry context blocks for prompt injection and the
#    /history API surface with source lineage drill-down.
#
# Every public entry point is failure-isolated: log/lesson failures are
# logged and swallowed so chat turns and the background loop are never
# affected.
# =============================================================================

import asyncio
import time
from collections import OrderedDict, deque
from datetime import date as date_type
from typing import Any, Deque, Dict, List, Optional, Tuple

from ....utils.datetime_utils import utc_now_naive
from ... import observability
from ..embedding import DEFAULT_EMBEDDING_MODEL, embed
from ..events.models import (
    EVENT_LESSON_RECORDED,
    EVENT_LOG_ENTRY,
    SOURCE_CAPTAINS_LOG,
    SOURCE_TOOL,
)
from ..graph.extractor import KnowledgeGraphExtractor
from ..graph.service import _schedule_to_seconds
from .models import SOURCE_TYPE_BUFFER_ITEM
from .storage import CaptainsLogStorage, LessonStorage
from .summarizer import CaptainsLogSummarizer

# PRD defaults (Configuration Reference -> memory.captains_log / memory.lessons).
DEFAULT_SCHEDULE = "daily"
DEFAULT_INCLUDE_IN_CONTEXT = 5
DEFAULT_INJECT_TOP_N = 20
DEFAULT_MAX_PER_AGENT = 50
DEFAULT_CONFIDENCE_DECAY_PER_30D = 0.05
DEFAULT_ARCHIVE_THRESHOLD = 0.2

# Confidence threshold for the digest's knowledge graph side (the periodic
# pass semantics from Phase 1).
DIGEST_GRAPH_CONFIDENCE = 0.7

# Bound on turns buffered per user between runs (Phase 1 convention).
MAX_PENDING_TURNS_PER_USER = 50

# Cosine similarity above which two lessons are considered the same rule
# during consolidation clustering.
CONSOLIDATION_SIMILARITY = 0.8

# Bound on cached per-session lesson blocks.
LESSON_BLOCK_CACHE_SIZE = 256

# Header used for the lessons dynamic block. The block sits at the tail of
# the system prompt, after the cache-stable static persona and addendum, so
# providers that cache prompt prefixes keep the static prefix intact (the
# PRD's cache-breakpoint placement, expressed structurally -- the current
# LLM layer has no per-block cache-control markers to attach).
LESSONS_BLOCK_HEADER = "=== LESSONS LEARNED (apply when relevant) ==="

# Name registered for the log derivation DAG on the graph algorithms layer.
CAPTAINS_LOG_DAG = "captains_log_sources"


class CaptainsLogService:
    """Owns captain's log storage, summarization, and the lessons loop."""

    def __init__(
        self,
        db_manager,
        formation_id: str,
        config: Optional[Dict[str, Any]] = None,
        lessons_config: Optional[Dict[str, Any]] = None,
        knowledge_graph=None,
        embedding_model: Optional[str] = None,
        event_log=None,
    ):
        """
        Initialize the captain's log service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all rows.
            config: The ``memory.captains_log`` formation config section.
            lessons_config: The ``memory.lessons`` formation config section.
            knowledge_graph: Phase 1 KnowledgeGraphService (or None) used
                for the digest's entity/relationship integration.
            embedding_model: Slug used for lesson-consolidation clustering;
                defaults to the shared memory embedding default.
            event_log: MemoryEventService (or None). When present, digest
                entries and lessons are appended to the memory event log
                before the projection writes (dual-write; append failures
                are isolated inside the event service).
        """
        config = config or {}
        lessons_config = lessons_config or {}

        self.formation_id = formation_id
        self.enabled = config.get("enabled", True)
        self.interval_seconds = _schedule_to_seconds(config.get("schedule", DEFAULT_SCHEDULE))
        self.include_in_context = int(config.get("include_in_context", DEFAULT_INCLUDE_IN_CONTEXT))

        self.lessons_enabled = lessons_config.get("enabled", True)
        self.extract_lessons_during_digest = lessons_config.get("extract_during_digest", True)
        self.lessons_inject_top_n = int(lessons_config.get("inject_top_n", DEFAULT_INJECT_TOP_N))
        self.lessons_max_per_agent = int(lessons_config.get("max_per_agent", DEFAULT_MAX_PER_AGENT))
        self.lessons_decay_per_30d = float(
            lessons_config.get("confidence_decay_per_30d", DEFAULT_CONFIDENCE_DECAY_PER_30D)
        )
        self.lessons_archive_threshold = float(
            lessons_config.get("archive_threshold", DEFAULT_ARCHIVE_THRESHOLD)
        )

        self.db_manager = db_manager
        self.storage = CaptainsLogStorage(db_manager, formation_id)
        self.lessons = LessonStorage(db_manager, formation_id)
        self.summarizer = CaptainsLogSummarizer()
        # The digest response's graph fields are validated with the Phase 1
        # extractor's parser at the periodic-pass confidence threshold.
        self.graph_extractor = KnowledgeGraphExtractor(confidence_threshold=DIGEST_GRAPH_CONFIDENCE)
        self.knowledge_graph = knowledge_graph
        self.embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL
        self.event_log = event_log

        # Turns accumulated per user since the last run, with the capture
        # timestamp used as the buffer_item source key.
        self._pending_turns: Dict[str, Deque[Tuple[str, str]]] = {}
        self._task: Optional[asyncio.Task] = None
        # Session-stable rendered lesson blocks: (user, agent, session) -> str.
        self._lesson_block_cache: "OrderedDict[Tuple[str, str, str], str]" = OrderedDict()

        # Expose the log derivation DAG to the shared graph algorithms
        # layer so topological_sort(dag="captains_log_sources") works on
        # both backends.
        if knowledge_graph is not None and hasattr(knowledge_graph, "algorithms"):
            knowledge_graph.algorithms.register_dag_edge_provider(
                CAPTAINS_LOG_DAG, self.storage.iter_log_edges
            )

    # ------------------------------------------------------------------
    # Turn intake (chat path -- no LLM work here)
    # ------------------------------------------------------------------

    def queue_turn(self, user_message: str, agent_response: str, user_id: Any) -> None:
        """Buffer one conversation turn for the next summarization run."""
        if not self.enabled:
            return
        text = _format_turn(user_message, agent_response)
        queue = self._pending_turns.setdefault(
            str(user_id), deque(maxlen=MAX_PENDING_TURNS_PER_USER)
        )
        queue.append((f"{time.time():.6f}", text))

    # ------------------------------------------------------------------
    # Background loop (Phase 1 lifecycle pattern)
    # ------------------------------------------------------------------

    def start(self, model_getter) -> None:
        """
        Start the periodic summarization background loop.

        Args:
            model_getter: Zero-argument callable returning the digest LLM
                (or None while unavailable). Resolved per run so the loop
                always uses the formation's current capability model.
        """
        if not self.enabled:
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(model_getter))

    async def stop(self) -> None:
        """Cancel the background loop, if running."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, model_getter) -> None:
        """Sleep-run loop for summarization and lesson maintenance."""
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                model = model_getter()
                await self.run_periodic_summarization(model)
                await self.run_lesson_maintenance(model)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_CAPTAINS_LOG_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "error_type": type(e).__name__, "pass": "loop"},
                    description=f"Captain's log periodic run failed: {e}",
                )

    async def run_periodic_summarization(self, model) -> Dict[str, int]:
        """
        Digest the turns accumulated since the last run.

        One digest per user: upserts the (user, date) entry, records
        buffer-item source lineage, upserts extracted lessons, and stores
        the digest's graph facts through the Phase 1 knowledge graph.
        Per-user failures are logged and skipped. Returns aggregate counts.
        """
        totals = {"entries": 0, "sources": 0, "lessons": 0}
        if not self.enabled or model is None:
            return totals

        pending = {user: list(turns) for user, turns in self._pending_turns.items() if turns}
        self._pending_turns.clear()

        for user_id, turns in pending.items():
            try:
                stored = await self._digest_user(user_id, turns, model)
                totals["entries"] += stored["entries"]
                totals["sources"] += stored["sources"]
                totals["lessons"] += stored["lessons"]
            except Exception as e:
                # A failed digest must not lose the snapshot: restore it
                # ahead of any turns that arrived while the run was in
                # flight so the next run digests them in order.
                self._requeue_turns(user_id, turns)
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_CAPTAINS_LOG_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "user_id": user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "pass": "summarization",
                        "requeued_turns": len(self._pending_turns.get(user_id, ())),
                    },
                    description=f"Captain's log summarization failed: {e}",
                )
        return totals

    def _requeue_turns(self, user_id: str, turns: List[Tuple[str, str]]) -> None:
        """Restore a failed digest's turn snapshot for the next run.

        The snapshot is prepended so ordering is preserved when new turns
        arrived during the failed run. The combined queue stays capped at
        MAX_PENDING_TURNS_PER_USER (drop-oldest, the deque's own policy)
        so persistent failure cannot grow memory unboundedly; a WARNING is
        emitted whenever the cap trims.
        """
        queue = self._pending_turns.setdefault(user_id, deque(maxlen=MAX_PENDING_TURNS_PER_USER))
        combined = list(turns) + list(queue)
        trimmed = len(combined) - MAX_PENDING_TURNS_PER_USER
        if trimmed > 0:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_CAPTAINS_LOG_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "user_id": user_id,
                    "pass": "requeue",
                    "trimmed_turns": trimmed,
                    "kept_turns": MAX_PENDING_TURNS_PER_USER,
                },
                description=(
                    f"Captain's log re-queue dropped {trimmed} oldest buffered turns "
                    "(per-user cap reached after repeated digest failures)"
                ),
            )
        queue.clear()
        queue.extend(combined)  # deque maxlen keeps the newest turns

    async def _digest_user(
        self, user_id: str, turns: List[Tuple[str, str]], model
    ) -> Dict[str, int]:
        """Digest one user's pending turns into today's log entry."""
        conversation = "\n\n".join(text for _, text in turns)
        entry_date = utc_now_naive().date()
        previous_entry = await self.storage.get_entry(user_id, entry_date)

        extract_lessons = self.lessons_enabled and self.extract_lessons_during_digest
        raw_response = await model.generate_text(
            self.summarizer.build_prompt(
                conversation,
                entry_date=entry_date.isoformat(),
                previous_entry=previous_entry,
                extract_lessons=extract_lessons,
            ),
            caching=False,
        )
        digest = self.summarizer.parse_response(raw_response)
        if digest is None:
            return {"entries": 0, "sources": 0, "lessons": 0}

        # Dual-write (Memory Event Substrate): the digest result becomes a
        # log.entry event first, then the projection write goes through the
        # same apply path the event replay uses.
        entry_payload = {
            "date": entry_date.isoformat(),
            "summary": digest["summary"],
            "decisions": digest["decisions"],
            "projects": digest["projects"],
            "context": digest["context"],
            "sources": [
                {"source_type": SOURCE_TYPE_BUFFER_ITEM, "source_id": timestamp_key}
                for timestamp_key, _ in turns
            ],
        }
        event = None
        if self.event_log is not None:
            event = await self.event_log.record(
                user_id=user_id,
                event_type=EVENT_LOG_ENTRY,
                payload=entry_payload,
                source=SOURCE_CAPTAINS_LOG,
            )
        entry, source_counts = await self.apply_log_entry_event(
            user_id, entry_payload, event_id=event["id"] if event else None
        )

        lessons_stored = 0
        if extract_lessons:
            lessons_stored = await self._store_lessons(
                user_id, digest["lessons"], source_log_date=entry_payload["date"]
            )

        # Knowledge graph integration: the same digest response carries
        # entity/relationship facts, validated by the Phase 1 extractor at
        # the periodic confidence threshold and stored through the Phase 1
        # service. Failure-isolated: a graph error never loses the entry.
        if self.knowledge_graph is not None:
            try:
                extraction = self.graph_extractor.parse_response(
                    raw_response, DIGEST_GRAPH_CONFIDENCE
                )
                stored = await self.knowledge_graph.store_extraction(
                    user_id, extraction, source=SOURCE_CAPTAINS_LOG
                )
                if stored["entities"] or stored["relationships"]:
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_AUTO_EXTRACTED,
                        level=observability.EventLevel.DEBUG,
                        data={"user_id": user_id, "pass": "captains_log", **stored},
                        description=(
                            f"Captain's log digest stored {stored['entities']} entities "
                            f"and {stored['relationships']} relationships"
                        ),
                    )
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_AUTO_EXTRACTION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "user_id": user_id,
                        "pass": "captains_log",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Captain's log graph integration failed: {e}",
                )

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_CAPTAINS_LOG_UPDATED,
            level=observability.EventLevel.DEBUG,
            data={
                "user_id": user_id,
                "date": entry["date"],
                "turns": len(turns),
                "sources_added": source_counts["added"],
                "lessons": lessons_stored,
            },
            description=f"Captain's log entry updated for {entry['date']}",
        )
        return {"entries": 1, "sources": source_counts["added"], "lessons": lessons_stored}

    async def _store_lessons(
        self,
        user_id: str,
        lessons: List[Dict[str, Optional[str]]],
        source_log_date: Optional[str] = None,
        agent_id: str = "overlord",
    ) -> int:
        """Upsert digest-extracted lessons; returns stored count.

        Lessons reference their source entry by date (the stable digest
        key) rather than by integer id so replayed events resolve against
        the rebuilt entry rows.
        """
        stored = 0
        for item in lessons:
            payload = {
                "agent_id": agent_id,
                "rule": item["rule"],
                "context": item.get("context"),
                "source_log_date": source_log_date,
            }
            event = None
            if self.event_log is not None:
                event = await self.event_log.record(
                    user_id=user_id,
                    event_type=EVENT_LESSON_RECORDED,
                    payload=payload,
                    source=SOURCE_CAPTAINS_LOG,
                )
            lesson, created = await self.apply_lesson_event(
                user_id, payload, event_id=event["id"] if event else None
            )
            stored += 1
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LESSON_RECORDED,
                level=observability.EventLevel.DEBUG,
                data={
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "lesson_id": lesson["public_id"],
                    "created": created,
                    "hits": lesson["hits"],
                    "source": "digest",
                },
                description="Lesson recorded from captain's log digest",
            )
        return stored

    # ------------------------------------------------------------------
    # Event apply path (shared by dual-write and replay rebuild)
    # ------------------------------------------------------------------

    async def apply_log_entry_event(
        self, user_id: str, payload: Dict[str, Any], event_id: Optional[int] = None
    ) -> Tuple[Dict[str, Any], Dict[str, int]]:
        """
        Apply one log.entry payload to the captains_log projection.

        Deterministic write shared by the live digest path and the event
        replay: upserts the (user, date) entry and attaches its source
        lineage rows. Returns (entry dict, source counts).
        """
        entry = await self.storage.upsert_entry(
            str(user_id),
            date_type.fromisoformat(payload["date"]),
            summary=payload.get("summary"),
            decisions=payload.get("decisions"),
            projects=payload.get("projects"),
            context=payload.get("context"),
            event_id=event_id,
        )
        counts = await self.storage.add_sources(
            str(user_id), entry["id"], payload.get("sources") or []
        )
        return entry, counts

    async def apply_lesson_event(
        self, user_id: str, payload: Dict[str, Any], event_id: Optional[int] = None
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Apply one lesson.recorded payload to the lessons projection.

        Resolves the source entry by date at apply time so the same event
        links to the rebuilt entry row after a replay. Returns
        (lesson dict, created).
        """
        user_id = str(user_id)
        source_log_id = None
        source_log_date = payload.get("source_log_date")
        if source_log_date:
            entry = await self.storage.get_entry(user_id, date_type.fromisoformat(source_log_date))
            if entry is not None:
                source_log_id = entry["id"]
        return await self.lessons.upsert_lesson(
            user_id=user_id,
            agent_id=payload["agent_id"],
            rule=payload["rule"],
            context=payload.get("context"),
            confidence=payload.get("confidence", 0.5),
            source_log_id=source_log_id,
            event_id=event_id,
        )

    # ------------------------------------------------------------------
    # Lessons: write path (agent tool) and read path (prompt injection)
    # ------------------------------------------------------------------

    async def record_lesson(
        self,
        user_id: Any,
        agent_id: str,
        rule: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record one lesson from the record_lesson agent tool.

        Raises:
            ValueError: When the rule is empty or lessons are disabled.
        """
        if not self.lessons_enabled:
            raise ValueError("Lessons are disabled for this formation")
        if not rule or not rule.strip():
            raise ValueError("record_lesson requires a non-empty rule")

        payload = {"agent_id": str(agent_id), "rule": rule.strip(), "context": context}
        event = None
        if self.event_log is not None:
            event = await self.event_log.record(
                user_id=str(user_id),
                event_type=EVENT_LESSON_RECORDED,
                payload=payload,
                source=SOURCE_TOOL,
                agent_id=str(agent_id),
            )
        lesson, created = await self.apply_lesson_event(
            str(user_id), payload, event_id=event["id"] if event else None
        )
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LESSON_RECORDED,
            level=observability.EventLevel.DEBUG,
            data={
                "user_id": str(user_id),
                "agent_id": agent_id,
                "lesson_id": lesson["public_id"],
                "created": created,
                "hits": lesson["hits"],
                "source": "tool",
            },
            description="Lesson recorded via record_lesson tool",
        )
        return lesson

    async def get_lessons_prompt_block(
        self, user_id: Any, agent_id: str, session_id: Optional[str]
    ) -> str:
        """
        Render the top-N lessons block for the agent's system prompt.

        Loaded once per (user, agent, session) and held stable for the
        session's duration (the PRD's no-mid-session-refresh rule: new
        lessons become visible to subsequent sessions, and a stable block
        keeps the prompt prefix cacheable). Returns "" when there are no
        lessons, lessons are disabled, or on any error.
        """
        if not self.enabled or not self.lessons_enabled:
            return ""
        cache_key = (str(user_id), str(agent_id), str(session_id or "default"))
        cached = self._lesson_block_cache.get(cache_key)
        if cached is not None:
            self._lesson_block_cache.move_to_end(cache_key)
            return cached

        try:
            lessons = await self.lessons.list_active(
                str(user_id), agent_id=None, limit=self.lessons_inject_top_n
            )
            if lessons:
                lines = [LESSONS_BLOCK_HEADER]
                for lesson in lessons:
                    line = f"- {lesson['rule']}"
                    if lesson.get("context"):
                        line += f" (when: {lesson['context']})"
                    lines.append(line)
                block = "\n".join(lines)
                await self.lessons.mark_applied([lesson["id"] for lesson in lessons])
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LESSON_APPLIED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "user_id": str(user_id),
                        "agent_id": str(agent_id),
                        "count": len(lessons),
                    },
                    description=f"Injected {len(lessons)} lessons into the session prompt",
                )
            else:
                block = ""
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_CAPTAINS_LOG_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "user_id": str(user_id),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "pass": "lesson_injection",
                },
                description=f"Lesson prompt-block lookup failed: {e}",
            )
            return ""

        self._lesson_block_cache[cache_key] = block
        while len(self._lesson_block_cache) > LESSON_BLOCK_CACHE_SIZE:
            self._lesson_block_cache.popitem(last=False)
        return block

    # ------------------------------------------------------------------
    # Lessons: maintenance (decay + consolidation)
    # ------------------------------------------------------------------

    async def run_lesson_maintenance(self, model) -> Dict[str, int]:
        """
        Run the lesson decay pass and (when a scope exceeds the cap) the
        consolidation job. Failure-isolated; returns aggregate counts.
        """
        totals = {"decayed": 0, "archived": 0, "consolidated": 0}
        if not self.enabled or not self.lessons_enabled:
            return totals

        try:
            decayed = await self.lessons.run_decay(
                self.lessons_decay_per_30d, self.lessons_archive_threshold
            )
            totals["decayed"] = decayed["decayed"]
            totals["archived"] = decayed["archived"]
            if decayed["archived"]:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LESSON_ARCHIVED,
                    level=observability.EventLevel.DEBUG,
                    data=decayed,
                    description=f"Archived {decayed['archived']} decayed lessons",
                )
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_CAPTAINS_LOG_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "error_type": type(e).__name__, "pass": "lesson_decay"},
                description=f"Lesson decay pass failed: {e}",
            )

        if model is not None:
            try:
                totals["consolidated"] = await self.run_lesson_consolidation(model)
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_CAPTAINS_LOG_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "pass": "lesson_consolidation",
                    },
                    description=f"Lesson consolidation failed: {e}",
                )
        return totals

    async def run_lesson_consolidation(self, model) -> int:
        """
        Consolidate semantically-similar lessons for scopes over the cap.

        For each (user, agent) whose active lesson count exceeds
        max_per_agent: embed the rules, greedily cluster by cosine
        similarity, rewrite each multi-lesson cluster into one combined
        rule via the LLM, insert it with hits summed and confidence maxed,
        and archive the originals. Returns the number of clusters merged.
        """
        consolidated = 0
        for user_id, agent_id, _count in await self.lessons.scopes_over_cap(
            self.lessons_max_per_agent
        ):
            lessons = await self.lessons.list_active(user_id, agent_id=agent_id)
            vectors = await embed(
                self.embedding_model, [lesson["rule"] for lesson in lessons], task="clustering"
            )
            for cluster in _cluster_by_similarity(vectors, CONSOLIDATION_SIMILARITY):
                if len(cluster) < 2:
                    continue
                members = [lessons[index] for index in cluster]
                combined_rule = await self._rewrite_cluster(members, model)
                if not combined_rule:
                    continue
                merged, _ = await self.lessons.upsert_lesson(
                    user_id=user_id,
                    agent_id=agent_id,
                    rule=combined_rule,
                    context=next((m["context"] for m in members if m.get("context")), None),
                    confidence=max(m["confidence"] or 0.0 for m in members),
                    hits=sum(m["hits"] or 1 for m in members),
                )
                await self.lessons.archive_lessons(
                    [m["id"] for m in members if m["id"] != merged["id"]]
                )
                consolidated += 1
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LESSON_CONSOLIDATED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "user_id": user_id,
                        "agent_id": agent_id,
                        "merged": len(members),
                        "lesson_id": merged["public_id"],
                    },
                    description=f"Consolidated {len(members)} lessons into one rule",
                )
        return consolidated

    async def _rewrite_cluster(self, members: List[Dict[str, Any]], model) -> Optional[str]:
        """Ask the LLM to combine one cluster of similar rules; None on failure."""
        rules = "\n".join(f"- {member['rule']}" for member in members)
        prompt = (
            "Combine the following similar rules of thumb into ONE concise prescriptive "
            "rule that preserves every distinct constraint. Respond with the combined "
            "rule text only, no preamble.\n\n"
            f"{rules}\n"
        )
        response = await model.generate_text(prompt, caching=False)
        if not isinstance(response, str) or not response.strip():
            return None
        return response.strip()

    # ------------------------------------------------------------------
    # Query surface (context injection + /history)
    # ------------------------------------------------------------------

    async def get_context_block(self, user_id: Any, limit: Optional[int] = None) -> str:
        """
        Render the most recent log entries for prompt injection.

        Returns "" when the log is empty, disabled, or on error.
        """
        if not self.enabled:
            return ""
        try:
            entries = await self.storage.list_entries(
                str(user_id), limit=limit or self.include_in_context
            )
            if not entries:
                return ""
            lines: List[str] = []
            for entry in entries:
                parts = [entry["summary"] or ""]
                if entry["decisions"]:
                    parts.append("Decisions: " + "; ".join(entry["decisions"]))
                if entry["projects"]:
                    parts.append("Projects: " + "; ".join(entry["projects"]))
                body = " ".join(part for part in parts if part).strip()
                if body:
                    lines.append(f"[{entry['date']}] {body}")
            return "\n".join(lines)
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVAL_FAILED,
                level=observability.EventLevel.WARNING,
                data={"user_id": str(user_id), "error": str(e), "component": "captains_log"},
                description=f"Captain's log context lookup failed: {e}",
            )
            return ""

    async def get_history(
        self,
        user_id: Any,
        limit: int = 10,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        include_sources: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return log entries for the /history API surface, newest first.

        Entries are external-facing dicts (public_id, never the integer
        primary key). With include_sources, each entry carries its source
        lineage rows (the evidence trail).
        """
        entries = await self.storage.list_entries(
            str(user_id),
            limit=limit,
            date_from=_parse_iso_date(date_from),
            date_to=_parse_iso_date(date_to),
        )
        sources_by_log: Dict[int, List[Dict[str, Any]]] = {}
        if include_sources and entries:
            # One batched IN query for all entries instead of a round-trip
            # per entry (up to the API's limit=100).
            sources_by_log = await self.storage.get_sources_for_logs(
                [entry["id"] for entry in entries]
            )
        history = []
        for entry in entries:
            item = {
                "id": entry["public_id"],
                "date": entry["date"],
                "summary": entry["summary"],
                "decisions": entry["decisions"],
                "projects": entry["projects"],
                "context": entry["context"],
                "created_at": entry["created_at"],
                "updated_at": entry["updated_at"],
            }
            if include_sources:
                item["sources"] = [
                    {"source_type": source["source_type"], "source_id": source["source_id"]}
                    for source in sources_by_log.get(entry["id"], [])
                ]
            history.append(item)
        return history


def _format_turn(user_message: str, agent_response: str) -> str:
    """Format a conversation turn for the digest, mirroring the extractors."""
    if agent_response and agent_response.strip():
        return f"User: {user_message}\nAssistant: {agent_response}"
    return f"User: {user_message}"


def _parse_iso_date(value: Optional[str]):
    """Parse an ISO date string to a date, or None when absent/invalid."""
    if not value:
        return None
    from datetime import date

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _cluster_by_similarity(vectors: List[List[float]], threshold: float) -> List[List[int]]:
    """Greedy single-pass clustering of vectors by cosine similarity.

    Each vector joins the first existing cluster whose seed member it is
    at least ``threshold`` similar to; otherwise it seeds a new cluster.
    Deterministic and O(n * clusters), plenty at the per-agent lesson cap.
    """
    clusters: List[List[int]] = []
    for index, vector in enumerate(vectors):
        placed = False
        for cluster in clusters:
            if _cosine(vectors[cluster[0]], vector) >= threshold:
                cluster.append(index)
                placed = True
                break
        if not placed:
            clusters.append([index])
    return clusters


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity of two vectors (0.0 when either is zero-length)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
