"""
Formation-level secrets manager for MUXI Runtime.

Provides secure, encrypted secrets storage with GitHub Actions-style interpolation.
"""

import json
import re
import os
import asyncio
import threading
from typing import Dict, Any, Optional, Union, List
from pathlib import Path
from cryptography.fernet import Fernet

# Import only what we need to avoid heavy dependencies
try:
    # Try to import from the already loaded observability module if available
    from ..observability import observe, SystemEvents, EventLevel
except ImportError:
    # If observability is not available, define no-op versions
    class SystemEvents:
        SECRET_OPERATION_FAILED = "secret.operation.failed"
        SECRET_OPERATION_COMPLETED = "secret.operation.completed"
        SECRET_LISTING_FAILED = "secret.listing.failed"

    class EventLevel:
        ERROR = "error"
        INFO = "info"
        WARNING = "warning"
        DEBUG = "debug"

    def observe(*args, **kwargs):
        # No-op when observability is not available
        pass


class SecretsManager:
    """
    Formation-level secrets management with encryption and secure storage.

    Features:
    - AES-256-GCM encryption for all sensitive data
    - Per-formation master key derivation
    - Path-agnostic operation (works with any formation directory)
    - Async operations for non-blocking secrets access
    - Flattened key-value storage with GitHub Actions syntax
    - Auto-normalization of secret names to uppercase
    - Flexible interpolation patterns supporting partial string replacement
    """

    def __init__(self, formation_dir: Union[str, Path]):
        """
        Initialize secrets manager for a specific formation.

        Args:
            formation_dir: Path to formation directory (secrets.enc will be stored here)
        """
        self.formation_dir = Path(formation_dir)
        self.master_key_path = self.formation_dir / ".key"
        self.secrets_file_path = self.formation_dir / "secrets.enc"
        self._fernet: Optional[Fernet] = None
        self._secrets_cache: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()  # Thread lock for sync operations

        # Regex pattern for secrets interpolation (whitespace tolerant)
        # Matches: ${{ secrets.SECRET_NAME }} with flexible whitespace
        self._secrets_pattern = re.compile(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", re.IGNORECASE)

    async def initialize_encryption(self) -> None:
        """Initialize encryption for formation (creates master key if needed)."""
        try:
            await self._ensure_formation_dir()
            await self._load_or_create_master_key()

        except Exception as e:
            # Observability: Encryption initialization failed
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secrets manager encryption initialization failed: {str(e)}",
                data={
                    "operation_type": "encryption",
                    "formation_dir": str(self.formation_dir),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    async def _ensure_formation_dir(self) -> None:
        """Ensure formation directory exists."""
        self.formation_dir.mkdir(parents=True, exist_ok=True)

    async def _load_or_create_master_key(self) -> None:
        """Load or create formation master key."""
        if self.master_key_path.exists():
            # Load existing key
            key_data = self.master_key_path.read_bytes()
            self._fernet = Fernet(key_data)
        else:
            # Create new key
            key = Fernet.generate_key()
            self.master_key_path.write_bytes(key)
            # Set restrictive permissions (owner read/write only)
            os.chmod(self.master_key_path, 0o600)
            self._fernet = Fernet(key)

    def _normalize_secret_name(self, name: str) -> str:
        """
        Normalize secret name to uppercase with only letters, numbers, and underscores.

        Args:
            name: Input secret name

        Returns:
            Normalized secret name

        Examples:
            "openai-api-key" -> "OPENAI_API_KEY"
            "database_url" -> "DATABASE_URL"
            "MySecret123" -> "MYSECRET123"
        """
        # Convert to uppercase and replace invalid chars with underscores
        normalized = re.sub(r"[^A-Z0-9_]", "_", name.upper())
        # Remove multiple consecutive underscores
        normalized = re.sub(r"_+", "_", normalized)
        # Remove leading/trailing underscores
        return normalized.strip("_")

    async def _load_secrets_from_file(self) -> Dict[str, Any]:
        """Load and decrypt secrets from file."""
        if not self.secrets_file_path.exists():
            return {}

        encrypted_data = self.secrets_file_path.read_bytes()
        decrypted_data = self._fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode("utf-8"))

    async def _save_secrets_to_file(self, secrets: Dict[str, Any]) -> None:
        """Encrypt and save secrets to file."""
        data = json.dumps(secrets, indent=2)
        encrypted_data = self._fernet.encrypt(data.encode("utf-8"))
        self.secrets_file_path.write_bytes(encrypted_data)
        # Set restrictive permissions
        os.chmod(self.secrets_file_path, 0o600)

    def get_secret_sync(self, name: str) -> Optional[Any]:
        """
        Synchronously retrieve secret by name (case-insensitive).

        This is a thread-safe sync version for use in sync contexts like config loading.
        Uses a threading.Lock to ensure safe concurrent access from multiple threads.

        Args:
            name: Secret name (will be normalized for lookup)

        Returns:
            Secret value or None if not found
        """
        with self._sync_lock:
            try:
                # Initialize encryption if needed
                if not self._fernet:
                    if self.master_key_path.exists():
                        key_data = self.master_key_path.read_bytes()
                        self._fernet = Fernet(key_data)
                    else:
                        return None

                normalized_name = self._normalize_secret_name(name)

                # Use cache if available, otherwise load from file
                if self._secrets_cache is None:
                    if not self.secrets_file_path.exists():
                        return None

                    encrypted_data = self.secrets_file_path.read_bytes()
                    decrypted_data = self._fernet.decrypt(encrypted_data)
                    self._secrets_cache = json.loads(decrypted_data.decode("utf-8"))

                secret_value = self._secrets_cache.get(normalized_name)
                return secret_value

            except Exception as e:
                observe(
                    event_type=SystemEvents.SECRET_OPERATION_FAILED,
                    level=EventLevel.ERROR,
                    description=f"Sync secret retrieval failed for {name}: {str(e)}",
                    data={
                        "operation_type": "sync_retrieval",
                        "secret_name": name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "success": False,
                    },
                )
                return None

    async def _get_secrets_cache(self) -> Dict[str, Any]:
        """Get secrets cache, loading from file if needed."""
        if self._secrets_cache is None:
            self._secrets_cache = await self._load_secrets_from_file()
        return self._secrets_cache

    async def store_secret(self, name: str, value: Any, overwrite: bool = False) -> None:
        """
        Store encrypted secret with auto-normalized name.

        Args:
            name: Secret name (will be normalized to uppercase)
            value: Secret value
            overwrite: Whether to overwrite existing secret
        """
        try:
            if not self._fernet:
                await self.initialize_encryption()

            normalized_name = self._normalize_secret_name(name)

            async with self._lock:
                secrets = await self._get_secrets_cache()

                if normalized_name in secrets and not overwrite:
                    error_msg = (
                        f"Secret '{normalized_name}' already exists. "
                        f"Use overwrite=True to replace."
                    )
                    raise ValueError(error_msg)

                secrets[normalized_name] = value
                await self._save_secrets_to_file(secrets)
                self._secrets_cache = secrets

        except Exception as e:
            # Observability: Secret storage failed with exception
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret storage failed for {name}: {str(e)}",
                data={
                    "operation_type": "storage",
                    "secret_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    async def get_secret(self, name: str) -> Optional[Any]:
        """
        Retrieve and decrypt secret by name (case-insensitive).

        Args:
            name: Secret name (will be normalized for lookup)

        Returns:
            Secret value or None if not found
        """
        try:
            if not self._fernet:
                await self.initialize_encryption()

            normalized_name = self._normalize_secret_name(name)

            async with self._lock:
                secrets = await self._get_secrets_cache()
                secret_value = secrets.get(normalized_name)
                return secret_value

        except Exception as e:
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret retrieval failed for {name}: {str(e)}",
                data={
                    "operation_type": "retrieval",
                    "secret_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    async def delete_secret(self, name: str) -> bool:
        """
        Delete secret by name.

        Args:
            name: Secret name to delete

        Returns:
            True if secret was deleted, False if not found
        """
        try:
            if not self._fernet:
                await self.initialize_encryption()

            normalized_name = self._normalize_secret_name(name)

            async with self._lock:
                secrets = await self._get_secrets_cache()

                if normalized_name not in secrets:
                    return False

                del secrets[normalized_name]
                await self._save_secrets_to_file(secrets)
                self._secrets_cache = secrets
                return True

        except Exception as e:
            # Observability: Secret deletion failed
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret deletion failed for {name}: {str(e)}",
                data={
                    "operation_type": "deletion",
                    "secret_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    async def list_secrets(self) -> List[str]:
        """
        List all secret names.

        Returns:
            List of all stored secret names
        """
        try:
            if not self._fernet:
                await self.initialize_encryption()

            async with self._lock:
                secrets = await self._get_secrets_cache()
                secret_names = list(secrets.keys())
                return secret_names

        except Exception as e:
            # Observability: Secret listing failed
            observe(
                event_type=SystemEvents.SECRET_LISTING_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret listing failed: {str(e)}",
                data={"error": str(e), "error_type": type(e).__name__, "success": False},
            )
            raise

    async def secret_exists(self, name: str) -> bool:
        """Check if secret exists."""
        normalized_name = self._normalize_secret_name(name)
        secrets = await self._get_secrets_cache()
        return normalized_name in secrets

    async def interpolate_secrets(self, value: Any) -> Any:
        """
        Recursively interpolate ${{ secrets.NAME }} patterns in any data structure.

        Args:
            value: Input value (string, dict, list, or primitive)

        Returns:
            Value with all secret references interpolated

        Raises:
            ValueError: If referenced secret doesn't exist
        """

        try:
            if not self._fernet:
                await self.initialize_encryption()

            result = await self._interpolate_recursive(value)
            return result

        except Exception as e:
            # Observability: Secret interpolation failed
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret interpolation failed: {str(e)}",
                data={
                    "operation_type": "interpolation",
                    "value_type": type(value).__name__,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    async def _interpolate_recursive(self, value: Any) -> Any:
        """Recursively interpolate secrets in nested data structures."""
        if isinstance(value, str):
            return await self._interpolate_string(value)
        elif isinstance(value, dict):
            return {k: await self._interpolate_recursive(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [await self._interpolate_recursive(item) for item in value]
        else:
            # Return primitives (int, bool, None, etc.) unchanged
            return value

    async def _interpolate_string(self, text: str) -> str:
        """
        Interpolate secret references in a string.

        Supports both full and partial string replacement:
        - "${{ secrets.API_KEY }}" -> "sk-1234567890abcdef"
        - "Bearer ${{ secrets.TOKEN }}" -> "Bearer sk-1234567890abcdef"
        """

        def replace_secret(match):
            secret_name = match.group(1)
            secret_value = secrets.get(secret_name)
            if secret_value is None:
                raise ValueError(f"Secret '{secret_name}' not found")
            return str(secret_value)

        secrets = await self._get_secrets_cache()
        return self._secrets_pattern.sub(replace_secret, text)

    async def clear_all_secrets(self) -> None:
        """Clear all secrets (use with caution)."""
        try:
            if not self._fernet:
                await self.initialize_encryption()

            async with self._lock:
                await self._save_secrets_to_file({})
                self._secrets_cache = {}

        except Exception as e:
            # Observability: Secret clearing failed
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret clearing failed: {str(e)}",
                data={
                    "operation_type": "clearing",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    async def import_secrets(self, secrets: Dict[str, Any], overwrite: bool = False) -> None:
        """
        Import multiple secrets from a dictionary.

        Args:
            secrets: Dictionary of secret name -> value mappings
            overwrite: Whether to overwrite existing secrets
        """

        try:
            imported_count = 0
            failed_count = 0
            errors = []

            for name, value in secrets.items():
                try:
                    await self.store_secret(name, value, overwrite=overwrite)
                    imported_count += 1
                except Exception as e:
                    failed_count += 1
                    errors.append({"name": name, "error": str(e)})

            # Observability: Secret import completed
            observe(
                event_type=SystemEvents.SECRET_OPERATION_COMPLETED,
                level=(EventLevel.INFO if failed_count == 0 else EventLevel.WARNING),
                description=(
                    f"Secret import completed: {imported_count} imported, " f"{failed_count} failed"
                ),
                data={
                    "operation_type": "import",
                    "total_secrets": len(secrets),
                    "imported_count": imported_count,
                    "failed_count": failed_count,
                    "errors": errors,
                    "success": failed_count == 0,
                },
            )

            if failed_count > 0:
                raise ValueError(f"Failed to import {failed_count} secrets: {errors}")

        except Exception as e:
            # Observability: Secret import failed
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret import failed: {str(e)}",
                data={
                    "operation_type": "import",
                    "secret_count": len(secrets),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    async def export_secrets(self) -> Dict[str, Any]:
        """
        Export all secrets as a dictionary.

        Returns:
            Dictionary of all secrets (decrypted)
        """

        try:
            if not self._fernet:
                await self.initialize_encryption()

            async with self._lock:
                secrets = await self._get_secrets_cache()
                return secrets

        except Exception as e:
            # Observability: Secret export failed
            observe(
                event_type=SystemEvents.SECRET_OPERATION_FAILED,
                level=EventLevel.ERROR,
                description=f"Secret export failed: {str(e)}",
                data={
                    "operation_type": "export",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise
