# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Tool Filter - Whitelist/Blacklist registration-time filter
# Description:  Pure filter applied between upstream tools/list response and
#               agent-visible tool registry insertion at MCP service
#               registration time.
# Role:         Lets a formation scope an upstream MCP catalog to a subset
#               (e.g. read-only tools, no destructive ops, single product
#               surface of a multi-product MCP) via two new optional keys
#               in MCP `.afs` files: ``tools.whitelist`` / ``tools.blacklist``.
# Usage:        Constructed from the ``tools`` block of an MCP `.afs`
#               config dict by ``ToolFilterSpec.from_config()``. Called by
#               ``MCPService._connect_single_transport`` between
#               ``handler.list_tools()`` and registry population.
# Author:       MUXI Framework Team
#
# Pattern semantics: shell-style globs via ``fnmatch.fnmatchcase`` —
# case-sensitive, no regex, no anchors. Two metacharacters carry 95%
# of real use:
#
#   ``*``       any run of characters (including empty)
#   ``?``       exactly one character
#   ``[abc]``   one character from a set (rarely useful; supported)
#   ``[!abc]``  one character NOT in set (rarely useful; supported)
#
# The module is **pure**: it does not log, does not call observe(), does not
# raise on configuration mistakes that callers may want to surface
# differently (empty set, unknown patterns). The caller decides what to
# do with each FilterReport finding.
#
# Validation that *must* fail-fast (whitelist+blacklist mutex, non-string
# entries) lives in ``formation/config/validation.py`` so the formation
# loader aborts before the runtime ever sees a malformed block.
# =============================================================================

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Dict, List, Optional, Sequence, Tuple

# How many "did you mean?" suggestions to surface for an unknown pattern.
_MAX_SUGGESTIONS = 3


@dataclass(frozen=True)
class ToolFilterSpec:
    """Resolved filter declared in an MCP `.afs` ``tools`` block.

    Exactly one of ``whitelist`` / ``blacklist`` is non-None when the
    filter is active. Both being None (or the spec being absent
    entirely) means "no filter" — the caller should pass the upstream
    catalog through unchanged.

    Construction goes through :meth:`from_config` so the dict shape from
    the loader can be validated and normalised in one place.
    """

    mode: Optional[str] = None  # "whitelist" | "blacklist" | None
    patterns: Tuple[str, ...] = ()

    @property
    def is_active(self) -> bool:
        """True iff this spec actually filters anything."""
        return self.mode is not None and len(self.patterns) > 0

    @classmethod
    def from_config(cls, tools_block: Optional[Dict[str, Any]]) -> "ToolFilterSpec":
        """Build a spec from a parsed MCP-config ``tools`` block.

        ``tools_block`` is whatever lives under the ``tools`` key in the
        MCP `.afs` file (or ``None`` if absent). Mutex and type errors
        are not raised here — the formation loader's validation layer
        is the canonical fail-fast site for those. This method tolerates
        them so unit tests can exercise the filter in isolation, and
        defaults to "no filter" on anything malformed.
        """
        if not tools_block or not isinstance(tools_block, dict):
            return cls()

        whitelist = tools_block.get("whitelist")
        blacklist = tools_block.get("blacklist")

        # Mutex is a load-time error caught upstream; if we somehow get
        # both at runtime, prefer "no filter" rather than make a silent
        # choice between them.
        if whitelist is not None and blacklist is not None:
            return cls()

        if isinstance(whitelist, list) and len(whitelist) > 0:
            patterns = tuple(p for p in whitelist if isinstance(p, str))
            if patterns:
                return cls(mode="whitelist", patterns=patterns)

        if isinstance(blacklist, list) and len(blacklist) > 0:
            patterns = tuple(p for p in blacklist if isinstance(p, str))
            if patterns:
                return cls(mode="blacklist", patterns=patterns)

        return cls()


