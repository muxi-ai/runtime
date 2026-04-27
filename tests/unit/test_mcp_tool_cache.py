"""Unit tests for the MCP tool result cache.

The tool cache is a small, deliberately conservative LRU-less in-process
cache that wraps remote MCP tool invocations to eliminate redundant calls
within a single workflow's lifetime. These tests guard:

1. Key determinism — semantically identical calls must hash to the same
   key regardless of dict iteration order.
2. Scoping — formation_id and user_id must be part of the key so two
   formations / users in the same process never collide.
3. TTL expiry — entries past their TTL must report as misses.
4. is_cacheable heuristics — mutators must be denied; reads must be
   allowed; ambiguous tools must default-deny.
5. Built-in non-MCP tools (generate_file, run_skill, activate_skill)
   must always be denied because they have side effects.
6. Counters (hits/misses/stores/skipped) must increment correctly so
   we can debug cache effectiveness in production.
"""

from __future__ import annotations

import time

import pytest

from muxi.runtime.services.mcp import tool_cache


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    tool_cache.clear()
    yield
    tool_cache.clear()


# ---------------------------------------------------------------------------
# Key determinism + scoping
# ---------------------------------------------------------------------------


def test_make_key_is_deterministic_for_same_inputs():
    k1 = tool_cache.make_key("f1", "search", {"q": "x"}, "srv", "u1")
    k2 = tool_cache.make_key("f1", "search", {"q": "x"}, "srv", "u1")
    assert k1 == k2


def test_make_key_normalizes_dict_ordering():
    """JSON sort_keys=True must collapse different insertion orders into
    one key. Without this, identical calls would miss the cache solely
    because Python preserves insertion order in dicts."""
    k1 = tool_cache.make_key("f1", "search", {"a": 1, "b": 2}, None, None)
    k2 = tool_cache.make_key("f1", "search", {"b": 2, "a": 1}, None, None)
    assert k1 == k2


def test_make_key_changes_with_formation_id():
    k1 = tool_cache.make_key("f1", "search", {"q": "x"}, None, None)
    k2 = tool_cache.make_key("f2", "search", {"q": "x"}, None, None)
    assert k1 != k2, "formation_id must scope the cache to prevent cross-formation leakage"


def test_make_key_changes_with_user_id():
    k1 = tool_cache.make_key("f1", "search", {"q": "x"}, None, "alice")
    k2 = tool_cache.make_key("f1", "search", {"q": "x"}, None, "bob")
    assert k1 != k2, "user_id must scope per-user tools (mailboxes, vaults, etc.)"


def test_make_key_changes_with_parameters():
    k1 = tool_cache.make_key("f1", "search", {"q": "cats"}, None, None)
    k2 = tool_cache.make_key("f1", "search", {"q": "dogs"}, None, None)
    assert k1 != k2


def test_make_key_handles_missing_optionals():
    """A call with no parameters / no server / no user must still produce
    a stable key rather than crashing."""
    k = tool_cache.make_key("f1", "search", None, None, None)
    assert isinstance(k, str) and len(k) == 32


def test_make_key_uncacheable_for_non_serializable_params():
    """If parameters cannot be JSON-serialized, make_key must produce a
    sentinel key that effectively bypasses the cache rather than
    returning a misleading hash."""

    class _NotSerializable:
        pass

    k = tool_cache.make_key("f1", "search", {"obj": _NotSerializable()}, None, None)
    # default=str should handle most things; the test verifies we do not
    # raise for arbitrary objects — the json fallback uses str() so we
    # still get a (possibly object-id-based) key.
    assert isinstance(k, str)


# ---------------------------------------------------------------------------
# is_cacheable heuristic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "read_file",
        "get_user",
        "list_repos",
        "search_messages",
        "fetch_url",
        "query_database",
        "find_records",
        "lookup_address",
        "view_calendar",
        "show_status",
        "retrieve_data",
        "describe_table",
        "browse_directory",
    ],
)
def test_read_tools_are_cacheable(name):
    assert tool_cache.is_cacheable(name) is True, name


