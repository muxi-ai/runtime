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


@router.patch("/async", response_model=APIResponse)
async def update_async_settings(request: Request, settings: AsyncSettingsUpdate) -> JSONResponse:
    """
    Update async processing settings.

    Args:
        settings: New async settings to apply

    Returns:
        Updated async configuration
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement async settings update logic

    async_config = {
        "enabled": settings.enabled,
        "max_concurrent_jobs": settings.max_concurrent_jobs,
        "job_timeout_seconds": settings.job_timeout_seconds,
        "retention_policy": settings.retention_policy,
    }

    response = create_success_response(
        APIObjectType.ASYNC, APIEventType.ASYNC_UPDATED, async_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/async/jobs", response_model=APIResponse)
async def list_async_jobs(request: Request) -> JSONResponse:
    """
    List all async jobs.

    Returns:
        List of async job statuses
    """
    formation = request.app.state.formation
    overlord = formation.overlord
    request_id = getattr(request.state, "request_id", None)

    # Get all active async jobs across all users
    all_requests = await overlord.request_tracker.get_all_requests()
    
    jobs = []
    for req_id, state in all_requests.items():
        job_data = {
            "request_id": req_id,
            "user_id": state.user_id,
            "session_id": state.session_id,
            "status": state.status.value,
            "progress": state.progress,
            "created_at": state.created_at if hasattr(state, 'created_at') else state.start_time,
            "completed_at": state.end_time,
        }
        # Include error if present
        if state.error:
            job_data["error"] = state.error
        jobs.append(job_data)

    # Wrap jobs list in dict for APIResponse schema compliance
    response = create_success_response(APIObjectType.LIST, APIEventType.JOB_LIST, {"jobs": jobs}, request_id)
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/async/jobs/{job_id}", response_model=APIResponse)
async def get_async_job(request: Request, job_id: str) -> JSONResponse:
    """
    Get async job status.

    Args:
        job_id: Job ID to retrieve

    Returns:
        Job status and result if complete
    """
    formation = request.app.state.formation
    overlord = formation.overlord
    request_id = getattr(request.state, "request_id", None)

    # Get full job status (checks both request tracker and buffer memory)
    status = await overlord.get_request_status(job_id)

    if "error" in status:
        response = create_error_response("NOT_FOUND", status["error"], None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(APIObjectType.JOB, APIEventType.JOB_RETRIEVED, status, request_id)
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/async/jobs/{job_id}", response_model=APIResponse)
async def cancel_async_job(request: Request, job_id: str) -> JSONResponse:
    """
    Cancel an async job.

    Args:
        job_id: Job ID to cancel

    Returns:
        Success response
    """
    formation = request.app.state.formation
    overlord = formation.overlord
    request_id = getattr(request.state, "request_id", None)

    # Cancel the job
    result = await overlord.cancel_request(job_id)

    if result["success"]:
        response = create_success_response(APIObjectType.JOB, APIEventType.JOB_CANCELLED, result, request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)
    else:
        response = create_error_response("OPERATION_FAILED", result["message"], None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=400)
