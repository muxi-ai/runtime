# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Streamable HTTP Transport using SDK
# Description:  Streamable HTTP transport using official MCP SDK
# Role:         Provides MCP protocol support via SDK streamable_http_client
# Usage:        Primary transport for modern MCP servers
# Author:       Muxi Framework Team
# =============================================================================

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx2

# MCP SDK imports
from mcp.client.streamable_http import streamable_http_client

from ..protocol.message_handler import MCPMessageHandler
from .auth import create_httpx_auth
from .base import CancellationToken, MCPConnectionError, MCPRequestError, MCPTimeoutError
from .sdk_session import SDKSessionTransport

# How long the server may keep a response stream silent. Matches the read
# timeout the SDK's own default client uses for streamable HTTP.
SSE_READ_TIMEOUT_SECONDS = 300.0


class StreamableHTTPTransport(SDKSessionTransport):
    """MCP Streamable HTTP transport using official SDK."""

    transport_type = "streamable_http"

    def __init__(self, url: str, request_timeout: int = 30, auth: Optional[Any] = None):
        """Initialize MCP SDK streamable HTTP transport."""
        super().__init__(url, request_timeout, auth)
        self.message_handler = MCPMessageHandler()
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

    @asynccontextmanager
    async def _open_streams(self) -> AsyncIterator[Tuple[Any, Any]]:
        # The SDK takes auth and timeouts from the httpx2 client it is given
        # and does not close a client it did not create.
        async with httpx2.AsyncClient(
            auth=create_httpx_auth(self.auth),
            timeout=httpx2.Timeout(self.request_timeout, read=SSE_READ_TIMEOUT_SECONDS),
        ) as http_client:
            async with streamable_http_client(self.url, http_client=http_client) as (
                read_stream,
                write_stream,
            ):
                yield read_stream, write_stream

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

        return base_stats
