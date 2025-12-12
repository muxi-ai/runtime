"""
Event streaming endpoints.

These endpoints provide SSE streams for async updates,
requiring client API key authentication.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["Events"])


@router.get("/events")
async def user_events(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> StreamingResponse:
    """
    SSE stream for async updates for a specific user.

    Args:
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Server-sent event stream

    Note:
        Client API key authentication is enforced at the router level
    """
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-Muxi-User-ID header is required")

    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)

    # Normalize user_id to "0" for single-user mode
    user_id = "0" if overlord and not getattr(overlord, "is_multi_user", False) else x_user_id

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
            # Subscribe to observability event stream filtered to this user
            # Only stream user-facing events (not internal system events)
            filters = {"user_id": user_id}

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


@router.get("/stream/{session_id}/{request_id}")
async def stream_request(
    request: Request,
    session_id: str,
    request_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> StreamingResponse:
    """
    SSE stream for real-time request processing events.

    Args:
        request: FastAPI request object (contains server reference)
        session_id: Session ID for security validation
        request_id: Request ID to stream events for
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Server-sent event stream of processing events

    Note:
        - Client API key authentication is enforced at the router level
        - User/session validation ensures proper access control
        - Real-time streaming - no event replay
    """
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-Muxi-User-ID header is required")

    # Normalize user_id to "0" for single-user mode
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    user_id = "0" if overlord and not getattr(overlord, "is_multi_user", False) else x_user_id

    from ....services.streaming import streaming_manager

    async def event_generator():
        try:
            # Subscribe to real-time events with security validation
            subscription = streaming_manager.subscribe(request_id, user_id, session_id)

            if subscription is None:
                # Not authorized or request not streaming
                yield f"data: {json.dumps({'error': 'Unauthorized or request not streaming'})}\n\n"
                return

            # Notify client that stream is successfully opened
            yield f"data: {json.dumps({'type': 'stream_open'})}\n\n"

            # Stream events in real-time
            async for event in subscription:
                yield f"data: {json.dumps(event)}\n\n"

            # Stream completed (request_id deleted from streaming_manager)
            yield f"data: {json.dumps({'type': 'stream_completed'})}\n\n"

        except asyncio.CancelledError:
            # Client disconnected - clean shutdown, no error message
            pass
        except Exception as e:
            # Real error - notify client (sanitize and truncate)
            error_msg = str(e).strip() if e else "Stream error"
            if error_msg:
                # Remove newlines and limit length for SSE safety
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
