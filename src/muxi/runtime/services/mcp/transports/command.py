# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Real MCP STDIO Transport
# Description:  Real MCP SDK-based STDIO transport implementation
# Role:         Provides real MCP protocol support via stdio_client
# Usage:        Used for MCP servers running as local command-line processes
# Author:       Muxi Framework Team
# =============================================================================

import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

# Real MCP SDK imports
from mcp.client.stdio import stdio_client, StdioServerParameters

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
    CancellationToken
)
from ..protocol.message_handler import MCPMessageHandler


class CommandLineTransport(BaseTransport):
    """Real MCP STDIO transport using MCP SDK."""

    def __init__(
        self,
        command: str,
        args: Optional[list] = None,
        env: Optional[dict] = None,
        request_timeout: int = 30,
        auth: Optional[Any] = None
    ):
        """Initialize real MCP STDIO transport."""
        super().__init__(command, request_timeout, auth)

        # Parse command string if args not provided
        if args is None and isinstance(command, str):
            # Split command string into command and args
            import shlex
            parsed_command = shlex.split(command)
            self.command = parsed_command[0]
            self.args = parsed_command[1:] if len(parsed_command) > 1 else []
        else:
            self.command = command
            self.args = args or []

        self.env = env or {}
        self.message_handler = MCPMessageHandler()
        self.session = None
        self.read_stream = None
        self.write_stream = None

        # Initialize connection stats
        self.connection_stats = {
            'requests_sent': 0,
            'responses_received': 0,
            'errors_encountered': 0
        }

    async def connect(self) -> bool:
        """Connect using real MCP SDK stdio_client."""
        if self.connected:
            return True

        try:
            # Create server parameters object
            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env
            )

            # Connect using real MCP SDK
            self.session = stdio_client(server_params)
            self.read_stream, self.write_stream = await self.session.__aenter__()

            self.connected = True
            self.connect_time = datetime.now()
            self.last_activity = datetime.now()
            return True

        except Exception as e:
            error_details = {
                "command": self.command,
                "args": self.args,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            raise MCPConnectionError("Failed to connect to MCP server", error_details) from e

    async def send_request(
        self,
        request_obj: Any,
        timeout: Optional[int] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> Dict[str, Any]:
        """Send request using real MCP protocol."""
        if not self.connected:
            raise MCPConnectionError("Not connected to MCP server")

        if cancellation_token:
            cancellation_token.throw_if_cancelled()

        try:
            # Convert request to proper MCP format
            if isinstance(request_obj, dict):
                method = request_obj.get("method")
                params = request_obj.get("params", {})
            else:
                raise MCPRequestError("Invalid request format")

            # Create proper MCP request message
            request_message = self.message_handler.create_request(method, params)

            # Send via MCP SDK streams
            await self.write_stream.send(request_message)

            # Wait for response with timeout
            request_timeout = timeout or self.request_timeout
            response_message = await asyncio.wait_for(
                self.read_stream.receive(),
                timeout=request_timeout
            )

            # Parse response using message handler
            parsed_response = self.message_handler.parse_response(response_message)

            self.last_activity = datetime.now()
            self.connection_stats['requests_sent'] += 1
            self.connection_stats['responses_received'] += 1

            return parsed_response

        except asyncio.TimeoutError as e:
            self.connection_stats['errors_encountered'] += 1
            error_details = {
                "timeout": request_timeout,
                "timestamp": datetime.now().isoformat()
            }
            raise MCPTimeoutError("Request timed out", error_details) from e
        except Exception as e:
            self.connection_stats['errors_encountered'] += 1
            error_details = {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            raise MCPRequestError("Request failed", error_details) from e

    async def disconnect(self) -> bool:
        """Disconnect from MCP server."""
        if not self.connected:
            return True

        try:
            if self.session:
                await self.session.__aexit__(None, None, None)
        except Exception:
            pass
        finally:
            self.connected = False
            self.session = None
            self.read_stream = None
            self.write_stream = None

        return True

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about this connection.

        Returns information about the server process, connection timing, and
        activity, useful for monitoring and debugging.

        Returns:
            Dict with connection statistics including process details,
            timing information, and activity metrics
        """
        stats = {
            "connected": self.connected,
            "type": "command",
            "command": self.command,
            "current_time": datetime.now().isoformat(),
        }

        if self.session and hasattr(self.session, 'session_id'):
            stats["session_id"] = self.session.session_id
        else:
            stats["session_id"] = None

        if self.connect_time:
            stats["connect_time"] = self.connect_time.isoformat()
            stats["connection_age_s"] = (datetime.now() - self.connect_time).total_seconds()

        if self.last_activity:
            stats["last_activity"] = self.last_activity.isoformat()
            stats["idle_time_s"] = (datetime.now() - self.last_activity).total_seconds()

        # Add connection stats
        stats.update(self.connection_stats)

        return stats
