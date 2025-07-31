"""
Configuration and status endpoints.

These endpoints provide formation configuration and status,
requiring admin API key authentication.
"""

from copy import deepcopy
from typing import Any, Dict
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Configuration"])


def _mask_secrets_in_config(config: Dict[str, Any]) -> None:
    """
    Mask hardcoded secrets in formation config while preserving template references.

    This is a simplified implementation focused on known secret locations.
    TODO: Implement more comprehensive secret detection and masking system.

    Args:
        config: Formation configuration dictionary (modified in place)
    """
    # Mask LLM API keys
    if "llm" in config and "api_keys" in config["llm"]:
        for key, value in config["llm"]["api_keys"].items():
            if isinstance(value, str) and not value.startswith("${{ secrets."):
                config["llm"]["api_keys"][key] = "••••••••"

    # Add more secret masking patterns here as needed
    # Examples for future expansion:
    # - Database connection strings with passwords
    # - Webhook secrets
    # - Third-party service tokens


@router.get("/config", response_model=APIResponse)
async def get_formation_config(request: Request) -> JSONResponse:
    """
    Get complete formation configuration.

    Returns:
        Full formation YAML as JSON with defaults filled and secrets masked
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get full config with defaults
    config = deepcopy(formation.config)

    # Mask hardcoded secrets but preserve references
    _mask_secrets_in_config(config)

    response = create_success_response(
        APIObjectType.FORMATION_CONFIG, APIEventType.CONFIG_RETRIEVED, config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/formation", response_model=APIResponse)
async def get_formation_config_detailed(request: Request) -> JSONResponse:
    """
    Get complete formation configuration.

    Returns:
        Full formation YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get full config with defaults
    config = deepcopy(formation.config)

    # Mask hardcoded secrets but preserve references
    _mask_secrets_in_config(config)

    response = create_success_response(
        APIObjectType.FORMATION_CONFIG, APIEventType.CONFIG_RETRIEVED, config, request_id
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
        APIObjectType.FORMATION_STATUS, APIEventType.STATUS_RETRIEVED, status, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
