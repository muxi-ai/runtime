"""
Request cancellation support for cooperative cancellation.

This module provides infrastructure for gracefully stopping request
processing when a user cancels a request via DELETE /requests/{id}.
"""

from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .request_tracker import RequestTracker


class RequestCancelledException(Exception):
    """
    Raised when processing detects a cancelled request.
    
    This exception should be caught at the top level of request
    processing to cleanly stop work and log the cancellation.
    """
    
    def __init__(self, request_id: str):
        self.request_id = request_id
        super().__init__(f"Request {request_id} cancelled by user")


def cancellable(request_tracker: "RequestTracker"):
    """
    Factory that creates a cancellable decorator using the given tracker.
    
    The decorator checks if the current request has been cancelled
    before executing the wrapped function. If cancelled, it raises
    RequestCancelledException.
    
    Usage:
        # Create decorator bound to a tracker
        check_cancelled = cancellable(overlord.request_tracker)
        
        @check_cancelled
        async def some_long_running_function(...):
            ...
    
    Args:
        request_tracker: The RequestTracker instance to check for cancellation
        
    Returns:
        A decorator function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            from ...services.observability.context import get_current_request_context
            
            ctx = get_current_request_context()
            if ctx and request_tracker.is_cancelled(ctx.id):
                await request_tracker.clear_cancelled(ctx.id)
                raise RequestCancelledException(ctx.id)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def check_cancellation(request_tracker: "RequestTracker", request_id: str) -> None:
    """
    Inline cancellation check for use without decorator.
    
    Use this when you need a cancellation checkpoint but can't use
    the decorator (e.g., in the middle of a function).
    
    Usage:
        async def some_method(self, request_id, ...):
            # ... do some work ...
            await check_cancellation(self.request_tracker, request_id)
            # ... do more work ...
    
    Args:
        request_tracker: The RequestTracker instance
        request_id: The request ID to check
        
    Raises:
        RequestCancelledException: If the request is cancelled
    """
    if request_tracker.is_cancelled(request_id):
        await request_tracker.clear_cancelled(request_id)
        raise RequestCancelledException(request_id)


async def check_cancellation_from_context(request_tracker: "RequestTracker") -> None:
    """
    Check cancellation using request_id from current context.
    
    This is useful when you don't have direct access to request_id
    but the request context has been set via set_request_context().
    
    Usage:
        async def some_method(self, ...):
            # ... do some long operation ...
            await check_cancellation_from_context(overlord.request_tracker)
            # ... continue if not cancelled ...
    
    Args:
        request_tracker: The RequestTracker instance
        
    Raises:
        RequestCancelledException: If the request is cancelled
    """
    from ...services.observability.context import get_current_request_context
    
    ctx = get_current_request_context()
    if ctx and ctx.id and request_tracker.is_cancelled(ctx.id):
        await request_tracker.clear_cancelled(ctx.id)
        raise RequestCancelledException(ctx.id)