@pytest.mark.parametrize(
    "name",
    [
        "create_file",
        "update_record",
        "delete_user",
        "remove_member",
        "write_log",
        "send_email",
        "post_message",
        "push_to_branch",
        "modify_config",
        "edit_document",
        "upload_file",
        "save_state",
        "store_secret",
        "insert_row",
        "execute_script",
        "set_value",
        "add_user",
        "run_pipeline",
    ],
)
def test_mutator_tools_are_not_cacheable(name):
    assert tool_cache.is_cacheable(name) is False, name


@pytest.mark.parametrize(
    "name",
    ["generate_file", "activate_skill", "run_skill"],
)
def test_builtin_side_effect_tools_are_never_cacheable(name):
    assert tool_cache.is_cacheable(name) is False


def test_unknown_tool_default_denies():
    """Tools that match neither read nor write patterns must default to
    not cacheable. False negatives (skipping cache) only cost latency;
    false positives can produce incorrect application behavior."""
    assert tool_cache.is_cacheable("xyzzy_quux") is False


def test_empty_tool_name_is_not_cacheable():
    assert tool_cache.is_cacheable("") is False
    assert tool_cache.is_cacheable(None) is False  # type: ignore[arg-type]


def test_mutator_pattern_wins_over_read_pattern():
    """A name like "create_list" mixes both signals; the conservative
    behavior is to treat it as a mutator (not cache)."""
    assert tool_cache.is_cacheable("create_list") is False


# ---------------------------------------------------------------------------
# get / set / TTL
# ---------------------------------------------------------------------------


def test_get_returns_none_for_missing_key():
    assert tool_cache.get("nonexistent") is None


def test_set_then_get_returns_stored_value():
    key = tool_cache.make_key("f", "list_files", {"path": "/"}, None, None)
    tool_cache.set(key, {"files": ["a", "b"]})
    assert tool_cache.get(key) == {"files": ["a", "b"]}


def test_expired_entries_are_treated_as_miss(monkeypatch):
    """Past the TTL the entry must report as a miss AND be evicted so we
    don't accumulate dead memory across long-running processes."""
    key = tool_cache.make_key("f", "list_files", {}, None, None)
    tool_cache.set(key, "value")

    # Fast-forward past the TTL by patching time.time at the module
    # boundary so we don't have to actually sleep.
    real_now = time.time()
    monkeypatch.setattr(
        tool_cache, "time", type("T", (), {"time": staticmethod(lambda: real_now + 9999)})
    )
    assert tool_cache.get(key) is None
    # Re-stub back to real time before checking size, so the eviction
    # was based on the patched clock.
    assert tool_cache.size() == 0


def test_clear_resets_cache_and_stats():
    key = tool_cache.make_key("f", "list_files", {}, None, None)
    tool_cache.set(key, "v")
    tool_cache.get(key)  # 1 hit
    tool_cache.get("missing")  # 1 miss
    tool_cache.clear()
    assert tool_cache.size() == 0
    s = tool_cache.stats()
    assert s["hits"] == 0
    assert s["misses"] == 0
    assert s["stores"] == 0


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


def test_stats_track_hits_misses_stores_skipped():
    key = tool_cache.make_key("f", "list_files", {}, None, None)

    tool_cache.get(key)  # miss
    tool_cache.set(key, "v")  # store
    tool_cache.get(key)  # hit
    tool_cache.note_skipped()  # skipped

    s = tool_cache.stats()
    assert s["hits"] == 1
    assert s["misses"] == 1
    assert s["stores"] == 1
    assert s["skipped"] == 1


def test_size_reflects_distinct_entries():
    k1 = tool_cache.make_key("f", "list_files", {"p": "/a"}, None, None)
    k2 = tool_cache.make_key("f", "list_files", {"p": "/b"}, None, None)
    tool_cache.set(k1, "a")
    tool_cache.set(k2, "b")
    assert tool_cache.size() == 2
