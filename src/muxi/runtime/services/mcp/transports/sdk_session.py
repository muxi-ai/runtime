# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP SDK Session Transport - Single-Task Session Lifecycle
# Description:  Base class for transports that hold an MCP SDK ClientSession
# Role:         Owns the SDK client contexts in one dedicated asyncio task
# Usage:        Extended by the streamable HTTP and HTTP+SSE transports
# Author:       Muxi Framework Team
# =============================================================================

import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Optional, Tuple

from mcp.client.session import ClientSession

from ... import observability
from .base import BaseTransport, MCPConnectionError


def _describe_error(exc: BaseException) -> str:
    """Name the leaf failures inside an anyio task-group exception group."""
    if isinstance(exc, BaseExceptionGroup):
        leaves = [
            _describe_error(inner)
            for inner in exc.exceptions
            if not isinstance(inner, (asyncio.CancelledError, GeneratorExit))
        ]
        if leaves:
            return "; ".join(leaves)
    return str(exc) or type(exc).__name__


class SDKSessionTransport(BaseTransport):
    """Transport that keeps the SDK client and ClientSession open in one task.

    The SDK client context managers open an anyio task group. anyio requires a
    task group's cancel scope to be entered and exited in the same task, and on
    failure it cancels the task that entered it. Entering the contexts from
    ``connect()`` (in the caller's task) and leaving them from ``disconnect()``
    breaks the first rule, and since Python 3.12, where ``asyncio.wait_for`` no
    longer wraps a coroutine in a new task, a failed request inside the SDK
    cancels the caller's task. A dedicated lifecycle task enters and exits both
    contexts, so SDK failures stay inside it.
    """

    transport_type = "sdk_session"

    def __init__(self, url: str, request_timeout: int = 30, auth: Optional[Any] = None):
        super().__init__(url, request_timeout, auth)
        self.session: Any = None
        self.read_stream: Any = None
        self.write_stream: Any = None
        self._connection_task: Optional[asyncio.Task] = None
        self._connected_event: Optional[asyncio.Event] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._connect_error: Optional[BaseException] = None

    def _open_streams(self) -> AbstractAsyncContextManager[Tuple[Any, Any]]:
        """Return the SDK client context manager yielding ``(read, write)``."""
        raise NotImplementedError("Subclasses must implement _open_streams()")

    async def _connection_lifecycle(self) -> None:
        try:
            async with self._open_streams() as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    self.read_stream = read_stream
                    self.write_stream = write_stream
                    self.session = session
                    self.connected = True
                    self.connect_time = datetime.now()
                    self.last_activity = datetime.now()
                    self._connected_event.set()

                    await self._shutdown_event.wait()

                    # Workaround for modelcontextprotocol/python-sdk#1805: close
                    # the streams before the contexts exit so SDK tasks blocked
                    # on a zero-buffer send() get ClosedResourceError and stop,
                    # instead of anyio busy-looping in _deliver_cancellation.
                    for stream in (read_stream, write_stream):
                        try:
                            await stream.aclose()
                        except Exception:
                            pass
        except BaseException as exc:  # noqa: BLE001 - connect() reports it
            if not self._connected_event.is_set():
                self._connect_error = exc
                self._connected_event.set()
            # A failure after connecting (server gone, network error) ends the
            # session; the state reset below makes is_connected report it.
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            self.connected = False
            self.session = None
            self.read_stream = None
            self.write_stream = None

    def _observe_connect_failure(self, action: str, description: str, **data: Any) -> None:
        observability.observe(
            event_type=observability.SystemEvents.MCP_SERVER_CONNECTION_FAILED,
            level=observability.EventLevel.ERROR,
            data={
                "service": "mcp",
                "transport": self.transport_type,
                "action": action,
                "url": self.url,
                **data,
            },
            description=description,
        )

    async def connect(self) -> bool:
        """Start the lifecycle task and wait until the session is initialized."""
        if self.connected:
            return True

        self._connected_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._connect_error = None
        self._connection_task = asyncio.create_task(self._connection_lifecycle())

        try:
            # Bounds the whole handshake: the SDK can hang on auth errors (401).
            await asyncio.wait_for(self._connected_event.wait(), timeout=self.request_timeout)
        except asyncio.TimeoutError as e:
            self._observe_connect_failure(
                "connect_timeout",
                f"Connection timed out after {self.request_timeout}s: {self.url}",
                timeout=self.request_timeout,
            )
            await self._cleanup()
            raise MCPConnectionError(
                f"Connection to {self.url} timed out after {self.request_timeout}s"
            ) from e
        except BaseException:
            await self._cleanup()
            raise

        error = self._connect_error
        if error is not None:
            message = _describe_error(error)
            self._observe_connect_failure(
                "connect_failed", f"Connection failed: {message}", error=message
            )
            await self._cleanup()
            raise MCPConnectionError(f"Failed to connect to {self.url}: {message}") from error

        return True

    async def _cleanup(self) -> None:
        """Stop the lifecycle task; it exits the SDK contexts itself."""
        task = self._connection_task
        self._connection_task = None
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        if task is not None and not task.done():
            # Before the session is up the task is not waiting on the shutdown
            # event, so only cancellation stops it.
            if self.session is None:
                task.cancel()
            # asyncio.wait never raises the task's outcome, so only a
            # cancellation of the caller itself propagates from here.
            done, _ = await asyncio.wait({task}, timeout=10)
            if not done:
                task.cancel()
                await asyncio.wait({task})

        self.connected = False
        self.session = None
        self.read_stream = None
        self.write_stream = None

    async def disconnect(self) -> bool:
        """Disconnect from the MCP server."""
        await self._cleanup()
        return True

    @property
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self.connected and self.session is not None
