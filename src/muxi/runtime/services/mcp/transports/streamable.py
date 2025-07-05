# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Streamable HTTP Transport using SDK
# Description:  Streamable HTTP transport using official MCP SDK
# Role:         Provides MCP protocol support via SDK streamablehttp_client
# Usage:        Primary transport for modern MCP servers
# Author:       Muxi Framework Team
# =============================================================================

import httpx
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
        print(f"[StreamableHTTP] Initialized with URL: {url}")
        print(f"[StreamableHTTP] Auth config: {auth}")

    async def connect(self) -> bool:
        """Connect using MCP SDK streamablehttp_client."""
        if self.connected:
            return True

        try:
            # Convert auth dict to httpx.Auth
            httpx_auth = self._create_httpx_auth(self.auth)

            # Use SDK client
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

            print(f"[StreamableHTTP] Connected successfully to {self.url}")
            return True

        except Exception as e:
            print(f"[StreamableHTTP] Connection failed: {e}")
            # Clean up any partially created resources
            await self._cleanup()
            raise MCPConnectionError(f"Failed to connect to {self.url}: {e}")

    def _create_httpx_auth(self, auth_config: Optional[Dict]) -> Optional[httpx.Auth]:
        """Convert auth config to httpx.Auth object."""
        if not auth_config:
            return None

        auth_type = auth_config.get("type", "bearer").lower()

        if auth_type == "bearer" and "token" in auth_config:
            # Custom Bearer auth class
            class BearerAuth(httpx.Auth):
                def __init__(self, token):
                    self.token = token

                def auth_flow(self, request):
                    request.headers["Authorization"] = f"Bearer {self.token}"
                    yield request

            return BearerAuth(auth_config["token"])

        elif auth_type == "basic":
            return httpx.BasicAuth(
                username=auth_config.get("username", ""), password=auth_config.get("password", "")
            )

        elif auth_type == "api_key":
            # API key auth
            class ApiKeyAuth(httpx.Auth):
                def __init__(self, key, header_name=None):
                    self.key = key
                    self.header_name = header_name or "X-API-Key"

                def auth_flow(self, request):
                    request.headers[self.header_name] = self.key
                    yield request

            return ApiKeyAuth(auth_config.get("key", ""), auth_config.get("header_name"))

        return None

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
            raise MCPRequestError(f"Request failed: {e}")

    async def _cleanup(self):
        """Clean up resources even if not fully connected."""
        try:
            # Close session if it exists
            if self.session:
                try:
                    await self.session.__aexit__(None, None, None)
                except Exception:
                    pass

            # Close client context if it exists
            if self.client_context:
                try:
                    await self.client_context.__aexit__(None, None, None)
                except Exception:
                    pass

        finally:
            self.connected = False
            self.session = None
            self.read_stream = None
            self.write_stream = None
            self.get_session_id = None
            self.client_context = None

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
