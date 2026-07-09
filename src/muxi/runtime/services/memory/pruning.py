# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Context Pruner - Cache-TTL Tool-Result Pruning
# Description:  Prunes old tool results / oversized turns on idle resume
# Role:         Formation-level utility applied when assembling chat context
# Usage:        Created by the Overlord when memory.pruning is configured
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 3 (Context Optimization - Cache-TTL Pruning).
#
# Providers cache prompt prefixes for a short window (Anthropic: 5 minutes).
# When a session resumes after that window, the whole prefix is re-cached at
# full cost -- and old bulky content (tool results, large pasted outputs)
# is the expensive part. This pruner trims that content from the assembled
# context before the next request:
#
# - mode "never":     pruner is inert (the default when memory.pruning is
#                     not configured -- the formation behaves byte-identically
#                     to a build without this module).
# - mode "cache-ttl": prune only when the (user, session) has been idle for
#                     longer than cache_ttl_seconds.
# - mode "always":    prune on every context assembly.
#
# Two strategies (PRD "Pruning Strategies"):
# - soft_trim (default): keep the first/last SOFT_TRIM_KEEP_CHARS characters
#   of any prunable message longer than soft_trim_max_chars, replacing the
#   middle with a truncation marker.
# - hard_clear: replace the prunable message body with CLEARED_PLACEHOLDER.
#
# "Keep recent" is always applied: the newest keep_last_n_tool_results
# prunable messages are never touched.
#
# A message is prunable when its role is "tool" (explicit tool results, for
# callers that assemble raw chat-API message lists) or when its content
# exceeds soft_trim_max_chars (tool output surfaced inside stored buffer
# turns -- the shape the orchestrator's clean-context path produces).
#
# Failure-isolated: pruning errors return the original messages unchanged.
# =============================================================================

import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from .. import observability

MODE_ALWAYS = "always"
MODE_CACHE_TTL = "cache-ttl"
MODE_NEVER = "never"
PRUNING_MODES = {MODE_ALWAYS, MODE_CACHE_TTL, MODE_NEVER}

STRATEGY_SOFT_TRIM = "soft_trim"
STRATEGY_HARD_CLEAR = "hard_clear"
PRUNING_STRATEGIES = {STRATEGY_SOFT_TRIM, STRATEGY_HARD_CLEAR}

# PRD defaults (Configuration Reference -> memory.pruning).
DEFAULT_MODE = MODE_CACHE_TTL
DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_KEEP_LAST_N_TOOL_RESULTS = 3
DEFAULT_SOFT_TRIM_MAX_CHARS = 4000

# PRD "Soft trim": keep first 1500 + last 1500 chars, truncate the middle.
SOFT_TRIM_KEEP_CHARS = 1500

CLEARED_PLACEHOLDER = "[Previous output cleared]"

# Bound on tracked (user, session) activity timestamps.
ACTIVITY_CACHE_SIZE = 1024


class ContextPruner:
    """Prunes old tool results from assembled context after idle periods."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the pruner from the ``memory.pruning`` config section.

        Args:
            config: The ``memory.pruning`` formation config section. When
                the section is absent the formation never constructs a
                pruner at all (inert when unconfigured); a present-but-
                partial section fills in the PRD defaults.
        """
        config = config or {}
        self.mode = str(config.get("mode", DEFAULT_MODE)).strip().lower()
        if self.mode not in PRUNING_MODES:
            raise ValueError(
                f"memory.pruning.mode must be one of {sorted(PRUNING_MODES)}, got {self.mode!r}"
            )
        self.strategy = str(config.get("strategy", STRATEGY_SOFT_TRIM)).strip().lower()
        if self.strategy not in PRUNING_STRATEGIES:
            raise ValueError(
                f"memory.pruning.strategy must be one of {sorted(PRUNING_STRATEGIES)}, "
                f"got {self.strategy!r}"
            )
        self.cache_ttl_seconds = float(config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS))
        self.keep_last_n_tool_results = int(
            config.get("keep_last_n_tool_results", DEFAULT_KEEP_LAST_N_TOOL_RESULTS)
        )
        self.soft_trim_max_chars = int(
            config.get("soft_trim_max_chars", DEFAULT_SOFT_TRIM_MAX_CHARS)
        )

        # Last request timestamp per (user, session), LRU-capped.
        self._last_activity: "OrderedDict[Tuple[str, str], float]" = OrderedDict()

    # ------------------------------------------------------------------
    # Activity tracking (the cache-ttl trigger)
    # ------------------------------------------------------------------

    def _activity_key(self, user_id: Any, session_id: Any) -> Tuple[str, str]:
        return (str(user_id), str(session_id or "default"))

    def record_activity(self, user_id: Any, session_id: Any, now: Optional[float] = None) -> None:
        """Record a request for (user, session); starts the idle clock."""
        key = self._activity_key(user_id, session_id)
        self._last_activity[key] = time.time() if now is None else now
        self._last_activity.move_to_end(key)
        while len(self._last_activity) > ACTIVITY_CACHE_SIZE:
            self._last_activity.popitem(last=False)

    def should_prune(self, user_id: Any, session_id: Any, now: Optional[float] = None) -> bool:
        """Return True when this request's context should be pruned."""
        if self.mode == MODE_NEVER:
            return False
        if self.mode == MODE_ALWAYS:
            return True
        last = self._last_activity.get(self._activity_key(user_id, session_id))
        if last is None:
            # First request of the session in this process: nothing was
            # provider-cached for it, so there is nothing worth pruning.
            return False
        now = time.time() if now is None else now
        return (now - last) > self.cache_ttl_seconds

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune_turns(
        self, user_id: Any, session_id: Any, turns: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prune one request's history turns and record the request's activity.

        The orchestrator entry point: checks the idle trigger, applies the
        strategy, and stamps the activity clock for the next request.
        Failure-isolated -- any error returns the original turns unchanged.
        """
        try:
            pruned_turns = turns
            pruned_count = 0
            if turns and self.should_prune(user_id, session_id):
                pruned_turns, pruned_count = self.prune_messages(turns)
                if pruned_count:
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_CONTEXT_PRUNED,
                        level=observability.EventLevel.DEBUG,
                        data={
                            "user_id": str(user_id),
                            "session_id": str(session_id or "default"),
                            "mode": self.mode,
                            "strategy": self.strategy,
                            "pruned_messages": pruned_count,
                        },
                        description=(
                            f"Pruned {pruned_count} stale tool-result message(s) "
                            "from resumed session context"
                        ),
                    )
            self.record_activity(user_id, session_id)
            return pruned_turns
        except Exception:
            return turns

    def prune_messages(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Apply the pruning strategy to one message list.

        Returns (new message list, number of messages pruned). The newest
        ``keep_last_n_tool_results`` prunable messages are preserved intact
        (the PRD's "keep recent" rule); older ones are soft-trimmed or
        hard-cleared per the configured strategy. Input dicts are never
        mutated -- pruned messages are shallow copies.
        """
        prunable = [index for index, message in enumerate(messages) if self._is_prunable(message)]
        if self.keep_last_n_tool_results > 0:
            prunable = prunable[: -self.keep_last_n_tool_results]
        if not prunable:
            return messages, 0

        result = list(messages)
        pruned = 0
        for index in prunable:
            content = str(result[index].get("content") or "")
            replacement = self._apply_strategy(content)
            if replacement == content:
                continue
            updated = dict(result[index])
            updated["content"] = replacement
            result[index] = updated
            pruned += 1
        return result, pruned

    def _is_prunable(self, message: Dict[str, Any]) -> bool:
        """A message is prunable as a tool result or an oversized turn."""
        if message.get("role") == "tool":
            return True
        content = message.get("content")
        return isinstance(content, str) and len(content) > self.soft_trim_max_chars

    def _apply_strategy(self, content: str) -> str:
        """Return the pruned body for one message's content."""
        if self.strategy == STRATEGY_HARD_CLEAR:
            return CLEARED_PLACEHOLDER
        if len(content) <= self.soft_trim_max_chars:
            return content
        trimmed = len(content) - 2 * SOFT_TRIM_KEEP_CHARS
        return (
            content[:SOFT_TRIM_KEEP_CHARS]
            + f"\n[... {trimmed} chars trimmed ...]\n"
            + content[-SOFT_TRIM_KEEP_CHARS:]
        )
