"""
Live log streaming endpoint.

This endpoint provides admin-only access to stream live formation logs
via Server-Sent Events (SSE) with required filtering to prevent firehose.
"""

import asyncio
import json
import re
from functools import lru_cache
from typing import Optional, Pattern

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from .....services import observability

router = APIRouter(tags=["Logs"])


@lru_cache(maxsize=128)
def _compile_event_type_pattern(filter_value: str) -> Pattern:
    """
    Compile and cache a regex pattern for event_type wildcard matching.
    
    Escapes regex metacharacters and converts * wildcards to .* pattern.
    Cached to avoid recompiling the same pattern on every event.
    
    Args:
        filter_value: Event type filter value (may contain * wildcards)
    
    Returns:
        Compiled regex pattern for matching
    """
    escaped = re.escape(filter_value)
    pattern_str = escaped.replace(r"\*", ".*")
    return re.compile(pattern_str)


@router.get("/logs")
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
        GET /logs?level=ERROR
        GET /logs?user_id=alice&level=ERROR
        GET /logs?agent_id=weather-assistant
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
            "endpoint": "/logs",
            "filters": active_filters,
        },
    )

    async def event_generator():
        """
        Generate Server-Sent Events from observability logs.
        """
        formation = request.app.state.formation
        overlord = getattr(formation, "_overlord", None)
        
        if not overlord:
            error_msg = {
                "error": True,
                "message": "Overlord service not available",
                "filters_received": active_filters,
            }
            yield "event: error\n"
            yield f"data: {json.dumps(error_msg)}\n\n"
            return
        
        # Get observability manager
        observability_manager = overlord.observability_manager if hasattr(overlord, 'observability_manager') else None
        
        if not observability_manager or not hasattr(observability_manager, 'subscribe'):
            # Fallback if observability manager doesn't have subscription support
            error_msg = {
                "error": True,
                "message": "Observability manager does not support live streaming",
                "filters_received": active_filters,
            }
            yield "event: error\n"
            yield f"data: {json.dumps(error_msg)}\n\n"
            return
        
        try:
            # Subscribe to observability event stream with filters
            async for event in observability_manager.subscribe(active_filters):
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Format event for SSE
                event_data = {
                    "timestamp": event.get("timestamp"),
                    "level": event.get("level"),
                    "event_type": event.get("event_type"),
                    "user_id": event.get("user_id"),
                    "session_id": event.get("session_id"),
                    "request_id": event.get("request_id"),
                    "agent_id": event.get("data", {}).get("agent_id"),
                    "message": event.get("description"),
                    "data": event.get("data"),
                }
                
                yield "event: log\n"
                yield f"data: {json.dumps(event_data)}\n\n"

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
                    "endpoint": "/logs",
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
            # Support wildcard matching for event_type (with cached compiled pattern)
            pattern = _compile_event_type_pattern(value)
            if not pattern.fullmatch(event_data.get("event_type", "")):
                return False
        else:
            # Exact match for other fields
            if event_data.get(key) != value:
                return False
    return True
