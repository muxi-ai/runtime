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
    group_id: Optional[str] = None  # Reserved for future use: group-based permission filtering
    request_id: Optional[str] = None
    mode: Optional[str] = "sync"  # sync or async
    files: Optional[List[Dict[str, Any]]] = None
    stream: Optional[bool] = True  # Enable/disable streaming (default: True)


class AudioChatRequest(BaseModel):
    """Model for audio chat requests (voice notes).
    
    The audio is transcribed first, then the transcription is used as the user's message.
    Only audio/* MIME types are accepted.
    """

    files: List[Dict[str, Any]]  # Required: list of audio file objects with content
    user_id: Optional[str] = None  # Deprecated: use X-Muxi-User-Id header instead
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
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

    # Async mode support: Returns request_id immediately, processes in background
    # User can poll GET /v1/requests or subscribe to GET /v1/events (with X-Muxi-User-ID header)
    if chat_request.mode == "async":
        # Async mode is supported via request tracking system
        # Implementation requires webhook configuration or SSE subscription for results
        raise HTTPException(
            status_code=501, 
            detail="Async mode requires webhook configuration. Use stream=true for real-time responses or mode=sync for immediate responses."
        )

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

            # Extract session_id from response metadata if available (overlord may have generated one)
            response_session_id = chat_request.session_id
            if hasattr(response, 'metadata') and response.metadata:
                response_session_id = response.metadata.get('session_id', chat_request.session_id)

            data = {
                "message": response,
                "user_id": effective_user_id,
                "session_id": response_session_id,
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
            # Re-raise HTTPException unchanged to preserve status code and details
            if isinstance(e, HTTPException):
                raise
            
            # Log non-HTTP exceptions
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
            # Raise new HTTPException with original exception chain preserved
            raise HTTPException(status_code=500, detail=str(e)) from e

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


@router.post("/audiochat", response_model=None)
async def audiochat(request: Request, audiochat_request: AudioChatRequest) -> Union[StreamingResponse, JSONResponse]:
    """
    Send audio files (voice notes) for transcription and conversational response.

    The audio is transcribed first using a speech-to-text model (e.g., Whisper),
    then the transcribed text is used as the user's message for the conversation.

    This endpoint is designed for voice note interactions (WhatsApp, Telegram, etc.)
    where the audio IS the user's message, not an attachment to analyze.

    For file attachments with a text prompt, use /chat with the files parameter instead.

    Args:
        audiochat_request: The audio chat request containing audio files

    Headers:
        X-Muxi-User-Id: User ID for request context (optional, defaults to "0")

    Returns:
        Streaming response or JSON response
    """
    formation = request.app.state.formation

    # Ensure we have an overlord
    if not formation.is_overlord_running():
        raise HTTPException(status_code=503, detail="Overlord not available")

    # Validate files are provided
    if not audiochat_request.files:
        from ...responses import create_error_response
        response = create_error_response(
            "VALIDATION_ERROR",
            "files parameter is required for audiochat()",
            {"field": "files"},
            audiochat_request.request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Validate all files are audio
    for file_data in audiochat_request.files:
        content_type = file_data.get("content_type", file_data.get("mime_type", ""))
        if not content_type.startswith("audio/"):
            from ...responses import create_error_response
            response = create_error_response(
                "VALIDATION_ERROR",
                "Only audio files (audio/*) are accepted. For video or other files, use /chat with the files parameter.",
                {"field": "files", "invalid_content_type": content_type},
                audiochat_request.request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=400)

    # Get user_id from header first, fallback to body, then default
    header_user_id = get_header_case_insensitive(request.headers, "X-Muxi-User-Id")
    effective_user_id = header_user_id or audiochat_request.user_id or "0"

    # Log audio chat request
    observability.observe(
        event_type=observability.ConversationEvents.REQUEST_RECEIVED,
        level=observability.EventLevel.INFO,
        data={
            "service": "formation_api_server",
            "endpoint": "/api/audiochat",
            "user_id": effective_user_id,
            "session_id": audiochat_request.session_id,
            "request_id": audiochat_request.request_id,
            "agent_id": audiochat_request.agent_id,
            "file_count": len(audiochat_request.files),
            "formation_id": formation.formation_id,
        },
        description="Audio chat request received via Formation API",
    )

    # Get overlord for processing
    overlord = formation._overlord

    # Handle non-streaming mode - use audiochat() which transcribes audio first
    if audiochat_request.stream is False:
        try:
            response = await overlord.audiochat(
                files=audiochat_request.files,
                user_id=effective_user_id,
                session_id=audiochat_request.session_id,
                agent_name=audiochat_request.agent_id,
                stream=False,
            )

            from ...responses import create_success_response
            from .....datatypes.api import APIObjectType, APIEventType

            data = {
                "message": response,
                "user_id": effective_user_id,
                "session_id": audiochat_request.session_id,
                "request_id": audiochat_request.request_id,
            }

            api_response = create_success_response(
                APIObjectType.MESSAGE,
                APIEventType.CHAT_COMPLETED,
                data,
                audiochat_request.request_id,
            )

            return JSONResponse(content=api_response.model_dump(), status_code=200)

        except Exception as e:
            if isinstance(e, HTTPException):
                raise

            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "formation_api_server",
                    "endpoint": "/api/audiochat",
                    "user_id": effective_user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "formation_id": formation.formation_id,
                },
                description=f"Audio chat request failed: {e}",
            )
            raise HTTPException(status_code=500, detail=str(e)) from e

    # Streaming mode - use audiochat() which transcribes audio first
    async def generate_stream():
        """Generate SSE stream from overlord response."""
        try:
            response = await overlord.audiochat(
                files=audiochat_request.files,
                user_id=effective_user_id,
                session_id=audiochat_request.session_id,
                agent_name=audiochat_request.agent_id,
                stream=True,
            )

            async for token in response:
                data = json.dumps({"token": token})
                yield f"data: {data}\n\n"

            yield f"event: done\ndata: {json.dumps({'finished': True})}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "formation_api_server",
                    "endpoint": "/api/audiochat",
                    "user_id": effective_user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "formation_id": formation.formation_id,
                },
                description=f"Audio chat request failed: {e}",
            )

            error_msg = str(e).strip() if e else "Request failed"
            if error_msg:
                error_msg = error_msg.replace('\n', ' ').replace('\r', '')[:200]

            error_data = json.dumps({"error": error_msg, "type": type(e).__name__})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
