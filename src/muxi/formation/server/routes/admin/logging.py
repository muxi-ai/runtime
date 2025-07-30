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
    create_error_response,
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
        APIObjectType.LOGGING, APIEventType.LOGGING_RETRIEVED, logging_config, request_id
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

    # Define valid logging stream names
    VALID_LOGGING_STREAMS = {"console", "file", "syslog"}
    
    # Validate the stream name
    if name not in VALID_LOGGING_STREAMS:
        response = create_error_response(
            "INVALID_PARAMS",
            f"Invalid logging stream '{name}'. Valid streams are: {', '.join(sorted(VALID_LOGGING_STREAMS))}",
            None,
            request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # TODO: Implement logging stream update logic
    # Update configuration for the validated stream

    stream_config = {
        "name": name,
        "enabled": stream.enabled,
        "level": stream.level,
        "format": stream.format,
        "options": stream.options,
    }

    response = create_success_response(
        APIObjectType.LOGGING,
        APIEventType.LOGGING_UPDATED,
        stream_config,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
