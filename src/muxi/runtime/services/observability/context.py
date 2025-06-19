"""
MUXI Observability Context Management

This module contains context variable infrastructure for request tracking
and context propagation throughout the observability system.
"""

from contextvars import ContextVar
from typing import Optional

from ...datatypes.observability import RequestContext


# ===================================================================
# CONTEXT VARIABLE INFRASTRUCTURE
# ===================================================================

# Global context variable to track current request context
_current_request_context: ContextVar[Optional[RequestContext]] = ContextVar(
    'request_context',
    default=None
)


def get_current_request_context() -> Optional[RequestContext]:
    """Get the current request context from context variable."""
    return _current_request_context.get()


def set_request_context(context: RequestContext) -> None:
    """Set the current request context (internal use only)."""
    _current_request_context.set(context)
