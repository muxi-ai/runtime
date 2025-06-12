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
    default_version = "0.1.0"

    try:
        # Try to read from package.json if it exists
        version_file = os.path.join(os.path.dirname(__file__), "..", "..", ".version")
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()

        return default_version
    except Exception as e:
        print(f"Error getting version: {e}")
        return default_version
