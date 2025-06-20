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
import time
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

    This transport implementation uses the modern Streamable HTTP protocol
    for communicating with MCP servers, offering superior performance over
    HTTP+SSE through:
    - Optimized request/response cycles
    - Better resource utilization
    - Modern protocol design
    - Enhanced error handling
    """

    def __init__(self, url: str, request_timeout: int = 60):
        """
        Initialize with server URL.

        Args:
            url: Base URL of the MCP server supporting Streamable HTTP protocol
            request_timeout: Timeout for requests in seconds
        """
        self.url = url.rstrip('/')
        self.request_timeout = request_timeout
        self.client = None
        self.connected = False
        self.connect_time = None
        self.last_activity = None
        self.connection_stats = {
            'requests_sent': 0,
            'responses_received': 0,
            'errors_encountered': 0,
            'bytes_sent': 0,
            'bytes_received': 0
        }

    async def connect(self) -> bool:
        """
        Connect to the MCP server using Streamable HTTP protocol.

        Establishes a connection using the MCP Python SDK's streamablehttp_client
        for modern protocol support with optimized performance characteristics.

        Returns:
            bool: True if connected successfully

        Raises:
            MCPConnectionError: If connection fails
            MCPTimeoutError: If connection times out
            MCPCancelledError: If connection is cancelled
        """
        try:
            # start_time = time.time()  # TODO: Use for observability timing

            # Create Streamable HTTP client using MCP SDK
            self.client = streamablehttp_client(
                url=self.url,
                timeout=self.request_timeout
            )

            # Attempt to establish connection
            await self.client.connect()

            # connection_time = time.time() - start_time  # TODO: Use for observability
            self.connected = True
            self.connect_time = datetime.now()
            self.last_activity = self.connect_time

            # Log successful connection
            # TODO: Add observability logging
            # connection_details = {
            #     "url": self.url,
            #     "protocol": "streamable_http",
            #     "connection_time_s": connection_time,
            #     "timestamp": self.connect_time.isoformat(),
            #     "mcp_version": "2025-03-26"
            # }
            # observability.log_event("MCP_SERVER_CONNECTED", connection_details)

            return True

        except asyncio.TimeoutError as e:
            error_details = {
                "url": self.url,
                "timeout_seconds": self.request_timeout,
                "error_type": "timeout",
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            self.connection_stats['errors_encountered'] += 1
            raise MCPTimeoutError("Connection to Streamable HTTP endpoint timed out", error_details) from e

        except asyncio.CancelledError:
            raise MCPCancelledError(
                "Streamable HTTP connection attempt was cancelled",
                {"url": self.url, "timestamp": datetime.now().isoformat()}
            )

        except Exception as e:
            error_details = {
                "url": self.url,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            self.connection_stats['errors_encountered'] += 1
            raise MCPConnectionError("Error connecting to Streamable HTTP MCP server", error_details) from e

    async def send_request(
        self, request_obj: Any, cancellation_token: Optional[CancellationToken] = None
    ) -> Dict[str, Any]:
        """
        Send request to the MCP server using Streamable HTTP protocol.

        Args:
            request_obj: A request object with model_dump() method or a dictionary
            cancellation_token: Optional token to cancel the operation

        Returns:
            Dict containing the response from the server

        Raises:
            MCPConnectionError: If not connected or connection issues
            MCPRequestError: If request is invalid or server returns error
            MCPTimeoutError: If request times out
            MCPCancelledError: If operation is cancelled
        """
        if not self.connected or not self.client:
            raise MCPConnectionError(
                "Cannot send request: not connected to Streamable HTTP server",
                {"url": self.url, "timestamp": datetime.now().isoformat()}
            )

        if cancellation_token:
            cancellation_token.throw_if_cancelled()

        try:
            start_time = time.time()

            # Prepare request data
            if hasattr(request_obj, 'model_dump'):
                request_data = request_obj.model_dump()
            elif isinstance(request_obj, dict):
                request_data = request_obj
            else:
                raise MCPRequestError(
                    "Invalid request object: must be dict or have model_dump() method",
                    {"request_type": type(request_obj).__name__}
                )

            # Add request ID if not present
            if 'id' not in request_data:
                request_data['id'] = str(uuid.uuid4())

            # Track request size
            request_json = json.dumps(request_data)
            self.connection_stats['bytes_sent'] += len(request_json.encode('utf-8'))
            self.connection_stats['requests_sent'] += 1

            # Send request using Streamable HTTP client
            response = await self.client.send_request(request_data)

            request_time = time.time() - start_time
            self.last_activity = datetime.now()

            # Track response
            self.connection_stats['responses_received'] += 1
            if isinstance(response, dict):
                response_json = json.dumps(response)
                self.connection_stats['bytes_received'] += len(response_json.encode('utf-8'))

            # Handle modern protocol features (MCP 2025-06-18)
            if hasattr(response, 'content') and hasattr(response, 'isError'):
                return {
                    "result": {
                        "content": response.content,
                        "isError": response.isError,
                        # Support for resource links if present
                        "links": getattr(response, 'links', []),
                        # Include metadata for structured output
                        "_meta": getattr(response, '_meta', {})
                    },
                    "status": "success" if not response.isError else "error"
                }

            # TODO: Add observability logging
            # observability.log_event("MCP_REQUEST_COMPLETED", {
            #     "url": self.url,
            #     "method": request_data.get('method'),
            #     "request_time_s": request_time,
            #     "protocol": "streamable_http"
            # })

            # Return legacy format for older servers
            return response

        except asyncio.TimeoutError as e:
            error_details = {
                "url": self.url,
                "method": request_data.get('method') if 'request_data' in locals() else 'unknown',
                "timeout_seconds": self.request_timeout,
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            self.connection_stats['errors_encountered'] += 1
            raise MCPTimeoutError("Streamable HTTP request timed out", error_details) from e

        except asyncio.CancelledError:
            if cancellation_token:
                cancellation_token.throw_if_cancelled()
            raise MCPCancelledError(
                "Streamable HTTP request was cancelled",
                {"url": self.url, "timestamp": datetime.now().isoformat()}
            )

        except Exception as e:
            error_details = {
                "url": self.url,
                "method": request_data.get('method') if 'request_data' in locals() else 'unknown',
                "error_type": type(e).__name__,
                "error_message": str(e),
                "protocol": "streamable_http",
                "timestamp": datetime.now().isoformat()
            }
            self.connection_stats['errors_encountered'] += 1

            # Check if this is a server error vs client error
            if "server" in str(e).lower() or "5" in str(e)[:3]:
                raise MCPRequestError("Server error in Streamable HTTP request", error_details) from e
            else:
                raise MCPConnectionError("Connection error in Streamable HTTP request", error_details) from e

    async def disconnect(self) -> bool:
        """
        Disconnect from the MCP server.

        Properly closes the Streamable HTTP connection and cleans up resources.

        Returns:
            bool: True if disconnected successfully
        """
        if not self.connected:
            return True

        try:
            if self.client:
                await self.client.disconnect()

            self.connected = False
            self.client = None

            # TODO: Add observability logging
            # disconnect_details = {
            #     "url": self.url,
            #     "protocol": "streamable_http",
            #     "session_duration_s": (
            #         (datetime.now() - self.connect_time).total_seconds()
            #         if self.connect_time else 0
            #     ),
            #     "total_requests": self.connection_stats['requests_sent'],
            #     "total_responses": self.connection_stats['responses_received'],
            #     "total_errors": self.connection_stats['errors_encountered'],
            #     "timestamp": datetime.now().isoformat()
            # }
            # observability.log_event("MCP_SERVER_DISCONNECTED", disconnect_details)

            return True

        except Exception:
            # Mark as disconnected even if cleanup failed
            self.connected = False
            self.client = None

            # TODO: Add observability logging
            # error_details = {
            #     "url": self.url,
            #     "error_type": type(e).__name__,
            #     "error_message": str(e),
            #     "protocol": "streamable_http",
            #     "timestamp": datetime.now().isoformat()
            # }
            # observability.log_event("MCP_DISCONNECT_ERROR", error_details)

            return False

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get detailed statistics about the Streamable HTTP connection.

        Returns:
            Dict containing connection statistics and metrics
        """
        stats = {
            "transport_type": "streamable_http",
            "protocol_version": "2025-03-26",
            "url": self.url,
            "connected": self.connected,
            "connect_time": self.connect_time.isoformat() if self.connect_time else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "session_duration_s": (datetime.now() - self.connect_time).total_seconds() if self.connect_time else 0,
            **self.connection_stats
        }

        # Add efficiency metrics
        if stats['requests_sent'] > 0:
            stats['success_rate'] = 1 - (stats['errors_encountered'] / stats['requests_sent'])
            stats['avg_bytes_per_request'] = stats['bytes_sent'] / stats['requests_sent']
            stats['avg_bytes_per_response'] = stats['bytes_received'] / max(stats['responses_received'], 1)

        return stats
