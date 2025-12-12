"""
A2A configuration endpoints.

These endpoints provide A2A configuration access and management,
requiring admin API key authentication.
"""

from typing import Dict, Any
from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    create_success_response,
)
from ...secrets import restore_secret_placeholders
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["A2A"])


class A2AOutboundUpdate(BaseModel):
    """Model for updating A2A outbound settings."""

    enabled: bool = True
    endpoints: Dict[str, Dict[str, Any]] = {}
    retry_policy: Dict[str, Any] = {"max_retries": 3, "initial_delay": 1, "max_delay": 60}


@router.get("/a2a", response_model=APIResponse)
async def get_a2a_config(request: Request) -> JSONResponse:
    """
    Get complete A2A configuration.

    Returns:
        Full A2A YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    a2a_config = formation.config.get("a2a", {})

    # Create a temporary config structure to apply placeholders
    temp_config = {"a2a": deepcopy(a2a_config)}
    temp_config = restore_secret_placeholders(temp_config, formation.secret_placeholders)
    a2a_config = temp_config.get("a2a", {})

    response = create_success_response(
        APIObjectType.A2A, APIEventType.A2A_RETRIEVED, a2a_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.patch("/a2a/outbound", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def update_a2a_outbound(request: Request, settings: A2AOutboundUpdate) -> JSONResponse:
    """
    Update A2A outbound settings.

    DEPRECATED: A2A configuration should be changed via formation YAML and redeployment.

    Args:
        settings: New A2A outbound configuration

    Returns:
        Updated A2A outbound configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Acquire async lock to prevent race conditions when modifying shared config
    if formation._async_config_lock is None:
        # Fallback: initialize lock if not already created (should not happen in normal operation)
        import asyncio
        formation._async_config_lock = asyncio.Lock()

    async with formation._async_config_lock:
        # Update in-memory configuration (ephemeral - lost on restart)
        a2a_config = formation.config.setdefault("a2a", {})
        outbound_config = a2a_config.setdefault("outbound", {})

        # Update only fields that were explicitly provided by the client
        # Using exclude_unset=True to avoid overwriting with default values
        for key, value in settings.dict(exclude_unset=True).items():
            outbound_config[key] = value

    response = create_success_response(
        APIObjectType.A2A,
        APIEventType.A2A_UPDATED,
        {"outbound": outbound_config},
        request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.delete("/a2a/outbound/{item}", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def reset_a2a_outbound_setting(request: Request, item: str) -> JSONResponse:
    """
    Reset a specific A2A outbound setting to default.

    DEPRECATED: A2A configuration should be changed via formation YAML and redeployment.

    Args:
        item: Setting item to reset (e.g., specific endpoint name)

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Acquire async lock to prevent race conditions
    if formation._async_config_lock is None:
        import asyncio
        formation._async_config_lock = asyncio.Lock()

    async with formation._async_config_lock:
        # Remove specific endpoint from in-memory configuration (ephemeral)
        a2a_config = formation.config.get("a2a", {})
        outbound_config = a2a_config.get("outbound", {})
        endpoints = outbound_config.get("endpoints", {})

        if item in endpoints:
            del endpoints[item]

    response = create_success_response(
        APIObjectType.A2A,
        APIEventType.A2A_UPDATED,
        {"message": f"A2A outbound setting '{item}' reset to default"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
