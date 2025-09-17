"""
Event streaming endpoints.

These endpoints provide SSE streams for async updates,
requiring client API key authentication.
"""

import asyncio
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["Events"])


@router.get("/events/{user_id}")
async def user_events(request: Request, user_id: str) -> StreamingResponse:
    """
    SSE stream for async updates for a specific user.

    Args:
        user_id: User ID to get events for

    Returns:
        Server-sent event stream

    Note:
        Client API key authentication is enforced at the router level
    """
    # TODO: Implement user event streaming
    raise HTTPException(status_code=501, detail="Event streaming not yet implemented")


@router.get("/stream/{user_id}/{session_id}/{request_id}")
async def stream_request(
    request: Request,
    user_id: str,
    session_id: str,
    request_id: str
) -> StreamingResponse:
    """
    SSE stream for real-time request processing events.

    Args:
        request: FastAPI request object (contains server reference)
        user_id: User ID for security validation
        session_id: Session ID for security validation
        request_id: Request ID to stream events for

    Returns:
        Server-sent event stream of processing events

    Note:
        - Client API key authentication is enforced at the router level
        - User/session validation ensures proper access control
        - Real-time streaming - no event replay
    """
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
