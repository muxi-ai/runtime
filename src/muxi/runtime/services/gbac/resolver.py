# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        GBAC Permission Resolver - group-combination resolution engine
# Description:  Resolves a request's effective permissions from the group ids
#               the formation middleware attached and the formation's loaded
#               group definitions. MUXI stores no memberships (request-
#               middleware PRD): groups reach the runtime exclusively via the
#               ``middleware:`` request transformer.
# Role:         Exposes the API enforcement (resource filtering) consumes:
#               ``PermissionResolver.resolve_groups(group_ids)`` returns
#               ``ResolvedPermissions`` with ``is_allowed`` / ``filter`` /
#               ``effective_tools`` / ``memory_write_scopes``. Nothing here
#               enforces anything -- enforcement lives in enforcement.py.
# Usage:        Constructed by Formation._setup_rbac() when RBAC is active.
#               Group ids arrive per request from the middleware (via the
#               request context); resolution per group combination is cached
#               in a small LRU. ``fallback_group`` (rbac.fallback) applies
#               when a request carries no groups -- never to middleware
#               errors, which reject fail-closed upstream.
# Author:       MUXI Framework Team
#
# Resolution semantics (PRD "Permission Resolution Rules"):
#   * Union of allows across the user's groups; any group's deny wins.
#   * fnmatchcase globs in all pattern lists (same semantics as the MCP
#     registry tool filter in services/mcp/tool_filter.py).
#   * native_apps unspecified in a group = that group allows all native
#     Apps (privilege gating of operator+ Apps is a Phase 3 concern).
#   * No memberships = empty permissions ("registered but inactive").
#
# Tool override cascade (PRD "Tool Override Cascade"):
#   group agent-scoped override > group server-wide override > inherited
#   (agent attachment / registry) config. Within a block: allow alone =
#   exactly that set (supersede, not intersect); deny alone = inherited
#   minus denied; both = allow-then-subtract. Per-group effective sets are
#   computed first, then merged across groups (union; any group's deny wins).
#   Only groups that grant the agent participate in the merge -- the PRD
#   scopes server-wide overrides to "every granted agent".
# =============================================================================

from __future__ import annotations

from collections import OrderedDict
from fnmatch import fnmatchcase
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .. import observability
from .loader import LIST_SECTIONS, ResolvedGroup, ToolRules

# Default from the PRD's performance section.
DEFAULT_RESOLUTION_CACHE_SIZE = 512


def _matches(name: str, patterns: Iterable[str]) -> bool:
    """True if ``name`` matches any fnmatch glob in ``patterns``."""
    return any(fnmatchcase(name, pattern) for pattern in patterns)


class ResolvedPermissions:
    """Effective permissions for one combination of groups.

    Instances are user-agnostic (cached per group combination) and expose
    the read API Phase 3 consumes at request time.
    """

    def __init__(self, group_ids: Tuple[str, ...], groups: Tuple[ResolvedGroup, ...]):
        self._group_ids = group_ids
        self._groups = groups

    @property
    def group_ids(self) -> Tuple[str, ...]:
        """The (sorted) group ids this resolution was computed from."""
        return self._group_ids

    @property
    def has_groups(self) -> bool:
        """False for the "registered but inactive" empty-membership state."""
        return bool(self._groups)

    @property
    def memory_write_scopes(self) -> Tuple[str, ...]:
        """Union of ``memory.write`` scopes across groups (parsed, not enforced)."""
        scopes: List[str] = []
        for group in self._groups:
            scopes.extend(s for s in group.memory_write if s not in scopes)
        return tuple(scopes)

    def is_allowed(self, kind: str, resource_id: str) -> bool:
        """True if the user's groups grant ``resource_id`` of type ``kind``.

        ``kind`` is one of ``agents`` / ``triggers`` / ``sops`` /
        ``native_apps``. Union of allows across groups; any group's deny
        wins. With no group memberships everything is denied.
        """
        if kind not in LIST_SECTIONS:
            raise KeyError(f"Unknown permission kind: {kind!r}; expected one of {LIST_SECTIONS}")
        allowed = False
        for group in self._groups:
            rules = group.section(kind)
            if _matches(resource_id, rules.deny):
                return False
            if kind == "native_apps" and not rules.specified:
                # PRD: groups with no native_apps section allow all native
                # Apps (operator+ privilege gating happens in Phase 3).
                allowed = True
            elif _matches(resource_id, rules.allow):
                allowed = True
        return allowed

    def filter(self, kind: str, resource_ids: Sequence[str]) -> List[str]:
        """Return the subset of ``resource_ids`` allowed for ``kind``, in order."""
        return [rid for rid in resource_ids if self.is_allowed(kind, rid)]

    def effective_tools(
        self,
        agent_id: str,
        mcp_id: str,
        inherited_tools: Sequence[str],
        catalog: Optional[Sequence[str]] = None,
    ) -> Set[str]:
        """Compute the user's effective tool set for one agent+server attachment.

        Args:
            agent_id: The granted agent whose attachment is being resolved.
            mcp_id: The MCP server id of the attachment.
            inherited_tools: The tool names the agent would see with no group
                override (registry catalog already narrowed by the agent
                attachment's own ``tools:`` block).
            catalog: The post-registry tool catalog for the server -- the
                universe ``allow`` globs expand against, letting a group
                override supersede (not intersect) the attachment config.
                Defaults to ``inherited_tools``.

        Returns:
            The effective tool names. Empty when no group grants the agent
            (or the user has no groups), and when overrides hide the server
            (``tools: {deny: "*"}``).
        """
        # Deny-wins must hold here independently of callers: if ANY group
        # denies the agent, the user cannot reach it, so its tool surface
        # is empty regardless of what other groups would grant.
        if not self.is_allowed("agents", agent_id):
            return set()

        universe = tuple(catalog) if catalog is not None else tuple(inherited_tools)
        union: Set[str] = set()
        deny_patterns: List[str] = []
        for group in self._groups:
            # Only groups that grant the agent participate: the PRD scopes
            # group overrides to "every granted agent" on that server.
            rules = group.section("agents")
            if not _matches(agent_id, rules.allow):
                continue
            block = self._override_for(group, agent_id, mcp_id)
            if block is None:
                union.update(inherited_tools)
                continue
            if block.allow is not None:
                effective = {t for t in universe if _matches(t, block.allow)}
            else:
                effective = set(inherited_tools)
            if block.deny is not None:
                effective = {t for t in effective if not _matches(t, block.deny)}
                deny_patterns.extend(block.deny)
            union.update(effective)

        # Cross-group deny sweep: "any group's deny wins" applies to the
        # merged union, so an explicit deny in one group also strips tools
        # contributed by groups that had no override block at all. This
        # asymmetry is intentional -- deny is global, allow is per-group.
        if deny_patterns:
            union = {t for t in union if not _matches(t, deny_patterns)}
        return union

    @staticmethod
    def _override_for(group: ResolvedGroup, agent_id: str, mcp_id: str) -> Optional[ToolRules]:
        """Pick the group's most specific override block for agent+server."""
        agent_scoped = group.agent_tool_overrides.get(agent_id, {}).get(mcp_id)
        if agent_scoped is not None:
            return agent_scoped
        return group.mcp_servers.get(mcp_id)


