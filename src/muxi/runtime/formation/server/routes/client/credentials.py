"""
User credential management endpoints.

These endpoints provide CRUD operations for user credentials,
requiring either ClientKey or AdminKey with X-Muxi-User-ID header.
"""

import json
import secrets
from typing import Optional, Tuple, Dict, Any

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Credentials"])


class CredentialCreate(BaseModel):
    """Request model for creating a credential."""
    service: str = Field(..., description="Service name (e.g., github, gmail, slack)")
    name: Optional[str] = Field(None, description="Optional friendly name. Auto-discovered if omitted.")
    credential: Dict[str, Any] = Field(..., description="Credential data (structure varies by service)")


def _redact_credential(credential_data: Any) -> str:
    """
    Create a redacted preview of credential data.
    
    Shows first 7 chars + ***** + last 3 chars.
    If credential < 15 chars: ***redacted***
    For nested objects, redacts each string value.
    """
    if isinstance(credential_data, dict):
        # For nested credentials, find the primary value to redact
        # Priority: token > access_token > api_key > password > first string value
        priority_keys = ["token", "access_token", "api_key", "password", "key", "secret"]
        value = None
        for key in priority_keys:
            if key in credential_data and isinstance(credential_data[key], str):
                value = credential_data[key]
                break
        if value is None:
            # Find first string value
            for v in credential_data.values():
                if isinstance(v, str) and len(v) > 5:
                    value = v
                    break
        if value is None:
            return "***redacted***"
        return _redact_string(value)
    elif isinstance(credential_data, str):
        return _redact_string(credential_data)
    else:
        return "***redacted***"


def _redact_string(value: str) -> str:
    """Redact a string value."""
    if len(value) < 15:
        return "***redacted***"
    return f"{value[:7]}*****{value[-3:]}"


def _check_auth_and_user_id(
    request: Request,
    x_user_id: Optional[str],
    request_id: Optional[str],
) -> Tuple[Optional[str], bool, Optional[JSONResponse]]:
    """
    Check authentication type and validate user_id requirement.

    Returns:
        Tuple of (user_id, is_admin, error_response)
    """
    formation = request.app.state.formation

    # Get keys from formation._api_keys (where they're actually stored)
    api_keys = getattr(formation, "_api_keys", {})
    admin_key = api_keys.get("admin", "")
    client_key = api_keys.get("client", "")

    provided_admin_key = request.headers.get("x-muxi-admin-key")
    provided_client_key = request.headers.get("x-muxi-client-key")

    is_admin = False
    if provided_admin_key and admin_key and secrets.compare_digest(provided_admin_key, admin_key):
        is_admin = True
    elif provided_client_key and client_key and secrets.compare_digest(provided_client_key, client_key):
        is_admin = False
    else:
        response = create_error_response(
            "UNAUTHORIZED",
            "Valid API key required",
            None,
            request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=401)

    # X-Muxi-User-ID is required for both auth types
    if not x_user_id:
        response = create_error_response(
            "INVALID_REQUEST",
            "X-Muxi-User-ID header is required",
            None,
            request_id,
        )
        return None, False, JSONResponse(content=response.model_dump(), status_code=400)

    return x_user_id, is_admin, None


