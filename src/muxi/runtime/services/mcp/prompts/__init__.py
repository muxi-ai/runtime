"""MCP Prompts support for MUXI Framework.

This package provides client-side support for MCP Prompts protocol,
including prompt discovery and retrieval with argument substitution.
"""

from .discovery import MCPPromptDiscovery
from .manager import MCPPromptManager

__all__ = [
    "MCPPromptDiscovery",
    "MCPPromptManager",
]
