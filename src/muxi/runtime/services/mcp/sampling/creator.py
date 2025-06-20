"""MCP Sampling implementation for createMessage functionality."""

from typing import Dict, Any, List, Optional
from ..transports.base import BaseTransport
from ..protocol.message_handler import MCPMessageHandler
from ....datatypes.exceptions import MCPRequestError


class MCPSamplingCreator:
    """MCP Sampling creator for sampling/createMessage method."""

    def __init__(self):
        """Initialize sampling creator."""
        self.message_handler = MCPMessageHandler()

    async def create_message(
        self,
        transport: BaseTransport,
        messages: List[Dict[str, Any]],
        model_preferences: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Request LLM message creation via sampling/createMessage method.

        Args:
            transport: MCP transport to use for communication
            messages: List of message objects for conversation context
            model_preferences: Optional model selection preferences
            max_tokens: Optional maximum tokens for response
            temperature: Optional sampling temperature (0.0-1.0)
            stop_sequences: Optional list of stop sequences

        Returns:
            Message creation result

        Raises:
            MCPRequestError: If message creation fails
        """
        try:
            # Validate input messages
            self._validate_messages(messages)

            # Prepare request parameters
            params = {"messages": messages}

            # Add optional parameters if provided
            if model_preferences:
                params["modelPreferences"] = model_preferences
            if max_tokens is not None:
                self._validate_max_tokens(max_tokens)
                params["maxTokens"] = max_tokens
            if temperature is not None:
                self._validate_temperature(temperature)
                params["temperature"] = temperature
            if stop_sequences:
                params["stopSequences"] = stop_sequences

            # Send request to MCP server
            response = await transport.send_request({
                "method": "sampling/createMessage",
                "params": params
            })

            # Extract result - handle both dict and direct response
            if hasattr(response, 'get'):
                result = response.get("result", {})
            else:
                result = response if isinstance(response, dict) else {}

            return self._process_message_result(result)

        except Exception as e:
            if isinstance(e, MCPRequestError):
                raise
            raise MCPRequestError(f"Failed to create message: {e}")

    def prepare_conversation_messages(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        system_message: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Prepare messages in the format expected by createMessage.

        Args:
            user_message: The user's input message
            conversation_history: Optional previous conversation messages
            system_message: Optional system message to include

        Returns:
            List of formatted messages
        """
        messages = []

        # Add system message if provided
        if system_message:
            messages.append({
                "role": "system",
                "content": system_message
            })

        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history:
                self._validate_message_format(msg)
                messages.append(msg)

        # Add user message
        messages.append({
            "role": "user",
            "content": user_message
        })

        return messages

    def create_model_preferences(
        self,
        hints: Optional[List[Dict[str, Any]]] = None,
        cost_priority: Optional[float] = None,
        speed_priority: Optional[float] = None,
        intelligence_priority: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create model preferences object for sampling requests.

        Args:
            hints: Optional model hints
            cost_priority: Optional cost priority (0.0-1.0)
            speed_priority: Optional speed priority (0.0-1.0)
            intelligence_priority: Optional intelligence priority (0.0-1.0)

        Returns:
            Model preferences object
        """
        preferences = {}

        if hints:
            preferences["hints"] = hints

        if cost_priority is not None:
            self._validate_priority(cost_priority, "cost_priority")
            preferences["costPriority"] = cost_priority

        if speed_priority is not None:
            self._validate_priority(speed_priority, "speed_priority")
            preferences["speedPriority"] = speed_priority

        if intelligence_priority is not None:
            self._validate_priority(intelligence_priority, "intelligence_priority")
            preferences["intelligencePriority"] = intelligence_priority

        return preferences

    def _validate_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Validate messages array.

        Args:
            messages: Messages to validate

        Raises:
            MCPRequestError: If messages are invalid
        """
        if not isinstance(messages, list):
            raise MCPRequestError("Messages must be a list")

        if not messages:
            raise MCPRequestError("Messages list cannot be empty")

        for i, message in enumerate(messages):
            try:
                self._validate_message_format(message)
            except MCPRequestError as e:
                raise MCPRequestError(f"Message {i} is invalid: {e}")

    def _validate_message_format(self, message: Dict[str, Any]) -> None:
        """Validate individual message format.

        Args:
            message: Message to validate

        Raises:
            MCPRequestError: If message format is invalid
        """
        if not isinstance(message, dict):
            raise MCPRequestError("Message must be an object")

        # Validate required role field
        if "role" not in message:
            raise MCPRequestError("Message missing required 'role' field")

        role = message["role"]
        if role not in ["user", "assistant", "system"]:
            raise MCPRequestError(f"Invalid message role: {role}")

        # Validate required content field
        if "content" not in message:
            raise MCPRequestError("Message missing required 'content' field")

        content = message["content"]
        if not isinstance(content, (str, list)):
            raise MCPRequestError("Message content must be string or array")

        # If content is array, validate each item
        if isinstance(content, list):
            for j, content_item in enumerate(content):
                if not isinstance(content_item, dict):
                    raise MCPRequestError(f"Content item {j} must be an object")
                if "type" not in content_item:
                    raise MCPRequestError(f"Content item {j} missing 'type' field")

    def _validate_temperature(self, temperature: float) -> None:
        """Validate temperature parameter.

        Args:
            temperature: Temperature to validate

        Raises:
            MCPRequestError: If temperature is invalid
        """
        if not isinstance(temperature, (int, float)):
            raise MCPRequestError("Temperature must be a number")

        if not (0.0 <= temperature <= 1.0):
            raise MCPRequestError("Temperature must be between 0.0 and 1.0")

    def _validate_max_tokens(self, max_tokens: int) -> None:
        """Validate max_tokens parameter.

        Args:
            max_tokens: Max tokens to validate

        Raises:
            MCPRequestError: If max_tokens is invalid
        """
        if not isinstance(max_tokens, int):
            raise MCPRequestError("Max tokens must be an integer")

        if max_tokens <= 0:
            raise MCPRequestError("Max tokens must be positive")

    def _validate_priority(self, priority: float, name: str) -> None:
        """Validate priority parameter.

        Args:
            priority: Priority to validate
            name: Name of the priority for error messages

        Raises:
            MCPRequestError: If priority is invalid
        """
        if not isinstance(priority, (int, float)):
            raise MCPRequestError(f"{name} must be a number")

        if not (0.0 <= priority <= 1.0):
            raise MCPRequestError(f"{name} must be between 0.0 and 1.0")

    def _validate_create_message_result(self, result: Dict[str, Any]) -> None:
        """Validate createMessage result.

        Args:
            result: Result to validate

        Raises:
            MCPRequestError: If result is invalid
        """
        # Check for required fields
        if "role" not in result:
            raise MCPRequestError("Create message result missing 'role' field")

        if "content" not in result:
            raise MCPRequestError("Create message result missing 'content' field")

        # Validate role
        role = result["role"]
        if role != "assistant":
            raise MCPRequestError(f"Create message result should have role 'assistant', got '{role}'")

        # Validate content
        content = result["content"]
        if not isinstance(content, (str, list)):
            raise MCPRequestError("Create message result content must be string or array")

    def extract_message_text(self, result: Dict[str, Any]) -> str:
        """Extract text content from createMessage result.

        Args:
            result: Result from createMessage

        Returns:
            Text content from the result
        """
        content = result.get("content", "")

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Extract text from content items
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            return " ".join(text_parts)
        else:
            return str(content)

    def format_sampling_summary(self, result: Dict[str, Any]) -> str:
        """Format a human-readable summary of sampling result.

        Args:
            result: Result from createMessage

        Returns:
            Formatted summary string
        """
        role = result.get("role", "unknown")
        content = self.extract_message_text(result)
        model = result.get("model", "Unknown model")
        stop_reason = result.get("stopReason", "unknown")

        summary_lines = [
            f"🤖 Message from {role}:",
            f"📝 Content: {content[:200]}{'...' if len(content) > 200 else ''}",
            f"🔧 Model: {model}",
            f"⏹️  Stop reason: {stop_reason}"
        ]

        return "\n".join(summary_lines)

    def _process_message_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Process the result from createMessage.

        Args:
            result: Result from createMessage

        Returns:
            Processed result

        Raises:
            MCPRequestError: If result is invalid
        """
        self._validate_create_message_result(result)
        return result
