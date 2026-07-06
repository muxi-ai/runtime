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

Resource *filtering* (applying these permissions to agents, triggers,
SOPs, and MCP tools at request time) is Phase 3 and intentionally not
implemented here.
"""

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
    "load_groups",
]
