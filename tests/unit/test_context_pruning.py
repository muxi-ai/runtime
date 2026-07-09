"""Unit tests for Memory Revamp Phase 3: cache-TTL context pruning.

Covers mode gating (never/always/cache-ttl), the idle-clock trigger, the
keep-recent protection window, both strategies (soft trim shape with the
PRD's first/last 1500 chars, hard clear placeholder), tool-role vs
oversized-turn prunability, input immutability, config validation, and the
inertness pins ("never" mode and first-request-of-session behave
byte-identically to no pruner).
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.memory.pruning import (
    CLEARED_PLACEHOLDER,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_KEEP_LAST_N_TOOL_RESULTS,
    DEFAULT_SOFT_TRIM_MAX_CHARS,
    SOFT_TRIM_KEEP_CHARS,
    ContextPruner,
)


def _turn(content: str, role: str = "assistant"):
    return {"role": role, "content": content}


class TestConfig:
    def test_defaults_match_prd(self):
        pruner = ContextPruner()
        assert pruner.mode == "cache-ttl"
        assert pruner.strategy == "soft_trim"
        assert pruner.cache_ttl_seconds == DEFAULT_CACHE_TTL_SECONDS
        assert pruner.keep_last_n_tool_results == DEFAULT_KEEP_LAST_N_TOOL_RESULTS
        assert pruner.soft_trim_max_chars == DEFAULT_SOFT_TRIM_MAX_CHARS

    def test_invalid_mode_fails_fast(self):
        with pytest.raises(ValueError, match="memory.pruning.mode"):
            ContextPruner({"mode": "sometimes"})

    def test_invalid_strategy_fails_fast(self):
        with pytest.raises(ValueError, match="memory.pruning.strategy"):
            ContextPruner({"strategy": "medium_clear"})


class TestShouldPrune:
    def test_never_mode_is_inert(self):
        pruner = ContextPruner({"mode": "never"})
        pruner.record_activity("u1", "s1", now=0.0)
        assert pruner.should_prune("u1", "s1", now=10_000.0) is False

    def test_always_mode_prunes_every_request(self):
        pruner = ContextPruner({"mode": "always"})
        assert pruner.should_prune("u1", "s1") is True

    def test_cache_ttl_waits_for_idle_window(self):
        pruner = ContextPruner({"mode": "cache-ttl", "cache_ttl_seconds": 300})
        pruner.record_activity("u1", "s1", now=1000.0)
        assert pruner.should_prune("u1", "s1", now=1200.0) is False  # still cached
        assert pruner.should_prune("u1", "s1", now=1301.0) is True  # cache expired

    def test_first_request_of_session_never_prunes(self):
        # Nothing was provider-cached for a session this process has not
        # seen; pruning would only degrade context (inertness pin).
        pruner = ContextPruner({"mode": "cache-ttl"})
        assert pruner.should_prune("u1", "brand-new") is False

    def test_sessions_are_tracked_independently(self):
        pruner = ContextPruner({"mode": "cache-ttl", "cache_ttl_seconds": 300})
        pruner.record_activity("u1", "s1", now=1000.0)
        pruner.record_activity("u1", "s2", now=1290.0)
        assert pruner.should_prune("u1", "s1", now=1400.0) is True
        assert pruner.should_prune("u1", "s2", now=1400.0) is False


class TestPruneMessages:
    def test_soft_trim_keeps_head_and_tail(self):
        pruner = ContextPruner({"mode": "always", "keep_last_n_tool_results": 0})
        content = "A" * 2000 + "B" * 2000 + "C" * 2000
        pruned, count = pruner.prune_messages([_turn(content)])

        assert count == 1
        result = pruned[0]["content"]
        assert result.startswith("A" * SOFT_TRIM_KEEP_CHARS)
        assert result.endswith("C" * SOFT_TRIM_KEEP_CHARS)
        assert "chars trimmed" in result
        assert len(result) < len(content)

    def test_hard_clear_replaces_body(self):
        pruner = ContextPruner(
            {"mode": "always", "strategy": "hard_clear", "keep_last_n_tool_results": 0}
        )
        pruned, count = pruner.prune_messages([_turn("X" * 5000)])
        assert count == 1
        assert pruned[0]["content"] == CLEARED_PLACEHOLDER

    def test_tool_role_messages_are_prunable_regardless_of_size(self):
        pruner = ContextPruner(
            {"mode": "always", "strategy": "hard_clear", "keep_last_n_tool_results": 0}
        )
        pruned, count = pruner.prune_messages([_turn("small output", role="tool")])
        assert count == 1
        assert pruned[0]["content"] == CLEARED_PLACEHOLDER

    def test_small_non_tool_messages_are_untouched(self):
        pruner = ContextPruner({"mode": "always", "keep_last_n_tool_results": 0})
        messages = [_turn("short user turn", role="user"), _turn("short reply")]
        pruned, count = pruner.prune_messages(messages)
        assert count == 0
        assert pruned == messages

    def test_keep_recent_protects_last_n_results(self):
        pruner = ContextPruner(
            {"mode": "always", "strategy": "hard_clear", "keep_last_n_tool_results": 2}
        )
        messages = [_turn(f"result {index}", role="tool") for index in range(5)]
        pruned, count = pruner.prune_messages(messages)

        assert count == 3
        assert [m["content"] for m in pruned[:3]] == [CLEARED_PLACEHOLDER] * 3
        assert pruned[3]["content"] == "result 3"
        assert pruned[4]["content"] == "result 4"

    def test_input_messages_are_never_mutated(self):
        pruner = ContextPruner(
            {"mode": "always", "strategy": "hard_clear", "keep_last_n_tool_results": 0}
        )
        original = _turn("Y" * 5000)
        pruner.prune_messages([original])
        assert original["content"] == "Y" * 5000


class TestPruneTurns:
    def test_prune_turns_applies_after_idle_and_records_activity(self):
        pruner = ContextPruner(
            {"mode": "cache-ttl", "cache_ttl_seconds": 300, "keep_last_n_tool_results": 0}
        )
        big = _turn("Z" * 10_000)

        # First request: no idle history -> untouched, clock starts.
        first = pruner.prune_turns("u1", "s1", [big])
        assert first == [big]

        # Simulate an idle window past the TTL, then request again.
        key = ("u1", "s1")
        pruner._last_activity[key] = pruner._last_activity[key] - 301
        second = pruner.prune_turns("u1", "s1", [big])
        assert "chars trimmed" in second[0]["content"]

    def test_prune_turns_is_failure_isolated(self, monkeypatch):
        pruner = ContextPruner({"mode": "always", "keep_last_n_tool_results": 0})
        turns = [_turn("Z" * 10_000)]

        def explode(messages):
            raise RuntimeError("pruner boom")

        monkeypatch.setattr(pruner, "prune_messages", explode)
        result = pruner.prune_turns("u1", "s1", turns)  # must not raise
        assert result == turns
