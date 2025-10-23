"""
User identifier management endpoints.

These endpoints provide user identity mapping operations,
requiring client API key authentication.
"""

from typing import List, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType
from .....utils.user_resolution import resolve_user_identifier, associate_user_identifiers
from .....services import observability

router = APIRouter(tags=["Users"])


@router.get("/users/identifiers/{user_id}", response_model=APIResponse)
async def get_user_identifiers(request: Request, user_id: str) -> JSONResponse:
    """
    List all identifiers associated with a MUXI user.

    Args:
        user_id: MUXI user ID (public_id like usr_abc123)

    Returns:
        List of identifiers with their types and metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get database manager
    db_manager = formation.get_db_manager()
    if not db_manager:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Database service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        # Query database for user and their identifiers
        from .....services.memory.long_term import User, UserIdentifier
        from sqlalchemy import select

        async with db_manager.get_session() as session:
            # Find user by public_id (muxi_user_id)
            result = await session.execute(
                select(User).where(User.public_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                response = create_error_response(
                    "RESOURCE_NOT_FOUND",
                    f"User not found: {user_id}",
                    None,
                    request_id,
                )
                return JSONResponse(content=response.model_dump(), status_code=404)

            # Get all identifiers for this user
            result = await session.execute(
                select(UserIdentifier).where(
                    UserIdentifier.user_id == user.id,
                    UserIdentifier.formation_id == formation.formation_id
                )
            )
            identifiers = result.scalars().all()

            # Format identifiers
            identifier_list = [
                {
                    "identifier": id_obj.identifier,
                    "type": id_obj.identifier_type or "unknown",
                    "created_at": id_obj.created_at.isoformat() + "Z" if id_obj.created_at else None,
                }
                for id_obj in identifiers
            ]

            data = {
                "muxi_user_id": user.public_id,
                "internal_user_id": user.id,
                "identifiers": identifier_list,
                "count": len(identifier_list),
            }

            response = create_success_response(
                APIObjectType.USER_IDENTIFIER_LIST,
                APIEventType.USER_IDENTIFIERS_LIST,
                data,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to retrieve user identifiers: {str(e)}",
            data={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to retrieve user identifiers: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.delete("/users/identifiers/{identifier}", response_model=APIResponse)
async def delete_user_identifier(request: Request, identifier: str) -> JSONResponse:
    """
    Remove a specific identifier mapping from a user.

    Args:
        identifier: Identifier to remove (e.g., email, Slack ID, etc.)

    Returns:
        Success response with details
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get database manager
    db_manager = formation.get_db_manager()
    if not db_manager:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Database service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        from .....services.memory.long_term import UserIdentifier, User
        from sqlalchemy import select, delete

        async with db_manager.get_session() as session:
            # Find the identifier
            result = await session.execute(
                select(UserIdentifier).where(
                    UserIdentifier.identifier == identifier,
                    UserIdentifier.formation_id == formation.formation_id
                )
            )
            id_obj = result.scalar_one_or_none()

            if not id_obj:
                response = create_error_response(
                    "RESOURCE_NOT_FOUND",
                    f"Identifier '{identifier}' not found",
                    None,
                    request_id,
                )
                return JSONResponse(content=response.model_dump(), status_code=404)

            # Get user info before deletion
            user_id = id_obj.user_id
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            muxi_user_id = user.public_id if user else None

            # Delete the identifier
            await session.execute(
                delete(UserIdentifier).where(UserIdentifier.id == id_obj.id)
            )
            await session.commit()

            # Invalidate cache
            kv_cache = formation.get_kv_cache()
            if kv_cache:
                cache_key = f"user_id:{formation.formation_id}:{identifier}"
                await kv_cache.delete(cache_key)

            observability.observe(
                event_type=observability.SystemEvents.OPERATION_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"User identifier '{identifier}' removed",
                data={
                    "identifier": identifier,
                    "muxi_user_id": muxi_user_id,
                },
            )

            data = {
                "message": f"Identifier '{identifier}' removed successfully",
                "muxi_user_id": muxi_user_id,
            }

            response = create_success_response(
                APIObjectType.MESSAGE,
                APIEventType.USER_IDENTIFIER_DELETED,
                data,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to delete user identifier: {str(e)}",
            data={
                "identifier": identifier,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to delete identifier: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.get("/users/{identifier}", response_model=APIResponse)
async def resolve_identifier(request: Request, identifier: str) -> JSONResponse:
    """
    Look up which MUXI user an identifier belongs to.

    Args:
        identifier: Identifier to resolve

    Returns:
        MUXI user information
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    try:
        # Use the resolve_user_identifier utility
        db_manager = formation.get_db_manager()
        kv_cache = formation.get_kv_cache()

        if not db_manager:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Database service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Resolve identifier (this will create if not exists, but that's okay for resolution)
        internal_user_id, muxi_user_id = await resolve_user_identifier(
            identifier=identifier,
            formation_id=formation.formation_id,
            db_manager=db_manager,
            kv_cache=kv_cache,
        )

        data = {
            "identifier": identifier,
            "muxi_user_id": muxi_user_id,
            "internal_user_id": internal_user_id,
        }

        response = create_success_response(
            APIObjectType.USER,
            APIEventType.USER_RESOLVED,
            data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    except ValueError as e:
        # Invalid input
        response = create_error_response(
            "INVALID_REQUEST",
            str(e),
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to resolve identifier: {str(e)}",
            data={
                "identifier": identifier,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to resolve identifier: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)
