"""
Cross-platform user directory utilities for Muxi Runtime.

This module provides consistent user directory paths across platforms:
- Windows: %APPDATA%/muxi
- Mac/Linux: ~/.muxi
"""

import os
from pathlib import Path


def user_dir(subdir: str = None) -> str:
    """Get user directory path for a specific subdirectory.

    Args:
        subdir: Subdirectory name (e.g., 'cache', 'data', 'logs')

    Returns:
        Full path to the user subdirectory
    """
    home = Path.home()

    if os.name == 'nt':  # Windows
        # Use %APPDATA%\muxi\Subdir
        appdata = os.environ.get('APPDATA', home / "AppData" / "Roaming")
        return str(Path(appdata) / "muxi" / subdir.title())
    else:
        # Use ~/.muxi/subdir (all lowercase on Unix-like systems)
        return str(home / ".muxi" / subdir.lower())


def user_cache_dir(subdir: str = None) -> str:
    """Get user cache directory path.

    Returns:
        Full path to the user cache directory
    """
    if subdir is None:
        return user_dir()
    return user_dir(f"cache/{subdir}")


def user_data_dir() -> str:
    """Get user data directory path.

    Returns:
        Full path to the user data directory
    """
    return user_dir("data")


def user_logs_dir() -> str:
    """Get user logs directory path.

    Returns:
        Full path to the user logs directory
    """
    return user_dir("logs")
