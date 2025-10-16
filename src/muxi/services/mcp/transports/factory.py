# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Transport Factory - Transport Creation and Management
# Description:  Factory for creating and configuring MCP transport instances
# Role:         Provides unified interface for transport instantiation
# Usage:        Used to create appropriate transport based on connection parameters
# Author:       Muxi Framework Team
# =============================================================================

import threading
from typing import Optional, List, Dict, Any, Set
from .base import BaseTransport, MCPConnectionError
from .http_sse import HTTPSSETransport
from .streamable import StreamableHTTPTransport
from .command import CommandLineTransport
from ... import observability

# Module-level cache for SSE servers (persists for formation lifetime)
_sse_server_cache: Set[str] = set()
_sse_cache_lock = threading.Lock()  # Use threading.Lock for both sync and async contexts


class MCPTransportFactory:
    """
    Factory class for creating MCP transport instances.

    Supports automatic transport selection with fallback capabilities:
    - Streamable HTTP (MCP 2025-03-26) - Primary choice for HTTP URLs
    - HTTP+SSE (MCP 2024-11-05) - Fallback for HTTP URLs (deprecated)
    - Command Line - For local process communication

    Formation YAML only exposes two types: "command" and "http"
    HTTP automatically tries streamable first, falls back to SSE if needed.
    """

    # Supported transport types (internal use only)
    TRANSPORT_STREAMABLE_HTTP = "streamable_http"
    TRANSPORT_HTTP_SSE = "http_sse"
    TRANSPORT_COMMAND = "command"

    @staticmethod
    def create_transport(
        url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        transport_type: Optional[str] = None,  # Kept for API compatibility, auto-detected
        auth: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> BaseTransport:
        """Create a transport instance based on parameters.

        Args:
            url: URL for HTTP-based MCP servers
            command: Command for command-line based MCP servers
            args: Optional list of arguments for command-line MCP servers
            transport_type: Explicit transport type selection
            auth: Authentication configuration
            **kwargs: Additional parameters for transport initialization

        Returns:
            An instance of BaseTransport

        Raises:
            ValueError: If parameters are invalid
        """
        # Extract auth from kwargs if not provided directly
        if auth is None and "credentials" in kwargs:
            auth = kwargs["credentials"]

        # Validate basic parameters
        if url is not None and command is not None:
            raise ValueError(
                "Cannot provide both url and command. "
                "Use url for HTTP servers and command for command-line servers."
            )

        if url is None and command is None:
            raise ValueError("Must provide either url or command.")

        # Extract common parameters
        request_timeout = kwargs.get("request_timeout", 60)

        # Handle command-line transport
        if command is not None:
            return CommandLineTransport(
                command, args=args, auth=auth, request_timeout=request_timeout
            )

        # Handle HTTP-based transports
        if url is not None:
            # Check if we already know this server uses SSE
            with _sse_cache_lock:
                if url in _sse_server_cache:
                    return HTTPSSETransport(url, request_timeout=request_timeout, auth=auth)

            # Default to streamable HTTP
            return StreamableHTTPTransport(url, request_timeout=request_timeout, auth=auth)

        # This should never be reached due to earlier validation
        raise ValueError("Unable to determine appropriate transport type.")

    @staticmethod
    async def create_transport_with_fallback(
        url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        auth: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> BaseTransport:
        """
        Create transport with automatic SSE fallback for HTTP servers.

        This is the main entry point that implements the fallback logic.
        For HTTP servers:
        1. Try streamable HTTP first (unless we know it's SSE)
        2. Fall back to SSE if streamable fails
        3. Cache SSE servers for formation lifetime

        Args:
            url: URL for HTTP-based MCP servers
            command: Command for command-line based MCP servers
            args: Optional list of arguments for command-line MCP servers
            auth: Authentication configuration
            **kwargs: Additional parameters for transport initialization

        Returns:
            An instance of BaseTransport

        Raises:
            MCPConnectionError: If both transports fail
            ValueError: If parameters are invalid
        """
        # Extract auth from kwargs if not provided directly
        if auth is None and "credentials" in kwargs:
            auth = kwargs["credentials"]

        # For command-line, no fallback needed
        if command is not None:
            return MCPTransportFactory.create_transport(
                command=command, args=args, auth=auth, **kwargs
            )

        # For HTTP URLs, implement fallback logic
        if url is not None:
            pass  # REMOVED: init-phase observe() call
            # First, try streamable HTTP (unless we know it's SSE)
            with _sse_cache_lock:
                is_sse_cached = url in _sse_server_cache

            if not is_sse_cached:
                try:
                    transport = MCPTransportFactory.create_transport(url=url, auth=auth, **kwargs)
                    # Try to connect to verify it works
                    await transport.connect()
                    if transport.connected:
                        return transport
                    else:
                        await transport.disconnect()
                except Exception as e:
                    # Log the streamable HTTP failure
                    observability.observe(
                        event_type=observability.SystemEvents.MCP_TRANSPORT_FAILED,
                        level=observability.EventLevel.DEBUG,
                        data={"service": "mcp", "action": "streamable_failed", "url": url, "error": str(e)},
                        description=f"Streamable HTTP failed for {url}: {e}"
                    )

            # Fall back to SSE
            observability.observe(
                event_type=observability.SystemEvents.MCP_TRANSPORT_ATTEMPT,
                level=observability.EventLevel.INFO,
                data={"service": "mcp", "action": "fallback_to_sse", "url": url},
                description=f"Falling back to SSE for {url}"
            )
            try:
                transport = HTTPSSETransport(url, auth=auth, **kwargs)
                # Test SSE connection too
                await transport.connect()
                if transport.connected:
                    observability.observe(
                        event_type=observability.SystemEvents.MCP_TRANSPORT_FALLBACK_SUCCESS,
                        level=observability.EventLevel.INFO,
                        data={"service": "mcp", "action": "sse_success", "url": url},
                        description="SSE connection successful"
                    )
                    # Remember this server uses SSE
                    with _sse_cache_lock:
                        _sse_server_cache.add(url)
                    pass  # REMOVED: init-phase observe() call
                    return transport
                else:
                    observability.observe(
                        event_type=observability.ErrorEvents.WARNING,
                        level=observability.EventLevel.WARNING,
                        data={"service": "mcp", "action": "sse_test_failed", "url": url},
                        description="SSE connection test failed"
                    )
                    await transport.disconnect()
            except Exception as e:
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_CONNECTION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={"service": "mcp", "action": "sse_test_failed", "url": url, "error": str(e)},
                    description=f"SSE test failed for {url}: {e}"
                )

            # Both transports failed
            raise MCPConnectionError(
                f"Failed to connect to {url} with both streamable HTTP and SSE"
            )

        raise ValueError("Must provide either url or command.")

    @staticmethod
    def supports_parameters(
        url: Optional[str] = None,
        command: Optional[str] = None,
        transport_type: Optional[str] = None,
    ) -> bool:
        """Check if the provided parameters are supported.

        Args:
            url: URL for HTTP-based MCP servers
            command: Command for command-line based MCP servers
            transport_type: Explicit transport type selection

        Returns:
            True if parameters are supported, False otherwise
        """
        # Basic parameter validation
        if url is not None and command is not None:
            return False
        if url is None and command is None:
            return False

        # Validate transport type compatibility
        if transport_type is not None:
            supported_types = [
                MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP,
                MCPTransportFactory.TRANSPORT_HTTP_SSE,
                MCPTransportFactory.TRANSPORT_COMMAND,
            ]

            if transport_type not in supported_types:
                return False

            # Check transport type compatibility with parameters
            if command is not None and transport_type != MCPTransportFactory.TRANSPORT_COMMAND:
                return False
            if url is not None and transport_type == MCPTransportFactory.TRANSPORT_COMMAND:
                return False

        return True

    @staticmethod
    def get_supported_transport_types() -> List[str]:
        """Get list of supported transport types.

        Returns:
            List of supported transport type strings
        """
        return [
            MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP,
            MCPTransportFactory.TRANSPORT_HTTP_SSE,
            MCPTransportFactory.TRANSPORT_COMMAND,
        ]

    @staticmethod
    def get_default_transport_type(url: Optional[str] = None, command: Optional[str] = None) -> str:
        """Get the default transport type for given parameters.

        Args:
            url: URL for HTTP-based MCP servers
            command: Command for command-line based MCP servers

        Returns:
            Default transport type string

        Raises:
            ValueError: If parameters are invalid
        """
        if url is not None and command is None:
            return MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP
        elif command is not None and url is None:
            return MCPTransportFactory.TRANSPORT_COMMAND
        else:
            raise ValueError("Must provide either url or command, but not both.")
