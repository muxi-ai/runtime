"""
Request tracking and management endpoints.

These endpoints provide request status, listing, and cancellation.
Supports both ClientKey and AdminKey authentication:
- ClientKey: X-Muxi-User-ID header required (returns only user's requests)
- AdminKey: X-Muxi-User-ID header optional (omit for all, provide to filter)
"""

import secrets
from typing import Optional, Tuple

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from .....datatypes.api import APIEventType, APIObjectType
from ....background.request_tracker import RequestStatus
from ...responses import (
    APIResponse,
    create_error_response,
    create_success_response,
)

router = APIRouter(tags=["Requests"])

# A request in one of these states has already run to its end: neither the
# cooperative cancellation flag nor asyncio task cancellation can affect it.
# CANCELLED is deliberately absent -- re-cancelling is a no-op, not a failure.
_UNCANCELLABLE_STATUSES = frozenset({RequestStatus.COMPLETED, RequestStatus.FAILED})


def _check_auth_and_user_id(
    request: Request,
    x_user_id: Optional[str],
    api_request_id: Optional[str],
) -> Tuple[Optional[str], bool, Optional[JSONResponse]]:
    """
    Check authentication type and validate user_id requirement.

    Returns:
        Tuple of (user_id, is_admin, error_response)
        - user_id: The user ID (may be None for admin without filter)
        - is_admin: True if admin key was used
        - error_response: JSONResponse if validation failed, None otherwise
    """
    formation = request.app.state.formation

    # Get keys from formation config
    # Get keys from formation._api_keys (where they're actually stored)
    api_keys = getattr(formation, "_api_keys", {})
    admin_key = api_keys.get("admin", "")
    client_key = api_keys.get("client", "")

    # Check which auth was used
    provided_admin_key = request.headers.get("x-muxi-admin-key")
    provided_client_key = request.headers.get("x-muxi-client-key")

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
        # Auth should have been validated by middleware, but just in case
        response = create_error_response(
            "UNAUTHORIZED",
            "Valid API key required",
            None,
            api_request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=401)

    # For client auth, user_id is required
    if not is_admin and not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required when using client API key",
            None,
            api_request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=400)

    return x_user_id, is_admin, None


@router.get("/requests", response_model=APIResponse, operation_id="list_requests")
async def list_requests(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    List requests.

    With ClientKey: X-Muxi-User-ID required, returns only user's requests.
    With AdminKey: X-Muxi-User-ID optional, omit for all requests.

    Returns:
        List of request details
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    api_request_id = getattr(request.state, "request_id", None)

    # Check auth type and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, api_request_id)
    if error_response:
        return error_response

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Normalize user_id to "0" for single-user mode (same as chat())
    if user_id and not getattr(overlord, "is_multi_user", False):
        user_id = "0"

    # Get all requests
    all_requests = await overlord.request_tracker.get_all_requests()

    # Filter by user_id if provided (required for client, optional for admin)
    if user_id:
        filtered_requests = {
            req_id: state for req_id, state in all_requests.items() if state.user_id == user_id
        }
    else:
        # Admin without user filter - return all
        filtered_requests = all_requests

    # Convert RequestState objects to API response format
    requests_list = []
    for req_id, state in filtered_requests.items():
        request_data = {
            "request_id": req_id,
            "user_id": state.user_id,
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


@router.get("/requests/{request_id}", response_model=APIResponse, operation_id="get_request_status")
async def get_request_status(
    request: Request,
    request_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Get status of a request (active or completed within retention period).

    With ClientKey: X-Muxi-User-ID required, only returns if request belongs to user.
    With AdminKey: X-Muxi-User-ID optional, can access any request.

    Returns:
        Request status information
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    api_request_id = getattr(request.state, "request_id", None)

    # Check auth type and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, api_request_id)
    if error_response:
        return error_response

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Normalize user_id to "0" for single-user mode (same as chat())
    if user_id and not getattr(overlord, "is_multi_user", False):
        user_id = "0"

    # Get request state from tracker
    request_state = await overlord.request_tracker.get_request(request_id)

    if not request_state:
        response = create_error_response(
            "REQUEST_NOT_FOUND", "Request not found", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Verify request belongs to user (only for client auth with user_id)
    if user_id and request_state.user_id != user_id:
        response = create_error_response(
            "FORBIDDEN", "Request does not belong to this user", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=403)

    # Build response data
    data = {
        "request_id": request_id,
        "user_id": request_state.user_id,
        "status": request_state.status.value,
        "progress": request_state.progress,
        "created_at": request_state.get_created_timestamp(),
    }

    if request_state.end_time:
        data["completed_at"] = request_state.end_time

    if request_state.error:
        data["error"] = request_state.error

    # Include result for completed requests so clients can poll for it
    if request_state.status == RequestStatus.COMPLETED and request_state.result is not None:
        result = request_state.result
        if hasattr(result, "content"):
            data["result"] = str(result.content)
        elif isinstance(result, dict):
            data["result"] = result
        else:
            data["result"] = str(result)

    response = create_success_response(
        APIObjectType.REQUEST_STATUS,
        APIEventType.REQUEST_STATUS_RETRIEVED,
        data,
        api_request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/requests/{request_id}", response_model=APIResponse, operation_id="cancel_request")
async def cancel_request(
    request: Request,
    request_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Cancel an in-progress request.

    With ClientKey: X-Muxi-User-ID required, can only cancel own requests.
    With AdminKey: X-Muxi-User-ID optional, can cancel any request.

    Returns:
        Success response
    """
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    api_request_id = getattr(request.state, "request_id", None)

    # Check auth type and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, api_request_id)
    if error_response:
        return error_response

    if not overlord:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord service not available", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Normalize user_id to "0" for single-user mode (same as chat())
    if user_id and not getattr(overlord, "is_multi_user", False):
        user_id = "0"

    # Verify request exists
    request_state = await overlord.request_tracker.get_request(request_id)
    if not request_state:
        response = create_error_response(
            "NOT_FOUND", f"Request {request_id} not found", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Verify request belongs to user (only for client auth with user_id)
    if user_id and request_state.user_id != user_id:
        response = create_error_response(
            "FORBIDDEN", "Request does not belong to this user", None, api_request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=403)

    # Nothing to cancel once the request has finished -- report that honestly
    if request_state.status in _UNCANCELLABLE_STATUSES:
        response = create_error_response(
            "OPERATION_FAILED",
            f"Cannot cancel request {request_id}: already {request_state.status.value}",
            None,
            api_request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Mark for cooperative cancellation (checkpoints will check this)
    await overlord.request_tracker.mark_cancelled(request_id)

    # Also try asyncio task cancellation. Only background workflow executions
    # carry a task_ref, so this succeeds for those alone -- a normal chat turn
    # relies entirely on the cooperative flag set above and stops at its next
    # checkpoint. Either way the cancellation has taken effect.
    result = await overlord.cancel_request(request_id)
    immediate = bool(result.get("success"))

    response = create_success_response(
        APIObjectType.REQUEST_STATUS,
        APIEventType.REQUEST_CANCELLED,
        {
            "request_id": request_id,
            "status": "cancelled",
            "cancellation": "immediate" if immediate else "cooperative",
            "message": (
                "Request cancelled"
                if immediate
                else "Request marked for cancellation; it will stop at the next checkpoint"
            ),
        },
        api_request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
