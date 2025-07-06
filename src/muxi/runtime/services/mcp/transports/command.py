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
import logging
from typing import Any, Dict, Optional
from datetime import datetime

# Real MCP SDK imports
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
    CancellationToken,
)
from ..protocol.message_handler import MCPMessageHandler

# Create logger for this module
logger = logging.getLogger(__name__)


class CommandLineTransport(BaseTransport):
    """Real MCP STDIO transport using MCP SDK."""

    def __init__(
        self,
        command: str,
        args: Optional[list] = None,
        env: Optional[dict] = None,
        request_timeout: int = 30,
        auth: Optional[Any] = None,
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
        self.client_context = None
        self.read_stream = None
        self.write_stream = None

        # Initialize connection stats
        self.connection_stats = {
            "requests_sent": 0,
            "responses_received": 0,
            "errors_encountered": 0,
        }

        logger.debug(f"Initialized with command: {self.command} {self.args}")

    async def connect(self) -> bool:
        """Connect using real MCP SDK stdio_client."""
        if self.connected:
            return True

        try:
            # Create server parameters object
            server_params = StdioServerParameters(
                command=self.command, args=self.args, env=self.env
            )

            # Use SDK client - store the context manager
            self.client_context = stdio_client(server_params)

            # Enter context and get streams
            self.read_stream, self.write_stream = await self.client_context.__aenter__()

            # Create session for high-level operations
            self.session = ClientSession(self.read_stream, self.write_stream)
            await self.session.__aenter__()

            # Initialize the connection
            await self.session.initialize()

            self.connected = True
            self.connect_time = datetime.now()
            self.last_activity = datetime.now()

            logger.info(f"Connected successfully to command: {self.command}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            # Clean up any partially created resources
            await self._cleanup()
            error_details = {
                "command": self.command,
                "args": self.args,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            raise MCPConnectionError("Failed to connect to MCP server", error_details) from e

    async def send_request(
        self,
        request_obj: Any,
        timeout: Optional[int] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Send request using real MCP protocol."""
        if not self.connected or not self.session:
            raise MCPConnectionError("Not connected to MCP server")

        if cancellation_token:
            cancellation_token.throw_if_cancelled()

        method = request_obj.get("method")
        params = request_obj.get("params", {})

        try:
            # Use SDK's high-level methods where possible
            if method == "tools/list":
                result = await self.session.list_tools()
                # Update stats
                self.last_activity = datetime.now()
                self.connection_stats["requests_sent"] += 1
                self.connection_stats["responses_received"] += 1
                # Convert to expected format
                return {
                    "status": "success",
                    "result": {"tools": [tool.model_dump() for tool in result.tools]},
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await self.session.call_tool(tool_name, arguments)
                # Update stats
                self.last_activity = datetime.now()
                self.connection_stats["requests_sent"] += 1
                self.connection_stats["responses_received"] += 1
                # Convert to expected format
                return {"status": "success", "result": result.model_dump()}
            elif method == "resources/list":
                result = await self.session.list_resources()
                # Update stats
                self.last_activity = datetime.now()
                self.connection_stats["requests_sent"] += 1
                self.connection_stats["responses_received"] += 1
                return {
                    "status": "success",
                    "result": {"resources": [res.model_dump() for res in result.resources]},
                }
            elif method == "prompts/list":
                result = await self.session.list_prompts()
                # Update stats
                self.last_activity = datetime.now()
                self.connection_stats["requests_sent"] += 1
                self.connection_stats["responses_received"] += 1
                return {
                    "status": "success",
                    "result": {"prompts": [prompt.model_dump() for prompt in result.prompts]},
                }
            else:
                # For other methods, use generic approach
                # Create proper MCP request message
                request_message = self.message_handler.create_request(method, params)

                # Send via MCP SDK streams
                await self.write_stream.send(request_message)

                # Wait for response with timeout
                request_timeout = timeout or self.request_timeout
                response_message = await asyncio.wait_for(
                    self.read_stream.receive(), timeout=request_timeout
                )

                # Parse response using message handler
                parsed_response = self.message_handler.parse_response(response_message)

                self.last_activity = datetime.now()
                self.connection_stats["requests_sent"] += 1
                self.connection_stats["responses_received"] += 1

                return parsed_response

        except asyncio.TimeoutError as e:
            self.connection_stats["errors_encountered"] += 1
            error_details = {"timeout": request_timeout, "timestamp": datetime.now().isoformat()}
            raise MCPTimeoutError("Request timed out", error_details) from e
        except Exception as e:
            self.connection_stats["errors_encountered"] += 1
            error_details = {"error": str(e), "timestamp": datetime.now().isoformat()}
            raise MCPRequestError("Request failed", error_details) from e

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

            # Terminate the subprocess if it's still running
            # The client_context should handle this, but we need to ensure it happens
            if hasattr(self, '_process') and self._process:
                try:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                except Exception:
                    pass

        finally:
            self.connected = False
            self.session = None
            self.client_context = None
            self.read_stream = None
            self.write_stream = None

    async def disconnect(self) -> bool:
        """Disconnect from MCP server."""
        await self._cleanup()
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

        if self.session and hasattr(self.session, "session_id"):
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
