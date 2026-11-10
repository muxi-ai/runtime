# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP HTTP+SSE Transport using SDK
# Description:  HTTP+SSE transport using official MCP SDK
# Role:         Provides MCP protocol support via SDK sse_client
# Usage:        Fallback transport for legacy MCP servers using SSE
# Author:       Muxi Framework Team
# =============================================================================

import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# MCP SDK imports
from mcp.client.sse import sse_client

from ..protocol.message_handler import MCPMessageHandler
from .auth import create_httpx_auth
from .base import CancellationToken, MCPConnectionError, MCPRequestError, MCPTimeoutError
from .sdk_session import SDKSessionTransport


class HTTPSSETransport(SDKSessionTransport):
    """MCP HTTP+SSE transport using official SDK."""

    transport_type = "http_sse"

    def __init__(self, url: str, request_timeout: int = 30, auth: Optional[Any] = None):
        """Initialize MCP SDK HTTP+SSE transport."""
        super().__init__(url, request_timeout, auth)
        self.message_handler = MCPMessageHandler()
        pass  # REMOVED: init-phase observe() call
        # Log auth config safely without exposing sensitive data
        if auth:
            pass  # REMOVED: init-phase observe() call

    def _open_streams(self) -> AbstractAsyncContextManager[Tuple[Any, Any]]:
        return sse_client(
            url=self.url,
            auth=create_httpx_auth(self.auth),
            timeout=self.request_timeout,
            sse_read_timeout=max(self.request_timeout, 60),
        )

    def _update_success_stats(self) -> None:
        """Update request/response statistics after a successful call."""
        self.last_activity = datetime.now()
        self.connection_stats["requests_sent"] += 1
        self.connection_stats["responses_received"] += 1

    async def send_request(
        self,
        request_obj: Any,
        timeout: Optional[int] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Send request using MCP SDK session."""
        if not self.connected or not self.session:
            raise MCPConnectionError("Not connected to MCP server")

        if cancellation_token:
            cancellation_token.throw_if_cancelled()

        try:
            if isinstance(request_obj, dict):
                method = request_obj.get("method")
                params = request_obj.get("params", {})
            else:
                raise MCPRequestError("Invalid request format")

            request_timeout = timeout or self.request_timeout

            # Use SDK's high-level methods
            if method == "tools/list":
                result = await asyncio.wait_for(self.session.list_tools(), timeout=request_timeout)
                # Convert to expected format
                self._update_success_stats()
                return {
                    "status": "success",
                    "result": {"tools": [tool.model_dump(by_alias=True) for tool in result.tools]},
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await asyncio.wait_for(
                    self.session.call_tool(tool_name, arguments), timeout=request_timeout
                )
                # Convert to expected format
                self._update_success_stats()
                return {"status": "success", "result": result.model_dump(by_alias=True)}
            elif method == "resources/list":
                result = await asyncio.wait_for(
                    self.session.list_resources(), timeout=request_timeout
                )
                self._update_success_stats()
                return {
                    "status": "success",
                    "result": {
                        "resources": [res.model_dump(by_alias=True) for res in result.resources]
                    },
                }
            elif method == "prompts/list":
                result = await asyncio.wait_for(
                    self.session.list_prompts(), timeout=request_timeout
                )
                self._update_success_stats()
                return {
                    "status": "success",
                    "result": {
                        "prompts": [prompt.model_dump(by_alias=True) for prompt in result.prompts]
                    },
                }
            else:
                if not isinstance(method, str):
                    raise MCPRequestError("Invalid request method")
                # For other methods, use generic approach
                # Create proper MCP message
                request_message = self.message_handler.create_request(method, params)

                # Send via write stream
                await self.write_stream.send(request_message)

                # Read response
                response_message = await asyncio.wait_for(
                    self.read_stream.receive(), timeout=request_timeout
                )

                # Parse response
                parsed = self.message_handler.parse_response(response_message)

                self._update_success_stats()
                return parsed

        except asyncio.TimeoutError as e:
            self.connection_stats["errors_encountered"] += 1
            raise MCPTimeoutError(
                "Request timed out",
                {"timeout": request_timeout, "timestamp": datetime.now().isoformat()},
            ) from e
        except Exception as e:
            self.connection_stats["errors_encountered"] += 1
            raise MCPRequestError(f"Request failed: {e}") from e

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics and performance metrics.

        Returns:
            Dict containing connection statistics
        """
        base_stats = super().get_connection_stats()

        # Add SSE-specific stats
        base_stats.update(
            {
                "transport_type": "http_sse",
                "protocol_version": "2024-11-05",
                "supports_streaming": True,
                "supports_endpoint_discovery": True,
                "has_active_session": self.session is not None,
            }
        )

        return base_stats
