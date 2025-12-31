"""
Event streaming endpoints.

These endpoints provide SSE streams for user-facing events.
Supports both ClientKey and AdminKey authentication:
- ClientKey: X-Muxi-User-ID required (user's events only)
- AdminKey: X-Muxi-User-ID optional (omit for all, provide to filter)
"""

import asyncio
import json
import secrets
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse

from ...responses import create_error_response

router = APIRouter(tags=["Events"])


def _check_auth_and_user_id(
    request: Request,
    x_user_id: Optional[str],
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
            None,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=401)

    if not is_admin and not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required when using client API key",
            None,
            None,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=400)

    return x_user_id, is_admin, None


@router.get("/events")
async def user_events(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
):
    """
    SSE stream of user-facing events.

    With ClientKey: X-Muxi-User-ID required (streams only user's events)
    With AdminKey: X-Muxi-User-ID optional (omit for all events, provide to filter)

    Returns:
        Server-sent event stream
    """
    # Check auth and validate user_id requirement
    user_id_filter, is_admin, error_response = _check_auth_and_user_id(request, x_user_id)
    if error_response:
        return error_response

    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)

    # Normalize user_id to "0" for single-user mode (only if user_id provided)
    if user_id_filter:
        user_id = "0" if overlord and not getattr(overlord, "is_multi_user", False) else user_id_filter
    else:
        user_id = None  # Admin without filter - all events

    if not overlord:
        raise HTTPException(
            status_code=503,
            detail="Overlord service not available"
        )

    # Get observability manager
    observability_manager = overlord.observability_manager if hasattr(overlord, 'observability_manager') else None

    if not observability_manager or not hasattr(observability_manager, 'subscribe'):
        raise HTTPException(
            status_code=503,
            detail="Live event streaming not available - observability manager not configured"
        )

    async def event_generator():
        try:
            # Subscribe to observability event stream
            # Only stream user-facing events (not internal system events)
            filters = {}
            if user_id:
                filters["user_id"] = user_id

            async for event in observability_manager.subscribe(filters):
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                # Only send user-facing events (filter out internal system events)
                event_type = event.get("event_type", "")
                if event_type.startswith(("chat.", "agent.", "workflow.", "task.")):
                    # Format event for user consumption (simplified)
                    event_data = {
                        "type": event_type,
                        "timestamp": event.get("timestamp"),
                        "message": event.get("description"),
                        "session_id": event.get("session_id"),
                        "request_id": event.get("request_id"),
                    }

                    yield f"data: {json.dumps(event_data)}\\n\\n"

        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception:
            # Send error event to client
            error_event = {
                "error": True,
                "message": "Streaming error occurred",
            }
            yield f"data: {json.dumps(error_event)}\\n\\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/events/{session_id}")
async def session_events(
    request: Request,
    session_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
):
    """
    SSE stream of events for a specific session.

    With ClientKey: X-Muxi-User-ID required, session must belong to user
    With AdminKey: X-Muxi-User-ID optional, can access any session

    Returns:
        Server-sent event stream for the session
    """
    # Check auth and validate user_id requirement
    user_id_filter, is_admin, error_response = _check_auth_and_user_id(request, x_user_id)
    if error_response:
        return error_response

    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)

    # Normalize user_id to "0" for single-user mode (only if user_id provided)
    if user_id_filter:
        user_id = "0" if overlord and not getattr(overlord, "is_multi_user", False) else user_id_filter
    else:
        user_id = None  # Admin without filter

    if not overlord:
        raise HTTPException(status_code=503, detail="Overlord service not available")

    # Get observability manager
    observability_manager = overlord.observability_manager if hasattr(overlord, 'observability_manager') else None

    if not observability_manager or not hasattr(observability_manager, 'subscribe'):
        raise HTTPException(
            status_code=503,
            detail="Live event streaming not available - observability manager not configured"
        )

    async def event_generator():
        try:
            # Subscribe to observability event stream filtered by session
            filters = {"session_id": session_id}
            if user_id:
                filters["user_id"] = user_id

            async for event in observability_manager.subscribe(filters):
                if await request.is_disconnected():
                    break

                event_type = event.get("event_type", "")
                if event_type.startswith(("chat.", "agent.", "workflow.", "task.")):
                    event_data = {
                        "type": event_type,
                        "timestamp": event.get("timestamp"),
                        "message": event.get("description"),
                        "session_id": event.get("session_id"),
                        "request_id": event.get("request_id"),
                    }
                    yield f"data: {json.dumps(event_data)}\\n\\n"

        except asyncio.CancelledError:
            pass
        except Exception:
            error_event = {"error": True, "message": "Streaming error occurred"}
            yield f"data: {json.dumps(error_event)}\\n\\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/events/{session_id}/{request_id}")
async def request_events(
    request: Request,
    session_id: str,
    request_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
):
    """
    SSE stream for events on a specific request.

    With ClientKey: X-Muxi-User-ID required, request must belong to user
    With AdminKey: X-Muxi-User-ID optional, can access any request

    Includes stream lifecycle events (open/completed), tokens for streaming
    responses, and errors.

    Returns:
        Server-sent event stream for the request
    """
    # Check auth and validate user_id requirement
    user_id_filter, is_admin, error_response = _check_auth_and_user_id(request, x_user_id)
    if error_response:
        return error_response

    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)

    # Normalize user_id to "0" for single-user mode (only if user_id provided)
    if user_id_filter:
        user_id = "0" if overlord and not getattr(overlord, "is_multi_user", False) else user_id_filter
    else:
        user_id = None  # Admin - can access any request

    from ....services.streaming import streaming_manager

    async def event_generator():
        try:
            # For admin without user_id, pass None to skip user validation
            subscription = streaming_manager.subscribe(
                request_id,
                user_id if user_id else None,
                session_id if user_id else None,  # Skip session check for admin
            )

            if subscription is None:
                yield f"data: {json.dumps({'error': 'Unauthorized or request not streaming'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'stream_open', 'session_id': session_id, 'request_id': request_id})}\n\n"

            async for event in subscription:
                yield f"data: {json.dumps(event)}\n\n"

            yield f"data: {json.dumps({'type': 'stream_completed', 'session_id': session_id, 'request_id': request_id})}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            error_msg = str(e).strip() if e else "Stream error"
            if error_msg:
                error_msg = error_msg.replace('\n', ' ').replace('\r', '')[:200]
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


# NOTE: /stream/{session_id}/{request_id} has been consolidated into /events/{session_id}/{request_id}
