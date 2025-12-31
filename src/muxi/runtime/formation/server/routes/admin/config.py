"""
Configuration and status endpoints.

These endpoints provide formation configuration and status,
requiring admin API key authentication.
"""

import time
from copy import deepcopy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import psutil

from ...responses import (
    APIResponse,
    create_success_response,
)
from ...secrets import restore_secret_placeholders
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Configuration"])


@router.get("/config", response_model=APIResponse)
async def get_formation_config(request: Request) -> JSONResponse:
    """
    Get formation configuration summary.

    Returns:
        Formation metadata with resource links instead of full configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Build configuration summary with resource links
    config_summary = {
        "formation_id": formation.config.get("id", "unknown"),
        "version": formation.config.get("version", "1.0.0"),
        "description": formation.config.get("description", ""),
        "schema_version": formation.config.get("schema", "1.0.0"),
        "agents": {
            "total": len(formation.config.get("agents", [])),
            "resource": "/v1/agents"
        },
        "secrets": {
            "total": formation.get_secrets_count(),
            "resource": "/v1/secrets"
        },
        "mcp": {
            "default_retry_attempts": formation.config.get("mcp", {}).get("default_retry_attempts", 3),
            "default_timeout_seconds": formation.config.get("mcp", {}).get("default_timeout_seconds", 30),
            "servers": {
                "total": len(formation.config.get("mcp", {}).get("servers", [])),
                "resource": "/v1/mcp/servers"
            }
        },
        "overlord": {
            "resource": "/v1/overlord"
        },
        "llm": {
            "resource": "/v1/llm/settings"
        },
        "memory": {
            "resource": "/v1/memory"
        },
        "async": {
            "resource": "/v1/async"
        },
        "scheduler": {
            "resource": "/v1/scheduler"
        },
        "a2a": {
            "resource": "/v1/a2a"
        },
        "logging": {
            "resource": "/v1/logging"
        }
    }

    response = create_success_response(
        APIObjectType.FORMATION_CONFIG, APIEventType.FORMATION_CONFIG_RETRIEVED, config_summary, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/formation", response_model=APIResponse)
async def get_formation_config_detailed(request: Request) -> JSONResponse:
    """
    Get complete formation configuration.

    Returns:
        Full formation YAML as JSON with defaults filled and secrets masked
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get full config with defaults
    config = deepcopy(formation.config)
    config = restore_secret_placeholders(config, formation.secret_placeholders)

    response = create_success_response(
        APIObjectType.FORMATION_CONFIG, APIEventType.FORMATION_CONFIG_RETRIEVED, config, request_id
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

    # Get server instance if available
    server = getattr(formation, '_server', None)

    # Calculate uptime
    uptime_seconds = 0
    request_count = 0
    if server:
        # Check for required attributes before accessing them
        if hasattr(server, '_start_time'):
            uptime_seconds = int(time.time() - server._start_time)
        if hasattr(server, '_request_count'):
            request_count = server._request_count

    # Use formation id as default name if name not specified
    formation_name = formation.config.get("name")
    if not formation_name:
        formation_name = formation.config.get("id", "unknown")

    # Get CPU and memory usage
    cpu_percent = None
    memory_usage_mb = None
    try:
        # Get CPU usage without blocking (uses last call's value)
        # Note: First call returns 0.0, subsequent calls return actual usage
        cpu_percent = psutil.cpu_percent(interval=None)
        # Get memory usage for this process
        process = psutil.Process()
        memory_usage_mb = process.memory_info().rss / 1024 / 1024
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        # Process-related errors - process may have terminated or access denied
        pass
    except Exception:
        # Catch any other unexpected psutil errors
        pass

    # Structure matching OpenAPI spec
    status = {
        "formation": {
            "id": formation.config.get("id", "unknown"),
            "name": formation_name,
            "description": formation.config.get("description", ""),
            "version": formation.config.get("version", "unknown"),
        },
        "agents": {
            "count": len(formation.config.get("agents", [])),
            "active": sum(1 for a in formation.config.get("agents", []) if a.get("active", True)),
        },
        "mcp_servers": {
            "count": len(formation.config.get("mcp", {}).get("servers", [])),
            "active": sum(1 for s in formation.config.get("mcp", {}).get("servers", []) if s.get("active", True)),
        },
        "stats": {
            "running": {
                "seconds": uptime_seconds,
                "since": int(server._start_time) if server and hasattr(server, '_start_time') else int(time.time()),
            },
            "memory": {
                "working_memory_mb": formation.config.get("memory", {}).get("working", {}).get("max_memory_mb", 512),
                "memory_usage_mb": memory_usage_mb,
            },
            "requests": {
                "total": request_count,
                "active": max(0, len(server._active_connections) - 1) if server and hasattr(
                    server, '_active_connections') else 0,  # Subtract current request

            },
            "buffer_size": formation.config.get("memory", {}).get("buffer", {}).get("size", 1000),
            "cpu_percent": cpu_percent,
        },
    }

    response = create_success_response(
        APIObjectType.FORMATION_STATUS, APIEventType.FORMATION_STATUS_RETRIEVED, status, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
