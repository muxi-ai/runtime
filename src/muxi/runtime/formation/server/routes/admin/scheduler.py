"""
Scheduler configuration endpoints.

These endpoints provide scheduler configuration access and job management.
GET /scheduler/jobs supports both ClientKey and AdminKey:
- ClientKey: X-Muxi-User-ID required (returns only user's jobs)
- AdminKey: X-Muxi-User-ID optional (omit for all, provide to filter)
"""

import secrets
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

import croniter

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType


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
    elif provided_client_key and client_key and secrets.compare_digest(provided_client_key, client_key):
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

router = APIRouter(tags=["Scheduler"])


class SchedulerUpdate(BaseModel):
    """Model for updating scheduler configuration."""

    enabled: bool = True
    timezone: str = "UTC"
    jobs: List[Dict[str, Any]] = []


class ScheduledJobCreate(BaseModel):
    """Model for creating a scheduled job."""

    type: str = Field(..., description="Job type: 'one_time' or 'recurring'")
    schedule: str = Field(..., description="Cron expression (recurring) or ISO 8601 datetime (one_time)")
    message: str = Field(..., description="Prompt to send to the AI when job executes")


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


# @router.patch("/scheduler", response_model=APIResponse)  # DEPRECATED: Use deployment instead
def update_scheduler(request: Request, config: SchedulerUpdate) -> JSONResponse:
    """
    Update scheduler configuration.

    DEPRECATED: Scheduler configuration should be changed via formation YAML and redeployment.

    Args:
        config: New scheduler configuration

    Returns:
        Updated scheduler configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Update in-memory configuration (ephemeral - lost on restart)
    scheduler_config = formation.config.setdefault("scheduler", {})
    
    # Update only fields that were explicitly provided by the client
    # Using exclude_unset=True to avoid overwriting with default values
    for key, value in config.dict(exclude_unset=True).items():
        scheduler_config[key] = value

    response = create_success_response(
        APIObjectType.SCHEDULER, APIEventType.SCHEDULER_UPDATED, scheduler_config, request_id
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
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth type and validate user_id requirement
    user_id_filter, is_admin, error_response = _check_auth_and_user_id(request, request_id)
    if error_response:
        return error_response

    # Get scheduler service
    scheduler = getattr(formation, "_scheduler", None)
    if not scheduler:
        response = create_success_response(
            APIObjectType.SCHEDULED_JOB_LIST,
            APIEventType.SCHEDULER_JOBS_LIST,
            {"jobs": [], "count": 0},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    # Get all jobs from scheduler
    jobs = []
    try:
        if hasattr(scheduler, "get_all_jobs"):
            jobs = scheduler.get_all_jobs()
        elif hasattr(scheduler, "jobs"):
            # Fallback: access jobs dict directly
            jobs_dict = scheduler.jobs if hasattr(scheduler, "jobs") else {}
            for job_id, job_data in jobs_dict.items():
                jobs.append({
                    "id": job_id,
                    "type": job_data.get("type", "one_time"),
                    "schedule": job_data.get("schedule"),
                    "run_at": job_data.get("run_at"),
                    "message": job_data.get("message", ""),
                    "user_id": job_data.get("user_id", "0"),
                    "session_id": job_data.get("session_id"),
                    "enabled": job_data.get("enabled", True),
                    "next_run": job_data.get("next_run"),
                    "last_run": job_data.get("last_run"),
                    "failure_count": job_data.get("failure_count", 0),
                })
    except Exception as e:
        # Log error but return empty list
        from .....services import observability
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            description=f"Failed to retrieve scheduled jobs: {str(e)}",
            data={"error": str(e), "error_type": type(e).__name__},
        )

    # Filter by user_id if header provided
    if user_id_filter:
        jobs = [job for job in jobs if job.get("user_id") == user_id_filter]

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB_LIST,
        APIEventType.SCHEDULER_JOBS_LIST,
        {"jobs": jobs, "count": len(jobs)},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/scheduler/jobs", response_model=APIResponse)
def create_scheduled_job(request: Request, job: ScheduledJobCreate) -> JSONResponse:
    """
    Create a new scheduled job. AdminKey only.

    User ID is taken from X-Muxi-User-ID header.

    **Schedule format:**
    - For type=recurring: cron expression (e.g., "0 9 * * 1")
    - For type=one_time: ISO 8601 datetime (e.g., "2025-10-25T14:00:00Z")

    **Database Storage**: Scheduler jobs are stored in the database and require
    persistent memory (PostgreSQL or MySQL). Returns 422 error if formation uses
    SQLite or no persistent memory.

    Args:
        job: Job configuration (type, schedule, message)

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
        # Validate cron expression
        try:
            base_time = datetime.now(timezone.utc)
            cron = croniter.croniter(job.schedule, base_time)
            next_run_dt = cron.get_next(datetime)
            next_run = next_run_dt.astimezone(timezone.utc).isoformat()
        except (ValueError, KeyError, croniter.CroniterBadCronError, croniter.CroniterBadDateError) as e:
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
        # Validate ISO 8601 datetime for one_time jobs
        try:
            from dateutil.parser import isoparse
            run_at_dt = isoparse(job.schedule)
            # Ensure timezone aware
            if run_at_dt.tzinfo is None:
                run_at_dt = run_at_dt.replace(tzinfo=timezone.utc)
            # Check if in the future
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
            next_run = run_at_dt.isoformat()
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

    # Check for persistent memory (SQLite or PostgreSQL/MySQL)
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
                "required": "Configure memory.persistent in formation (SQLite, PostgreSQL, or MySQL)",
            },
        )
        return JSONResponse(content=response.model_dump(), status_code=422)

    # Get scheduler service
    scheduler = getattr(formation, "_scheduler", None)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Generate job ID
    from .....utils.id_generator import generate_request_id
    job_id = f"job_{generate_request_id()[4:]}"  # Remove 'req_' prefix

    # Create job data
    job_data = {
        "id": job_id,
        "type": job.type,
        "schedule": job.schedule,
        "message": job.message,
        "user_id": user_id,
        "next_run": next_run,
    }

    # Add job to scheduler
    try:
        if hasattr(scheduler, "add_job"):
            scheduler.add_job(job_id, job_data)
        else:
            # Fallback: add to jobs dict directly
            if not hasattr(scheduler, "jobs"):
                scheduler.jobs = {}
            scheduler.jobs[job_id] = job_data

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to create scheduled job: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    response = create_success_response(
        APIObjectType.SCHEDULED_JOB,
        APIEventType.SCHEDULER_JOB_CREATED,
        job_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=201)


