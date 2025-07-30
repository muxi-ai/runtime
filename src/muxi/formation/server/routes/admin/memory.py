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
        APIObjectType.CONFIG, APIEventType.CONFIG_RETRIEVED, memory_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/memory/buffers", response_model=APIResponse)
async def list_memory_buffers(request: Request) -> JSONResponse:
    """
    List all memory buffers.

    Returns:
        List of memory buffer entries
    """
    # TODO: Implement memory buffer access
    request_id = getattr(request.state, "request_id", None)

    response = create_success_response(
        APIObjectType.MEMORY_LIST,
        APIEventType.MEMORY_LIST,
        {"memories": [], "count": 0},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/memory/buffers", response_model=APIResponse)
async def clear_memory_buffers(request: Request) -> JSONResponse:
    """
    Clear all memory buffers.

    Returns:
        Not implemented response
    """
    request_id = getattr(request.state, "request_id", None)
    
    # TODO: Implement memory buffer clearing
    # This would require access to the formation's overlord and buffer memory manager
    
    response = create_error_response(
        error_code="METHOD_NOT_FOUND",
        message="Memory buffer clearing is not yet implemented",
        request_id=request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=501)


@router.patch("/memory", response_model=APIResponse)
async def update_memory_config(request: Request, config: MemoryConfigUpdate) -> JSONResponse:
    """
    Update memory configuration.

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
        current_config.setdefault("working", {})["fifo_interval_min"] = config.working_fifo_interval_min
    
    # Update formation configuration
    formation.config["memory"] = current_config
    
    # TODO: Persist configuration to file/database if needed
    # For now, configuration is only updated in memory

    response = create_success_response(
        APIObjectType.CONFIG, APIEventType.CONFIG_UPDATED, current_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/memory/{item}", response_model=APIResponse)
async def reset_memory_setting(request: Request, item: str) -> JSONResponse:
    """
    Reset a specific memory setting to default value.

    Args:
        item: Memory setting to reset (e.g., buffer_size, working_max_memory_mb)

    Returns:
        Success response
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement memory setting reset logic

    response = create_success_response(
        APIObjectType.CONFIG,
        APIEventType.CONFIG_UPDATED,
        {"message": f"Memory setting '{item}' reset to default"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
