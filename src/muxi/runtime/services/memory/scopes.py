# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Scopes - Shared-Scope Helpers (Namespaces Phases 2+3)
# Description:  Write-grant matching and read fan-out composition for the
#               formation / group / user memory scope hierarchy
# Role:         Single home for the scope rules shared by the memory backends
#               (long_term.py, sqlite.py), the client memory routes, and the
#               event substrate
# Usage:        Backends call resolve_read_group_ids() to compose the read
#               fan-out; write surfaces call is_write_scope_allowed() before
#               performing a shared-scope write
# Author:       MUXI Framework Team
#
# Scope model (memory-namespaces PRD, "The Scope Model"):
#
#   formation            the org boundary; visible to every user
#    └── group           the SHARING unit -- membership via GBAC user_groups
#         └── user       memobase isolation (unchanged)
#
# Write-one-read-up: a memory is written to exactly one scope; retrieval for
# a user fans out user -> each group the user belongs to -> formation and
# merges by score. Visibility IS the ancestor chain -- the read fan-out only
# ever includes scopes the requesting user belongs to, so there is no
# post-hoc filtering and no per-memory ACL.
#
# Write grants (PRD "Interaction with Group-Based Access Control"): writing
# a shared scope requires a ``memory.write`` grant in the writer's group
# YAML. Grant syntax matches what the GBAC loader parses:
#
#   memory:
#     write:
#       - group:hr          # may write hr-shared memories
#       - formation         # may write formation-wide memories
#       - group:*           # fnmatch globs work like every other GBAC list
#
# Conflict weighting (PRD "Read Semantics"): more-specific scope wins by
# default -- a user fact outranks a group fact outranks a formation fact.
# SCOPE_WEIGHTS implements this as a multiplicative similarity weight with
# user pinned at 1.0 so user-scope scores are byte-identical to Phase 1.
#
# Membership resolution for the read fan-out:
#   1. The per-request ResolvedPermissions in the GBAC ContextVar (set once
#      per request by the overlord's permission gate) -- the normal path.
#   2. Fallback: the formation's PermissionResolver, registered here by
#      Formation._setup_groups(), looked up by external user id. Covers
#      API routes and direct service calls that never set the ContextVar.
#   3. No resolver / no memberships -> no group scopes; the fan-out is
#      user + formation only.
# =============================================================================

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Dict, List, Optional, Sequence, Tuple

from .base import SCOPE_TYPE_FORMATION, SCOPE_TYPE_GROUP, SCOPE_TYPE_USER

# All valid scope types, in most-specific-first order.
SCOPE_TYPES = (SCOPE_TYPE_USER, SCOPE_TYPE_GROUP, SCOPE_TYPE_FORMATION)

# Specificity-wins conflict weighting (PRD "Read Semantics"): similarity
# scores are multiplied by the row's scope weight before the merged sort,
# so on (near-)equal relevance the more specific scope ranks first. User
# weight is pinned at 1.0 so user-scope results are numerically identical
# to the pre-fan-out scores.
SCOPE_WEIGHTS: Dict[str, float] = {
    SCOPE_TYPE_USER: 1.0,
    SCOPE_TYPE_GROUP: 0.95,
    SCOPE_TYPE_FORMATION: 0.9,
}

# Formation-id -> PermissionResolver used as the read fan-out membership
# fallback when no per-request permissions are in the ContextVar. Keyed by
# formation id so multi-formation processes cannot cross wires; re-loading
# a formation simply overwrites its entry.
_membership_resolvers: Dict[str, object] = {}


def validate_scope(scope_type: str, scope_id: Optional[str]) -> None:
    """Validate a (scope_type, scope_id) write target.

    Raises:
        ValueError: On an unknown scope type, or a group scope without a
            group id.
    """
    if scope_type not in SCOPE_TYPES:
        raise ValueError(
            f"Unknown memory scope type: {scope_type!r}; expected one of {SCOPE_TYPES}"
        )
    if scope_type == SCOPE_TYPE_GROUP and not scope_id:
        raise ValueError("Group-scope memories require a scope_id (the group id)")


