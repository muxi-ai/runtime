"""MCP Resources support for MUXI Framework.

This package provides client-side support for MCP Resources protocol,
including resource discovery and content reading.
"""

from .discovery import MCPResourceDiscovery
from .manager import MCPResourceManager

__all__ = [
    "MCPResourceDiscovery",
    "MCPResourceManager",
]
