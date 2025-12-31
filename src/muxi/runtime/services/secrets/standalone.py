"""
Standalone secrets manager without heavy dependencies.

This module provides a lightweight version of SecretsManager that can be imported
quickly without triggering the heavy import chain (formation, ML libraries, etc).
"""

import json
import re
import os
import asyncio
import threading
from typing import Dict, Any, Optional, Union, List
from pathlib import Path
from cryptography.fernet import Fernet


class SecretsManager:
    """
    Formation-level secrets management with encryption and secure storage.

    This is a standalone version without observability dependencies for fast imports.
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
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

        # Regex pattern for secrets interpolation
        self._secrets_pattern = re.compile(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", re.IGNORECASE)

    async def initialize_encryption(self) -> None:
        """Initialize encryption for formation (creates master key if needed)."""
        await self._ensure_formation_dir()
        await self._load_or_create_master_key()

    async def _ensure_formation_dir(self) -> None:
        """Ensure formation directory exists."""
        self.formation_dir.mkdir(parents=True, exist_ok=True)

    async def _load_or_create_master_key(self) -> None:
        """Load or create formation master key."""
        if self.master_key_path.exists():
            key_data = self.master_key_path.read_bytes()
            self._fernet = Fernet(key_data)
        else:
            key = Fernet.generate_key()
            self.master_key_path.write_bytes(key)
            os.chmod(self.master_key_path, 0o600)
            self._fernet = Fernet(key)

    def _normalize_secret_name(self, name: str) -> str:
        """Normalize secret name to uppercase."""
        normalized = re.sub(r"[^A-Z0-9_]", "_", name.upper())
        normalized = re.sub(r"_+", "_", normalized)
        return normalized.strip("_")

    def _initialize_fernet_sync(self) -> bool:
        """
        Initialize Fernet encryption synchronously.

        This is a synchronous version of the encryption initialization
        used by sync methods like get_secret_sync.

        Returns:
            True if initialization was successful, False otherwise.
        """
        if self._fernet:
            return True

        if not self.master_key_path.exists():
            return False

        try:
            key_data = self.master_key_path.read_bytes()
            self._fernet = Fernet(key_data)
            return True
        except Exception:
            return False

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
        os.chmod(self.secrets_file_path, 0o600)

    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        if not self._fernet:
            await self.initialize_encryption()

        async with self._lock:
            secrets = await self._load_secrets_from_file()
            return list(secrets.keys())

    async def get_secret(self, name: str) -> Optional[Any]:
        """Retrieve and decrypt secret by name."""
        if not self._fernet:
            await self.initialize_encryption()

        normalized_name = self._normalize_secret_name(name)

        async with self._lock:
            secrets = await self._load_secrets_from_file()
            return secrets.get(normalized_name)

    async def store_secret(self, name: str, value: Any, overwrite: bool = False) -> None:
        """Store encrypted secret."""
        if not self._fernet:
            await self.initialize_encryption()

        normalized_name = self._normalize_secret_name(name)

        async with self._lock:
            secrets = await self._load_secrets_from_file()

            if normalized_name in secrets and not overwrite:
                raise ValueError(f"Secret '{normalized_name}' already exists")

            secrets[normalized_name] = value
            await self._save_secrets_to_file(secrets)
            self._secrets_cache = secrets  # Update cache

            # Update secrets file
            self._update_secrets_example(normalized_name)

    async def delete_secret(self, name: str, force: bool = False) -> bool:
        """
        Delete secret by name.

        By default, prevents deletion of secrets that are in use in formation YAML files.

        Args:
            name: Secret name to delete
            force: If True, skip usage check and delete anyway (default: False)

        Returns:
            True if secret was deleted, False if not found

        Raises:
            ValueError: If secret is in use and force=False
        """
        if not self._fernet:
            await self.initialize_encryption()

        normalized_name = self._normalize_secret_name(name)

        async with self._lock:
            secrets = await self._load_secrets_from_file()

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
            self._secrets_cache = secrets  # Update cache

            # Remove from secrets file
            self._remove_from_secrets_example(normalized_name)

            return True

    def get_secret_sync(self, name: str) -> Optional[Any]:
        """Synchronously retrieve secret by name."""
        with self._sync_lock:
            if not self._initialize_fernet_sync():
                return None

            normalized_name = self._normalize_secret_name(name)

            if not self.secrets_file_path.exists():
                return None

            encrypted_data = self.secrets_file_path.read_bytes()
            decrypted_data = self._fernet.decrypt(encrypted_data)
            secrets = json.loads(decrypted_data.decode("utf-8"))

            return secrets.get(normalized_name)

    def _update_secrets_example(self, secret_name: str) -> None:
        """Update secrets file with ALL keys from secrets.enc."""
        # Get ALL keys from the secrets cache (which was just updated)
        if self._secrets_cache is None:
            return

        all_keys = sorted(self._secrets_cache.keys())

        # Write all keys in ENV format (KEY=)
        lines = [f"{key}=" for key in all_keys]
        self.secrets_example_path.write_text('\n'.join(lines) + '\n')

    def _remove_from_secrets_example(self, secret_name: str) -> None:
        """Update secrets file with ALL remaining keys from secrets.enc."""
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
