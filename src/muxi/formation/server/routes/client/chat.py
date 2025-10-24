"""
Chat interaction endpoints.

These endpoints provide chat functionality for users,
requiring client API key authentication.
"""

from typing import Optional, List, Dict, Any, Union
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from .....services import observability
from ...utils import get_header_case_insensitive

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    """Model for chat requests."""

    message: str
    user_id: Optional[str] = None  # Deprecated: use X-Muxi-User-Id header instead
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    group_id: Optional[str] = None  # Support for group permissions
    request_id: Optional[str] = None
    mode: Optional[str] = "sync"  # sync or async
    files: Optional[List[Dict[str, Any]]] = None
    stream: Optional[bool] = True  # Enable/disable streaming (default: True)


@router.post("/chat", response_model=None)
async def chat(request: Request, chat_request: ChatRequest) -> Union[StreamingResponse, JSONResponse]:
    """
    Send a message to the formation and receive a response.

    For synchronous requests with stream=True, returns a streaming response.
    For synchronous requests with stream=False, returns a complete JSON response.
    For asynchronous requests, returns a job ID.

    Args:
        chat_request: The chat request containing message

    Headers:
        X-Muxi-User-Id: User ID for request context (optional, defaults to "0")

    Returns:
        Streaming response, JSON response, or async job details
    """
    formation = request.app.state.formation

    # Ensure we have an overlord
    if not formation.is_overlord_running():
        raise HTTPException(status_code=503, detail="Overlord not available")

    # Get user_id from header first, fallback to body (for backward compatibility), then default
    header_user_id = get_header_case_insensitive(request.headers, "X-Muxi-User-Id")
    effective_user_id = header_user_id or chat_request.user_id or "0"

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

    # Handle non-streaming mode
    if chat_request.stream is False:
        try:
            # Get complete response from overlord
            response = await overlord.chat(
                message=chat_request.message,
                user_id=effective_user_id,
                session_id=chat_request.session_id,
                request_id=chat_request.request_id,
                agent_name=chat_request.agent_id,
                files=chat_request.files,
                stream=False,  # Disable streaming
            )
            
            # Return complete response as JSON
            from ...responses import create_success_response
            from .....datatypes.api import APIObjectType, APIEventType
            
            data = {
                "message": response,
                "user_id": effective_user_id,
                "session_id": chat_request.session_id,
                "request_id": chat_request.request_id,
            }
            
            api_response = create_success_response(
                APIObjectType.MESSAGE,
                APIEventType.CHAT_COMPLETED,
                data,
                chat_request.request_id,
            )
            
            return JSONResponse(content=api_response.model_dump(), status_code=200)
            
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
            raise HTTPException(status_code=500, detail=str(e))

    # Process synchronously with streaming
    async def generate_stream():
        """Generate SSE stream from overlord response."""
        try:
            # Get streaming response from overlord
            # Note: overlord.chat() is async and returns AsyncGenerator when stream=True
            response = await overlord.chat(
                message=chat_request.message,
                user_id=effective_user_id,
                session_id=chat_request.session_id,
                request_id=chat_request.request_id,
                agent_name=chat_request.agent_id,
                files=chat_request.files,
                stream=True,  # Enable streaming
            )
            
            # Stream the tokens
            async for token in response:
                # Format as SSE (removed "role" to save bandwidth as requested)
                data = json.dumps({"token": token})
                yield f"data: {data}\n\n"

            # Send completion event
            yield f"event: done\ndata: {json.dumps({'finished': True})}\n\n"

        except asyncio.CancelledError:
            # Client disconnected - clean shutdown, no error message
            pass
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

            # Send error event (sanitize and truncate error message)
            error_msg = str(e).strip() if e else "Request failed"
            if error_msg:
                # Remove newlines and limit length for SSE safety
                error_msg = error_msg.replace('\n', ' ').replace('\r', '')[:200]

            error_data = json.dumps({"error": error_msg, "type": type(e).__name__})
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
