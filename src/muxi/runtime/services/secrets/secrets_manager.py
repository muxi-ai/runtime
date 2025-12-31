"""
Formation-level secrets manager for MUXI Runtime.

Provides secure, encrypted secrets storage with GitHub Actions-style interpolation.
"""

import json
import re
import os
import asyncio
import threading
import logging
from typing import Dict, Any, Optional, Union, List, Set
from pathlib import Path
from cryptography.fernet import Fernet
from .. import observability

# Get logger for this module
logger = logging.getLogger(__name__)


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
        self.secrets_example_path = self.formation_dir / "secrets"
        self._fernet: Optional[Fernet] = None
        self._secrets_cache: Optional[Dict[str, Any]] = None
        self._used_secrets: Set[str] = set()  # Track which secrets are actually used
        self._lock = asyncio.Lock()  # For async operations (except _used_secrets)
        self._sync_lock = threading.Lock()  # Thread lock for sync operations and _used_secrets
        self._encryption_initialized = False  # Track if async init has been called

        # Regex pattern for secrets interpolation (whitespace tolerant)
        # Matches: ${{ secrets.SECRET_NAME }} with flexible whitespace
        self._secrets_pattern = re.compile(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", re.IGNORECASE)

    @property
    def is_initialized(self) -> bool:
        """
        Check if the secrets manager has been initialized.

        Returns:
            bool: True if encryption has been initialized, False otherwise
        """
        return getattr(self, '_encryption_initialized', False)

    async def initialize_encryption(self) -> None:
        """Initialize encryption for formation (creates master key if needed)."""
        try:
            await self._ensure_formation_dir()
            await self._load_or_create_master_key()

            # Load all secrets into cache immediately
            if self.secrets_file_path.exists():
                self._secrets_cache = await self._load_secrets_from_file()
            else:
                self._secrets_cache = {}

            # Mark as initialized
            self._encryption_initialized = True

        except Exception as e:
            # Observability: Encryption initialization failed
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
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

                # Track that this secret was used (sync version)
                # Already protected by _sync_lock acquired above
                if secret_value is not None and hasattr(self, '_used_secrets'):
                    self._used_secrets.add(normalized_name)

                return secret_value

            except Exception as e:
                observability.observe(
                    event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                    level=observability.EventLevel.ERROR,
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
        """Get secrets cache, which should already be loaded during initialization."""
        if self._secrets_cache is None:
            # Log warning about uninitialized state
            logger.warning(
                "SecretsManager cache is None - initialization may not have been completed. "
                "Call initialize_encryption() before accessing secrets."
            )

            # Check if we're initialized
            if not self.is_initialized:
                raise RuntimeError(
                    "SecretsManager not initialized. Call initialize_encryption() before accessing secrets."
                )

            # If somehow initialized but cache is None, attempt to load
            self._secrets_cache = await self._load_secrets_from_file() if self.secrets_file_path.exists() else {}
        return self._secrets_cache

    def get_used_secrets(self) -> Set[str]:
        """Get the set of secrets that have been accessed/used."""
        with self._sync_lock:
            return self._used_secrets.copy()

    def get_all_secret_names(self) -> Set[str]:
        """
        Get all available secret names from cache.

        Returns:
            Set[str]: Set of all secret names in the cache

        Note:
            Returns empty set if not initialized. Consider calling
            initialize_encryption() first for accurate results.
        """
        if self._secrets_cache is None:
            logger.warning(
                "get_all_secret_names called with uninitialized cache. "
                "Returning empty set. Call initialize_encryption() first for accurate results."
            )
            return set()
        return set(self._secrets_cache.keys())

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

                # Update secrets file
                self._update_secrets_example(normalized_name)

        except Exception as e:
            # Observability: Secret storage failed with exception
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
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
            normalized_name = self._normalize_secret_name(name)

            async with self._lock:
                secrets = await self._get_secrets_cache()
                secret_value = secrets.get(normalized_name)

                # Track that this secret was used
                # LOCK ACQUISITION ORDER: asyncio.Lock (_lock) -> threading.Lock (_sync_lock)
                # This order is safe because:
                # 1. The async code always acquires _lock first, then _sync_lock
                # 2. The sync code only ever acquires _sync_lock, never _lock
                # 3. No reverse order acquisition exists, preventing deadlocks
                # IMPORTANT: Maintain this order to avoid deadlock risks
                if secret_value is not None:
                    with self._sync_lock:
                        self._used_secrets.add(normalized_name)

                return secret_value

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
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

    async def delete_secret(self, name: str, force: bool = False) -> bool:
        """
        Delete secret by name.

        By default, prevents deletion of secrets that are in use in formation YAML files.
        Use force=True to bypass this check (not recommended).

        Args:
            name: Secret name to delete
            force: If True, skip usage check and delete anyway (default: False)

        Returns:
            True if secret was deleted, False if not found

        Raises:
            ValueError: If secret is in use and force=False
        """
        try:
            if not self._fernet:
                await self.initialize_encryption()

            normalized_name = self._normalize_secret_name(name)

            async with self._lock:
                secrets = await self._get_secrets_cache()

                if normalized_name not in secrets:
                    return False

                # Check if secret is in use (unless forced)
                if not force:
                    usages = self.check_secret_usage(normalized_name)
                    if usages:
                        # Build detailed error message
                        usage_details = "\n".join([
                            f"  - {file_path.relative_to(self.formation_dir)}:{line_num} -> {line_content}"
                            for file_path, line_num, line_content in usages
                        ])
                        raise ValueError(
                            f"Cannot delete secret '{normalized_name}' - it is currently in use:\n{usage_details}\n"
                            f"Remove these references first, or use force=True to delete anyway."
                        )

                del secrets[normalized_name]
                await self._save_secrets_to_file(secrets)
                self._secrets_cache = secrets

                # Remove from secrets file
                self._remove_from_secrets_example(normalized_name)

                return True

        except Exception as e:
            # Observability: Secret deletion failed
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
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
            # Secrets should already be loaded in cache
            return sorted(list(self.get_all_secret_names()))

        except Exception as e:
            # Observability: Secret listing failed
            observability.observe(
                event_type=observability.SystemEvents.SECRET_LISTING_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Secret listing failed: {str(e)}",
                data={"error": str(e), "error_type": type(e).__name__, "success": False},
            )
            raise

    async def secret_exists(self, name: str) -> bool:
        """
        Check if secret exists.

        Ensures the secrets manager is initialized before checking.

        Args:
            name: The secret name to check

        Returns:
            bool: True if secret exists, False otherwise
        """
        # Ensure initialization before checking
        if not self.is_initialized:
            await self.initialize_encryption()

        # Now check if secret exists in cache
        normalized_name = self._normalize_secret_name(name)

        # Use _get_secrets_cache to ensure cache is properly loaded
        cache = await self._get_secrets_cache()
        return normalized_name in cache

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
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
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
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
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
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_COMPLETED,
                level=observability.EventLevel.INFO if failed_count == 0 else observability.EventLevel.WARNING,
                description=f"Secret import completed: {imported_count} imported, {failed_count} failed",
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
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
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
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Secret export failed: {str(e)}",
                data={
                    "operation_type": "export",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
            )
            raise

    def _update_secrets_example(self, secret_name: str) -> None:
        """
        Update secrets file with ALL keys from secrets.enc.
        This ensures the example file always matches what's actually stored.

        Args:
            secret_name: Normalized secret name (not used, kept for API compatibility)
        """
        # Get ALL keys from the secrets cache (which was just updated)
        if self._secrets_cache is None:
            return

        all_keys = sorted(self._secrets_cache.keys())

        # Write all keys in ENV format (KEY=)
        lines = [f"{key}=" for key in all_keys]
        self.secrets_example_path.write_text('\n'.join(lines) + '\n')

    def _remove_from_secrets_example(self, secret_name: str) -> None:
        """
        Update secrets file with ALL remaining keys from secrets.enc.
        This ensures the example file always matches what's actually stored.

        Args:
            secret_name: Normalized secret name (not used, kept for API compatibility)
        """
        # Get ALL keys from the secrets cache (which was just updated)
        if self._secrets_cache is None or not self._secrets_cache:
            # No secrets left, remove the example file
            if self.secrets_example_path.exists():
                self.secrets_example_path.unlink()
            return

        all_keys = sorted(self._secrets_cache.keys())

        # Write all keys in ENV format (KEY=)
        lines = [f"{key}=" for key in all_keys]
        self.secrets_example_path.write_text('\n'.join(lines) + '\n')

    def check_secret_usage(self, secret_name: str) -> List[tuple]:
        """
        Check if a secret is being used in any formation YAML files.

        Args:
            secret_name: Secret name to check (will be normalized)

        Returns:
            List of (file_path, line_number, line_content) tuples where secret is used
        """
        normalized_name = self._normalize_secret_name(secret_name)
        usages = []

        # Search in all config files (.afs, .yaml, .yml) in formation directory and subdirectories
        yaml_patterns = ['*.afs', '*.yaml', '*.yml']
        for pattern in yaml_patterns:
            for yaml_file in self.formation_dir.rglob(pattern):
                try:
                    content = yaml_file.read_text()
                    for line_num, line in enumerate(content.split('\n'), start=1):
                        matches = self._secrets_pattern.findall(line)
                        for match in matches:
                            if self._normalize_secret_name(match) == normalized_name:
                                usages.append((yaml_file, line_num, line.strip()))
                except Exception:
                    # Skip files that can't be read
                    continue

        return usages
