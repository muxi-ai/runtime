# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Streamable HTTP Transport using SDK
# Description:  Streamable HTTP transport using official MCP SDK
# Role:         Provides MCP protocol support via SDK streamablehttp_client
# Usage:        Primary transport for modern MCP servers
# Author:       Muxi Framework Team
# =============================================================================

from typing import Any, Dict, Optional
from datetime import datetime

# MCP SDK imports
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
)
from ..protocol.message_handler import MCPMessageHandler
from .auth import create_httpx_auth
from ... import observability


class StreamableHTTPTransport(BaseTransport):
    """MCP Streamable HTTP transport using official SDK."""

    def __init__(self, url: str, request_timeout: int = 30, auth: Optional[Any] = None):
        """Initialize MCP SDK streamable HTTP transport."""
        super().__init__(url, request_timeout, auth)
        self.message_handler = MCPMessageHandler()
        self.session = None
        self.read_stream = None
        self.write_stream = None
        self.get_session_id = None
        self.client_context = None
        pass  # REMOVED: init-phase observe() call
        # Log auth config safely without exposing sensitive data
        if auth:
            pass  # REMOVED: init-phase observe() call

    def _mask_sensitive_data(self, data: Any) -> Any:
        """
        Recursively mask sensitive data in dictionaries and lists.

        Args:
            data: The data structure to mask (dict, list, or primitive value)

        Returns:
            The same data structure with sensitive values masked
        """
        if data is None:
            return None

        # Define sensitive field patterns (case-insensitive)
        sensitive_patterns = {
            "token",
            "password",
            "key",
            "secret",
            "auth",
            "credential",
            "api_key",
            "access_token",
            "auth_token",
            "bearer_token",
            "client_secret",
            "app_secret",
            "private_key",
            "jwt",
        }

        if isinstance(data, dict):
            masked_dict = {}
            for key, value in data.items():
                # Check if the key itself indicates sensitive data
                if isinstance(key, str) and any(
                    pattern in key.lower() for pattern in sensitive_patterns
                ):
                    masked_dict[key] = "******"
                else:
                    # Recursively mask nested structures
                    masked_dict[key] = self._mask_sensitive_data(value)
            return masked_dict

        elif isinstance(data, (list, tuple)):
            # Recursively mask items in lists/tuples
            masked_items = [self._mask_sensitive_data(item) for item in data]
            return type(data)(masked_items)  # Preserve original type (list vs tuple)

        else:
            # Primitive values (str, int, bool, etc.) - return as-is
            return data

    async def connect(self) -> bool:
        """Connect using MCP SDK streamablehttp_client."""
        if self.connected:
            return True

        try:
            # Convert auth dict to httpx.Auth
            httpx_auth = create_httpx_auth(self.auth)

            # Store the context manager itself (like command transport)
            self.client_context = streamablehttp_client(
                url=self.url, auth=httpx_auth, timeout=self.request_timeout
            )

            # Enter context and get streams
            self.read_stream, self.write_stream, self.get_session_id = (
                await self.client_context.__aenter__()
            )

            # Create session for high-level operations
            self.session = ClientSession(self.read_stream, self.write_stream)
            await self.session.__aenter__()

            # Initialize the connection
            await self.session.initialize()

            self.connected = True
            self.connect_time = datetime.now()
            self.last_activity = datetime.now()

            pass  # REMOVED: init-phase observe() call
            return True

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_CONNECTION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "mcp",
                    "transport": "streamable_http",
                    "action": "connect_failed",
                    "url": self.url,
                    "error": str(e),
                },
                description=f"Connection failed: {e}"
            )
            # Clean up any partially created resources
            await self._cleanup()
            raise MCPConnectionError(f"Failed to connect to {self.url}: {e}") from e

    async def send_request(self, request_obj: Any, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Send request using MCP SDK session."""
        if not self.connected or not self.session:
            raise MCPConnectionError("Not connected to MCP server")

        method = request_obj.get("method")
        params = request_obj.get("params", {})

        try:
            # Use SDK's high-level methods
            if method == "tools/list":
                result = await self.session.list_tools()
                # Convert to expected format
                return {
                    "status": "success",
                    "result": {"tools": [tool.model_dump() for tool in result.tools]},
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await self.session.call_tool(tool_name, arguments)
                # Convert to expected format
                return {"status": "success", "result": result.model_dump()}
            elif method == "resources/list":
                result = await self.session.list_resources()
                return {
                    "status": "success",
                    "result": {"resources": [res.model_dump() for res in result.resources]},
                }
            elif method == "prompts/list":
                result = await self.session.list_prompts()
                return {
                    "status": "success",
                    "result": {"prompts": [prompt.model_dump() for prompt in result.prompts]},
                }
            else:
                # For other methods, use generic approach
                # Create proper MCP message
                request_message = self.message_handler.create_request(method, params)

                # Send via write stream
                await self.write_stream.send(request_message)

                # Read response
                response_message = await self.read_stream.receive()

                # Parse response
                parsed = self.message_handler.parse_response(response_message)

                self.last_activity = datetime.now()
                self.connection_stats["requests_sent"] += 1
                self.connection_stats["responses_received"] += 1

                return parsed

        except Exception as e:
            self.connection_stats["errors_encountered"] += 1
            raise MCPRequestError(f"Request failed: {e}") from e

    async def _cleanup(self):
        """Proper cleanup in same async context."""
        try:
            # Close session first
            if self.session:
                try:
                    await self.session.__aexit__(None, None, None)
                except Exception:
                    pass
                finally:
                    self.session = None

            # Then close client context
            if self.client_context:
                try:
                    await self.client_context.__aexit__(None, None, None)
                except Exception:
                    pass
                finally:
                    self.client_context = None

        finally:
            self.connected = False
            self.read_stream = None
            self.write_stream = None
            self.get_session_id = None

    async def disconnect(self) -> bool:
        """Disconnect from MCP server."""
        await self._cleanup()
        return True

    @property
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self.connected and self.session is not None

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics and performance metrics.

        Returns:
            Dict containing connection statistics
        """
        base_stats = super().get_connection_stats()

        # Add streamable-specific stats
        base_stats.update(
            {
                "transport_type": "streamable_http",
                "protocol_version": "2025-03-26",
                "supports_streaming": True,
                "supports_cancellation": True,
                "has_active_session": self.session is not None,
            }
        )

        # Add session ID if available
        if self.get_session_id:
            try:
                session_id = self.get_session_id()
                if session_id:
                    base_stats["session_id"] = session_id
            except Exception:
                pass

        return base_stats
