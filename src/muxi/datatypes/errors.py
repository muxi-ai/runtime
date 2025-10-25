"""
Centralized error code registry for MUXI runtime.

This module provides a comprehensive error code system with standardized
messages, HTTP status mappings, and categorization for consistent error
handling across all MUXI communication modes.
"""

import os
import logging
from typing import Dict, Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

logger = logging.getLogger(__name__)


class ErrorCodeInfo(BaseModel):
    """Information about a specific error code."""

    code: str = Field(..., min_length=1, description="Error code identifier")
    message: str = Field(..., min_length=1, description="Default error message")
    http_status: int = Field(..., ge=100, le=599, description="HTTP status code")
    category: Literal[
        "system", "auth", "validation", "resource", "processing", "rate_limit", "network", "mcp"
    ] = Field(..., description="Error category")
    description: str = Field(..., description="Detailed error description")

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v):
        """Ensure error code is uppercase with underscores."""
        import re
        if not re.match(r'^[A-Z_]+$', v):
            raise ValueError("Error code must contain only uppercase letters and underscores")
        return v

    @field_validator("http_status")
    @classmethod
    def validate_http_status(cls, v):
        """Ensure HTTP status is valid."""
        valid_ranges = [
            (100, 199),  # Informational
            (200, 299),  # Success
            (300, 399),  # Redirection
            (400, 499),  # Client error
            (500, 599),  # Server error
        ]
        if not any(start <= v <= end for start, end in valid_ranges):
            raise ValueError("Invalid HTTP status code")
        return v

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,  # Make instances immutable
    )


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
    "UNPROCESSABLE_ENTITY": ErrorCodeInfo(
        code="UNPROCESSABLE_ENTITY",
        message="Request cannot be processed due to semantic errors",
        http_status=422,
        category="validation",
        description="Request is well-formed but semantically incorrect or violates business rules",
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
    "SOP_NOT_FOUND": ErrorCodeInfo(
        code="SOP_NOT_FOUND",
        message="Specified SOP does not exist",
        http_status=404,
        category="resource",
        description="Invalid SOP name",
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


class ErrorDetails(BaseModel):
    """Standardized error details structure."""

    code: str = Field(..., min_length=1, description="Error code")
    message: str = Field(..., min_length=1, description="Error message")
    trace: Optional[str] = Field(default=None, description="Stack trace or additional context")

    @field_validator("code")
    @classmethod
    def validate_code_exists(cls, v):
        """Ensure error code exists in registry."""
        if v not in ERROR_CODE_REGISTRY:
            # Check if we're in production environment
            env = os.getenv("MUXI_ENV", os.getenv("ENVIRONMENT", "development")).lower()
            if env in ["production", "prod"]:
                logger.warning(
                    f"Custom error code '{v}' used in production environment. "
                    f"This code is not in the standard ERROR_CODE_REGISTRY. "
                    f"Consider adding it to the registry for consistency."
                )
        return v

    model_config = ConfigDict(extra="forbid")


def get_error_info(code: str) -> Optional[ErrorCodeInfo]:
    """Get error information for a given error code."""
    error_info = ERROR_CODE_REGISTRY.get(code)
    return error_info


def get_error_message(code: str, default: str = "An error occurred") -> str:
    """Get the standard message for an error code."""
    error_info = get_error_info(code)
    message = error_info.message if error_info else default

    return message


def get_http_status(code: str, default: int = 500) -> int:
    """Get the HTTP status code for an error code."""
    error_info = get_error_info(code)
    status = error_info.http_status if error_info else default
    return status


def create_error_details(
    code: str, custom_message: Optional[str] = None, trace: Optional[str] = None
) -> ErrorDetails:
    """Create standardized error details."""
    error_info = get_error_info(code)

    if not error_info:
        details = ErrorDetails(
            code=code,
            message=custom_message or "Unknown error occurred",
            trace=trace,
        )
    else:
        details = ErrorDetails(
            code=code,
            message=custom_message or error_info.message,
            trace=trace,
        )

    return details
