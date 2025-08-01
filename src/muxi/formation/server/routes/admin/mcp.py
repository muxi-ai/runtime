"""
MCP configuration and tool management endpoints.

These endpoints provide MCP configuration, server listing, and tool discovery,
requiring admin API key authentication.
"""

from typing import Dict, Any, Optional, List
import uuid
from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType
from ...secrets import restore_secret_placeholders
from ...utils import get_header_case_insensitive
from .....services.secrets.config_utils import get_config_item_with_secrets_restored

router = APIRouter(tags=["MCP"])


class MCPToolCall(BaseModel):
    """Model for MCP tool calls."""

    tool: str
    arguments: Dict[str, Any]


class MCPDefaultsUpdate(BaseModel):
    """Model for updating MCP defaults."""

    timeout: int = 30000
    max_retries: int = 3
    environment: Dict[str, str] = {}


class MCPServerCreate(BaseModel):
    """Model for creating an MCP server."""

    name: str
    command: str
    args: List[str] = []
    env: Dict[str, str] = {}
    enabled: bool = True


class MCPServerUpdate(BaseModel):
    """Model for updating an MCP server."""

    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None


# Tool definitions with access levels
MCP_TOOLS = {
    # Admin tools
    "formation_list_agents": {
        "description": "List all agents in the formation",
        "access": "admin",
        "handler": "list_agents",
    },
    "formation_update_agent": {
        "description": "Update agent configuration",
        "access": "admin",
        "handler": "update_agent",
    },
    "formation_manage_secrets": {
        "description": "Manage formation secrets",
        "access": "admin",
        "handler": "manage_secrets",
    },
    # Client tools
    "chat": {
        "description": "Send a message to the formation",
        "access": "client",
        "handler": "chat",
    },
    "get_memories": {
        "description": "Retrieve user memories",
        "access": "client",
        "handler": "get_memories",
    },
    "create_memory": {
        "description": "Create a user memory",
        "access": "client",
        "handler": "create_memory",
    },
}


