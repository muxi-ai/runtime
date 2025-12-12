"""
Job and request management endpoints for users.

These endpoints provide job tracking, request status, and cancellation,
requiring client API key authentication.
"""

from typing import Optional

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    job_list_response,
    create_error_response,
    create_success_response,
)
from .....datatypes.api import APIObjectType, APIEventType

router = APIRouter(tags=["Jobs"])


def _get_user_id(x_user_id: Optional[str], request_id: Optional[str]) -> tuple[Optional[str], Optional[JSONResponse]]:
    """Extract and validate user_id from X-Muxi-User-ID header."""
    if not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=400)
    return x_user_id, None


@router.get("/requests/{request_id}", response_model=APIResponse)
async def get_request_status(request: Request, request_id: str) -> JSONResponse:
    """
    Get status of any request (active or completed within retention period).

    Args:
        request_id: Unique identifier of the request

    Returns:
        Request status information
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    api_request_id = getattr(request.state, "request_id", None)

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get request state from tracker
    request_state = await overlord.request_tracker.get_request(request_id)

    if not request_state:
        response = create_error_response(
            "REQUEST_NOT_FOUND", "Request not found", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Build response data
    data = {
        "request_id": request_id,
        "status": request_state.status.value,
        "progress": request_state.progress,
        "created_at": request_state.get_created_timestamp(),
    }

    if request_state.end_time:
        data["completed_at"] = request_state.end_time

    if request_state.error:
        data["error"] = request_state.error

    response = create_success_response(
        APIObjectType.REQUEST_STATUS,
        APIEventType.REQUEST_STATUS_RETRIEVED,
        data,
        api_request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/jobs", response_model=APIResponse)
async def list_user_jobs(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    List async jobs for a user.

    Args:
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        List of job details
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Normalize user_id to "0" for single-user mode (same as chat())
    if not getattr(overlord, "is_multi_user", False):
        user_id = "0"

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
            "created_at": state.get_created_timestamp(),
            "completed_at": state.end_time,
        }
        # Only include error if present
        if state.error:
            job_data["error"] = state.error
        jobs.append(job_data)

    # Using spec-compliant format for client endpoints
    response = job_list_response(jobs, request_id, use_generic_type=True)
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/jobs/{job_id}", response_model=APIResponse)
async def cancel_job(
    request: Request,
    job_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Cancel or delete an async job.

    Args:
        job_id: Job ID to cancel
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Success response
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Normalize user_id to "0" for single-user mode (same as chat())
    if not getattr(overlord, "is_multi_user", False):
        user_id = "0"

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
        response = create_success_response(
            APIObjectType.JOB, APIEventType.JOB_CANCELLED, result, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=200)
    else:
        response = create_error_response(
            "OPERATION_FAILED", result["message"], None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)
