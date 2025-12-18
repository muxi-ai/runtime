"""
Logging configuration endpoints.

These endpoints provide logging configuration access and management,
requiring admin API key authentication.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Logging"])


class LoggingDestinationCreate(BaseModel):
    """Model for creating a logging destination."""

    id: Optional[str] = Field(default=None, description="Optional ID (auto-generated if not provided)")
    transport: Literal["stdout", "file", "stream"] = Field(..., description="Transport type: stdout, file, stream")
    destination: Optional[str] = Field(default=None, description="Destination path/URL (required for file and stream)")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")  # noqa: E501
    format: Literal["text", "jsonl"] = Field(default="jsonl", description="Log format: text or jsonl")
    enabled: bool = Field(default=True, description="Whether destination is enabled")

    @model_validator(mode='after')
    def validate_destination_requirement(self):
        """Validate that destination is provided when transport is file or stream."""
        if self.transport in ("file", "stream") and not self.destination:
            raise ValueError(
                f"destination is required when transport is '{self.transport}'. "
                f"Please provide a file path for 'file' transport or URL for 'stream' transport."
            )
        return self


class LoggingDestinationUpdate(BaseModel):
    """Model for updating logging destination configuration."""

    level: Optional[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]] = Field(
        default=None, description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )
    format: Optional[Literal["text", "jsonl"]] = Field(
        default=None, description="Log format: text or jsonl"
    )
    enabled: Optional[bool] = Field(default=None, description="Whether destination is enabled")


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


@router.get("/logging/destinations", response_model=APIResponse)
async def list_logging_destinations(request: Request) -> JSONResponse:
    """
    List all logging destinations.

    Returns:
        Logging destinations with two-tier structure:
        - system: Infrastructure event configuration
        - conversation: User-facing event streams
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get logging config from formation
    logging_config = formation.config.get("logging", {})

    # Parse system config (defaults)
    system_config = logging_config.get("system", {})
    system_data = {
        "level": system_config.get("level", "debug"),
        "destination": system_config.get("destination", "stdout"),
    }

    # Parse conversation config and extract destinations
    conversation_config = logging_config.get("conversation", {})
    destinations = []
    streams = conversation_config.get("streams", [])

    for idx, stream in enumerate(streams):
        # Defensive type check for malformed YAML entries
        if not isinstance(stream, dict):
            logger = logging.getLogger(__name__)
            logger.warning(
                "Malformed logging stream entry at index %d: expected dict, got %s. "
                "Value: %r. Skipping this entry.",
                idx,
                type(stream).__name__,
                stream
            )
            continue

        dest = {
            "id": stream.get("id", f"dest-{idx}"),
            "transport": stream.get("transport", "stdout"),
            "level": stream.get("level", "INFO"),
            "format": stream.get("format", "jsonl"),
            "enabled": stream.get("enabled", True),
        }
        # Add destination field if present
        if "destination" in stream:
            dest["destination"] = stream["destination"]
        destinations.append(dest)

    data = {
        "system": system_data,
        "conversation": {
            "destinations": destinations,
            "count": len(destinations),
        },
    }

    response = create_success_response(
        APIObjectType.LOGGING_DESTINATION_LIST,
        APIEventType.LOGGING_DESTINATIONS_LIST,
        data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.post("/logging/destinations", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def create_logging_destination(
    request: Request, destination: LoggingDestinationCreate
) -> JSONResponse:
    """
    Add a new logging destination.

    DEPRECATED: Logging configuration should be changed via formation YAML and redeployment.
    Runtime changes would be lost on next deploy.

    Args:
        destination: Destination configuration

    Returns:
        501 Not Implemented - persistence not yet implemented
    """
    request_id = getattr(request.state, "request_id", None)

    # Return 501 Not Implemented - logging destination persistence not yet implemented
    # This endpoint requires:
    # 1. Updating formation.config.logging.streams with the new destination
    # 2. Persisting the updated formation config to disk/storage
    # 3. Reloading the logging subsystem to activate the new destination
    # Until these are implemented, returning 501 is more honest than accepting
    # the request and silently failing to persist it.
    response = create_error_response(
        error_code="NOT_IMPLEMENTED",
        message="Logging destination persistence is not yet implemented",
        trace=None,
        request_id=request_id,
        idempotency_key=None,
        data=None,
        error_data={
            "reason": "Dynamic logging destination creation requires formation config persistence",
            "workaround": "Add logging destinations directly to your formation.afs file",
            "required_implementation": [
                "Formation config update mechanism",
                "Logging subsystem reload/reconfiguration",
                "Persistent storage of logging configuration"
            ]
        },
    )
    return JSONResponse(content=response.model_dump(), status_code=501)


# @router.patch("/logging/destinations/{destination_id}", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def update_logging_destination(
    request: Request, destination_id: str, update: LoggingDestinationUpdate
) -> JSONResponse:
    """
    Update a logging destination.

    DEPRECATED: Logging configuration should be changed via formation YAML and redeployment.
    Runtime changes would be lost on next deploy.

    Args:
        destination_id: ID of the destination
        update: Fields to update

    Returns:
        501 Not Implemented - persistence not yet implemented
    """
    request_id = getattr(request.state, "request_id", None)

    # Return 501 Not Implemented - logging destination updates not yet implemented
    # This endpoint requires the same persistence infrastructure as POST
    response = create_error_response(
        error_code="NOT_IMPLEMENTED",
        message="Logging destination updates are not yet implemented",
        trace=None,
        request_id=request_id,
        idempotency_key=None,
        data=None,
        error_data={
            "reason": "Dynamic logging destination updates require formation config persistence",
            "workaround": "Update logging destinations directly in your formation.afs file and restart",
            "required_implementation": [
                "Formation config update mechanism",
                "Logging subsystem reload/reconfiguration",
                "Persistent storage of logging configuration"
            ]
        },
    )
    return JSONResponse(content=response.model_dump(), status_code=501)


# @router.delete("/logging/destinations/{destination_id}", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def delete_logging_destination(request: Request, destination_id: str) -> JSONResponse:
    """
    Remove a logging destination.

    DEPRECATED: Logging configuration should be changed via formation YAML and redeployment.
    Runtime changes would be lost on next deploy.

    Args:
        destination_id: ID of the destination to remove

    Returns:
        501 Not Implemented - persistence not yet implemented
    """
    request_id = getattr(request.state, "request_id", None)

    # Return 501 Not Implemented - logging destination deletion not yet implemented
    # This endpoint requires the same persistence infrastructure as POST and PATCH
    response = create_error_response(
        error_code="NOT_IMPLEMENTED",
        message="Logging destination deletion is not yet implemented",
        trace=None,
        request_id=request_id,
        idempotency_key=None,
        data=None,
        error_data={
            "reason": "Dynamic logging destination deletion requires formation config persistence",
            "workaround": "Remove logging destinations directly from your formation.afs file and restart",
            "required_implementation": [
                "Formation config update mechanism",
                "Logging subsystem reload/reconfiguration",
                "Persistent storage of logging configuration"
            ]
        },
    )
    return JSONResponse(content=response.model_dump(), status_code=501)
