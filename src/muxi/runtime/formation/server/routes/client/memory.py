"""
User memory management endpoints.

These endpoints provide memory CRUD operations for users.
Buffer endpoints support both ClientKey and AdminKey:
- ClientKey: X-Muxi-User-ID required (user's buffer only)
- AdminKey: X-Muxi-User-ID optional (omit for all, provide to filter)
"""

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .....datatypes.api import APIEventType, APIObjectType
from .....services.memory.base import SCOPE_TYPE_GROUP, SCOPE_TYPE_USER
from .....services.memory.ingest import (
    STATUS_ACCEPTED,
    STATUS_DUPLICATE,
    STATUS_INVALID,
    IngestionBusyError,
    IngestionUnavailableError,
    validate_item,
)
from .....services.memory.scopes import (
    SCOPE_TYPES,
    is_write_scope_allowed,
    write_scope_target,
)
from .....utils.fastjson import json
from ....background.request_tracker import RequestStatus
from ...responses import (
    APIResponse,
    create_error_response,
    create_success_response,
    memory_list_response,
)

router = APIRouter(tags=["Memory"])

# Collection shared-scope rows are written to. Collections are a
# user-space organization scheme; shared rows are addressed by scope on
# the read side, so this is provenance bookkeeping ("context" is the
# catch-all in MEMORY_COLLECTIONS), not a retrieval filter.
SHARED_SCOPE_COLLECTION = "context"


class MemoryCreate(BaseModel):
    """Model for creating a memory.

    Accepts the SDK/spec format: { type, detail } and/or the flat format: { content }.

    Memory namespaces (Phases 2+3): ``scope`` selects the namespace the
    memory is written to -- ``user`` (default, ungated), ``group``
    (requires ``scope_id`` = the group id), or ``formation``. Shared
    scopes require a ``memory.write`` grant in the caller's group YAML;
    without one the request is rejected with 403.

    Memory ingestion (Phase 3a): providing ``source`` switches the
    request onto the ingestion contract -- the item is validated,
    appended to the event log under the (source, source_id) idempotency
    key, and processed asynchronously (classify -> filter -> extract ->
    embed -> link -> store). The response returns fast with a
    ``processing_id`` pollable at GET /v1/memories/ingestion/{id}.
    ``content`` may be structured (an object) on the ingestion path.
    """

    content: Optional[Any] = None
    type: Optional[str] = None
    detail: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None
    scope_id: Optional[str] = None
    # Ingestion contract fields (Memory Ingestion Phase 3a)
    source: Optional[str] = None
    source_id: Optional[str] = None
    timestamp: Optional[str] = None
    subject: Optional[str] = None

    def get_content_string(self) -> str:
        """Build the content string for storage.

        SDK format: { type: "preference", detail: "Prefers Python" }
        Flat format: { content: "User prefers Python" }
        """
        if self.content is not None and not isinstance(self.content, str):
            raise ValueError(
                "Structured 'content' requires the ingestion contract; "
                "include 'source' to route through POST /v1/memories ingestion"
            )
        if self.content:
            return self.content
        if self.detail:
            return self.detail
        raise ValueError("Either 'content' or 'detail' must be provided")

    def get_metadata(self) -> Dict[str, Any]:
        meta = self.metadata or {}
        if self.type and "type" not in meta:
            meta["type"] = self.type
        return meta


def _get_user_id(
    x_user_id: Optional[str], request_id: Optional[str]
) -> tuple[Optional[str], Optional[JSONResponse]]:
    """Extract and validate user_id from X-Muxi-User-ID header."""
    if not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=400)
    return x_user_id, None


def _check_auth_and_user_id(
    request: Request,
    x_user_id: Optional[str],
    request_id: Optional[str],
) -> Tuple[Optional[str], bool, Optional[JSONResponse]]:
    """
    Check authentication type and validate user_id requirement for buffer ops.

    Returns:
        Tuple of (user_id, is_admin, error_response)
    """
    formation = request.app.state.formation

    # Get keys from formation._api_keys (where they're actually stored)
    api_keys = getattr(formation, "_api_keys", {})
    admin_key = api_keys.get("admin", "")
    client_key = api_keys.get("client", "")

    provided_admin_key = request.headers.get("x-muxi-admin-key")
    provided_client_key = request.headers.get("x-muxi-client-key")

    is_admin = False
    if provided_admin_key and admin_key and secrets.compare_digest(provided_admin_key, admin_key):
        is_admin = True
    elif (
        provided_client_key
        and client_key
        and secrets.compare_digest(provided_client_key, client_key)
    ):
        is_admin = False
    else:
        response = create_error_response(
            "UNAUTHORIZED",
            "Valid API key required",
            None,
            request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=401)

    if not is_admin and not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required when using client API key",
            None,
            request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=400)

    return x_user_id, is_admin, None


