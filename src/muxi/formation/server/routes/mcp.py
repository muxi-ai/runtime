"""
MCP (Model Context Protocol) endpoint.

This endpoint provides a unified interface for tool-based access,
with intelligent routing based on API key permissions.
"""

from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

router = APIRouter()


class MCPToolCall(BaseModel):
    """Model for MCP tool calls."""
    tool: str
    arguments: Dict[str, Any]


class MCPResponse(BaseModel):
    """Model for MCP responses."""
    result: Any
    error: Optional[str] = None


# Tool definitions with access levels
MCP_TOOLS = {
    # Admin tools
    "formation_list_agents": {
        "description": "List all agents in the formation",
        "access": "admin",
        "handler": "list_agents"
    },
    "formation_update_agent": {
        "description": "Update agent configuration",
        "access": "admin",
        "handler": "update_agent"
    },
    "formation_manage_secrets": {
        "description": "Manage formation secrets",
        "access": "admin",
        "handler": "manage_secrets"
    },

    # Client tools
    "chat": {
        "description": "Send a message to the formation",
        "access": "client",
        "handler": "chat"
    },
    "get_memories": {
        "description": "Retrieve user memories",
        "access": "client",
        "handler": "get_memories"
    },
    "create_memory": {
        "description": "Create a user memory",
        "access": "client",
        "handler": "create_memory"
    }
}


@router.post("/tools/list")
async def list_tools(
    request: Request,
    x_admin_key: Optional[str] = Header(None),
    x_client_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    List available MCP tools based on authentication.

    Returns different tools based on whether admin or client key is provided.

    Returns:
        List of available tool definitions
    """
    formation = request.app.state.formation

    # Determine access level
    has_admin = x_admin_key == formation._api_keys.get("admin")
    has_client = x_client_key == formation._api_keys.get("client")

    if not has_admin and not has_client:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    # Filter tools based on access
    available_tools = {}
    for tool_name, tool_def in MCP_TOOLS.items():
        if tool_def["access"] == "admin" and has_admin:
            available_tools[tool_name] = {
                "description": tool_def["description"],
                "parameters": _get_tool_parameters(tool_name)
            }
        elif tool_def["access"] == "client" and (has_admin or has_client):
            available_tools[tool_name] = {
                "description": tool_def["description"],
                "parameters": _get_tool_parameters(tool_name)
            }

    return {"tools": available_tools}


@router.post("/tools/call")
async def call_tool(
    request: Request,
    tool_call: MCPToolCall,
    x_admin_key: Optional[str] = Header(None),
    x_client_key: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None)
) -> MCPResponse:
    """
    Execute an MCP tool.

    Routes to appropriate handler based on tool name and permissions.

    Args:
        tool_call: Tool name and arguments
        x_admin_key: Optional admin API key
        x_client_key: Optional client API key
        x_user_id: Optional user ID

    Returns:
        Tool execution result
    """
    formation = request.app.state.formation

    # Validate tool exists
    if tool_call.tool not in MCP_TOOLS:
        return MCPResponse(
            error=f"Unknown tool: {tool_call.tool}"
        )

    tool_def = MCP_TOOLS[tool_call.tool]

    # Check permissions
    has_admin = x_admin_key == formation._api_keys.get("admin")
    has_client = x_client_key == formation._api_keys.get("client")

    if tool_def["access"] == "admin" and not has_admin:
        return MCPResponse(
            error="Admin authentication required for this tool"
        )
    elif tool_def["access"] == "client" and not (has_admin or has_client):
        return MCPResponse(
            error="Client authentication required for this tool"
        )

    # Add user_id to arguments if provided and tool is client-level
    if tool_def["access"] == "client" and x_user_id:
        tool_call.arguments["user_id"] = x_user_id

    # Execute tool
    try:
        handler = _get_tool_handler(tool_def["handler"])
        result = await handler(formation, **tool_call.arguments)

        # TODO: Add observability event for MCP tool called

        return MCPResponse(result=result)

    except Exception as e:
        # TODO: Add observability event for MCP tool error

        return MCPResponse(
            error=f"Tool execution failed: {str(e)}"
        )


def _get_tool_parameters(tool_name: str) -> Dict[str, Any]:
    """Get parameter schema for a tool."""
    # Define parameter schemas for each tool
    schemas = {
        "formation_list_agents": {},
        "formation_update_agent": {
            "agent_id": {"type": "string", "required": True},
            "updates": {"type": "object", "required": True}
        },
        "formation_manage_secrets": {
            "action": {"type": "string", "enum": ["create", "update", "delete"], "required": True},
            "key": {"type": "string", "required": True},
            "value": {"type": "string", "required": False}
        },
        "chat": {
            "message": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": False},
            "files": {"type": "array", "required": False}
        },
        "get_memories": {
            "user_id": {"type": "string", "required": True},
            "limit": {"type": "integer", "required": False, "default": 10}
        },
        "create_memory": {
            "user_id": {"type": "string", "required": True},
            "content": {"type": "string", "required": True},
            "metadata": {"type": "object", "required": False}
        }
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
    agents = formation.config.get("agents", [])
    agent = next((a for a in agents if a.get("id") == agent_id), None)

    if not agent:
        raise ValueError(f"Agent '{agent_id}' not found")

    agent.update(updates)
    return agent


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


async def _handle_chat(formation, message: str, user_id: str = "anonymous", files: list = None, **kwargs):
    """Chat handler."""
    if not hasattr(formation, "_overlord") or not formation._overlord:
        raise ValueError("Overlord not available")

    # Use overlord's chat method
    response = await formation._overlord.chat(
        message,
        user_id=user_id,
        files=files
    )

    return {"response": response.content}


async def _handle_get_memories(formation, user_id: str, limit: int = 10, **kwargs):
    """Get memories handler."""
    # TODO: Implement memory retrieval
    return []


async def _handle_create_memory(formation, user_id: str, content: str, metadata: dict = None, **kwargs):
    """Create memory handler."""
    # TODO: Implement memory creation
    return {"id": "memory_123", "content": content, "metadata": metadata}
