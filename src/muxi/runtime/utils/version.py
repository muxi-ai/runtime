"""
Version utilities for MUXI Framework.

This module provides utilities for getting and managing version information.
"""

import os

# Observability integration
from ..services import observability


def get_version() -> str:
    """
    Get the version of the MUXI Framework.

    Returns:
        The version string
    """
    # Default version
    default_version = "unknown"

    # Try to read from package.json if it exists
    version_file = os.path.join(os.path.dirname(__file__), "..", "..", ".version")
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            version = f.read().strip()
            return version

    observability.observe(
        event_type=observability.ErrorEvents.RESOURCE_NOT_FOUND,
        level=observability.EventLevel.WARNING,
        description="Version file not found, using default version",
        data={
            "operation": "get_version",
            "version_file_path": version_file,
            "version": version,
            "source": "version_file",
        },
    )

    return default_version
