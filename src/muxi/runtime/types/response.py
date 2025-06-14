"""
Unified response types for MUXI runtime.

This module defines the standardized response format for all MUXI communication
modes (sync, async, webhooks) with multi-modal support and OpenAI compatibility.
"""

from typing import Optional, List, Literal, TypedDict


class MuxiFileContent(TypedDict):
    """File content with type specification."""

    type: Literal["image", "audio", "video", "document"]
    url: str


class MuxiContentItem(TypedDict):
    """Unified content item for MUXI responses."""

    type: Literal["text", "file"]
    text: Optional[str]  # Present when type="text"
    file: Optional[MuxiFileContent]  # Present when type="file"


class MuxiErrorDetails(TypedDict):
    """Standardized error information."""

    code: str  # Error code from error registry
    message: str  # Human-readable error message
    trace: Optional[str]  # Stack trace for debugging (optional)


class MuxiUnifiedResponse(TypedDict):
    """Unified response format for all MUXI communication modes."""

    id: str  # Request ID (req_NANO_ID format)
    object: Literal["response"]  # Always "response"
    status: Literal[
        "processing", "completed", "failed", "awaiting_clarification", "timeout", "cancelled"
    ]
    timestamp: int  # Unix timestamp in milliseconds
    formation_id: str  # Formation identifier
    user_id: Optional[str]  # User identifier
    processing_time: Optional[float]  # Processing time in seconds (null for async in-progress)
    processing_mode: Literal["sync", "async"]  # How request was processed
    webhook_url: Optional[str]  # Webhook URL (async only)
    error: Optional[MuxiErrorDetails]  # Error details (when status="failed")
    response: List[MuxiContentItem]  # Response content array
