"""
Agent management endpoints.

These endpoints provide agent CRUD operations,
requiring admin API key authentication.
"""

from typing import Optional, List, Dict, Any
from copy import deepcopy
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...responses import (
    APIResponse,
    agent_list_response,
    create_success_response,
    create_error_response,
)
from ...secrets import restore_secret_placeholders
from ...utils import validate_secret_references
from .....datatypes.api import APIEventType, APIObjectType
from .....services.secrets.config_utils import get_agent_with_secrets_restored
from .....services import observability

# Get logger for this module
logger = logging.getLogger(__name__)


router = APIRouter(tags=["Agents"])


# Constants
API_SOURCE = "api"
AGENT_NOT_FOUND_ERROR = "AGENT_NOT_FOUND"
INVALID_REQUEST_ERROR = "INVALID_REQUEST"
INTERNAL_ERROR = "INTERNAL_ERROR"
FORBIDDEN_ERROR = "FORBIDDEN"
AGENT_EXISTS_ERROR = "AGENT_EXISTS"


def _restore_agents_with_secrets(formation: Any) -> List[Dict[str, Any]]:
    """
    Helper function to get agents with secret placeholders restored.

    Args:
        formation: The formation instance

    Returns:
        List of agent configurations with secrets restored
    """
    agents = deepcopy(formation.config.get("agents", []))
    temp_config = {"agents": agents}
    temp_config = restore_secret_placeholders(temp_config, formation.secret_placeholders)
    return temp_config.get("agents", [])