async def _run_request_pipeline(
    formation,
    user_id: str,
    request_id: Optional[str],
    endpoint: str,
) -> Tuple[str, Optional[object], Optional[JSONResponse]]:
    """Run the request middleware + RBAC pipeline for a memory endpoint.

    Memory routes are authenticated inbound traffic, so they traverse the
    same pipeline as chat (request-middleware PRD): the middleware may
    attach groups (the only membership source) and rewrite the identity;
    RBAC then resolves permissions (applying ``rbac.fallback``) or
    rejects. The resolved permissions are stored in the request context
    so the shared-scope read fan-out (``resolve_read_group_ids``) sees
    the caller's groups.

    Returns:
        ``(user_id, permissions, error_response)`` -- the (possibly
        rewritten) identity, the resolved permissions (None when RBAC is
        inactive), and a formatted error response on rejection.
    """
    from .....services import middleware as middleware_service
    from .....services.gbac import enforcement as gbac_enforcement

    user_id = str(user_id).lower().strip()
    groups = None
    request_middleware = getattr(formation, "request_middleware", None)
    if request_middleware is not None:
        payload = middleware_service.build_request_payload(
            user_id=user_id,
            message="",
            metadata={"endpoint": endpoint},
            route_class="api",
        )
        try:
            transformed, groups = await request_middleware.transform(payload, request_id=request_id)
        except middleware_service.MiddlewareRejectedError:
            # Fail closed; the error.middleware.failed event was emitted.
            response = create_error_response(
                "FORBIDDEN",
                "Request rejected by the formation middleware",
                None,
                request_id,
            )
            return user_id, None, JSONResponse(content=response.model_dump(), status_code=403)
        user_id = str(transformed["user_id"]).lower().strip()
    gbac_enforcement.set_request_groups(groups if request_middleware is not None else None)

    permissions = None
    resolver = getattr(formation, "permission_resolver", None)
    if resolver is not None:
        try:
            permissions = gbac_enforcement.resolve_request_permissions(
                resolver,
                groups,
                user_id=user_id,
                formation_id=formation.formation_id,
                route_class="api",
            )
        except gbac_enforcement.RbacRejectedError:
            response = create_error_response(
                "FORBIDDEN",
                "Insufficient permissions to access this resource",
                None,
                request_id,
            )
            return user_id, None, JSONResponse(content=response.model_dump(), status_code=403)
        # Make the caller's groups visible to the shared-scope read
        # fan-out for the remainder of this request context.
        gbac_enforcement.set_current_permissions(permissions)

    return user_id, permissions, None


async def _resolve_write_scope(
    formation,
    user_id: str,
    memory: MemoryCreate,
    request_id: Optional[str],
    permissions=None,
) -> Tuple[Optional[Tuple[str, str]], Optional[JSONResponse]]:
    """Validate and authorize the requested memory write scope.

    Returns ``(scope, error_response)``: scope is None for user-scope
    writes (today's ungated path, byte-identical to Phase 1) and a
    ``(scope_type, scope_id)`` tuple for authorized shared-scope writes.

    ``permissions`` is the caller's ResolvedPermissions from the request
    pipeline (``_run_request_pipeline``), or None when RBAC is inactive.

    Shared scopes (memory namespaces PRD, "Interaction with GBAC"):
    writing group or formation scope requires a ``memory.write`` grant in
    the caller's group YAML, matched with the same glob semantics as
    every other GBAC list (``group:hr``, ``formation``, ``group:*``).
    Denials mirror the GBAC trigger route: an AUTHORIZATION_FAILED
    observability event plus a generic 403.
    """
    scope_type = (memory.scope or SCOPE_TYPE_USER).strip().lower()
    if scope_type not in SCOPE_TYPES:
        response = create_error_response(
            "INVALID_PARAMS",
            f"Invalid scope '{memory.scope}'; expected one of {list(SCOPE_TYPES)}",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=422)

    if scope_type == SCOPE_TYPE_USER:
        return None, None

    if scope_type == SCOPE_TYPE_GROUP and not (memory.scope_id or "").strip():
        response = create_error_response(
            "INVALID_PARAMS",
            "scope_id (the group id) is required when scope is 'group'",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=422)

    scope_id = memory.scope_id.strip() if scope_type == SCOPE_TYPE_GROUP else formation.formation_id

    resolver = getattr(formation, "permission_resolver", None)

    if not is_write_scope_allowed(permissions, scope_type, scope_id):
        from .....services.gbac import enforcement as gbac_enforcement

        gbac_enforcement.observe_denied(
            "memory_scopes",
            write_scope_target(scope_type, scope_id),
            permissions=permissions,
            user_id=user_id,
            formation_id=formation.formation_id,
            channel="api",
        )
        response = create_error_response(
            "FORBIDDEN",
            "Insufficient permissions to write to this memory scope",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=403)

    if scope_type == SCOPE_TYPE_GROUP and scope_id not in resolver.group_ids:
        # A glob grant (group:*) can match groups that don't exist; a
        # write there would be visible to nobody. Reject explicitly.
        response = create_error_response(
            "INVALID_PARAMS",
            f"Unknown group '{scope_id}'",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=422)

    return (scope_type, scope_id), None


