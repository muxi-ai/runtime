"""
Client interaction endpoints.

These endpoints provide user interaction capabilities,
requiring client API key authentication.
"""

from typing import Dict, Any, List, Optional
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ....services import observability

router = APIRouter()


# Pydantic models
class ChatRequest(BaseModel):
    """Model for chat requests."""

    message: str
    user_id: Optional[str] = "0"  # Default to "0" if not provided
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    group_id: Optional[str] = None  # Support for group permissions
    request_id: Optional[str] = None
    mode: Optional[str] = "sync"  # sync or async
    files: Optional[List[Dict[str, Any]]] = None


class ChatResponse(BaseModel):
    """Model for chat responses."""

    request_id: str
    mode: str
    content: Optional[str] = None
    estimated_seconds: Optional[int] = None


class MemoryCreate(BaseModel):
    """Model for creating a memory."""

    content: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/chat")
async def chat(
    request: Request, chat_request: ChatRequest
) -> StreamingResponse:
    """
    Send a message to the formation and receive a response.

    For synchronous requests, returns a streaming response.
    For asynchronous requests, returns a job ID.

    Args:
        chat_request: The chat request containing message and optional user_id

    Returns:
        Streaming response or async job details
    """
    formation = request.app.state.formation

    # Ensure we have an overlord
    if not hasattr(formation, "_overlord") or not formation._overlord:
        raise HTTPException(status_code=503, detail="Overlord not available")

    # Use user_id from request body
    effective_user_id = chat_request.user_id

    # Log chat request
    observability.observe(
        event_type=observability.ConversationEvents.REQUEST_RECEIVED,
        level=observability.EventLevel.INFO,
        data={
            "service": "formation_api_server",
            "endpoint": "/api/chat",
            "user_id": effective_user_id,
            "session_id": chat_request.session_id,
            "request_id": chat_request.request_id,
            "agent_id": chat_request.agent_id,
            "mode": chat_request.mode,
            "has_files": bool(chat_request.files),
            "formation_id": formation.formation_id,
        },
        description="Chat request received via Formation API",
    )

    # Get overlord for chat processing
    overlord = formation._overlord

    # For now, always use sync mode (async will be implemented later)
    if chat_request.mode == "async":
        # TODO: Implement async processing
        raise HTTPException(status_code=501, detail="Async mode not yet implemented")

    # Process synchronously with streaming
    async def generate_stream():
        """Generate SSE stream from overlord response."""
        try:
            # Get streaming response from overlord
            async for token in overlord.chat_stream(
                chat_request.message,
                user_id=effective_user_id,
                session_id=chat_request.session_id,
                request_id=chat_request.request_id,
                agent_name=chat_request.agent_id,
                files=chat_request.files,
            ):
                # Format as SSE
                data = json.dumps({"token": token, "role": "assistant"})
                yield f"data: {data}\n\n"

            # Send completion event
            yield f"event: done\ndata: {json.dumps({'finished': True})}\n\n"

        except Exception as e:
            # Log error
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "formation_api_server",
                    "endpoint": "/api/chat",
                    "user_id": effective_user_id,
                    "session_id": chat_request.session_id,
                    "request_id": chat_request.request_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "formation_id": formation.formation_id,
                },
                description=f"Chat request failed: {e}",
            )

            # Send error event
            error_data = json.dumps({"error": str(e), "type": type(e).__name__})
            yield f"event: error\ndata: {error_data}\n\n"

    # Return streaming response
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/events/{user_id}")
async def user_events(request: Request, user_id: str) -> StreamingResponse:
    """
    SSE stream for async updates for a specific user.

    Args:
        user_id: User ID to get events for

    Returns:
        Server-sent event stream
    """
    # TODO: Implement user event streaming
    raise HTTPException(status_code=501, detail="Event streaming not yet implemented")


@router.get("/jobs/{user_id}")
async def list_user_jobs(request: Request, user_id: str) -> List[Dict[str, Any]]:
    """
    List async jobs for a user.

    Args:
        user_id: User ID to get jobs for

    Returns:
        List of job details
    """
    # formation = request.app.state.formation  # TODO: Use when implementing job tracking

    # TODO: Get jobs from request tracker
    return []


@router.delete("/jobs/{user_id}/{job_id}")
async def cancel_job(request: Request, user_id: str, job_id: str) -> Dict[str, str]:
    """
    Cancel or delete an async job.

    Args:
        user_id: User ID who owns the job
        job_id: Job ID to cancel

    Returns:
        Success message
    """
    # TODO: Implement job cancellation
    raise HTTPException(status_code=501, detail="Job cancellation not yet implemented")


@router.get("/memories/{user_id}")
async def get_user_memories(
    request: Request, user_id: str, limit: int = 10, offset: int = 0
) -> List[Dict[str, Any]]:
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

    # Check if persistent memory is configured
    if not hasattr(formation, "_long_term_memory") or not formation._long_term_memory:
        return []

    # TODO: Implement memory retrieval
    return []


@router.post("/memories/{user_id}")
async def create_user_memory(
    request: Request, user_id: str, memory: MemoryCreate
) -> Dict[str, Any]:
    """
    Create a memory for a user.

    Args:
        user_id: User ID to create memory for
        memory: Memory content and metadata

    Returns:
        Created memory details
    """
    formation = request.app.state.formation

    # Check if persistent memory is configured
    if not hasattr(formation, "_long_term_memory") or not formation._long_term_memory:
        raise HTTPException(status_code=503, detail="Persistent memory not configured")

    # TODO: Implement memory creation
    raise HTTPException(status_code=501, detail="Memory creation not yet implemented")


@router.delete("/memories/{user_id}/{memory_id}")
async def delete_user_memory(request: Request, user_id: str, memory_id: str) -> Dict[str, str]:
    """
    Delete a user memory.

    Args:
        user_id: User ID who owns the memory
        memory_id: Memory ID to delete

    Returns:
        Success message
    """
    # TODO: Implement memory deletion
    raise HTTPException(status_code=501, detail="Memory deletion not yet implemented")
