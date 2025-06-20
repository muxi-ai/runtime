# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP HTTP+SSE Transport - Server-Sent Events Transport
# Description:  HTTP+SSE transport implementation for MCP servers
# Role:         Provides HTTP+SSE transport for legacy MCP protocol support
# Usage:        Used for MCP servers supporting HTTP+SSE (MCP 2024-11-05)
# Author:       Muxi Framework Team
# =============================================================================

import uuid
import time
import asyncio
import httpx
from typing import Any, Dict, Optional, Callable, AsyncGenerator
from datetime import datetime

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
    MCPCancelledError,
    CancellationToken
)


class HTTPSSETransport(BaseTransport):
    """
    HTTP+SSE transport for MCP servers.

    This transport implementation uses HTTP with Server-Sent Events (SSE)
    for communicating with MCP servers, following the official MCP specification.
    It handles connection establishment, message exchange, and connection
    management.
    """

    def __init__(self, url: str, request_timeout: int = 60):
        """
        Initialize with server URL.

        Args:
            url: Base URL of the MCP server. Can be either the main server URL
                or a specific SSE endpoint URL.
            request_timeout: Timeout for requests in seconds. Controls how long
                to wait for responses before raising a timeout error.
        """
        self.base_url = url
        self.sse_url = url if "/sse" in url else f"{url.rstrip('/')}/sse"
        self.message_url = None
        self.session_id = None
        self.client = httpx.AsyncClient(timeout=request_timeout)
        self.sse_connection = None
        self.connected = False
        self.request_timeout = request_timeout
        self.connect_time = None
        self.last_activity = None

    async def connect(self) -> bool:
        """
        Connect to the MCP server using HTTP+SSE protocol.

        Establishes a connection to the MCP server by:
        1. Connecting to the SSE endpoint
        2. Receiving the message endpoint information
        3. Extracting the session ID for future requests

        Returns:
            bool: True if connected successfully

        Raises:
            MCPConnectionError: If connection fails
            MCPTimeoutError: If connection times out
            MCPCancelledError: If connection is cancelled
        """
        try:
            # Initialize SSE connection with proper headers
            headers = {
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }

            start_time = time.time()
            #  Info - TODO: add observability
            #  MCP_SERVER_CONNECTING

            # Use the stream context manager properly
            async with self.client.stream(
                "GET", self.sse_url, headers=headers, timeout=self.request_timeout
            ) as response:
                self.sse_connection = response
                connection_time = time.time() - start_time

                if response.status_code != 200:
                    error_details = {
                        "status_code": response.status_code,
                        "url": self.sse_url,
                        "headers": dict(response.headers),
                        "connection_time_s": connection_time,
                        "timestamp": datetime.now().isoformat(),
                    }
                    #  Error - TODO: add observability
                    #  MCP_SERVER_CONNECTING
                    raise MCPConnectionError(
                        f"Failed to connect to SSE endpoint (status {response.status_code})",
                        error_details,
                    )

                #  Info - TODO: add observability
                #  MCP_SERVER_CONNECTING
                #     f"SSE connection established: {response.status_code} in {connection_time:.2f}s"
                # )

                # Process SSE events to get endpoint info
                found_endpoint = False
                async for line in response.aiter_lines():
                    #  Debug - TODO: add observability
                    #  MCP_SERVER_CONNECTING

                    if line.startswith("event: endpoint"):
                        # Next line should contain the data
                        continue

                    if line.startswith("data:") and self.message_url is None:
                        message_path = line[5:].strip()
                        #  Info - TODO: add observability
                        #  MCP_SERVER_CONNECTING

                        # Make sure it's a full URL
                        if message_path.startswith("http"):
                            self.message_url = message_path
                        else:
                            # Handle relative paths
                            server_base = self.base_url
                            if "/sse" in server_base:
                                server_base = server_base.split("/sse")[0]
                            else:
                                server_base = server_base.rstrip("/")

                            if not message_path.startswith("/"):
                                message_path = "/" + message_path
                            self.message_url = server_base + message_path

                        # Extract session ID from the URL
                        if "?" in self.message_url:
                            query = self.message_url.split("?")[1]
                            params = dict(p.split("=") for p in query.split("&"))

                            if "sessionId" in params:
                                self.session_id = params["sessionId"]
                            elif "session_id" in params:
                                self.session_id = params["session_id"]

                            #  MCP info - TODO: add observability
                            #  MCP_SERVER_CONNECTING
                            #  Info - TODO: add observability
                            #  MCP_SERVER_CONNECTING
                            self.connected = True
                            self.connect_time = datetime.now()
                            self.last_activity = self.connect_time
                            found_endpoint = True
                            break

                # If we found the endpoint info, we're connected
                if found_endpoint:
                    return True

                # If we got here without finding an endpoint, the connection failed
                error_details = {
                    "url": self.sse_url,
                    "status_code": response.status_code,
                    "connection_time_s": connection_time,
                    "timestamp": datetime.now().isoformat(),
                }
                #  Error - TODO: add observability
                #  MCP_SERVER_CONNECTING
                raise MCPConnectionError(
                    "Failed to extract endpoint information from SSE stream", error_details
                )

        except httpx.TimeoutException as e:
            error_details = {
                "url": self.sse_url,
                "timeout_seconds": self.request_timeout,
                "error_type": "timeout",
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  MCP error - TODO: add observability
            #  MCP_SERVER_CONNECTING
            raise MCPTimeoutError("Connection to SSE endpoint timed out", error_details) from e

        except asyncio.CancelledError:
            #  Info - TODO: add observability
            raise MCPCancelledError(
                "SSE connection attempt was cancelled",
                {"url": self.sse_url, "timestamp": datetime.now().isoformat()},
            )

        except Exception as e:
            error_details = {
                "url": self.sse_url,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  MCP error - TODO: add observability
            raise MCPConnectionError("Error connecting to MCP server", error_details) from e

    async def listen_for_events(
        self,
        callback: Optional[Callable] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> AsyncGenerator:
        """
        Listen for SSE events from the server.

        This method provides an async generator that yields SSE event lines
        as they are received from the server, allowing for real-time event
        processing.

        Args:
            callback: Optional callback function to call for each event line
            cancellation_token: Optional token for cancelling the listening operation

        Yields:
            str: Each line of SSE events from the server

        Raises:
            MCPConnectionError: If there are issues with the SSE connection
            MCPCancelledError: If the operation is cancelled
        """
        if not self.sse_connection:
            #  Error - TODO: add observability
            return

        try:
            async for line in self.sse_connection.aiter_lines():
                if cancellation_token:
                    cancellation_token.throw_if_cancelled()

                self.last_activity = datetime.now()
                if callback:
                    await callback(line)
                yield line
        except asyncio.CancelledError:
            #  Info - TODO: add observability
            raise MCPCancelledError(
                "SSE event listener was cancelled",
                {"url": self.sse_url, "timestamp": datetime.now().isoformat()},
            )
        except Exception as e:
            error_details = {
                "url": self.sse_url,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  Error - TODO: add observability
            raise MCPConnectionError("Error listening for SSE events", error_details) from e

    async def send_request(
        self, request_obj: Any, cancellation_token: Optional[CancellationToken] = None
    ) -> Dict[str, Any]:
        """
        Send request to the MCP server.

        Sends a request to the message endpoint of the MCP server and processes
        the response, handling different response types and status codes according
        to the MCP specification.

        Args:
            request_obj: A request object with model_dump() method or a dictionary
                containing the request details.
            cancellation_token: Optional token to cancel the operation if needed.

        Returns:
            Dict containing the response or status information.

        Raises:
            MCPConnectionError: If not connected to the server
            MCPRequestError: If the request fails
            MCPTimeoutError: If the request times out
            MCPCancelledError: If the operation is cancelled
        """
        if not self.message_url or not self.session_id:
            raise MCPConnectionError(
                "Not connected to MCP server",
                {
                    "message_url_exists": self.message_url is not None,
                    "session_id_exists": self.session_id is not None,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Convert request to dictionary
        if hasattr(request_obj, "model_dump"):
            request_data = request_obj.model_dump()
        else:
            request_data = request_obj

        # Ensure session ID is included
        url = self.message_url
        if "sessionId=" not in url and "session_id=" not in url:
            separator = "&" if "?" in url else "?"
            url += f"{separator}sessionId={self.session_id}"

        method_name = request_data.get("method", "unknown")
        request_id = request_data.get("id", str(uuid.uuid4()))
        #  Info - TODO: add observability

        try:
            if cancellation_token:
                cancellation_token.throw_if_cancelled()

            start_time = time.time()

            # Send request and handle 202 Accepted (async processing)
            response = await self.client.post(
                url, json=request_data, headers={"Content-Type": "application/json"}
            )

            request_time = time.time() - start_time
            self.last_activity = datetime.now()

            #  Info - TODO: add observability

            if response.status_code == 202:
                # Server accepted the request asynchronously
                #  Info - TODO: add observability
                return {
                    "status": "accepted",
                    "request_id": request_id,
                    "method": method_name,
                    "request_time_s": request_time,
                }

            elif response.status_code < 300:
                # Server returned immediate result
                try:
                    return response.json()
                except Exception:
                    #  Warning - TODO: add observability
                    # resp_text = (
                    #     response.text[:100] + "..." if len(response.text) > 100 else response.text
                    # )
                    #     f"Non-JSON response with status {response.status_code}: {resp_text}"
                    # )
                    return {
                        "status": "success",
                        "response": response.text,
                        "request_id": request_id,
                        "method": method_name,
                        "request_time_s": request_time,
                    }
            else:
                error_details = {
                    "status_code": response.status_code,
                    "url": url,
                    "method": method_name,
                    "request_id": request_id,
                    "response_text": response.text[:500],
                    "request_time_s": request_time,
                    "timestamp": datetime.now().isoformat(),
                }
                #  Error - TODO: add observability
                raise MCPRequestError(
                    f"Request failed with status {response.status_code}", error_details
                )

        except httpx.TimeoutException as e:
            error_details = {
                "url": url,
                "method": method_name,
                "request_id": request_id,
                "timeout_seconds": self.request_timeout,
                "error_type": "timeout",
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  Error - TODO: add observability
            raise MCPTimeoutError("Request timed out", error_details) from e

        except asyncio.CancelledError:
            #  Info - TODO: add observability
            raise MCPCancelledError(
                "Request was cancelled",
                {
                    "url": url,
                    "method": method_name,
                    "request_id": request_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        except Exception as e:
            if isinstance(e, (MCPConnectionError, MCPRequestError, MCPTimeoutError, MCPCancelledError)):
                raise

            error_details = {
                "url": url,
                "method": method_name,
                "request_id": request_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  Error - TODO: add observability
            raise MCPRequestError("Error sending request", error_details) from e

    async def disconnect(self) -> bool:
        """
        Disconnect from MCP server.

        Properly closes the SSE connection and HTTP client to ensure
        clean disconnection from the MCP server.

        Returns:
            bool: True if disconnected successfully

        Raises:
            MCPConnectionError: If there are issues during disconnection
        """
        try:
            if self.sse_connection:
                await self.sse_connection.aclose()

            await self.client.aclose()
            self.connected = False
            #  MCP info - TODO: add observability
            return True
        except Exception as e:
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  Error - TODO: add observability
            raise MCPConnectionError("Error disconnecting from MCP server", error_details) from e

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about this connection.

        Returns information about the connection status, timing, and activity,
        useful for monitoring and debugging.

        Returns:
            Dict with connection statistics including status, URLs,
            timing information, and activity metrics
        """
        stats = {
            "connected": self.connected,
            "type": "http",
            "base_url": self.base_url,
            "session_id": self.session_id,
            "current_time": datetime.now().isoformat(),
        }

        if self.connect_time:
            stats["connect_time"] = self.connect_time.isoformat()
            stats["connection_age_s"] = (datetime.now() - self.connect_time).total_seconds()

        if self.last_activity:
            stats["last_activity"] = self.last_activity.isoformat()
            stats["idle_time_s"] = (datetime.now() - self.last_activity).total_seconds()

        return stats
