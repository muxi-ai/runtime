"""Unit tests for MCP tool filtering (whitelist / blacklist).

Three layers of coverage:

1. **Pure ``apply_filter`` semantics** — literal/glob match, mode
   exclusivity, deterministic ordering, FilterReport shape. No I/O.
2. **``ToolFilterSpec.from_config``** — dict → spec normalisation,
   including malformed inputs that the formation loader would have
   rejected (we tolerate them at the runtime boundary so the filter
   itself is total).
3. **Validation hooks** — the formation-level validator's
   ``_validate_mcp_tools_block`` enforces mutex, type, and
   non-empty-pattern rules at load time.

The PRD's e2e test (registration-time integration with a mock MCP
upstream) is deliberately out of scope here and lives in a separate
PR per the rollout plan.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from muxi.runtime.formation.config.validation import FormationValidator, ValidationResult
from muxi.runtime.services.mcp.tool_filter import (
    FilterReport,
    ToolFilterSpec,
    apply_filter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def github_like_catalog() -> List[Dict[str, Any]]:
    """A representative upstream catalog modelled after github-mcp.

    Mix of literal-friendly names (`create_issue`), glob-friendly
    families (`list_*`, `get_*`, `search_*`), and destructive ops
    (`delete_*`, `force_push_branch`) that real-world whitelists /
    blacklists are likely to target.
    """
    names = [
        "list_branches",
        "list_commits",
        "list_issues",
        "list_pull_requests",
        "get_branch",
        "get_commit",
        "get_issue",
        "search_code",
        "search_issues",
        "create_issue",
        "create_pull_request",
        "delete_branch",
        "delete_repo",
        "force_push_branch",
    ]
    return [{"name": n, "description": f"{n} description", "inputSchema": {}} for n in names]


def _make_validator() -> Any:
    """Tiny harness that exposes only what the helper needs: ``.result``."""

    class _V:
        def __init__(self) -> None:
            self.result = ValidationResult()

        # Bind the unbound method straight onto the harness.
        _validate_mcp_tools_block = FormationValidator._validate_mcp_tools_block

    return _V()


# ---------------------------------------------------------------------------
# 1. Pure apply_filter semantics
# ---------------------------------------------------------------------------


def test_no_filter_block_passes_all_tools(github_like_catalog: List[Dict[str, Any]]) -> None:
    """Inactive spec → upstream catalog passes through unchanged.

    This is the back-compat path. ``report`` is None so the caller
    knows not to emit ``mcp.tool_filter.applied``.
    """
    spec = ToolFilterSpec()  # default: no mode, no patterns
    kept, report = apply_filter(github_like_catalog, spec)
    assert kept == list(github_like_catalog)
    assert report is None


def test_whitelist_literal_only(github_like_catalog: List[Dict[str, Any]]) -> None:
    """Literal names register exactly themselves, drop everything else."""
    spec = ToolFilterSpec.from_config({"whitelist": ["create_issue", "get_branch"]})
    kept, report = apply_filter(github_like_catalog, spec)
    assert [t["name"] for t in kept] == ["get_branch", "create_issue"]  # upstream order preserved
    assert report is not None
    assert report.mode == "whitelist"
    assert report.registered_tool_count == 2
    assert report.upstream_tool_count == len(github_like_catalog)


def test_blacklist_literal_only(github_like_catalog: List[Dict[str, Any]]) -> None:
    """Literal blacklist drops only the named tool."""
    spec = ToolFilterSpec.from_config({"blacklist": ["delete_repo"]})
    kept, report = apply_filter(github_like_catalog, spec)
    names = [t["name"] for t in kept]
    assert "delete_repo" not in names
    assert "delete_branch" in names  # still here; only delete_repo was named
    assert len(names) == len(github_like_catalog) - 1
    assert report is not None and report.mode == "blacklist"


def test_whitelist_glob_star(github_like_catalog: List[Dict[str, Any]]) -> None:
    """``list_*`` matches every list_* tool, drops everything else."""
    spec = ToolFilterSpec.from_config({"whitelist": ["list_*"]})
    kept, report = apply_filter(github_like_catalog, spec)
    names = [t["name"] for t in kept]
    assert names == [
        "list_branches",
        "list_commits",
        "list_issues",
        "list_pull_requests",
    ]
    assert report is not None
    pattern, matches = report.pattern_resolutions[0]
    assert pattern == "list_*"
    assert matches == names


def test_whitelist_glob_question() -> None:
    """``v?`` matches single-char suffix only — ``v1``/``v2``, NOT ``v10``."""
    catalog = [{"name": n} for n in ("v1", "v2", "v10", "verbose")]
    spec = ToolFilterSpec.from_config({"whitelist": ["v?"]})
    kept, report = apply_filter(catalog, spec)
    assert [t["name"] for t in kept] == ["v1", "v2"]
    assert report is not None and report.registered_tool_count == 2


def test_blacklist_glob(github_like_catalog: List[Dict[str, Any]]) -> None:
    """``delete_*`` drops every delete_* tool."""
    spec = ToolFilterSpec.from_config({"blacklist": ["delete_*"]})
    kept, report = apply_filter(github_like_catalog, spec)
    names = [t["name"] for t in kept]
    assert "delete_branch" not in names
    assert "delete_repo" not in names
    # Other tools survived.
    assert "create_issue" in names
    assert report is not None
    pattern, matches = report.pattern_resolutions[0]
    assert pattern == "delete_*"
    assert sorted(matches) == ["delete_branch", "delete_repo"]


def test_mixed_literal_and_glob_in_whitelist(
    github_like_catalog: List[Dict[str, Any]],
) -> None:
    """One literal + one glob in the same whitelist combine OR-style."""
    spec = ToolFilterSpec.from_config({"whitelist": ["create_issue", "list_*"]})
    kept, report = apply_filter(github_like_catalog, spec)
    names = [t["name"] for t in kept]
    # All list_* tools plus the literal create_issue, in upstream order.
    assert names == [
        "list_branches",
        "list_commits",
        "list_issues",
        "list_pull_requests",
        "create_issue",
    ]
    assert report is not None
    # Two pattern entries, each carrying its own resolution list.
    assert len(report.pattern_resolutions) == 2
    by_pattern = {p: m for p, m in report.pattern_resolutions}
    assert by_pattern["create_issue"] == ["create_issue"]
    assert by_pattern["list_*"] == [
        "list_branches",
        "list_commits",
        "list_issues",
        "list_pull_requests",
    ]


def test_unknown_literal_pattern_records_difflib_suggestions(
    github_like_catalog: List[Dict[str, Any]],
) -> None:
    """A typo'd literal surfaces difflib 'did you mean?' suggestions."""
    spec = ToolFilterSpec.from_config({"whitelist": ["create_isue"]})  # typo
    kept, report = apply_filter(github_like_catalog, spec)
    assert kept == []  # nothing matched
    assert report is not None and report.registered_tool_count == 0
    assert len(report.unknown_patterns) == 1
    pattern, suggestions = report.unknown_patterns[0]
    assert pattern == "create_isue"
    # difflib should pick up "create_issue" given the small Levenshtein gap.
    assert "create_issue" in suggestions