class PermissionResolver:
    """Resolves middleware-attached group ids to effective permissions.

    MUXI stores no memberships: group ids arrive per request from the
    formation middleware (the only way groups enter the pipeline).
    Permission resolution per group combination is cached in an LRU --
    this caches pure YAML-derived computation, never middleware answers.
    """

    def __init__(
        self,
        groups: Dict[str, ResolvedGroup],
        formation_id: str,
        fallback_group: Optional[str] = None,
        resolution_cache_size: int = DEFAULT_RESOLUTION_CACHE_SIZE,
    ):
        """
        Args:
            groups: Inheritance-resolved group definitions from
                :func:`muxi.runtime.services.gbac.loader.load_groups`.
            formation_id: Formation id for multi-formation isolation.
            fallback_group: The ``rbac.fallback`` group applied when a
                request carries no groups, or None (``fallback: false``:
                such requests are rejected). Validated against ``groups``
                at formation load.
            resolution_cache_size: Max cached group combinations (LRU).
        """
        self._groups = groups
        self._formation_id = formation_id
        self._fallback_group = fallback_group
        self._resolution_cache: "OrderedDict[Tuple[str, ...], ResolvedPermissions]" = OrderedDict()
        self._resolution_cache_size = resolution_cache_size
        self._warned_unknown_groups: Set[str] = set()

    @property
    def group_count(self) -> int:
        """Number of loaded group definitions."""
        return len(self._groups)

    @property
    def group_ids(self) -> Tuple[str, ...]:
        """All loaded group ids, sorted."""
        return tuple(sorted(self._groups))

    @property
    def fallback_group(self) -> Optional[str]:
        """The ``rbac.fallback`` group name, or None (reject on no groups)."""
        return self._fallback_group

    def resolve_request(self, group_ids: Optional[Sequence[str]]) -> Optional[ResolvedPermissions]:
        """Resolve a request's groups to permissions, applying ``rbac.fallback``.

        Args:
            group_ids: The middleware-attached groups; None or empty when
                the request ended up with no groups (no middleware
                declared, or the middleware cleanly answered "none").

        Returns:
            ResolvedPermissions, or None when the request must be
            rejected (no groups and ``fallback: false``). The caller
            emits the rejection event -- it has the request context.
        """
        effective = tuple(group_ids) if group_ids else ()
        if not effective:
            if self._fallback_group is None:
                return None
            effective = (self._fallback_group,)
        return self.resolve_groups(effective)

    def resolve_groups(self, group_ids: Sequence[str]) -> ResolvedPermissions:
        """Resolve a set of middleware-attached group ids to permissions.

        An empty sequence resolves to empty permissions (nothing granted).
        Group ids without a matching group file grant nothing and are
        reported once per group id via observability.
        """
        known = tuple(sorted({g for g in group_ids if g in self._groups}))
        unknown = sorted(set(group_ids) - set(known))
        for group_id in unknown:
            if group_id in self._warned_unknown_groups:
                continue
            self._warned_unknown_groups.add(group_id)
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "service": "gbac_permission_resolver",
                    "operation": "group_resolution",
                    "group_id": group_id,
                    "formation_id": self._formation_id,
                },
                description=(
                    f"middleware attached group {group_id!r} but no "
                    f"groups/{group_id}.yaml exists; the group grants nothing"
                ),
            )

        return self._resolve_combination(known)

    def _resolve_combination(self, group_ids: Tuple[str, ...]) -> ResolvedPermissions:
        """Return the (LRU-cached) resolution for a sorted group combination."""
        cached = self._resolution_cache.get(group_ids)
        if cached is not None:
            self._resolution_cache.move_to_end(group_ids)
            return cached

        permissions = ResolvedPermissions(
            group_ids=group_ids,
            groups=tuple(self._groups[gid] for gid in group_ids),
        )
        self._resolution_cache[group_ids] = permissions
        if len(self._resolution_cache) > self._resolution_cache_size:
            self._resolution_cache.popitem(last=False)
        return permissions