@router.get("/scheduler/jobs/{job_id}", response_model=APIResponse)
def get_scheduled_job(request: Request, job_id: str) -> JSONResponse:
    """
    Get details for a specific scheduled job. AdminKey only.

    Args:
        job_id: ID of the scheduled job

    Returns:
        Job details including configuration, status, and execution history
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    # Get scheduler service
    scheduler = getattr(formation, "_scheduler", None)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get job from scheduler
    job_data = None
    try:
        if hasattr(scheduler, "get_job"):
            job_data = scheduler.get_job(job_id)
        elif hasattr(scheduler, "jobs"):
            job_data = scheduler.jobs.get(job_id)
    except Exception as e:
        from .....services import observability
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            description=f"Failed to retrieve scheduled job: {str(e)}",
            data={"job_id": job_id, "error": str(e)},
        )

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


@router.delete("/scheduler/jobs/{job_id}", response_model=APIResponse)
def remove_scheduled_job(request: Request, job_id: str) -> JSONResponse:
    """
    Remove a scheduled job. AdminKey only.

    Args:
        job_id: ID of the scheduled job to remove

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Require AdminKey
    error_response = _require_admin_key(request, request_id)
    if error_response:
        return error_response

    # Get scheduler service
    scheduler = getattr(formation, "_scheduler", None)
    if not scheduler:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Scheduler is not available or not enabled",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Remove job from scheduler
    try:
        if hasattr(scheduler, "remove_job"):
            removed = scheduler.remove_job(job_id)
            if not removed:
                response = create_error_response(
                    "RESOURCE_NOT_FOUND",
                    f"Scheduled job '{job_id}' not found",
                    None,
                    request_id,
                )
                return JSONResponse(content=response.model_dump(), status_code=404)
        elif hasattr(scheduler, "jobs"):
            if job_id not in scheduler.jobs:
                response = create_error_response(
                    "RESOURCE_NOT_FOUND",
                    f"Scheduled job '{job_id}' not found",
                    None,
                    request_id,
                )
                return JSONResponse(content=response.model_dump(), status_code=404)
            del scheduler.jobs[job_id]
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to remove scheduled job: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    response = create_success_response(
        APIObjectType.MESSAGE,
        APIEventType.SCHEDULER_JOB_DELETED,
        {"message": f"Scheduled job '{job_id}' removed successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
