# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Command Line Transport - Local Process Transport
# Description:  Command-line transport implementation for MCP servers
# Role:         Provides process-based transport for local MCP tools
# Usage:        Used for MCP servers running as local command-line processes
# Author:       Muxi Framework Team
# =============================================================================

import uuid
import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

from .base import (
    BaseTransport,
    MCPConnectionError,
    MCPRequestError,
    MCPCancelledError,
    CancellationToken
)


class CommandLineTransport(BaseTransport):
    """
    Command-line transport for MCP servers.

    This transport implementation launches MCP servers as local processes
    and communicates with them via standard input/output. It's useful for
    running local tool servers that don't require HTTP communication.
    """

    def __init__(self, command: str):
        """
        Initialize with command to start the server.

        Args:
            command: Shell command to start the server process. This should
                launch an executable that implements the MCP protocol over
                standard input/output.
        """
        self.command = command
        self.process = None
        self.stdin = None
        self.stdout = None
        self.connected = False
        self.connect_time = None
        self.last_activity = None
        self.session_id = str(uuid.uuid4())  # Generate a unique session ID

    async def connect(self) -> bool:
        """
        Start the server process and establish connection.

        Launches the MCP server as a subprocess and sets up communication
        channels via standard input/output.

        Returns:
            bool: True if the server was started successfully

        Raises:
            MCPConnectionError: If the server process cannot be started
            MCPCancelledError: If the operation is cancelled
        """
        try:
            #  MCP info - TODO: add observability
            # start_time = time.time()

            # Start the process
            self.process = await asyncio.create_subprocess_shell(
                self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # connection_time = time.time() - start_time

            if self.process:
                self.stdin = self.process.stdin
                self.stdout = self.process.stdout
                self.connected = True
                self.connect_time = datetime.now()
                self.last_activity = self.connect_time

                #  Info - TODO: add observability
                #     f"MCP server process started with PID {self.process.pid} "
                #     f"in {connection_time:.2f}s"
                # )
                return True
            else:
                error_details = {
                    "command": self.command,
                    # "connection_time_s": connection_time,
                    "timestamp": datetime.now().isoformat(),
                }
                #  MCP error - TODO: add observability
                raise MCPConnectionError("Failed to start MCP server process", error_details)

        except asyncio.CancelledError:
            #  Info - TODO: add observability
            raise MCPCancelledError(
                "Process start was cancelled",
                {"command": self.command, "timestamp": datetime.now().isoformat()},
            )

        except Exception as e:
            error_details = {
                "command": self.command,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  MCP error - TODO: add observability
            raise MCPConnectionError("Error starting MCP server process", error_details) from e

    async def send_request(
        self, request_obj: Any, cancellation_token: Optional[CancellationToken] = None
    ) -> Dict[str, Any]:
        """
        Send a request to the MCP server process.

        Sends a request to the MCP server via standard input and reads the
        response from standard output, following the MCP JSON-RPC protocol.

        Args:
            request_obj: A request object with model_dump() method or a dictionary
                containing the request details.
            cancellation_token: Optional token to cancel the operation if needed.

        Returns:
            Dict containing the response from the server.

        Raises:
            MCPConnectionError: If not connected to the server
            MCPRequestError: If the request fails
            MCPCancelledError: If the operation is cancelled
        """
        if not self.connected or not self.stdin or not self.stdout:
            raise MCPConnectionError(
                "Not connected to MCP server process",
                {
                    "connected": self.connected,
                    "stdin_exists": self.stdin is not None,
                    "stdout_exists": self.stdout is not None,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # Convert request to dictionary
        if hasattr(request_obj, "model_dump"):
            request_data = request_obj.model_dump()
        else:
            request_data = request_obj

        method_name = request_data.get("method", "unknown")
        request_id = request_data.get("id", str(uuid.uuid4()))
        #  Info - TODO: add observability

        try:
            if cancellation_token:
                cancellation_token.throw_if_cancelled()

            # start_time = time.time()

            # Send request to process stdin
            request_json = json.dumps(request_data) + "\n"
            self.stdin.write(request_json.encode())
            await self.stdin.drain()

            # Read response from process stdout
            response_line = await self.stdout.readline()

            # request_time = time.time() - start_time
            self.last_activity = datetime.now()

            #  Info - TODO: add observability

            if not response_line:
                error_details = {
                    "method": method_name,
                    "request_id": request_id,
                    # "request_time_s": request_time,
                    "timestamp": datetime.now().isoformat(),
                }
                #  MCP error - TODO: add observability
                raise MCPRequestError("Empty response from MCP server process", error_details)

            try:
                response_data = json.loads(response_line.decode())
                return response_data
            except json.JSONDecodeError as e:
                response_text = (
                    response_line.decode()[:100] + "..."
                    if len(response_line) > 100
                    else response_line.decode()
                )
                error_details = {
                    "method": method_name,
                    "request_id": request_id,
                    "response_text": response_text,
                    # "request_time_s": request_time,
                    "error_type": "json_decode_error",
                    "error_message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                #  Error - TODO: add observability
                raise MCPRequestError(
                    "Invalid JSON response from MCP server process", error_details
                ) from e

        except asyncio.CancelledError:
            #  Info - TODO: add observability
            raise MCPCancelledError(
                "Request was cancelled",
                {
                    "method": method_name,
                    "request_id": request_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        except Exception as e:
            if isinstance(e, (MCPConnectionError, MCPRequestError, MCPCancelledError)):
                raise

            error_details = {
                "method": method_name,
                "request_id": request_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  Error - TODO: add observability
            raise MCPRequestError(
                "Error sending request to MCP server process", error_details
            ) from e

    async def disconnect(self) -> bool:
        """
        Terminate the server process.

        Properly shuts down the MCP server process by closing stdin and
        terminating the process if necessary.

        Returns:
            bool: True if the server process was terminated successfully

        Raises:
            MCPConnectionError: If there are issues during termination
        """
        try:
            if self.process:
                # Close stdin to signal end of input
                if self.stdin:
                    self.stdin.close()

                # Terminate process if it's still running
                if self.process.returncode is None:
                    #  MCP info - TODO: add observability
                    self.process.terminate()

                    # Wait for process to terminate
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        #  Warning - TODO: add observability
                        #     f"Process didn't terminate, killing it (PID {self.process.pid})"
                        # )
                        self.process.kill()

                # Reset state
                self.process = None
                self.stdin = None
                self.stdout = None
                self.connected = False

                #  MCP info - TODO: add observability
                return True

            return True  # Already disconnected

        except Exception as e:
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            #  MCP error - TODO: add observability
            raise MCPConnectionError(
                "Error disconnecting from MCP server process", error_details
            ) from e

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
            "session_id": self.session_id,
            "current_time": datetime.now().isoformat(),
        }

        if self.process:
            stats["pid"] = self.process.pid
            stats["returncode"] = self.process.returncode

        if self.connect_time:
            stats["connect_time"] = self.connect_time.isoformat()
            stats["connection_age_s"] = (datetime.now() - self.connect_time).total_seconds()

        if self.last_activity:
            stats["last_activity"] = self.last_activity.isoformat()
            stats["idle_time_s"] = (datetime.now() - self.last_activity).total_seconds()

        return stats