def test_unknown_glob_pattern_has_empty_suggestion_list(
    github_like_catalog: List[Dict[str, Any]],
) -> None:
    """Globs that match nothing produce no difflib noise.

    Suggesting alternatives for ``destroy_*`` would surface arbitrary
    unrelated names; per the design we explicitly suppress this for any
    pattern containing a glob metacharacter.
    """
    spec = ToolFilterSpec.from_config({"whitelist": ["destroy_*"]})
    _, report = apply_filter(github_like_catalog, spec)
    assert report is not None
    assert len(report.unknown_patterns) == 1
    _, suggestions = report.unknown_patterns[0]
    assert suggestions == []


def test_post_filter_empty_set_reported_with_zero_count(
    github_like_catalog: List[Dict[str, Any]],
) -> None:
    """Whitelist that matches nothing → kept=[], registered_tool_count=0.

    The filter itself does not raise or skip — that decision belongs
    to ``MCPService._connect_single_transport``, which observes the
    report and aborts registration. The pure function just reports
    the truth.
    """
    spec = ToolFilterSpec.from_config({"whitelist": ["nonexistent_*"]})
    kept, report = apply_filter(github_like_catalog, spec)
    assert kept == []
    assert report is not None
    assert report.registered_tool_count == 0
    assert report.upstream_tool_count == len(github_like_catalog)


