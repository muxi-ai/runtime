#!/usr/bin/env python3
"""
Fast List Secrets - Minimal implementation without heavy imports
"""

import asyncio
import json
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

            # Validate Fernet key format
            # Fernet keys must be 32 bytes (url-safe base64 encoded to 44 chars)
            try:
                # Strip any whitespace that might have been added
                key_data = key_data.strip()

                # Check if it's the correct length for a base64-encoded Fernet key
                if len(key_data) != 44:
                    raise ValueError(
                        f"Invalid master key length: {len(key_data)} bytes. "
                        f"Fernet keys must be exactly 44 characters when base64-encoded."
                    )

                # Try to decode to verify it's valid base64
                import base64

                decoded = base64.urlsafe_b64decode(key_data)
                if len(decoded) != 32:
                    raise ValueError(
                        f"Invalid decoded key length: {len(decoded)} bytes. "
                        f"Fernet keys must decode to exactly 32 bytes."
                    )

                # If validation passes, create Fernet instance
                self._fernet = Fernet(key_data)

            except Exception as e:
                raise ValueError(
                    f"Invalid master key format: {e}. "
                    f"Fernet keys must be 44-character base64-urlsafe encoded strings."
                )
        else:
            raise ValueError("No master key found")

    async def list_secrets(self):
        """List all secret names."""
        if not self._fernet:
            await self.initialize_encryption()

        if not self.secrets_file_path.exists():
            return []

        try:
            # Read and decrypt the secrets file
            encrypted_data = self.secrets_file_path.read_bytes()
            decrypted_data = self._fernet.decrypt(encrypted_data)

            # Parse JSON and validate data structure
            secrets = json.loads(decrypted_data.decode("utf-8"))

            # Validate that the decrypted data is a dictionary
            if not isinstance(secrets, dict):
                raise ValueError(
                    f"Invalid secrets format: expected dictionary, got {type(secrets).__name__}. "
                    f"The secrets file may be corrupted."
                )

            return list(secrets.keys())

        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse secrets file as JSON: {e}. "
                f"The secrets file may be corrupted or was not properly encrypted."
            )
        except Exception as e:
            # Handle decryption errors (InvalidToken) and other issues
            if "decrypt" in str(e).lower() or "token" in str(e).lower():
                raise ValueError(
                    f"Failed to decrypt secrets file: {e}. "
                    f"This may indicate the wrong master key or a corrupted secrets file."
                )
            else:
                raise ValueError(f"Error reading secrets: {e}")


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
