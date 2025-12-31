"""
LLM configuration endpoints.

These endpoints provide LLM configuration access and management,
requiring admin API key authentication.
"""

from typing import Dict, Any
from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from ...secrets import restore_secret_placeholders
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["LLM"])

# Valid LLM settings that can be updated/reset via API
VALID_LLM_SETTINGS = {"temperature", "max_tokens", "timeout_seconds"}


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

    llm_config = deepcopy(formation.config.get("llm", {}))

    # Create a temporary config structure to apply placeholders
    temp_config = {"llm": llm_config}
    temp_config = restore_secret_placeholders(temp_config, formation.secret_placeholders)
    llm_config = temp_config.get("llm", {})

    response = create_success_response(
        APIObjectType.LLM_SETTINGS, APIEventType.LLM_SETTINGS_RETRIEVED, llm_config, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.patch("/llm/settings", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def update_llm_settings(request: Request, settings: LLMSettingsUpdate) -> JSONResponse:
    """
    Update LLM settings.

    DEPRECATED: LLM configuration should be changed via formation YAML and redeployment.

    Args:
        settings: New LLM settings to apply

    Returns:
        Updated LLM configuration
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Update in-memory configuration (ephemeral - lost on restart)
    llm_config = formation.config.setdefault("llm", {})
    llm_settings = llm_config.setdefault("settings", {})

    # Validate all incoming keys against VALID_LLM_SETTINGS
    invalid_keys = [key for key in settings.settings.keys() if key not in VALID_LLM_SETTINGS]
    if invalid_keys:
        response = create_error_response(
            "INVALID_PARAMS",
            f"Invalid LLM setting(s): {', '.join(sorted(invalid_keys))}. "
            f"Valid settings are: {', '.join(sorted(VALID_LLM_SETTINGS))}",
            None,
            request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Update only the validated settings
    for key, value in settings.settings.items():
        llm_settings[key] = value

    response = create_success_response(
        APIObjectType.LLM_SETTINGS,
        APIEventType.LLM_SETTINGS_UPDATED,
        {"settings": llm_settings},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# @router.delete("/llm/settings/{item}", response_model=APIResponse)  # DEPRECATED: Use deployment instead
async def reset_llm_setting(request: Request, item: str) -> JSONResponse:
    """
    Reset a specific LLM setting to default.

    DEPRECATED: LLM configuration should be changed via formation YAML and redeployment.

    Args:
        item: Setting item to reset

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate the item parameter
    if item not in VALID_LLM_SETTINGS:
        response = create_error_response(
            "INVALID_PARAMS",
            f"Invalid LLM setting '{item}'. Valid settings are: {', '.join(sorted(VALID_LLM_SETTINGS))}",
            None,
            request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Reset specific LLM setting by removing it from in-memory config
    # This restores the formation YAML default value
    llm_config = formation.config.get("llm", {})
    settings = llm_config.get("settings", {})

    if item in settings:
        del settings[item]
        # Note: This only updates the in-memory config, not persisted

    response = create_success_response(
        APIObjectType.LLM_SETTINGS,
        APIEventType.LLM_RESET,
        {"message": f"LLM setting '{item}' reset to default"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
