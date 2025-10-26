"""
Job management endpoints for users.

These endpoints provide job tracking and cancellation,
requiring client API key authentication.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    job_list_response,
    create_error_response,
)

router = APIRouter(tags=["Jobs"])


@router.get("/jobs/{user_id}", response_model=APIResponse)
async def list_user_jobs(request: Request, user_id: str) -> JSONResponse:
    """
    List async jobs for a user.

    Args:
        user_id: User ID to get jobs for

    Returns:
        List of job details
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    request_id = getattr(request.state, "request_id", None)

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get all requests and filter by user_id
    all_requests = await overlord.request_tracker.get_all_requests()
    user_requests = {
        req_id: state for req_id, state in all_requests.items()
        if state.user_id == user_id
    }

    # Convert RequestState objects to API response format
    jobs = []
    for req_id, state in user_requests.items():
        job_data = {
            "id": req_id,
            "status": state.status.value,
            "progress": state.progress,
            "created_at": state.created_at if hasattr(state, 'created_at') else state.start_time,
            "completed_at": state.end_time,
        }
        # Only include error if present
        if state.error:
            job_data["error"] = state.error
        jobs.append(job_data)

    # Using spec-compliant format for client endpoints
    response = job_list_response(jobs, request_id, use_generic_type=True)
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/jobs/{user_id}/{job_id}", response_model=APIResponse)
async def cancel_job(request: Request, user_id: str, job_id: str) -> JSONResponse:
    """
    Cancel or delete an async job.

    Args:
        user_id: User ID who owns the job
        job_id: Job ID to cancel

    Returns:
        Success response
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    request_id = getattr(request.state, "request_id", None)

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Verify job exists and belongs to user (security check)
    job_state = await overlord.request_tracker.get_request(job_id)
    if not job_state:
        response = create_error_response(
            "NOT_FOUND", f"Job {job_id} not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    if job_state.user_id != user_id:
        response = create_error_response(
            "FORBIDDEN", "Job does not belong to this user", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=403)

    # Cancel the job
    result = await overlord.cancel_request(job_id)

    if result["success"]:
        from ...responses import create_success_response
        from .....datatypes.api import APIObjectType, APIEventType
        response = create_success_response(
            APIObjectType.JOB, APIEventType.JOB_CANCELLED, result, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=200)
    else:
        response = create_error_response(
            "OPERATION_FAILED", result["message"], None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)
