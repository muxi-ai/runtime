"""
Agent management endpoints.

These endpoints provide agent CRUD operations,
requiring admin API key authentication.
"""

from typing import Optional
from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...responses import (
    APIResponse,
    agent_list_response_spec,
    create_success_response,
    create_error_response,
)
from ...secrets import restore_secret_placeholders
from .....datatypes.api import APIEventType, APIObjectType


def get_config_item_with_secrets_restored(formation, config_path: list, item_id: str, id_field: str = "id"):
    """
    Get configuration item with secrets restored.

    Args:
        formation: Formation instance
        config_path: Path to the config array (e.g., ["agents"] or ["mcp", "servers"])
        item_id: ID of item to retrieve
        id_field: Field name containing the ID (default: "id")

    Returns:
        Tuple of (item_config_with_secrets_restored, item_index) or (None, None) if not found
    """
    # Navigate to the config array
    config_section = formation.config
    for path_part in config_path:
        config_section = config_section.get(path_part, {})

    # Handle case where config_section is a list (final path element)
    if isinstance(config_section, dict) and len(config_path) > 0:
        config_section = config_section.get(config_path[-1], [])

    # Ensure we have a list
    if not isinstance(config_section, list):
        return None, None

    # Find item
    item_index = next((i for i, item in enumerate(config_section) if item.get(id_field) == item_id), None)

    if item_index is None:
        return None, None

    # Get a deep copy of the item
    item = deepcopy(config_section[item_index])

    # Create a temporary config structure to apply placeholders
    # Build the nested structure based on config_path
    temp_config = {}
    current_level = temp_config
    for i, path_part in enumerate(config_path[:-1]):
        current_level[path_part] = {}
        current_level = current_level[path_part]

    # Set the final array with our item
    if config_path:
        current_level[config_path[-1]] = [item]
    else:
        temp_config = [item]

    # Restore secrets
    temp_config = restore_secret_placeholders(temp_config, formation._secret_placeholders)

    # Extract the restored item
    restored_item = temp_config
    for path_part in config_path:
        restored_item = restored_item.get(path_part, {})

    if isinstance(restored_item, list) and len(restored_item) > 0:
        restored_item = restored_item[0]

    return restored_item, item_index


def get_agent_with_secrets_restored(formation, agent_id: str):
    """
    Get agent configuration with secrets restored.

    Args:
        formation: Formation instance
        agent_id: ID of agent to retrieve

    Returns:
        Agent configuration with secrets restored, or None if not found
    """
    item, _ = get_config_item_with_secrets_restored(formation, ["agents"], agent_id)
    return item


router = APIRouter(tags=["Agents"])


class AgentCreate(BaseModel):
    """Model for creating a new agent."""

    id: str
    name: str
    description: str
    model: str
    active: bool = True


class AgentUpdate(BaseModel):
    """Model for updating an agent."""

    active: Optional[bool] = Field(default=None)
    description: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)


@router.get("/agents", response_model=APIResponse)
async def list_agents(request: Request) -> JSONResponse:
    """
    List all agents in the formation.

    Returns:
        Structured response with list of agent configurations
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get agents from formation config
    agents = deepcopy(formation.config.get("agents", []))

    # Create a temporary config structure to apply placeholders
    temp_config = {"agents": agents}
    temp_config = restore_secret_placeholders(temp_config, formation._secret_placeholders)
    agents = temp_config.get("agents", [])

    # Create structured response
    response = agent_list_response_spec(agents, request_id)
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/agents", response_model=APIResponse)
async def create_agent(request: Request, agent: AgentCreate) -> JSONResponse:
    """
    Create a new agent in the formation.

    Args:
        agent: Agent configuration

    Returns:
        Created agent configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Create agent config
    agent_config = {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "model": agent.model,
        "active": agent.active,
        "source": "api",
    }

    # Add to formation config using thread-safe method
    try:
        formation.add_agent_to_config(agent_config)
    except ValueError as e:
        response = create_error_response("AGENT_EXISTS", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=409)

    # TODO: Notify overlord of agent addition
    # TODO: Add observability event for agent added

    response = create_success_response(
        APIObjectType.AGENT, APIEventType.AGENT_CREATED, agent_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=201)


@router.get("/agents/{agent_id}", response_model=APIResponse)
async def get_agent(request: Request, agent_id: str) -> JSONResponse:
    """
    Get a specific agent configuration.

    Args:
        agent_id: ID of agent to retrieve

    Returns:
        Agent configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get agent with secrets restored
    agent = get_agent_with_secrets_restored(formation, agent_id)

    if agent is None:
        response = create_error_response(
            "AGENT_NOT_FOUND", f"Agent '{agent_id}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.AGENT, APIEventType.AGENT_RETRIEVED, agent, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.patch("/agents/{agent_id}", response_model=APIResponse)
async def update_agent(request: Request, agent_id: str, updates: AgentUpdate) -> JSONResponse:
    """
    Update an existing agent.

    Args:
        agent_id: ID of agent to update
        updates: Fields to update

    Returns:
        Updated agent configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Apply updates using thread-safe method
    update_data = updates.model_dump(exclude_unset=True)
    try:
        agent = formation.update_agent_in_config(agent_id, update_data)
    except ValueError as e:
        response = create_error_response("AGENT_NOT_FOUND", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=404)

    # TODO: Notify overlord of agent update
    # TODO: Add observability event for agent updated

    response = create_success_response(
        APIObjectType.AGENT, APIEventType.AGENT_UPDATED, agent, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/agents/{agent_id}", response_model=APIResponse)
async def delete_agent(request: Request, agent_id: str) -> JSONResponse:
    """
    Delete an agent from the formation.

    Only agents created via API (source="api") can be removed.

    Args:
        agent_id: ID of agent to remove

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Remove agent using thread-safe method
    try:
        formation.remove_agent_from_config(agent_id)
    except ValueError as e:
        if "not found" in str(e):
            response = create_error_response("AGENT_NOT_FOUND", str(e), None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=404)
        else:
            response = create_error_response("FORBIDDEN", str(e), None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=403)

    # TODO: Notify overlord of agent removal
    # TODO: Add observability event for agent removed

    response = create_success_response(
        APIObjectType.AGENT,
        APIEventType.AGENT_DELETED,
        {"message": f"Agent '{agent_id}' deleted successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
