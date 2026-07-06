# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        GBAC Permission Resolver - membership lookup + resolution engine
# Description:  Resolves a user's effective permissions from their group
#               memberships (user_groups table) and the formation's loaded
#               group definitions. Request-time half of GBAC Phase 2.
# Role:         Exposes the API Phase 3 (resource filtering) consumes:
#               ``PermissionResolver.resolve(user_id) -> ResolvedPermissions``
#               with ``is_allowed`` / ``filter`` / ``effective_tools`` /
#               ``memory_write_scopes``. Nothing here enforces anything --
#               enforcement is Phase 3.
# Usage:        Constructed by Formation._setup_groups() when a groups/
#               directory is present. Membership rows are read by external
#               user identifier + formation_id (per GBAC Phase 1's design)
#               with a TTL cache (default 60s); resolution per group
#               combination is cached in a small LRU.
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

import time
from collections import OrderedDict
from fnmatch import fnmatchcase
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .. import observability
from .loader import LIST_SECTIONS, ResolvedGroup, ToolRules

# Defaults from the PRD's performance section.
DEFAULT_MEMBERSHIP_TTL_SECONDS = 60.0
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
    """Resolves users to effective permissions from group memberships.

    Membership rows are read from the ``user_groups`` table by external
    user identifier + formation id, cached with a TTL (default 60s).
    Permission resolution per group combination is cached in an LRU.
    """

    def __init__(
        self,
        groups: Dict[str, ResolvedGroup],
        formation_id: str,
        db_manager_getter: Callable[[], Optional[object]],
        membership_ttl: float = DEFAULT_MEMBERSHIP_TTL_SECONDS,
        resolution_cache_size: int = DEFAULT_RESOLUTION_CACHE_SIZE,
    ):
        """
        Args:
            groups: Inheritance-resolved group definitions from
                :func:`muxi.runtime.services.gbac.loader.load_groups`.
            formation_id: Formation id for multi-formation isolation.
            db_manager_getter: Callable returning the formation's database
                manager (or None before memory initialization). Deferred so
                the resolver can be constructed during config preparation.
            membership_ttl: Seconds a user's membership lookup stays cached.
            resolution_cache_size: Max cached group combinations (LRU).
        """
        self._groups = groups
        self._formation_id = formation_id
        self._db_manager_getter = db_manager_getter
        self._membership_ttl = membership_ttl
        self._membership_cache: Dict[str, Tuple[float, Tuple[str, ...]]] = {}
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

    async def resolve(self, user_id: str) -> ResolvedPermissions:
        """Resolve ``user_id`` (external identifier) to effective permissions.

        A user with no memberships resolves to empty permissions
        ("registered but inactive"). Membership rows referencing group ids
        without a matching group file grant nothing and are reported once
        per group id via observability.

        Raises:
            Exception: Database errors propagate after a resolution-failure
                event is emitted -- the caller (Phase 3) decides how to fail.
        """
        try:
            member_group_ids = await self._get_memberships(user_id)
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.PROCESSING_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "gbac_permission_resolver",
                    "operation": "membership_lookup",
                    "user_id": user_id,
                    "formation_id": self._formation_id,
                    "error": str(e),
                },
                description=f"GBAC permission resolution failed for user {user_id!r}: {e}",
            )
            raise

        known = tuple(sorted(g for g in member_group_ids if g in self._groups))
        unknown = sorted(set(member_group_ids) - set(known))
        for group_id in unknown:
            if group_id in self._warned_unknown_groups:
                continue
            self._warned_unknown_groups.add(group_id)
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "service": "gbac_permission_resolver",
                    "operation": "membership_resolution",
                    "group_id": group_id,
                    "formation_id": self._formation_id,
                },
                description=(
                    f"user_groups references group {group_id!r} but no "
                    f"groups/{group_id}.yaml exists; membership grants nothing"
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

    async def _get_memberships(self, user_id: str) -> Tuple[str, ...]:
        """Read the user's group ids from user_groups, with TTL caching."""
        now = time.monotonic()
        cached = self._membership_cache.get(user_id)
        if cached is not None and now - cached[0] < self._membership_ttl:
            return cached[1]

        db_manager = self._db_manager_getter()
        if db_manager is None:
            raise RuntimeError(
                "Group permissions are configured but no persistent database "
                "is available for membership lookup"
            )

        from sqlalchemy import select

        from ..memory.long_term import UserGroup

        async with db_manager.get_async_session() as session:
            result = await session.execute(
                select(UserGroup.group_id).where(
                    UserGroup.user_id == user_id,
                    UserGroup.formation_id == self._formation_id,
                )
            )
            group_ids = tuple(row[0] for row in result.all())

        self._membership_cache[user_id] = (now, group_ids)
        return group_ids

    def invalidate_memberships(self, user_id: Optional[str] = None) -> None:
        """Drop cached memberships for one user (or all users)."""
        if user_id is None:
            self._membership_cache.clear()
        else:
            self._membership_cache.pop(user_id, None)
