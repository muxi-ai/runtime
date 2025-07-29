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

# Set multitasking to thread mode for shared memory access
multitasking.set_engine("thread")

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

    Args:
        event_type: The event type enum or string
        level: Event level (defaults to INFO)
        data: Additional event data
        description: Human-readable description
    """
    try:
        # Get the runtime event logger
        configured_logger = get_runtime_event_logger()

        # If no runtime logger configured, silently return
        if not configured_logger:
            return

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

        # Start the background task with all parameters explicit
        _emit_in_background(
            configured_logger, request_context, event_type, level, data or {}, description
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


# Create a module-like interface
observability = sys.modules[__name__]
