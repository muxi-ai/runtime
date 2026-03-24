"""
Scheduler configuration endpoints.

These endpoints provide scheduler configuration access and job management.
GET /scheduler/jobs supports both ClientKey and AdminKey:
- ClientKey: X-Muxi-User-ID required (returns only user's jobs)
- AdminKey: X-Muxi-User-ID optional (omit for all, provide to filter)
"""

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import croniter
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .....datatypes.api import APIEventType, APIObjectType
from ...responses import (
    APIResponse,
    create_error_response,
    create_success_response,
)


def _require_admin_key(
    request: Request,
    request_id: Optional[str],
) -> Optional[JSONResponse]:
    """
    Require AdminKey for this endpoint. Returns error response if ClientKey used.

    Returns:
        Error response if ClientKey was used, None if AdminKey was used
    """
    formation = request.app.state.formation
    api_keys = getattr(formation, "_api_keys", {})
    admin_key = api_keys.get("admin", "")

    provided_admin_key = request.headers.get("x-muxi-admin-key")
    if provided_admin_key and admin_key and secrets.compare_digest(provided_admin_key, admin_key):
        return None  # AdminKey OK

    # Not admin - reject
    response = create_error_response(
        "UNAUTHORIZED",
        "Admin API key required for this endpoint",
        None,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=401)


def _check_auth_and_user_id(
    request: Request,
    api_request_id: Optional[str],
) -> Tuple[Optional[str], bool, Optional[JSONResponse]]:
    """
    Check authentication type and validate user_id requirement.

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
    x_user_id = request.headers.get("x-muxi-user-id")

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
            api_request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=401)

    if not is_admin and not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required when using client API key",
            None,
            api_request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=400)

    return x_user_id, is_admin, None


def _get_scheduler_service(request: Request):
    """Get SchedulerService from the formation's overlord, or None."""
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    return getattr(overlord, "scheduler_service", None) if overlord else None


router = APIRouter(tags=["Scheduler"])


class SchedulerUpdate(BaseModel):
    """Model for updating scheduler configuration."""

    enabled: bool = True
    timezone: str = "UTC"
    jobs: List[Dict[str, Any]] = []


class ScheduledJobCreate(BaseModel):
    """Model for creating a scheduled job."""

    type: str = Field(..., description="Job type: 'one_time' or 'recurring'")
    schedule: str = Field(
        ..., description="Cron expression (recurring) or ISO 8601 datetime (one_time)"
    )
    message: str = Field(..., description="Prompt to send to the AI when job executes")


class ScheduledJobUpdate(BaseModel):
    """Model for updating a scheduled job."""

    message: Optional[str] = Field(None, description="New prompt message")
    schedule: Optional[str] = Field(None, description="New cron expression or ISO 8601 datetime")
    title: Optional[str] = Field(None, description="New job title")


# Default scheduler configuration values
SCHEDULER_DEFAULTS = {
    "enabled": True,
    "timezone": "UTC",
    "check_interval_minutes": 1,
    "max_concurrent_jobs": 10,
    "max_failures_before_pause": 3,
}


