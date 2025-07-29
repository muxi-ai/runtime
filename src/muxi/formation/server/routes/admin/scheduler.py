"""
Scheduler configuration endpoints.

These endpoints provide scheduler configuration access and job management,
requiring admin API key authentication.
"""

from typing import Dict, Any, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    create_success_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Scheduler"])


class SchedulerUpdate(BaseModel):
    """Model for updating scheduler configuration."""

    enabled: bool = True
    timezone: str = "UTC"
    jobs: List[Dict[str, Any]] = []


@router.get("/scheduler", response_model=APIResponse)
async def get_scheduler_config(request: Request) -> JSONResponse:
    """
    Get complete scheduler configuration.

    Returns:
        Full scheduler YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    scheduler_config = formation.config.get("scheduler", {})

    response = create_success_response(
        APIObjectType("scheduler"),
        APIEventType("scheduler.retrieved"),
        scheduler_config,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.patch("/scheduler", response_model=APIResponse)
async def update_scheduler(request: Request, config: SchedulerUpdate) -> JSONResponse:
    """
    Update scheduler configuration.

    Args:
        config: New scheduler configuration

    Returns:
        Updated scheduler configuration
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement scheduler update logic

    scheduler_config = {"enabled": config.enabled, "timezone": config.timezone, "jobs": config.jobs}

    response = create_success_response(
        APIObjectType("scheduler"), APIEventType("scheduler.updated"), scheduler_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/scheduler/jobs/{job_id}", response_model=APIResponse)
async def remove_scheduled_job(request: Request, job_id: str) -> JSONResponse:
    """
    Remove a scheduled job.

    Args:
        job_id: ID of the scheduled job to remove

    Returns:
        Success response
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement scheduled job removal logic
    # Check if job exists and remove it

    response = create_success_response(
        APIObjectType("scheduler"),
        APIEventType("scheduler_job.deleted"),
        {"message": f"Scheduled job '{job_id}' removed successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
