"""
Secret management endpoints.

These endpoints provide secret CRUD operations,
requiring admin API key authentication.
"""

import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...responses import (
    APIResponse,
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
                    if not secret_value:
                        masked_value = "••••••••"
                    else:
                        # Check for protocols (preserve these)
                        protocol_match = re.match(r'^([a-zA-Z][a-zA-Z0-9+.-]*://)', secret_value)
                        protocol = protocol_match.group(1) if protocol_match else ""
                        value_after_protocol = secret_value[len(protocol):]

                        # Check for common API key prefixes
                        common_prefixes = ["sk-", "pk-", "ghp_", "ghs_", "pat_", "key-", "tok-", "lin_"]
                        prefix_len = 0
                        for prefix in common_prefixes:
                            if value_after_protocol.startswith(prefix):
                                prefix_len = len(prefix)
                                break

                        if protocol:
                            # For URLs with protocols, be more careful about what we show
                            # Show protocol + first 2 chars + dots + last few chars
                            if len(value_after_protocol) > 8:
                                masked_value = f"{protocol}{value_after_protocol[:2]}•••••••{value_after_protocol[-4:]}"
                            else:
                                masked_value = f"{protocol}••••••••"
                        elif len(value_after_protocol) > 12:
                            if prefix_len > 0:
                                # Show prefix + 2 chars and last 4 chars
                                masked_value = f"{value_after_protocol[:prefix_len+2]}••••••{value_after_protocol[-4:]}"
                            else:
                                # Show first 4 and last 4 characters
                                masked_value = f"{value_after_protocol[:4]}••••••••{value_after_protocol[-4:]}"
                        elif len(value_after_protocol) > 6:
                            # For medium secrets, show first 3 and last 3
                            masked_value = f"{value_after_protocol[:3]}••••{value_after_protocol[-3:]}"
                        else:
                            # For very short secrets, just mask them entirely
                            masked_value = "••••••••"
                except Exception:
                    # If we can't get the secret, just use a generic mask
                    masked_value = "••••••••"

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
    if not await formation.secrets_manager.secret_exists(key):
        response = create_error_response(
            "SECRET_NOT_FOUND", f"Secret '{key}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Update secret
    await formation.secrets_manager.store_secret(key, secret.value, overwrite=True)

    # TODO: Add observability event for secret updated

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

    # TODO: Add observability event for secret deleted

    # Return standardized response format
    response = create_success_response(
        APIObjectType.SECRET,
        APIEventType.SECRET_DELETED,
        {"message": f"Secret '{key}' deleted successfully"},
        request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
