"""
Configuration and status endpoints.

These endpoints provide formation configuration and status,
requiring admin API key authentication.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Configuration"])


@router.get("/config", response_model=APIResponse)
async def get_config_navigation(request: Request) -> JSONResponse:
    """
    Get formation configuration navigation structure.

    Returns:
        Navigation structure with resource counts and endpoints
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Build navigation structure
    navigation = {
        "agents": {"total": len(formation.config.get("agents", [])), "resource": "/v1/agents"},
        "secrets": {
            "total": (
                len(await formation.secrets_manager.list_secrets())
                if hasattr(formation, "secrets_manager") and formation.secrets_manager
                else 0
            ),
            "resource": "/v1/secrets",
        },
        "mcp": {
            "servers": {
                "total": len(formation.config.get("mcp", {}).get("servers", [])),
                "resource": "/v1/mcp/servers",
            },
            "tools": {"resource": "/v1/mcp/tools"},
        },
        "llm": {"resource": "/v1/llm"},
        "logging": {"resource": "/v1/logging"},
        "memory": {"resource": "/v1/memory"},
        "overlord": {"resource": "/v1/overlord"},
    }

    response = create_success_response(
        APIObjectType.CONFIG, APIEventType.CONFIG_RETRIEVED, navigation, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/formation", response_model=APIResponse)
async def get_formation_config(request: Request) -> JSONResponse:
    """
    Get complete formation configuration.

    Returns:
        Full formation YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get full config with defaults
    config = formation.config.copy()

    # Mask hardcoded secrets but preserve references
    # TODO: Implement secret masking logic

    response = create_success_response(
        APIObjectType.CONFIG, APIEventType.CONFIG_RETRIEVED, config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/status", response_model=APIResponse)
async def get_formation_status(request: Request) -> JSONResponse:
    """
    Get formation runtime status.

    Returns:
        Runtime statistics and health information
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    status = {
        "formation_id": formation.config.get("id", "unknown"),
        "name": formation.config.get("name", "unknown"),
        "version": formation.config.get("version", "unknown"),
        "status": "running",
        "uptime_seconds": 0,  # TODO: Track formation uptime
        "agents": {
            "total": len(formation.config.get("agents", [])),
            "active": sum(1 for a in formation.config.get("agents", []) if a.get("active", True)),
        },
        "memory": {
            "usage_mb": 0,  # TODO: Get actual memory usage
            "limit_mb": 0,  # TODO: Get memory limit
        },
        "requests": {
            "total": 0,  # TODO: Track request count
            "active": 0,  # TODO: Track active requests
        },
    }

    response = create_success_response(
        APIObjectType.STATUS, APIEventType.STATUS_RETRIEVED, status, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