async def _validate_agent_secrets(
    agent_data: Dict[str, Any], formation: Any, request_id: Optional[str]
) -> Optional[JSONResponse]:
    """
    Helper function to validate secret references in agent data.

    Args:
        agent_data: Agent configuration data to validate
        formation: The formation instance
        request_id: Request ID for error responses

    Returns:
        JSONResponse with error if validation fails, None if valid
    """
    is_valid, validation_errors = await validate_secret_references(agent_data, formation)

    if not is_valid:
        response = create_error_response(
            INVALID_REQUEST_ERROR,
            "Invalid secret references in agent configuration",
            None,
            request_id,
            error_data={"validation_errors": validation_errors},
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    return None


def _build_agent_config(agent: "AgentCreate") -> Dict[str, Any]:
    """
    Helper function to build agent configuration from AgentCreate model.

    Args:
        agent: AgentCreate model instance

    Returns:
        Complete agent configuration dictionary
    """
    agent_config = {
        "schema": agent.schema,
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "active": agent.active,
        "source": API_SOURCE,  # Mark as created via API
    }

    # Add optional fields if provided
    optional_fields = [
        "author",
        "url",
        "license",
        "version",
        "system_message",
        "llm_models",
        "mcp_servers",
        "knowledge",
        "a2a",
    ]

    for field in optional_fields:
        value = getattr(agent, field, None)
        if value is not None:
            agent_config[field] = value

    return agent_config


def _find_agent_by_id(agents: List[Dict[str, Any]], agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Helper function to find an agent by ID in a list of agents.

    Args:
        agents: List of agent configurations
        agent_id: ID of agent to find

    Returns:
        Agent configuration if found, None otherwise
    """
    return next((a for a in agents if a.get("id") == agent_id), None)


def _can_delete_agent(agent: Dict[str, Any]) -> bool:
    """
    Helper function to check if an agent can be deleted.
    Only agents created via API (source="api") can be removed.

    Args:
        agent: Agent configuration

    Returns:
        True if agent can be deleted, False otherwise
    """
    return agent.get("source") == API_SOURCE


async def _cleanup_agent_from_overlord(formation: Any, agent_id: str) -> None:
    """
    Helper function to remove agent from overlord if running.

    Args:
        formation: The formation instance
        agent_id: ID of agent to remove
    """
    # Use public method to remove agent from overlord
    await formation.remove_agent_from_overlord(agent_id)


def _cleanup_secret_placeholders(formation: Any, agent_index: int) -> None:
    """
    Helper function to clean up secret placeholders for an agent.

    Args:
        formation: The formation instance
        agent_index: Index of agent in agents list
    """
    if agent_index >= 0 and formation.has_secret_placeholders():
        # Remove all placeholders for this agent using public method
        prefix = f"agents[{agent_index}]"
        formation.remove_secret_placeholders_for_prefix(prefix)


def _delete_agent_file_safe(formation: Any, agent_id: str) -> None:
    """
    Helper function to safely delete agent YAML file.

    Args:
        formation: The formation instance
        agent_id: ID of agent to delete file for
    """
    formation_path = formation.get_formation_path()
    if formation_path:
        from ....utils.agent_persistence import delete_agent_file

        try:
            deleted = delete_agent_file(agent_id, formation_path)
            if not deleted:
                # File didn't exist, but that's okay - agent was still removed from config
                pass
        except Exception as e:
            # Log the error but don't fail the deletion
            # The agent is already removed from config/overlord
            logger.warning(f"Failed to delete agent file for '{agent_id}': {str(e)}")
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                description=f"Failed to delete agent file for '{agent_id}', but agent was removed from config",
                data={
                    "operation": "delete_agent_file",
                    "agent_id": agent_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )


class AgentCreate(BaseModel):
    """Model for creating a new agent."""

    schema_version: str = Field(..., description="Agent schema version", alias="schema")
    id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    description: str = Field(..., description="Agent purpose and capabilities")
    active: bool = Field(default=True, description="Agent activation state")
    author: Optional[str] = Field(default=None, description="Author information")
    url: Optional[str] = Field(default=None, description="Documentation URL")
    license: Optional[str] = Field(default="Unlicense", description="License type")
    version: Optional[str] = Field(default=None, description="Agent version")
    system_message: Optional[str] = Field(default=None, description="Agent behavior instructions")
    llm_models: Optional[List[Dict[str, Any]]] = Field(default=None, description="Model overrides")
    mcp_servers: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="MCP server access"
    )
    knowledge: Optional[List[Dict[str, Any]]] = Field(default=None, description="Knowledge sources")
    a2a: Optional[Dict[str, Any]] = Field(default=None, description="A2A settings")


class AgentUpdate(BaseModel):
    """Model for updating an agent."""

    name: Optional[str] = Field(default=None, description="Human-readable agent name")
    description: Optional[str] = Field(default=None, description="Agent purpose and capabilities")
    active: Optional[bool] = Field(default=None, description="Agent activation state")
    author: Optional[str] = Field(default=None, description="Author information")
    url: Optional[str] = Field(default=None, description="Documentation URL")
    license: Optional[str] = Field(default=None, description="License type")
    version: Optional[str] = Field(default=None, description="Agent version")
    system_message: Optional[str] = Field(default=None, description="Agent behavior instructions")
    llm_models: Optional[List[Dict[str, Any]]] = Field(default=None, description="Model overrides")
    mcp_servers: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="MCP server access"
    )
    knowledge: Optional[List[Dict[str, Any]]] = Field(default=None, description="Knowledge sources")
    a2a: Optional[Dict[str, Any]] = Field(default=None, description="A2A settings")


@router.get("/agents", response_model=APIResponse)
async def list_agents(request: Request) -> JSONResponse:
    """
    List all agents in the formation.

    Returns:
        Structured response with list of agent configurations
    """
    formation = request.app.state.formation
    request_id: Optional[str] = getattr(request.state, "request_id", None)

    # Get agents with secret placeholders restored
    agents = _restore_agents_with_secrets(formation)

    # Create structured response using spec-compliant format (agent_list object type)
    response = agent_list_response(agents, request_id, use_generic_type=False)
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.post("/agents", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def create_agent(request: Request, agent: AgentCreate) -> JSONResponse:
    """
    Create a new agent in the formation.

    Args:
        agent: Agent configuration

    Returns:
        Created agent configuration
    """
    formation = request.app.state.formation
    request_id: Optional[str] = getattr(request.state, "request_id", None)

    # Build the complete agent configuration
    agent_config = _build_agent_config(agent)

    # Validate all secret references in the final agent configuration
    validation_error = await _validate_agent_secrets(agent_config, formation, request_id)
    if validation_error:
        return validation_error

    # Save agent to file and auto-load into formation and overlord
    try:
        await formation.save_agent_to_file(agent_config, auto_load=True)
    except ValueError as e:
        error_msg = str(e)
        if "already exists" in error_msg:
            response = create_error_response(AGENT_EXISTS_ERROR, error_msg, None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=409)
        else:
            response = create_error_response(INVALID_REQUEST_ERROR, error_msg, None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=400)
    except Exception as e:
        response = create_error_response(
            INTERNAL_ERROR, f"Failed to create agent: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    # Log agent addition
    observability.observe(
        event_type=observability.SystemEvents.AGENT_ADDED,
        level=observability.EventLevel.INFO,
        data={
            "agent_id": agent_config["id"],
            "agent_name": agent_config["name"],
            "source": "api",
        },
        description=f"Agent '{agent_config['id']}' (name: {agent_config['name']}) added via API",
    )

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
    request_id: Optional[str] = getattr(request.state, "request_id", None)

    # Get agent with secrets restored
    agent = get_agent_with_secrets_restored(formation, agent_id)

    if agent is None:
        response = create_error_response(
            AGENT_NOT_FOUND_ERROR, f"Agent '{agent_id}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.AGENT, APIEventType.AGENT_RETRIEVED, agent, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.patch("/agents/{agent_id}", response_model=APIResponse)  # DEPRECATED: Use deployment instead
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
    request_id: Optional[str] = getattr(request.state, "request_id", None)

    # Get the update data, excluding unset fields
    update_data = updates.model_dump(exclude_unset=True)

    # If there are any secret references in the update, validate them
    if update_data:
        validation_error = await _validate_agent_secrets(update_data, formation, request_id)
        if validation_error:
            return validation_error

    # Update agent file and auto-reload into formation and overlord
    try:
        await formation.update_agent_file(agent_id, update_data, auto_reload=True)

        # Get updated agent using same logic as LIST endpoint
        agents = _restore_agents_with_secrets(formation)
        agent = _find_agent_by_id(agents, agent_id)

        if not agent:
            raise ValueError(f"Agent '{agent_id}' not found after update")
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg or "does not exist" in error_msg:
            response = create_error_response(AGENT_NOT_FOUND_ERROR, error_msg, None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=404)
        else:
            response = create_error_response(INVALID_REQUEST_ERROR, error_msg, None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=400)
    except Exception as e:
        response = create_error_response(
            INTERNAL_ERROR, f"Failed to update agent: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    # Log agent update
    observability.observe(
        event_type=observability.SystemEvents.AGENT_UPDATED,
        level=observability.EventLevel.INFO,
        data={
            "agent_id": agent_id,
            "updated_fields": list(update_data.keys()),
            "source": "api",
        },
        description=f"Agent '{agent_id}' updated via API (fields: {', '.join(list(update_data.keys()))})",
    )

    response = create_success_response(
        APIObjectType.AGENT, APIEventType.AGENT_UPDATED, agent, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.delete("/agents/{agent_id}", response_model=APIResponse)  # DEPRECATED: Use deployment instead
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
    request_id: Optional[str] = getattr(request.state, "request_id", None)

    # Check if agent exists and can be deleted
    agents = formation.config.get("agents", [])
    agent = _find_agent_by_id(agents, agent_id)

    if not agent:
        response = create_error_response(
            AGENT_NOT_FOUND_ERROR, f"Agent '{agent_id}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Check if agent can be deleted (source="api")
    if not _can_delete_agent(agent):
        response = create_error_response(
            FORBIDDEN_ERROR,
            f"Agent '{agent_id}' was not created via API and cannot be removed",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=403)

    try:
        # Get agent index before removal (for secret placeholder cleanup)
        agent_index = next((i for i, a in enumerate(agents) if a.get("id") == agent_id), -1)

        # Remove from formation config
        logger.info(f"Removing agent '{agent_id}' from config...")
        formation.remove_agent_from_config(agent_id)

        # Remove from overlord if running
        logger.info(f"Removing agent '{agent_id}' from overlord...")
        await _cleanup_agent_from_overlord(formation, agent_id)

        # Clean up secret placeholders
        logger.info(f"Cleaning up secret placeholders for agent '{agent_id}'...")
        _cleanup_secret_placeholders(formation, agent_index)

        # Delete the YAML file
        logger.info(f"Deleting agent file for '{agent_id}'...")
        _delete_agent_file_safe(formation, agent_id)

        # Log agent removal
        observability.observe(
            event_type=observability.SystemEvents.AGENT_REMOVED,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": agent_id,
                "source": "api",
            },
            description=f"Agent '{agent_id}' removed via API",
        )

    except ValueError as e:
        # This shouldn't happen since we already checked, but handle it
        error_msg = str(e)
        if "not found" in error_msg:
            response = create_error_response(AGENT_NOT_FOUND_ERROR, error_msg, None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=404)
        else:
            response = create_error_response(FORBIDDEN_ERROR, error_msg, None, request_id)
            return JSONResponse(content=response.model_dump(), status_code=403)
    except Exception as e:
        logger.error("Failed to delete agent '%s': %s", agent_id, e, exc_info=True)
        response = create_error_response(
            INTERNAL_ERROR, f"Failed to delete agent: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    response = create_success_response(
        APIObjectType.AGENT,
        APIEventType.AGENT_DELETED,
        {"id": agent_id, "deleted": True},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
