"""
Cross-platform user directory utilities for Muxi Runtime.

This module provides consistent user directory paths across platforms:
- Windows: %APPDATA%/muxi
- Mac/Linux: ~/.muxi
"""

import os
from pathlib import Path

# Default formation ID used for directory organization
FORMATION_ID = "default"


def set_formation_id(formation_id: str) -> None:
    """Set the formation ID for the user directory.

    Args:
        formation_id: Formation ID to use for directory organization
    """
    global FORMATION_ID
    FORMATION_ID = formation_id


def get_user_dir(subdir: str = None) -> Path:
    """Get user directory path for a specific subdirectory.

    Args:
        subdir: Subdirectory name (e.g., 'cache', 'data', 'logs')

    Returns:
        Full path to the user subdirectory as a Path object
    """
    home = Path.home()

    if subdir is None:
        # Return base muxi directory based on platform
        if os.name == "nt":  # Windows
            appdata = os.environ.get("APPDATA", home / "AppData" / "Roaming")
            dir = Path(appdata) / "muxi"
        else:  # Mac/Linux
            dir = home / ".muxi"
    else:
        # Return subdirectory with platform-specific casing
        if os.name == "nt":  # Windows
            appdata = os.environ.get("APPDATA", home / "AppData" / "Roaming")
            dir = Path(appdata) / "muxi" / subdir.title()
        else:  # Mac/Linux
            dir = home / ".muxi" / subdir.lower()

    # Ensure directory exists
    dir.mkdir(parents=True, exist_ok=True)
    return dir


def get_formation_dir(subdir: str = None) -> str:
    """Get formation directory path.

    Args:
        subdir: Optional subdirectory within formation directory

    Returns:
        Full path to the formation directory as a string
    """
    if subdir is None:
        dir = get_user_dir(FORMATION_ID)
    else:
        dir = get_user_dir(f"{FORMATION_ID}/{subdir}")

    # Ensure directory exists
    dir.mkdir(parents=True, exist_ok=True)
    return str(dir)


def get_cache_dir(subdir: str = None) -> str:
    """Get user cache directory path.

    Args:
        subdir: Optional subdirectory within cache directory

    Returns:
        Full path to the cache directory or subdirectory as a string
    """
    if subdir:
        return get_formation_dir(f"cache/{subdir}")
    else:
        return get_formation_dir("cache")


def get_data_dir() -> str:
    """Get user data directory path.

    Returns:
        Full path to the user data directory as a string
    """
    return get_formation_dir("data")


def get_logs_dir() -> str:
    """Get user logs directory path.

    Returns:
        Full path to the user logs directory as a string
    """
    return get_formation_dir("logs")


def get_knowledge_dir() -> str:
    """Get cache directory for knowledge embeddings.

    Returns:
        Full path to the knowledge embeddings cache directory as a string
    """
    return get_cache_dir("knowledge")


def get_a2a_cache_dir() -> str:
    """Get cache directory for A2A operations.

    Returns:
        Full path to the A2A cache directory as a string
    """
    return get_cache_dir("a2a")


def get_a2a_cards_dir() -> str:
    """Get cache directory for A2A service discovery cards.

    Returns:
        Full path to the A2A cards cache directory as a string
    """
    return get_cache_dir("a2a_cards")


def get_a2a_registry_dir() -> str:
    """Get cache directory for A2A service discovery registry.

    Returns:
        Full path to the A2A registry cache directory as a string
    """
    return get_cache_dir("a2a_registry")


def get_memory_dir() -> str:
    """Get directory for knowledge embeddings storage.

    Returns:
        Full path to the memory directory as a string
    """
    return get_formation_dir("memory")


def get_mcp_cache_dir() -> str:
    """Get cache directory for MCP server responses.

    Returns:
        Full path to the MCP cache directory as a string
    """
    return get_cache_dir("mcp")


def get_model_cache_dir() -> str:
    """Get cache directory for model responses.

    Returns:
        Full path to the model cache directory as a string
    """
    return get_cache_dir("models")


def get_session_cache_dir() -> str:
    """Get cache directory for session data.

    Returns:
        Full path to the session cache directory as a string
    """
    return get_cache_dir("sessions")


def get_observability_dir() -> str:
    """Get directory for observability data.

    Returns:
        Full path to the observability directory as a string
    """
    return get_formation_dir("observability")
