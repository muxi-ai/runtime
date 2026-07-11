# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        GBAC Group Loader - group YAML parsing + inheritance resolution
# Description:  Parses the simplified group definition format (2026-07-06 PRD
#               revision) from a formation's groups/ directory and resolves
#               inheritance into flat, ready-to-merge per-group permissions.
# Role:         Load-time half of GBAC Phase 2. Every parse or inheritance
#               problem raises GroupPermissionError naming the file and the
#               exact problem, so the formation loader can fail fast.
# Usage:        ``load_groups(groups_dir)`` returns ``{group_id: ResolvedGroup}``.
#               Group id is the filename stem; groups are auto-discovered
#               (no manifest declaration -- groups are policy data, not
#               architecture; see the PRD's auto-discovery rationale).
# Author:       MUXI Framework Team
#
# Format summary (see prds/group-based-access-control.md):
#   name / description        optional strings
#   inherits                  optional string or list of group ids
#   agents/triggers/sops/     plain list (= allow-list), the string "*",
#   native_apps               or long form {allow: [...], deny: [...]}
#   agents entries            strings, or single-key dicts granting the agent
#                             plus per-agent MCP tool overrides
#   mcp_servers               {mcp-id: {tools: {allow/deny}}} group-wide
#   memory                    {write: [...]} -- parsed and stored only;
#                             enforcement belongs to the memory-namespaces PRD
#
# Inheritance semantics:
#   * Parents resolve first (depth-first); unknown parents and cycles are
#     load-time errors naming the group chain.
#   * Section lists merge additively: child allow/deny are unioned onto the
#     parent's. Deny always wins at match time, so a child deny overrides a
#     parent allow (and a parent deny cannot be re-allowed by a child --
#     deny is sticky by design).
#   * Tool override blocks supersede, not merge: a child block for the same
#     (agent, server) or (server) key replaces the parent's block entirely,
#     mirroring the PRD's override-cascade semantics.
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Sections that accept the list / "*" / {allow, deny} resource grammar.
LIST_SECTIONS = ("agents", "triggers", "sops", "native_apps")

_VALID_TOP_KEYS = frozenset(
    {"name", "description", "inherits", "mcp_servers", "mcp", "memory", *LIST_SECTIONS}
)
_VALID_RULE_KEYS = frozenset({"allow", "deny"})


class GroupPermissionError(ValueError):
    """A group permission file is malformed or inheritance cannot resolve."""


@dataclass(frozen=True)
class ToolRules:
    """One ``tools: {allow: [...], deny: [...]}`` override block.

    ``None`` means the key was not specified -- the distinction matters:
    ``allow`` alone means *exactly this set*, ``deny`` alone means
    *inherited minus these*, both means allow-then-subtract.
    """

    allow: Optional[Tuple[str, ...]] = None
    deny: Optional[Tuple[str, ...]] = None


@dataclass(frozen=True)
class SectionRules:
    """Allow/deny patterns for one resource section of one group.

    ``specified`` records whether the section appeared in the file at all.
    Unspecified sections grant nothing -- except ``native_apps``, where the
    PRD defines "no section = all native Apps below operator privilege"
    (interpreted by the resolver, not here).
    """

    specified: bool = False
    allow: Tuple[str, ...] = ()
    deny: Tuple[str, ...] = ()


