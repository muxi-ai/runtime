"""
Health check and status endpoints.

These endpoints provide basic server health information
and formation status without requiring authentication.
"""

from typing import Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....utils.version import get_version

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Basic health check endpoint.

    Returns:
        Simple health status
    """
    return {"status": "healthy"}


@router.get("/status")
async def formation_status(request: Request) -> JSONResponse:
    """
    Get detailed formation status.

    Returns formation information including:
    - Formation ID and description
    - Server version
    - Uptime
    - Agent count
    - Active connections

    Returns:
        Detailed status information
    """
    # Get formation from app state (will be set during server startup)
    formation = request.app.state.formation

    status = {
        "formation": {
            "id": formation.formation_id,
            "description": formation.config.get("description", ""),
            "version": formation.config.get("version", "1.0.0"),
        },
        "server": {
            "version": get_version(),
            "uptime_seconds": 0,  # TODO: Track actual uptime
        },
        "agents": {
            "count": len(formation._agents_config) if hasattr(formation, "_agents_config") else 0,
            "active": 0,  # TODO: Track active agents
        },
        "connections": {
            "active_http": 0,  # TODO: Track connections
            "active_websocket": 0,
        }
    }

    # TODO: Add observability event for health check

    return JSONResponse(content=status)
