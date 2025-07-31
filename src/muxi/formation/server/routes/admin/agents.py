"""
Agent management endpoints.

These endpoints provide agent CRUD operations,
requiring admin API key authentication.
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...responses import (
    APIResponse,
    agent_list_response_spec,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

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
    agents = formation.config.get("agents", [])

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

    # Find agent
    agents = formation.config.get("agents", [])
    agent = next((a for a in agents if a.get("id") == agent_id), None)

    if not agent:
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