async def _write_shared_memory(
    overlord,
    user_id: str,
    content_str: str,
    metadata: Dict[str, Any],
    scope: Tuple[str, str],
    request_id: Optional[str],
) -> Tuple[Optional[str], Optional[JSONResponse]]:
    """Perform an authorized shared-scope write through the event substrate.

    Shared facts must be replayable by construction: the fact.extracted
    event (carrying the true scope) is appended FIRST, and the projection
    row is only written once the append succeeded. Without the event, a
    shared row would carry no ``derived_from_event_id`` provenance --
    ``FlatFactProjector.reset`` would never wipe it and no replay would
    recreate it, so it would silently survive (and duplicate across)
    every wipe-and-rebuild. If the substrate is unavailable or the
    append fails, the write is rejected with 503 and no row is written.

    Returns ``(memory_id, error_response)``.
    """
    from .....services.memory.events.models import EVENT_FACT_EXTRACTED, SOURCE_USER_EDIT
    from .....services.memory.events.projectors import apply_fact_event

    meta = dict(metadata)
    meta.setdefault("source", "user_edit")
    meta["written_by"] = user_id
    payload = {
        "memory": content_str,
        "collection": SHARED_SCOPE_COLLECTION,
        "metadata": meta,
    }

    memory_events = getattr(overlord, "memory_events", None)
    event = None
    if memory_events is not None:
        # record() is failure-isolated by contract: it returns None on
        # append failure (or when the substrate is disabled), never raises.
        event = await memory_events.record(
            user_id=str(user_id),
            event_type=EVENT_FACT_EXTRACTED,
            payload=payload,
            source=SOURCE_USER_EDIT,
            scope_type=scope[0],
            scope_id=scope[1],
        )
    if event is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Shared-scope memories require the memory event substrate; "
            "the write was not recorded",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=503)

    memory_id = await apply_fact_event(
        overlord.long_term_memory,
        user_id,
        payload,
        event_id=event["id"],
        scope=scope,
    )
    return memory_id, None


# ---------------------------------------------------------------------------
# Memory ingestion (Phase 3a): contract validation + async accept helpers
# ---------------------------------------------------------------------------

# RequestTracker statuses -> the ingestion status vocabulary developers see.
_INGESTION_STATUS_MAP = {
    RequestStatus.PENDING: "queued",
    RequestStatus.PROCESSING: "processing",
    RequestStatus.RUNNING: "processing",
    RequestStatus.AWAITING_CLARIFICATION: "processing",
    RequestStatus.COMPLETED: "completed",
    RequestStatus.FAILED: "failed",
    RequestStatus.CANCELLED: "failed",
}


class MemoryIngestBatch(BaseModel):
    """Body for POST /v1/memories/batch: up to input_limits.max_batch_items
    ingestion items, each following the single-item contract (``source``
    required per item)."""

    items: List[MemoryCreate]


def _ingest_payload(memory: MemoryCreate) -> Dict[str, Any]:
    """Map the request model onto the ingestion validator's contract keys."""
    return {
        "content": memory.content if memory.content is not None else memory.detail,
        "source": memory.source,
        "source_id": memory.source_id,
        "timestamp": memory.timestamp,
        "subject": memory.subject,
        "metadata": memory.metadata,
    }