@dataclass
class ResolvedGroup:
    """A group definition with inheritance already applied."""

    group_id: str
    source_path: str
    name: Optional[str] = None
    description: Optional[str] = None
    inherits: Tuple[str, ...] = ()
    agents: SectionRules = field(default_factory=SectionRules)
    triggers: SectionRules = field(default_factory=SectionRules)
    sops: SectionRules = field(default_factory=SectionRules)
    native_apps: SectionRules = field(default_factory=SectionRules)
    # agent_id -> mcp_id -> ToolRules (most specific cascade level)
    agent_tool_overrides: Dict[str, Dict[str, ToolRules]] = field(default_factory=dict)
    # mcp_id -> ToolRules (group-wide cascade level)
    mcp_servers: Dict[str, ToolRules] = field(default_factory=dict)
    memory_write: Tuple[str, ...] = ()
    # Group-level watch quota override (mcp: {watch: {max_concurrent: N}});
    # None = no override (formation default applies). Governs watches ONLY.
    watch_max_concurrent: Optional[int] = None

    def section(self, kind: str) -> SectionRules:
        """Return the SectionRules for ``kind`` (one of LIST_SECTIONS)."""
        if kind not in LIST_SECTIONS:
            raise KeyError(f"Unknown permission section: {kind!r}")
        return getattr(self, kind)


def _as_pattern_list(value: Any, *, context: str, path: str) -> Tuple[str, ...]:
    """Normalize a string or list-of-strings into a tuple of patterns."""
    if isinstance(value, str):
        if not value.strip():
            raise GroupPermissionError(f"{path}: {context} must not be an empty string")
        return (value,)
    if isinstance(value, list):
        patterns: List[str] = []
        for i, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                raise GroupPermissionError(
                    f"{path}: {context} entry {i} must be a non-empty string, "
                    f"got: {type(item).__name__} = {item!r}"
                )
            patterns.append(item)
        return tuple(patterns)
    raise GroupPermissionError(
        f"{path}: {context} must be a string or a list of strings, " f"got: {type(value).__name__}"
    )


def _parse_tool_rules(block: Any, *, context: str, path: str) -> ToolRules:
    """Parse a ``tools: {allow/deny}`` dict into ToolRules."""
    if not isinstance(block, dict) or not block:
        raise GroupPermissionError(
            f"{path}: {context} must be a mapping with 'allow' and/or 'deny' keys, "
            f"got: {type(block).__name__}"
        )
    unknown = set(block) - _VALID_RULE_KEYS
    if unknown:
        raise GroupPermissionError(
            f"{path}: {context} has unknown key(s) {sorted(unknown)}; "
            "only 'allow' and 'deny' are supported"
        )
    allow = block.get("allow")
    deny = block.get("deny")
    return ToolRules(
        allow=(
            _as_pattern_list(allow, context=f"{context}.allow", path=path)
            if allow is not None
            else None
        ),
        deny=(
            _as_pattern_list(deny, context=f"{context}.deny", path=path)
            if deny is not None
            else None
        ),
    )


def _parse_server_overrides(block: Any, *, context: str, path: str) -> Dict[str, ToolRules]:
    """Parse ``{mcp-id: {tools: {allow/deny}}}`` into per-server ToolRules."""
    if not isinstance(block, dict) or not block:
        raise GroupPermissionError(
            f"{path}: {context} must be a mapping of MCP server id to a "
            f"'tools' block, got: {type(block).__name__}"
        )
    overrides: Dict[str, ToolRules] = {}
    for mcp_id, server_block in block.items():
        if not isinstance(mcp_id, str) or not mcp_id.strip():
            raise GroupPermissionError(
                f"{path}: {context} server ids must be non-empty strings, got: {mcp_id!r}"
            )
        server_context = f"{context}.{mcp_id}"
        if not isinstance(server_block, dict) or set(server_block) != {"tools"}:
            raise GroupPermissionError(
                f"{path}: {server_context} must be a mapping with exactly one "
                f"'tools' key, got: {server_block!r}"
            )
        overrides[mcp_id] = _parse_tool_rules(
            server_block["tools"], context=f"{server_context}.tools", path=path
        )
    return overrides


