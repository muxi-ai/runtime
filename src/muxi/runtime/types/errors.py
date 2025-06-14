"""
Centralized error code registry for MUXI runtime.

This module provides a comprehensive error code system with standardized
messages, HTTP status mappings, and categorization for consistent error
handling across all MUXI communication modes.
"""

from typing import Dict, Optional
from dataclasses import dataclass

# Observability integration
from .. import observability


@dataclass
class ErrorCodeInfo:
    """Information about a specific error code."""

    code: str
    message: str
    http_status: int
    category: str
    description: str


# Centralized error code registry
ERROR_CODE_REGISTRY: Dict[str, ErrorCodeInfo] = {
    # System Errors
    "INTERNAL_ERROR": ErrorCodeInfo(
        code="INTERNAL_ERROR",
        message="An internal system error occurred",
        http_status=500,
        category="system",
        description="Unexpected runtime errors",
    ),
    "SYSTEM_OVERLOAD": ErrorCodeInfo(
        code="SYSTEM_OVERLOAD",
        message="System is currently at capacity",
        http_status=503,
        category="system",
        description="Rate limiting, resource exhaustion",
    ),
    "TIMEOUT": ErrorCodeInfo(
        code="TIMEOUT",
        message="Operation timed out",
        http_status=408,
        category="system",
        description="Request/processing timeout",
    ),
    "CANCELLED": ErrorCodeInfo(
        code="CANCELLED",
        message="Operation was cancelled",
        http_status=499,
        category="system",
        description="User/system cancellation",
    ),
    # Authentication & Authorization
    "UNAUTHORIZED": ErrorCodeInfo(
        code="UNAUTHORIZED",
        message="Authentication required",
        http_status=401,
        category="auth",
        description="Missing/invalid credentials",
    ),
    "FORBIDDEN": ErrorCodeInfo(
        code="FORBIDDEN",
        message="Access denied",
        http_status=403,
        category="auth",
        description="Insufficient permissions",
    ),
    "BAD_CREDENTIALS": ErrorCodeInfo(
        code="BAD_CREDENTIALS",
        message="Invalid credentials provided",
        http_status=401,
        category="auth",
        description="Wrong API key/token",
    ),
    # Request Validation
    "INVALID_REQUEST": ErrorCodeInfo(
        code="INVALID_REQUEST",
        message="Request is malformed or invalid",
        http_status=400,
        category="validation",
        description="JSON/schema validation",
    ),
    "INVALID_PARAMS": ErrorCodeInfo(
        code="INVALID_PARAMS",
        message="Invalid parameters provided",
        http_status=400,
        category="validation",
        description="Parameter validation",
    ),
    "PARSE_ERROR": ErrorCodeInfo(
        code="PARSE_ERROR",
        message="Failed to parse request",
        http_status=400,
        category="validation",
        description="Malformed JSON",
    ),
    "METHOD_NOT_FOUND": ErrorCodeInfo(
        code="METHOD_NOT_FOUND",
        message="Unknown method or endpoint",
        http_status=404,
        category="validation",
        description="Invalid API method",
    ),
    # Resource Errors
    "AGENT_NOT_FOUND": ErrorCodeInfo(
        code="AGENT_NOT_FOUND",
        message="Specified agent does not exist",
        http_status=404,
        category="resource",
        description="Invalid agent name",
    ),
    "FORMATION_NOT_FOUND": ErrorCodeInfo(
        code="FORMATION_NOT_FOUND",
        message="Specified formation does not exist",
        http_status=404,
        category="resource",
        description="Invalid formation ID",
    ),
    "TOOL_NOT_FOUND": ErrorCodeInfo(
        code="TOOL_NOT_FOUND",
        message="Requested tool is not available",
        http_status=404,
        category="resource",
        description="MCP tool not available",
    ),
    "RESOURCE_NOT_FOUND": ErrorCodeInfo(
        code="RESOURCE_NOT_FOUND",
        message="Requested resource not found",
        http_status=404,
        category="resource",
        description="Any missing resource",
    ),
    # Processing Errors
    "PROCESSING_ERROR": ErrorCodeInfo(
        code="PROCESSING_ERROR",
        message="Failed to process request",
        http_status=500,
        category="processing",
        description="LLM/agent processing",
    ),
    "TOOL_EXECUTION_ERROR": ErrorCodeInfo(
        code="TOOL_EXECUTION_ERROR",
        message="Tool execution failed",
        http_status=500,
        category="processing",
        description="MCP tool failure",
    ),
    "LLM_ERROR": ErrorCodeInfo(
        code="LLM_ERROR",
        message="LLM provider error",
        http_status=502,
        category="processing",
        description="OpenAI/provider issues",
    ),
    "CLARIFICATION_FAILED": ErrorCodeInfo(
        code="CLARIFICATION_FAILED",
        message="Clarification process failed",
        http_status=422,
        category="processing",
        description="Clarification timeout/error",
    ),
    # Rate Limiting
    "RATE_LIMITED": ErrorCodeInfo(
        code="RATE_LIMITED",
        message="Rate limit exceeded",
        http_status=429,
        category="rate_limit",
        description="API rate limiting",
    ),
    "LLM_RATE_LIMITED": ErrorCodeInfo(
        code="LLM_RATE_LIMITED",
        message="LLM provider rate limit exceeded",
        http_status=429,
        category="rate_limit",
        description="Provider rate limits",
    ),
    # Network & Connectivity
    "CONNECTION_ERROR": ErrorCodeInfo(
        code="CONNECTION_ERROR",
        message="Connection failed",
        http_status=502,
        category="network",
        description="Network connection failures",
    ),
    "NETWORK_ERROR": ErrorCodeInfo(
        code="NETWORK_ERROR",
        message="Network connectivity issue",
        http_status=502,
        category="network",
        description="Connection failures",
    ),
    "BAD_GATEWAY": ErrorCodeInfo(
        code="BAD_GATEWAY",
        message="Upstream service error",
        http_status=502,
        category="network",
        description="External service issues",
    ),
    "WEBHOOK_DELIVERY_FAILED": ErrorCodeInfo(
        code="WEBHOOK_DELIVERY_FAILED",
        message="Failed to deliver webhook",
        http_status=500,  # Internal error for webhook failures
        category="network",
        description="Async webhook errors",
    ),
    # MCP-Specific Errors
    "MCP_CONNECTION_ERROR": ErrorCodeInfo(
        code="MCP_CONNECTION_ERROR",
        message="Failed to connect to MCP server",
        http_status=502,
        category="mcp",
        description="MCP transport issues",
    ),
    "MCP_PROTOCOL_ERROR": ErrorCodeInfo(
        code="MCP_PROTOCOL_ERROR",
        message="MCP protocol violation",
        http_status=400,
        category="mcp",
        description="Invalid MCP messages",
    ),
    "MCP_TOOL_TIMEOUT": ErrorCodeInfo(
        code="MCP_TOOL_TIMEOUT",
        message="MCP tool execution timed out",
        http_status=408,
        category="mcp",
        description="Tool timeout",
    ),
}