def test_filter_preserves_full_tool_dict(github_like_catalog: List[Dict[str, Any]]) -> None:
    """Filter is a pass-through filter, not a projection.

    The kept tools retain ``description`` / ``inputSchema`` / any other
    upstream fields untouched — the filter only decides which tools
    survive, not what shape they take.
    """
    spec = ToolFilterSpec.from_config({"whitelist": ["create_issue"]})
    kept, _ = apply_filter(github_like_catalog, spec)
    assert kept[0] == {
        "name": "create_issue",
        "description": "create_issue description",
        "inputSchema": {},
    }


def test_filter_preserves_upstream_order(github_like_catalog: List[Dict[str, Any]]) -> None:
    """Tool order in the surviving list matches upstream order, not pattern order.

    This matters for deterministic test assertions and for the planning
    prompt's tool render order — which today follows registration order.
    """
    spec = ToolFilterSpec.from_config({"whitelist": ["create_issue", "list_*"]})
    kept, _ = apply_filter(github_like_catalog, spec)
    # ``list_*`` tools come first in upstream; literal ``create_issue``
    # comes later → that order is preserved.
    assert [t["name"] for t in kept].index("list_branches") < [t["name"] for t in kept].index(
        "create_issue"
    )


# ---------------------------------------------------------------------------
# 2. ToolFilterSpec.from_config tolerance
# ---------------------------------------------------------------------------


def test_spec_from_none_returns_inactive() -> None:
    spec = ToolFilterSpec.from_config(None)
    assert spec.is_active is False


def test_spec_from_empty_dict_returns_inactive() -> None:
    spec = ToolFilterSpec.from_config({})
    assert spec.is_active is False


def test_spec_from_both_keys_present_falls_back_to_inactive() -> None:
    """Both keys → no filter at runtime (the loader rejects this earlier).

    The runtime tolerates this so a malformed config doesn't crash
    registration; the formation loader's
    ``_validate_mcp_tools_block`` is the canonical fail-fast site.
    """
    spec = ToolFilterSpec.from_config({"whitelist": ["a"], "blacklist": ["b"]})
    assert spec.is_active is False


def test_spec_from_empty_list_returns_inactive() -> None:
    spec = ToolFilterSpec.from_config({"whitelist": []})
    assert spec.is_active is False


def test_spec_strips_non_string_entries() -> None:
    """Non-string entries are skipped, not raised on.

    The validator catches them at load time; the filter just survives.
    """
    spec = ToolFilterSpec.from_config({"whitelist": ["valid", 42, None, "also_valid"]})
    assert spec.is_active is True
    assert spec.patterns == ("valid", "also_valid")


# ---------------------------------------------------------------------------
# 3. Formation-level validation
# ---------------------------------------------------------------------------


def test_validation_rejects_whitelist_and_blacklist_both_set() -> None:
    """Mutex rule fires at load time with a clear, actionable message."""
    v = _make_validator()
    v._validate_mcp_tools_block({"whitelist": ["list_*"], "blacklist": ["delete_*"]}, "demo-mcp")
    assert v.result.errors
    msg = v.result.errors[-1]
    assert "demo-mcp" in msg
    assert "whitelist" in msg and "blacklist" in msg
    assert "not both" in msg


def test_validation_rejects_neither_whitelist_nor_blacklist() -> None:
    """Empty ``tools`` block (with neither sub-key) is a load-time error.

    The block exists clearly with intent — it shouldn't be silently
    treated as "no filter".
    """
    v = _make_validator()
    v._validate_mcp_tools_block({}, "demo-mcp")
    assert v.result.errors
    msg = v.result.errors[-1]
    assert "whitelist" in msg and "blacklist" in msg


def test_validation_rejects_non_list_patterns() -> None:
    """``whitelist`` / ``blacklist`` must be a list."""
    v = _make_validator()
    v._validate_mcp_tools_block({"whitelist": "list_*"}, "demo-mcp")
    assert v.result.errors
    assert "must be a list" in v.result.errors[-1]


