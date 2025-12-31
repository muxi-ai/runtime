"""
Secret management endpoints.

These endpoints provide secret CRUD operations,
requiring admin API key authentication.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from ...utils import mask_secret_value
from .....datatypes.api import APIEventType, APIObjectType
from .....services import observability

router = APIRouter(tags=["Secrets"])


class SecretCreate(BaseModel):
    """Model for creating a secret."""

    key: str
    value: str


class SecretUpdate(BaseModel):
    """Model for updating a secret."""

    value: str


@router.get("/secrets", response_model=APIResponse)
async def list_secrets(request: Request) -> JSONResponse:
    """
    List all secret keys (with masked values).

    Returns:
        Structured response with dictionary of secret keys with masked values
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        secret_list = {
            "secrets": {},
            "count": 0
        }
    else:
        try:
            # Get all secret names (async call)
            secret_names = await formation.secrets_manager.list_secrets()

            # Create secrets object with partially masked values
            secrets_dict = {}
            for name in secret_names:
                # Get the actual secret value to partially mask it
                try:
                    secret_value = await formation.secrets_manager.get_secret(name)
                    masked_value = mask_secret_value(secret_value)
                except Exception:
                    # If we can't get the secret, just use a generic mask
                    masked_value = mask_secret_value(None)

                secrets_dict[name] = masked_value

            # Return in spec-compliant format
            secret_list = {
                "secrets": secrets_dict,
                "count": len(secret_names)
            }
        except Exception as e:
            # Handle secrets manager errors gracefully
            response = create_error_response(
                "SECRETS_ERROR", f"Error retrieving secrets: {str(e)}", None, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=500)

    # Create structured response with spec-compliant format
    response = create_success_response(
        APIObjectType.SECRET_LIST, APIEventType.SECRET_LIST, secret_list, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/secrets", response_model=APIResponse)
async def create_secret(request: Request, secret: SecretCreate) -> JSONResponse:
    """
    Create a new secret.

    Args:
        secret: Secret key and value

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Secrets manager not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Check if secret already exists
    if await formation.secrets_manager.secret_exists(secret.key):
        response = create_error_response(
            "SECRET_EXISTS", f"Secret '{secret.key}' already exists", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=409)

    # Create secret
    await formation.secrets_manager.store_secret(secret.key, secret.value)

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={"secret_key": secret.key, "operation": "create"},
        description=f"Secret '{secret.key}' created successfully",
    )

    response = create_success_response(
        APIObjectType.SECRET,
        APIEventType.SECRET_CREATED,
        {"message": f"Secret '{secret.key}' created successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=201)


@router.put("/secrets/{key}", response_model=APIResponse)
async def update_secret(request: Request, key: str, secret: SecretUpdate) -> JSONResponse:
    """
    Update an existing secret.

    Args:
        key: Secret key
        secret: New secret value

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Secrets manager not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Check if secret exists
    if not await formation.secrets_manager.secret_exists(key):
        response = create_error_response(
            "SECRET_NOT_FOUND", f"Secret '{key}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Update secret
    await formation.secrets_manager.store_secret(key, secret.value, overwrite=True)

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={"secret_key": key, "operation": "update"},
        description=f"Secret '{key}' updated successfully",
    )

    # Return standardized response format
    response = create_success_response(
        APIObjectType.SECRET,
        APIEventType.SECRET_UPDATED,
        {"message": f"Secret '{key}' updated successfully"},
        request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/secrets/{key}", response_model=APIResponse)
async def delete_secret(request: Request, key: str) -> JSONResponse:
    """
    Delete a secret.

    Args:
        key: Secret key to delete

    Returns:
        Success response
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    if not hasattr(formation, "secrets_manager") or not formation.secrets_manager:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Secrets manager not available", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Check if secret exists
    if not await formation.secrets_manager.secret_exists(key):
        response = create_error_response(
            "SECRET_NOT_FOUND", f"Secret '{key}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Check if secret is in use
    if formation.is_secret_in_use(key):
        response = create_error_response(
            "SECRET_IN_USE",
            f"Cannot delete secret '{key}' because it is currently in use by the formation configuration",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=409)

    # Delete secret
    await formation.secrets_manager.delete_secret(key)

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={"secret_key": key, "operation": "delete"},
        description=f"Secret '{key}' deleted successfully",
    )

    # Return standardized response format
    response = create_success_response(
        APIObjectType.SECRET,
        APIEventType.SECRET_DELETED,
        {"message": f"Secret '{key}' deleted successfully"},
        request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
