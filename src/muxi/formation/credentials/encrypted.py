"""
Encrypted Credential Resolution Service

This module extends CredentialResolver to add encryption for stored credentials.
Uses zero-configuration encryption with formation_id and per-user key derivation.
"""

import json
import base64
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet

from .resolver import CredentialResolver


class EncryptedCredentialResolver(CredentialResolver):
    """
    Credential resolver with encryption support.

    Extends the base CredentialResolver to add:
    - Zero-configuration encryption using formation_id
    - Support for custom encryption keys
    - Per-user key derivation using PBKDF2
    - Backward compatibility with plaintext credentials
    """

    def __init__(
        self,
        async_session_maker,
        formation_id: str,
        llm_model: Optional[str] = None,
        encryption_key: Optional[str] = None
    ):
        """
        Initialize the encrypted credential resolver.

        Args:
            async_session_maker: Async SQLAlchemy session factory
            formation_id: The formation ID (used as default encryption key)
            llm_model: Optional LLM model for extraction
            encryption_key: Optional custom encryption key (overrides formation_id)
        """
        super().__init__(async_session_maker, formation_id, llm_model)
        self.custom_key = encryption_key
        self._fernet_cache = {}  # Cache Fernet instances per user

    def derive_user_key(self, user_id: str) -> Fernet:
        """
        Derive a per-user encryption key using PBKDF2.

        This ensures each user's credentials are encrypted with a unique key,
        providing additional isolation between users.

        Args:
            user_id: The user identifier

        Returns:
            Fernet instance for encryption/decryption
        """
        # Check cache first
        if user_id in self._fernet_cache:
            return self._fernet_cache[user_id]

        # Use custom key if provided, otherwise use formation_id
        base_key = self.custom_key or self.formation_id

        # Combine base key with user_id for per-user isolation
        combined = f"{base_key}:{user_id}".encode('utf-8')

        # Derive key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'muxi-user-credentials-v1',  # Static salt for deterministic key derivation
            iterations=100000,
            backend=default_backend()
        )

        # Generate Fernet-compatible key
        key = base64.urlsafe_b64encode(kdf.derive(combined))
        fernet = Fernet(key)

        # Cache for future use
        self._fernet_cache[user_id] = fernet

        return fernet

    def _encrypt_credentials(self, user_id: str, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt credential data.

        Args:
            user_id: The user identifier
            credentials: The plaintext credentials

        Returns:
            Dictionary with encrypted data and version marker
        """
        fernet = self.derive_user_key(user_id)

        # Convert credentials to JSON string
        plaintext = json.dumps(credentials)

        # Encrypt
        encrypted = fernet.encrypt(plaintext.encode('utf-8'))

        # Return with version marker
        return {
            "version": "v1",
            "encrypted": True,
            "data": encrypted.decode('utf-8')  # Store as string in DB
        }

    def _decrypt_credentials(self, user_id: str, stored_data: Any) -> Dict[str, Any]:
        """
        Decrypt credential data or return plaintext if not encrypted.

        Args:
            user_id: The user identifier
            stored_data: The stored credential data (encrypted or plaintext)

        Returns:
            The decrypted credentials
        """
        # Handle backward compatibility - check if data is encrypted
        if isinstance(stored_data, dict) and stored_data.get("encrypted") is True:
            # This is encrypted data
            fernet = self.derive_user_key(user_id)

            # Get encrypted data
            encrypted_data = stored_data.get("data", "")

            # Decrypt
            decrypted = fernet.decrypt(encrypted_data.encode('utf-8'))

            # Parse JSON
            return json.loads(decrypted.decode('utf-8'))
        else:
            # Legacy plaintext data - return as-is
            return stored_data

    async def resolve(self, user_id: str, service: str) -> Optional[Dict]:
        """
        Resolve and decrypt user credentials for a service.

        Overrides the base method to add decryption.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)

        Returns:
            The decrypted credential data if found, None otherwise.
        """
        # Get the encrypted data from parent class
        stored_data = await super().resolve(user_id, service)

        if stored_data is None:
            return None

        # Handle multiple credentials case
        if isinstance(stored_data, list):
            # Multiple credentials - decrypt each one
            decrypted_list = []
            for item in stored_data:
                # The credentials might be a JSON string that needs parsing
                cred_data = item["credentials"]
                if isinstance(cred_data, str):
                    try:
                        cred_data = json.loads(cred_data)
                    except (json.JSONDecodeError, TypeError):
                        pass  # Keep as string if not JSON

                decrypted_creds = self._decrypt_credentials(user_id, cred_data)
                decrypted_list.append({
                    "name": item["name"],
                    "credentials": decrypted_creds
                })
            return decrypted_list
        else:
            # Single credential - handle as JSON string if needed
            # The database might return a JSON string that needs parsing
            if isinstance(stored_data, str):
                try:
                    stored_data = json.loads(stored_data)
                except (json.JSONDecodeError, TypeError):
                    # Not JSON, treat as raw credential value
                    return stored_data

            # Now decrypt and return
            return self._decrypt_credentials(user_id, stored_data)

    async def store_credential(
        self,
        user_id: str,
        service: str,
        credentials: Dict[str, Any],
        credential_name: Optional[str] = None,
        mcp_service: Optional[Any] = None,
    ) -> None:
        """
        Store encrypted user credentials in the database.

        Overrides the base method to add encryption before storage.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)
            credentials: The credential data to store (will be encrypted)
            credential_name: Optional name for the credential
            mcp_service: Optional MCP service for identity discovery
        """
        # Encrypt the credentials
        encrypted_data = self._encrypt_credentials(user_id, credentials)

        # Store using parent class method
        await super().store_credential(
            user_id=user_id,
            service=service,
            credentials=encrypted_data,  # Store encrypted version
            credential_name=credential_name,
            mcp_service=mcp_service
        )