@dataclass
class FilterReport:
    """Diagnostic output of one filter application.

    Carries everything observability + init-time logging need:

    * ``mode`` / ``patterns`` — what the spec asked for.
    * ``upstream_tool_count`` / ``registered_tool_count`` — sizes
      before / after.
    * ``pattern_resolutions`` — for each pattern, the list of upstream
      tool names it matched (in their original upstream order). Empty
      list means the pattern matched nothing.
    * ``unknown_patterns`` — patterns that produced zero matches, with
      ``difflib`` suggestions. Empty list when every pattern matched
      at least one tool.
    """

    mode: str
    patterns: Tuple[str, ...]
    upstream_tool_count: int
    registered_tool_count: int
    pattern_resolutions: List[Tuple[str, List[str]]] = field(default_factory=list)
    unknown_patterns: List[Tuple[str, List[str]]] = field(default_factory=list)


def _tool_name(tool: Any) -> Optional[str]:
    """Return the upstream tool's ``name`` field, or None if shape is off.

    MCP discovery normalises tools into dicts with a ``name`` key; we
    accept anything dict-shaped here so the filter survives a future
    schema bump or test fixture variation without crashing.
    """
    if isinstance(tool, dict):
        name = tool.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _suggestions_for(pattern: str, upstream_names: Sequence[str]) -> List[str]:
    """`difflib`-based "did you mean?" list for an unmatched literal.

    For a glob pattern (containing any of ``* ? [``) the suggestion
    list is empty — globs that match nothing are usually deliberate
    over-specifications (e.g. ``delete_*`` against an upstream that
    happens to use ``destroy_*``), and surfacing arbitrary alternatives
    is more noise than signal.
    """
    if any(c in pattern for c in "*?["):
        return []
    return difflib.get_close_matches(pattern, list(upstream_names), n=_MAX_SUGGESTIONS, cutoff=0.6)


def apply_filter(
    upstream_tools: Sequence[Dict[str, Any]],
    spec: ToolFilterSpec,
) -> Tuple[List[Dict[str, Any]], Optional[FilterReport]]:
    """Apply ``spec`` to ``upstream_tools`` and return ``(kept, report)``.

    Behaviour:

    * Inactive spec (no whitelist or blacklist declared) → ``upstream_tools``
      passes through unchanged, ``report`` is ``None`` (the caller skips
      the "filter applied" observability event entirely).
    * Whitelist mode → keep tools whose ``name`` matches **at least one**
      pattern.
    * Blacklist mode → keep tools whose ``name`` matches **none** of the
      patterns.

    Tool order is preserved relative to the upstream sequence in both
    modes — handy for deterministic test assertions and for the planning
    prompt (which renders tools in registration order).

    The returned :class:`FilterReport` always carries one entry per
    pattern in :attr:`FilterReport.pattern_resolutions`. Patterns that
    matched zero tools also appear in :attr:`FilterReport.unknown_patterns`
    with ``difflib`` suggestions for literal patterns.
    """
    if not spec.is_active:
        return list(upstream_tools), None

    upstream_names = [n for n in (_tool_name(t) for t in upstream_tools) if n is not None]

    # Per-pattern resolution table — name order preserved.
    resolutions: List[Tuple[str, List[str]]] = []
    matched_set: set[str] = set()
    for pattern in spec.patterns:
        matches = [n for n in upstream_names if fnmatchcase(n, pattern)]
        resolutions.append((pattern, matches))
        matched_set.update(matches)

    if spec.mode == "whitelist":
        kept = [t for t in upstream_tools if _tool_name(t) in matched_set]
    elif spec.mode == "blacklist":
        kept = [t for t in upstream_tools if _tool_name(t) not in matched_set]
    else:
        # is_active implies mode is set; this branch is defensive only.
        return list(upstream_tools), None

    unknown: List[Tuple[str, List[str]]] = [
        (p, _suggestions_for(p, upstream_names)) for p, matches in resolutions if not matches
    ]

    report = FilterReport(
        mode=spec.mode,
        patterns=spec.patterns,
        upstream_tool_count=len(upstream_tools),
        registered_tool_count=len(kept),
        pattern_resolutions=resolutions,
        unknown_patterns=unknown,
    )
    return kept, report
