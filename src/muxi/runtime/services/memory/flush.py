# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Pre-Compaction Flush - Silent Turn Before Buffer Eviction
# Description:  Persists at-risk buffer context to the log + graph pre-eviction
# Role:         Formation-level service bridging WorkingMemory FIFO cleanup
#               and the Captain's Log / Knowledge Graph write pipeline
# Usage:        Created and attached by the Overlord during startup
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 3 (Context Optimization - Pre-Compaction Flush).
#
# The working memory buffer is bounded: when its estimated usage exceeds
# max_memory_mb, FIFO cleanup evicts the oldest items -- silently losing
# conversational context in long-running sessions where the buffer fills
# before the periodic Captain's Log digest runs. This service hooks the
# eviction path so nothing is lost without first being captured:
#
# 1. Threshold trigger: when buffer usage crosses flush_threshold (default
#    0.80) of the limit, the oldest ~25% of buffer items (the next eviction
#    candidates) are handed to this service BEFORE any eviction happens.
# 2. Eviction safety net: any item that reaches eviction without having
#    been flushed is handed over at eviction time (the item dicts are
#    snapshotted first, so persistence proceeds after the buffer drops them).
#
# Each hand-off runs a SILENT TURN: an LLM pass outside the user-visible
# conversation that digests the at-risk items through the Captain's Log
# pipeline -- which writes the narrative entry, source lineage, lessons,
# and the digest's knowledge graph facts in one pass. No reply is surfaced.
#
# Failure isolation: the WorkingMemory listener callback never raises into
# FIFO cleanup, and a failed silent turn only loses that best-effort flush
# (eviction proceeds regardless -- exactly what happens today without it).
# =============================================================================

import asyncio
from typing import Any, Dict, List, Optional

from .. import observability

# PRD defaults (Configuration Reference -> memory.compaction).
DEFAULT_FLUSH_ENABLED = True
DEFAULT_FLUSH_THRESHOLD = 0.80


class PreCompactionFlushService:
    """Runs the silent memory flush before working-memory eviction."""

    def __init__(self, captains_log, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the flush service.

        Args:
            captains_log: Phase 2 CaptainsLogService. The silent turn rides
                its digest pipeline (log entry + lessons + graph facts).
            config: The ``memory.compaction`` formation config section.
        """
        config = config or {}
        self.enabled = bool(config.get("flush_enabled", DEFAULT_FLUSH_ENABLED))
        self.flush_threshold = float(config.get("flush_threshold", DEFAULT_FLUSH_THRESHOLD))
        self.captains_log = captains_log
        self._model_getter = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def attach(self, working_memory, model_getter) -> None:
        """
        Register the eviction listener on the working memory buffer.

        Must be called from the event loop the flush should run on (the
        Overlord's startup path). No-op when disabled or when either side
        of the bridge is missing.

        Args:
            working_memory: The WorkingMemory buffer instance to guard.
            model_getter: Zero-argument callable returning the digest LLM
                (or None while unavailable), resolved per flush.
        """
        if not self.enabled or working_memory is None or self.captains_log is None:
            return
        self._model_getter = model_getter
        self._loop = asyncio.get_running_loop()
        working_memory.set_eviction_listener(self._on_items_at_risk, self.flush_threshold)

    # ------------------------------------------------------------------
    # WorkingMemory bridge (sync, called from the FIFO cleanup thread)
    # ------------------------------------------------------------------

    def _on_items_at_risk(self, items: List[Dict[str, Any]]) -> None:
        """
        Receive at-risk buffer item snapshots and schedule the silent turn.

        Called synchronously by WorkingMemory's cleanup path (which runs on
        a daemon thread); the flush itself is scheduled onto the formation
        event loop. Never raises.
        """
        if not items or self._loop is None or self._loop.is_closed():
            return
        try:
            observability.observe(
                event_type=(observability.ConversationEvents.MEMORY_PRECOMPACTION_FLUSH_TRIGGERED),
                level=observability.EventLevel.DEBUG,
                data={"items": len(items), "threshold": self.flush_threshold},
                description=(
                    f"Pre-compaction flush triggered for {len(items)} at-risk buffer item(s)"
                ),
            )
            asyncio.run_coroutine_threadsafe(self.flush_items(list(items)), self._loop)
        except Exception as e:
            self._observe_failure(e, user_id=None)

    # ------------------------------------------------------------------
    # The silent turn
    # ------------------------------------------------------------------

    async def flush_items(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Run the silent memory flush for a batch of buffer item snapshots.

        Groups items per user, renders them as conversation turns, and
        digests each user's batch through the Captain's Log pipeline
        (narrative entry + source lineage + lessons + graph facts).
        Failure-isolated per user; returns aggregate stored counts.
        """
        totals = {"entries": 0, "sources": 0, "lessons": 0}
        model = self._model_getter() if self._model_getter else None
        if model is None or self.captains_log is None:
            return totals

        for user_id, turns in _group_items_by_user(items).items():
            try:
                stored = await self.captains_log.digest_turns(user_id, turns, model)
                totals["entries"] += stored["entries"]
                totals["sources"] += stored["sources"]
                totals["lessons"] += stored["lessons"]
                observability.observe(
                    event_type=(
                        observability.ConversationEvents.MEMORY_PRECOMPACTION_FLUSH_COMPLETED
                    ),
                    level=observability.EventLevel.DEBUG,
                    data={"user_id": user_id, "turns": len(turns), **stored},
                    description=(
                        f"Pre-compaction flush persisted {len(turns)} buffer item(s) "
                        "before eviction"
                    ),
                )
            except Exception as e:
                self._observe_failure(e, user_id=user_id)
        return totals

    def _observe_failure(self, error: Exception, user_id: Optional[str]) -> None:
        """Emit the flush-failed event (shared by both failure sites)."""
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_PRECOMPACTION_FLUSH_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "user_id": user_id,
                "error": str(error),
                "error_type": type(error).__name__,
            },
            description=f"Pre-compaction flush failed: {error}",
        )


def _group_items_by_user(items: List[Dict[str, Any]]) -> Dict[str, List[tuple]]:
    """
    Group buffer item snapshots into per-user digest turns.

    Each turn is ``(timestamp_key, rendered_text)`` -- the exact shape the
    Captain's Log digest consumes, with the buffer timestamp as the
    ``buffer_item`` source-lineage key. Items without a ``user_id`` in
    their metadata are skipped (with a debug event): attributing them to a
    fallback scope would pollute a real user's persistent memory --
    single-user mode stores ``user_id`` explicitly, so legitimate chat
    items always carry the key.
    """
    grouped: Dict[str, List[tuple]] = {}
    skipped_missing_user = 0
    for item in items:
        metadata = item.get("metadata") or {}
        text = (item.get("text") or "").strip()
        if not text:
            continue
        raw_user_id = metadata.get("user_id")
        if raw_user_id is None:
            skipped_missing_user += 1
            continue
        role = metadata.get("role")
        if role == "user":
            rendered = f"User: {text}"
        elif role == "assistant":
            rendered = f"Assistant: {text}"
        else:
            rendered = text
        timestamp = item.get("timestamp") or 0.0
        grouped.setdefault(str(raw_user_id), []).append((f"{float(timestamp):.6f}", rendered))
    if skipped_missing_user:
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_PRECOMPACTION_FLUSH_FAILED,
            level=observability.EventLevel.DEBUG,
            data={"reason": "missing_user_id", "skipped_items": skipped_missing_user},
            description=(
                f"Pre-compaction flush skipped {skipped_missing_user} buffer item(s) "
                "without user_id metadata"
            ),
        )
    return grouped
