# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Real MCP Streamable HTTP Transport
# Description:  Fixed streamable HTTP transport using direct HTTP communication
# Role:         Provides real MCP protocol support bypassing SDK bugs
# Usage:        Primary transport for modern MCP servers
# Author:       Muxi Framework Team
# =============================================================================

import asyncio
import aiohttp
from typing import Any, Dict, Optional
from datetime import datetime
import uuid

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
)
from ..protocol.message_handler import MCPMessageHandler


class StreamableHTTPTransport(BaseTransport):
    """Fixed MCP Streamable HTTP transport using direct HTTP communication."""

    def __init__(
        self,
        url: str,
        request_timeout: int = 30,
        auth: Optional[Any] = None
    ):
        """Initialize fixed streamable HTTP transport."""
        super().__init__(url, request_timeout, auth)
        self.message_handler = MCPMessageHandler()
        self.session = None

    async def connect(self) -> bool:
        """Connect to the MCP server with health check."""
        error_details = {
            "url": self.url,
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Content-Type": "application/json"}
            )

            # Test connection with minimal POST request instead of GET
            # Send a simple JSON-RPC request to test connectivity
            test_request = {
                "jsonrpc": "2.0",
                "id": "test",
                "method": "tools/list",
                "params": {}
            }

            async with self.session.post(self.url, json=test_request) as response:
                if response.status == 400:
                    # 400 might be expected if server doesn't like our test request format
                    # but it means the server is responding to POST requests
                    self.connection_stats["connected"] = True
                    return True
                elif 200 <= response.status < 300:
                    # Success response is even better
                    self.connection_stats["connected"] = True
                    return True
                else:
                    # Other errors (like 405, 404) indicate real problems
                    error_details["error"] = f"Server unreachable: {response.status}"
                    raise MCPConnectionError(f"Server unreachable: {response.status}")

        except aiohttp.ClientError as e:
            error_details["error"] = f"Connection failed: {str(e)}"
            raise MCPConnectionError(f"Connection failed: {str(e)}")
        except Exception as e:
            error_details["error"] = str(e)
            raise MCPConnectionError("Failed to connect to MCP server", error_details) from e

    async def send_request(self, request: Dict[str, Any], timeout: Optional[int] = None) -> Dict[str, Any]:
        """Send request via HTTP POST."""
        if not self.session or not self.connection_stats.get("connected", False):
            raise MCPConnectionError("Not connected to MCP server")

        # Use provided timeout or fall back to instance default
        request_timeout = timeout or self.request_timeout

        try:
            # For streamable HTTP, send all requests to the base URL with JSON-RPC method in body
            method = request.get("method", "")
            params = request.get("params", {})

            # Create proper JSON-RPC request
            session_message = self.message_handler.create_request(method, params)

            # Extract the raw JSON-RPC data
            if hasattr(session_message.message, 'model_dump'):
                json_request = session_message.message.model_dump()
            else:
                # Fallback for compatibility
                json_request = {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "method": method,
                    "params": params
                }

            # Send HTTP request to base URL (streamable servers handle routing via JSON-RPC method)
            raw_response = await self._send_http_request(self.url, json_request, request_timeout)

            # Parse the response using the message handler to get consistent format
            parsed_response = self.message_handler.parse_response(raw_response)

            # Update stats
            self.connection_stats["requests_sent"] = self.connection_stats.get("requests_sent", 0) + 1
            self.connection_stats["last_activity"] = datetime.utcnow().isoformat()

            return parsed_response

        except Exception as e:
            self.connection_stats["errors"] = self.connection_stats.get("errors", 0) + 1
            raise MCPConnectionError(f"Request failed: {str(e)}")

    def _map_method_to_endpoint(self, method: str) -> str:
        """Map MCP method to HTTP endpoint."""
        # Remove the jsonrpc prefix if present and map to endpoint
        endpoint_map = {
            "tools/list": "tools/list",
            "tools/call": "tools/call",
            "resources/list": "resources/list",
            "resources/read": "resources/read",
            "prompts/list": "prompts/list",
            "prompts/get": "prompts/get",
            "sampling/createMessage": "sampling/createMessage",
            "initialize": "initialize",
            "ping": "ping"
        }

        return endpoint_map.get(method, method.replace("/", "/"))

    async def _send_http_request(self, url: str, json_request: dict, timeout: int) -> dict:
        """Send HTTP POST request to MCP server."""
        try:
            # Send HTTP POST request using asyncio.wait_for for Python 3.10 compatibility
            async def make_request():
                async with self.session.post(
                    url,
                    json=json_request,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        response_text = await response.text()
                        raise MCPRequestError(f"HTTP {response.status} for {url}: {response_text}")

            return await asyncio.wait_for(make_request(), timeout=timeout)

        except asyncio.TimeoutError:
            self.connection_stats['errors_encountered'] += 1
            raise MCPRequestError(f"Request timeout after {timeout}s")
        except Exception as e:
            self.connection_stats['errors_encountered'] += 1
            raise MCPRequestError(f"Request failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self.session:
            await self.session.close()
            self.session = None

        self.connection_stats["connected"] = False
        self.connection_stats["disconnected_at"] = datetime.utcnow().isoformat()

    @property
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self.session is not None and self.connection_stats.get("connected", False)

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics and performance metrics.

        Returns:
            Dict containing connection statistics
        """
        base_stats = super().get_connection_stats()

        # Add streamable-specific stats
        base_stats.update({
            "transport_type": "streamable_http",
            "protocol_version": "2025-03-26",
            "supports_streaming": True,
            "supports_cancellation": True,
        })

        # Add session duration if connected
        if self.connected and self.connect_time:
            session_duration = (datetime.now() - self.connect_time).total_seconds()
            base_stats["session_duration_s"] = session_duration

        # Add session info if available
        if self.session:
            base_stats["has_active_session"] = True

        # Calculate efficiency metrics
        if self.connection_stats['requests_sent'] > 0:
            base_stats['success_rate'] = 1.0 - (
                self.connection_stats['errors_encountered'] / self.connection_stats['requests_sent']
            )
            base_stats['avg_bytes_per_request'] = (
                self.connection_stats['bytes_sent'] / self.connection_stats['requests_sent']
            )

        if self.connection_stats['responses_received'] > 0:
            base_stats['avg_bytes_per_response'] = (
                self.connection_stats['bytes_received'] / self.connection_stats['responses_received']
            )

        return base_stats

    def get_transport_info(self) -> Dict[str, Any]:
        """
        Get transport information and capabilities.

        Returns:
            Dict containing transport information
        """
        return {
            "type": "streamable_http",
            "protocol_version": "2025-03-26",
            "supports_streaming": True,
            "supports_cancellation": True,
            "supports_batching": False,  # Not implemented yet
            "max_concurrent_requests": 10,  # HTTP allows multiple concurrent requests
            "url": self.url,
            "connected": self.connected,
            "has_active_session": self.session is not None
        }
