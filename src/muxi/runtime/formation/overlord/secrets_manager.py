"""
Secrets management utilities for the Overlord.

This module handles secrets interpolation and management for formation configurations.
"""

from typing import Any, Dict, Optional

from muxi.runtime.datatypes import observability


class SecretsInterpolator:
    """
    Handles secrets interpolation for configuration values.

    This class provides utilities for interpolating GitHub Actions-style secrets
    references (${{ secrets.NAME }}) in configuration dictionaries.
    """

    def __init__(self, secrets_manager):
        """
        Initialize the secrets interpolator.

        Args:
            secrets_manager: The SecretsManager instance to use for secret retrieval
        """
        self.secrets_manager = secrets_manager

    async def interpolate_secrets(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpolate secrets in a configuration dictionary.

        Args:
            config: Configuration dictionary that may contain ${{ secrets.NAME }} references

        Returns:
            Dict[str, Any]: Configuration with secrets interpolated
        """
        if not self.secrets_manager:
            return config

        try:
            return await self.secrets_manager.interpolate_secrets(config)
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "interpolate",
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to interpolate secrets in configuration",
            )
            return config

    async def ensure_secrets_manager(self) -> bool:
        """
        Ensure the SecretsManager is initialized and ready to use.

        Returns:
            bool: True if SecretsManager is available, False otherwise
        """
        if not self.secrets_manager:
            return False

        try:
            await self.secrets_manager.initialize_encryption()
            return True
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "initialize_encryption",
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to initialize secrets manager encryption",
            )
            return False

    async def store_secret(self, name: str, value: str) -> bool:
        """
        Store a secret in the formation's secrets manager.

        Args:
            name: Name of the secret (will be normalized to uppercase)
            value: Secret value to store

        Returns:
            bool: True if successful, False otherwise
        """
        if not await self.ensure_secrets_manager():
            return False

        try:
            await self.secrets_manager.store_secret(name, value)
            return True
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "store",
                    "secret_name": name,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description=f"Failed to store secret '{name}'",
            )
            return False

    async def get_secret(self, name: str) -> Optional[str]:
        """
        Retrieve a secret from the formation's secrets manager.

        Args:
            name: Name of the secret to retrieve

        Returns:
            Optional[str]: Secret value if found, None otherwise
        """
        if not await self.ensure_secrets_manager():
            return None

        try:
            return await self.secrets_manager.get_secret(name)
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "retrieve",
                    "secret_name": name,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description=f"Failed to retrieve secret '{name}'",
            )
            return None

    async def list_secrets(self) -> list[str]:
        """
        List all secret names in the formation's secrets manager.

        Returns:
            List[str]: List of secret names
        """
        if not await self.ensure_secrets_manager():
            return []

        try:
            return await self.secrets_manager.list_secrets()
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_LISTING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to list secrets",
            )
            return []

    async def delete_secret(self, name: str) -> bool:
        """
        Delete a secret from the formation's secrets manager.

        Args:
            name: Name of the secret to delete

        Returns:
            bool: True if successful, False otherwise
        """
        if not await self.ensure_secrets_manager():
            return False

        try:
            await self.secrets_manager.delete_secret(name)
            return True
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "delete",
                    "secret_name": name,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description=f"Failed to delete secret '{name}'",
            )
            return False