def write_scope_target(scope_type: str, scope_id: Optional[str] = None) -> str:
    """Return the grant string a shared-scope write is matched against.

    Mirrors the ``memory.write`` grant syntax the GBAC loader parses:
    ``"formation"`` for formation scope, ``"group:{id}"`` for group scope.
    """
    if scope_type == SCOPE_TYPE_FORMATION:
        return SCOPE_TYPE_FORMATION
    if scope_type == SCOPE_TYPE_GROUP:
        return f"{SCOPE_TYPE_GROUP}:{scope_id}"
    raise ValueError(f"No write grant exists for scope type {scope_type!r}")


def is_write_scope_allowed(permissions, scope_type: str, scope_id: Optional[str] = None) -> bool:
    """True if ``permissions`` grants writing to the given shared scope.

    ``permissions`` is a ResolvedPermissions (or None). The target is
    matched against the union of ``memory.write`` grants across the user's
    groups with the same fnmatchcase glob semantics as every other GBAC
    pattern list (``group:*`` grants all groups). With no permissions --
    no groups configured, or an unresolved user -- every shared write is
    denied: system principals map to explicit grants, never an implicit
    bypass (PRD).
    """
    if scope_type == SCOPE_TYPE_USER:
        return True  # user scope is never gated
    validate_scope(scope_type, scope_id)
    if permissions is None:
        return False
    target = write_scope_target(scope_type, scope_id)
    return any(fnmatchcase(target, pattern) for pattern in permissions.memory_write_scopes)


def normalize_read_scopes(scopes: Optional[Sequence[str]]) -> Tuple[str, ...]:
    """Normalize a per-query ``scopes`` narrowing list.

    ``None`` means the full implicit cascade (user + group + formation --
    PRD "Read Semantics"). Privacy-sensitive callers narrow explicitly,
    e.g. ``scopes=["user"]`` restores the exact Phase 1 user-only query.

    Raises:
        ValueError: On an unknown scope type or an empty list.
    """
    if scopes is None:
        return SCOPE_TYPES
    normalized: List[str] = []
    for scope in scopes:
        if scope not in SCOPE_TYPES:
            raise ValueError(f"Unknown memory scope: {scope!r}; expected a subset of {SCOPE_TYPES}")
        if scope not in normalized:
            normalized.append(scope)
    if not normalized:
        raise ValueError("scopes must not be empty; omit it for the full cascade")
    return tuple(normalized)


def current_group_ids() -> Tuple[str, ...]:
    """The requesting user's group ids from the per-request ContextVar.

    Returns () when no permissions are set (no groups configured, or a
    system-initiated flow with no requesting user). Imported lazily to
    keep the memory package import-light.
    """
    from ..gbac import enforcement as gbac_enforcement

    permissions = gbac_enforcement.get_current_permissions()
    if permissions is None:
        return ()
    return permissions.group_ids


def register_group_membership_resolver(formation_id: str, resolver) -> None:
    """Register a formation's PermissionResolver as the fan-out fallback.

    Called by ``Formation._setup_groups()``. ``None`` unregisters.
    """
    if resolver is None:
        _membership_resolvers.pop(formation_id, None)
    else:
        _membership_resolvers[formation_id] = resolver


async def resolve_read_group_ids(
    formation_id: str,
    external_user_id: Optional[str] = None,
    group_ids: Optional[Sequence[str]] = None,
) -> Tuple[str, ...]:
    """Compose the group ids for a user-context read fan-out.

    Resolution order: an explicit ``group_ids`` argument (callers that
    resolved permissions themselves) -> the per-request ContextVar ->
    the registered PermissionResolver looked up by external user id ->
    (). Failures in the fallback resolver degrade to no group scopes
    (the fan-out is then user + formation only) -- retrieval must never
    hard-fail because a membership lookup did.
    """
    if group_ids is not None:
        return tuple(group_ids)

    from_context = current_group_ids()
    if from_context:
        return from_context

    resolver = _membership_resolvers.get(formation_id)
    if resolver is None or not external_user_id:
        return ()
    try:
        permissions = await resolver.resolve(str(external_user_id).lower().strip())
        return permissions.group_ids
    except Exception:
        return ()
