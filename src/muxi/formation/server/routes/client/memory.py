"""
User memory management endpoints.

These endpoints provide memory CRUD operations for users.
Buffer endpoints support both ClientKey and AdminKey:
- ClientKey: X-Muxi-User-ID required (user's buffer only)
- AdminKey: X-Muxi-User-ID optional (omit for all, provide to filter)
"""

import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from fastapi import APIRouter, Request, Query, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    memory_list_response,
    create_error_response,
    create_success_response,
)
from .....datatypes.api import APIObjectType, APIEventType

router = APIRouter(tags=["Memory"])


class MemoryCreate(BaseModel):
    """Model for creating a memory."""

    content: str
    metadata: Optional[Dict[str, Any]] = None


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


def _check_auth_and_user_id(
    request: Request,
    x_user_id: Optional[str],
    request_id: Optional[str],
) -> Tuple[Optional[str], bool, Optional[JSONResponse]]:
    """
    Check authentication type and validate user_id requirement for buffer ops.

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
            request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=401)

    if not is_admin and not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required when using client API key",
            None,
            request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=400)

    return x_user_id, is_admin, None


@router.get("/memories", response_model=APIResponse)
async def get_user_memories(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of memories to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> JSONResponse:
    """
    Get memories for a user.

    Args:
        x_user_id: User ID from X-Muxi-User-ID header
        limit: Maximum number of memories to return
        offset: Offset for pagination

    Returns:
        List of user memories
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    # Check if persistent memory is configured
    if not formation.has_persistent_memory():
        response = memory_list_response([], request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)

    # Get overlord for memory access
    overlord = getattr(formation, "_overlord", None)
    if not overlord or not hasattr(overlord, "long_term_memory") or not overlord.long_term_memory:
        response = memory_list_response([], request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)

    try:
        # Get recent memories for this user (search with empty query returns all)
        memories = await overlord.long_term_memory.search(
            query="",
            limit=limit,
            external_user_id=user_id,
        )

        # Convert to API format
        memory_list = []
        for mem in memories:
            memory_list.append({
                "id": mem.get("id"),
                "content": mem.get("content") or mem.get("text"),
                "created_at": mem.get("created_at"),
                "metadata": mem.get("metadata", {})
            })

        response = memory_list_response(memory_list, request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to retrieve memories: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.post("/memories", response_model=APIResponse)
async def create_user_memory(
    request: Request,
    memory: MemoryCreate,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Create a memory for a user.

    Args:
        memory: Memory content and metadata
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Created memory details
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    # Check if persistent memory is configured
    if not formation.has_persistent_memory():
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Persistent memory not configured", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get overlord for memory access
    overlord = getattr(formation, "_overlord", None)
    if not overlord or not hasattr(overlord, "long_term_memory") or not overlord.long_term_memory:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Memory service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        # Add memory
        memory_id = await overlord.long_term_memory.add(
            content=memory.content,
            metadata=memory.metadata or {},
            external_user_id=user_id,
        )

        result = {
            "id": memory_id,
            "content": memory.content,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "metadata": memory.metadata or {}
        }

        response = create_success_response(
            APIObjectType.MEMORY, APIEventType.MEMORY_CREATED, result, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to create memory: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete("/memories/{memory_id}", response_model=APIResponse)
async def delete_user_memory(
    request: Request,
    memory_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Delete a user memory.

    Args:
        memory_id: Memory ID to delete
        x_user_id: User ID from X-Muxi-User-ID header

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate user_id from header
    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return error_response

    # Check if persistent memory is configured
    if not formation.has_persistent_memory():
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Persistent memory not configured", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get overlord for memory access
    overlord = getattr(formation, "_overlord", None)
    if not overlord or not hasattr(overlord, "long_term_memory") or not overlord.long_term_memory:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Memory service not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        # Delete memory (with user_id check for security)
        success = await overlord.long_term_memory.delete(
            memory_id=memory_id,
            external_user_id=user_id,
        )

        if success:
            result = {
                "deleted": memory_id,
                "user_id": user_id
            }
            response = create_success_response(
                APIObjectType.MEMORY, APIEventType.MEMORY_DELETED, result, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=200)
        else:
            response = create_error_response(
                "NOT_FOUND", f"Memory {memory_id} not found", None, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=404)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to delete memory: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


# Buffer Memory Operations
@router.get("/memory/buffer", response_model=APIResponse)
def get_buffer_status(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Get buffer memory data for a specific user.

    Accepts both ClientKey and AdminKey, but X-Muxi-User-ID is required for both.
    For aggregate stats, use GET /memory/buffer/stats instead.

    Returns:
        Buffer status with message counts and session info
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # User ID is required for this endpoint (both ClientKey and AdminKey)
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
        if buffer is None:
            # Return empty status if no buffer
            data = {
                "user_id": user_id,
                "total_messages": 0,
                "sessions": [],
                "buffer_size_kb": 0,
            }
            response = create_success_response(
                APIObjectType.MEMORY,
                APIEventType.MEMORY_RETRIEVED,
                data,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)

        # Get buffer stats
        total_messages = 0
        sessions = []
        buffer_size_kb = 0

        if hasattr(buffer, "get_buffer_stats"):
            stats = buffer.get_buffer_stats(user_id)
            total_messages = stats.get("total_messages", 0)
            sessions = stats.get("sessions", [])
            buffer_size_kb = stats.get("size_kb", 0)
        else:
            # Fallback: calculate from buffer deque
            if hasattr(buffer, "buffer"):
                # Buffer is a deque - count messages for this user by filtering
                import sys

                user_messages = [
                    msg
                    for msg in buffer.buffer
                    if isinstance(msg, dict) and msg.get("metadata", {}).get("user_id") == user_id
                ]
                total_messages = len(user_messages)
                buffer_size_kb = sys.getsizeof(str(user_messages)) / 1024

        data = {
            "user_id": user_id,
            "total_messages": total_messages,
            "sessions": sessions,
            "buffer_size_kb": round(buffer_size_kb, 2),
        }

        response = create_success_response(
            APIObjectType.MEMORY,
            APIEventType.MEMORY_BUFFER_STATUS,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to get buffer status: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete("/memory/buffer", response_model=APIResponse)
def clear_buffer(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Clear buffer memory.

    With ClientKey: X-Muxi-User-ID required (clears user's buffer)
    With AdminKey: X-Muxi-User-ID optional (omit to clear all, provide to clear specific user)

    Returns:
        Success response with cleared counts
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
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
        if buffer is None:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Buffer memory is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Clear user's buffer by manually removing matching items
        messages_cleared = 0
        sessions_cleared = 0

        if hasattr(buffer, "buffer"):
            # Single-pass rebuild for O(n) performance
            from collections import deque

            original_length = len(buffer.buffer)
            new_buffer = deque()
            unique_sessions = set()

            for item in buffer.buffer:
                if isinstance(item, dict) and item.get("metadata", {}).get("user_id") == user_id:
                    # Track unique sessions being removed
                    sess_id = item.get("metadata", {}).get("session_id")
                    if sess_id:
                        unique_sessions.add(sess_id)
                else:
                    # Keep items that don't match
                    new_buffer.append(item)

            messages_cleared = original_length - len(new_buffer)
            sessions_cleared = len(unique_sessions)
            buffer.buffer = new_buffer

            # Mark index for rebuild if we removed items and vector search is enabled
            if messages_cleared > 0 and hasattr(buffer, "needs_rebuild"):
                buffer.needs_rebuild = True

        data = {
            "message": "Buffer cleared successfully",
            "user_id": user_id,
            "messages_cleared": messages_cleared,
            "sessions_cleared": sessions_cleared,
        }

        response = create_success_response(
            APIObjectType.MESSAGE,
            APIEventType.MEMORY_BUFFER_USER_CLEARED,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to clear buffer: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete("/memory/buffer/{session_id}", response_model=APIResponse)
def clear_session_buffer(
    request: Request,
    session_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Clear buffer memory for a specific session.

    With ClientKey: X-Muxi-User-ID required, session must belong to user
    With AdminKey: X-Muxi-User-ID optional, can clear any session

    Returns:
        Success response with cleared message count
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
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
        if buffer is None:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Buffer memory is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Clear session buffer by manually removing matching items
        messages_cleared = 0

        if hasattr(buffer, "buffer"):
            # Single-pass rebuild for O(n) performance
            from collections import deque

            original_length = len(buffer.buffer)
            new_buffer = deque()

            for item in buffer.buffer:
                if (
                    isinstance(item, dict)
                    and item.get("metadata", {}).get("user_id") == user_id
                    and item.get("metadata", {}).get("session_id") == session_id
                ):
                    # Skip items that match (they're being cleared)
                    pass
                else:
                    # Keep items that don't match
                    new_buffer.append(item)

            messages_cleared = original_length - len(new_buffer)
            buffer.buffer = new_buffer

            # Mark index for rebuild if we removed items and vector search is enabled
            if messages_cleared > 0 and hasattr(buffer, "needs_rebuild"):
                buffer.needs_rebuild = True

        data = {
            "message": "Session buffer cleared successfully",
            "user_id": user_id,
            "session_id": session_id,
            "messages_cleared": messages_cleared,
        }

        response = create_success_response(
            APIObjectType.MESSAGE,
            APIEventType.MEMORY_BUFFER_SESSION_CLEARED,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to clear session buffer: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)
