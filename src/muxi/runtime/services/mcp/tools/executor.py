"""
Real MCP tool execution using tools/call protocol.
"""

from typing import Dict, Any
from datetime import datetime
from ..transports.base import BaseTransport, MCPTimeoutError


class MCPToolExecutor:
    """Real MCP tool execution using tools/call protocol."""

    async def execute_tool(
        self,
        transport: BaseTransport,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: int = None,
    ) -> Dict[str, Any]:
        """Execute tool using real MCP tools/call method."""
        try:
            # Send real tools/call request
            response = await transport.send_request(
                {"method": "tools/call", "params": {"name": tool_name, "arguments": arguments}},
                timeout=timeout,
            )

            return self._process_tool_result(response, tool_name)

        except MCPTimeoutError as e:
            return self._process_tool_timeout(tool_name, timeout, e)
        except Exception as e:
            return self._process_tool_error(tool_name, arguments, e)

    def _process_tool_result(self, response: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """Process successful tool result."""
        if "result" in response:
            # Standard MCP response format
            result = response["result"]
            return {
                "status": "success",
                "content": result.get("content", []),
                "isError": result.get("isError", False),
                "metadata": result.get("_meta", {}),
                "tool_name": tool_name,
                "execution_time": datetime.now().isoformat(),
            }
        elif "error" in response:
            # MCP error response
            error = response["error"]
            return {
                "status": "error",
                "error": {
                    "code": error.get("code", -1),
                    "message": error.get("message", "Unknown error"),
                    "data": error.get("data", {}),
                },
                "tool_name": tool_name,
                "execution_time": datetime.now().isoformat(),
            }
        else:
            # Direct result format (legacy compatibility)
            return {
                "status": "success",
                "content": response if isinstance(response, list) else [response],
                "isError": False,
                "metadata": {},
                "tool_name": tool_name,
                "execution_time": datetime.now().isoformat(),
            }

    def _process_tool_timeout(
        self, tool_name: str, timeout: int, error: MCPTimeoutError
    ) -> Dict[str, Any]:
        """Process tool execution timeout."""
        return {
            "status": "timeout",
            "error": f"Tool execution timed out after {timeout} seconds",
            "tool_name": tool_name,
            "timeout_seconds": timeout,
            "execution_time": datetime.now().isoformat(),
            "details": str(error),
        }

    def _process_tool_error(
        self, tool_name: str, arguments: Dict[str, Any], error: Exception
    ) -> Dict[str, Any]:
        """Process tool execution error."""
        return {
            "status": "error",
            "error": f"Tool execution failed: {error}",
            "tool_name": tool_name,
            "arguments": arguments,
            "execution_time": datetime.now().isoformat(),
            "error_type": type(error).__name__,
        }

    def validate_arguments(
        self, arguments: Dict[str, Any], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate tool arguments against schema."""
        validation_result = {"valid": True, "errors": [], "warnings": []}

        # Check required parameters
        required = schema.get("required", [])
        for param in required:
            if param not in arguments:
                validation_result["valid"] = False
                validation_result["errors"].append(f"Missing required parameter: {param}")

        # Check parameter types (basic validation)
        properties = schema.get("properties", {})
        for param, value in arguments.items():
            if param in properties:
                param_schema = properties[param]
                param_type = param_schema.get("type")

                if param_type and not self._validate_type(value, param_type):
                    validation_result["valid"] = False
                    validation_result["errors"].append(
                        f"Parameter '{param}' should be of type {param_type}, got {type(value).__name__}"
                    )

        # Check for unknown parameters
        for param in arguments:
            if param not in properties:
                validation_result["warnings"].append(f"Unknown parameter: {param}")

        return validation_result

    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Basic type validation for tool parameters."""
        type_mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
        }

        if expected_type in type_mapping:
            expected_python_type = type_mapping[expected_type]
            return isinstance(value, expected_python_type)

        return True  # Unknown type, allow it

    def format_tool_result(self, result: Dict[str, Any]) -> str:
        """Format tool execution result for display."""
        if result["status"] == "success":
            content = result.get("content", [])
            if isinstance(content, list) and content:
                # Format content items
                formatted_content = []
                for item in content:
                    if isinstance(item, dict):
                        if "text" in item:
                            formatted_content.append(item["text"])
                        elif "type" in item and "text" in item:
                            formatted_content.append(f"[{item['type']}] {item['text']}")
                        else:
                            formatted_content.append(str(item))
                    else:
                        formatted_content.append(str(item))

                return "\n".join(formatted_content)
            elif isinstance(content, str):
                return content
            else:
                return str(content)

        elif result["status"] == "error":
            error_info = result.get("error", "Unknown error")
            if isinstance(error_info, dict):
                return f"Error: {error_info.get('message', 'Unknown error')}"
            return f"Error: {error_info}"

        elif result["status"] == "timeout":
            return f"Timeout: {result.get('error', 'Tool execution timed out')}"

        else:
            return f"Unknown status: {result.get('status', 'unknown')}"
