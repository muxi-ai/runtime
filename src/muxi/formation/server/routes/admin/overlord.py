"""
Overlord configuration endpoints.

These endpoints provide overlord configuration access,
requiring admin API key authentication.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Overlord"])


@router.get("/overlord", response_model=APIResponse)
async def get_overlord_config(request: Request) -> JSONResponse:
    """
    Get complete overlord configuration.

    Returns:
        Full overlord YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord_config = formation.config.get("overlord", {})

    response = create_success_response(
        APIObjectType("overlord"), APIEventType("overlord.retrieved"), overlord_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/overlord/persona", response_model=APIResponse)
async def get_overlord_persona(request: Request) -> JSONResponse:
    """
    Get overlord persona configuration.

    Returns:
        Persona string from overlord configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    persona = formation.config.get("overlord", {}).get("persona", "")

    response = create_success_response(
        APIObjectType("persona"),
        APIEventType("persona.retrieved"),
        {"persona": persona},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
