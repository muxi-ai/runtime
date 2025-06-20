# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Streamable HTTP Transport - Modern Streamable Transport
# Description:  Streamable HTTP transport implementation for MCP servers
# Role:         Provides modern Streamable HTTP transport (MCP 2025-03-26)
# Usage:        Primary transport for modern MCP servers with enhanced performance
# Author:       Muxi Framework Team
# =============================================================================

import uuid
import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

# MCP SDK imports - Streamable HTTP available in MCP >=1.9.0
from mcp.client.streamable_http import streamablehttp_client

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
    MCPCancelledError,
    CancellationToken
)


class StreamableHTTPTransport(BaseTransport):
    """
    Streamable HTTP transport for MCP servers (MCP Protocol 2025-03-26).

    This transport provides modern protocol support with:
    - Optimized performance over HTTP+SSE
    - Real-time bidirectional streaming
    - Enhanced error handling and observability
    - Full cancellation support
    """

    def __init__(
        self,
        url: str,
        request_timeout: int = 30,
        auth: Optional[Any] = None
    ):
        """
        Initialize Streamable HTTP transport.

        Args:
            url: MCP server URL (must include protocol)
            request_timeout: Default timeout for requests in seconds
            auth: Optional authentication configuration
        """
        super().__init__(url, request_timeout, auth)
        self.protocol_version = "2025-03-26"
        self.transport_type = "streamable_http"

        # Connection state
        self.context_manager = None
        self.read_stream = None
        self.write_stream = None
        self.get_session_id = None

    async def connect(self) -> bool:
        """
        Establish connection to the MCP server using Streamable HTTP.

        Returns:
            bool: True if connection successful

        Raises:
            MCPConnectionError: If connection fails
            MCPTimeoutError: If connection times out
        """
        if self.connected:
            return True

        try:
            # Use asyncio.wait_for for Python 3.10 compatibility
            self.context_manager = streamablehttp_client(
                url=self.url,
                # Add auth headers if provided
                **({"headers": self.auth} if self.auth else {})
            )

            # Enter the context manager and get streams
            streams = await asyncio.wait_for(
                self.context_manager.__aenter__(),
                timeout=self.request_timeout
            )

            self.read_stream, self.write_stream, self.get_session_id = streams

            # Mark as connected and update stats
            self.connected = True
            self.connect_time = datetime.now()
            self.last_activity = datetime.now()

            return True

        except asyncio.TimeoutError as e:
            error_details = {
                "url": self.url,
                "timeout_seconds": self.request_timeout,
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            raise MCPTimeoutError("Streamable HTTP connection timed out", error_details) from e

        except Exception as e:
            error_details = {
                "url": self.url,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            self.connected = False
            raise MCPConnectionError("Failed to connect via Streamable HTTP", error_details) from e

    async def send_request(
        self,
        request_obj: Any,
        timeout: Optional[int] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> Dict[str, Any]:
        """
        Send request to the MCP server using Streamable HTTP protocol.

        Args:
            request_obj: Request object (dict or object with model_dump method)
            timeout: Optional timeout override for this request
            cancellation_token: Optional cancellation token

        Returns:
            Dict containing the response from the server

        Raises:
            MCPConnectionError: If not connected or connection issues
            MCPRequestError: If request is invalid
            MCPTimeoutError: If request times out
        """
        if not self.connected or not self.write_stream or not self.read_stream:
            raise MCPConnectionError(
                "Not connected to Streamable HTTP server",
                {"url": self.url, "timestamp": datetime.now().isoformat()}
            )

        if cancellation_token:
            cancellation_token.throw_if_cancelled()

        # Initialize request_data for error handling
        request_data = {}

        try:
            # Validate and prepare request
            if isinstance(request_obj, dict):
                if "method" not in request_obj:
                    raise MCPRequestError("Request missing required 'method' field")
                request_data = request_obj.copy()
            elif hasattr(request_obj, 'model_dump'):
                request_data = request_obj.model_dump()
            else:
                raise MCPRequestError("Invalid request object: must be dict or have model_dump() method")

            # Add request ID if not present
            if 'id' not in request_data:
                request_data['id'] = str(uuid.uuid4())

            # Track request size
            request_json = json.dumps(request_data)
            self.connection_stats['bytes_sent'] += len(request_json.encode('utf-8'))
            self.connection_stats['requests_sent'] += 1

            # Use the timeout override or default
            request_timeout = timeout or self.request_timeout

            # Send request through write stream and read response from read stream
            # Using asyncio.wait_for for Python 3.10 compatibility
            async def _send_and_receive():
                # Write request to stream
                await self.write_stream.send(request_json.encode('utf-8'))

                # Read response from stream
                response_bytes = await self.read_stream.receive()
                response_data = json.loads(response_bytes.decode('utf-8'))

                return response_data

            response_data = await asyncio.wait_for(
                _send_and_receive(),
                timeout=request_timeout
            )

            self.last_activity = datetime.now()
            self.connection_stats['responses_received'] += 1

            # Return the response in standard format
            return {
                "result": response_data,
                "status": "success"
            }

        except MCPRequestError:
            # Let MCPRequestError propagate as-is (validation errors, etc.)
            raise

        except asyncio.TimeoutError as e:
            error_details = {
                "url": self.url,
                "method": request_data.get('method', 'unknown'),
                "timeout_seconds": request_timeout,
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            self.connection_stats['errors_encountered'] += 1
            raise MCPTimeoutError("Streamable HTTP request timed out", error_details) from e

        except Exception as e:
            error_details = {
                "url": self.url,
                "method": request_data.get('method', 'unknown'),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            self.connection_stats['errors_encountered'] += 1
            raise MCPConnectionError("Streamable HTTP request failed", error_details) from e

    async def disconnect(self) -> bool:
        """
        Disconnect from the MCP server.

        Returns:
            bool: True if disconnection successful
        """
        if not self.connected:
            return True

        try:
            if self.context_manager:
                await self.context_manager.__aexit__(None, None, None)
        except Exception:
            # Log but don't raise - we want to mark as disconnected regardless
            pass
        finally:
            self.connected = False
            self.context_manager = None
            self.read_stream = None
            self.write_stream = None
            self.get_session_id = None

        return True

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics and performance metrics.

        Returns:
            Dict containing connection statistics
        """
        base_stats = super().get_connection_stats()

        # Add streamable-specific stats
        base_stats.update({
            "transport_type": self.transport_type,
            "protocol_version": self.protocol_version,
            "supports_streaming": True,
            "supports_cancellation": True,
        })

        # Add session duration if connected
        if self.connected and self.connect_time:
            session_duration = (datetime.now() - self.connect_time).total_seconds()
            base_stats["session_duration_s"] = session_duration

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
            "type": self.transport_type,
            "protocol_version": self.protocol_version,
            "supports_streaming": True,
            "supports_cancellation": True,
            "supports_batching": False,  # Not implemented yet
            "max_concurrent_requests": 1,  # Current limitation
            "url": self.url,
            "connected": self.connected
        }
