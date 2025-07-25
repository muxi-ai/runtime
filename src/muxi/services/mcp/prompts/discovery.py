"""MCP Prompts discovery and retrieval implementation."""

from typing import List, Dict, Any, Optional
from ..transports.base import BaseTransport
from ..protocol.message_handler import MCPMessageHandler
from ....datatypes.exceptions import MCPRequestError


class MCPPromptDiscovery:
    """MCP Prompts discovery and retrieval using prompts protocol."""

    def __init__(self):
        """Initialize prompt discovery."""
        self.message_handler = MCPMessageHandler()

    def _extract_result_from_response(self, response: Any, method_name: str) -> Dict[str, Any]:
        """Extract result from MCP response with validation.

        Args:
            response: Raw response from MCP server
            method_name: Name of the MCP method for error context

        Returns:
            Extracted result dictionary

        Raises:
            MCPRequestError: If response is invalid or malformed
        """
        # Validate response type
        if isinstance(response, dict):
            result = response.get("result", response)

            # Validate result is also a dictionary
            if not isinstance(result, dict):
                raise MCPRequestError(
                    f"Invalid {method_name} response: result must be a dictionary, "
                    f"got {type(result).__name__}"
                )

            return result
        else:
            # Handle non-dict response
            raise MCPRequestError(
                f"Invalid {method_name} response: expected dictionary, "
                f"got {type(response).__name__}"
            )

    async def list_prompts(self, transport: BaseTransport) -> List[Dict[str, Any]]:
        """List available prompts using prompts/list method.

        Args:
            transport: MCP transport to use for communication

        Returns:
            List of prompt definitions with metadata

        Raises:
            MCPRequestError: If prompt listing fails
        """
        try:
            # Send request to MCP server
            response = await transport.send_request({
                "method": "prompts/list",
                "params": {}
            })

            # Extract result using helper method
            result = self._extract_result_from_response(response, "prompts/list")
            prompts = result.get("prompts", [])

            # Validate and process prompts
            return self._process_prompt_definitions(prompts)

        except Exception as e:
            raise MCPRequestError(f"Failed to list prompts: {e}")

    async def get_prompt(
        self,
        transport: BaseTransport,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get prompt with arguments using prompts/get method.

        Args:
            transport: MCP transport to use for communication
            name: Name of the prompt to get
            arguments: Optional arguments for prompt templating

        Returns:
            Prompt result with messages and metadata

        Raises:
            MCPRequestError: If prompt retrieval fails
        """
        try:
            # Prepare request parameters
            params = {"name": name}
            if arguments:
                params["arguments"] = arguments

            # Send request to MCP server
            response = await transport.send_request({
                "method": "prompts/get",
                "params": params
            })

            # Extract result using helper method
            result = self._extract_result_from_response(response, "prompts/get")
            return self._process_prompt_result(result)

        except Exception as e:
            raise MCPRequestError(f"Failed to get prompt '{name}': {e}")

    def _process_prompt_definitions(self, prompts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process and validate prompt definitions.

        Args:
            prompts: Raw prompt definitions from server

        Returns:
            Processed and validated prompt definitions

        Raises:
            MCPRequestError: If any prompt definition is invalid
        """
        processed_prompts = []

        for prompt in prompts:
            # Validate the prompt definition
            self._validate_prompt_definition(prompt)

            # Add to processed list
            processed_prompts.append({
                "name": prompt["name"],
                "description": prompt.get("description", ""),
                "arguments": prompt.get("arguments", []),
                "metadata": prompt.get("metadata", {}),
                "protocol_compliant": True
            })

        return processed_prompts

    def _process_prompt_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Process prompt result from prompts/get method.

        Args:
            result: Raw result from server

        Returns:
            Processed prompt result

        Raises:
            MCPRequestError: If result is invalid
        """
        # Validate the prompt content
        self._validate_prompt_content(result)

        return {
            "messages": result["messages"],
            "description": result.get("description", ""),
            "metadata": result.get("_meta", {}),
            "status": "success"
        }

    def _validate_prompt_definition(self, prompt: Dict[str, Any]) -> None:
        """Validate prompt definition structure.

        Args:
            prompt: Prompt definition to validate

        Raises:
            MCPRequestError: If prompt definition is invalid
        """
        required_fields = ["name"]

        for field in required_fields:
            if field not in prompt:
                raise MCPRequestError(f"Prompt definition missing required field: {field}")

        # Validate name is string
        if not isinstance(prompt["name"], str):
            raise MCPRequestError("Prompt name must be a string")

        # Validate optional fields if present
        if "description" in prompt and not isinstance(prompt["description"], str):
            raise MCPRequestError("Prompt description must be a string")

        if "arguments" in prompt:
            arguments = prompt["arguments"]
            if not isinstance(arguments, list):
                raise MCPRequestError("Prompt arguments must be a list")

            # Validate each argument definition
            for arg in arguments:
                if not isinstance(arg, dict):
                    raise MCPRequestError("Each prompt argument must be an object")
                if "name" not in arg:
                    raise MCPRequestError("Prompt argument missing required 'name' field")
                if not isinstance(arg["name"], str):
                    raise MCPRequestError("Prompt argument name must be a string")

    def _validate_prompt_content(self, content: Dict[str, Any]) -> None:
        """Validate prompt content structure.

        Args:
            content: Prompt content to validate

        Raises:
            MCPRequestError: If prompt content is invalid
        """
        # Check for required messages field
        if "messages" not in content:
            raise MCPRequestError("Prompt content missing required 'messages' field")

        messages = content["messages"]
        if not isinstance(messages, list):
            raise MCPRequestError("Prompt messages must be a list")

        # Validate each message
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

            content_value = message["content"]
            if not isinstance(content_value, (str, list)):
                raise MCPRequestError(f"Message {i} content must be string or array")

            # If content is array, validate each item
            if isinstance(content_value, list):
                for j, content_item in enumerate(content_value):
                    if not isinstance(content_item, dict):
                        raise MCPRequestError(f"Message {i} content item {j} must be an object")
                    if "type" not in content_item:
                        raise MCPRequestError(f"Message {i} content item {j} missing 'type' field")

    def format_prompt_summary(self, prompts: List[Dict[str, Any]]) -> str:
        """Format a human-readable summary of available prompts.

        Args:
            prompts: List of prompt definitions

        Returns:
            Formatted summary string
        """
        if not prompts:
            return "No prompts available"

        summary_lines = [f"💬 Available Prompts ({len(prompts)} total):"]

        for prompt in prompts:
            name = prompt.get("name", "Unnamed")
            description = prompt.get("description", "No description")
            arguments = prompt.get("arguments", [])

            summary_lines.append(f"\n  📝 {name}")
            summary_lines.append(f"     {description}")

            if arguments:
                arg_names = [arg.get("name", "?") for arg in arguments]
                summary_lines.append(f"     Arguments: {', '.join(arg_names)}")

        return "\n".join(summary_lines)

    def extract_prompt_text(self, prompt_content: Dict[str, Any]) -> str:
        """Extract text content from prompt messages.

        Args:
            prompt_content: Prompt content with messages

        Returns:
            Combined text from all messages
        """
        messages = prompt_content.get("messages", [])
        text_parts = []

        for message in messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")

            if isinstance(content, str):
                text_parts.append(f"[{role.upper()}] {content}")
            elif isinstance(content, list):
                # Extract text from content items
                content_texts = []
                for item in content:
                    if item.get("type") == "text":
                        content_texts.append(item.get("text", ""))
                if content_texts:
                    text_parts.append(f"[{role.upper()}] {' '.join(content_texts)}")

        return "\n\n".join(text_parts)

    def get_prompt_arguments_info(self, prompt: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get detailed argument information for a prompt.

        Args:
            prompt: Prompt definition

        Returns:
            List of argument details with name, description, required status, etc.
        """
        arguments = prompt.get("arguments", [])
        arg_info = []

        for arg in arguments:
            info = {
                "name": arg.get("name", ""),
                "description": arg.get("description", ""),
                "required": arg.get("required", False),
                "type": arg.get("type", "string"),
            }

            # Add default value if present
            if "default" in arg:
                info["default"] = arg["default"]

            arg_info.append(info)

        return arg_info
