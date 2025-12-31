"""
Response conversion utilities for MUXI runtime.

This module provides utilities to convert between OneLLM's OpenAI-compatible
types and MUXI's unified response format, maintaining separation of concerns.
"""

import inspect
import time
import traceback
from typing import List, Optional, Dict, Any, Union, AsyncGenerator

from onellm.types.common import ContentItem as OneLLMContentItem
from ..datatypes.response import MuxiContentItem, MuxiUnifiedResponse, MuxiErrorDetails
from ..datatypes.errors import get_error_info
from ..utils.error_classifier import classify_error_code
from ..services import observability


def convert_onellm_to_muxi_content(
    onellm_content: List[OneLLMContentItem],
) -> List[MuxiContentItem]:
    """
    Convert OneLLM ContentItem list to MUXI MuxiContentItem list.

    Args:
        onellm_content: List of OneLLM ContentItem objects

    Returns:
        List of MUXI MuxiContentItem objects
    """
    try:

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_STARTED,
            level=observability.EventLevel.DEBUG,
            description="Starting OneLLM to MUXI content conversion",
            data={"input_items_count": len(onellm_content), "conversion_type": "onellm_to_muxi"},
        )
    except Exception:
        pass  # Don't let observability failures break core functionality

    muxi_content: List[MuxiContentItem] = []

    try:
        for item in onellm_content:
            if item["type"] == "text":
                muxi_content.append({"type": "text", "text": item["text"], "file": None})
            elif item["type"] == "image_url":
                # Convert image_url to file format
                muxi_content.append(
                    {
                        "type": "file",
                        "text": None,
                        "file": {"type": "image", "url": item["image_url"]["url"]},
                    }
                )

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="OneLLM to MUXI content conversion completed",
            data={
                "input_items_count": len(onellm_content),
                "output_items_count": len(muxi_content),
                "conversion_type": "onellm_to_muxi",
            },
        )

        return muxi_content

    except Exception as e:
        observability.observe(
            observability.ErrorEvents.INTERNAL_ERROR,
            observability.EventLevel.ERROR,
            f"OneLLM to MUXI content conversion failed: {str(e)}",
            data={
                "error_type": type(e).__name__,
                "conversion_type": "onellm_to_muxi",
                "input_items_count": len(onellm_content),
            },
        )
        raise


def extract_user_content(
    mcp_message_content: Union[str, List[Dict[str, Any]]],
) -> List[MuxiContentItem]:
    """
    Extract user-facing content from MCP message content, filtering out tool calls.

    Args:
        mcp_message_content: MuxiResponse content (string or list of MuxiMessageContent dicts)

    Returns:
        List of user-facing MUXI MuxiContentItem objects
    """
    try:

        content_type = "string" if isinstance(mcp_message_content, str) else "list"
        content_length = (
            len(mcp_message_content) if isinstance(mcp_message_content, (str, list)) else 0
        )

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_STARTED,
            level=observability.EventLevel.DEBUG,
            description="Starting MCP message content extraction",
            data={
                "content_type": content_type,
                "content_length": content_length,
                "conversion_type": "mcp_to_user_content",
            },
        )
    except Exception:
        pass

    user_content: List[MuxiContentItem] = []

    try:
        # Handle string content
        if isinstance(mcp_message_content, str):
            user_content.append({"type": "text", "text": mcp_message_content, "file": None})

            observability.observe(
                event_type=observability.ConversationEvents.RESPONSE_CONVERSION_COMPLETED,
                level=observability.EventLevel.DEBUG,
                description="MCP string content extraction completed",
                data={
                    "content_type": "string",
                    "output_items_count": 1,
                    "conversion_type": "mcp_to_user_content",
                },
            )

            return user_content

        # Handle list of MuxiMessageContent objects
        tool_calls_filtered = 0
        for item in mcp_message_content:
            item_type = item.get("type", "")

            # Skip tool calls - these are internal implementation details
            if item_type == "tool_calls":
                tool_calls_filtered += 1
                continue

            if item_type == "text":
                text_content = item.get("text", "")
                if text_content:  # Only add non-empty text
                    user_content.append({"type": "text", "text": text_content, "file": None})
            elif item_type == "file":
                # Handle file content (future extension)
                file_info = item.get("file", {})
                user_content.append(
                    {
                        "type": "file",
                        "text": None,
                        "file": {
                            "type": file_info.get("type", "document"),
                            "url": file_info.get("url", ""),
                        },
                    }
                )

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="MCP list content extraction completed",
            data={
                "content_type": "list",
                "input_items_count": len(mcp_message_content),
                "output_items_count": len(user_content),
                "tool_calls_filtered": tool_calls_filtered,
                "conversion_type": "mcp_to_user_content",
            },
        )

        return user_content

    except Exception as e:
        observability.observe(
            observability.ErrorEvents.INTERNAL_ERROR,
            observability.EventLevel.ERROR,
            f"MCP content extraction failed: {str(e)}",
            data={
                "error_type": type(e).__name__,
                "conversion_type": "mcp_to_user_content",
                "content_type": "string" if isinstance(mcp_message_content, str) else "list",
            },
        )
        raise


