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
    # formation = request.app.state.formation  # TODO: Use when implementing job tracking
    request_id = getattr(request.state, "request_id", None)

    # TODO: Get jobs from request tracker
    # Using spec-compliant format for client endpoints
    response = job_list_response([], request_id, use_generic_type=True)
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
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement job cancellation
    response = create_error_response(
        "NOT_IMPLEMENTED", "Job cancellation not yet implemented", None, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=501)
