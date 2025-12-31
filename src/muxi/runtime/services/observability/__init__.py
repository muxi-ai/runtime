"""
MUXI Observability System

This module provides the dual logging architecture for MUXI runtime:
1. SystemEvents: Infrastructure events, startup, MCP/A2A operations (always stdout)
2. ConversationEvents: User request lifecycle tracking (configurable output)

Key Components:
- EventLogger: Central component for event emission with intelligent routing
- SystemEvents: Enum for system infrastructure events (routed to stdout)
- ConversationEvents: Enum for conversation lifecycle events (routed to configured output)
- RequestContextManager: In-memory request tracking with automatic cleanup
- Event structures with JSON-L formatting for external tool consumption

Event Routing:
- SystemEvents events → Always stdout (for server monitoring)
- ConversationEvents events → Configured output (stdout/file/stream/trail for observability)

Note: This implementation follows the specification with dual event architecture.
"""

import sys

# Import all types and classes
from ...datatypes.observability import (
    APIEvents,
    ConversationEvents,
    ErrorEvents,
    EventLevel,
    InitEventFormatter,
    InitFailureInfo,
    RequestContext,
    ServerEvents,
    SystemEvents,
    TokenUsage,
)
from .context import get_current_request_context, set_request_context
from .logger import EventLogger
from .manager import ObservabilityManager
from .request_manager import RequestContextManager

# Main exports
__all__ = [
    # Event types and levels
    "APIEvents",
    "ConversationEvents",
    "ErrorEvents",
    "EventLevel",
    "ServerEvents",
    "SystemEvents",
    # Data classes
    "InitEventFormatter",
    "InitFailureInfo",
    "RequestContext",
    "TokenUsage",
    # Context management
    "get_current_request_context",
    "set_request_context",
    # Core classes
    "EventLogger",
    "ObservabilityManager",
    "RequestContextManager",
    # Helper functions
    "emit_event",
    "observe",
    "enable",
    "disable",
    "is_enabled",
    # Runtime logger management
    "get_runtime_event_logger",
    "set_runtime_event_logger",
]


# ===================================================================
# CLEAN MODULE INTERFACE WITH EXPLICIT HELPER FUNCTION
# ===================================================================

from typing import Any, Dict, Optional, Union
import multitasking
import signal
import threading

from ...utils.security import redact_sensitive_content

# Set multitasking to thread mode for shared memory access
multitasking.set_engine("thread")


# PII Redaction Helper
def _redact_data_recursive(obj: Any) -> Any:
    """
    Recursively redact PII in nested data structures.

    Uses redact_sensitive_content() from utils.security to redact:
    - API keys and tokens
    - Passwords and secrets
    - Email addresses (partial)
    - Phone numbers
    - Credit card numbers
    - SSNs
    - AWS credentials
    - Database connection strings
    - JWT tokens

    Args:
        obj: Data to redact (can be str, dict, list, tuple, or primitive)

    Returns:
        Redacted copy of the data
    """
    if isinstance(obj, str):
        return redact_sensitive_content(obj)
    elif isinstance(obj, dict):
        return {k: _redact_data_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        result = [_redact_data_recursive(item) for item in obj]
        return result if isinstance(obj, list) else tuple(result)
    else:
        # Numbers, bools, None, etc. - return as-is
        return obj


# Kill all tasks on ctrl-c for clean shutdown
# Only register signal handlers in main thread to avoid errors in tests
try:
    signal.signal(signal.SIGINT, multitasking.killall)
except ValueError:
    # Signal handlers can only be registered in main thread
    # This is expected in tests or when imported from threads
    pass


# ===================================================================
# RUNTIME EVENT LOGGER STORAGE
# ===================================================================

# Global runtime variable to store the configured EventLogger
_runtime_event_logger: Optional["EventLogger"] = None
_runtime_event_logger_lock = threading.Lock()

# Global flag to control observability event emission
# Start disabled during init, enable after formation is ready
_enabled = False


def set_runtime_event_logger(logger: "EventLogger") -> None:
    """Set the runtime event logger for global access."""
    global _runtime_event_logger
    with _runtime_event_logger_lock:
        _runtime_event_logger = logger


def get_runtime_event_logger() -> Optional["EventLogger"]:
    """Get the runtime event logger."""
    with _runtime_event_logger_lock:
        return _runtime_event_logger


def observe(
    event_type: Union[SystemEvents, ConversationEvents, ServerEvents, ErrorEvents, APIEvents, str],
    level: EventLevel = EventLevel.INFO,
    data: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> None:
    """
    Emit an observability event (non-blocking).

    This function captures the request context and configured logger before
    spawning a background thread to ensure context is properly passed to the thread.

    Note: If observability is disabled (during init), this is a no-op.

    Args:
        event_type: The event type enum or string
        level: Event level (defaults to INFO)
        data: Additional event data
        description: Human-readable description
    """
    global _enabled

    # Skip if observability is disabled (during init)
    if not _enabled:
        return

    try:
        # Get the runtime event logger
        configured_logger = get_runtime_event_logger()

        # If no runtime logger configured, silently return
        if not configured_logger:
            return

        # Conditionally redact PII based on event type
        # Only redact for user-facing events (conversation, errors, API, user-related)
        should_redact = False
        if isinstance(event_type, (ConversationEvents, ErrorEvents, APIEvents)):
            should_redact = True
        elif isinstance(event_type, str):
            # Check for user-related keywords in string event types
            event_type_lower = event_type.lower()
            if any(keyword in event_type_lower for keyword in ["user", "conversation", "message", "error", "api"]):
                should_redact = True

        if should_redact:
            redacted_data = _redact_data_recursive(data or {})
            redacted_description = _redact_data_recursive(description) if description else ""
        else:
            redacted_data = data or {}
            redacted_description = description or ""

        # Get request context
        from .context import get_current_request_context
        request_context = get_current_request_context()

        @multitasking.task
        def _emit_in_background(logger, context, evt_type, evt_level, evt_data, evt_desc):
            try:
                # Use all parameters passed explicitly - no closure dependencies
                logger.emit_event(
                    event_type=evt_type,
                    level=evt_level,
                    data=evt_data,
                    description=evt_desc,
                    request_context=context,
                )
            except Exception:
                # Silently fail if observability unavailable
                pass

        # Start the background task with all parameters explicit (using redacted data)
        _emit_in_background(
            configured_logger, request_context, event_type, level, redacted_data, redacted_description
        )

    except Exception:
        # Silently fail if observability unavailable
        pass


def emit_event(
    event_type: Union[SystemEvents, ConversationEvents, ServerEvents, ErrorEvents, APIEvents, str],
    level: EventLevel = EventLevel.INFO,
    data: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> None:
    """
    Alias for observe() function for backward compatibility.

    Args:
        event_type: The event type enum or string
        level: Event level (defaults to INFO)
        data: Additional event data
        description: Human-readable description
    """
    observe(event_type, level, data, description)


def enable() -> None:
    """
    Enable observability event emission.

    Should be called after formation initialization is complete.
    This starts the flow of JSON observability events.
    """
    global _enabled
    _enabled = True


def disable() -> None:
    """
    Disable observability event emission.

    Used during initialization to suppress JSON events and show only
    clean formatted output.
    """
    global _enabled
    _enabled = False


def is_enabled() -> bool:
    """
    Check if observability is currently enabled.

    Returns:
        True if observability events are being emitted, False otherwise
    """
    global _enabled
    return _enabled


# Create a module-like interface
observability = sys.modules[__name__]
