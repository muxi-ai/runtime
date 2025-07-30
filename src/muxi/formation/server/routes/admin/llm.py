"""
LLM configuration endpoints.

These endpoints provide LLM configuration access and management,
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

router = APIRouter(tags=["LLM"])


class LLMSettingsUpdate(BaseModel):
    """Model for updating LLM settings."""

    settings: Dict[str, Any]


@router.get("/llm/settings", response_model=APIResponse)
async def get_llm_config(request: Request) -> JSONResponse:
    """
    Get complete LLM configuration.

    Returns:
        Full LLM YAML as JSON with defaults filled
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    llm_config = formation.config.get("llm", {})

    response = create_success_response(
        APIObjectType.LLM, APIEventType.LLM_RETRIEVED, llm_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.patch("/llm/settings", response_model=APIResponse)
async def update_llm_settings(request: Request, settings: LLMSettingsUpdate) -> JSONResponse:
    """
    Update LLM settings.

    Args:
        settings: New LLM settings to apply

    Returns:
        Updated LLM configuration
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement LLM settings update logic
    # For now, just return success with the provided settings

    response = create_success_response(
        APIObjectType.LLM,
        APIEventType.LLM_UPDATED,
        {"settings": settings.settings},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/llm/settings/{item}", response_model=APIResponse)
async def reset_llm_setting(request: Request, item: str) -> JSONResponse:
    """
    Reset a specific LLM setting to default.

    Args:
        item: Setting item to reset

    Returns:
        Success response
    """
    request_id = getattr(request.state, "request_id", None)

    # TODO: Implement LLM setting reset logic
    # Check if setting exists and reset to default

    response = create_success_response(
        APIObjectType.LLM,
        APIEventType.LLM_RESET,
        {"message": f"LLM setting '{item}' reset to default"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
