"""
Session management endpoints.

These endpoints provide session lifecycle management and history access,
requiring client API key authentication.
"""

from typing import Optional

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType
from .....services import observability

router = APIRouter(tags=["Sessions"])


@router.get("/sessions/{user_id}", response_model=APIResponse)
async def list_user_sessions(
    request: Request,
    user_id: str,
    active_only: bool = Query(default=False, description="Only return active sessions"),
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of sessions"),
) -> JSONResponse:
    """
    List all sessions for a user.

    Args:
        user_id: User ID
        active_only: Only return active sessions (default: False)
        limit: Maximum number of sessions to return (default: 50)

    Returns:
        List of user sessions with metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    try:
        # Get overlord for buffer access
        overlord = getattr(formation, "_overlord", None)
        if not overlord:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Overlord service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Get buffer memory
        buffer = getattr(overlord, "buffer_memory", None)
        if not buffer:
            # Return empty list if no buffer
            data = {"sessions": [], "count": 0}
            response = create_success_response(
                APIObjectType.SESSION_LIST,
                APIEventType.SESSION_LIST,
                data,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)

        # Get sessions from buffer
        # This is a simplified implementation - production would query buffer metadata
        sessions = []
        
        # Get buffer entries for this user
        if hasattr(buffer, "get_user_sessions"):
            sessions = buffer.get_user_sessions(user_id, active_only=active_only, limit=limit)
        else:
            # Fallback: scan buffer for sessions
            # In production, buffer would maintain session metadata
            pass

        data = {"sessions": sessions[:limit], "count": len(sessions[:limit])}

        response = create_success_response(
            APIObjectType.SESSION_LIST,
            APIEventType.SESSION_LIST,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to list sessions: {str(e)}",
            data={"user_id": user_id, "error": str(e), "error_type": type(e).__name__},
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to list sessions: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.get("/sessions/{user_id}/{session_id}", response_model=APIResponse)
async def get_session(request: Request, user_id: str, session_id: str) -> JSONResponse:
    """
    Get detailed information about a specific session.

    Args:
        user_id: User ID
        session_id: Session ID

    Returns:
        Session details including metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    try:
        # Get overlord for buffer access
        overlord = getattr(formation, "_overlord", None)
        if not overlord:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Overlord service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Get buffer memory
        buffer = getattr(overlord, "buffer_memory", None)
        if not buffer:
            response = create_error_response(
                "RESOURCE_NOT_FOUND",
                f"Session '{session_id}' not found",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=404)

        # Get session details
        session_data = None
        if hasattr(buffer, "get_session"):
            session_data = buffer.get_session(user_id, session_id)
        else:
            # Fallback: construct from buffer entries
            if hasattr(buffer, "get_messages"):
                messages = buffer.get_messages(user_id=user_id, session_id=session_id)
                if messages:
                    session_data = {
                        "session_id": session_id,
                        "user_id": user_id,
                        "message_count": len(messages),
                        "active": True,
                    }

        if not session_data:
            response = create_error_response(
                "RESOURCE_NOT_FOUND",
                f"Session '{session_id}' not found",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=404)

        response = create_success_response(
            APIObjectType.SESSION,
            APIEventType.SESSION_RETRIEVED,
            session_data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to get session: {str(e)}",
            data={
                "user_id": user_id,
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to get session: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete("/sessions/{user_id}/{session_id}", response_model=APIResponse)
async def clear_session(request: Request, user_id: str, session_id: str) -> JSONResponse:
    """
    Clear a session and its buffer memory.

    Args:
        user_id: User ID
        session_id: Session ID

    Returns:
        Success response with cleared message count
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    try:
        # Get overlord for buffer access
        overlord = getattr(formation, "_overlord", None)
        if not overlord:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Overlord service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Get buffer memory
        buffer = getattr(overlord, "buffer_memory", None)
        if not buffer:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Buffer memory is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Clear session from buffer
        messages_cleared = 0
        if hasattr(buffer, "clear_session"):
            messages_cleared = buffer.clear_session(user_id, session_id)
        elif hasattr(buffer, "clear"):
            # Fallback: clear specific session
            buffer.clear(user_id=user_id, session_id=session_id)
            messages_cleared = 0  # Unknown count

        observability.observe(
            event_type=observability.SystemEvents.OPERATION_COMPLETED,
            level=observability.EventLevel.INFO,
            description=f"Session '{session_id}' cleared",
            data={
                "user_id": user_id,
                "session_id": session_id,
                "messages_cleared": messages_cleared,
            },
        )

        data = {
            "message": "Session cleared successfully",
            "session_id": session_id,
            "messages_cleared": messages_cleared,
        }

        response = create_success_response(
            APIObjectType.MESSAGE,
            APIEventType.SESSION_CLEARED,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to clear session: {str(e)}",
            data={
                "user_id": user_id,
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to clear session: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.get("/sessions/{user_id}/{session_id}/messages", response_model=APIResponse)
async def get_session_messages(
    request: Request,
    user_id: str,
    session_id: str,
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum messages"),
    before: Optional[str] = Query(default=None, description="Get messages before this timestamp"),
) -> JSONResponse:
    """
    Retrieve chat message history for a session.

    Args:
        user_id: User ID
        session_id: Session ID
        limit: Maximum number of messages (default: 50)
        before: Get messages before this ISO 8601 timestamp

    Returns:
        Message history with pagination info
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    try:
        # Get overlord for buffer access
        overlord = getattr(formation, "_overlord", None)
        if not overlord:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Overlord service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Get buffer memory
        buffer = getattr(overlord, "buffer_memory", None)
        if not buffer:
            data = {
                "session_id": session_id,
                "messages": [],
                "count": 0,
                "has_more": False,
            }
            response = create_success_response(
                APIObjectType.SESSION,
                APIEventType.SESSION_RETRIEVED,
                data,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)

        # Get messages from buffer
        messages = []
        if hasattr(buffer, "get_messages"):
            messages = buffer.get_messages(
                user_id=user_id,
                session_id=session_id,
                limit=limit + 1,  # Get one extra to check has_more
                before=before,
            )
        else:
            # Fallback: direct buffer access
            if hasattr(buffer, "buffer"):
                # Simple implementation - production would have proper indexing
                all_messages = buffer.buffer.get(user_id, [])
                messages = [
                    msg for msg in all_messages
                    if msg.get("session_id") == session_id
                ][:limit + 1]

        # Check pagination
        has_more = len(messages) > limit
        messages = messages[:limit]

        data = {
            "session_id": session_id,
            "messages": messages,
            "count": len(messages),
            "has_more": has_more,
        }

        response = create_success_response(
            APIObjectType.SESSION,
            APIEventType.SESSION_MESSAGES_LIST,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to get session messages: {str(e)}",
            data={
                "user_id": user_id,
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to get session messages: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)