def _parse_agent_entry(
    entry: Any,
    *,
    index: int,
    path: str,
    allow: List[str],
    overrides: Dict[str, Dict[str, ToolRules]],
) -> None:
    """Parse one entry of an agents allow list (string or grant+override dict)."""
    if isinstance(entry, str):
        if not entry.strip():
            raise GroupPermissionError(f"{path}: agents entry {index} must not be empty")
        allow.append(entry)
        return
    if isinstance(entry, dict):
        if len(entry) != 1:
            raise GroupPermissionError(
                f"{path}: agents entry {index} must be a single-key mapping of "
                f"agent id to per-server tool overrides, got keys: {sorted(entry)}"
            )
        agent_id, override_block = next(iter(entry.items()))
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise GroupPermissionError(
                f"{path}: agents entry {index} agent id must be a non-empty string"
            )
        allow.append(agent_id)
        # ``- some-agent:`` with no body parses as {"some-agent": None};
        # treat it as a plain grant with no overrides.
        if override_block is None:
            return
        overrides[agent_id] = _parse_server_overrides(
            override_block, context=f"agents.{agent_id}", path=path
        )
        return
    raise GroupPermissionError(
        f"{path}: agents entry {index} must be a string or a single-key "
        f"mapping, got: {type(entry).__name__}"
    )


def _parse_section(
    value: Any,
    *,
    section: str,
    path: str,
    overrides: Dict[str, Dict[str, ToolRules]],
) -> SectionRules:
    """Parse one resource section: plain list, "*", or {allow, deny}."""
    context = section

    def parse_allow_entries(entries: Any, sub_context: str) -> Tuple[str, ...]:
        if isinstance(entries, str):
            entries = [entries]
        if not isinstance(entries, list):
            raise GroupPermissionError(
                f"{path}: {sub_context} must be a string or a list, "
                f"got: {type(entries).__name__}"
            )
        allow: List[str] = []
        for i, entry in enumerate(entries):
            if section == "agents":
                _parse_agent_entry(entry, index=i, path=path, allow=allow, overrides=overrides)
            elif isinstance(entry, str) and entry.strip():
                allow.append(entry)
            else:
                raise GroupPermissionError(
                    f"{path}: {sub_context} entry {i} must be a non-empty string, "
                    f"got: {type(entry).__name__} = {entry!r}"
                )
        return tuple(allow)

    # Plain string ("*" or a single pattern) and plain list are allow-lists.
    if isinstance(value, (str, list)):
        return SectionRules(specified=True, allow=parse_allow_entries(value, context))

    if isinstance(value, dict):
        if not value:
            raise GroupPermissionError(
                f"{path}: {context} must not be an empty mapping; use the long "
                "form {allow: [...], deny: [...]} with at least one key"
            )
        unknown = set(value) - _VALID_RULE_KEYS
        if unknown:
            raise GroupPermissionError(
                f"{path}: {context} has unknown key(s) {sorted(unknown)}; "
                "only 'allow' and 'deny' are supported"
            )
        allow = value.get("allow")
        deny = value.get("deny")
        return SectionRules(
            specified=True,
            allow=(parse_allow_entries(allow, f"{context}.allow") if allow is not None else ()),
            deny=(
                _as_pattern_list(deny, context=f"{context}.deny", path=path)
                if deny is not None
                else ()
            ),
        )

    raise GroupPermissionError(
        f'{path}: {context} must be a list, the string "*", or a mapping '
        f"with allow/deny keys, got: {type(value).__name__}"
    )


def _parse_group_mcp_block(block: Any, *, path: str) -> Optional[int]:
    """Parse a group's ``mcp:`` block (watch quota override only).

    Mirrors the formation's ``mcp.watch`` shape so overrides look like
    the thing they override (remote-async-tools PRD, owner ruling
    2026-07-11). Closed key sets at both levels; only
    ``watch.max_concurrent`` is supported.
    """
    if not isinstance(block, dict) or not block:
        raise GroupPermissionError(
            f"{path}: mcp must be a mapping with a 'watch' key, " f"got: {type(block).__name__}"
        )
    unknown = set(block) - {"watch"}
    if unknown:
        raise GroupPermissionError(
            f"{path}: mcp has unknown key(s) {sorted(unknown)}; only 'watch' is supported"
        )
    watch = block.get("watch")
    if not isinstance(watch, dict) or not watch:
        raise GroupPermissionError(
            f"{path}: mcp.watch must be a mapping with a 'max_concurrent' key, "
            f"got: {type(watch).__name__}"
        )
    unknown = set(watch) - {"max_concurrent"}
    if unknown:
        raise GroupPermissionError(
            f"{path}: mcp.watch has unknown key(s) {sorted(unknown)}; "
            "only 'max_concurrent' is supported in group files"
        )
    value = watch.get("max_concurrent")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GroupPermissionError(
            f"{path}: mcp.watch.max_concurrent must be an integer >= 1, got: {value!r}"
        )
    return value