def test_validation_rejects_non_string_pattern_entry() -> None:
    """Each pattern must be a string with a useful type error."""
    v = _make_validator()
    v._validate_mcp_tools_block({"whitelist": ["list_*", 42]}, "demo-mcp")
    assert v.result.errors
    msg = v.result.errors[-1]
    assert "tools.whitelist[1]" in msg
    assert "int" in msg


def test_validation_rejects_blank_pattern_entry() -> None:
    """Whitespace-only pattern is a load-time error.

    A blank pattern in fnmatch matches only the empty string — almost
    certainly not what the operator meant. Refusing it loudly avoids a
    silent no-op filter.
    """
    v = _make_validator()
    v._validate_mcp_tools_block({"whitelist": ["list_*", "   "]}, "demo-mcp")
    assert v.result.errors
    assert "non-empty pattern" in v.result.errors[-1]


def test_validation_warns_on_empty_pattern_list() -> None:
    """Empty list is treated as no-filter at runtime, with a warning."""
    v = _make_validator()
    v._validate_mcp_tools_block({"whitelist": []}, "demo-mcp")
    # No errors — the filter just no-ops.
    assert not v.result.errors
    assert v.result.warnings
    assert "empty" in v.result.warnings[-1]


def test_validation_clean_whitelist_produces_no_errors_no_warnings() -> None:
    v = _make_validator()
    v._validate_mcp_tools_block({"whitelist": ["list_*", "get_*"]}, "demo-mcp")
    assert v.result.errors == []
    assert v.result.warnings == []


def test_validation_clean_blacklist_produces_no_errors_no_warnings() -> None:
    v = _make_validator()
    v._validate_mcp_tools_block({"blacklist": ["delete_*", "force_push_*"]}, "demo-mcp")
    assert v.result.errors == []
    assert v.result.warnings == []


# ---------------------------------------------------------------------------
# 4. FilterReport shape sanity
# ---------------------------------------------------------------------------


def test_filter_report_pattern_resolutions_one_entry_per_pattern(
    github_like_catalog: List[Dict[str, Any]],
) -> None:
    """Every declared pattern contributes exactly one resolution entry.

    Even patterns that match nothing — they appear with an empty match
    list. Operators should be able to cross-reference the spec and the
    resolution table 1:1 when reading startup logs.
    """
    spec = ToolFilterSpec.from_config({"whitelist": ["list_*", "create_issue", "destroy_*"]})
    _, report = apply_filter(github_like_catalog, spec)
    assert report is not None
    assert len(report.pattern_resolutions) == 3
    by_pattern = {p: m for p, m in report.pattern_resolutions}
    assert "list_*" in by_pattern and len(by_pattern["list_*"]) > 0
    assert by_pattern["create_issue"] == ["create_issue"]
    assert by_pattern["destroy_*"] == []  # no matches but still recorded


def test_filter_report_is_dataclass_with_expected_fields(
    github_like_catalog: List[Dict[str, Any]],
) -> None:
    """Pin the public shape of FilterReport so observability code can rely on it."""
    spec = ToolFilterSpec.from_config({"whitelist": ["list_*"]})
    _, report = apply_filter(github_like_catalog, spec)
    assert isinstance(report, FilterReport)
    # Required fields used by _observe_filter_applied:
    assert isinstance(report.mode, str)
    assert isinstance(report.patterns, tuple)
    assert isinstance(report.upstream_tool_count, int)
    assert isinstance(report.registered_tool_count, int)
    assert isinstance(report.pattern_resolutions, list)
    assert isinstance(report.unknown_patterns, list)


# ---------------------------------------------------------------------------
# Issue 2 fix — nameless tools dropped symmetrically in both modes.
# ---------------------------------------------------------------------------


