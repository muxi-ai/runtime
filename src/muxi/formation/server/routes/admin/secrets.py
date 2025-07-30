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
    secret_list_response,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

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
        masked_secrets = {}
    else:
        try:
            # Get all secret names (async call)
            secret_names = await formation.secrets_manager.list_secrets()

            # Mask values with consistent pattern (no length disclosure)
            masked_secrets = {name: "••••••••" for name in secret_names}
        except Exception as e:
            # Handle secrets manager errors gracefully
            response = create_error_response(
                "SECRETS_ERROR", f"Error retrieving secrets: {str(e)}", None, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=500)

    # Create structured response
    response = secret_list_response({"secrets": masked_secrets}, request_id)
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
    if formation.secrets_manager.has_secret(secret.key):
        response = create_error_response(
            "SECRET_EXISTS", f"Secret '{secret.key}' already exists", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=409)

    # Create secret
    formation.secrets_manager.set_secret(secret.key, secret.value)

    # TODO: Add observability event for secret created

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
    if not formation.secrets_manager.has_secret(key):
        response = create_error_response(
            "SECRET_NOT_FOUND", f"Secret '{key}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Update secret
    formation.secrets_manager.set_secret(key, secret.value)

    # TODO: Add observability event for secret updated

    response = create_success_response(
        APIObjectType.SECRET,
        APIEventType.SECRET_UPDATED,
        {"key": key, "value": "••••••••"},
        request_id,
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
    if not formation.secrets_manager.has_secret(key):
        response = create_error_response(
            "SECRET_NOT_FOUND", f"Secret '{key}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Delete secret
    formation.secrets_manager.delete_secret(key)

    # TODO: Add observability event for secret deleted

    response = create_success_response(
        APIObjectType.SECRET,
        APIEventType.SECRET_DELETED,
        {"message": f"Secret '{key}' deleted successfully"},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
