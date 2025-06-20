# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Real MCP HTTP+SSE Transport
# Description:  Real MCP SDK-based HTTP+SSE transport implementation
# Role:         Provides real MCP protocol support via sse_client
# Usage:        Used for MCP servers supporting HTTP+SSE protocol
# Author:       Muxi Framework Team
# =============================================================================

import asyncio
import json
import aiohttp
from typing import Any, Dict, Optional
from datetime import datetime

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
)
from ..protocol.message_handler import MCPMessageHandler


class HTTPSSETransport(BaseTransport):
    """Real MCP HTTP+SSE transport with working SSE client."""

    def __init__(
        self,
        url: str,
        request_timeout: int = 30,
        auth: Optional[Any] = None
    ):
        """Initialize real MCP HTTP+SSE transport."""
        super().__init__(url, request_timeout, auth)
        self.message_handler = MCPMessageHandler()
        self.session = None
        self.response = None
        self.message_queue = asyncio.Queue()
        self.reader_task = None

    async def connect(self) -> bool:
        """Connect using working HTTP+SSE implementation."""
        if self.connected:
            return True

        try:
            # Create aiohttp session
            self.session = aiohttp.ClientSession()

            # Connect to SSE endpoint
            self.response = await self.session.get(
                self.url,
                headers={
                    'Accept': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive'
                }
            )

            if self.response.status != 200:
                raise MCPConnectionError(f"HTTP error: {self.response.status}")

            # Start reading SSE events
            self.reader_task = asyncio.create_task(self._read_sse_events())

            self.connected = True
            self.connect_time = datetime.now()
            self.last_activity = datetime.now()
            return True

        except Exception as e:
            error_details = {
                "url": self.url,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            raise MCPConnectionError("Failed to connect to MCP server", error_details) from e

    async def _read_sse_events(self):
        """Read SSE events and queue MCP messages."""
        try:
            buffer = ""
            async for data in self.response.content:
                chunk = data.decode('utf-8')
                buffer += chunk

                # Process complete SSE events
                while '\r\n\r\n' in buffer:
                    event_data, buffer = buffer.split('\r\n\r\n', 1)
                    await self._process_sse_event(event_data)

        except Exception as e:
            print(f"SSE reader error: {e}")

    async def _process_sse_event(self, event_data: str):
        """Process a single SSE event."""
        try:
            lines = event_data.strip().split('\r\n')
            data_content = None

            for line in lines:
                if line.startswith('data: '):
                    data_content = line[6:]  # Remove 'data: ' prefix
                    break

            if data_content:
                # Parse JSON message
                message_data = json.loads(data_content)

                # Convert to SessionMessage format for compatibility
                from mcp.shared.message import SessionMessage
                from mcp.types import JSONRPCResponse, JSONRPCRequest, JSONRPCNotification

                if 'result' in message_data:
                    # Response message
                    response = JSONRPCResponse(
                        jsonrpc=message_data.get('jsonrpc', '2.0'),
                        id=message_data.get('id'),
                        result=message_data.get('result')
                    )
                    session_msg = SessionMessage(message=response)
                elif 'method' in message_data:
                    # Check if it's a notification (no id) or request (has id)
                    message_id = message_data.get('id')
                    if message_id is None:
                        # Notification message
                        notification = JSONRPCNotification(
                            jsonrpc=message_data.get('jsonrpc', '2.0'),
                            method=message_data.get('method'),
                            params=message_data.get('params', {})
                        )
                        session_msg = SessionMessage(message=notification)
                    else:
                        # Request message
                        request = JSONRPCRequest(
                            jsonrpc=message_data.get('jsonrpc', '2.0'),
                            id=message_id,
                            method=message_data.get('method'),
                            params=message_data.get('params', {})
                        )
                        session_msg = SessionMessage(message=request)
                else:
                    # Raw message data - create a basic session message
                    session_msg = SessionMessage(message=message_data)

                await self.message_queue.put(session_msg)

        except Exception as e:
            print(f"Error processing SSE event: {e}")
            # Don't fail on processing errors, just log them

    async def _send_http_request(self, message_data: dict) -> dict:
        """Send HTTP POST request for MCP messages."""
        try:
            # Determine correct POST URL based on MCP method
            method = message_data.get('method', '')

            if self.url.endswith('/sse'):
                base_url = self.url[:-4]  # Remove '/sse' suffix
            else:
                base_url = self.url

            # Map MCP methods to specific endpoints
            if method == 'tools/list':
                post_url = f"{base_url}/mcp/tools/list"
            elif method == 'tools/call':
                post_url = f"{base_url}/mcp/tools/call"
            elif method == 'resources/list':
                post_url = f"{base_url}/mcp/resources/list"
            elif method == 'prompts/list':
                post_url = f"{base_url}/mcp/prompts/list"
            elif method == 'initialize':
                post_url = f"{base_url}/mcp/initialize"
            elif method == 'ping':
                post_url = f"{base_url}/mcp/ping"
            else:
                # Fallback for unknown methods
                post_url = f"{base_url}/mcp/{method}"

            async with self.session.post(
                post_url,
                json=message_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise MCPRequestError(f"HTTP POST failed: {response.status} for URL {post_url}")
        except Exception as e:
            raise MCPRequestError(f"Failed to send HTTP request: {e}")

    async def send_request(self, request_obj: Any, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Send MCP request via HTTP POST and receive response via SSE."""
        if not self.connected:
            raise MCPConnectionError("Not connected to MCP server")

        # Use provided timeout or default
        actual_timeout = timeout or self.request_timeout

        # Convert to proper MCP format
        if isinstance(request_obj, dict):
            method = request_obj.get("method")
            params = request_obj.get("params", {})
        else:
            raise MCPRequestError("Invalid request format")

        # Create proper MCP message
        request_message = self.message_handler.create_request(method, params)

        # Extract raw message data for HTTP POST
        raw_message = request_message.message
        if hasattr(raw_message, 'model_dump'):
            message_data = raw_message.model_dump()
        else:
            message_data = {
                'jsonrpc': '2.0',
                'id': getattr(raw_message, 'id', None),
                'method': method,
                'params': params
            }

        # Send HTTP POST request
        try:
            # For tools/list and other methods, send via HTTP POST
            response_data = await self._send_http_request(message_data)
            return {
                "status": "success",
                "result": response_data.get("result", response_data),
                "id": response_data.get("id"),
                "jsonrpc": response_data.get("jsonrpc", "2.0")
            }
        except Exception as e:
            # If HTTP POST fails, try to get response from SSE stream
            try:
                response_message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=actual_timeout
                )
                return self.message_handler.parse_response(response_message)
            except asyncio.TimeoutError:
                raise MCPRequestError(f"Request timeout after {actual_timeout}s: {e}")
            except Exception as stream_error:
                raise MCPRequestError(f"Request failed: {e}, Stream error: {stream_error}")

    async def disconnect(self) -> bool:
        """Disconnect from MCP server."""
        if not self.connected:
            return True

        try:
            # Cancel SSE reader task
            if self.reader_task and not self.reader_task.done():
                self.reader_task.cancel()
                try:
                    await self.reader_task
                except asyncio.CancelledError:
                    pass

            # Close HTTP response
            if self.response:
                self.response.close()

            # Close aiohttp session
            if self.session:
                await self.session.close()

        except Exception:
            pass
        finally:
            self.connected = False
            self.session = None
            self.response = None
            self.reader_task = None

        return True