def test_blacklist_drops_nameless_tools_symmetrically() -> None:
    """Tools with missing/non-string ``name`` are dropped in BOTH modes.

    Regression: before the fix, blacklist mode silently let through
    malformed upstream tools because ``_tool_name(t) is None`` and
    ``None not in matched_set`` is always True. Whitelist mode was
    fine (``None in matched_set`` is always False). The asymmetry
    meant a blacklist intended to block destructive tooling could
    leak unnamed tools without any signal.
    """
    catalog: List[Dict[str, Any]] = [
        {"name": "create_issue", "description": "real"},
        {"description": "no name field"},  # nameless
        {"name": None, "description": "explicit None"},  # nameless
        {"name": 42, "description": "non-string name"},  # nameless
        {"name": "", "description": "empty name"},  # nameless (empty)
        {"name": "delete_repo", "description": "destructive"},
    ]

    # Blacklist: even though no nameless tool matches the pattern, they
    # must still be dropped — we cannot reason about whether they are
    # safe to expose without a name.
    spec_b = ToolFilterSpec.from_config({"blacklist": ["delete_*"]})
    kept_b, _ = apply_filter(catalog, spec_b)
    kept_names = [t.get("name") for t in kept_b]
    # Only the named, non-blacklisted tool survives.
    assert kept_names == ["create_issue"]

    # Whitelist mirror: same input, same outcome for nameless tools.
    spec_w = ToolFilterSpec.from_config({"whitelist": ["create_issue"]})
    kept_w, _ = apply_filter(catalog, spec_w)
    assert [t.get("name") for t in kept_w] == ["create_issue"]


# ---------------------------------------------------------------------------
# Issue 3 fix — `_observe_filter_applied` suppresses INFO init line on
# empty-set, unit-tested via the FilterReport contract that the helper
# branches on.
# ---------------------------------------------------------------------------


def test_filter_report_signals_empty_set_via_count() -> None:
    """``registered_tool_count == 0`` is the contract the service uses
    to decide whether to print the ``[ INFO ]`` init line.

    A whitelist that matches nothing must produce a report whose
    ``registered_tool_count`` is exactly zero (not None, not a falsy
    sentinel) so the service's ``> 0`` guard is unambiguous.
    """
    catalog = [{"name": "alpha"}, {"name": "beta"}]
    spec = ToolFilterSpec.from_config({"whitelist": ["nonexistent_tool"]})
    kept, report = apply_filter(catalog, spec)
    assert kept == []
    assert report is not None
    assert report.registered_tool_count == 0
    assert report.upstream_tool_count == 2
    # Unknown-pattern suggestions still recorded so the audit-trail
    # event in ``_observe_filter_applied`` can fire even on empty-set.
    assert report.unknown_patterns
    pattern, _suggestions = report.unknown_patterns[0]
    assert pattern == "nonexistent_tool"


# ---------------------------------------------------------------------------
# Issue 1 fix — typed exception for empty-set registration abort.
# ---------------------------------------------------------------------------


def test_empty_set_error_inherits_from_mcp_error_family() -> None:
    """``MCPToolFilterEmptySetError`` extends ``MCPError`` so it travels
    through the same exception-handling layers as other MCP errors,
    but is distinct from ``MCPConnectionError`` / ``MCPTimeoutError``
    / ``MCPCancelledError`` so callers can branch on it specifically
    (clean skip vs. registration failure)."""
    from muxi.runtime.services.mcp.transports.base import (
        MCPCancelledError,
        MCPConnectionError,
        MCPError,
        MCPTimeoutError,
        MCPToolFilterEmptySetError,
    )

    err = MCPToolFilterEmptySetError(
        "MCP server 'gh' skipped: whitelist matched 0 of 44 upstream tools",
        details={"server_id": "gh", "mode": "whitelist", "upstream_tool_count": 44},
    )
    # Inheritance — must reach generic Exception handlers and the MCP
    # family root, but NOT be conflated with the existing leaf types.
    assert isinstance(err, MCPError)
    assert isinstance(err, Exception)
    assert not isinstance(err, MCPConnectionError)
    assert not isinstance(err, MCPTimeoutError)
    assert not isinstance(err, MCPCancelledError)

    # Payload — observability code reads ``details`` for structured
    # event data; the message is human-readable.
    assert err.details["server_id"] == "gh"
    assert err.details["mode"] == "whitelist"
    assert err.details["upstream_tool_count"] == 44
    assert "skipped" in err.message
