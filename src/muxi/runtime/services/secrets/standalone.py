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

    async def delete_secret(self, name: str) -> bool:
        """Delete secret by name."""
        if not self._fernet:
            await self.initialize_encryption()

        normalized_name = self._normalize_secret_name(name)

        async with self._lock:
            secrets = await self._load_secrets_from_file()

            if normalized_name not in secrets:
                return False

            del secrets[normalized_name]
            await self._save_secrets_to_file(secrets)
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
