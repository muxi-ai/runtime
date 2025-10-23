"""
Logging configuration endpoints.

These endpoints provide logging configuration access and management,
requiring admin API key authentication.
"""

from typing import Dict, Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType
from .....services import observability

router = APIRouter(tags=["Logging"])


class LoggingDestinationCreate(BaseModel):
    """Model for creating a logging destination."""

    id: Optional[str] = Field(default=None, description="Optional ID (auto-generated if not provided)")
    transport: str = Field(..., description="Transport type: stdout, file, stream")
    destination: Optional[str] = Field(default=None, description="Destination path/URL (required for file and stream)")
    level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    format: str = Field(default="jsonl", description="Log format: text or jsonl")
    enabled: bool = Field(default=True, description="Whether destination is enabled")


class LoggingDestinationUpdate(BaseModel):
    """Model for updating logging destination configuration."""

    level: Optional[str] = Field(default=None, description="Log level")
    format: Optional[str] = Field(default=None, description="Log format")
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
        List of all configured logging destinations
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get logging config from formation
    logging_config = formation.config.get("logging", {})
    
    # Extract destinations (streams in YAML)
    destinations = []
    streams = logging_config.get("streams", [])
    
    for idx, stream in enumerate(streams):
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
        "destinations": destinations,
        "count": len(destinations),
    }

    response = create_success_response(
        APIObjectType.LOGGING_DESTINATION_LIST,
        APIEventType.LOGGING_DESTINATIONS_LIST,
        data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/logging/destinations", response_model=APIResponse)
async def create_logging_destination(
    request: Request, destination: LoggingDestinationCreate
) -> JSONResponse:
    """
    Add a new logging destination.

    Args:
        destination: Destination configuration

    Returns:
        Created destination with ID
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate transport type
    if destination.transport not in ["stdout", "file", "stream"]:
        response = create_error_response(
            "INVALID_REQUEST",
            f"Invalid transport '{destination.transport}'. Must be: stdout, file, or stream",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Validate destination field for file/stream
    if destination.transport in ["file", "stream"] and not destination.destination:
        response = create_error_response(
            "INVALID_REQUEST",
            f"Field 'destination' is required for transport type '{destination.transport}'",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Generate ID if not provided
    dest_id = destination.id
    if not dest_id:
        from .....utils.id_generator import generate_request_id
        dest_id = f"dest_{generate_request_id()[4:]}"

    # Build destination config
    dest_config = {
        "id": dest_id,
        "transport": destination.transport,
        "level": destination.level,
        "format": destination.format,
        "enabled": destination.enabled,
    }
    if destination.destination:
        dest_config["destination"] = destination.destination

    # TODO: Add destination to formation logging config
    # This would require updating the formation config and reloading logging

    observability.observe(
        event_type=observability.SystemEvents.OPERATION_COMPLETED,
        level=observability.EventLevel.INFO,
        description=f"Logging destination '{dest_id}' created",
        data={"destination_id": dest_id, "transport": destination.transport},
    )

    response = create_success_response(
        APIObjectType.LOGGING_DESTINATION,
        APIEventType.LOGGING_DESTINATION_CREATED,
        dest_config,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=201)


@router.patch("/logging/destinations/{destination_id}", response_model=APIResponse)
async def update_logging_destination(
    request: Request, destination_id: str, update: LoggingDestinationUpdate
) -> JSONResponse:
    """
    Update a logging destination.

    Args:
        destination_id: ID of the destination
        update: Fields to update

    Returns:
        Updated destination configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get logging config
    logging_config = formation.config.get("logging", {})
    streams = logging_config.get("streams", [])

    # Find destination by ID
    dest_index = None
    for idx, stream in enumerate(streams):
        if stream.get("id", f"dest-{idx}") == destination_id:
            dest_index = idx
            break

    if dest_index is None:
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Logging destination '{destination_id}' not found",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Apply updates
    dest = streams[dest_index]
    if update.level is not None:
        dest["level"] = update.level
    if update.format is not None:
        dest["format"] = update.format
    if update.enabled is not None:
        dest["enabled"] = update.enabled

    # TODO: Persist changes to formation config and reload logging

    observability.observe(
        event_type=observability.SystemEvents.OPERATION_COMPLETED,
        level=observability.EventLevel.INFO,
        description=f"Logging destination '{destination_id}' updated",
        data={"destination_id": destination_id, "updates": update.model_dump(exclude_unset=True)},
    )

    response = create_success_response(
        APIObjectType.LOGGING_DESTINATION,
        APIEventType.LOGGING_DESTINATION_UPDATED,
        dest,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/logging/destinations/{destination_id}", response_model=APIResponse)
async def delete_logging_destination(request: Request, destination_id: str) -> JSONResponse:
    """
    Remove a logging destination.

    Args:
        destination_id: ID of the destination to remove

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get logging config
    logging_config = formation.config.get("logging", {})
    streams = logging_config.get("streams", [])

    # Find destination by ID
    dest_index = None
    for idx, stream in enumerate(streams):
        if stream.get("id", f"dest-{idx}") == destination_id:
            dest_index = idx
            break

    if dest_index is None:
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Logging destination '{destination_id}' not found",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Remove destination
    del streams[dest_index]

    # TODO: Persist changes to formation config and reload logging

    observability.observe(
        event_type=observability.SystemEvents.OPERATION_COMPLETED,
        level=observability.EventLevel.INFO,
        description=f"Logging destination '{destination_id}' removed",
        data={"destination_id": destination_id},
    )

    response = create_success_response(
        APIObjectType.MESSAGE,
        APIEventType.LOGGING_DESTINATION_DELETED,
        {"message": f"Logging destination '{destination_id}' removed successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
