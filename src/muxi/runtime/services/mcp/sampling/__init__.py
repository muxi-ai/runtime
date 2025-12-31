"""MCP Sampling support for MUXI Framework.

This package provides client-side support for MCP Sampling protocol,
allowing MCP servers to generate completions using LLM capabilities.
"""

from .client import MCPSamplingClient
from .manager import MCPSamplingManager

__all__ = [
    "MCPSamplingClient",
    "MCPSamplingManager",
]
