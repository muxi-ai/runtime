"""
Response conversion utilities for MUXI runtime.

This module provides utilities to convert between OneLLM's OpenAI-compatible
types and MUXI's unified response format, maintaining separation of concerns.
"""

import time
import traceback
from typing import List, Optional, Dict, Any, Union

from onellm.types.common import ContentItem as OneLLMContentItem
from ..types.response import (
    MuxiContentItem,
    MuxiUnifiedResponse,
    MuxiErrorDetails
)
from ..types.errors import get_error_info
from ..utils.error_classifier import classify_error_code


def convert_onellm_to_muxi_content(
    onellm_content: List[OneLLMContentItem]
) -> List[MuxiContentItem]:
    """
    Convert OneLLM ContentItem list to MUXI ContentItem list.

    Args:
        onellm_content: List of OneLLM ContentItem objects

    Returns:
        List of MUXI ContentItem objects
    """
    muxi_content: List[MuxiContentItem] = []

    for item in onellm_content:
        if item["type"] == "text":
            muxi_content.append({
                "type": "text",
                "text": item["text"],
                "file": None
            })
        elif item["type"] == "image_url":
            # Convert image_url to file format
            muxi_content.append({
                "type": "file",
                "text": None,
                "file": {
                    "type": "image",
                    "url": item["image_url"]["url"]
                }
            })

    return muxi_content


def extract_user_content(
    mcp_message_content: Union[str, List[Dict[str, Any]]]
) -> List[MuxiContentItem]:
    """
    Extract user-facing content from MCP message content, filtering out tool calls.

    Args:
        mcp_message_content: MCPMessage content (string or list of ContentItem dicts)

    Returns:
        List of user-facing MUXI ContentItem objects
    """
    user_content: List[MuxiContentItem] = []

    # Handle string content
    if isinstance(mcp_message_content, str):
        user_content.append({
            "type": "text",
            "text": mcp_message_content,
            "file": None
        })
        return user_content

    # Handle list of ContentItem objects
    for item in mcp_message_content:
        item_type = item.get("type", "")

        # Skip tool calls - these are internal implementation details
        if item_type == "tool_calls":
            continue

        if item_type == "text":
            text_content = item.get("text", "")
            if text_content:  # Only add non-empty text
                user_content.append({
                    "type": "text",
                    "text": text_content,
                    "file": None
                })
        elif item_type == "file":
            # Handle file content (future extension)
            file_info = item.get("file", {})
            user_content.append({
                "type": "file",
                "text": None,
                "file": {
                    "type": file_info.get("type", "document"),
                    "url": file_info.get("url", "")
                }
            })

    return user_content


def create_unified_response(
    request_id: str,
    status: str,
    content: List[MuxiContentItem],
    formation_id: str,
    processing_mode: str = "sync",
    processing_time: Optional[float] = None,
    webhook_url: Optional[str] = None,
    error: Optional[MuxiErrorDetails] = None,
    user_id: Optional[str] = None
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
    return {
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
        "response": content
    }


def create_error_response(
    exception: Exception,
    include_trace: bool = False
) -> MuxiErrorDetails:
    """
    Create standardized error details from an exception.

    Args:
        exception: The exception that occurred
        include_trace: Whether to include stack trace

    Returns:
        MuxiErrorDetails object
    """
    error_code = classify_error_code(exception)
    error_info = get_error_info(error_code)

    return {
        "code": error_code,
        "message": error_info.message if error_info else str(exception),
        "trace": traceback.format_exc() if include_trace else None
    }
