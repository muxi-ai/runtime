"""
Authentication utilities for the Formation server.

Provides dependency injection classes for validating API keys
in incoming requests.
"""

import secrets

from fastapi import HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_500_INTERNAL_SERVER_ERROR


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
                headers={"WWW-Authenticate": "ApiKey realm=\"admin\", header=\"X-Muxi-Admin-Key\""},
            )

        if not secrets.compare_digest(api_key, self.admin_key):
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Invalid admin API key. Please check your 'X-Muxi-Admin-Key' header value.",
                headers={"WWW-Authenticate": "ApiKey realm=\"admin\", header=\"X-Muxi-Admin-Key\""},
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
                headers={"WWW-Authenticate": "ApiKey realm=\"client\", header=\"X-Muxi-Client-Key\""},
            )

        if not secrets.compare_digest(api_key, self.client_key):
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Invalid client API key. Please check your 'X-Muxi-Client-Key' header value.",
                headers={"WWW-Authenticate": "ApiKey realm=\"client\", header=\"X-Muxi-Client-Key\""},
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
