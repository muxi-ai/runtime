"""
Live log streaming endpoint.

This endpoint provides admin-only access to stream live formation logs
via Server-Sent Events (SSE) with required filtering to prevent firehose.
"""

from typing import Optional
import asyncio
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from .....services import observability

router = APIRouter(tags=["Logs"])


@router.get("/logs/stream")
async def stream_logs(
    request: Request,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    level: Optional[str] = None,
    event_type: Optional[str] = None,
) -> StreamingResponse:
    """
    Stream live logs via Server-Sent Events (SSE).

    Requires at least ONE filter parameter to prevent firehose.

    Args:
        user_id: Filter by user ID
        session_id: Filter by session ID
        request_id: Filter by request ID
        agent_id: Filter by agent ID
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        event_type: Filter by event type pattern (supports wildcards like "chat.*")

    Returns:
        SSE stream of log events

    Example:
        GET /logs/stream?level=ERROR
        GET /logs/stream?user_id=alice&level=ERROR
        GET /logs/stream?agent_id=weather-assistant
    """
    formation = request.app.state.formation

    # Validate that at least one filter is provided
    filters = {
        "user_id": user_id,
        "session_id": session_id,
        "request_id": request_id,
        "agent_id": agent_id,
        "level": level,
        "event_type": event_type,
    }
    active_filters = {k: v for k, v in filters.items() if v is not None}

    if not active_filters:
        raise HTTPException(
            status_code=400,
            detail="At least one filter parameter is required (user_id, session_id, request_id, agent_id, level, or event_type)",
        )

    # Log the streaming request
    observability.observe(
        event_type=observability.SystemEvents.OPERATION_COMPLETED,
        level=observability.EventLevel.INFO,
        description="Admin log streaming started",
        data={
            "service": "formation_api_server",
            "endpoint": "/logs/stream",
            "filters": active_filters,
        },
    )

    async def event_generator():
        """
        Generate Server-Sent Events from observability logs.

        This is a simplified implementation that demonstrates the SSE format.
        A production implementation would hook into the observability system's
        event emitter to get real-time events.
        """
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'connected': True, 'filters': active_filters})}\n\n"

            # Keep connection alive and send events
            # In a real implementation, this would subscribe to the observability
            # event stream and filter based on the provided parameters
            
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                # Wait a bit before next check (this would be event-driven in production)
                await asyncio.sleep(1)

                # In production, this would receive actual events from observability system
                # and filter them based on active_filters, then format and yield them
                
                # Example event format:
                # event_data = {
                #     "timestamp": 1706616000000,
                #     "level": "INFO",
                #     "event_type": "chat.completed",
                #     "user_id": "alice",
                #     "session_id": "sess123",
                #     "request_id": "req_abc",
                #     "message": "Request completed",
                #     "data": {}
                # }
                # 
                # if matches_filters(event_data, active_filters):
                #     yield f"event: log\n"
                #     yield f"data: {json.dumps(event_data)}\n\n"

        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception as e:
            # Log error
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Log streaming error: {str(e)}",
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "filters": active_filters,
                },
            )
            # Send error event to client
            error_event = {
                "error": True,
                "message": "Streaming error occurred",
            }
            yield f"event: error\n"
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            # Log disconnection
            observability.observe(
                event_type=observability.SystemEvents.OPERATION_COMPLETED,
                level=observability.EventLevel.INFO,
                description="Admin log streaming ended",
                data={
                    "service": "formation_api_server",
                    "endpoint": "/logs/stream",
                    "filters": active_filters,
                },
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


def matches_filters(event_data: dict, filters: dict) -> bool:
    """
    Check if an event matches the active filters.

    Args:
        event_data: Event data to check
        filters: Active filters (only includes non-None values)

    Returns:
        True if event matches all filters, False otherwise
    """
    for key, value in filters.items():
        if key == "event_type":
            # Support wildcard matching for event_type
            pattern = value.replace("*", ".*")
            import re
            if not re.match(pattern, event_data.get("event_type", "")):
                return False
        else:
            # Exact match for other fields
            if event_data.get(key) != value:
                return False
    return True
