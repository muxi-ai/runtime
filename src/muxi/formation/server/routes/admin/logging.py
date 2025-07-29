"""
Logging configuration endpoints.

These endpoints provide logging configuration access and management,
requiring admin API key authentication.
"""

from typing import Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    create_success_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Logging"])


class LoggingStreamUpdate(BaseModel):
    """Model for updating logging stream configuration."""

    enabled: bool
    level: str = "INFO"
    format: str = "json"
    options: Dict[str, Any] = {}


@router.get("/logging", response_model=APIResponse)
async def get_logging_config(request: Request) -> JSONResponse:
    """
    Get complete logging configuration.

    Returns:
        Full logging YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    logging_config = formation.config.get("logging", {})

    response = create_success_response(
        APIObjectType("logging"), APIEventType("logging.retrieved"), logging_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.patch("/logging/streams/{name}", response_model=APIResponse)
async def update_logging_stream(
    request: Request, name: str, stream: LoggingStreamUpdate
) -> JSONResponse:
    """
    Update a specific logging stream configuration.

    Args:
        name: Name of the logging stream (e.g., console, file, syslog)
        stream: Stream configuration to update

    Returns:
        Updated logging stream configuration
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement logging stream update logic
    # Validate stream name and update configuration

    stream_config = {
        "name": name,
        "enabled": stream.enabled,
        "level": stream.level,
        "format": stream.format,
        "options": stream.options,
    }

    response = create_success_response(
        APIObjectType("logging_stream"),
        APIEventType("logging_stream.updated"),
        stream_config,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