def _parse_group_file(group_id: str, path: str) -> ResolvedGroup:
    """Parse one group YAML file into an (unresolved) ResolvedGroup."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as e:
        raise GroupPermissionError(f"{path}: invalid YAML: {e}") from e
    except OSError as e:
        raise GroupPermissionError(f"{path}: cannot read group file: {e}") from e

    # An empty file is a valid group that grants nothing.
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise GroupPermissionError(
            f"{path}: group file must contain a YAML mapping at the top level, "
            f"got: {type(raw).__name__}"
        )

    unknown = set(raw) - _VALID_TOP_KEYS
    if unknown:
        raise GroupPermissionError(
            f"{path}: unknown key(s) {sorted(unknown)}; supported keys are "
            f"{sorted(_VALID_TOP_KEYS)}"
        )

    name = raw.get("name")
    if name is not None and not isinstance(name, str):
        raise GroupPermissionError(f"{path}: name must be a string")
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise GroupPermissionError(f"{path}: description must be a string")

    inherits_raw = raw.get("inherits")
    inherits: Tuple[str, ...] = ()
    if inherits_raw is not None:
        inherits = _as_pattern_list(inherits_raw, context="inherits", path=path)

    group = ResolvedGroup(
        group_id=group_id,
        source_path=path,
        name=name,
        description=description,
        inherits=inherits,
    )

    overrides: Dict[str, Dict[str, ToolRules]] = {}
    for section in LIST_SECTIONS:
        if section in raw:
            rules = _parse_section(raw[section], section=section, path=path, overrides=overrides)
            setattr(group, section, rules)
    group.agent_tool_overrides = overrides

    if "mcp_servers" in raw:
        group.mcp_servers = _parse_server_overrides(
            raw["mcp_servers"], context="mcp_servers", path=path
        )

    if "mcp" in raw:
        group.watch_max_concurrent = _parse_group_mcp_block(raw["mcp"], path=path)

    if "memory" in raw:
        memory_block = raw["memory"]
        if not isinstance(memory_block, dict):
            raise GroupPermissionError(
                f"{path}: memory must be a mapping, got: {type(memory_block).__name__}"
            )
        unknown = set(memory_block) - {"write"}
        if unknown:
            raise GroupPermissionError(
                f"{path}: memory has unknown key(s) {sorted(unknown)}; " "only 'write' is supported"
            )
        if "write" in memory_block:
            group.memory_write = _as_pattern_list(
                memory_block["write"], context="memory.write", path=path
            )

    return group


def _merge_sections(base: SectionRules, overlay: SectionRules) -> SectionRules:
    """Additively overlay a child's section rules on the inherited ones."""
    if not overlay.specified:
        return base
    if not base.specified:
        return overlay

    def union(first: Tuple[str, ...], second: Tuple[str, ...]) -> Tuple[str, ...]:
        merged = list(first)
        merged.extend(p for p in second if p not in merged)
        return tuple(merged)

    return SectionRules(
        specified=True,
        allow=union(base.allow, overlay.allow),
        deny=union(base.deny, overlay.deny),
    )


