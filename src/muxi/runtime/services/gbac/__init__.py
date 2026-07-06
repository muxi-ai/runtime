"""
Group-Based Access Control (GBAC) services.

Phase 2 of the group-based access control PRD: loading group permission
files from a formation's ``groups/`` directory and resolving a user's
effective permissions from their group memberships.

Public surface:

- ``load_groups(groups_dir)`` -- parse + inheritance-resolve every group
  YAML file in a directory (fail-fast on malformed files or cycles).
- ``PermissionResolver`` -- membership lookup (TTL-cached) plus
  permission resolution (LRU-cached per group combination).
- ``ResolvedPermissions`` -- the object Phase 3 consumes at request time
  (``is_allowed``, ``filter``, ``effective_tools``, ``memory_write_scopes``).
- ``GroupPermissionError`` -- raised for any malformed group definition;
  the formation loader converts it into a load failure.

Resource *filtering* (Phase 3) lives in ``enforcement``: the overlord
resolves the requesting user's permissions once per request and stores
them in a ContextVar; the enforcement helpers filter agents, SOPs,
triggers, and MCP tool surfaces at each site, and are strict no-ops when
no permissions are set (formations without a ``groups/`` directory).
"""

from .enforcement import (
    effective_tool_registry,
    filter_agent_registry,
    filter_ids,
    get_current_permissions,
    is_allowed,
    observe_denied,
    reset_current_permissions,
    set_current_permissions,
)
from .loader import (
    GroupPermissionError,
    ResolvedGroup,
    SectionRules,
    ToolRules,
    load_groups,
)
from .resolver import PermissionResolver, ResolvedPermissions

__all__ = [
    "GroupPermissionError",
    "PermissionResolver",
    "ResolvedGroup",
    "ResolvedPermissions",
    "SectionRules",
    "ToolRules",
    "effective_tool_registry",
    "filter_agent_registry",
    "filter_ids",
    "get_current_permissions",
    "is_allowed",
    "load_groups",
    "observe_denied",
    "reset_current_permissions",
    "set_current_permissions",
]
