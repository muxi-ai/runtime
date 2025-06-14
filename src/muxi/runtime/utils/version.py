"""
Version utilities for MUXI Framework.

This module provides utilities for getting and managing version information.
"""

import os

# Observability integration
from .. import observability


def get_version() -> str:
    """
    Get the version of the MUXI Framework.

    Returns:
        The version string
    """
    observability.emit_event(
        event_type=observability.SystemEvents.UTILITY_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting version retrieval",
        data={"operation": "get_version", "utility": "version"},
    )

    # Default version
    default_version = "0.1.0"

    try:
        # Try to read from package.json if it exists
        version_file = os.path.join(os.path.dirname(__file__), "..", "..", ".version")

        observability.emit_event(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.DEBUG,
            description="Checking for version file",
            data={
                "operation": "get_version",
                "version_file_path": version_file,
                "file_exists": os.path.exists(version_file),
                "default_version": default_version,
            },
        )

        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                version = f.read().strip()

            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_COMPLETED,
                level=observability.EventLevel.DEBUG,
                description="Version file read successfully",
                data={
                    "operation": "get_version",
                    "version_file_path": version_file,
                    "version": version,
                    "source": "version_file",
                },
            )

            observability.emit_event(
                event_type=observability.SystemEvents.UTILITY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                description="Version retrieval completed successfully",
                data={
                    "operation": "get_version",
                    "version": version,
                    "source": "version_file",
                    "utility": "version",
                },
            )

            return version
        else:
            observability.emit_event(
                event_type=observability.SystemEvents.UTILITY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                description="Version retrieval completed using default version",
                data={
                    "operation": "get_version",
                    "version": default_version,
                    "source": "default",
                    "utility": "version",
                    "reason": "version_file_not_found",
                },
            )

            return default_version

    except Exception as e:
        observability.emit_event(
            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
            level=observability.EventLevel.ERROR,
            description="Version retrieval failed, using default version",
            data={
                "operation": "get_version",
                "error": str(e),
                "error_type": type(e).__name__,
                "fallback_version": default_version,
                "utility": "version",
            },
        )

        print(f"Error getting version: {e}")
        return default_version
