#!/usr/bin/env python3
"""
Fast List Secrets - Minimal implementation without heavy imports
"""

import json
import asyncio
from pathlib import Path
from cryptography.fernet import Fernet


class MinimalSecretsManager:
    """Minimal secrets manager without observability dependencies."""

    def __init__(self, formation_dir: Path):
        self.formation_dir = Path(formation_dir)
        self.master_key_path = self.formation_dir / ".key"
        self.secrets_file_path = self.formation_dir / "secrets.enc"
        self._fernet = None

    async def initialize_encryption(self):
        """Initialize encryption."""
        if self.master_key_path.exists():
            key_data = self.master_key_path.read_bytes()
            self._fernet = Fernet(key_data)
        else:
            raise ValueError("No master key found")

    async def list_secrets(self):
        """List all secret names."""
        if not self._fernet:
            await self.initialize_encryption()

        if not self.secrets_file_path.exists():
            return []

        encrypted_data = self.secrets_file_path.read_bytes()
        decrypted_data = self._fernet.decrypt(encrypted_data)
        secrets = json.loads(decrypted_data.decode("utf-8"))
        return list(secrets.keys())


async def main():
    """List secrets in current directory."""
    try:
        secrets_manager = MinimalSecretsManager(".")
        await secrets_manager.initialize_encryption()
        secrets = await secrets_manager.list_secrets()

        if secrets:
            for secret in sorted(secrets):
                print(secret)

        print(f"\nTotal: {len(secrets)} secret(s)")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
