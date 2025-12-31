"""
Error classification utilities for MUXI runtime.

This module provides utilities to classify exceptions into standardized
error codes for consistent error handling across the system.
"""

import asyncio
from typing import Type, Dict

from ..datatypes.errors import ERROR_CODE_REGISTRY
from ..services import observability


# Exception type to error code mapping
EXCEPTION_TO_ERROR_CODE: Dict[Type[Exception], str] = {
    # Standard Python exceptions
    ValueError: "INVALID_PARAMS",
    TypeError: "INVALID_PARAMS",
    KeyError: "RESOURCE_NOT_FOUND",
    FileNotFoundError: "RESOURCE_NOT_FOUND",
    PermissionError: "FORBIDDEN",
    ConnectionError: "CONNECTION_ERROR",
    TimeoutError: "TIMEOUT",
    asyncio.TimeoutError: "TIMEOUT",
    # HTTP-related exceptions (if using requests/aiohttp)
    # ConnectionRefusedError: "CONNECTION_ERROR",
    # ConnectionResetError: "CONNECTION_ERROR",
    # Default fallback
    Exception: "INTERNAL_ERROR",
}


def classify_error_code(exception: Exception) -> str:
    """
    Classify an exception into a standardized error code.

    Args:
        exception: The exception to classify

    Returns:
        Error code string from the error registry
    """
    observability.observe(
        event_type=observability.ErrorEvents.WARNING,
        level=observability.EventLevel.WARNING,
        description=f"Error classified: {type(exception).__name__}",
        data={
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "source": "error_classifier",
            "operation": "classify_error_code",
        },
    )

    # Check for specific exception types first
    for exc_type, error_code in EXCEPTION_TO_ERROR_CODE.items():
        if isinstance(exception, exc_type) and exc_type is not Exception:
            return error_code

    # Check exception message for specific patterns
    error_msg = str(exception).lower()

    if "not found" in error_msg:
        if "agent" in error_msg:
            return "AGENT_NOT_FOUND"
        elif "formation" in error_msg:
            return "FORMATION_NOT_FOUND"
        elif "tool" in error_msg:
            return "TOOL_NOT_FOUND"
        else:
            return "RESOURCE_NOT_FOUND"

    if "timeout" in error_msg or "timed out" in error_msg:
        return "TIMEOUT"

    if "cancelled" in error_msg or "canceled" in error_msg:
        return "CANCELLED"

    if "unauthorized" in error_msg or "authentication" in error_msg:
        return "UNAUTHORIZED"

    if "forbidden" in error_msg or "permission" in error_msg:
        return "FORBIDDEN"

    if "rate limit" in error_msg or "too many requests" in error_msg:
        return "RATE_LIMITED"

    if "invalid" in error_msg or "malformed" in error_msg:
        return "INVALID_REQUEST"

    # Default fallback
    return "INTERNAL_ERROR"


def is_retryable_error(error_code: str) -> bool:
    """
    Determine if an error code represents a retryable error.

    Args:
        error_code: Error code to check

    Returns:
        True if the error is retryable, False otherwise
    """
    retryable_codes = {
        "TIMEOUT",
        "CONNECTION_ERROR",
        "NETWORK_ERROR",
        "SYSTEM_OVERLOAD",
        "RATE_LIMITED",
        "LLM_RATE_LIMITED",
    }

    return error_code in retryable_codes


def get_http_status_for_error(error_code: str) -> int:
    """
    Get the appropriate HTTP status code for an error code.

    Args:
        error_code: Error code from the registry

    Returns:
        HTTP status code
    """
    error_info = ERROR_CODE_REGISTRY.get(error_code)
    if error_info:
        return error_info.http_status

    # Default to 500 for unknown errors
    return 500
