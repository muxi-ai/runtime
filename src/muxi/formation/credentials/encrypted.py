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
from cachetools import LRUCache

from .resolver import CredentialResolver
from ...services import observability
from ...utils.user_resolution import resolve_user_identifier

# Default salt for key derivation (v1 format)
DEFAULT_ENCRYPTION_SALT = "muxi-user-credentials-salt-v1"


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
        db_manager=None,
        encryption_key: Optional[str] = None,
        encryption_salt: Optional[str] = None,
        cache_ttl: int = 3600,  # Pass through to parent
        cache_maxsize: int = 10000,  # Pass through to parent
        fernet_cache_maxsize: int = 10000,  # Separate limit for Fernet instances
    ):
        """
        Initialize the encrypted credential resolver.

        Args:
            async_session_maker: Async SQLAlchemy session factory
            formation_id: The formation ID (used as default encryption key)
            llm_model: Optional LLM model for extraction
            db_manager: Database manager instance for user resolution
            encryption_key: Optional custom encryption key (overrides formation_id)
            encryption_salt: Optional salt for key derivation (default: DEFAULT_ENCRYPTION_SALT)
            cache_ttl: Time-to-live for cached credentials in seconds (default: 1 hour)
            cache_maxsize: Maximum number of users in credential cache (default: 10,000)
            fernet_cache_maxsize: Maximum Fernet instances to cache (default: 10,000)
        """
        super().__init__(async_session_maker, formation_id, llm_model, db_manager, cache_ttl, cache_maxsize)
        self.custom_key = encryption_key
        # Use provided salt or default
        self.encryption_salt = (encryption_salt or DEFAULT_ENCRYPTION_SALT).encode("utf-8")
        # Bounded LRU cache for Fernet instances (deterministic, no TTL needed)
        # Fernet instances are small (~200 bytes) but should still be bounded
        self._fernet_cache = LRUCache(maxsize=fernet_cache_maxsize)

        # Warn if using formation_id as encryption key (security concern)
        if not encryption_key:
            observability.observe(
                event_type=observability.SystemEvents.SECURITY_CONFIGURATION_WARNING,
                level=observability.EventLevel.WARNING,
                data={
                    "formation_id": formation_id,
                    "encryption_key_source": "formation_id",
                    "recommendation": "Provide explicit encryption_key for production deployments"
                },
                description=(
                    "Using formation_id as encryption key. This is acceptable for development "
                    "but consider providing an explicit encryption_key for production."
                ),
            )

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
        combined = f"{base_key}:{user_id}".encode("utf-8")

        # Derive key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.encryption_salt,  # Configurable salt (formation-specific)
            iterations=100000,
            backend=default_backend(),
        )

        # Generate Fernet-compatible key
        key = base64.urlsafe_b64encode(kdf.derive(combined))
        fernet = Fernet(key)

        # Cache for future use
        self._fernet_cache[user_id] = fernet

        return fernet

    def _encrypt_credentials(self, user_id: str, credentials: Any) -> Dict[str, Any]:
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
        encrypted = fernet.encrypt(plaintext.encode("utf-8"))

        # Return with version marker
        return {
            "version": "v1",
            "encrypted": True,
            "data": encrypted.decode("utf-8"),  # Store as string in DB
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
            decrypted = fernet.decrypt(encrypted_data.encode("utf-8"))

            # Parse JSON
            return json.loads(decrypted.decode("utf-8"))
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
                decrypted_list.append({"name": item["name"], "credentials": decrypted_creds})
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

    def _canonicalize_credential(self, credential: Any) -> str:
        """
        Canonicalize a credential structure for consistent comparison.

        Converts credentials to a normalized form that's invariant to:
        - Dictionary key ordering
        - Whitespace differences in strings
        - Type variations (e.g., int vs string for numbers)

        Args:
            credential: The credential to canonicalize

        Returns:
            A canonical string representation
        """

        def _normalize(obj: Any) -> Any:
            """Recursively normalize an object for canonical representation."""
            if obj is None:
                return None
            elif isinstance(obj, bool):
                # Handle bool before int since bool is a subclass of int
                return obj
            elif isinstance(obj, (int, float)):
                return obj
            elif isinstance(obj, str):
                # Keep strings as-is but trimmed
                return obj.strip()
            elif isinstance(obj, dict):
                # Sort keys and recursively normalize values
                return {k: _normalize(v) for k, v in sorted(obj.items())}
            elif isinstance(obj, (list, tuple)):
                # Recursively normalize list items
                return [_normalize(item) for item in obj]
            else:
                # Fallback for other types
                return str(obj)

        # Normalize the credential structure first
        normalized = _normalize(credential)

        # Convert to canonical JSON string with sorted keys
        # This ensures consistent string representation
        return json.dumps(normalized, sort_keys=True, separators=(",", ":"))

    async def check_duplicate(
        self,
        user_id: str,
        service: str,
        credentials: Any,
    ) -> bool:
        """
        Check if a credential already exists by comparing decrypted values.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)
            credentials: The credential to check

        Returns:
            True if duplicate exists, False otherwise
        """
        from sqlalchemy import select
        from .resolver import Credential

        service = service.lower()

        # Resolve user identifier to internal user ID
        try:
            internal_user_id, _ = await resolve_user_identifier(
                identifier=user_id,
                formation_id=self.formation_id,
                db_manager=self.async_session_maker,
                kv_cache=None,
            )
        except Exception:
            # If resolution fails, user doesn't exist, so no duplicates
            return False

        async with self.async_session_maker() as session:
            # Check existing credentials
            cred_stmt = select(Credential).where(
                Credential.user_id == internal_user_id,
                Credential.service == service,
            )
            result = await session.execute(cred_stmt)
            existing_credentials = result.scalars().all()

            # Canonicalize the incoming credential for comparison
            canonical_new = self._canonicalize_credential(credentials)

            # Check each existing credential
            for existing in existing_credentials:
                stored = existing.credentials

                # Parse JSON string if needed
                if isinstance(stored, str):
                    try:
                        stored = json.loads(stored)
                    except (json.JSONDecodeError, TypeError):
                        pass

                decrypted = self._decrypt_credentials(user_id, stored)

                # Canonicalize the decrypted credential and compare
                canonical_existing = self._canonicalize_credential(decrypted)
                if canonical_existing == canonical_new:
                    return True  # Duplicate found

            return False  # No duplicate

    async def store_credential(
        self,
        user_id: str,
        service: str,
        credentials: Any,  # Can be string or dict
        credential_name: Optional[str] = None,
        mcp_service: Optional[Any] = None,
    ) -> str:
        """
        Store encrypted user credentials in the database.

        Overrides the base method to add encryption before storage.
        Note: Duplicate checking should be done via check_duplicate() before calling this.

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
        return await super().store_credential(
            user_id=user_id,
            service=service,
            credentials=encrypted_data,  # Store encrypted version
            credential_name=credential_name,
            mcp_service=mcp_service,
        )
