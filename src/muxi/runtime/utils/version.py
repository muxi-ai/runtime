"""
Version utilities for MUXI Framework.

This module provides utilities for getting and managing version information.
"""

import os

# Observability integration
try:
    from ..observability import ObservabilityManager, ConversationEventType, SystemEventType, EventLevel
except ImportError:
    # Graceful fallback if observability is not available
    ObservabilityManager = None
    ConversationEventType = None
    EventLevel = None


def get_version() -> str:
    """
    Get the version of the MUXI Framework.

    Returns:
        The version string
    """
    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=ConversationEventType.UTILITY_STARTED,
                level=EventLevel.DEBUG,
                message="Starting version retrieval",
                data={
                    "operation": "get_version",
                    "utility": "version"
                }
            )
        except Exception:
            pass

    # Default version
    default_version = "0.1.0"

    try:
        # Try to read from package.json if it exists
        version_file = os.path.join(os.path.dirname(__file__), "..", "..", ".version")

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.FILE_READ_STARTED,
                    level=EventLevel.DEBUG,
                    message="Checking for version file",
                    data={
                        "operation": "get_version",
                        "version_file_path": version_file,
                        "file_exists": os.path.exists(version_file),
                        "default_version": default_version
                    }
                )
            except Exception:
                pass

        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                version = f.read().strip()

            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=ConversationEventType.FILE_READ_COMPLETED,
                        level=EventLevel.DEBUG,
                        message="Version file read successfully",
                        data={
                            "operation": "get_version",
                            "version_file_path": version_file,
                            "version": version,
                            "source": "version_file"
                        }
                    )
                except Exception:
                    pass

            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=ConversationEventType.UTILITY_COMPLETED,
                        level=EventLevel.DEBUG,
                        message="Version retrieval completed successfully",
                        data={
                            "operation": "get_version",
                            "version": version,
                            "source": "version_file",
                            "utility": "version"
                        }
                    )
                except Exception:
                    pass

            return version
        else:
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=ConversationEventType.UTILITY_COMPLETED,
                        level=EventLevel.DEBUG,
                        message="Version retrieval completed using default version",
                        data={
                            "operation": "get_version",
                            "version": default_version,
                            "source": "default",
                            "utility": "version",
                            "reason": "version_file_not_found"
                        }
                    )
                except Exception:
                    pass

            return default_version

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Version retrieval failed, using default version",
                    data={
                        "operation": "get_version",
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "fallback_version": default_version,
                        "utility": "version"
                    }
                )
            except Exception:
                pass

        print(f"Error getting version: {e}")
        return default_version