def create_unified_response(
    request_id: str,
    status: str,
    content: List[MuxiContentItem],
    formation_id: str,
    processing_mode: str = "sync",
    processing_time: Optional[float] = None,
    webhook_url: Optional[str] = None,
    error: Optional[MuxiErrorDetails] = None,
    user_id: Optional[str] = None,
) -> MuxiUnifiedResponse:
    """
    Create a unified response object.

    Args:
        request_id: Unique request identifier
        status: Response status
        content: Response content items
        formation_id: Formation identifier
        processing_mode: sync or async
        processing_time: Processing time in seconds
        webhook_url: Webhook URL for async responses
        error: Error details if status is failed
        user_id: User identifier

    Returns:
        MuxiUnifiedResponse object
    """
    try:

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_STARTED,
            level=observability.EventLevel.DEBUG,
            description="Creating unified response object",
            data={
                "request_id": request_id,
                "status": status,
                "formation_id": formation_id,
                "processing_mode": processing_mode,
                "content_items_count": len(content),
                "has_error": error is not None,
                "conversion_type": "unified_response_creation",
            },
        )
    except Exception:
        pass

    try:
        response = {
            "id": request_id,
            "object": "response",
            "status": status,
            "timestamp": int(time.time() * 1000),  # Unix timestamp in milliseconds
            "formation_id": formation_id,
            "user_id": user_id,
            "processing_time": processing_time,
            "processing_mode": processing_mode,
            "webhook_url": webhook_url,
            "error": error,
            "response": content,
        }

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="Unified response object created successfully",
            data={
                "request_id": request_id,
                "status": status,
                "formation_id": formation_id,
                "processing_mode": processing_mode,
                "content_items_count": len(content),
                "has_error": error is not None,
                "conversion_type": "unified_response_creation",
            },
        )

        return response

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Unified response creation failed: {str(e)}",
            data={
                "error_type": type(e).__name__,
                "request_id": request_id,
                "status": status,
                "conversion_type": "unified_response_creation",
            },
        )
        raise


def create_error_response(exception: Exception, include_trace: bool = False) -> MuxiErrorDetails:
    """
    Create standardized error details from an exception.

    Args:
        exception: The exception that occurred
        include_trace: Whether to include stack trace

    Returns:
        MuxiErrorDetails object
    """
    try:

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_STARTED,
            level=observability.EventLevel.DEBUG,
            description="Creating error response details",
            data={
                "exception_type": type(exception).__name__,
                "include_trace": include_trace,
                "conversion_type": "error_response_creation",
            },
        )
    except Exception:
        pass

    try:
        error_code = classify_error_code(exception)
        error_info = get_error_info(error_code)

        # Handle traceback safely to avoid scoping issues
        trace_info = None
        if include_trace:
            trace_info = traceback.format_exc()

        error_details = {
            "code": error_code,
            "message": error_info.message if error_info else str(exception),
            "trace": trace_info,
        }

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_CONVERSION_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="Error response details created successfully",
            data={
                "exception_type": type(exception).__name__,
                "error_code": error_code,
                "include_trace": include_trace,
                "has_trace": error_details["trace"] is not None,
                "conversion_type": "error_response_creation",
            },
        )

        return error_details

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={
                "error_type": type(e).__name__,
                "original_exception_type": type(exception).__name__,
                "conversion_type": "error_response_creation",
            },
            description=f"Error response creation failed: {str(e)}",
        )
        raise


async def extract_response_content(response: Any) -> str:
    """
    Extract text content from various response types.

    Handles:
    - Async generators (streaming responses) - consumes and joins chunks
    - MuxiResponse objects with .content attribute
    - String responses
    - Any other type (converted to string)

    Args:
        response: Response from overlord.chat() - can be async generator,
                  MuxiResponse, string, or other types

    Returns:
        Extracted text content as string
    """
    # Handle async generator (streaming response)
    if inspect.isasyncgen(response):
        chunks = []
        async for chunk in response:
            if isinstance(chunk, str):
                chunks.append(chunk)
            elif hasattr(chunk, 'content'):
                content = chunk.content
                if content:
                    chunks.append(str(content) if not isinstance(content, str) else content)
        return "".join(chunks)

    # Handle MuxiResponse or similar objects with .content attribute
    if hasattr(response, 'content'):
        content = response.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Extract text from content items (multi-modal responses)
            text_parts = []
            for item in content:
                if hasattr(item, 'text') and item.text:
                    text_parts.append(item.text)
                elif isinstance(item, dict) and item.get('text'):
                    text_parts.append(item['text'])
            return " ".join(text_parts)
        else:
            return str(content) if content else ""

    # Handle string responses
    if isinstance(response, str):
        return response

    # Fallback for other types
    return str(response)
