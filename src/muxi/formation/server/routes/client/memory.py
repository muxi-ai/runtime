"""
User memory management endpoints.

These endpoints provide memory CRUD operations for users,
requiring client API key authentication.
"""

from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, Query
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


@router.get("/memories/{user_id}", response_model=APIResponse)
async def get_user_memories(
    request: Request,
    user_id: str,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of memories to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> JSONResponse:
    """
    Get memories for a user.

    Args:
        user_id: User ID to get memories for
        limit: Maximum number of memories to return
        offset: Offset for pagination

    Returns:
        List of user memories
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

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


@router.post("/memories/{user_id}", response_model=APIResponse)
async def create_user_memory(request: Request, user_id: str, memory: MemoryCreate) -> JSONResponse:
    """
    Create a memory for a user.

    Args:
        user_id: User ID to create memory for
        memory: Memory content and metadata

    Returns:
        Created memory details
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

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

        from datetime import datetime
        result = {
            "id": memory_id,
            "content": memory.content,
            "created_at": datetime.utcnow().isoformat() + "Z",
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


@router.delete("/memories/{user_id}/{memory_id}", response_model=APIResponse)
async def delete_user_memory(request: Request, user_id: str, memory_id: str) -> JSONResponse:
    """
    Delete a user memory.

    Args:
        user_id: User ID who owns the memory
        memory_id: Memory ID to delete

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

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
@router.get("/memory/buffer/{user_id}", response_model=APIResponse)
def get_buffer_status(request: Request, user_id: str) -> JSONResponse:
    """
    Get buffer memory status for a user.

    Args:
        user_id: User ID

    Returns:
        Buffer status with message counts and session info
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


@router.delete("/memory/buffer/{user_id}", response_model=APIResponse)
def clear_user_buffer(request: Request, user_id: str) -> JSONResponse:
    """
    Clear all buffer memory for a user across all sessions.

    Args:
        user_id: User ID

    Returns:
        Success response with cleared counts
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


@router.delete("/memory/buffer/{user_id}/{session_id}", response_model=APIResponse)
def clear_session_buffer(request: Request, user_id: str, session_id: str) -> JSONResponse:
    """
    Clear buffer memory for a specific session.

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
