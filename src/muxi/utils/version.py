"""
Version utilities for MUXI Framework.

This module provides utilities for getting and managing version information.
"""

import os


def get_version() -> str:
    """
    Get the version of the MUXI Framework.

    Returns:
        The version string
    """
    # Default version
    default_version = "unknown"
    version = default_version  # Initialize version variable

    # Try to read from .version file in runtime directory
    version_file = os.path.join(os.path.dirname(__file__), "..", ".version")
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            version = f.read().strip()
            return version

    return default_version
