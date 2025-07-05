# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Base Transport - Abstract Transport Interface
# Description:  Base classes and error types for MCP transports
# Role:         Provides common interfaces and error handling for all transports
# Usage:        Extended by concrete transport implementations
# Author:       Muxi Framework Team
# =============================================================================

import json
from typing import Any, Dict, Optional
from datetime import datetime


class MCPError(Exception):
    """
    Base exception class for MCP-related errors.

    This serves as the parent class for all MCP-specific exceptions,
    providing a consistent interface for error handling and propagation.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize an MCP error.

        Args:
            message: Human-readable error message describing what went wrong
            details: Optional dictionary with additional error context and details
        """
        self.message = message
        self.details = details or {}
        super().__init__(f"{message}" + (f": {json.dumps(details)}" if details else ""))


class MCPConnectionError(MCPError):
    """
    Exception raised for connection-related errors.

    This exception indicates issues establishing or maintaining a connection
    to an MCP server, such as network failures, authentication problems,
    or server unavailability.
    """

    pass


class MCPRequestError(MCPError):
    """
    Exception raised for errors when making requests to MCP servers.

    This exception indicates issues with specific requests, such as
    invalid parameters, missing permissions, or server-side errors
    during tool execution.
    """

    pass


class MCPTimeoutError(MCPError):
    """
    Exception raised when MCP operations time out.

    This exception indicates that a request to an MCP server took
    longer than the specified timeout period, which could be due to
    network issues, server overload, or long-running operations.
    """

    pass


class MCPCancelledError(MCPError):
    """
    Exception raised when an MCP operation is cancelled.

    This exception indicates that an operation was intentionally
    cancelled, typically by user action or as part of cleanup during
    error handling or shutdown.
    """

    pass


class CancellationToken:
    """
    A token that can be used to cancel async operations.

    This class provides a mechanism for cancelling asynchronous operations,
    such as MCP requests, by registering tasks that should be cancelled
    when the token is cancelled.
    """

    def __init__(self):
        """Initialize a new cancellation token in the non-cancelled state."""
        self.cancelled = False
        self._tasks = set()

    def cancel(self):
        """
        Mark the token as cancelled and cancel all registered tasks.

        This method cancels all asyncio tasks that have been registered
        with this token, allowing for coordinated cancellation of related
        operations.
        """
        self.cancelled = True
        for task in self._tasks:
            if not task.done():
                task.cancel()

    def register(self, task):
        """
        Register a task to be cancelled when this token is cancelled.

        Args:
            task: The asyncio task to register for cancellation
        """
        self._tasks.add(task)

    def unregister(self, task):
        """
        Unregister a task so it won't be cancelled with this token.

        Args:
            task: The asyncio task to unregister
        """
        if task in self._tasks:
            self._tasks.remove(task)

    def throw_if_cancelled(self):
        """
        Throw an exception if this token has been cancelled.

        Raises:
            MCPCancelledError: If this token has been cancelled
        """
        if self.cancelled:
            raise MCPCancelledError(
                "Operation was cancelled", {"timestamp": datetime.now().isoformat()}
            )


class BaseTransport:
    """
    Base class for all MCP transport implementations.

    This abstract class defines the interface that all transport implementations
    must follow, providing a consistent way to connect to different types of
    MCP servers regardless of the underlying transport mechanism.
    """

    def __init__(self, url: str, request_timeout: int = 30, auth: Optional[Any] = None):
        """
        Initialize the base transport.

        Args:
            url: MCP server URL (must include protocol)
            request_timeout: Default timeout for requests in seconds
            auth: Optional authentication configuration
        """
        self.url = url.rstrip("/")
        self.request_timeout = request_timeout
        self.auth = auth
        self.connected = False
        self.connect_time = None
        self.last_activity = None

        # Connection statistics
        self.connection_stats = {
            "requests_sent": 0,
            "responses_received": 0,
            "errors_encountered": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
        }

    async def connect(self) -> bool:
        """
        Connect to the MCP server.

        Returns:
            bool: True if connected successfully

        Raises:
            NotImplementedError: Subclasses must implement this method
        """
        raise NotImplementedError("Subclasses must implement connect()")

    async def send_request(self, request_obj: Any, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Send a request to the MCP server.

        Args:
            request_obj: The request object to send
            timeout: Optional timeout in seconds (overrides default)

        Returns:
            Dict: The response from the server

        Raises:
            NotImplementedError: Subclasses must implement this method
        """
        raise NotImplementedError("Subclasses must implement send_request()")

    async def disconnect(self) -> bool:
        """
        Disconnect from the MCP server.

        Returns:
            bool: True if disconnected successfully

        Raises:
            NotImplementedError: Subclasses must implement this method
        """
        raise NotImplementedError("Subclasses must implement disconnect()")

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics and performance metrics.

        Returns:
            Dict containing connection statistics
        """
        return {
            "url": self.url,
            "connected": self.connected,
            "connect_time": self.connect_time.isoformat() if self.connect_time else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            **self.connection_stats,
        }

    async def test_connection(self) -> bool:
        """
        Quick test to see if transport can connect.
        Used for fallback detection.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            await self.connect()
            if self.connected:
                await self.disconnect()
                return True
            return False
        except Exception:
            return False
