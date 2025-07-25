# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Transports - Model Context Protocol Transport Layer
# Description:  Transport implementations for MCP communication
# Role:         Provides transport abstractions for different MCP protocols
# Usage:        Used by MCPHandler and MCPService for server communication
# Author:       Muxi Framework Team
#
# This package contains all transport implementations for the Model Context
# Protocol, organized by transport type for better maintainability.
# =============================================================================

# Error classes
from .base import (
    MCPError,
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
    MCPCancelledError,
    CancellationToken,
    BaseTransport,
)

# Transport implementations
from .http_sse import HTTPSSETransport
from .streamable import StreamableHTTPTransport
from .command import CommandLineTransport

# Factory
from .factory import MCPTransportFactory

# Transport utilities
from .detector import TransportDetector
from .protocol_features import ModernProtocolFeatures

__all__ = [
    # Error classes and utilities
    "MCPError",
    "MCPConnectionError",
    "MCPRequestError",
    "MCPTimeoutError",
    "MCPCancelledError",
    "CancellationToken",
    "BaseTransport",
    # Transport implementations
    "HTTPSSETransport",
    "StreamableHTTPTransport",
    "CommandLineTransport",
    # Factory and utilities
    "MCPTransportFactory",
    "TransportDetector",
    "ModernProtocolFeatures",
]
