# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Transport Factory - Transport Creation and Management
# Description:  Factory for creating and configuring MCP transport instances
# Role:         Provides unified interface for transport instantiation
# Usage:        Used to create appropriate transport based on connection parameters
# Author:       Muxi Framework Team
# =============================================================================

from typing import Optional, List
from .base import BaseTransport
from .http_sse import HTTPSSETransport
from .streamable import StreamableHTTPTransport
from .command import CommandLineTransport


class MCPTransportFactory:
    """
    Factory class for creating MCP transport instances.

    Supports automatic transport selection with fallback capabilities:
    - Streamable HTTP (MCP 2025-03-26) - Primary choice for HTTP URLs
    - HTTP+SSE (MCP 2024-11-05) - Fallback for HTTP URLs
    - Command Line - For local process communication
    """

    # Supported transport types
    TRANSPORT_STREAMABLE_HTTP = "streamable_http"
    TRANSPORT_HTTP_SSE = "http_sse"
    TRANSPORT_COMMAND = "command"

    @staticmethod
    def create_transport(
        url: Optional[str] = None,
        command: Optional[str] = None,
        transport_type: Optional[str] = None,
        **kwargs
    ) -> BaseTransport:
        """Create a transport instance based on parameters.

        Args:
            url: URL for HTTP-based MCP servers
            command: Command for command-line based MCP servers
            transport_type: Explicit transport type selection:
                - "streamable_http": Use Streamable HTTP (MCP 2025-03-26)
                - "http_sse": Use HTTP+SSE (MCP 2024-11-05)
                - "command": Use command-line transport
                - None: Auto-select (defaults to streamable_http for URLs)
            **kwargs: Additional parameters for transport initialization

        Returns:
            An instance of BaseTransport

        Raises:
            ValueError: If parameters are invalid or transport type is unsupported
        """
        # TODO: Add observability logging for transport creation

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
            if transport_type is not None and transport_type != MCPTransportFactory.TRANSPORT_COMMAND:
                raise ValueError(
                    f"Transport type '{transport_type}' is not compatible with command parameter. "
                    f"Use transport_type='{MCPTransportFactory.TRANSPORT_COMMAND}' or omit it."
                )
            return CommandLineTransport(command)

        # Handle HTTP-based transports
        if url is not None:
            # Auto-select transport type if not specified
            if transport_type is None:
                transport_type = MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP

            # Create appropriate HTTP transport
            if transport_type == MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP:
                return StreamableHTTPTransport(url, request_timeout)
            elif transport_type == MCPTransportFactory.TRANSPORT_HTTP_SSE:
                return HTTPSSETransport(url, request_timeout)
            else:
                raise ValueError(
                    f"Unsupported transport type '{transport_type}' for HTTP URLs. "
                    f"Supported types: {MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP}, "
                    f"{MCPTransportFactory.TRANSPORT_HTTP_SSE}"
                )

        # This should never be reached due to earlier validation
        raise ValueError("Unable to determine appropriate transport type.")

    @staticmethod
    def create_transport_with_fallback(
        url: Optional[str] = None,
        command: Optional[str] = None,
        **kwargs
    ) -> BaseTransport:
        """
        Create a transport instance with automatic fallback for HTTP URLs.

        For HTTP URLs, attempts to create StreamableHTTPTransport first,
        then falls back to HTTPSSETransport if needed.

        Args:
            url: URL for HTTP-based MCP servers
            command: Command for command-line based MCP servers
            **kwargs: Additional parameters for transport initialization

        Returns:
            An instance of BaseTransport

        Raises:
            ValueError: If parameters are invalid
        """
        # TODO: Add observability logging for transport creation with fallback

        # For command-line, no fallback needed
        if command is not None:
            return MCPTransportFactory.create_transport(command=command, **kwargs)

        # For HTTP URLs, try streamable_http first
        if url is not None:
            try:
                return MCPTransportFactory.create_transport(
                    url=url,
                    transport_type=MCPTransportFactory.TRANSPORT_STREAMABLE_HTTP,
                    **kwargs
                )
            except Exception:
                # TODO: Add observability logging for fallback
                # Fall back to HTTP+SSE
                return MCPTransportFactory.create_transport(
                    url=url,
                    transport_type=MCPTransportFactory.TRANSPORT_HTTP_SSE,
                    **kwargs
                )

        raise ValueError("Must provide either url or command.")

    @staticmethod
    def supports_parameters(
        url: Optional[str] = None,
        command: Optional[str] = None,
        transport_type: Optional[str] = None
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
                MCPTransportFactory.TRANSPORT_COMMAND
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
            MCPTransportFactory.TRANSPORT_COMMAND
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
