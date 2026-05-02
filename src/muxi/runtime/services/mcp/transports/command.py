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
import warnings
from datetime import datetime
from typing import Any, Dict, Optional

from mcp.client.session import ClientSession

# Real MCP SDK imports
from mcp.client.stdio import StdioServerParameters, stdio_client

from ..protocol.message_handler import MCPMessageHandler
from .base import (
    BaseTransport,
    CancellationToken,
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
)


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

        # Start with provided env or empty dict
        self.env = env or {}

        # If auth is provided and is env type, merge env vars
        if auth and isinstance(auth, dict) and auth.get("type") == "env":
            # Extract all keys except 'type' - no name validation
            auth_env_vars = {k: v for k, v in auth.items() if k != "type"}
            # Merge with existing env (auth vars take precedence)
            self.env.update(auth_env_vars)

        self.message_handler = MCPMessageHandler()
        self.session = None
        self.read_stream = None
        self.write_stream = None

        # Connection-lifecycle plumbing. ``stdio_client`` is an anyio
        # async context manager that internally creates a task group +
        # cancel scope. anyio enforces that the scope must be entered
        # AND exited in the same asyncio task; if ``__aenter__`` runs in
        # task A and ``__aexit__`` runs in task B (which happened when
        # ``connect()`` and ``disconnect()`` were awaited from different
        # request handlers / cleanup paths), anyio raises
        # ``RuntimeError: Attempted to exit cancel scope in a different
        # task than it was entered in``. The fix is to hold both the
        # ``stdio_client`` and the ``ClientSession`` context managers
        # open inside a single dedicated background task, and signal
        # shutdown via an asyncio.Event so the task tears them down
        # from within its own scope.
        self._connection_task: Optional[asyncio.Task] = None
        self._connected_event: Optional[asyncio.Event] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._connect_error: Optional[BaseException] = None

        # Initialize connection stats
        self.connection_stats = {
            "requests_sent": 0,
            "responses_received": 0,
            "errors_encountered": 0,
        }

    async def _connection_lifecycle(self) -> None:
        """Hold the stdio_client + ClientSession contexts open in ONE task.

        Entered from :meth:`connect`. Spawns inside a dedicated asyncio
        task so the ``async with`` cancel scopes the MCP SDK opens are
        both entered and exited from the same task - the only contract
        anyio's task-group implementation honors.

        Lifecycle:

        1. Open ``stdio_client(server_params)`` -> ``(read, write)``.
        2. Open ``ClientSession(read, write)`` and ``initialize()``.
        3. Publish ``read``, ``write``, ``session`` on ``self`` and signal
           ``_connected_event`` so the caller of ``connect()`` can return.
        4. ``await self._shutdown_event.wait()`` - block until something
           calls ``disconnect()``.
        5. Fall out of both ``async with`` blocks - clean teardown
           inside the connection-owning task.

        Exceptions during steps 1-3 are captured on
        ``self._connect_error`` and the connected event is still set
        (with ``error`` populated) so ``connect()`` raises a clean
        ``MCPConnectionError`` instead of deadlocking the caller.
        """
        server_params = StdioServerParameters(
            command=self.command, args=self.args, env=self.env
        )

        try:
            with warnings.catch_warnings():
                # Suppress annoying MCP server warnings about
                # notification-validation noise.
                warnings.simplefilter("ignore")
                root_logger = logging.getLogger()
                original_level = root_logger.level
                root_logger.setLevel(logging.ERROR)
                try:
                    async with stdio_client(server_params) as (
                        read_stream,
                        write_stream,
                    ):
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()

                            self.read_stream = read_stream
                            self.write_stream = write_stream
                            self.session = session
                            self.connected = True
                            self.connect_time = datetime.now()
                            self.last_activity = datetime.now()
                            self._connected_event.set()

                            # Hold the contexts open. ``disconnect()``
                            # sets this event, the task wakes, falls
                            # out of both ``async with`` blocks, and
                            # the cancel scopes tear down inside this
                            # same task (the only place anyio allows).
                            await self._shutdown_event.wait()
                finally:
                    root_logger.setLevel(original_level)
        except BaseException as exc:  # noqa: BLE001 - surface any failure
            # Capture the failure for ``connect()`` to re-raise. Do not
            # swallow ``BaseException`` (e.g. ``CancelledError``) - the
            # caller needs to see the real reason the lifecycle aborted.
            if not self._connected_event.is_set():
                self._connect_error = exc
                self._connected_event.set()
            # If we were already connected, the exception is from the
            # post-connect path (provider died, network issue, etc.) -
            # let it surface in the task result so callers awaiting it
            # observe the failure.
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            self.connected = False
            self.session = None
            self.read_stream = None
            self.write_stream = None

    async def connect(self) -> bool:
        """Connect using MCP SDK pattern with proper context management."""
        if self.connected:
            return True

        # Reset per-attempt state so a retry after a previous failure
        # does not see stale events.
        self._connected_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._connect_error = None

        # Spawn the lifecycle task that owns both async-context managers.
        self._connection_task = asyncio.create_task(self._connection_lifecycle())

        try:
            await self._connected_event.wait()
        except Exception as e:
            # Caller cancelled the connect; tear down the lifecycle.
            self._shutdown_event.set()
            try:
                await asyncio.wait_for(self._connection_task, timeout=5)
            except Exception:
                pass
            error_details = {
                "command": self.command,
                "args": self.args,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            raise MCPConnectionError("Failed to connect to MCP server", error_details) from e

        if self._connect_error is not None:
            error_details = {
                "command": self.command,
                "args": self.args,
                "error": str(self._connect_error),
                "timestamp": datetime.now().isoformat(),
            }
            raise MCPConnectionError(
                "Failed to connect to MCP server", error_details
            ) from self._connect_error

        return True

    def _update_success_stats(self) -> None:
        """Update statistics for successful request/response."""
        self.last_activity = datetime.now()
        self.connection_stats["requests_sent"] += 1
        self.connection_stats["responses_received"] += 1

    async def send_request(
        self,
        request_obj: Any,
        timeout: Optional[int] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Send request using MCP SDK high-level methods."""
        if not self.connected or not self.session:
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

            request_timeout = timeout or self.request_timeout

            # Route to appropriate session method based on MCP method
            if method == "tools/list":
                result = await asyncio.wait_for(self.session.list_tools(), timeout=request_timeout)
                self._update_success_stats()
                return {
                    "status": "success",
                    "result": {"tools": [tool.model_dump() for tool in result.tools]},
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await asyncio.wait_for(
                    self.session.call_tool(tool_name, arguments), timeout=request_timeout
                )
                self._update_success_stats()
                return {"status": "success", "result": result.model_dump()}
            elif method == "resources/list":
                result = await asyncio.wait_for(
                    self.session.list_resources(), timeout=request_timeout
                )
                self._update_success_stats()
                return {
                    "status": "success",
                    "result": {"resources": [res.model_dump() for res in result.resources]},
                }
            elif method == "prompts/list":
                result = await asyncio.wait_for(
                    self.session.list_prompts(), timeout=request_timeout
                )
                self._update_success_stats()
                return {
                    "status": "success",
                    "result": {"prompts": [prompt.model_dump() for prompt in result.prompts]},
                }
            else:
                # For other methods, use the raw streams
                request_message = self.message_handler.create_request(method, params)

                # Send via write stream
                await self.write_stream.send(request_message)

                # Read response with timeout
                response_message = await asyncio.wait_for(
                    self.read_stream.receive(), timeout=request_timeout
                )

                # Parse response
                parsed_response = self.message_handler.parse_response(response_message)

                self._update_success_stats()
                return parsed_response

        except asyncio.TimeoutError as e:
            self.connection_stats["errors_encountered"] += 1
            error_details = {"timeout": request_timeout, "timestamp": datetime.now().isoformat()}
            raise MCPTimeoutError("Request timed out", error_details) from e
        except Exception as e:
            self.connection_stats["errors_encountered"] += 1
            error_details = {"error": str(e), "timestamp": datetime.now().isoformat()}
            raise MCPRequestError("Request failed", error_details) from e

    async def _cleanup(self) -> None:
        """Signal the connection-lifecycle task to tear down its contexts.

        The actual ``__aexit__`` for both ``stdio_client`` and
        ``ClientSession`` runs inside ``_connection_lifecycle`` (the
        same task that called ``__aenter__``), so this method only has
        to flip the shutdown event and wait for the task to finish.
        """
        if self._shutdown_event is not None and not self._shutdown_event.is_set():
            self._shutdown_event.set()

        task = self._connection_task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(task, timeout=10)
            except asyncio.TimeoutError:
                # The lifecycle task didn't react in time - cancel and
                # await it so the cancellation propagates inside the
                # task's own scope (still anyio-safe).
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                # Surface in observability via the caller; the
                # connection state is already torn down here.
                pass

        self._connection_task = None
        self.connected = False
        self.session = None
        self.read_stream = None
        self.write_stream = None

    async def disconnect(self) -> bool:
        """Disconnect from MCP server."""
        if not self.connected and self._connection_task is None:
            return True

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
