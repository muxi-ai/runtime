"""
Memory configuration and management endpoints.

These endpoints provide memory configuration and buffer management,
requiring admin API key authentication.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .....datatypes.api import APIEventType, APIObjectType
from .....services import observability
from ...responses import (
    APIResponse,
    create_error_response,
    create_success_response,
)
from ...utils import distillery_service_or_error

router = APIRouter(tags=["Memory"])


class MemoryConfigUpdate(BaseModel):
    """Model for updating memory configuration."""

    buffer_size: Optional[int] = None
    buffer_multiplier: Optional[float] = None
    buffer_vector_search: Optional[bool] = None
    working_max_memory_mb: Optional[int] = None
    working_fifo_interval_min: Optional[int] = None


class MemoryItemUpdate(BaseModel):
    """Model for updating memory configuration item."""

    value: Any


class MemoryRebuildRequest(BaseModel):
    """Model for a memory projection rebuild request."""

    user_id: str
    projection: Optional[str] = None
    dry_run: bool = False


@router.get("/memory", response_model=APIResponse)
async def get_memory_config(request: Request) -> JSONResponse:
    """
    Get complete memory configuration.

    Returns:
        Full memory YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    memory_config = formation.config.get("memory", {})

    response = create_success_response(
        APIObjectType.MEMORY_CONFIG, APIEventType.MEMORY_CONFIG_RETRIEVED, memory_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/memory/stats", response_model=APIResponse)
async def get_buffer_stats(request: Request) -> JSONResponse:
    """
    Get aggregate buffer statistics across all users.

    Admin only endpoint. Returns total entries, user count, session count,
    and utilization metrics.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord = getattr(formation, "_overlord", None)
    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Overlord service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    buffer = getattr(overlord, "buffer_memory", None)
    if not buffer:
        data = {
            "total_entries": 0,
            "total_users": 0,
            "total_sessions": 0,
            "buffer_size_kb": 0,
            "max_size": 0,
            "utilization": 0.0,
        }
        response = create_success_response(
            APIObjectType.MEMORY,
            APIEventType.MEMORY_RETRIEVED,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    total_entries = 0
    if hasattr(buffer, "buffer"):
        total_entries = len(buffer.buffer)

    max_size = getattr(buffer, "size", 0)
    utilization = (total_entries / max_size) if max_size > 0 else 0.0

    users = set()
    sessions = set()
    buffer_size_bytes = 0

    if hasattr(buffer, "buffer"):
        import sys

        for msg in buffer.buffer:
            if isinstance(msg, dict):
                metadata = msg.get("metadata", {})
                if metadata.get("user_id"):
                    users.add(metadata["user_id"])
                if metadata.get("session_id"):
                    sessions.add(metadata["session_id"])
        buffer_size_bytes = sys.getsizeof(str(list(buffer.buffer)))

    data = {
        "total_entries": total_entries,
        "total_users": len(users),
        "total_sessions": len(sessions),
        "buffer_size_kb": round(buffer_size_bytes / 1024, 2),
        "max_size": max_size,
        "utilization": round(utilization, 2),
    }

    response = create_success_response(
        APIObjectType.MEMORY,
        APIEventType.MEMORY_RETRIEVED,
        data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/memory/rebuild", response_model=APIResponse, operation_id="rebuild_memory")
async def rebuild_memory_projections(
    request: Request, rebuild: MemoryRebuildRequest
) -> JSONResponse:
    """
    Rebuild memory projections from the event log (Memory Event Substrate).

    Wipes the requested projection(s) for a user and replays that user's
    memory events through the projection builders. Omit ``projection`` to
    rebuild every registered projection; set ``dry_run`` to report the
    event counts that would be replayed without touching derived state.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord = getattr(formation, "_overlord", None)
    memory_events = getattr(overlord, "memory_events", None) if overlord else None
    if memory_events is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Memory event substrate is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        report = await memory_events.rebuild(
            rebuild.user_id, projection=rebuild.projection, dry_run=rebuild.dry_run
        )
    except ValueError as e:
        response = create_error_response("INVALID_PARAMS", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=422)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to rebuild projections: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    data = {"user_id": rebuild.user_id, "dry_run": rebuild.dry_run, "projections": report}
    response = create_success_response(
        APIObjectType.MEMORY, APIEventType.MEMORY_RETRIEVED, data, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


class MemoryLintRequest(BaseModel):
    """Model for an on-demand memory lint request."""

    user_id: Optional[str] = None  # None audits every user


@router.post("/memory/lint", response_model=APIResponse, operation_id="lint_memory")
async def lint_memory(request: Request, lint: MemoryLintRequest) -> JSONResponse:
    """
    Run the memory lint audit on demand (Memory Revamp Phase 5).

    Walks the knowledge store (one user, or every user when ``user_id`` is
    omitted) and returns the health report: unresolved conflicts, superseded
    facts hard-deleted, orphaned relationships removed, captain's log gaps,
    stale artifacts, and knowledge index regenerations. Findings are written
    back into the knowledge index as knowledge gaps.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord = getattr(formation, "_overlord", None)
    memory_lint = getattr(overlord, "memory_lint", None) if overlord else None
    if memory_lint is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Memory lint is not configured (declare a 'memory.lint' block)",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        report = await memory_lint.run_lint(user_id=lint.user_id)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Memory lint failed: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    data = {"user_id": lint.user_id, "report": report}
    response = create_success_response(
        APIObjectType.MEMORY, APIEventType.MEMORY_RETRIEVED, data, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# ---------------------------------------------------------------------------
# Distillery registration (Memory Distillery Phase 3b)
# ---------------------------------------------------------------------------


class DistilleryRegistration(BaseModel):
    """Model for registering an on-prem distillery.

    ``public_key`` is the distillery's Ed25519 public key
    (``ed25519:<base64 DER or raw 32 bytes>``). ``scope`` limits what the
    distillery may write: ``user_ids`` ("all" | "pattern:<glob>" | [ids]),
    ``event_types``, ``max_events_per_day``, ``max_batch_size`` -- omitted
    keys fall back to the formation's memory.distillery defaults.
    """

    name: str
    public_key: str
    description: Optional[str] = None
    scope: Optional[Dict[str, Any]] = None
    trust_level: Optional[str] = None


@router.post("/memory/distilleries", response_model=APIResponse, operation_id="register_distillery")
async def register_distillery(
    request: Request, registration: DistilleryRegistration
) -> JSONResponse:
    """
    Register a distillery (Memory Distillery Phase 3b).

    Stores the distillery's Ed25519 public key and write scope; the
    returned ``distillery_id`` is the X-Distillery-ID every signed batch
    must carry. New registrations default to the formation's configured
    trust level (provisional unless overridden) -- provisional caps
    source_confidence until the registration is trusted.
    """
    request_id = getattr(request.state, "request_id", None)

    service, error_response = distillery_service_or_error(request, request_id)
    if error_response:
        return error_response

    try:
        record = await service.registry.register(
            name=registration.name,
            public_key=registration.public_key,
            scope=service.scope_defaults(registration.scope),
            trust_level=registration.trust_level or service.default_trust_level,
            description=registration.description,
        )
    except ValueError as e:
        response = create_error_response("INVALID_PARAMS", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=422)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to register distillery: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    observability.observe(
        event_type=observability.ConversationEvents.MEMORY_DISTILLERY_REGISTERED,
        level=observability.EventLevel.INFO,
        data={
            "distillery_id": record["distillery_id"],
            "name": record["name"],
            "trust_level": record["trust_level"],
            "scope": record["scope"],
        },
        description=f"Distillery registered: {record['name']} ({record['distillery_id']})",
    )
    response = create_success_response(
        APIObjectType.MEMORY_DISTILLERY,
        APIEventType.MEMORY_DISTILLERY_REGISTERED,
        record,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=201)


@router.get("/memory/distilleries", response_model=APIResponse, operation_id="list_distilleries")
async def list_distilleries(request: Request) -> JSONResponse:
    """List this formation's registered distilleries (newest first)."""
    request_id = getattr(request.state, "request_id", None)

    service, error_response = distillery_service_or_error(request, request_id)
    if error_response:
        return error_response

    try:
        distilleries = await service.registry.list()
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to list distilleries: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    response = create_success_response(
        APIObjectType.MEMORY_DISTILLERY_LIST,
        APIEventType.MEMORY_DISTILLERY_LIST,
        {"distilleries": distilleries, "count": len(distilleries)},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete(
    "/memory/distilleries/{distillery_id}",
    response_model=APIResponse,
    operation_id="revoke_distillery",
)
async def revoke_distillery(request: Request, distillery_id: str) -> JSONResponse:
    """
    Revoke a distillery registration.

    Subsequent batches from it are rejected with 410 Gone. Previously
    ingested events are NOT removed -- issue explicit user.deletion events
    (the substrate's forgetting path) to purge them.
    """
    request_id = getattr(request.state, "request_id", None)

    service, error_response = distillery_service_or_error(request, request_id)
    if error_response:
        return error_response

    try:
        record = await service.registry.revoke(distillery_id)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to revoke distillery: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    if record is None:
        response = create_error_response(
            "NOT_FOUND", f"Unknown distillery '{distillery_id}'", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    observability.observe(
        event_type=observability.ConversationEvents.MEMORY_DISTILLERY_REVOKED,
        level=observability.EventLevel.INFO,
        data={"distillery_id": record["distillery_id"], "name": record["name"]},
        description=f"Distillery revoked: {record['name']} ({record['distillery_id']})",
    )
    response = create_success_response(
        APIObjectType.MEMORY_DISTILLERY,
        APIEventType.MEMORY_DISTILLERY_REVOKED,
        record,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# NOTE: /memory/buffers endpoints are deprecated - use /memory/stats instead


# Legacy endpoints kept for backward compatibility - will be removed in future version
@router.get("/memory/buffers", response_model=APIResponse, deprecated=True)
async def list_memory_buffers(request: Request) -> JSONResponse:
    """
    DEPRECATED: Use GET /memory/buffer with AdminKey instead.

    List all memory buffers.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord = getattr(formation, "_overlord", None)
    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Overlord service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    buffer = getattr(overlord, "buffer_memory", None)
    if not buffer:
        response = create_success_response(
            APIObjectType.LIST,
            APIEventType.MEMORY_LIST,
            {"buffers": [], "total_entries": 0},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    total_entries = 0
    if hasattr(buffer, "buffer"):
        total_entries = len(buffer.buffer)

    max_size = getattr(buffer, "size", 0)
    utilization = (total_entries / max_size) if max_size > 0 else 0

    kv_namespaces = {}
    kv_store = getattr(buffer, "kv_store", None)
    if kv_store is not None and (hasattr(kv_store, "keys") or isinstance(kv_store, dict)):
        for key in kv_store.keys():
            namespace = key.split(":")[0] if ":" in key else "default"
            kv_namespaces[namespace] = kv_namespaces.get(namespace, 0) + 1

    buffer_stats = {
        "total_entries": total_entries,
        "max_size": max_size,
        "utilization": round(utilization, 2),
        "kv_namespaces": kv_namespaces,
    }

    response = create_success_response(
        APIObjectType.LIST,
        APIEventType.MEMORY_LIST,
        {"buffers": [buffer_stats]},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/memory/buffers", response_model=APIResponse, deprecated=True)
async def clear_memory_buffers(request: Request) -> JSONResponse:
    """
    DEPRECATED: Use DELETE /memory/buffer with AdminKey instead.

    Clear all memory buffers.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord = getattr(formation, "_overlord", None)
    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Overlord service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    buffer = getattr(overlord, "buffer_memory", None)
    if not buffer:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Buffer memory is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    entries_cleared = 0
    if hasattr(buffer, "buffer"):
        from collections import deque

        entries_cleared = len(buffer.buffer)
        existing_maxlen = getattr(buffer.buffer, "maxlen", None)
        buffer.buffer = deque(maxlen=existing_maxlen) if existing_maxlen is not None else deque()

    kv_entries_cleared = 0
    if hasattr(buffer, "kv_store"):
        kv_entries_cleared = len(buffer.kv_store)
        buffer.kv_store.clear()

    # Mark index for rebuild if vector search is enabled
    if hasattr(buffer, "needs_rebuild"):
        buffer.needs_rebuild = True

    data = {
        "message": "All buffers cleared successfully",
        "entries_cleared": entries_cleared,
        "kv_entries_cleared": kv_entries_cleared,
    }

    response = create_success_response(
        APIObjectType.MESSAGE,
        APIEventType.MEMORY_BUFFER_CLEARED,
        data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.patch("/memory", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def update_memory_config(request: Request, config: MemoryConfigUpdate) -> JSONResponse:
    """
    Update memory configuration.

    DEPRECATED: Memory configuration should be changed via formation YAML and redeployment.

    Args:
        config: Memory configuration updates

    Returns:
        Updated memory configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get current memory configuration
    current_config = formation.config.get("memory", {})
    if not current_config:
        current_config = {"buffer": {}, "working": {}}

    # Update only provided fields (non-None values)
    if config.buffer_size is not None:
        current_config.setdefault("buffer", {})["size"] = config.buffer_size
    if config.buffer_multiplier is not None:
        current_config.setdefault("buffer", {})["multiplier"] = config.buffer_multiplier
    if config.buffer_vector_search is not None:
        current_config.setdefault("buffer", {})["vector_search"] = config.buffer_vector_search
    if config.working_max_memory_mb is not None:
        current_config.setdefault("working", {})["max_memory_mb"] = config.working_max_memory_mb
    if config.working_fifo_interval_min is not None:
        current_config.setdefault("working", {})[
            "fifo_interval_min"
        ] = config.working_fifo_interval_min

    # Update formation configuration
    formation.config["memory"] = current_config

    # NOTE: Configuration changes are ephemeral (in-memory only)
    # They take effect immediately but are lost on formation restart
    # This is by design for runtime configuration management

    response = create_success_response(
        APIObjectType.MEMORY_CONFIG, APIEventType.MEMORY_CONFIG_UPDATED, current_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.delete("/memory/{item}", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def reset_memory_setting(request: Request, item: str) -> JSONResponse:
    """
    Reset a specific memory setting to default value.

    DEPRECATED: Memory configuration should be changed via formation YAML and redeployment.

    Args:
        item: Memory setting to reset (e.g., buffer_size, working_max_memory_mb)

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Reset specific memory setting by removing it from in-memory config
    # This restores the formation YAML default value
    memory_config = formation.config.get("memory", {})

    # Define valid memory settings that can be reset
    valid_paths = {
        "buffer_size": ["buffer", "size"],
        "buffer_multiplier": ["buffer", "multiplier"],
        "buffer_vector_search": ["buffer", "vector_search"],
        "working_max_memory_mb": ["working", "max_memory_mb"],
        "working_fifo_interval_min": ["working", "fifo_interval_min"],
    }

    if item in valid_paths:
        path = valid_paths[item]
        if len(path) == 2 and path[0] in memory_config:
            section = memory_config[path[0]]
            if isinstance(section, dict) and path[1] in section:
                del section[path[1]]

    response = create_success_response(
        APIObjectType.MEMORY_CONFIG,
        APIEventType.MEMORY_CONFIG_UPDATED,
        {"message": f"Memory setting '{item}' reset to default"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
