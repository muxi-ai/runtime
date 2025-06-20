"""
Real MCP protocol message handling.
"""

from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCError
import uuid
import json
from typing import Dict, Any, Union


class MCPMessageHandler:
    """Real MCP protocol message handling."""

    def create_request(self, method: str, params: dict) -> SessionMessage:
        """Create proper MCP request message."""
        request = JSONRPCRequest(
            jsonrpc="2.0",
            id=str(uuid.uuid4()),
            method=method,
            params=params
        )
        return SessionMessage(message=request)

    def parse_response(self, message: Union[SessionMessage, bytes, dict, str]) -> Dict[str, Any]:
        """Parse MCP response message from various formats."""

        # Handle bytes response (need to decode and parse JSON)
        if isinstance(message, bytes):
            try:
                decoded = message.decode('utf-8')
                parsed = json.loads(decoded)
                return {
                    "status": "success",
                    "result": parsed,
                    "id": parsed.get("id"),
                    "jsonrpc": parsed.get("jsonrpc", "2.0")
                }
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                return {
                    "status": "error",
                    "error": f"Failed to parse response: {e}",
                    "id": None,
                    "jsonrpc": "2.0"
                }

        # Handle string response (parse JSON)
        if isinstance(message, str):
            try:
                parsed = json.loads(message)
                return {
                    "status": "success",
                    "result": parsed,
                    "id": parsed.get("id"),
                    "jsonrpc": parsed.get("jsonrpc", "2.0")
                }
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "error": f"Failed to parse JSON response: {e}",
                    "id": None,
                    "jsonrpc": "2.0"
                }

        # Handle dict response directly
        if isinstance(message, dict):
            return {
                "status": "success",
                "result": message,
                "id": message.get("id"),
                "jsonrpc": message.get("jsonrpc", "2.0")
            }

        # Handle SessionMessage objects
        if isinstance(message, SessionMessage):
            if isinstance(message.message, JSONRPCResponse):
                return {
                    "status": "success",
                    "result": message.message.result,
                    "id": message.message.id,
                    "jsonrpc": message.message.jsonrpc
                }
            elif isinstance(message.message, JSONRPCError):
                return {
                    "status": "error",
                    "error": {
                        "code": message.message.error.code,
                        "message": message.message.error.message,
                        "data": getattr(message.message.error, 'data', None)
                    },
                    "id": message.message.id,
                    "jsonrpc": message.message.jsonrpc
                }
            else:
                # Handle raw message data within SessionMessage
                return {
                    "status": "success",
                    "result": message.message if isinstance(message.message, dict) else {},
                    "id": getattr(message.message, "id", None),
                    "jsonrpc": getattr(message.message, "jsonrpc", "2.0")
                }

        # Fallback for unknown types
        return {
            "status": "error",
            "error": f"Unknown response type: {type(message)}",
            "id": None,
            "jsonrpc": "2.0"
        }

    def create_notification(self, method: str, params: dict) -> SessionMessage:
        """Create proper MCP notification message (no ID)."""
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        return SessionMessage(message=request)

    def validate_request(self, request: Dict[str, Any]) -> bool:
        """Validate MCP request format."""
        required_fields = ["jsonrpc", "method"]
        return all(field in request for field in required_fields)

    def validate_response(self, response: Dict[str, Any]) -> bool:
        """Validate MCP response format."""
        if not isinstance(response, dict):
            return False

        # Check for required JSONRPC fields
        if response.get("jsonrpc") != "2.0":
            return False

        # Must have either result or error, and must have id
        has_result = "result" in response
        has_error = "error" in response
        has_id = "id" in response

        return has_id and (has_result or has_error) and not (has_result and has_error)

    def format_error_response(self, request_id: str, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        """Format proper MCP error response."""
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }
        if data is not None:
            error_response["error"]["data"] = data
        return error_response