@router.get("/scheduler", response_model=APIResponse)
async def get_scheduler_config(request: Request) -> JSONResponse:
    """
    Get complete scheduler configuration. AdminKey only.

    Returns:
        Full scheduler YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    # Get raw config and merge with defaults
    raw_config = formation.config.get("scheduler", {})
    scheduler_config = {**SCHEDULER_DEFAULTS, **raw_config}

    response = create_success_response(
        APIObjectType.SCHEDULER,
        APIEventType.SCHEDULER_RETRIEVED,
        scheduler_config,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/scheduler/jobs", response_model=APIResponse)
async def list_scheduled_jobs(request: Request) -> JSONResponse:
    """
    List scheduled jobs.

    With ClientKey: X-Muxi-User-ID required, returns only user's jobs.
    With AdminKey: X-Muxi-User-ID optional, omit for all jobs.

    Returns:
        List of scheduled jobs with their configuration and status
    """
    request_id = getattr(request.state, "request_id", None)

    # Check auth type and validate user_id requirement
    user_id_filter, is_admin, error_response = _check_auth_and_user_id(request, request_id)
    if error_response:
        return error_response

    scheduler = _get_scheduler_service(request)
    if not scheduler:
        response = create_success_response(
            APIObjectType.SCHEDULED_JOB_LIST,
            APIEventType.SCHEDULER_JOBS_LIST,
            {"jobs": [], "count": 0},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    try:
        if user_id_filter:
            jobs = await scheduler.job_manager.get_all_jobs(user_id=user_id_filter)
        else:
            jobs = await scheduler.job_manager.get_all_jobs()
    except Exception as e:
        from .....services import observability

        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            description=f"Failed to retrieve scheduled jobs: {str(e)}",
            data={"error": str(e), "error_type": type(e).__name__},
        )
        jobs = []

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB_LIST,
        APIEventType.SCHEDULER_JOBS_LIST,
        {"jobs": jobs, "count": len(jobs)},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/scheduler/jobs", response_model=APIResponse)
async def create_scheduled_job(request: Request, job: ScheduledJobCreate) -> JSONResponse:
    """
    Create a new scheduled job. AdminKey only.

    User ID is taken from the request body field, falling back to X-Muxi-User-ID header.

    **Schedule format:**
    - For type=recurring: cron expression (e.g., "0 9 * * 1")
    - For type=one_time: ISO 8601 datetime (e.g., "2025-10-25T14:00:00Z")

    Args:
        job: Job configuration (type, schedule, message, optional user_id)

    Returns:
        Created job with ID and next execution time
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    # Get user_id from header
    user_id = request.headers.get("X-Muxi-User-ID", "0")

    # Validate job type
    if job.type not in ["one_time", "recurring"]:
        response = create_error_response(
            "VALIDATION_ERROR",
            f"Invalid job type '{job.type}'. Must be 'one_time' or 'recurring'",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Validate schedule format based on type
    if job.type == "recurring":
        try:
            base_time = datetime.now(timezone.utc)
            cron = croniter.croniter(job.schedule, base_time)
            cron.get_next(datetime)
        except (
            ValueError,
            KeyError,
            croniter.CroniterBadCronError,
            croniter.CroniterBadDateError,
        ) as e:
            response = create_error_response(
                error_code="VALIDATION_ERROR",
                message="Invalid cron expression for recurring job",
                trace=None,
                request_id=request_id,
                idempotency_key=None,
                data=None,
                error_data={
                    "field": "schedule",
                    "value": job.schedule,
                    "expected": "Valid cron expression (e.g., '0 9 * * 1')",
                    "error": str(e),
                },
            )
            return JSONResponse(content=response.model_dump(), status_code=422)
    else:
        try:
            from dateutil.parser import isoparse

            run_at_dt = isoparse(job.schedule)
            if run_at_dt.tzinfo is None:
                run_at_dt = run_at_dt.replace(tzinfo=timezone.utc)
            if run_at_dt <= datetime.now(timezone.utc):
                response = create_error_response(
                    error_code="VALIDATION_ERROR",
                    message="Schedule datetime must be in the future",
                    trace=None,
                    request_id=request_id,
                    idempotency_key=None,
                    data=None,
                    error_data={
                        "field": "schedule",
                        "value": job.schedule,
                        "expected": "Future ISO 8601 datetime",
                    },
                )
                return JSONResponse(content=response.model_dump(), status_code=422)
        except (ValueError, TypeError) as e:
            response = create_error_response(
                error_code="VALIDATION_ERROR",
                message="Invalid datetime format for one_time job",
                trace=None,
                request_id=request_id,
                idempotency_key=None,
                data=None,
                error_data={
                    "field": "schedule",
                    "value": job.schedule,
                    "expected": "ISO 8601 datetime (e.g., '2025-10-25T14:00:00Z')",
                    "error": str(e),
                },
            )
            return JSONResponse(content=response.model_dump(), status_code=422)

    # Check for persistent memory
    if not formation.has_persistent_memory():
        response = create_error_response(
            error_code="UNPROCESSABLE_ENTITY",
            message="Scheduler jobs require persistent memory",
            trace=None,
            request_id=request_id,
            idempotency_key=None,
            data=None,
            error_data={
                "reason": "Formation has no persistent memory configured",
                "required": "Configure memory.persistent in formation (PostgreSQL or MySQL)",
            },
        )
        return JSONResponse(content=response.model_dump(), status_code=422)

    scheduler = _get_scheduler_service(request)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        scheduled_for = None
        if job.type == "one_time":
            from dateutil.parser import isoparse as _isoparse

            dt = _isoparse(job.schedule)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            scheduled_for = dt

        job_id = await scheduler.job_manager.create_job(
            user_id=user_id,
            title=job.message[:80],
            original_prompt=job.message,
            execution_prompt=job.message,
            cron_expression=job.schedule if job.type == "recurring" else None,
            scheduled_for=scheduled_for,
            is_recurring=(job.type == "recurring"),
        )
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to create scheduled job: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    # Retrieve the created job to return full data
    job_data = await scheduler.job_manager.get_job(job_id)
    if not job_data:
        job_data = {"id": job_id, "type": job.type, "schedule": job.schedule, "message": job.message}

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB,
        APIEventType.SCHEDULER_JOB_CREATED,
        job_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=201)