@router.get("/credentials/services", response_model=APIResponse)
async def list_credential_services(
    request: Request,
) -> JSONResponse:
    """
    List available services that can use user credentials.
    
    Returns the list of MCP servers configured with user credential placeholders.
    Developers should check this list before storing credentials.
    
    No X-Muxi-User-ID required - this returns formation-level configuration.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get MCP servers that use user credentials
    mcp_servers = getattr(formation, "_mcp_servers_with_user_credentials", {})

    services = []
    for server_id, config in mcp_servers.items():
        services.append({
            "service": config.get("service", server_id),
            "server_id": server_id,
            "description": f"MCP server requiring user authentication",
        })

    response = create_success_response(
        APIObjectType.CREDENTIAL_LIST,
        APIEventType.CREDENTIALS_LISTED,
        {"services": services, "count": len(services)},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/credentials", response_model=APIResponse)
async def list_credentials(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    List all credentials for the authenticated user.
    Returns metadata only - secrets are never exposed, only a redacted preview.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
    if error_response:
        return error_response

    # Get credential resolver from overlord
    overlord = getattr(formation, "_overlord", None)
    credential_resolver = getattr(overlord, "credential_resolver", None) if overlord else None

    if not credential_resolver:
        # No credential resolver - return empty list
        response = create_success_response(
            APIObjectType.CREDENTIAL_LIST,
            APIEventType.CREDENTIALS_LISTED,
            {"credentials": [], "count": 0},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    try:
        # Get all credentials for the user
        credentials_by_service = await credential_resolver.list_credentials(user_id)

        # Flatten and format for response
        credentials = []
        for service, creds in credentials_by_service.items():
            for cred in creds:
                # Parse the stored credentials JSON to create preview
                try:
                    cred_data = json.loads(cred["credentials"]) if isinstance(cred["credentials"], str) else cred["credentials"]
                except (json.JSONDecodeError, TypeError):
                    cred_data = cred["credentials"]

                credentials.append({
                    "credential_id": cred["credential_id"],
                    "service": service,
                    "name": cred["name"],
                    "credential_preview": _redact_credential(cred_data),
                    "created_at": cred["created_at"],
                    "updated_at": cred["updated_at"],
                })

        response = create_success_response(
            APIObjectType.CREDENTIAL_LIST,
            APIEventType.CREDENTIALS_LISTED,
            {"credentials": credentials, "count": len(credentials)},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to list credentials: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.post("/credentials", response_model=APIResponse)
async def create_credential(
    request: Request,
    body: CredentialCreate,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Store a new credential for the authenticated user.
    The credential is encrypted at rest.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
    if error_response:
        return error_response

    # Validate service name: lowercase, no spaces
    service = body.service.lower().strip()
    if " " in service:
        response = create_error_response(
            "VALIDATION_ERROR",
            "Service name cannot contain spaces",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Get credential resolver from overlord
    overlord = getattr(formation, "_overlord", None)
    credential_resolver = getattr(overlord, "credential_resolver", None) if overlord else None

    if not credential_resolver:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Credential service is not available. Ensure persistent memory is configured.",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        # Store the credential
        credential_id = await credential_resolver.store(
            user_id=user_id,
            service=service,
            credentials=body.credential,
            name=body.name,
        )

        # Get the stored credential to return metadata
        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        response = create_success_response(
            APIObjectType.CREDENTIAL,
            APIEventType.CREDENTIAL_CREATED,
            {
                "credential_id": credential_id,
                "service": service,
                "name": body.name or service,
                "credential_preview": _redact_credential(body.credential),
                "created_at": created_at,
            },
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=201)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to create credential: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.get("/credentials/{credential_id}", response_model=APIResponse)
async def get_credential(
    request: Request,
    credential_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Get metadata for a specific credential.
    Returns metadata only - secrets are never exposed, only a redacted preview.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
    if error_response:
        return error_response

    # Get credential resolver from overlord
    overlord = getattr(formation, "_overlord", None)
    credential_resolver = getattr(overlord, "credential_resolver", None) if overlord else None

    if not credential_resolver:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Credential service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        # Get all credentials and find the one with matching ID
        credentials_by_service = await credential_resolver.list_credentials(user_id)

        for service, creds in credentials_by_service.items():
            for cred in creds:
                if cred["credential_id"] == credential_id:
                    # Parse the stored credentials JSON to create preview
                    try:
                        cred_data = json.loads(cred["credentials"]) if isinstance(cred["credentials"], str) else cred["credentials"]
                    except (json.JSONDecodeError, TypeError):
                        cred_data = cred["credentials"]

                    response = create_success_response(
                        APIObjectType.CREDENTIAL,
                        APIEventType.CREDENTIAL_RETRIEVED,
                        {
                            "credential_id": cred["credential_id"],
                            "service": service,
                            "name": cred["name"],
                            "credential_preview": _redact_credential(cred_data),
                            "created_at": cred["created_at"],
                            "updated_at": cred["updated_at"],
                        },
                        request_id,
                    )
                    return JSONResponse(content=response.model_dump(), status_code=200)

        # Not found
        response = create_error_response(
            "RESOURCE_NOT_FOUND",
            f"Credential not found: {credential_id}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to get credential: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete("/credentials/{credential_id}", response_model=APIResponse)
async def delete_credential(
    request: Request,
    credential_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """
    Delete a credential for the authenticated user.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Check auth and validate user_id requirement
    user_id, is_admin, error_response = _check_auth_and_user_id(request, x_user_id, request_id)
    if error_response:
        return error_response

    # Get credential resolver from overlord
    overlord = getattr(formation, "_overlord", None)
    credential_resolver = getattr(overlord, "credential_resolver", None) if overlord else None

    if not credential_resolver:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Credential service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        # Find the credential to get its service
        credentials_by_service = await credential_resolver.list_credentials(user_id)
        target_service = None
        
        for service, creds in credentials_by_service.items():
            for cred in creds:
                if cred["credential_id"] == credential_id:
                    target_service = service
                    break
            if target_service:
                break

        if not target_service:
            response = create_error_response(
                "RESOURCE_NOT_FOUND",
                f"Credential not found: {credential_id}",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=404)

        # Delete the credential
        deleted = await credential_resolver.delete_credential(user_id, target_service)

        if deleted:
            response = create_success_response(
                APIObjectType.CREDENTIAL,
                APIEventType.CREDENTIAL_DELETED,
                {
                    "credential_id": credential_id,
                    "deleted": True,
                },
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)
        else:
            response = create_error_response(
                "RESOURCE_NOT_FOUND",
                f"Credential not found: {credential_id}",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=404)

    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to delete credential: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)
