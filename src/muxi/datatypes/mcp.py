# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Message Models - JSON-RPC Message Definitions
# Description:  Message models for the Model Context Protocol (MCP)
# Role:         Provides Pydantic models for all MCP message types
# Usage:        Used for serializing and validating MCP messages
# Author:       Muxi Framework Team
#
# The MCP Message module provides Pydantic models that define the structure
# of messages used in the Model Context Protocol. These models ensure proper
# validation, serialization, and type safety for all MCP communications.
#
# Key components:
#
# 1. JSON-RPC Base Models
#    - Core models for JSON-RPC 2.0 messaging
#    - Request, response, and error structures
#    - Specification-compliant validation
#
# 2. MCP-Specific Message Types
#    - Tool call request and response models
#    - Function invocation structures
#    - Parameter validation
#
# 3. Type Definitions
#    - Common type structures used across messages
#    - Type-safe parameter modeling
#    - Rich data validation
#
# These models ensure that all messages created and processed within
# the MCP system adhere to the JSON-RPC 2.0 specification and the MCP
# extensions, providing type safety and validation.
# =============================================================================

from enum import Enum
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


class FunctionCallModel(BaseModel):
    """
    Model representing a function/tool call.

    This model defines the structure of a function or tool call within the MCP
    system, including the name of the function and its parameters. It's used
    to represent both agent-generated function calls and their results.
    """

    name: str = Field(..., description="Function/tool name")
    parameters: Dict[str, Any] = Field(..., description="Function/tool parameters")
    output: Optional[Any] = Field(None, description="Function/tool output (when available)")

    class Config:
        """Pydantic configuration for the model."""

        json_schema_extra = {
            "example": {
                "name": "get_weather",
                "parameters": {"location": "New York", "unit": "celsius", "include_forecast": True},
                "output": {"temperature": 22, "conditions": "Partly cloudy", "humidity": 65},
            }
        }


class ErrorCodes(int, Enum):
    """
    Standard JSON-RPC 2.0 error codes plus MCP-specific extension codes.

    This enum defines the error codes used in JSON-RPC 2.0 responses with errors.
    It includes both standard codes from the JSON-RPC specification and MCP-specific
    extension codes for more granular error reporting.
    """

    # Standard JSON-RPC 2.0 error codes
    PARSE_ERROR = -32700  # Invalid JSON was received
    INVALID_REQUEST = -32600  # The JSON sent is not a valid Request object
    METHOD_NOT_FOUND = -32601  # The method does not exist / is not available
    INVALID_PARAMS = -32602  # Invalid method parameter(s)
    INTERNAL_ERROR = -32603  # Internal JSON-RPC error

    # MCP extension error codes
    TOOL_NOT_FOUND = -32000  # The requested tool was not found
    TOOL_EXECUTION_ERROR = -32001  # Error during tool execution
    UNAUTHORIZED = -32002  # Client not authorized to use the tool
    RATE_LIMITED = -32003  # Request was rate limited
    BAD_CREDENTIALS = -32004  # Invalid or missing credentials
    TIMEOUT = -32005  # Operation timed out
    CANCELLED = -32006  # Operation was cancelled


class JSONRPCError(BaseModel):
    """
    Error object for JSON-RPC 2.0 responses.

    This model defines the structure of error objects in JSON-RPC 2.0
    responses, following the specification. It includes required code
    and message fields, plus an optional data field for additional
    error details.
    """

    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Optional[Any] = Field(None, description="Additional error data")


class JSONRPCBaseRequest(BaseModel):
    """
    Base class for all JSON-RPC 2.0 requests.

    This model defines the common structure for all JSON-RPC 2.0 requests,
    including the JSON-RPC version, method name, and request ID. It serves
    as the foundation for more specific request types.
    """

    jsonrpc: str = Field("2.0", description="JSON-RPC version (always '2.0')")
    method: str = Field(..., description="Method to be invoked")
    id: Union[str, int] = Field(..., description="Request identifier")


class JSONRPCRequest(JSONRPCBaseRequest):
    """
    Complete JSON-RPC 2.0 request with params.

    This model extends the base request model to include the params field,
    which contains the parameters for the requested method. The params field
    can be any valid JSON structure, typically an object or array.
    """

    params: Optional[Dict[str, Any]] = Field(None, description="Method parameters")


class JSONRPCBaseResponse(BaseModel):
    """
    Base class for all JSON-RPC 2.0 responses.

    This model defines the common structure for all JSON-RPC 2.0 responses,
    including the JSON-RPC version and the response ID (which must match
    the ID from the corresponding request).
    """

    jsonrpc: str = Field("2.0", description="JSON-RPC version (always '2.0')")
    id: Union[str, int, None] = Field(..., description="Request identifier")


class JSONRPCSuccessResponse(JSONRPCBaseResponse):
    """
    Successful JSON-RPC 2.0 response with result.

    This model represents successful JSON-RPC 2.0 responses, which include
    a result field containing the return value of the invoked method. The
    structure of the result field depends on the specific method called.
    """

    result: Any = Field(..., description="Method execution result")


class JSONRPCErrorResponse(JSONRPCBaseResponse):
    """
    Error JSON-RPC 2.0 response with error object.

    This model represents JSON-RPC 2.0 responses that indicate an error
    occurred during method invocation. It includes an error object that
    provides details about what went wrong.
    """

    error: JSONRPCError = Field(..., description="Error object")


JSONRPCResponse = Union[JSONRPCSuccessResponse, JSONRPCErrorResponse]


class MCPToolCall(FunctionCallModel):
    """
    Model representing a tool call in the MCP protocol.

    This is a specialized version of FunctionCallModel specifically for
    MCP tool calls. It provides the same structure with a more specific
    name that aligns with the MCP protocol terminology.
    """

    pass


class MCPToolCallRequest(JSONRPCRequest):
    """
    Model for an MCP tool call request.

    This model represents a JSON-RPC request specifically for invoking
    a tool in the MCP system. It ensures the request follows both the
    JSON-RPC 2.0 specification and the MCP extensions for tool calls.
    """

    # Method is the tool name in MCP
    params: Dict[str, Any] = Field(..., description="Tool parameters")


class MCPToolCallResponse(JSONRPCSuccessResponse):
    """
    Model for an MCP tool call response.

    This model represents a JSON-RPC response specifically for the result
    of a tool call in the MCP system. It ensures the response follows both
    the JSON-RPC 2.0 specification and the MCP extensions for tool calls.
    """

    result: Any = Field(..., description="Tool execution result")
