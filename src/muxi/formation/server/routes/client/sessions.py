"""
Session management endpoints.

These endpoints provide session lifecycle management and history access,
requiring client API key authentication.
"""

from typing import Optional

from fastapi import APIRouter, Request, Query, Header
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType
from .....services import observability

router = APIRouter(tags=["Sessions"])


def _get_user_id(x_user_id: Optional[str], request_id: Optional[str]) -> tuple[Optional[str], Optional[JSONResponse]]:
    """Extract and validate user_id from X-Muxi-User-ID header."""
    if not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required",
            None,
            request_id,
        )
        return None, JSONResponse(content=response.model_dump(), status_code=400)
    return x_user_id, None


@router.get("/sessions", response_model=APIResponse)
def list_user_sessions(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
    active_only: bool = Query(default=False, description="Only return active sessions"),
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of sessions"),
) -> JSONResponse:
    """
    List all sessions for a user.

    Args:
        x_user_id: User ID from X-Muxi-User-ID header
        active_only: Only return active sessions (default: False)
        limit: Maximum number of sessions to return (default: 50)

    Returns:
        List of user sessions with metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

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
        sessions = []

        # Get buffer entries for this user
        if hasattr(buffer, "get_user_sessions"):
            # If method exists, it should already respect the limit
            sessions = buffer.get_user_sessions(user_id, active_only=active_only, limit=limit)
        else:
            # Fallback: scan buffer to extract unique sessions
            # Track unique session IDs with metadata
            seen_sessions = {}

            if hasattr(buffer, "buffer"):
                # Scan buffer in reverse (most recent first)
                for item in reversed(buffer.buffer):
                    metadata = item.get("metadata", {})
                    item_user_id = metadata.get("user_id")
                    session_id = metadata.get("session_id")

                    # Skip if not matching user or no session ID
                    if item_user_id != user_id or not session_id:
                        continue

                    # Track unique sessions
                    if session_id not in seen_sessions:
                        seen_sessions[session_id] = {
                            "session_id": session_id,
                            "user_id": user_id,
                            "last_activity": metadata.get("timestamp", item.get("timestamp")),
                            "active": True,  # Sessions in buffer are considered active
                        }

                        # Stop if we've reached the limit
                        if len(seen_sessions) >= limit:
                            break

                # Convert to list (already in most-recent-first order)
                sessions = list(seen_sessions.values())

                # Apply active_only filter if requested
                if active_only:
                    sessions = [s for s in sessions if s.get("active", True)]

        # Compute paged results once and reuse
        paged_sessions = sessions[:limit]  # Ensure limit (already applied in fallback)
        data = {"sessions": paged_sessions, "count": len(paged_sessions)}

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


@router.get("/sessions/{session_id}", response_model=APIResponse)
def get_session(
    request: Request,
    session_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Get detailed information about a specific session.

    Args:
        session_id: Session ID
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Session details including metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

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


@router.delete("/sessions/{session_id}", response_model=APIResponse)
def clear_session(
    request: Request,
    session_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Clear a session and its buffer memory.

    Args:
        session_id: Session ID
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Success response with cleared message count
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

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


@router.get("/sessions/{session_id}/messages", response_model=APIResponse)
def get_session_messages(
    request: Request,
    session_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum messages"),
    before: Optional[str] = Query(default=None, description="Get messages before this timestamp"),
) -> JSONResponse:
    """
    Retrieve chat message history for a session.

    Args:
        session_id: Session ID
        x_user_id: User ID from X-Muxi-User-ID header
        limit: Maximum number of messages (default: 50)
        before: Get messages before this ISO 8601 timestamp

    Returns:
        Message history with pagination info
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

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
                # buffer.buffer is a deque - iterate and filter by user_id and session_id
                messages = []
                for item in buffer.buffer:
                    if not isinstance(item, dict):
                        continue
                    metadata = item.get("metadata", {})
                    if (
                        metadata.get("user_id") == user_id
                        and metadata.get("session_id") == session_id
                    ):
                        messages.append(item)
                        if len(messages) >= limit + 1:
                            break

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