@router.get("/scheduler/jobs/{job_id}", response_model=APIResponse)
async def get_scheduled_job(request: Request, job_id: str) -> JSONResponse:
    """
    Get details for a specific scheduled job. AdminKey only.

    Args:
        job_id: ID of the scheduled job

    Returns:
        Job details including configuration, status, and execution history
    """
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    scheduler = _get_scheduler_service(request)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        job_data = await scheduler.job_manager.get_job(job_id)
    except Exception as e:
        from .....services import observability

        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            description=f"Failed to retrieve scheduled job: {str(e)}",
            data={"job_id": job_id, "error": str(e)},
        )
        job_data = None

    if not job_data:
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Scheduled job '{job_id}' not found",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB,
        APIEventType.SCHEDULER_JOB_RETRIEVED,
        job_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.put("/scheduler/jobs/{job_id}", response_model=APIResponse)
async def update_scheduled_job(
    request: Request, job_id: str, update: ScheduledJobUpdate
) -> JSONResponse:
    """
    Update a scheduled job's message, schedule, or title. AdminKey only.

    Args:
        job_id: ID of the scheduled job
        update: Fields to update

    Returns:
        Updated job data
    """
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    user_id = request.headers.get("X-Muxi-User-ID", "0")

    scheduler = _get_scheduler_service(request)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Verify job exists
    existing = await scheduler.job_manager.get_job(job_id)
    if not existing:
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Scheduled job '{job_id}' not found",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    try:
        result_id, action = await scheduler.job_manager.update_or_replace_job(
            job_id=job_id,
            user_id=user_id,
            new_prompt=update.message,
            new_title=update.title,
            new_schedule=update.schedule,
        )
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to update scheduled job: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    job_data = await scheduler.job_manager.get_job(result_id)
    if not job_data:
        job_data = {"id": result_id, "action": action}

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB,
        APIEventType.SCHEDULER_JOB_UPDATED,
        job_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/scheduler/jobs/{job_id}/pause", response_model=APIResponse)
async def pause_scheduled_job(request: Request, job_id: str) -> JSONResponse:
    """
    Pause a scheduled job. AdminKey only.

    Args:
        job_id: ID of the scheduled job to pause

    Returns:
        Success response
    """
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    user_id = request.headers.get("X-Muxi-User-ID", "0")

    scheduler = _get_scheduler_service(request)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        success = await scheduler.pause_job(job_id, user_id=user_id)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to pause scheduled job: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    if not success:
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Scheduled job '{job_id}' not found or not in ACTIVE state",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB,
        APIEventType.SCHEDULER_JOB_PAUSED,
        {"id": job_id, "status": "PAUSED"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/scheduler/jobs/{job_id}/resume", response_model=APIResponse)
async def resume_scheduled_job(request: Request, job_id: str) -> JSONResponse:
    """
    Resume a paused scheduled job. AdminKey only.

    Args:
        job_id: ID of the scheduled job to resume

    Returns:
        Success response
    """
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    user_id = request.headers.get("X-Muxi-User-ID", "0")

    scheduler = _get_scheduler_service(request)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        success = await scheduler.resume_job(job_id, user_id=user_id)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to resume scheduled job: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    if not success:
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Scheduled job '{job_id}' not found or not in PAUSED state",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB,
        APIEventType.SCHEDULER_JOB_RESUMED,
        {"id": job_id, "status": "ACTIVE"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/scheduler/jobs/{job_id}", response_model=APIResponse)
async def remove_scheduled_job(request: Request, job_id: str) -> JSONResponse:
    """
    Remove a scheduled job. AdminKey only.

    Args:
        job_id: ID of the scheduled job to remove

    Returns:
        Success response
    """
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    user_id = request.headers.get("X-Muxi-User-ID", "0")

    scheduler = _get_scheduler_service(request)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        success = await scheduler.delete_job(job_id, user_id=user_id)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to remove scheduled job: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    if not success:
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Scheduled job '{job_id}' not found",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.MESSAGE,
        APIEventType.SCHEDULER_JOB_DELETED,
        {"message": f"Scheduled job '{job_id}' removed successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
