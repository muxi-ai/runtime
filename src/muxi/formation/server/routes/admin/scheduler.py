"""
Scheduler configuration endpoints.

These endpoints provide scheduler configuration access and job management,
requiring admin API key authentication.
"""

from typing import Dict, Any, List, Optional
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

router = APIRouter(tags=["Scheduler"])


class SchedulerUpdate(BaseModel):
    """Model for updating scheduler configuration."""

    enabled: bool = True
    timezone: str = "UTC"
    jobs: List[Dict[str, Any]] = []


class ScheduledJobCreate(BaseModel):
    """Model for creating a scheduled job."""

    type: str = Field(default="one_time", description="Job type: one_time or recurring")
    schedule: Optional[str] = Field(default=None, description="Cron expression for recurring jobs")
    run_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp for one_time jobs")
    message: str = Field(..., description="Message to send when job executes")
    user_id: str = Field(..., description="User ID for job execution context")
    session_id: Optional[str] = Field(default=None, description="Optional session ID")
    enabled: bool = Field(default=True, description="Whether job is enabled")


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
        APIObjectType.SCHEDULER,
        APIEventType.SCHEDULER_RETRIEVED,
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
        APIObjectType.SCHEDULER, APIEventType.SCHEDULER_UPDATED, scheduler_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/scheduler/jobs", response_model=APIResponse)
async def list_scheduled_jobs(request: Request) -> JSONResponse:
    """
    List all scheduled jobs.

    Returns:
        List of all scheduled jobs with their configuration and status
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

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
    Create a new scheduled job.

    **Database Storage**: Scheduler jobs are stored in the database and require
    persistent memory (PostgreSQL or MySQL). Returns 422 error if formation uses
    SQLite or no persistent memory.

    Args:
        job: Job configuration (one-time or recurring)

    Returns:
        Created job with ID and next execution time
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check for persistent memory (non-SQLite database required)
    if not formation.has_persistent_memory():
        response = create_error_response(
            error_code="UNPROCESSABLE_ENTITY",
            message="Scheduler jobs require persistent memory (non-SQLite database)",
            trace=None,
            request_id=request_id,
            idempotency_key=None,
            data=None,
            error_data={
                "reason": "Formation has no persistent memory configured",
                "required": "PostgreSQL or MySQL for scheduler job persistence",
                "current_memory_type": "none",
            },
        )
        return JSONResponse(content=response.model_dump(), status_code=422)

    # Check if using SQLite (not suitable for persistent jobs)
    is_multi_user = getattr(formation, "_is_multi_user", False)
    if not is_multi_user:
        # SQLite is detected - not suitable for scheduler jobs
        response = create_error_response(
            error_code="UNPROCESSABLE_ENTITY",
            message="Scheduler jobs require persistent memory (non-SQLite database)",
            trace=None,
            request_id=request_id,
            idempotency_key=None,
            data=None,
            error_data={
                "reason": "Formation is using SQLite or no persistent memory",
                "required": "PostgreSQL or MySQL for scheduler job persistence",
                "current_memory_type": "sqlite",
            },
        )
        return JSONResponse(content=response.model_dump(), status_code=422)

    # Validate job type
    if job.type not in ["one_time", "recurring"]:
        response = create_error_response(
            "INVALID_REQUEST",
            f"Invalid job type '{job.type}'. Must be 'one_time' or 'recurring'",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Validate required fields based on type
    if job.type == "recurring" and not job.schedule:
        response = create_error_response(
            "INVALID_REQUEST",
            "Field 'schedule' (cron expression) is required for recurring jobs",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    if job.type == "one_time" and not job.run_at:
        response = create_error_response(
            "INVALID_REQUEST",
            "Field 'run_at' (ISO 8601 timestamp) is required for one_time jobs",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

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
        "message": job.message,
        "user_id": job.user_id,
        "session_id": job.session_id,
        "enabled": job.enabled,
    }

    if job.type == "recurring":
        job_data["schedule"] = job.schedule
    else:
        job_data["run_at"] = job.run_at

    # Add job to scheduler
    try:
        if hasattr(scheduler, "add_job"):
            scheduler.add_job(job_id, job_data)
        else:
            # Fallback: add to jobs dict directly
            if not hasattr(scheduler, "jobs"):
                scheduler.jobs = {}
            scheduler.jobs[job_id] = job_data

        # Calculate next run time
        next_run = None
        if job.type == "recurring":
            # Calculate next run from cron expression using croniter
            try:
                base_time = datetime.now(timezone.utc)
                cron = croniter.croniter(job.schedule, base_time)
                next_run_dt = cron.get_next(datetime)
                # Convert to ISO 8601 UTC string
                next_run = next_run_dt.astimezone(timezone.utc).isoformat()
            except (ValueError, KeyError, croniter.CroniterBadCronError, croniter.CroniterBadDateError) as e:
                # Invalid cron expression - log and set to None
                from .....services import observability
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    description=f"Invalid cron expression '{job.schedule}': {str(e)}",
                    data={
                        "job_id": job_id,
                        "schedule": job.schedule,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                next_run = None  # Will need manual intervention
        else:
            next_run = job.run_at

        job_data["next_run"] = next_run

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
    Get details for a specific scheduled job.

    Args:
        job_id: ID of the scheduled job

    Returns:
        Job details including configuration, status, and execution history
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

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
    Remove a scheduled job.

    Args:
        job_id: ID of the scheduled job to remove

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

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
