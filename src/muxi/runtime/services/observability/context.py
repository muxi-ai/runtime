"""
MUXI Observability Context Management

This module contains context variable infrastructure for request tracking
and context propagation throughout the observability system.
"""

from contextvars import ContextVar
from typing import Optional, TYPE_CHECKING

from ...datatypes.observability import RequestContext

# Avoid circular imports
if TYPE_CHECKING:
    from .logger import EventLogger


# ===================================================================
# CONTEXT VARIABLE INFRASTRUCTURE
# ===================================================================

# Global context variable to track current request context
_current_request_context: ContextVar[Optional[RequestContext]] = ContextVar(
    "request_context", default=None
)

# Global context variable to track configured event logger
_current_event_logger: ContextVar[Optional["EventLogger"]] = ContextVar(
    "event_logger", default=None
)


def get_current_request_context() -> Optional[RequestContext]:
    """Get the current request context from context variable."""
    return _current_request_context.get()


def set_request_context(context: RequestContext) -> None:
    """Set the current request context (internal use only)."""
    _current_request_context.set(context)


def get_current_event_logger() -> Optional["EventLogger"]:
    """Get the current event logger from context variable."""
    return _current_event_logger.get()


def set_event_logger(logger: "EventLogger") -> None:
    """Set the current event logger (internal use only)."""
    _current_event_logger.set(logger)
