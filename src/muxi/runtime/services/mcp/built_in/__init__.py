"""
Built-in MCP (Model Context Protocol) servers for MUXI Runtime.

This module contains MCP servers that are bundled with MUXI Runtime and can be
enabled/disabled via formation configuration.
"""

from functools import lru_cache
from pathlib import Path
from typing import Dict

# Registry of built-in MCP servers
BUILTIN_MCP_REGISTRY: Dict[str, str] = {
    # Future additions?:
    # "web-search": "web_search.py",
    # "database": "database.py",
}


def get_builtin_mcp_path(name: str) -> Path:
    """
    Get the absolute path to a built-in MCP server script.

    Args:
        name: Name of the built-in MCP server

    Returns:
        Absolute path to the MCP server script

    Raises:
        ValueError: If the MCP server name is not recognized
    """
    if name not in BUILTIN_MCP_REGISTRY:
        raise ValueError(f"Unknown built-in MCP server: {name}")

    # Get the directory containing this file
    builtin_dir = Path(__file__).parent

    # Return the absolute path to the MCP script
    return builtin_dir / BUILTIN_MCP_REGISTRY[name]


@lru_cache(maxsize=1)
def list_builtin_mcps() -> Dict[str, Path]:
    """
    List all available built-in MCP servers.

    Returns:
        Dictionary mapping MCP names to their absolute paths

    Note: This function is cached since the registry is static.
    """
    builtin_dir = Path(__file__).parent
    return {name: builtin_dir / script for name, script in BUILTIN_MCP_REGISTRY.items()}
