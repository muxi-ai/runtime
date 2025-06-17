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

Note: This implementation follows Task 5 Phase 1 specification with dual event architecture.
"""

# Import all types and classes
from .types import (
    EventLevel,
    SystemEvents,
    ConversationEvents,
    ServerEvents,
    ErrorEvents,
    TokenUsage,
    RequestContext,
)
from .context import get_current_request_context, set_request_context
from .logger import EventLogger
from .manager import ObservabilityManager
from .request_manager import RequestContextManager

# Main exports
__all__ = [
    # Event types and levels
    "EventLevel",
    "SystemEvents",
    "ConversationEvents",
    "ServerEvents",
    "ErrorEvents",
    # Data classes
    "TokenUsage",
    "RequestContext",
    # Context management
    "get_current_request_context",
    "set_request_context",
    # Core classes
    "EventLogger",
    "ObservabilityManager",
    "RequestContextManager",
    # Helper functions
    "emit_event",
    "observe",  # Backward compatibility
]


# ===================================================================
# CLEAN MODULE INTERFACE WITH EXPLICIT HELPER FUNCTION
# ===================================================================

import asyncio
from typing import Any, Dict, Optional, Union


def emit_event(
    event_type: Union[SystemEvents, ConversationEvents, str],
    level: EventLevel = EventLevel.INFO,
    data: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> None:
    """
    Emit an observability event.

    This is a clean helper function that creates a minimal event logger
    instance for immediate use. For advanced usage, use ObservabilityManager directly.

    Args:
        event_type: The event type enum or string
        level: Event level (defaults to INFO)
        data: Additional event data
        description: Human-readable description
    """
    try:
        # Create a minimal event logger for immediate use
        from .logger import EventLogger
        logger = EventLogger(level=EventLevel.DEBUG, output="stdout")

        # Run the async emission in a sync context
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create new one
            asyncio.run(logger.emit_event(
                event_type=event_type,
                level=level,
                data=data or {},
                description=description,
                request_context=None
            ))
        else:
            # Running loop exists, create task
            loop.create_task(logger.emit_event(
                event_type=event_type,
                level=level,
                data=data or {},
                description=description,
                request_context=None
            ))
    except Exception:
        # Silently fail if observability unavailable
        pass


# Backward compatibility alias
def observe(
    event_type: Union[SystemEvents, ConversationEvents, str],
    level: EventLevel = EventLevel.INFO,
    data: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> None:
    """
    Backward compatibility alias for emit_event.

    Args:
        event_type: The event type enum or string
        level: Event level (defaults to INFO)
        data: Additional event data
        description: Human-readable description
    """
    emit_event(event_type=event_type, level=level, data=data, description=description)
