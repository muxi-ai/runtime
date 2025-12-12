"""
Overlord configuration endpoints.

These endpoints provide overlord configuration access,
requiring admin API key authentication.
"""

from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
)
from ...secrets import restore_secret_placeholders
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Overlord"])


@router.get("/overlord", response_model=APIResponse)
async def get_overlord_config(request: Request) -> JSONResponse:
    """
    Get complete overlord configuration.

    Returns:
        Full overlord configuration per API spec including persona, llm, caching,
        response, workflow, and clarification settings.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord_raw = formation.config.get("overlord", {})
    llm_config = formation.config.get("llm", {})

    # Build overlord config per API spec structure
    overlord_config = {
        "persona": overlord_raw.get("persona", ""),
        "llm": overlord_raw.get("llm", {}),
        "caching": llm_config.get("settings", {}).get("caching", {"enabled": True, "ttl": 3600}),
        "response": overlord_raw.get("response", {
            "format": "markdown",
            "widgets": False,
            "streaming": True,
        }),
        "workflow": overlord_raw.get("workflow", {
            "auto_decomposition": True,
            "plan_approval_threshold": 7,
            "complexity_method": "heuristic",
            "complexity_threshold": 7.0,
            "routing_strategy": "capability_based",
            "enable_agent_affinity": True,
            "error_recovery": "retry_with_backoff",
            "parallel_execution": True,
            "max_parallel_tasks": 5,
            "partial_results": True,
        }),
        "clarification": overlord_raw.get("clarification", {
            "max_questions": 5,
            "style": "conversational",
            "persist_learned_info": False,
        }),
    }

    # Create a temporary config structure to apply placeholders
    temp_config = {"overlord": overlord_config}
    temp_config = restore_secret_placeholders(temp_config, formation.secret_placeholders)
    overlord_config = temp_config.get("overlord", {})

    response = create_success_response(
        APIObjectType.OVERLORD_CONFIG, APIEventType.OVERLORD_CONFIG_RETRIEVED, overlord_config, request_id
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
        APIObjectType.PERSONA,
        APIEventType.PERSONA_RETRIEVED,
        {"persona": persona},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