def _error_details(error_response: JSONResponse) -> str:
    """Extract the human-readable message from a formed error response.

    Used to fold per-item scope-authorization failures into the batch
    endpoint's 207-style per-item results while the single-item path
    returns the same response verbatim -- one source of truth for the
    denial semantics (403 grant checks, 422 scope validation).
    """
    try:
        body = json.loads(error_response.body)
        return body["error"]["message"]
    except Exception:
        return "Request rejected"


def _ingestion_service_or_error(overlord, request_id):
    """Resolve the overlord's ingestion service, or a formed 503."""
    service = getattr(overlord, "memory_ingestion", None)
    if service is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Memory ingestion service not available",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=503)
    return service, None


async def _handle_ingestion(
    formation, overlord, user_id: str, memory: MemoryCreate, request_id: Optional[str]
) -> JSONResponse:
    """POST /v1/memories with ``source``: the single-item ingestion path.

    Idempotency contract: (source, source_id) within this formation+user
    never creates duplicates. A replayed POST returns 200 with
    ``duplicate: true``, the original event id, and the events already
    derived from it -- never an error. New items return 202 with the
    ``processing_id`` to poll.
    """
    service, error_response = _ingestion_service_or_error(overlord, request_id)
    if error_response:
        return error_response

    item, error_message = validate_item(
        _ingest_payload(memory), getattr(overlord, "input_validator", None)
    )
    if error_message:
        response = create_error_response("INVALID_PARAMS", error_message, None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=422)

    # Scope + grant behavior is identical to the direct memory write path
    # (memory namespaces Phases 2+3): same validation, same 403 semantics.
    scope, error_response = await _resolve_write_scope(formation, user_id, memory, request_id)
    if error_response:
        return error_response
    item.scope = scope

    try:
        outcome = await service.submit(user_id, [(0, item)])
    except IngestionBusyError as e:
        response = create_error_response("RATE_LIMITED", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=429)
    except IngestionUnavailableError as e:
        response = create_error_response("SERVICE_UNAVAILABLE", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=503)
    except Exception as e:
        # Unexpected accept-path failure (tracker/task machinery): the
        # service released its in-flight slot on the way out, so a retry
        # is safe -- surface a formatted error, never a raw 500.
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to accept memory for ingestion: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    result = outcome["results"][0]
    if result["status"] == STATUS_INVALID:  # defensive; validate_item runs first
        response = create_error_response(
            "INVALID_PARAMS", result.get("error", "Invalid ingestion item"), None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=422)

    duplicate = result["status"] == STATUS_DUPLICATE
    data: Dict[str, Any] = {
        "status": result["status"],
        "duplicate": duplicate,
        "event_id": result["event_id"],
        "source": item.source,
        "source_id": item.source_id,
        "scope": scope[0] if scope else SCOPE_TYPE_USER,
        "scope_id": scope[1] if scope else None,
    }
    if duplicate:
        # The original accept's outcome: events the pipeline derived from
        # the first ingestion of this (source, source_id).
        data["derived_events"] = result.get("derived_events", [])
        status_code = 200
    else:
        processing_id = outcome["processing_id"]
        data["processing_id"] = processing_id
        data["status_url"] = f"/v1/memories/ingestion/{processing_id}"
        status_code = 202

    response = create_success_response(
        APIObjectType.MEMORY_INGESTION, APIEventType.MEMORY_INGESTION_ACCEPTED, data, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=status_code)


