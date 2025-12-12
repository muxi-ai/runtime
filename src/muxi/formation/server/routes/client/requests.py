"""
Request tracking and management endpoints for users.

These endpoints provide request status, listing, and cancellation,
requiring client API key authentication.
"""

from typing import Optional

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_error_response,
    create_success_response,
)
from .....datatypes.api import APIObjectType, APIEventType

router = APIRouter(tags=["Requests"])


def _get_user_id(x_user_id: Optional[str], api_request_id: Optional[str]) -> tuple[Optional[str], Optional[JSONResponse]]:
    """Extract and validate user_id from X-Muxi-User-ID header."""
    if not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required",
            None,
            api_request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=400)
    return x_user_id, None


@router.get("/requests", response_model=APIResponse)
async def list_requests(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    List requests for a user.

    Args:
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        List of request details
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    api_request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, api_request_id)
    if error_response:
        return error_response

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, api_request_id
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
    requests_list = []
    for req_id, state in user_requests.items():
        request_data = {
            "request_id": req_id,
            "status": state.status.value,
            "progress": state.progress,
            "created_at": state.get_created_timestamp(),
            "completed_at": state.end_time,
        }
        # Only include error if present
        if state.error:
            request_data["error"] = state.error
        requests_list.append(request_data)

    response = create_success_response(
        APIObjectType.REQUEST_LIST,
        APIEventType.REQUEST_LIST_RETRIEVED,
        {"requests": requests_list, "count": len(requests_list)},
        api_request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


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


@router.delete("/requests/{request_id}", response_model=APIResponse)
async def cancel_request(
    request: Request,
    request_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Cancel an in-progress request.

    Args:
        request_id: Request ID to cancel
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Success response
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    api_request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, api_request_id)
    if error_response:
        return error_response

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Normalize user_id to "0" for single-user mode (same as chat())
    if not getattr(overlord, "is_multi_user", False):
        user_id = "0"

    # Verify request exists and belongs to user (security check)
    request_state = await overlord.request_tracker.get_request(request_id)
    if not request_state:
        response = create_error_response(
            "NOT_FOUND", f"Request {request_id} not found", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    if request_state.user_id != user_id:
        response = create_error_response(
            "FORBIDDEN", "Request does not belong to this user", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=403)

    # Cancel the request
    result = await overlord.cancel_request(request_id)

    if result["success"]:
        response = create_success_response(
            APIObjectType.REQUEST_STATUS,
            APIEventType.REQUEST_CANCELLED,
            {"request_id": request_id, "status": "cancelled", "message": "Request cancelled"},
            api_request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)
    else:
        response = create_error_response(
            "OPERATION_FAILED", result["message"], None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)
