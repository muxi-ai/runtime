"""
Standardized response format utilities for the Formation API.

This module provides utilities to create consistent API responses
following the envelope format defined in the API specification.
"""

import time
from typing import Any, Dict, Optional, List, Union

from pydantic import BaseModel, Field

from ...datatypes.api import APIEventType, APIObjectType
from ...datatypes.errors import get_error_info
from ...utils.id_generator import generate_request_id


class APIRequest(BaseModel):
    """Request information in API responses."""

    id: str = Field(..., description="Request ID")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key if provided")


class APIError(BaseModel):
    """Error details in API responses."""

    code: str = Field(..., description="Error code from error registry")
    message: str = Field(..., description="Human-readable error message")
    trace: Optional[str] = Field(None, description="Stack trace for debugging")


class APIResponse(BaseModel):
    """Base API response envelope."""

    object: str = Field(..., description="Response object type")
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    type: str = Field(..., description="Event type for observability")
    request: APIRequest = Field(..., description="Request information")
    success: bool = Field(..., description="Success indicator")
    error: Optional[APIError] = Field(None, description="Error details if failed")
    data: Dict[str, Any] = Field(..., description="Response data")


def create_api_response(
    object_type: Union[APIObjectType, str],
    event_type: Union[APIEventType, str],
    data: Dict[str, Any],
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    success: bool = True,
    error: Optional[APIError] = None,
) -> APIResponse:
    """
    Create a standardized API response.

    Args:
        object_type: Type of object being returned
        event_type: Event type for observability
        data: Response data
        request_id: Request ID (generated if not provided)
        idempotency_key: Idempotency key if provided
        success: Whether the request succeeded
        error: Error details if failed

    Returns:
        APIResponse object
    """
    # Generate request ID if not provided
    if not request_id:
        request_id = generate_request_id()

    # Ensure data is empty dict on error
    if not success and error:
        data = {}

    return APIResponse(
        object=object_type.value if isinstance(object_type, APIObjectType) else object_type,
        timestamp=int(time.time() * 1000),
        type=event_type.value if isinstance(event_type, APIEventType) else event_type,
        request=APIRequest(id=request_id, idempotency_key=idempotency_key),
        success=success,
        error=error,
        data=data,
    )


def create_error_response(
    error_code: str,
    message: Optional[str] = None,
    trace: Optional[str] = None,
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> APIResponse:
    """
    Create a standardized error response.

    Args:
        error_code: Error code from error registry
        message: Custom error message (uses default if not provided)
        trace: Stack trace for debugging
        request_id: Request ID
        idempotency_key: Idempotency key if provided

    Returns:
        APIResponse object with error
    """
    # Get error info from registry
    error_info = get_error_info(error_code)

    # Determine event type based on error code
    event_type = APIEventType.ERROR_INTERNAL
    if error_code in ["INVALID_REQUEST", "INVALID_PARAMS", "PARSE_ERROR"]:
        event_type = APIEventType.ERROR_VALIDATION
    elif error_code in ["UNAUTHORIZED", "BAD_CREDENTIALS"]:
        event_type = APIEventType.ERROR_AUTHENTICATION
    elif error_code == "FORBIDDEN":
        event_type = APIEventType.ERROR_AUTHORIZATION
    elif error_code in ["AGENT_NOT_FOUND", "RESOURCE_NOT_FOUND", "METHOD_NOT_FOUND"]:
        event_type = APIEventType.ERROR_NOT_FOUND
    elif error_code in ["PROCESSING_ERROR", "LLM_ERROR", "TOOL_EXECUTION_ERROR"]:
        event_type = APIEventType.ERROR_PROCESSING

    # Create error object
    error = APIError(
        code=error_code,
        message=message or (error_info.message if error_info else "An error occurred"),
        trace=trace,
    )

    return create_api_response(
        object_type=APIObjectType.ERROR,
        event_type=event_type,
        data={},
        request_id=request_id,
        idempotency_key=idempotency_key,
        success=False,
        error=error,
    )


def create_success_response(
    object_type: Union[APIObjectType, str],
    event_type: Union[APIEventType, str],
    data: Dict[str, Any],
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> APIResponse:
    """
    Create a successful API response.

    Convenience function that ensures success=True and no error.

    Args:
        object_type: Type of object being returned
        event_type: Event type for observability
        data: Response data
        request_id: Request ID
        idempotency_key: Idempotency key if provided

    Returns:
        Successful APIResponse object
    """
    return create_api_response(
        object_type=object_type,
        event_type=event_type,
        data=data,
        request_id=request_id,
        idempotency_key=idempotency_key,
        success=True,
        error=None,
    )


# Convenience functions for common responses
def agent_response(agent: Dict[str, Any], request_id: Optional[str] = None) -> APIResponse:
    """Create a response for a single agent."""
    return create_success_response(
        APIObjectType.AGENT,
        APIEventType.AGENT_RETRIEVED,
        agent,
        request_id,
    )


def agent_list_response(
    agents: List[Dict[str, Any]], request_id: Optional[str] = None
) -> APIResponse:
    """Create a response for a list of agents."""
    return create_success_response(
        APIObjectType.AGENT_LIST,
        APIEventType.AGENT_LIST,
        {"agents": agents, "count": len(agents)},
        request_id,
    )


def agent_list_response_spec(
    agents: List[Dict[str, Any]], request_id: Optional[str] = None
) -> APIResponse:
    """Create a spec-compliant response for a list of agents."""
    return create_success_response(
        APIObjectType.LIST,
        APIEventType.AGENT_LIST,
        {"agents": agents, "count": len(agents)},
        request_id,
    )


def secret_list_response(secrets: Dict[str, Any], request_id: Optional[str] = None) -> APIResponse:
    """Create a response for a list of secrets."""
    return create_success_response(
        APIObjectType.SECRET_LIST,
        APIEventType.SECRET_LIST,
        secrets,
        request_id,
    )


def memory_list_response(
    memories: List[Dict[str, Any]], request_id: Optional[str] = None
) -> APIResponse:
    """Create a response for a list of memories."""
    return create_success_response(
        APIObjectType.MEMORY_LIST,
        APIEventType.MEMORY_LIST,
        {"memories": memories, "count": len(memories)},
        request_id,
    )


def job_list_response(jobs: List[Dict[str, Any]], request_id: Optional[str] = None) -> APIResponse:
    """Create a response for a list of jobs."""
    return create_success_response(
        APIObjectType.JOB_LIST,
        APIEventType.JOB_LIST,
        {"jobs": jobs, "count": len(jobs)},
        request_id,
    )


def job_list_response_spec(
    jobs: List[Dict[str, Any]], request_id: Optional[str] = None
) -> APIResponse:
    """Create a spec-compliant response for a list of jobs."""
    return create_success_response(
        APIObjectType.LIST,
        APIEventType.JOB_LIST,
        jobs,
        request_id,
    )