@router.get("/memories", response_model=APIResponse, operation_id="search_memories")
async def get_user_memories(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of memories to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    scopes: Optional[str] = Query(
        None,
        description=(
            "Comma-separated scope narrowing (user,group,formation). "
            "Default: all scopes the user can read"
        ),
    ),
) -> JSONResponse:
    """
    Get memories for a user.

    By default the listing includes the shared-scope memories the user
    can read (their groups' rows and formation rows -- memory namespaces
    Phases 2+3); ``scopes=user`` narrows to the user's own memories.

    Args:
        x_user_id: User ID from X-Muxi-User-ID header
        limit: Maximum number of memories to return
        offset: Offset for pagination
        scopes: Optional comma-separated scope narrowing

    Returns:
        List of memories visible to the user
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    scopes_list = None
    if scopes:
        scopes_list = [s.strip().lower() for s in scopes.split(",") if s.strip()]
        invalid = [s for s in scopes_list if s not in SCOPE_TYPES]
        if invalid or not scopes_list:
            response = create_error_response(
                "INVALID_PARAMS",
                f"Invalid scopes {invalid}; expected a subset of {list(SCOPE_TYPES)}",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=422)

    # Check if persistent memory is configured
    if not formation.has_persistent_memory():
        response = memory_list_response([], request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)

    # Get overlord for memory access
    overlord = getattr(formation, "_overlord", None)
    if not overlord or not hasattr(overlord, "long_term_memory") or not overlord.long_term_memory:
        response = memory_list_response([], request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)

    # Request middleware + RBAC pipeline (request-middleware PRD): the
    # middleware attaches the caller's groups and may rewrite the
    # identity; the resolved permissions land in the request context so
    # the shared-scope read fan-out below sees them.
    user_id, _permissions, error_response = await _run_request_pipeline(
        formation, user_id, request_id, "/v1/memories"
    )
    if error_response:
        return error_response

    try:
        # List memories visible to this user (no vector search required).
        # Default fans out to the shared scopes the user can read, taken
        # from the per-request permissions set by the pipeline above.
        memories = await overlord.long_term_memory.list_memories(
            limit=limit,
            offset=offset,
            external_user_id=user_id,
            scopes=scopes_list,
        )

        # Convert to API format
        memory_list = []
        for mem in memories:
            memory_list.append(
                {
                    "id": mem.get("id"),
                    "content": mem.get("content") or mem.get("text"),
                    "created_at": mem.get("created_at"),
                    "metadata": mem.get("metadata", {}),
                    "scope": mem.get("scope_type", SCOPE_TYPE_USER),
                    "scope_id": mem.get("scope_id"),
                }
            )

        response = memory_list_response(memory_list, request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to retrieve memories: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.post("/memories", response_model=APIResponse, operation_id="create_memory")
async def create_user_memory(
    request: Request,
    memory: MemoryCreate,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Create a memory for a user.

    Args:
        memory: Memory content and metadata
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Created memory details
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    # Check if persistent memory is configured
    if not formation.has_persistent_memory():
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Persistent memory not configured", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get overlord for memory access
    overlord = getattr(formation, "_overlord", None)
    if not overlord or not hasattr(overlord, "long_term_memory") or not overlord.long_term_memory:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Memory service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Memory ingestion (Phase 3a): a request carrying `source` follows the
    # ingestion contract (idempotent accept + async pipeline). Requests
    # without `source` stay on the direct write path, byte-identical to
    # the pre-ingestion behavior.
    if memory.source is not None:
        return await _handle_ingestion(formation, overlord, user_id, memory, request_id)

    try:
        content_str = memory.get_content_string()
    except ValueError as e:
        response = create_error_response(
            "INVALID_PARAMS",
            str(e),
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=422)

    # Request middleware + RBAC pipeline (request-middleware PRD): groups
    # arrive from the middleware; the identity may be rewritten.
    user_id, permissions, error_response = await _run_request_pipeline(
        formation, user_id, request_id, "/v1/memories"
    )
    if error_response:
        return error_response

    # Memory namespaces: validate + authorize the requested scope (user
    # scope returns scope=None and stays on the exact pre-namespaces path).
    scope, error_response = await _resolve_write_scope(
        formation, user_id, memory, request_id, permissions=permissions
    )
    if error_response:
        return error_response

    try:
        if scope is None:
            # User scope: today's ungated write path, unchanged.
            memory_id = await overlord.long_term_memory.add(
                content=content_str,
                metadata=memory.get_metadata(),
                external_user_id=user_id,
            )
        else:
            # Shared scope: event-first write (see _write_shared_memory).
            memory_id, error_response = await _write_shared_memory(
                overlord, user_id, content_str, memory.get_metadata(), scope, request_id
            )
            if error_response:
                return error_response

        # Scope awareness note: per-user synopsis caches
        # (user_synopsis_identity / user_synopsis_context) are built from
        # user-scope sources only (identity collections + captain's log),
        # so a shared-scope write cannot stale them; the context synopsis
        # is additionally TTL-bound. No invalidation hook is needed here.
        result = {
            "id": memory_id,
            "content": {"type": memory.type or "general", "detail": content_str},
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "metadata": memory.get_metadata(),
            "scope": scope[0] if scope else SCOPE_TYPE_USER,
            "scope_id": scope[1] if scope else None,
        }

        response = create_success_response(
            APIObjectType.MEMORY, APIEventType.MEMORY_CREATED, result, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to create memory: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.post("/memories/batch", response_model=APIResponse, operation_id="ingest_memories_batch")
async def ingest_memories_batch(
    request: Request,
    batch: MemoryIngestBatch,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Ingest a batch of memories (Memory Ingestion Phase 3a).

    Accepts up to input_limits.max_batch_items items, each following the
    single-item ingestion contract (``source`` required). The response is
    207-style: one entry per item, in order, with status
    accepted | duplicate | invalid. Accepted items share one background
    processing job (``processing_id``) whose per-item pipeline outcomes
    are pollable at GET /v1/memories/ingestion/{processing_id}.

    Duplicates within the formation+user's (source, source_id) space are
    never re-created and never errors; invalid items never block the rest
    of the batch.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    if not formation.has_persistent_memory():
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Persistent memory not configured", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    overlord = getattr(formation, "_overlord", None)
    if not overlord or not hasattr(overlord, "long_term_memory") or not overlord.long_term_memory:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Memory service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    service, error_response = _ingestion_service_or_error(overlord, request_id)
    if error_response:
        return error_response

    if not batch.items:
        response = create_error_response(
            "INVALID_PARAMS", "'items' must contain at least one item", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=422)

    input_validator = getattr(overlord, "input_validator", None)
    if input_validator is not None:
        try:
            input_validator.validate_batch_size(batch.items)
        except ValueError as e:
            response = create_error_response("INVALID_PARAMS", str(e), None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=422)

    # Per-item validation + scope authorization. Invalid items are
    # reported in place; they never block the rest of the batch.
    item_results: Dict[int, Dict[str, Any]] = {}
    to_submit = []
    for index, entry in enumerate(batch.items):
        item, error_message = validate_item(_ingest_payload(entry), input_validator)
        if error_message:
            item_results[index] = {"status": STATUS_INVALID, "error": error_message}
            continue
        scope, error_response = await _resolve_write_scope(formation, user_id, entry, request_id)
        if error_response:
            item_results[index] = {
                "status": STATUS_INVALID,
                "error": _error_details(error_response),
            }
            continue
        item.scope = scope
        to_submit.append((index, item))

    processing_id = None
    if to_submit:
        try:
            outcome = await service.submit(user_id, to_submit)
        except IngestionBusyError as e:
            # Nothing was appended: the whole batch is safely retryable.
            response = create_error_response("RATE_LIMITED", str(e), None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=429)
        except IngestionUnavailableError as e:
            response = create_error_response("SERVICE_UNAVAILABLE", str(e), None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=503)
        except Exception as e:
            # Unexpected accept-path failure: the service released its
            # in-flight slot on the way out, so a retry is safe.
            response = create_error_response(
                "INTERNAL_ERROR",
                f"Failed to accept memory batch for ingestion: {str(e)}",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=500)
        processing_id = outcome["processing_id"]
        item_results.update(outcome["results"])

    items_data = []
    for index in range(len(batch.items)):
        entry_result = dict(item_results[index])
        entry_result["index"] = index
        items_data.append(entry_result)

    counts = {
        "accepted": sum(1 for r in items_data if r["status"] == STATUS_ACCEPTED),
        "duplicate": sum(1 for r in items_data if r["status"] == STATUS_DUPLICATE),
        "invalid": sum(1 for r in items_data if r["status"] == STATUS_INVALID),
    }
    data: Dict[str, Any] = {
        "processing_id": processing_id,
        "items": items_data,
        "counts": counts,
    }
    if processing_id:
        data["status_url"] = f"/v1/memories/ingestion/{processing_id}"

    response = create_success_response(
        APIObjectType.MEMORY_INGESTION, APIEventType.MEMORY_INGESTION_ACCEPTED, data, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get(
    "/memories/ingestion/{processing_id}",
    response_model=APIResponse,
    operation_id="get_ingestion_status",
)
async def get_ingestion_status(
    request: Request,
    processing_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Poll an ingestion processing job (Memory Ingestion Phase 3a).

    Status lifecycle: queued -> processing -> completed | failed.
    Completed jobs report per-item pipeline outcomes (classification,
    filter level, disposition, extracted-fact counts) plus the job's
    token usage for cost attribution. Completed results are retained for
    a short TTL (default 5 minutes) after completion.

    With ClientKey: X-Muxi-User-ID required; only the submitting user's
    jobs are visible. With AdminKey: any job.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
    if error_response:
        return error_response

    overlord = getattr(formation, "_overlord", None)
    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    state = await overlord.request_tracker.get_request(processing_id)
    if state is None:
        response = create_error_response(
            "NOT_FOUND",
            f"Unknown or expired processing_id '{processing_id}' "
            "(completed results are retained for 5 minutes)",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    if user_id and state.user_id != user_id:
        response = create_error_response(
            "FORBIDDEN", "Ingestion job does not belong to this user", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=403)

    data: Dict[str, Any] = {
        "processing_id": processing_id,
        "status": _INGESTION_STATUS_MAP.get(state.status, state.status.value),
        "created_at": state.get_created_timestamp(),
    }
    if state.end_time:
        data["completed_at"] = state.end_time
    if state.error:
        data["error"] = state.error
    if isinstance(state.result, dict):
        # Per-item pipeline outcomes + counts + token usage.
        data.update(state.result)

    response = create_success_response(
        APIObjectType.MEMORY_INGESTION, APIEventType.MEMORY_INGESTION_STATUS, data, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/memories/{memory_id}", response_model=APIResponse, operation_id="delete_memory")
async def delete_user_memory(
    request: Request,
    memory_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Delete a user memory.

    Args:
        memory_id: Memory ID to delete
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    # Check if persistent memory is configured
    if not formation.has_persistent_memory():
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Persistent memory not configured", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get overlord for memory access
    overlord = getattr(formation, "_overlord", None)
    if not overlord or not hasattr(overlord, "long_term_memory") or not overlord.long_term_memory:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Memory service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        # Delete memory (with user_id check for security)
        # Handle both sync (LongTermMemory) and async (Memobase) delete methods
        import inspect

        delete_result = overlord.long_term_memory.delete(
            memory_id=memory_id,
            external_user_id=user_id,
        )
        if inspect.iscoroutine(delete_result):
            success = await delete_result
        else:
            success = delete_result

        if success:
            result = {"deleted": memory_id, "user_id": user_id}
            response = create_success_response(
                APIObjectType.MEMORY, APIEventType.MEMORY_DELETED, result, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=200)
        else:
            response = create_error_response(
                "NOT_FOUND", f"Memory {memory_id} not found", None, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=404)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to delete memory: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.get("/history", response_model=APIResponse, operation_id="get_history")
async def get_history(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of log entries to return"),
    date_from: Optional[str] = Query(None, description="Earliest entry date (ISO date)"),
    date_to: Optional[str] = Query(None, description="Latest entry date (ISO date)"),
    include_sources: bool = Query(False, description="Include source lineage per entry"),
) -> JSONResponse:
    """
    Get the user's captain's log history (Memory Revamp Phase 2).

    Returns the narrative log entries for a user, newest first, optionally
    with the source lineage each entry was derived from.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    overlord = getattr(formation, "_overlord", None)
    captains_log = getattr(overlord, "captains_log", None) if overlord else None
    if captains_log is None:
        response = create_success_response(
            APIObjectType.MEMORY,
            APIEventType.MEMORY_RETRIEVED,
            {"entries": [], "count": 0},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    try:
        entries = await captains_log.get_history(
            user_id,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            include_sources=include_sources,
        )
        response = create_success_response(
            APIObjectType.MEMORY,
            APIEventType.MEMORY_RETRIEVED,
            {"entries": entries, "count": len(entries)},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to retrieve history: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


# Buffer Memory Operations
@router.get("/memory/buffer", response_model=APIResponse, operation_id="get_buffer_memory")
def get_buffer_status(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Get buffer memory data for a specific user.

    Accepts both ClientKey and AdminKey, but X-Muxi-User-ID is required for both.
    For aggregate stats, use GET /memory/buffer/stats instead.

    Returns:
        Buffer status with message counts and session info
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # User ID is required for this endpoint (both ClientKey and AdminKey)
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    try:
        # Get overlord for buffer access
        overlord = getattr(formation, "_overlord", None)
        if not overlord:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Overlord service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Get buffer memory
        buffer = getattr(overlord, "buffer_memory", None)
        if buffer is None:
            # Return empty status if no buffer
            data = {
                "user_id": user_id,
                "total_messages": 0,
                "sessions": [],
                "buffer_size_kb": 0,
            }
            response = create_success_response(
                APIObjectType.MEMORY,
                APIEventType.MEMORY_RETRIEVED,
                data,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)

        # Get buffer stats
        total_messages = 0
        sessions = []
        buffer_size_kb = 0

        if hasattr(buffer, "get_buffer_stats"):
            stats = buffer.get_buffer_stats(user_id)
            total_messages = stats.get("total_messages", 0)
            sessions = stats.get("sessions", [])
            buffer_size_kb = stats.get("size_kb", 0)
        else:
            # Fallback: calculate from buffer deque
            if hasattr(buffer, "buffer"):
                # Buffer is a deque - count messages for this user by filtering
                import sys

                user_messages = [
                    msg
                    for msg in buffer.buffer
                    if isinstance(msg, dict) and msg.get("metadata", {}).get("user_id") == user_id
                ]
                total_messages = len(user_messages)
                buffer_size_kb = sys.getsizeof(str(user_messages)) / 1024

        data = {
            "user_id": user_id,
            "total_messages": total_messages,
            "sessions": sessions,
            "buffer_size_kb": round(buffer_size_kb, 2),
        }

        response = create_success_response(
            APIObjectType.MEMORY,
            APIEventType.MEMORY_BUFFER_STATUS,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to get buffer status: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete("/memory/buffer", response_model=APIResponse, operation_id="clear_buffer_memory")
def clear_buffer(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Clear buffer memory.

    With ClientKey: X-Muxi-User-ID required (clears user's buffer)
    With AdminKey: X-Muxi-User-ID optional (omit to clear all, provide to clear specific user)

    Returns:
        Success response with cleared counts
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
    if error_response:
        return error_response

    try:
        # Get overlord for buffer access
        overlord = getattr(formation, "_overlord", None)
        if not overlord:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Overlord service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Get buffer memory
        buffer = getattr(overlord, "buffer_memory", None)
        if buffer is None:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Buffer memory is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Clear user's buffer by manually removing matching items
        messages_cleared = 0
        sessions_cleared = 0

        if hasattr(buffer, "buffer"):
            # Single-pass rebuild for O(n) performance
            from collections import deque

            original_length = len(buffer.buffer)
            new_buffer = deque()
            unique_sessions = set()

            for item in buffer.buffer:
                if isinstance(item, dict) and item.get("metadata", {}).get("user_id") == user_id:
                    # Track unique sessions being removed
                    sess_id = item.get("metadata", {}).get("session_id")
                    if sess_id:
                        unique_sessions.add(sess_id)
                else:
                    # Keep items that don't match
                    new_buffer.append(item)

            messages_cleared = original_length - len(new_buffer)
            sessions_cleared = len(unique_sessions)
            buffer.buffer = new_buffer

            # Mark index for rebuild if we removed items and vector search is enabled
            if messages_cleared > 0 and hasattr(buffer, "needs_rebuild"):
                buffer.needs_rebuild = True

        data = {
            "message": "Buffer cleared successfully",
            "user_id": user_id,
            "messages_cleared": messages_cleared,
            "sessions_cleared": sessions_cleared,
        }

        response = create_success_response(
            APIObjectType.MESSAGE,
            APIEventType.MEMORY_BUFFER_USER_CLEARED,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to clear buffer: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete(
    "/memory/buffer/{session_id}", response_model=APIResponse, operation_id="clear_session_buffer"
)
def clear_session_buffer(
    request: Request,
    session_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Clear buffer memory for a specific session.

    With ClientKey: X-Muxi-User-ID required, session must belong to user
    With AdminKey: X-Muxi-User-ID optional, can clear any session

    Returns:
        Success response with cleared message count
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
    if error_response:
        return error_response

    try:
        # Get overlord for buffer access
        overlord = getattr(formation, "_overlord", None)
        if not overlord:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Overlord service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Get buffer memory
        buffer = getattr(overlord, "buffer_memory", None)
        if buffer is None:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Buffer memory is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Clear session buffer by manually removing matching items
        messages_cleared = 0

        if hasattr(buffer, "buffer"):
            # Single-pass rebuild for O(n) performance
            from collections import deque

            original_length = len(buffer.buffer)
            new_buffer = deque()

            for item in buffer.buffer:
                if (
                    isinstance(item, dict)
                    and item.get("metadata", {}).get("user_id") == user_id
                    and item.get("metadata", {}).get("session_id") == session_id
                ):
                    # Skip items that match (they're being cleared)
                    pass
                else:
                    # Keep items that don't match
                    new_buffer.append(item)

            messages_cleared = original_length - len(new_buffer)
            buffer.buffer = new_buffer

            # Mark index for rebuild if we removed items and vector search is enabled
            if messages_cleared > 0 and hasattr(buffer, "needs_rebuild"):
                buffer.needs_rebuild = True

        data = {
            "message": "Session buffer cleared successfully",
            "user_id": user_id,
            "session_id": session_id,
            "messages_cleared": messages_cleared,
        }

        response = create_success_response(
            APIObjectType.MESSAGE,
            APIEventType.MEMORY_BUFFER_SESSION_CLEARED,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to clear session buffer: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)
