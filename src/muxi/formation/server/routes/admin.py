"""
Admin management endpoints.

These endpoints provide formation management capabilities,
requiring admin API key authentication.
"""

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


# Pydantic models for request/response
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


class SecretCreate(BaseModel):
    """Model for creating a secret."""
    value: str


class SecretUpdate(BaseModel):
    """Model for updating a secret."""
    value: str


@router.get("/test-auth")
async def test_auth(request: Request) -> Dict[str, str]:
    """
    Simple test endpoint for auth validation.

    Returns:
        Simple success message
    """
    return {"status": "success", "message": "Admin auth validated!", "endpoint": "admin"}


@router.get("/agents")
async def list_agents(request: Request) -> List[Dict[str, Any]]:
    """
    List all agents in the formation.

    Returns:
        List of agent configurations
    """
    formation = request.app.state.formation

    # Get agents from formation config
    agents = formation.config.get("agents", [])

    # Add source information
    for agent in agents:
        if "source" not in agent:
            agent["source"] = "yaml"

    return agents


@router.post("/agents")
async def add_agent(request: Request, agent: AgentCreate) -> Dict[str, Any]:
    """
    Add a new agent to the formation.

    Args:
        agent: Agent configuration

    Returns:
        Created agent configuration
    """
    formation = request.app.state.formation

    # Create agent config
    agent_config = {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "model": agent.model,
        "active": agent.active,
    }

    # Add to formation config using thread-safe method
    try:
        formation.add_agent_to_config(agent_config)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # TODO: Notify overlord of agent addition

    # TODO: Add observability event for agent added

    return agent_config


@router.patch("/agents/{agent_id}")
async def update_agent(
    request: Request,
    agent_id: str,
    updates: AgentUpdate
) -> Dict[str, Any]:
    """
    Update an existing agent.

    Args:
        agent_id: ID of agent to update
        updates: Fields to update

    Returns:
        Updated agent configuration
    """
    formation = request.app.state.formation

    # Apply updates using thread-safe method
    update_data = updates.model_dump(exclude_unset=True)
    try:
        agent = formation.update_agent_in_config(agent_id, update_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # TODO: Notify overlord of agent update

    # TODO: Add observability event for agent updated

    return agent


@router.delete("/agents/{agent_id}")
async def remove_agent(request: Request, agent_id: str) -> Dict[str, str]:
    """
    Remove an agent from the formation.

    Only agents created via API (source="api") can be removed.

    Args:
        agent_id: ID of agent to remove

    Returns:
        Success message
    """
    formation = request.app.state.formation

    # Remove agent using thread-safe method
    try:
        formation.remove_agent_from_config(agent_id)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=403, detail=str(e))

    # TODO: Notify overlord of agent removal

    # TODO: Add observability event for agent removed

    return {"message": f"Agent '{agent_id}' removed successfully"}


@router.get("/secrets")
async def list_secrets(request: Request) -> Dict[str, Any]:
    """
    List all secret keys (with masked values).

    Returns:
        Dictionary of secret keys with masked values
    """
    formation = request.app.state.formation

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        return {}

    # Get all secret keys
    secrets = formation.secrets_manager.list_secrets()

    # Mask values with consistent pattern (no length disclosure)
    masked_secrets = {
        key: "••••••••"
        for key, value in secrets.items()
    }

    return masked_secrets


@router.post("/secrets/{key}")
async def create_secret(
    request: Request,
    key: str,
    secret: SecretCreate
) -> Dict[str, str]:
    """
    Create a new secret.

    Args:
        key: Secret key
        secret: Secret value

    Returns:
        Success message
    """
    formation = request.app.state.formation

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        raise HTTPException(
            status_code=503,
            detail="Secrets manager not available"
        )

    # Check if secret already exists
    if formation.secrets_manager.has_secret(key):
        raise HTTPException(
            status_code=409,
            detail=f"Secret '{key}' already exists"
        )

    # Create secret
    formation.secrets_manager.set_secret(key, secret.value)

    # TODO: Add observability event for secret created

    return {"message": f"Secret '{key}' created successfully"}


@router.put("/secrets/{key}")
async def update_secret(
    request: Request,
    key: str,
    secret: SecretUpdate
) -> Dict[str, str]:
    """
    Update an existing secret.

    Args:
        key: Secret key
        secret: New secret value

    Returns:
        Success message
    """
    formation = request.app.state.formation

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        raise HTTPException(
            status_code=503,
            detail="Secrets manager not available"
        )

    # Check if secret exists
    if not formation.secrets_manager.has_secret(key):
        raise HTTPException(
            status_code=404,
            detail=f"Secret '{key}' not found"
        )

    # Update secret
    formation.secrets_manager.set_secret(key, secret.value)

    # TODO: Add observability event for secret updated

    return {"message": f"Secret '{key}' updated successfully"}


@router.delete("/secrets/{key}")
async def delete_secret(request: Request, key: str) -> Dict[str, str]:
    """
    Delete a secret.

    Args:
        key: Secret key to delete

    Returns:
        Success message
    """
    formation = request.app.state.formation

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        raise HTTPException(
            status_code=503,
            detail="Secrets manager not available"
        )

    # Check if secret exists
    if not formation.secrets_manager.has_secret(key):
        raise HTTPException(
            status_code=404,
            detail=f"Secret '{key}' not found"
        )

    # Delete secret
    formation.secrets_manager.delete_secret(key)

    # TODO: Add observability event for secret deleted

    return {"message": f"Secret '{key}' deleted successfully"}
