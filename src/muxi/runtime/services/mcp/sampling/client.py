"""MCP Sampling client implementation."""

from typing import List, Dict, Any, Optional
from ..transports.base import BaseTransport
from ..protocol.message_handler import MCPMessageHandler
from ....datatypes.exceptions import MCPRequestError


class MCPSamplingClient:
    """MCP Sampling client using sampling protocol."""

    def __init__(self):
        """Initialize sampling client."""
        self.message_handler = MCPMessageHandler()

    async def create_message(
        self,
        transport: BaseTransport,
        messages: List[Dict[str, Any]],
        model_preferences: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create a message using MCP sampling/createMessage method.

        Args:
            transport: MCP transport to use for communication
            messages: List of conversation messages
            model_preferences: Optional model selection preferences
            max_tokens: Optional maximum tokens for response
            temperature: Optional sampling temperature

        Returns:
            Generated message response

        Raises:
            MCPRequestError: If message creation fails
        """
        try:
            # Validate messages format
            self._validate_messages(messages)

            # Prepare request parameters
            params = {"messages": messages}

            if model_preferences:
                params["modelPreferences"] = model_preferences
            if max_tokens is not None:
                params["maxTokens"] = max_tokens
            if temperature is not None:
                params["temperature"] = temperature

            # Send request to MCP server
            response = await transport.send_request({
                "method": "sampling/createMessage",
                "params": params
            })

            # Extract result
            result = response.get("result", {})

            # Validate result structure
            self._validate_message_result(result)

            return result

        except Exception as e:
            if isinstance(e, MCPRequestError):
                raise
            raise MCPRequestError(f"Failed to create message: {e}")

    def _validate_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Validate message list structure.

        Args:
            messages: List of messages to validate

        Raises:
            MCPRequestError: If message structure is invalid
        """
        if not isinstance(messages, list):
            raise MCPRequestError("Messages must be a list")

        if not messages:
            raise MCPRequestError("Messages list cannot be empty")

        for i, message in enumerate(messages):
            if not isinstance(message, dict):
                raise MCPRequestError(f"Message {i} must be an object")

            # Validate required role field
            if "role" not in message:
                raise MCPRequestError(f"Message {i} missing required 'role' field")

            role = message["role"]
            if role not in ["user", "assistant", "system"]:
                raise MCPRequestError(f"Message {i} has invalid role: {role}")

            # Validate content field
            if "content" not in message:
                raise MCPRequestError(f"Message {i} missing required 'content' field")

            content = message["content"]
            if not isinstance(content, (str, list)):
                raise MCPRequestError(f"Message {i} content must be string or array")

            # If content is array, validate each item
            if isinstance(content, list):
                for j, content_item in enumerate(content):
                    if not isinstance(content_item, dict):
                        raise MCPRequestError(f"Message {i} content item {j} must be an object")
                    if "type" not in content_item:
                        raise MCPRequestError(f"Message {i} content item {j} missing 'type' field")

                    content_type = content_item["type"]
                    if content_type == "text":
                        if "text" not in content_item:
                            raise MCPRequestError(f"Message {i} content item {j} missing 'text' field")
                    elif content_type == "image":
                        if "data" not in content_item:
                            raise MCPRequestError(f"Message {i} content item {j} missing 'data' field")

    def _validate_message_result(self, result: Dict[str, Any]) -> None:
        """Validate message creation result.

        Args:
            result: Result to validate

        Raises:
            MCPRequestError: If result structure is invalid
        """
        # Check for required content field in response
        if "content" not in result:
            raise MCPRequestError("Message result missing required 'content' field")

        content = result["content"]
        if not isinstance(content, (str, list)):
            raise MCPRequestError("Message result content must be string or array")

        # Validate content array if present
        if isinstance(content, list):
            for i, content_item in enumerate(content):
                if not isinstance(content_item, dict):
                    raise MCPRequestError(f"Result content item {i} must be an object")
                if "type" not in content_item:
                    raise MCPRequestError(f"Result content item {i} missing 'type' field")

        # Check for role field if present
        if "role" in result:
            role = result["role"]
            if role not in ["user", "assistant", "system"]:
                raise MCPRequestError(f"Result has invalid role: {role}")

        # Validate model field if present
        if "model" in result and not isinstance(result["model"], str):
            raise MCPRequestError("Result model must be a string")

        # Validate stopReason if present
        if "stopReason" in result:
            stop_reason = result["stopReason"]
            if stop_reason not in ["endTurn", "stopSequence", "maxTokens"]:
                raise MCPRequestError(f"Result has invalid stopReason: {stop_reason}")

    def extract_text_content(self, result: Dict[str, Any]) -> str:
        """Extract text content from message result.

        Args:
            result: Message creation result

        Returns:
            Extracted text content
        """
        content = result.get("content", "")

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            text_parts = []
            for item in content:
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return " ".join(text_parts)
        else:
            return str(content)

    def prepare_conversation_messages(
        self,
        conversation_history: List[str],
        roles: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Prepare conversation messages from simple text list.

        Args:
            conversation_history: List of conversation messages
            roles: Optional list of roles (defaults to alternating user/assistant)

        Returns:
            Formatted message list for sampling
        """
        if not conversation_history:
            return []

        messages = []

        for i, message_text in enumerate(conversation_history):
            # Determine role
            if roles and i < len(roles):
                role = roles[i]
            else:
                # Default to alternating user/assistant starting with user
                role = "user" if i % 2 == 0 else "assistant"

            message = {
                "role": role,
                "content": message_text
            }

            messages.append(message)

        return messages

    def create_model_preferences(
        self,
        hints: List[str] = None,
        cost_priority: float = None,
        speed_priority: float = None,
        intelligence_priority: float = None
    ) -> Dict[str, Any]:
        """Create model preferences object.

        Args:
            hints: Optional model hints or names
            cost_priority: Priority for cost optimization (0.0-1.0)
            speed_priority: Priority for speed optimization (0.0-1.0)
            intelligence_priority: Priority for intelligence/capability (0.0-1.0)

        Returns:
            Model preferences object
        """
        preferences = {}

        if hints:
            preferences["hints"] = hints

        if cost_priority is not None:
            preferences["costPriority"] = max(0.0, min(1.0, cost_priority))

        if speed_priority is not None:
            preferences["speedPriority"] = max(0.0, min(1.0, speed_priority))

        if intelligence_priority is not None:
            preferences["intelligencePriority"] = max(0.0, min(1.0, intelligence_priority))

        return preferences if preferences else None

    def get_message_summary(self, result: Dict[str, Any]) -> str:
        """Get a summary of the message creation result.

        Args:
            result: Message creation result

        Returns:
            Human-readable summary
        """
        content_text = self.extract_text_content(result)
        model = result.get("model", "unknown")
        stop_reason = result.get("stopReason", "unknown")

        summary_lines = [
            f"🤖 Generated Message (model: {model})",
            f"Stop reason: {stop_reason}",
            f"Content: {content_text[:200]}{'...' if len(content_text) > 200 else ''}"
        ]

        # Add usage information if available
        if "usage" in result:
            usage = result["usage"]
            if "inputTokens" in usage:
                summary_lines.append(f"Input tokens: {usage['inputTokens']}")
            if "outputTokens" in usage:
                summary_lines.append(f"Output tokens: {usage['outputTokens']}")

        return "\n".join(summary_lines)