def _merge_groups(base: ResolvedGroup, overlay: ResolvedGroup) -> ResolvedGroup:
    """Merge ``overlay`` (child) on top of ``base`` (resolved parents).

    Sections merge additively; tool override blocks supersede per key;
    memory write scopes union. Identity fields come from the overlay.
    """
    merged_agent_overrides: Dict[str, Dict[str, ToolRules]] = {
        agent_id: dict(server_map) for agent_id, server_map in base.agent_tool_overrides.items()
    }
    for agent_id, server_map in overlay.agent_tool_overrides.items():
        merged_agent_overrides.setdefault(agent_id, {}).update(server_map)

    memory_write = list(base.memory_write)
    memory_write.extend(s for s in overlay.memory_write if s not in memory_write)

    # Watch quota: grants are additive, so inheritance keeps the highest
    # value (same semantics as the multi-group merge at request time).
    quotas = [q for q in (base.watch_max_concurrent, overlay.watch_max_concurrent) if q]
    watch_max_concurrent = max(quotas) if quotas else None

    return ResolvedGroup(
        group_id=overlay.group_id,
        source_path=overlay.source_path,
        name=overlay.name,
        description=overlay.description,
        inherits=overlay.inherits,
        agents=_merge_sections(base.agents, overlay.agents),
        triggers=_merge_sections(base.triggers, overlay.triggers),
        sops=_merge_sections(base.sops, overlay.sops),
        native_apps=_merge_sections(base.native_apps, overlay.native_apps),
        agent_tool_overrides=merged_agent_overrides,
        mcp_servers={**base.mcp_servers, **overlay.mcp_servers},
        memory_write=tuple(memory_write),
        watch_max_concurrent=watch_max_concurrent,
    )


def _resolve_inheritance(definitions: Dict[str, ResolvedGroup]) -> Dict[str, ResolvedGroup]:
    """Resolve every group's inheritance chain (parents first, child on top)."""
    resolved: Dict[str, ResolvedGroup] = {}

    def resolve(group_id: str, chain: Tuple[str, ...]) -> ResolvedGroup:
        if group_id in resolved:
            return resolved[group_id]
        if group_id in chain:
            cycle_start = chain.index(group_id)
            cycle = " -> ".join((*chain[cycle_start:], group_id))
            raise GroupPermissionError(
                f"Circular group inheritance detected: {cycle} "
                f"(started from {definitions[group_id].source_path})"
            )

        definition = definitions[group_id]
        merged = definition
        if definition.inherits:
            # Multiple parents merge left-to-right, then the child overlays.
            base: Optional[ResolvedGroup] = None
            for parent_id in definition.inherits:
                if parent_id not in definitions:
                    raise GroupPermissionError(
                        f"{definition.source_path}: group '{group_id}' inherits "
                        f"unknown group '{parent_id}' (no groups/{parent_id}.yaml)"
                    )
                parent = resolve(parent_id, (*chain, group_id))
                base = parent if base is None else _merge_groups(base, parent)
            merged = _merge_groups(base, definition)

        resolved[group_id] = merged
        return merged

    for group_id in definitions:
        resolve(group_id, ())
    return resolved


def load_groups(groups_dir: str) -> Dict[str, ResolvedGroup]:
    """Load and resolve every group definition in ``groups_dir``.

    Files matching ``*.yaml`` / ``*.yml`` are auto-discovered; the group id
    is the filename stem. Malformed files, duplicate stems, unknown parents,
    and inheritance cycles all raise :class:`GroupPermissionError`.

    Returns:
        Mapping of group id to its inheritance-resolved definition.
    """
    definitions: Dict[str, ResolvedGroup] = {}
    for entry in sorted(os.listdir(groups_dir)):
        stem, ext = os.path.splitext(entry)
        if ext.lower() not in (".yaml", ".yml"):
            continue
        path = os.path.join(groups_dir, entry)
        if not os.path.isfile(path):
            continue
        if stem in definitions:
            raise GroupPermissionError(
                f"{path}: duplicate group id '{stem}' "
                f"(already defined by {definitions[stem].source_path})"
            )
        definitions[stem] = _parse_group_file(stem, path)

    return _resolve_inheritance(definitions)
