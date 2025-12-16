"""
Memory configuration and management endpoints.

These endpoints provide memory configuration and buffer management,
requiring admin API key authentication.
"""

from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

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
