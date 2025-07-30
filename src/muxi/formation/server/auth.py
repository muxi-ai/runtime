"""
Authentication utilities for the Formation server.

Provides dependency injection classes for validating API keys
in incoming requests.
"""

import secrets

from fastapi import HTTPException, Request
from starlette.status import HTTP_403_FORBIDDEN, HTTP_500_INTERNAL_SERVER_ERROR


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

        # Look for the header case-insensitively
        api_key = None
        for header_name, header_value in request.headers.items():
            if header_name.lower() == "x-muxi-admin-key":
                api_key = header_value
                break

        if not api_key:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, 
                detail="A valid admin API key is required. Please provide the 'X-Muxi-Admin-Key' header."
            )

        if not secrets.compare_digest(api_key, self.admin_key):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, 
                detail="Invalid admin API key. Please check your 'X-Muxi-Admin-Key' header value."
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

        # Look for the header case-insensitively
        api_key = None
        for header_name, header_value in request.headers.items():
            if header_name.lower() == "x-muxi-client-key":
                api_key = header_value
                break

        if not api_key:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, 
                detail="A valid client API key is required. Please provide the 'X-Muxi-Client-Key' header."
            )

        if not secrets.compare_digest(api_key, self.client_key):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, 
                detail="Invalid client API key. Please check your 'X-Muxi-Client-Key' header value."
            )

        return api_key