def get_error_info(code: str) -> Optional[ErrorCodeInfo]:
    """Get error information for a given error code."""
    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting error info lookup",
        data={"operation": "get_error_info", "error_code": code, "utility": "error_registry"},
    )

    error_info = ERROR_CODE_REGISTRY.get(code)

    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_COMPLETED,
        level=observability.EventLevel.DEBUG,
        description="Error info lookup completed",
        data={
            "operation": "get_error_info",
            "error_code": code,
            "found": error_info is not None,
            "category": error_info.category if error_info else None,
            "http_status": error_info.http_status if error_info else None,
            "utility": "error_registry",
        },
    )

    return error_info


def get_error_message(code: str, default: str = "An error occurred") -> str:
    """Get the standard message for an error code."""
    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting error message lookup",
        data={
            "operation": "get_error_message",
            "error_code": code,
            "default_message": default,
            "utility": "error_registry",
        },
    )

    error_info = get_error_info(code)
    message = error_info.message if error_info else default

    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_COMPLETED,
        level=observability.EventLevel.DEBUG,
        description="Error message lookup completed",
        data={
            "operation": "get_error_message",
            "error_code": code,
            "message": message,
            "used_default": error_info is None,
            "utility": "error_registry",
        },
    )

    return message


def get_http_status(code: str, default: int = 500) -> int:
    """Get the HTTP status code for an error code."""
    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting HTTP status lookup",
        data={
            "operation": "get_http_status",
            "error_code": code,
            "default_status": default,
            "utility": "error_registry",
        },
    )

    error_info = get_error_info(code)
    status = error_info.http_status if error_info else default

    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_COMPLETED,
        level=observability.EventLevel.DEBUG,
        description="HTTP status lookup completed",
        data={
            "operation": "get_http_status",
            "error_code": code,
            "http_status": status,
            "used_default": error_info is None,
            "utility": "error_registry",
        },
    )

    return status


def create_error_details(
    code: str, custom_message: Optional[str] = None, trace: Optional[str] = None
) -> Dict[str, str]:
    """Create standardized error details."""
    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting error details creation",
        data={
            "operation": "create_error_details",
            "error_code": code,
            "has_custom_message": custom_message is not None,
            "has_trace": trace is not None,
            "utility": "error_registry",
        },
    )

    error_info = get_error_info(code)

    if not error_info:
        details = {
            "code": code,
            "message": custom_message or "Unknown error occurred",
            "trace": trace,
        }
    else:
        details = {"code": code, "message": custom_message or error_info.message, "trace": trace}

    observability.emit_event(
        event_type=observability.SystemEventType.UTILITY_COMPLETED,
        level=observability.EventLevel.DEBUG,
        description="Error details creation completed",
        data={
            "operation": "create_error_details",
            "error_code": code,
            "found_error_info": error_info is not None,
            "final_message": details["message"],
            "has_trace": details.get("trace") is not None,
            "utility": "error_registry",
        },
    )

    return details
