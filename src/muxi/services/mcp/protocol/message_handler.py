"""
Real MCP protocol message handling.
"""

from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCError
from ....utils.id_generator import generate_nanoid
import json
import logging
from typing import Dict, Any, Union

logger = logging.getLogger(__name__)


class MCPMessageHandler:
    """Real MCP protocol message handling."""

    def create_request(self, method: str, params: dict) -> SessionMessage:
        """Create proper MCP request message."""
        request = JSONRPCRequest(jsonrpc="2.0", id=f"rpc_{generate_nanoid()}", method=method, params=params)
        return SessionMessage(message=request)

    def parse_response(self, message: Union[SessionMessage, bytes, dict, str]) -> Dict[str, Any]:
        """Parse MCP response message from various formats."""

        # Handle bytes response (need to decode and parse JSON)
        if isinstance(message, bytes):
            try:
                decoded = message.decode("utf-8")
                parsed = json.loads(decoded)
                return {
                    "status": "success",
                    "result": parsed,
                    "id": parsed.get("id"),
                    "jsonrpc": parsed.get("jsonrpc", "2.0"),
                }
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                return {
                    "status": "error",
                    "error": f"Failed to parse response: {e}",
                    "id": None,
                    "jsonrpc": "2.0",
                }

        # Handle string response (parse JSON)
        if isinstance(message, str):
            try:
                parsed = json.loads(message)
                return {
                    "status": "success",
                    "result": parsed,
                    "id": parsed.get("id"),
                    "jsonrpc": parsed.get("jsonrpc", "2.0"),
                }
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "error": f"Failed to parse JSON response: {e}",
                    "id": None,
                    "jsonrpc": "2.0",
                }

        # Handle dict response directly
        if isinstance(message, dict):
            return {
                "status": "success",
                "result": message,
                "id": message.get("id"),
                "jsonrpc": message.get("jsonrpc", "2.0"),
            }

        # Handle SessionMessage objects
        if isinstance(message, SessionMessage):
            # Check if message.message is a JSONRPCMessage with a root attribute
            if hasattr(message.message, "root"):
                # Handle JSONRPCMessage wrapper
                root = message.message.root
                if isinstance(root, JSONRPCResponse):
                    return {
                        "status": "success",
                        "result": root.result,
                        "id": root.id,
                        "jsonrpc": root.jsonrpc,
                    }
                elif isinstance(root, JSONRPCError):
                    return {
                        "status": "error",
                        "error": {
                            "code": root.error.code,
                            "message": root.error.message,
                            "data": getattr(root.error, "data", None),
                        },
                        "id": root.id,
                        "jsonrpc": root.jsonrpc,
                    }
            # Fall back to direct handling
            elif isinstance(message.message, JSONRPCResponse):
                return {
                    "status": "success",
                    "result": message.message.result,
                    "id": message.message.id,
                    "jsonrpc": message.message.jsonrpc,
                }
            elif isinstance(message.message, JSONRPCError):
                return {
                    "status": "error",
                    "error": {
                        "code": message.message.error.code,
                        "message": message.message.error.message,
                        "data": getattr(message.message.error, "data", None),
                    },
                    "id": message.message.id,
                    "jsonrpc": message.message.jsonrpc,
                }
            else:
                # Handle raw message data within SessionMessage
                return {
                    "status": "success",
                    "result": message.message if isinstance(message.message, dict) else {},
                    "id": getattr(message.message, "id", None),
                    "jsonrpc": getattr(message.message, "jsonrpc", "2.0"),
                }

        # Fallback for unknown types
        return {
            "status": "error",
            "error": f"Unknown response type: {type(message)}",
            "id": None,
            "jsonrpc": "2.0",
        }

    def create_notification(self, method: str, params: dict) -> SessionMessage:
        """Create proper MCP notification message (no ID)."""
        # Create JSONRPCRequest without ID (notifications don't have IDs per JSON-RPC spec)
        notification = JSONRPCRequest(
            jsonrpc="2.0",
            method=method,
            params=params,
            id=None,  # Notifications explicitly have no ID
        )
        return SessionMessage(message=notification)

    def validate_request(self, request: Dict[str, Any]) -> bool:
        """Validate MCP request format according to JSON-RPC 2.0 specification.

        Args:
            request: Request dictionary to validate

        Returns:
            True if request is valid, False otherwise
        """
        try:
            # Basic type check
            if not isinstance(request, dict):
                logger.debug(f"Request is not a dictionary: {type(request)}")
                return False

            # Validate required 'jsonrpc' field
            if "jsonrpc" not in request:
                logger.debug("Request missing required 'jsonrpc' field")
                return False

            jsonrpc_version = request["jsonrpc"]
            if not isinstance(jsonrpc_version, str):
                logger.debug(f"jsonrpc field is not a string: {type(jsonrpc_version)}")
                return False

            if jsonrpc_version != "2.0":
                logger.debug(f"Invalid jsonrpc version: {jsonrpc_version}, expected '2.0'")
                return False

            # Validate required 'method' field
            if "method" not in request:
                logger.debug("Request missing required 'method' field")
                return False

            method = request["method"]
            if not isinstance(method, str):
                logger.debug(f"method field is not a string: {type(method)}")
                return False

            if not method.strip():
                logger.debug("method field is empty or whitespace only")
                return False

            # Validate optional 'params' field
            if "params" in request:
                params = request["params"]
                # JSON-RPC allows params to be Object (dict) or Array (list)
                if not isinstance(params, (dict, list)):
                    logger.debug(f"params field must be dict or list: {type(params)}")
                    return False

            # Validate optional 'id' field
            if "id" in request:
                request_id = request["id"]
                # JSON-RPC allows id to be String, Number, or null
                if not isinstance(request_id, (str, int, float, type(None))):
                    logger.debug(f"id field must be string, number, or null: {type(request_id)}")
                    return False

            return True

        except Exception as e:
            logger.debug(f"Error validating request: {e}")
            return False

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

    def format_error_response(
        self, request_id: str, code: int, message: str, data: Any = None
    ) -> Dict[str, Any]:
        """Format proper MCP error response."""
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        if data is not None:
            error_response["error"]["data"] = data
        return error_response