@router.get("/mcp", response_model=APIResponse)
async def get_mcp_config(request: Request) -> JSONResponse:
    """
    Get complete MCP configuration.

    Returns:
        Full MCP YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    mcp_config = formation.config.get("mcp", {})

    response = create_success_response(
        APIObjectType.MCP, APIEventType.MCP_RETRIEVED, mcp_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.patch("/mcp", response_model=APIResponse)
async def update_mcp_defaults(request: Request, defaults: MCPDefaultsUpdate) -> JSONResponse:
    """
    Update MCP default settings.

    Args:
        defaults: New MCP default settings

    Returns:
        Updated MCP configuration
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement MCP defaults update logic

    mcp_defaults = {
        "timeout": defaults.timeout,
        "max_retries": defaults.max_retries,
        "environment": defaults.environment,
    }

    response = create_success_response(
        APIObjectType.MCP, APIEventType.MCP_UPDATED, {"defaults": mcp_defaults}, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/mcp/servers", response_model=APIResponse)
async def list_mcp_servers(request: Request) -> JSONResponse:
    """
    List all MCP servers.

    Returns:
        List of MCP server configurations
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    servers = deepcopy(formation.config.get("mcp", {}).get("servers", []))

    # Create a temporary config structure to apply placeholders
    temp_config = {"mcp": {"servers": servers}}
    temp_config = restore_secret_placeholders(temp_config, formation.secret_placeholders)
    servers = temp_config.get("mcp", {}).get("servers", [])

    response = create_success_response(
        APIObjectType.LIST,
        APIEventType.MCP_SERVER_LIST,
        servers,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/mcp/servers", response_model=APIResponse)
async def create_mcp_server(request: Request, server: MCPServerCreate) -> JSONResponse:
    """
    Create a new MCP server configuration.

    Args:
        server: MCP server configuration

    Returns:
        Created MCP server configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get existing servers to check for duplicates
    existing_servers = formation.config.get("mcp", {}).get("servers", [])

    # Check if a server with the same name already exists
    if any(s.get("name") == server.name for s in existing_servers):
        response = create_error_response(
            "DUPLICATE_RESOURCE",
            f"MCP server with name '{server.name}' already exists",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=409)

    # Generate unique ID using UUID
    server_id = f"mcp-server-{uuid.uuid4().hex[:8]}"

    # Ensure the generated ID is unique (very unlikely to collide with 8 hex chars)
    while any(s.get("id") == server_id for s in existing_servers):
        server_id = f"mcp-server-{uuid.uuid4().hex[:8]}"

    server_config = {
        "id": server_id,
        "name": server.name,
        "command": server.command,
        "args": server.args,
        "env": server.env,
        "enabled": server.enabled,
    }

    # TODO: Add server to formation configuration
    # For now, this just returns the created config without persisting

    response = create_success_response(
        APIObjectType.MCP_SERVER, APIEventType.MCP_SERVER_CREATED, server_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=201)


@router.get("/mcp/servers/{server_id}", response_model=APIResponse)
async def get_mcp_server(request: Request, server_id: str) -> JSONResponse:
    """
    Get a specific MCP server configuration.

    Args:
        server_id: ID of the MCP server

    Returns:
        MCP server configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get server with secrets restored
    server, _ = get_config_item_with_secrets_restored(formation, ["mcp", "servers"], server_id)

    if server is None:
        response = create_error_response(
            "MCP_SERVER_NOT_FOUND", f"MCP server '{server_id}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.MCP_SERVER, APIEventType.MCP_SERVER_RETRIEVED, server, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.patch("/mcp/servers/{server_id}", response_model=APIResponse)
async def update_mcp_server(
    request: Request, server_id: str, update: MCPServerUpdate
) -> JSONResponse:
    """
    Update an MCP server configuration.

    Args:
        server_id: ID of the MCP server
        update: Fields to update

    Returns:
        Updated MCP server configuration
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement MCP server update logic
    # Find server and apply updates

    update_data = update.model_dump(exclude_unset=True)

    # Mock response for now
    server_config = {"id": server_id, **update_data}

    response = create_success_response(
        APIObjectType.MCP_SERVER, APIEventType.MCP_SERVER_UPDATED, server_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/mcp/servers/{server_id}", response_model=APIResponse)
async def delete_mcp_server(request: Request, server_id: str) -> JSONResponse:
    """
    Delete an MCP server configuration.

    Args:
        server_id: ID of the MCP server to delete

    Returns:
        Success response
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement MCP server deletion logic
    # Find and remove server from configuration

    response = create_success_response(
        APIObjectType.MCP_SERVER,
        APIEventType.MCP_SERVER_DELETED,
        {"message": f"MCP server '{server_id}' deleted successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/mcp/tools", response_model=APIResponse)
async def list_mcp_tools(request: Request) -> JSONResponse:
    """
    List all available MCP tools.

    Note: This endpoint is admin-only. The returned tools include both
    admin and client tools since admin has access to all.

    Returns:
        List of available tool definitions
    """
    request_id = getattr(request.state, "request_id", None)

    # Since this is under admin auth, show all tools
    available_tools = []
    for tool_name, tool_def in MCP_TOOLS.items():
        available_tools.append(
            {
                "name": tool_name,
                "description": tool_def["description"],
                "access": tool_def["access"],
                "parameters": _get_tool_parameters(tool_name),
            }
        )

    response = create_success_response(
        APIObjectType.LIST,
        APIEventType.MCP_TOOL_LIST,
        available_tools,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/mcp/tools/call", response_model=APIResponse)
async def call_mcp_tool(request: Request, tool_call: MCPToolCall) -> JSONResponse:
    """
    Execute an MCP tool.

    Routes to appropriate handler based on tool name.
    This endpoint is admin-only so admin can execute any tool.

    Args:
        tool_call: Tool name and arguments

    Returns:
        Tool execution result
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate tool exists
    if tool_call.tool not in MCP_TOOLS:
        response = create_error_response(
            "TOOL_NOT_FOUND", f"Unknown tool: {tool_call.tool}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    tool_def = MCP_TOOLS[tool_call.tool]

    # Get user_id from case-insensitive header if provided
    x_user_id = get_header_case_insensitive(request.headers, "X-User-Id")

    # Add user_id to arguments if provided and tool is client-level
    if tool_def["access"] == "client" and x_user_id:
        tool_call.arguments["user_id"] = x_user_id

    # Execute tool
    try:
        handler = _get_tool_handler(tool_def["handler"])
        result = await handler(formation, **tool_call.arguments)

        # TODO: Add observability event for MCP tool called

        response = create_success_response(
            APIObjectType.MCP_TOOL_RESULT,
            APIEventType.MCP_TOOL_EXECUTED,
            {"tool": tool_call.tool, "result": result},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except ValueError as e:
        # Handle expected validation errors with specific messages
        # TODO: Add observability event for MCP tool validation error
        response = create_error_response("INVALID_PARAMS", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=400)

    except AttributeError:
        # Handle missing attributes/methods (e.g., formation components not available)
        # TODO: Add observability event for MCP tool configuration error
        response = create_error_response(
            "TOOL_EXECUTION_ERROR",
            "Tool configuration error: required component not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    except KeyError as e:
        # Handle missing required arguments
        # TODO: Add observability event for MCP tool argument error
        response = create_error_response(
            "INVALID_PARAMS", f"Missing required argument: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    except Exception:
        # Handle unexpected errors without exposing internal details
        # TODO: Add observability event for MCP tool unexpected error with full details
        # Log the actual error internally but return generic message to client
        response = create_error_response(
            "TOOL_EXECUTION_ERROR",
            "An unexpected error occurred during tool execution",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


def _get_tool_parameters(tool_name: str) -> Dict[str, Any]:
    """Get parameter schema for a tool."""
    # Define parameter schemas for each tool
    schemas = {
        "formation_list_agents": {},
        "formation_update_agent": {
            "agent_id": {"type": "string", "required": True},
            "updates": {"type": "object", "required": True},
        },
        "formation_manage_secrets": {
            "action": {"type": "string", "enum": ["create", "update", "delete"], "required": True},
            "key": {"type": "string", "required": True},
            "value": {"type": "string", "required": False},
        },
        "chat": {
            "message": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": False},
            "files": {"type": "array", "required": False},
        },
        "get_memories": {
            "user_id": {"type": "string", "required": True},
            "limit": {"type": "integer", "required": False, "default": 10},
        },
        "create_memory": {
            "user_id": {"type": "string", "required": True},
            "content": {"type": "string", "required": True},
            "metadata": {"type": "object", "required": False},
        },
    }

    return schemas.get(tool_name, {})


async def _get_tool_handler(handler_name: str):
    """Get the handler function for a tool."""
    # Import handlers dynamically to avoid circular imports
    handlers = {
        "list_agents": _handle_list_agents,
        "update_agent": _handle_update_agent,
        "manage_secrets": _handle_manage_secrets,
        "chat": _handle_chat,
        "get_memories": _handle_get_memories,
        "create_memory": _handle_create_memory,
    }

    return handlers.get(handler_name)


# Tool handler implementations
async def _handle_list_agents(formation, **kwargs):
    """List agents handler."""
    return formation.config.get("agents", [])


async def _handle_update_agent(formation, agent_id: str, updates: Dict[str, Any], **kwargs):
    """Update agent handler."""
    # Use formation's thread-safe update method to persist changes
    try:
        updated_agent = formation.update_agent_in_config(agent_id, updates)
        return updated_agent
    except ValueError as e:
        # Re-raise with consistent error message
        raise ValueError(f"Agent '{agent_id}' not found") from e


async def _handle_manage_secrets(formation, action: str, key: str, value: str = None, **kwargs):
    """Manage secrets handler."""
    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        raise ValueError("Secrets manager not available")

    if action == "create":
        if not value:
            raise ValueError("Value required for create action")
        formation.secrets_manager.set_secret(key, value)
        return {"message": f"Secret '{key}' created"}

    elif action == "update":
        if not value:
            raise ValueError("Value required for update action")
        if not formation.secrets_manager.has_secret(key):
            raise ValueError(f"Secret '{key}' not found")
        formation.secrets_manager.set_secret(key, value)
        return {"message": f"Secret '{key}' updated"}

    elif action == "delete":
        if not formation.secrets_manager.has_secret(key):
            raise ValueError(f"Secret '{key}' not found")
        formation.secrets_manager.delete_secret(key)
        return {"message": f"Secret '{key}' deleted"}

    else:
        raise ValueError(f"Invalid action: {action}")


async def _handle_chat(
    formation, message: str, user_id: str = "anonymous", files: list = None, **kwargs
):
    """Chat handler."""
    if not hasattr(formation, "_overlord") or not formation._overlord:
        raise ValueError("Overlord not available")

    # Use overlord's chat method
    response = await formation._overlord.chat(message, user_id=user_id, files=files)

    return {"response": response.content}


async def _handle_get_memories(formation, user_id: str, limit: int = 10, **kwargs):
    """Get memories handler."""
    # TODO: Implement memory retrieval
    return []


async def _handle_create_memory(
    formation, user_id: str, content: str, metadata: dict = None, **kwargs
):
    """Create memory handler."""
    # TODO: Implement memory creation
    return {"id": "memory_123", "content": content, "metadata": metadata}
