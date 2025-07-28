"""
Authentication utilities for the Formation server.

Provides dependency injection classes for validating API keys
in incoming requests.
"""

import secrets
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader


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

    async def __call__(
        self,
        api_key: str = Security(APIKeyHeader(name="X-Admin-Key"))
    ) -> str:
        """
        Validate the admin API key.

        Args:
            api_key: The API key from the request header

        Returns:
            The validated API key

        Raises:
            HTTPException: If the API key is invalid
        """
        if not self.admin_key:
            raise HTTPException(
                status_code=500,
                detail="Admin API key not configured"
            )

        if not secrets.compare_digest(api_key, self.admin_key):
            raise HTTPException(
                status_code=403,
                detail="Invalid admin API key"
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

    async def __call__(
        self,
        api_key: str = Security(APIKeyHeader(name="X-Client-Key"))
    ) -> str:
        """
        Validate the client API key.

        Args:
            api_key: The API key from the request header

        Returns:
            The validated API key

        Raises:
            HTTPException: If the API key is invalid
        """
        if not self.client_key:
            raise HTTPException(
                status_code=500,
                detail="Client API key not configured"
            )

        if not secrets.compare_digest(api_key, self.client_key):
            raise HTTPException(
                status_code=403,
                detail="Invalid client API key"
            )

        return api_key


def get_user_id(
    user_id: Optional[str] = Security(APIKeyHeader(name="X-User-Id", auto_error=False))
) -> Optional[str]:
    """
    Extract user ID from request headers.

    This is an optional header used for multi-user scenarios.

    Args:
        user_id: The user ID from the request header

    Returns:
        The user ID if provided, None otherwise
    """
    return user_id
