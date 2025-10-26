"""
User Identifier Resolution Utilities

This module provides utility functions for resolving external user identifiers
to internal MUXI user IDs. It enables multi-identity support, allowing multiple
external identifiers (email, Slack ID, Telegram handle, etc.) to map to a single
MUXI user.

Key Functions:
- resolve_user_identifier: Resolve any identifier to (internal_user_id, muxi_user_id)
- associate_user_identifiers: Associate multiple identifiers to a single user

This is a simple utility module with stateless functions - no service class needed.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..services.memory.long_term import User, UserIdentifier
from ..services import observability
from ..utils.id_generator import get_default_nanoid


async def resolve_user_identifier(
    identifier: str,
    formation_id: str,
    db_manager,
    kv_cache,
    identifier_type: Optional[str] = None,
    create_if_missing: bool = True,
) -> Optional[Tuple[int, str]]:
    """
    Resolve any external identifier to (internal_user_id, muxi_user_id).

    This function provides fast identifier resolution with KV caching. It first
    checks the cache, then queries the database if needed. If the identifier
    doesn't exist, behavior depends on create_if_missing parameter.

    Args:
        identifier: Developer-provided ID (email, Slack ID, etc.)
        formation_id: Formation ID for multi-formation isolation
        db_manager: Database manager instance
        kv_cache: KV cache instance for fast lookups
        identifier_type: Optional type hint for new users ('email', 'slack', etc.)
        create_if_missing: If True, creates new user when identifier not found.
                          If False, returns None when identifier not found.
                          Default: True (for backward compatibility)

    Returns:
        Tuple of (internal_user_id: int, muxi_user_id: str) if found/created
        None if not found and create_if_missing=False
        Example: (123, "usr_abc123")

    Raises:
        ValueError: If identifier or formation_id is not a non-empty string

    Example:
        >>> # Resolve with creation (default behavior)
        >>> internal_id, muxi_id = await resolve_user_identifier(
        ...     identifier="alice@email.com",
        ...     formation_id="form_123",
        ...     db_manager=db,
        ...     kv_cache=kv
        ... )
        >>> print(f"Internal: {internal_id}, MUXI: {muxi_id}")
        Internal: 123, MUXI: usr_abc123
        >>>
        >>> # Lookup only (no creation)
        >>> result = await resolve_user_identifier(
        ...     identifier="unknown@email.com",
        ...     formation_id="form_123",
        ...     db_manager=db,
        ...     kv_cache=kv,
        ...     create_if_missing=False
        ... )
        >>> print(result)  # None if not found
        None
    """
    # Input validation - fail fast with clear errors
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError(
            f"identifier must be a non-empty string, got: {type(identifier).__name__} = {repr(identifier)}"
        )
    if not isinstance(formation_id, str) or not formation_id.strip():
        raise ValueError(
            f"formation_id must be a non-empty string, got: {type(formation_id).__name__} = {repr(formation_id)}"
        )

    cache_key = f"user_id:{formation_id}:{identifier}"

    # Step 1: Check cache (if available)
    if kv_cache is not None:
        if cached_value := await kv_cache.get(cache_key):
            try:
                internal_id_str, muxi_id = cached_value.split(":", 1)
                observability.observe(
                    event_type=observability.SystemEvents.OPERATION_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "cache_type": "user_identifier",
                        "cache_key": cache_key,
                        "identifier": identifier,
                        "formation_id": formation_id,
                    },
                    description=f"User identifier resolved from cache: {identifier}",
                )
                return (int(internal_id_str), muxi_id)
            except (ValueError, AttributeError) as e:
                # Corrupted cache entry - invalidate it
                observability.observe(
                    event_type=observability.ErrorEvents.VALIDATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "message": "Corrupted cache entry for user identifier",
                        "cache_key": cache_key,
                        "error": str(e),
                    },
                    description=f"Corrupted cache entry for user identifier {identifier}: {str(e)}",
                )
                await kv_cache.delete(cache_key)

    # Step 2: Database lookup
    observability.observe(
        event_type=observability.SystemEvents.OPERATION_COMPLETED,
        level=observability.EventLevel.DEBUG,
        data={
            "cache_type": "user_identifier",
            "cache_key": cache_key,
            "identifier": identifier,
            "formation_id": formation_id,
        },
        description=f"User identifier cache miss, querying database: {identifier}",
    )

    async with db_manager.get_async_session() as session:
        # Query user_identifiers table with JOIN to users
        result = await session.execute(
            select(User.id, User.public_id)
            .join(UserIdentifier, User.id == UserIdentifier.user_id)
            .where(
                UserIdentifier.identifier == identifier,
                UserIdentifier.formation_id == formation_id,
            )
        )

        row = result.first()
        if row:
            # Found existing user
            internal_id, muxi_id = row
            observability.observe(
                event_type=observability.SystemEvents.USER_RESOLVED,
                level=observability.EventLevel.DEBUG,
                data={
                    "operation": "user_identifier_resolved",
                    "identifier": identifier,
                    "muxi_user_id": muxi_id,
                    "internal_user_id": internal_id,
                    "source": "database",
                    "formation_id": formation_id,
                },
                description=f"Resolved user identifier {identifier!r} to {muxi_id} (internal ID: {internal_id})",
            )
        elif create_if_missing:
            # Create new user + identifier
            new_user = await User.create(
                session,
                public_id=get_default_nanoid(),
                formation_id=formation_id,
            )

            await UserIdentifier.create(
                session,
                user_id=new_user.id,
                identifier=identifier,
                identifier_type=identifier_type,
                formation_id=formation_id,
            )

            await session.commit()
            internal_id, muxi_id = new_user.id, new_user.public_id

            observability.observe(
                event_type=observability.SystemEvents.USER_CREATED,
                level=observability.EventLevel.DEBUG,
                data={
                    "operation": "user_identifier_resolved",
                    "identifier": identifier,
                    "muxi_user_id": muxi_id,
                    "internal_user_id": internal_id,
                    "source": "created",
                    "formation_id": formation_id,
                    "identifier_type": identifier_type,
                },
                description=f"User resolution: Resolved identifier {identifier!r} to muxi_user_id={muxi_id}",
            )
        else:
            # Not found and create_if_missing=False
            observability.observe(
                event_type=observability.SystemEvents.USER_RESOLVED,
                level=observability.EventLevel.DEBUG,
                data={
                    "operation": "user_identifier_lookup",
                    "identifier": identifier,
                    "source": "not_found",
                    "formation_id": formation_id,
                },
                description=f"User identifier {identifier!r} not found (lookup only, no creation)",
            )
            return None

    # Step 3: Cache result (1 hour TTL) - if cache available
    if kv_cache is not None:
        await kv_cache.set(cache_key, f"{internal_id}:{muxi_id}", ttl=3600)

    return (internal_id, muxi_id)


async def associate_user_identifiers(
    identifiers: List[Union[str, Tuple[str, str], Dict[str, str]]],
    muxi_user_id: Optional[str],
    formation_id: str,
    db_manager,
    kv_cache,
) -> Dict[str, Any]:
    """
    Associate multiple identifiers to the same MUXI user.

    This function allows linking multiple external identifiers (email, Slack ID,
    Telegram handle, etc.) to a single MUXI user. It supports flexible input
    formats and handles conflict detection.

    Args:
        identifiers: List of identifiers in various formats:
            - Strings: ["alice@email.com", "U12345"]
            - Tuples: [("alice@email.com", "email"), ("U12345", "slack")]
            - Dicts: [{"identifier": "alice@email.com", "type": "email"}]
        muxi_user_id: MUXI user ID (public_id) to associate identifiers to.
                      If None, creates a new user.
        formation_id: Formation ID for multi-formation isolation
        db_manager: Database manager instance
        kv_cache: KV cache instance for invalidation

    Returns:
        Dictionary with results:
        {
            "muxi_user_id": "usr_abc123",
            "internal_user_id": 123,
            "identifiers_associated": 3,
            "new_identifiers": ["U12345", "@alice_tg"],
            "existing_identifiers": ["alice@email.com"],
            "conflicts": []
        }

    Raises:
        ValueError: If muxi_user_id not found or input format invalid
        IntegrityError: If identifier already linked to different user

    Example:
        >>> result = await associate_user_identifiers(
        ...     identifiers=[
        ...         "alice@email.com",
        ...         {"identifier": "U12345", "type": "slack"},
        ...         ("@alice_tg", "telegram")
        ...     ],
        ...     muxi_user_id="usr_abc123",
        ...     formation_id="form_123",
        ...     db_manager=db,
        ...     kv_cache=kv
        ... )
        >>> print(result)
        {
            "muxi_user_id": "usr_abc123",
            "identifiers_associated": 3,
            "new_identifiers": ["U12345", "@alice_tg"],
            "existing_identifiers": ["alice@email.com"]
        }
    """
    if not identifiers:
        raise ValueError("At least one identifier must be provided")

    # Normalize identifiers to list of (identifier, type) tuples
    normalized_identifiers: List[Tuple[str, Optional[str]]] = []
    for item in identifiers:
        if isinstance(item, str):
            normalized_identifiers.append((item, None))
        elif isinstance(item, tuple) and len(item) == 2:
            normalized_identifiers.append((item[0], item[1]))
        elif isinstance(item, dict):
            if "identifier" not in item:
                raise ValueError(f"Dict format must have 'identifier' key: {item}")
            normalized_identifiers.append((item["identifier"], item.get("type")))
        else:
            raise ValueError(f"Invalid identifier format: {item}")

    async with db_manager.get_async_session() as session:
        # Step 1: Get or create user
        if muxi_user_id:
            # Find existing user by public_id
            result = await session.execute(
                select(User).where(User.public_id == muxi_user_id, User.formation_id == formation_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError(f"User not found: {muxi_user_id}")
        else:
            # Create new user
            user = await User.create(
                session,
                public_id=get_default_nanoid(),
                formation_id=formation_id,
            )
            await session.commit()

        # Capture user attributes before they expire
        user_id = user.id
        user_public_id = user.public_id

        # Step 2: Check for conflicts
        conflicts = []
        for identifier, _ in normalized_identifiers:
            result = await session.execute(
                select(UserIdentifier.user_id)
                .where(
                    UserIdentifier.identifier == identifier,
                    UserIdentifier.formation_id == formation_id,
                )
            )
            existing_user_id = result.scalar_one_or_none()
            if existing_user_id and existing_user_id != user_id:
                conflicts.append(
                    {
                        "identifier": identifier,
                        "reason": f"Already linked to different user (ID: {existing_user_id})",
                    }
                )

        if conflicts:
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "message": "Identifier conflicts detected",
                    "muxi_user_id": user_public_id,
                    "conflicts": conflicts,
                    "formation_id": formation_id,
                },
                description=f"Cannot associate identifiers to {user_public_id}: {len(conflicts)} conflict(s) detected",
            )
            raise IntegrityError(
                f"Identifier conflicts detected: {conflicts}",
                params=None,
                orig=None,
            )

        # Step 3: Associate identifiers
        new_identifiers = []
        existing_identifiers = []

        for identifier, identifier_type in normalized_identifiers:
            try:
                # Try to create new identifier
                await UserIdentifier.create(
                    session,
                    user_id=user_id,
                    identifier=identifier,
                    identifier_type=identifier_type,
                    formation_id=formation_id,
                )

                # Commit immediately to preserve this success even if later ones fail
                await session.commit()

                # Track successful creation
                new_identifiers.append(identifier)

                # Invalidate cache for this identifier
                if kv_cache is not None:
                    cache_key = f"user_id:{formation_id}:{identifier}"
                    await kv_cache.delete(cache_key)

            except IntegrityError:
                # Identifier already exists - rollback only this failed statement
                # Previous successful creates are already committed
                await session.rollback()
                existing_identifiers.append(identifier)

        # Step 4: Log event
        observability.observe(
            event_type=observability.SystemEvents.USER_IDENTIFIERS_ASSOCIATED,
            level=observability.EventLevel.DEBUG,
            data={
                "muxi_user_id": user_public_id,
                "internal_user_id": user_id,
                "identifiers_associated": len(new_identifiers),
                "new_identifiers": new_identifiers,
                "existing_identifiers": existing_identifiers,
                "formation_id": formation_id,
            },
            description=(
                f"User resolution: Created new user "
                f"(muxi_user_id={user_public_id}, identifier='{identifier}')"
            ),
        )

        return {
            "muxi_user_id": user_public_id,
            "internal_user_id": user_id,
            "identifiers_associated": len(new_identifiers),
            "new_identifiers": new_identifiers,
            "existing_identifiers": existing_identifiers,
            "conflicts": [],
        }
