"""
Group-Based Access Control (GBAC) services.

Loads group permission files from a formation's ``groups/`` directory
and resolves a request's effective permissions from the group ids the
formation middleware attached. MUXI stores no memberships (request-
middleware PRD): groups reach the runtime exclusively via the
``middleware:`` request transformer.

Public surface:

- ``load_groups(groups_dir)`` -- parse + inheritance-resolve every group
  YAML file in a directory (fail-fast on malformed files or cycles).
- ``PermissionResolver`` -- permission resolution from middleware-
  attached group ids (LRU-cached per group combination), carrying the
  ``rbac.fallback`` group applied when a request has no groups.
- ``ResolvedPermissions`` -- the object enforcement consumes at request
  time (``is_allowed``, ``filter``, ``effective_tools``,
  ``memory_write_scopes``).
- ``GroupPermissionError`` -- raised for any malformed group definition;
  the formation loader converts it into a load failure.

Resource *filtering* lives in ``enforcement``: the overlord resolves the
request's permissions once (from the middleware-attached groups in the
request context) and stores them in a ContextVar; the enforcement
helpers filter agents, SOPs, triggers, and MCP tool surfaces at each
site, and are strict no-ops when no permissions are set (RBAC inactive).
"""

from .enforcement import (
    RbacRejectedError,
    effective_tool_registry,
    filter_agent_registry,
    filter_ids,
    get_current_permissions,
    get_request_groups,
    is_allowed,
    observe_denied,
    reset_current_permissions,
    reset_request_groups,
    resolve_request_permissions,
    set_current_permissions,
    set_request_groups,
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
    "RbacRejectedError",
    "resolve_request_permissions",
    "ResolvedGroup",
    "ResolvedPermissions",
    "SectionRules",
    "ToolRules",
    "effective_tool_registry",
    "filter_agent_registry",
    "filter_ids",
    "get_current_permissions",
    "get_request_groups",
    "is_allowed",
    "load_groups",
    "observe_denied",
    "reset_current_permissions",
    "reset_request_groups",
    "set_current_permissions",
    "set_request_groups",
]
