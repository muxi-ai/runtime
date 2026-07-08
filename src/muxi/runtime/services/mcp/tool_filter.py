# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Tool Filter - Allow/Deny registration-time filter
# Description:  Pure filter applied between upstream tools/list response and
#               agent-visible tool registry insertion at MCP service
#               registration time.
# Role:         Lets a formation scope an upstream MCP catalog to a subset
#               (e.g. read-only tools, no destructive ops, single product
#               surface of a multi-product MCP) via the optional ``tools``
#               block in MCP `.afs` files: ``tools.allow`` / ``tools.deny``
#               (``whitelist`` / ``blacklist`` accepted as aliases).
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
# Filter semantics mirror the group-level GBAC ``ToolRules`` (deny after
# allow): ``allow`` alone keeps only matching tools, ``deny`` alone keeps
# everything except matching tools, both together apply allow first and
# then subtract deny. A spec may also chain onto a ``base`` spec — the
# base is applied first, so an agent-attachment override can never
# resurrect tools pruned by the formation-level catalog bound.
#
# The module is **pure**: it does not log, does not call observe(), does not
# raise on configuration mistakes that callers may want to surface
# differently (empty set, unknown patterns). The caller decides what to
# do with each FilterReport finding.
#
# Validation that *must* fail-fast (alias conflicts, non-string entries,
# unknown keys) lives in ``formation/config/validation.py`` so the
# formation loader aborts before the runtime ever sees a malformed block.
# =============================================================================

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Dict, List, Optional, Sequence, Tuple

# How many "did you mean?" suggestions to surface for an unknown pattern.
_MAX_SUGGESTIONS = 3


def _normalise_patterns(value: Any) -> Optional[Tuple[str, ...]]:
    """Normalise a pattern declaration into a non-empty tuple, or None.

    Accepts a single string (the group-level ``deny: "*"`` shorthand) or
    a list of strings. Non-string and blank entries are dropped — those
    are load-time validation errors caught upstream; here we tolerate
    them so unit tests can exercise the filter in isolation.
    """
    if isinstance(value, str):
        return (value,) if value.strip() else None
    if isinstance(value, list):
        patterns = tuple(p for p in value if isinstance(p, str) and p.strip())
        return patterns or None
    return None


@dataclass(frozen=True)
class ToolFilterSpec:
    """Resolved filter declared in an MCP `.afs` ``tools`` block.

    ``allow`` / ``deny`` are each either None (key not declared) or a
    non-empty tuple of fnmatch patterns. Both may be set together —
    semantics follow the group-level GBAC ``ToolRules``: allow first,
    then subtract deny. Both being None (and no active ``base``) means
    "no filter" — the caller should pass the upstream catalog through
    unchanged.

    ``base`` optionally chains another spec that is applied *before*
    this one. The agent-attachment override cascade uses this: the
    formation-level catalog bound is the base, so the override selects
    from the already-pruned catalog and can never resurrect tools the
    registry level removed.

    Construction goes through :meth:`from_config` so the dict shape from
    the loader can be validated and normalised in one place.
    """

    allow: Optional[Tuple[str, ...]] = None
    deny: Optional[Tuple[str, ...]] = None
    base: Optional["ToolFilterSpec"] = None

    @property
    def is_active(self) -> bool:
        """True iff this spec (or its base chain) actually filters anything."""
        if self.allow is not None or self.deny is not None:
            return True
        return self.base is not None and self.base.is_active

    @property
    def mode(self) -> Optional[str]:
        """Human-readable label for this spec's own rules (ignores base)."""
        if self.allow is not None and self.deny is not None:
            return "allow+deny"
        if self.allow is not None:
            return "allow"
        if self.deny is not None:
            return "deny"
        return None

    def stages(self) -> List["ToolFilterSpec"]:
        """Flatten the base chain into application order (base first)."""
        chain: List["ToolFilterSpec"] = []
        if self.base is not None:
            chain.extend(self.base.stages())
        if self.allow is not None or self.deny is not None:
            chain.append(self)
        return chain

    @classmethod
    def from_config(
        cls,
        tools_block: Optional[Dict[str, Any]],
        base: Optional["ToolFilterSpec"] = None,
    ) -> "ToolFilterSpec":
        """Build a spec from a parsed MCP-config ``tools`` block.

        ``tools_block`` is whatever lives under the ``tools`` key in the
        MCP `.afs` file (or ``None`` if absent). Canonical keys are
        ``allow`` / ``deny``; ``whitelist`` / ``blacklist`` are accepted
        as aliases (canonical spelling wins if both appear — a conflict
        the formation loader's validation layer rejects fail-fast).
        Type errors are not raised here either — this method tolerates
        them so unit tests can exercise the filter in isolation, and
        defaults to "no filter" on anything malformed.

        ``base`` optionally chains a spec applied before this one; an
        inactive base is dropped.
        """
        base = base if base is not None and base.is_active else None

        if not tools_block or not isinstance(tools_block, dict):
            return cls(base=base)

        allow_raw = tools_block.get("allow")
        if allow_raw is None:
            allow_raw = tools_block.get("whitelist")
        deny_raw = tools_block.get("deny")
        if deny_raw is None:
            deny_raw = tools_block.get("blacklist")

        return cls(
            allow=_normalise_patterns(allow_raw),
            deny=_normalise_patterns(deny_raw),
            base=base,
        )


