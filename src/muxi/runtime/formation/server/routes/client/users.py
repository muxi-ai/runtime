"""
User identifier management endpoints.

These endpoints provide user identity mapping operations,
requiring client API key authentication.
"""

from datetime import timezone
from typing import Optional, List, Any, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType
from .....utils.user_resolution import resolve_user_identifier
from .....services import observability

router = APIRouter(tags=["Users"])


class AssociateIdentifiersRequest(BaseModel):
    """Request model for associating multiple identifiers to a user."""
    muxi_user_id: Optional[str] = Field(None, description="MUXI user ID to associate identifiers to. If not provided, creates a new user.")
    identifiers: List[Any] = Field(..., description="List of identifiers (strings, [id, type] arrays, or {identifier, type} objects)")


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

    # Get database manager from overlord
    overlord = getattr(formation, "_overlord", None)
    db_manager = getattr(overlord, "db_manager", None) if overlord else None
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
                    f"User not found: {user_id!r}",
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
                    "created_at": (
                        id_obj.created_at.astimezone(timezone.utc).isoformat()
                        if id_obj.created_at and id_obj.created_at.tzinfo
                        else id_obj.created_at.isoformat() + "Z" if id_obj.created_at
                        else None
                    ),
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
            description=f"Failed to retrieve user identifiers: {e!r}",
            data={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to retrieve user identifiers: {e!r}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.post("/users/identifiers", response_model=APIResponse)
async def associate_user_identifiers(request: Request, body: AssociateIdentifiersRequest) -> JSONResponse:
    """
    Associate multiple identifiers to a user.

    Links multiple external identifiers (email, Slack ID, Telegram handle, etc.)
    to a single MUXI user. Enables context and memory carryover across channels.

    Args:
        body: Request with muxi_user_id (optional) and identifiers list

    Returns:
        User info with all associated identifiers
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Get database manager from overlord
    overlord = getattr(formation, "_overlord", None)
    db_manager = getattr(overlord, "db_manager", None) if overlord else None
    if not db_manager:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Database service is not available",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        from .....services.memory.long_term import User, UserIdentifier
        from sqlalchemy import select
        import uuid

        async with db_manager.get_session() as session:
            user = None
            muxi_user_id = body.muxi_user_id

            # Find or create user
            if muxi_user_id:
                result = await session.execute(
                    select(User).where(User.public_id == muxi_user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    response = create_error_response(
                        "RESOURCE_NOT_FOUND",
                        f"User not found: {muxi_user_id!r}",
                        None,
                        request_id,
                    )
                    return JSONResponse(content=response.model_dump(), status_code=404)
            else:
                # Create new user
                new_public_id = f"usr_{uuid.uuid4().hex[:12]}"
                user = User(public_id=new_public_id)
                session.add(user)
                await session.flush()
                muxi_user_id = new_public_id

            # Parse and associate identifiers
            associated = []
            for item in body.identifiers:
                identifier = None
                identifier_type = None

                if isinstance(item, str):
                    identifier = item
                elif isinstance(item, list) and len(item) >= 2:
                    identifier = item[0]
                    identifier_type = item[1]
                elif isinstance(item, dict):
                    identifier = item.get("identifier")
                    identifier_type = item.get("type")

                if not identifier:
                    continue

                # Check if identifier already exists
                result = await session.execute(
                    select(UserIdentifier).where(
                        UserIdentifier.identifier == identifier,
                        UserIdentifier.formation_id == formation.formation_id
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    if existing.user_id != user.id:
                        # Update to point to new user
                        existing.user_id = user.id
                        if identifier_type:
                            existing.identifier_type = identifier_type
                else:
                    # Create new identifier mapping
                    new_identifier = UserIdentifier(
                        user_id=user.id,
                        identifier=identifier,
                        identifier_type=identifier_type,
                        formation_id=formation.formation_id,
                    )
                    session.add(new_identifier)

                associated.append({
                    "identifier": identifier,
                    "type": identifier_type or "unknown",
                })

                # Invalidate cache (KV cache not yet implemented)
                # kv_cache = None
                # if kv_cache:
                #     cache_key = f"user_id:{formation.formation_id}:{identifier}"
                #     await kv_cache.delete(cache_key)

            await session.commit()

            data = {
                "muxi_user_id": muxi_user_id,
                "identifiers": associated,
                "count": len(associated),
            }

            response = create_success_response(
                APIObjectType.USER_IDENTIFIER_LIST,
                APIEventType.USER_IDENTIFIERS_ASSOCIATED,
                data,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=200)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to associate user identifiers: {e!r}",
            data={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to associate identifiers: {e!r}",
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

    # Get database manager from overlord
    overlord = getattr(formation, "_overlord", None)
    db_manager = getattr(overlord, "db_manager", None) if overlord else None
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
                    f"Identifier {identifier!r} not found",
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

            # Invalidate cache (KV cache not yet implemented)
            # kv_cache = None
            # if kv_cache:
            #     cache_key = f"user_id:{formation.formation_id}:{identifier}"
            #     await kv_cache.delete(cache_key)

            observability.observe(
                event_type=observability.SystemEvents.OPERATION_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"User identifier {identifier!r} removed",
                data={
                    "identifier": identifier,
                    "muxi_user_id": muxi_user_id,
                },
            )

            data = {
                "message": f"Identifier {identifier!r} removed successfully",
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
            description=f"Failed to delete user identifier: {e!r}",
            data={
                "identifier": identifier,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to delete identifier: {e!r}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.get("/users/{identifier}", response_model=APIResponse)
async def lookup_identifier(request: Request, identifier: str) -> JSONResponse:
    """
    Look up which MUXI user an identifier belongs to (read-only, no creation).

    This endpoint follows proper HTTP GET semantics: it is safe and idempotent,
    with no side effects. If the identifier doesn't exist, returns 404.

    To resolve an identifier with automatic user creation, use POST /users/resolve.

    Args:
        identifier: Identifier to look up (email, Slack ID, etc.)

    Returns:
        MUXI user information if found, 404 if not found
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    try:
        # Get database manager from overlord
        overlord = getattr(formation, "_overlord", None)
        db_manager = getattr(overlord, "db_manager", None) if overlord else None
        kv_cache = None  # KV cache not yet implemented

        if not db_manager:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Database service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Lookup only (no creation)
        result = await resolve_user_identifier(
            identifier=identifier,
            formation_id=formation.formation_id,
            db_manager=db_manager,
            kv_cache=kv_cache,
            create_if_missing=False,
        )

        if result is None:
            # Identifier not found
            response = create_error_response(
                "RESOURCE_NOT_FOUND",
                f"Identifier not found: {identifier!r}",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=404)

        internal_user_id, muxi_user_id = result

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
            f"{e!r}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to lookup identifier: {e!r}",
            data={
                "identifier": identifier,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to lookup identifier: {e!r}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.post("/users/resolve", response_model=APIResponse)
async def resolve_identifier(request: Request) -> JSONResponse:
    """
    Resolve an identifier to a MUXI user (creates user if needed).

    This endpoint uses POST method since it has side effects (user creation).
    If the identifier doesn't exist, creates a new user and returns its details.

    Request body:
        {
            "identifier": "alice@email.com",
            "identifier_type": "email"  // optional
        }

    Args:
        identifier: Identifier to resolve (from request body)
        identifier_type: Optional type hint (email, slack, telegram, etc.)

    Returns:
        MUXI user information (creates user if identifier is new)
    """
    from pydantic import BaseModel, Field

    class ResolveRequest(BaseModel):
        identifier: str = Field(..., description="Identifier to resolve")
        identifier_type: Optional[str] = Field(None, description="Optional identifier type")

    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    try:
        # Parse request body
        body = await request.json()
        resolve_req = ResolveRequest(**body)

        # Get database manager from overlord
        overlord = getattr(formation, "_overlord", None)
        db_manager = getattr(overlord, "db_manager", None) if overlord else None
        kv_cache = None  # KV cache not yet implemented

        if not db_manager:
            response = create_error_response(
                "SERVICE_UNAVAILABLE",
                "Database service is not available",
                None,
                request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=503)

        # Resolve identifier with creation enabled
        result = await resolve_user_identifier(
            identifier=resolve_req.identifier,
            formation_id=formation.formation_id,
            db_manager=db_manager,
            kv_cache=kv_cache,
            identifier_type=resolve_req.identifier_type,
            create_if_missing=True,
        )

        # Should never be None with create_if_missing=True
        if result is None:
            raise ValueError("Unexpected None result from resolve_user_identifier")

        internal_user_id, muxi_user_id = result

        data = {
            "identifier": resolve_req.identifier,
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
            f"{e!r}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description=f"Failed to resolve identifier: {e!r}",
            data={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to resolve identifier: {e!r}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)
