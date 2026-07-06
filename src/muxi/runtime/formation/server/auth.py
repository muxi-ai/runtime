"""
Authentication utilities for the Formation server.

Provides dependency injection classes for validating API keys
and formation user identities in incoming requests.
"""

import secrets

from fastapi import HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_500_INTERNAL_SERVER_ERROR

from ...services import observability


class AdminKeyAuth:
    """
    Admin API key authentication dependency.

    Validates that requests include the correct admin API key
    for formation management operations.
    """

    def __init__(self, admin_key: str):
        """
        Initialize admin auth with the expected key.

        Args:
            admin_key: The valid admin API key
        """
        self.admin_key = admin_key

    async def __call__(self, request: Request) -> str:
        """
        Validate the admin API key from case-insensitive header.

        Args:
            request: The FastAPI request object

        Returns:
            The validated API key

        Raises:
            HTTPException: If the API key is invalid or missing
        """
        if not self.admin_key:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="Admin API key not configured"
            )

        # FastAPI request.headers supports case-insensitive lookups
        api_key = request.headers.get("x-muxi-admin-key")

        if not api_key:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="A valid admin API key is required. Please provide the 'X-Muxi-Admin-Key' header.",
                headers={"WWW-Authenticate": 'ApiKey realm="admin", header="X-Muxi-Admin-Key"'},
            )

        if not secrets.compare_digest(api_key, self.admin_key):
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Invalid admin API key. Please check your 'X-Muxi-Admin-Key' header value.",
                headers={"WWW-Authenticate": 'ApiKey realm="admin", header="X-Muxi-Admin-Key"'},
            )

        return api_key


class ClientKeyAuth:
    """
    Client API key authentication dependency.

    Validates that requests include the correct client API key
    for user interaction operations.
    """

    def __init__(self, client_key: str):
        """
        Initialize client auth with the expected key.

        Args:
            client_key: The valid client API key
        """
        self.client_key = client_key

    async def __call__(self, request: Request) -> str:
        """
        Validate the client API key from case-insensitive header.

        Args:
            request: The FastAPI request object

        Returns:
            The validated API key

        Raises:
            HTTPException: If the API key is invalid or missing
        """
        if not self.client_key:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="Client API key not configured"
            )

        # FastAPI request.headers supports case-insensitive lookups
        api_key = request.headers.get("x-muxi-client-key")

        if not api_key:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="A valid client API key is required. Please provide the 'X-Muxi-Client-Key' header.",
                headers={"WWW-Authenticate": 'ApiKey realm="client", header="X-Muxi-Client-Key"'},
            )

        if not secrets.compare_digest(api_key, self.client_key):
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Invalid client API key. Please check your 'X-Muxi-Client-Key' header value.",
                headers={"WWW-Authenticate": 'ApiKey realm="client", header="X-Muxi-Client-Key"'},
            )

        return api_key


class DualKeyAuth:
    """
    Authentication dependency that accepts either Admin or Client API key.

    Sets request.state.auth_type to "admin" or "client" for downstream use.
    """

    def __init__(self, admin_key: str, client_key: str):
        """
        Initialize with both keys.

        Args:
            admin_key: The valid admin API key
            client_key: The valid client API key
        """
        self.admin_key = admin_key
        self.client_key = client_key

    async def __call__(self, request: Request) -> str:
        """
        Validate either admin or client API key.

        Sets request.state.auth_type to "admin" or "client".

        Returns:
            The validated API key

        Raises:
            HTTPException: If no valid API key is provided
        """
        # Try admin key first
        admin_api_key = request.headers.get("x-muxi-admin-key")
        if admin_api_key and self.admin_key:
            if secrets.compare_digest(admin_api_key, self.admin_key):
                request.state.auth_type = "admin"
                return admin_api_key

        # Try client key
        client_api_key = request.headers.get("x-muxi-client-key")
        if client_api_key and self.client_key:
            if secrets.compare_digest(client_api_key, self.client_key):
                request.state.auth_type = "client"
                return client_api_key

        # Neither key was valid
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="A valid API key is required. Provide either 'X-Muxi-Admin-Key' or 'X-Muxi-Client-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


class UserAuthGate:
    """
    Formation user auth gate dependency (server.auth: required).

    When the formation config sets ``server.auth: required``, the user
    identity carried by the request must resolve to a known user via the
    user_identifiers table for this formation; unknown users receive 401.
    With the default ``server.auth: open`` this dependency is a no-op.

    Runs after API key validation: the key authenticates the caller
    (application), this gate authorizes the end user it acts for.
    """

    # Endpoints whose deprecated JSON body ``user_id`` field participates in
    # identity resolution (mirrors the chat routes' header-then-body order).
    _BODY_FALLBACK_PATHS = frozenset({"/v1/chat", "/v1/audiochat"})

    async def __call__(self, request: Request) -> None:
        """
        Reject the request if auth is required and the user is unknown.

        Args:
            request: The FastAPI request object

        Raises:
            HTTPException: 401 if the user identity is not in the database,
                500 if auth is required but no database is configured
        """
        formation = getattr(request.app.state, "formation", None)
        if formation is None:
            return

        server_config = getattr(formation, "_server_config", None) or {}
        if server_config.get("auth", "open") != "required":
            return

        # Check the DB before resolving identity so a misconfigured
        # formation fails fast without consuming the request body
        db_manager = getattr(formation, "_db_manager", None)
        if db_manager is None:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail="server.auth is 'required' but no persistent database is configured",
            )

        identity = await self._resolve_identity(request)

        from ...utils.user_resolution import resolve_user_identifier

        resolved = await resolve_user_identifier(
            identifier=identity,
            formation_id=formation.formation_id,
            db_manager=db_manager,
            kv_cache=None,
            create_if_missing=False,
        )

        if resolved is None:
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "service": "formation_api_server",
                    "auth_gate": "user",
                    "auth_mode": "required",
                    "path": request.url.path,
                    "user_id": identity,
                    "formation_id": formation.formation_id,
                },
                description=f"Auth gate rejected unknown user {identity!r}",
            )
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail=(
                    f"Unknown user {identity!r}. This formation requires registered "
                    "users (server.auth: required)."
                ),
            )

    async def _resolve_identity(self, request: Request) -> str:
        """
        Resolve the user identity the way the gated routes do.

        Order: X-Muxi-User-Id header, then (chat endpoints only) the
        deprecated ``user_id`` body field, then the default user "0".
        """
        identity = request.headers.get("x-muxi-user-id")

        if not identity and request.url.path in self._BODY_FALLBACK_PATHS:
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                # Malformed body falls through to the default identity,
                # matching the gated routes' own parsing behavior.
                # Transport-level errors (client disconnect, upstream
                # middleware failures) propagate instead of silently
                # masquerading as user "0".
                body = None
            if isinstance(body, dict):
                body_user_id = body.get("user_id")
                if isinstance(body_user_id, str):
                    identity = body_user_id

        return identity or "0"