@dataclass
class FilterReport:
    """Diagnostic output of one filter application.

    Carries everything observability + init-time logging need:

    * ``mode`` / ``patterns`` — what the spec asked for. ``mode`` is
      ``"allow"``, ``"deny"`` or ``"allow+deny"`` for a single-stage
      spec; chained stages join with `` > `` in application order.
    * ``upstream_tool_count`` / ``registered_tool_count`` — sizes
      before / after.
    * ``pattern_resolutions`` — for each pattern, the list of tool
      names it matched (in their original upstream order) within the
      universe its stage saw. Empty list means the pattern matched
      nothing.
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

    * Inactive spec (no allow or deny declared anywhere in the chain) →
      ``upstream_tools`` passes through unchanged, ``report`` is ``None``
      (the caller skips the "filter applied" observability event
      entirely).
    * ``allow`` → keep tools whose ``name`` matches **at least one**
      pattern.
    * ``deny`` → drop tools whose ``name`` matches **any** pattern.
    * Both in one stage → allow first, then subtract deny (deny wins on
      overlap). Deny patterns resolve against the stage's *input*
      universe, not the post-allow set, so a deny that overlaps the
      allowed set is never misreported as unknown.
    * Chained stages (``spec.base``) apply base-first; each stage's
      patterns resolve against the previous stage's output.

    Tool order is preserved relative to the upstream sequence — handy
    for deterministic test assertions and for the planning prompt
    (which renders tools in registration order).

    The returned :class:`FilterReport` always carries one entry per
    pattern in :attr:`FilterReport.pattern_resolutions`. Patterns that
    matched zero tools also appear in :attr:`FilterReport.unknown_patterns`
    with ``difflib`` suggestions for literal patterns.
    """
    if not spec.is_active:
        return list(upstream_tools), None

    # Nameless / malformed tools (``_tool_name(t) is None``) are dropped
    # whenever a filter is active, in allow and deny directions alike.
    # Since the filter cannot reason about a tool with no usable name,
    # the conservative decision is the same in either direction: drop it.
    kept = [t for t in upstream_tools if _tool_name(t) is not None]

    resolutions: List[Tuple[str, List[str]]] = []
    unknown: List[Tuple[str, List[str]]] = []
    stages = spec.stages()

    for stage in stages:
        names = [_tool_name(t) for t in kept]

        allowed: Optional[set] = None
        if stage.allow is not None:
            allowed = set()
            for pattern in stage.allow:
                matches = [n for n in names if fnmatchcase(n, pattern)]
                resolutions.append((pattern, matches))
                if not matches:
                    unknown.append((pattern, _suggestions_for(pattern, names)))
                allowed.update(matches)

        denied: set = set()
        if stage.deny is not None:
            for pattern in stage.deny:
                matches = [n for n in names if fnmatchcase(n, pattern)]
                resolutions.append((pattern, matches))
                if not matches:
                    unknown.append((pattern, _suggestions_for(pattern, names)))
                denied.update(matches)

        kept = [
            t
            for t in kept
            if (allowed is None or _tool_name(t) in allowed) and _tool_name(t) not in denied
        ]

    all_patterns: List[str] = []
    for stage in stages:
        all_patterns.extend(stage.allow or ())
        all_patterns.extend(stage.deny or ())

    report = FilterReport(
        mode=" > ".join(stage.mode or "" for stage in stages),
        patterns=tuple(all_patterns),
        upstream_tool_count=len(upstream_tools),
        registered_tool_count=len(kept),
        pattern_resolutions=resolutions,
        unknown_patterns=unknown,
    )
    return kept, report
