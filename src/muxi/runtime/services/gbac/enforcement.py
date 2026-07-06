# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        GBAC Enforcement - request-scoped permission filtering helpers
# Description:  Phase 3 of the group-based access control PRD. Holds the
#               request-scoped ResolvedPermissions (resolved once per request
#               by the overlord) and exposes the filtering helpers every
#               enforcement site consumes: agent routing, workflow
#               decomposition/execution, SOP matching, and the per-turn MCP
#               tool surface.
# Role:         The permissions travel in a ContextVar so deep call sites
#               (router, workflow executor, agent tool assembly) can consult
#               them without threading a parameter through a dozen
#               signatures. ContextVars propagate into asyncio tasks created
#               by the chat orchestrator (streaming + async paths copy the
#               context explicitly or via asyncio.create_task).
# Usage:        ``Overlord.chat()`` resolves the requesting user's
#               permissions once (Phase 2 caches make this cheap) and calls
#               ``set_current_permissions``. Every helper here is a strict
#               no-op when no permissions are set -- formations without a
#               groups/ directory see zero behavior change.
# Author:       MUXI Framework Team
#
# Mental-model compliance (PRD "The Mental Model"):
#   Filtering removes denied resources from what the LLM can see; it never
#   produces "permission denied" replies in the conversation. Hard denials
#   (403 on triggers, unknown-agent behavior on direct addressing) are
#   emitted as observability events, not surfaced as resource-revealing
#   errors to the requester.
# =============================================================================

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional, Sequence

from .. import observability
from .resolver import ResolvedPermissions

# Request-scoped permissions. None means "no enforcement" (no groups/
# directory, or a system-initiated flow with no requesting user).
_current_permissions: ContextVar[Optional[ResolvedPermissions]] = ContextVar(
    "gbac_current_permissions", default=None
)


def set_current_permissions(
    permissions: Optional[ResolvedPermissions],
) -> "Token[Optional[ResolvedPermissions]]":
    """Set the request-scoped permissions (or None to disable enforcement)."""
    return _current_permissions.set(permissions)


def get_current_permissions() -> Optional[ResolvedPermissions]:
    """The requesting user's resolved permissions, or None when inactive."""
    return _current_permissions.get()


def reset_current_permissions(token: "Token[Optional[ResolvedPermissions]]") -> None:
    """Restore the permissions saved by a previous ``set_current_permissions``."""
    _current_permissions.reset(token)


def is_allowed(kind: str, resource_id: str) -> bool:
    """True if the current request may use ``resource_id`` of type ``kind``.

    Always True when no permissions are set (enforcement inactive).
    """
    permissions = get_current_permissions()
    if permissions is None:
        return True
    return permissions.is_allowed(kind, resource_id)


def filter_ids(kind: str, resource_ids: Sequence[str]) -> List[str]:
    """Return the subset of ``resource_ids`` the current request may use.

    Emits a ``gbac.permissions.filtered`` event when filtering actually
    removed something (permission-decision observability, PRD Phase 3/4).
    """
    resource_ids = list(resource_ids)
    permissions = get_current_permissions()
    if permissions is None:
        return resource_ids
    allowed = permissions.filter(kind, resource_ids)
    if len(allowed) != len(resource_ids):
        removed = [rid for rid in resource_ids if rid not in allowed]
        observability.observe(
            event_type=observability.SystemEvents.PERMISSION_FILTERED,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "gbac_enforcement",
                "kind": kind,
                "removed": removed,
                "allowed_count": len(allowed),
                "group_ids": list(permissions.group_ids),
            },
            description=(
                f"GBAC filtered {len(removed)} {kind} for groups "
                f"{list(permissions.group_ids)}: {removed}"
            ),
        )
    return allowed


def filter_agent_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Filter an ``{agent_id: agent}`` mapping to permitted agents.

    Returns the *same* object when enforcement is inactive so callers can
    cheaply detect the no-op case (``result is registry``).
    """
    permissions = get_current_permissions()
    if permissions is None:
        return registry
    allowed = set(filter_ids("agents", list(registry.keys())))
    return {agent_id: agent for agent_id, agent in registry.items() if agent_id in allowed}


def effective_tool_registry(
    agent_id: str,
    registry: Dict[str, Dict[str, Any]],
    catalogs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Narrow an agent's per-server tool registry to the user's effective set.

    Applies the PRD tool override cascade via
    :meth:`ResolvedPermissions.effective_tools` for each attached server.

    Args:
        agent_id: The agent whose tool surface is being assembled.
        registry: ``{server_id: {tool_name: tool_info}}`` -- the agent's
            inherited tool view (post-registry, post-attachment).
        catalogs: ``{server_id: {tool_name: tool_info}}`` -- the
            post-registry catalog per server (the universe group ``allow``
            overrides expand against, letting a group supersede the
            attachment config). Defaults to ``registry``.

    Returns:
        The filtered registry. Servers whose effective tool set is empty
        are omitted entirely (``tools: {deny: "*"}`` hides the server).
        Returns ``registry`` unchanged when enforcement is inactive.
    """
    permissions = get_current_permissions()
    if permissions is None:
        return registry

    catalogs = catalogs if catalogs is not None else registry
    filtered: Dict[str, Dict[str, Any]] = {}
    removed: Dict[str, List[str]] = {}
    for server_id, tools in registry.items():
        catalog_tools = catalogs.get(server_id, tools)
        allowed = permissions.effective_tools(
            agent_id,
            server_id,
            inherited_tools=list(tools.keys()),
            catalog=list(catalog_tools.keys()),
        )
        # A group allow-override supersedes the attachment config, so the
        # effective set may include catalog tools outside the inherited
        # view -- source tool definitions from both, attachment view first.
        source = {**catalog_tools, **tools}
        kept = {name: info for name, info in source.items() if name in allowed}
        # Report only tools removed from the agent's inherited view --
        # catalog-only tools were never on this agent's surface, so their
        # absence is not a "drop" worth alerting on.
        dropped = [name for name in tools if name not in allowed]
        if kept:
            filtered[server_id] = kept
        if dropped:
            removed[server_id] = dropped

    if removed:
        observability.observe(
            event_type=observability.SystemEvents.PERMISSION_FILTERED,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "gbac_enforcement",
                "kind": "mcp_tools",
                "agent_id": agent_id,
                "removed": removed,
                "group_ids": list(permissions.group_ids),
            },
            description=(
                f"GBAC narrowed the tool surface for agent {agent_id!r}: "
                + ", ".join(f"{sid} -{len(names)}" for sid, names in removed.items())
            ),
        )
    return filtered


def observe_denied(
    kind: str, resource_id: str, permissions: Optional[Any] = None, **data: Any
) -> None:
    """Emit a permission-denial event (hard denial, e.g. 403 or direct address).

    Callers outside the chat pipeline (e.g. the trigger route) never set the
    permissions ContextVar; they pass their locally resolved ``permissions``
    explicitly so group_ids are recorded structurally rather than via a
    caller-supplied kwarg override.
    """
    permissions = permissions if permissions is not None else get_current_permissions()
    observability.observe(
        event_type=observability.ErrorEvents.AUTHORIZATION_FAILED,
        level=observability.EventLevel.WARNING,
        data={
            "service": "gbac_enforcement",
            "kind": kind,
            "resource_id": resource_id,
            "group_ids": list(permissions.group_ids) if permissions else [],
            **data,
        },
        description=f"GBAC denied {kind[:-1] if kind.endswith('s') else kind} {resource_id!r}",
    )
