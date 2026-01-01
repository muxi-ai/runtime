"""
Standardized response format utilities for the Formation API.

This module provides utilities to create consistent API responses
following the envelope format defined in the API specification.

Response Function Naming Convention:
- Regular functions (e.g., agent_list_response): Use specific APIObjectType values
  (e.g., AGENT_LIST, JOB_LIST) for backward compatibility
- Spec-compliant functions (e.g., agent_list_response_spec): Use generic APIObjectType.LIST
  to comply with OpenAPI specifications

Note: The spec-compliant versions (_spec suffix) are now DEPRECATED. Instead, use the
regular functions with use_generic_type=True parameter for OpenAPI compliance.
"""

import copy
import time
from typing import Any, Dict, List, Optional, Union

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
    data: Optional[Dict[str, Any]] = Field(
        None, description="Additional error data (validation errors, stack traces, etc.)"
    )


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
    data: Optional[Dict[str, Any]] = None,
    error_data: Optional[Dict[str, Any]] = None,
) -> APIResponse:
    """
    Create a standardized error response.

    Args:
        error_code: Error code from error registry
        message: Custom error message (uses default if not provided)
        trace: Stack trace for debugging (will be included in error.data if provided)
        request_id: Request ID
        idempotency_key: Idempotency key if provided
        data: Additional data to include in the response data field
        error_data: Additional data to include in the error.data field

    Returns:
        APIResponse object with error
    """
    # Get error info from registry
    error_info = get_error_info(error_code)

    # Determine event type based on error code
    event_type = APIEventType.ERROR_INTERNAL
    if error_code in ["INVALID_REQUEST", "INVALID_PARAMS", "PARSE_ERROR", "UNPROCESSABLE_ENTITY"]:
        event_type = APIEventType.ERROR_VALIDATION
    elif error_code in ["UNAUTHORIZED", "BAD_CREDENTIALS"]:
        event_type = APIEventType.ERROR_AUTHENTICATION
    elif error_code == "FORBIDDEN":
        event_type = APIEventType.ERROR_AUTHORIZATION
    elif error_code in ["AGENT_NOT_FOUND", "RESOURCE_NOT_FOUND", "METHOD_NOT_FOUND"]:
        event_type = APIEventType.ERROR_NOT_FOUND
    elif error_code in ["PROCESSING_ERROR", "LLM_ERROR", "TOOL_EXECUTION_ERROR"]:
        event_type = APIEventType.ERROR_PROCESSING

    # Build error data, including trace if provided
    # Use deepcopy to prevent mutations of nested structures in the original
    final_error_data = copy.deepcopy(error_data) if error_data else {}
    if trace:
        final_error_data["trace"] = trace

    # Create error object
    error = APIError(
        code=error_code,
        message=message or (error_info.message if error_info else "An error occurred"),
        data=final_error_data if final_error_data else None,
    )

    return create_api_response(
        object_type=APIObjectType.ERROR,
        event_type=event_type,
        data=data or {},
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
    agents: List[Dict[str, Any]], request_id: Optional[str] = None, use_generic_type: bool = False
) -> APIResponse:
    """
    Create a response for a list of agents.

    Args:
        agents: List of agent configurations
        request_id: Optional request ID for tracking
        use_generic_type: If True, uses APIObjectType.LIST for OpenAPI spec compliance.
                         If False (default), uses APIObjectType.AGENT_LIST for legacy compatibility.

    Note:
        - use_generic_type=False: Uses specific type (APIObjectType.AGENT_LIST) - legacy behavior
        - use_generic_type=True: Uses generic type (APIObjectType.LIST) - OpenAPI spec compliant

    TODO: Consider deprecating the specific type in favor of the generic LIST type
          to maintain consistency with OpenAPI specifications.
    """
    object_type = APIObjectType.LIST if use_generic_type else APIObjectType.AGENT_LIST
    return create_success_response(
        object_type,
        APIEventType.AGENT_LIST,
        {"agents": agents, "count": len(agents)},
        request_id,
    )


def agent_list_response_spec(
    agents: List[Dict[str, Any]], request_id: Optional[str] = None
) -> APIResponse:
    """
    Create a spec-compliant response for a list of agents.

    DEPRECATED: Use agent_list_response(agents, request_id, use_generic_type=True) instead.

    This function exists for backward compatibility but should be replaced with
    the parameterized version to reduce code duplication.
    """
    return agent_list_response(agents, request_id, use_generic_type=True)


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


def job_list_response(
    jobs: List[Dict[str, Any]], request_id: Optional[str] = None, use_generic_type: bool = False
) -> APIResponse:
    """
    Create a response for a list of jobs.

    Args:
        jobs: List of job objects
        request_id: Optional request ID for tracking
        use_generic_type: If True, uses APIObjectType.LIST for OpenAPI spec compliance.
                         If False (default), uses APIObjectType.JOB_LIST for legacy compatibility.

    Note:
        - use_generic_type=False: Uses specific type (APIObjectType.JOB_LIST) - legacy behavior
        - use_generic_type=True: Uses generic type (APIObjectType.LIST) - OpenAPI spec compliant

    TODO: Consider deprecating the specific type in favor of the generic LIST type
          to maintain consistency with OpenAPI specifications.
    """
    object_type = APIObjectType.LIST if use_generic_type else APIObjectType.JOB_LIST
    return create_success_response(
        object_type,
        APIEventType.JOB_LIST,
        {"jobs": jobs, "count": len(jobs)},
        request_id,
    )


def job_list_response_spec(
    jobs: List[Dict[str, Any]], request_id: Optional[str] = None
) -> APIResponse:
    """
    Create a spec-compliant response for a list of jobs.

    DEPRECATED: Use job_list_response(jobs, request_id, use_generic_type=True) instead.

    This function exists for backward compatibility but should be replaced with
    the parameterized version to reduce code duplication.
    """
    return job_list_response(jobs, request_id, use_generic_type=True)
