"""
Unified response types for MUXI runtime.

This module defines the standardized response format for all MUXI communication
modes (sync, async, webhooks) with multi-modal support and OpenAI compatibility.
"""

from typing import Optional, List, Literal, TypedDict, Union, Dict, Any
from pydantic import BaseModel, Field

from .mcp import FunctionCallModel
from .artifacts import MuxiArtifact


class MuxiFileContent(TypedDict):
    """
    File content with type specification.

    Represents file metadata including type and URL for external API responses.
    """

    type: Literal["image", "audio", "video", "document"]  # Supported file types
    url: str  # File URL for access


class MuxiContentItem(TypedDict):
    """
    Unified content item for MUXI responses.

    Used for external communication (user <> MUXI) in API responses.
    Supports both text and file content types.
    """

    type: Literal["text", "file"]  # Content type identifier
    text: Optional[str]  # Present when type="text"
    file: Optional[MuxiFileContent]  # Present when type="file"


class MuxiErrorDetails(TypedDict):
    """
    Standardized error information.

    Provides consistent error structure across all MUXI communication modes.
    """

    code: str  # Error code from error registry
    message: str  # Human-readable error message
    trace: Optional[str]  # Stack trace for debugging (optional)


class MuxiUnifiedResponse(TypedDict):
    """
    Unified response format for all MUXI communication modes.

    Standardizes response structure across sync, async, and webhook modes
    with comprehensive metadata and content support.
    """

    id: str  # Request ID (req_NANO_ID format)
    object: Literal["response"]  # Always "response"
    status: Literal[
        "processing", "completed", "failed", "awaiting_clarification", "timeout", "cancelled"
    ]  # Current request status
    timestamp: int  # Unix timestamp in milliseconds
    formation_id: str  # Formation identifier
    user_id: Optional[str]  # User identifier
    processing_time: Optional[float]  # Processing time in seconds (null for async in-progress)
    processing_mode: Literal["sync", "async"]  # How request was processed
    webhook_url: Optional[str]  # Webhook URL (async only)
    error: Optional[MuxiErrorDetails]  # Error details (when status="failed")
    response: List[MuxiContentItem]  # Response content array


# ============================================================================
# Message Response Types (Internal message types)
# ============================================================================


class MuxiMessageContent(BaseModel):
    """
    Model representing a single content item in an internal message.

    This model defines the structure of a content item within an internal message,
    which can be either text content or a tool/function call. It supports
    the LLM multi-modal content format.

    Used for internal communication (MUXI <> agents, overlord <> agents).
    Distinct from muxi.runtimeContentItem which is for external communication (user <> MUXI).

    """

    type: str = Field(..., description="Content type ('text' or 'tool_calls')")
    text: Optional[str] = Field(None, description="Text content (when type='text')")
    tool_calls: Optional[List[FunctionCallModel]] = Field(
        None, description="Tool calls (when type='tool_calls')"
    )

    def model_dump(self, **kwargs):
        """
        Convert model to dictionary with custom handling.

        This method provides a custom serialization for MuxiMessageContent objects,
        which ensures proper translation between the Pydantic model and the
        format expected by the JSON-RPC protocol.

        Args:
            **kwargs: Additional arguments passed to model_dump
                     - mode: If "json", uses JSON-compatible serialization

        Returns:
            Dict[str, Any]: Dictionary representation of the content item
        """
        # Check if JSON mode is requested for special handling
        if kwargs.get("mode") == "json":
            # For JSON output - ensure proper serialization format
            has_tool_calls = self.type == "tool_calls" and self.tool_calls
            tool_calls_json = None
            if has_tool_calls:
                if not isinstance(self.tool_calls, list):
                    raise ValueError("tool_calls must be a list when type is 'tool_calls'")

                # Serialize each tool call in JSON mode
                tool_calls_json = [tc.model_dump(mode="json") for tc in self.tool_calls]

            return {
                "type": self.type,
                "text": self.text if self.type == "text" else None,
                "tool_calls": tool_calls_json,
            }

        # For regular dict output - standard serialization
        result = {"type": self.type}
        if self.type == "text":
            result["text"] = self.text
        elif self.type == "tool_calls":
            # Validate tool_calls is a list before iteration
            if self.tool_calls and not isinstance(self.tool_calls, list):
                raise ValueError("tool_calls must be a list when type is 'tool_calls'")

            # Serialize tool calls using default model_dump
            result["tool_calls"] = (
                [tc.model_dump() for tc in self.tool_calls] if self.tool_calls else None
            )
        return result


class MuxiResponse(BaseModel):
    """
    Model representing a complete message with mixed content.

    This model defines the structure of a complete message within the MUXI
    system, which includes a role (user, assistant, etc.) and content that
    can be either a simple string or a list of content items supporting
    multi-modal content.

    """

    role: str = Field(..., description="Message role (user, assistant, system, etc.)")
    content: Union[str, List[MuxiMessageContent]] = Field(
        ..., description="Message content (string or content items)"
    )
    artifacts: Optional[List[MuxiArtifact]] = None
    metadata: Optional[Dict[str, Any]] = None

    def model_dump(self, **kwargs):
        """
        Convert model to dictionary with custom handling.

        This method provides a custom serialization for Message objects,
        which ensures proper translation between the Pydantic model and
        the format expected by clients.

        Args:
            **kwargs: Additional arguments passed to model_dump
                     - mode: If "json", uses JSON-compatible serialization

        Returns:
            Dict[str, Any]: Dictionary representation of the message
        """
        # Initialize result with role
        result = {"role": self.role}

        # Handle different content types based on content structure
        if isinstance(self.content, str):
            # Simple string content - direct assignment
            result["content"] = self.content
        else:
            # Complex content with multiple items - serialize each item
            mode = "json" if kwargs.get("mode") == "json" else None
            result["content"] = [item.model_dump(mode=mode) for item in self.content]

        # Include artifacts if present
        if self.artifacts:
            mode = "json" if kwargs.get("mode") == "json" else None
            result["artifacts"] = [artifact.model_dump(mode=mode) for artifact in self.artifacts]

        # Include metadata if present
        if self.metadata:
            result["metadata"] = self.metadata

        return result
