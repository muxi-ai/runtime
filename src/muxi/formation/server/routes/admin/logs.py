"""
Live log streaming endpoint.

This endpoint provides admin-only access to stream live formation logs
via Server-Sent Events (SSE) with required filtering to prevent firehose.
"""

import re
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
            detail=(
                "At least one filter parameter is required "
                "(user_id, session_id, request_id, agent_id, level, or event_type)"
            ),
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

        TODO: Production implementation required
        This is currently a placeholder that returns a "not implemented" message.

        Production implementation should:
        1. Subscribe to the observability system's event emitter instead of polling
        2. Use the existing matches_filters() function to filter events
        3. Emit SSE-compliant messages (event: log + data: JSON) for matching events
        4. Monitor request.is_disconnected() and break/cleanup subscription to avoid leaks
        5. Handle backpressure and buffering appropriately
        """
        try:
            # FIXME: Replace this placeholder with real event streaming
            # Currently returns a "not implemented" message to avoid misleading users
            not_implemented = {
                "error": True,
                "message": "Real-time log streaming is not yet implemented",
                "reason": "Event sourcing from observability system not connected",
                "workaround": "Use GET /v1/logging/destinations to view configured log outputs",
                "filters_received": active_filters,
            }
            yield "event: error\n"
            yield f"data: {json.dumps(not_implemented)}\n\n"

            # Production implementation outline:
            # 1. Subscribe to observability event emitter:
            #    subscription = observability.subscribe()
            #
            # 2. Stream events with filtering:
            #    async for event in subscription:
            #        if await request.is_disconnected():
            #            break
            #
            #        if matches_filters(event, active_filters):
            #            event_data = {
            #                "timestamp": event.timestamp,
            #                "level": event.level,
            #                "event_type": event.event_type,
            #                "user_id": event.get("user_id"),
            #                "session_id": event.get("session_id"),
            #                "request_id": event.get("request_id"),
            #                "agent_id": event.get("agent_id"),
            #                "message": event.description,
            #                "data": event.data,
            #            }
            #            yield f"event: log\n"
            #            yield f"data: {json.dumps(event_data)}\n\n"
            #
            # 3. Cleanup subscription on disconnect/error

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
            yield "event: error\n"
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
            if not re.fullmatch(pattern, event_data.get("event_type", "")):
                return False
        else:
            # Exact match for other fields
            if event_data.get(key) != value:
                return False
    return True
