"""
Async configuration and job management endpoints.

These endpoints provide async configuration and job tracking,
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
    create_error_response,
)
from ...secrets import restore_secret_placeholders
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Async"])


class AsyncSettingsUpdate(BaseModel):
    """Model for updating async settings."""

    enabled: bool = True
    max_concurrent_jobs: int = 10
    job_timeout_seconds: int = 3600
    retention_policy: Dict[str, Any] = {}


@router.get("/async", response_model=APIResponse)
async def get_async_config(request: Request) -> JSONResponse:
    """
    Get complete async configuration.

    Returns:
        Full async YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    async_config = formation.config.get("async", {})

    # Create a temporary config structure to apply placeholders
    temp_config = {"async": deepcopy(async_config)}
    temp_config = restore_secret_placeholders(temp_config, formation.secret_placeholders)
    async_config = temp_config.get("async", {})

    response = create_success_response(
        APIObjectType.ASYNC, APIEventType.ASYNC_RETRIEVED, async_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.patch("/async", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def update_async_settings(request: Request, settings: AsyncSettingsUpdate) -> JSONResponse:
    """
    Update async processing settings.

    DEPRECATED: Async configuration should be changed via formation YAML and redeployment.

    Args:
        settings: New async settings to apply

    Returns:
        Updated async configuration
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    request_id = getattr(request.state, "request_id", None)

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Update in-memory configuration (ephemeral - lost on restart)
    async_config = formation.config.setdefault("async", {})
    async_config["enabled"] = settings.enabled
    async_config["max_concurrent_jobs"] = settings.max_concurrent_jobs
    async_config["job_timeout_seconds"] = settings.job_timeout_seconds
    async_config["retention_policy"] = settings.retention_policy

    # Also update overlord runtime settings if available
    if hasattr(overlord, "async_threshold_seconds"):
        # Map job_timeout_seconds to async threshold
        overlord.async_threshold_seconds = settings.job_timeout_seconds

    response = create_success_response(
        APIObjectType.ASYNC, APIEventType.ASYNC_UPDATED, async_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# NOTE: /async/jobs endpoints have been removed.
# Use /requests endpoints instead (supports both ClientKey and AdminKey):
# - GET /requests - List requests (admin: all, client: user's only)
# - GET /requests/{request_id} - Get request status
# - DELETE /requests/{request_id} - Cancel request
