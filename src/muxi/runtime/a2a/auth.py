"""
A2A Authentication Module

Handles authentication for external Agent-to-Agent communication.
Supports multiple authentication types as defined in the A2A protocol:
- API Key authentication
- Bearer token authentication
- OAuth2 client credentials
- Basic authentication
- No authentication

Now integrated with formation-level encrypted secrets management.
"""

import logging
import os
import time
import hmac
import hashlib
import uuid
from enum import Enum
from typing import Dict, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, field
import httpx

# JWT and cryptography imports
try:
    import jwt
    from cryptography.hazmat.primitives import serialization
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

# Avoid circular imports
if TYPE_CHECKING:
    from src.muxi.runtime.secrets import SecretsManager

logger = logging.getLogger(__name__)


class AuthType(str, Enum):
    """Supported authentication types for A2A communication"""

    NONE = "none"
    API_KEY = "apiKey"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    HMAC = "hmac"
    JWT = "jwt"


@dataclass
class AuthCredentials:
    """Container for authentication credentials"""

    auth_type: AuthType
    credentials: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate credentials based on auth type"""
        if self.auth_type == AuthType.API_KEY:
            if "api_key" not in self.credentials:
                raise ValueError("API key authentication requires 'api_key' credential")
        elif self.auth_type == AuthType.BEARER:
            if "token" not in self.credentials:
                raise ValueError("Bearer authentication requires 'token' credential")
        elif self.auth_type == AuthType.BASIC:
            if "username" not in self.credentials or "password" not in self.credentials:
                raise ValueError(
                    "Basic authentication requires 'username' and 'password' credentials"
                )
        elif self.auth_type == AuthType.OAUTH2:
            required = ["client_id", "client_secret"]
            missing = [req for req in required if req not in self.credentials]
            if missing:
                raise ValueError(f"OAuth2 authentication requires: {missing}")
        elif self.auth_type == AuthType.HMAC:
            if "secret" not in self.credentials:
                raise ValueError("HMAC authentication requires 'secret' credential")
        elif self.auth_type == AuthType.JWT:
            if "private_key" not in self.credentials:
                raise ValueError("JWT authentication requires 'private_key' credential")
            if not JWT_AVAILABLE:
                raise ValueError("JWT authentication requires 'PyJWT' and 'cryptography' packages")


class A2AAuthManager:
    """
    Manages authentication credentials for external A2A communication.

    Now uses SecretsManager exclusively for secure credential storage.
    No fallbacks to environment variables or test values.
    """

    def __init__(self, secrets_manager: "SecretsManager"):
        """
        Initialize A2A authentication manager with SecretsManager.

        Args:
            secrets_manager: Required SecretsManager instance for credential access
        """
        if not secrets_manager:
            raise ValueError("SecretsManager is required for A2A authentication")

        self.secrets_manager = secrets_manager
        self._credentials: Dict[str, AuthCredentials] = {}
        self._credentials_loaded = False

        logger.debug("Initialized A2A auth manager with secrets")

    async def ensure_credentials_loaded(self):
        """Ensure credentials are loaded from secrets manager."""
        if not self._credentials_loaded:
            await self._load_default_credentials()
            self._credentials_loaded = True

    async def _load_default_credentials(self):
        """Load default credentials from secrets manager only."""
        logger.debug("Loading A2A credentials from secrets manager...")

        # Define credential mappings: service_id -> secret configurations
        credential_configs = {
            # API Key services
            "external-billing-service": {
                "auth_type": AuthType.API_KEY,
                "secret_name": "BILLING_API_KEY"
            },
            "document-processor": {
                "auth_type": AuthType.API_KEY,
                "secret_name": "DOCUMENT_API_KEY"
            },

            # Bearer token services
            "analytics-engine": {
                "auth_type": AuthType.BEARER,
                "secret_name": "ANALYTICS_TOKEN"
            },

            # OAuth2 services
            "notification-hub": {
                "auth_type": AuthType.OAUTH2,
                "secret_names": {
                    "client_id": "NOTIFICATION_CLIENT_ID",
                    "client_secret": "NOTIFICATION_CLIENT_SECRET",
                    "token_url": "NOTIFICATION_TOKEN_URL"
                }
            },

            # HMAC services
            "secure-messaging": {
                "auth_type": AuthType.HMAC,
                "secret_name": "SECURE_MESSAGING_SECRET"
            },

            # JWT services
            "auth-service": {
                "auth_type": AuthType.JWT,
                "secret_name": "AUTH_SERVICE_PRIVATE_KEY",
                "extra_config": {
                    "algorithm": "RS256",
                    "issuer": "muxi-a2a",
                    "audience": "a2a-network"
                }
            }
        }

        # Load credentials for each service
        for service_id, config in credential_configs.items():
            try:
                auth_type = config["auth_type"]

                if auth_type == AuthType.OAUTH2:
                    # Handle OAuth2 multi-credential case
                    credentials = await self._load_oauth2_credentials(service_id, config)
                elif auth_type == AuthType.JWT:
                    # Handle JWT special case
                    credentials = await self._load_jwt_credentials(service_id, config)
                else:
                    # Handle single credential cases (API_KEY, BEARER, HMAC)
                    credentials = await self._load_single_credential(service_id, config)

                if credentials:
                    self._credentials[service_id] = AuthCredentials(auth_type, credentials)
                    logger.debug(f"Loaded credentials for {service_id} ({auth_type})")
                else:
                    logger.warning(f"No credentials found for {service_id}")

            except Exception as e:
                logger.warning(f"Failed to load credentials for {service_id}: {e}")

    async def _load_single_credential(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load a single credential from secrets manager only."""
        secret_name = config["secret_name"]

        try:
            secret_value = await self.secrets_manager.get_secret(secret_name)
            if secret_value:
                credential_key = self._get_credential_key_for_auth_type(
                    config["auth_type"]
                )
                return {credential_key: secret_value}
        except Exception as e:
            logger.warning(f"Failed to get secret {secret_name}: {e}")

        return None

    async def _load_oauth2_credentials(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load OAuth2 credentials from secrets manager only."""
        secret_names = config["secret_names"]
        credentials = {}

        for key, secret_name in secret_names.items():
            try:
                secret_value = await self.secrets_manager.get_secret(secret_name)
                if secret_value:
                    credentials[key] = secret_value
                else:
                    logger.warning(f"Secret {secret_name} not found for OAuth2 {key}")
                    return None
            except Exception as e:
                logger.warning(f"Failed to get secret {secret_name}: {e}")
                return None

        # Return credentials only if we have all required fields
        required_fields = ["client_id", "client_secret"]
        if all(field in credentials for field in required_fields):
            return credentials

        return None

    async def _load_jwt_credentials(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load JWT credentials from secrets manager only."""
        secret_name = config["secret_name"]
        extra_config = config.get("extra_config", {})

        try:
            private_key = await self.secrets_manager.get_secret(secret_name)
            if private_key:
                credentials = {"private_key": private_key}
                credentials.update(extra_config)
                return credentials
        except Exception as e:
            logger.warning(f"Failed to get secret {secret_name}: {e}")

        return None

    def _get_credential_key_for_auth_type(self, auth_type: AuthType) -> str:
        """Get the credential dictionary key for a given auth type."""
        if auth_type == AuthType.API_KEY:
            return "api_key"
        elif auth_type == AuthType.BEARER:
            return "token"
        elif auth_type == AuthType.HMAC:
            return "secret"
        else:
            raise ValueError(f"Unsupported single credential auth type: {auth_type}")

    async def load_credentials_from_formation_config(self, formation_config: Dict[str, Any]):
        """
        Load A2A credentials from formation configuration.

        Expected format:
        a2a:
          outbound:
            services:
              - service_id: "external-api"
                auth:
                  type: "apiKey"
                  api_key: "${{ secrets.EXTERNAL_API_KEY }}"
        """
        if not formation_config:
            return

        a2a_config = formation_config.get("a2a", {})
        outbound_config = a2a_config.get("outbound", {})
        services = outbound_config.get("services", [])

        for service_config in services:
            try:
                service_id = service_config.get("service_id")
                auth_config = service_config.get("auth", {})

                if not service_id or not auth_config:
                    continue

                auth_type_str = auth_config.get("type")
                if not auth_type_str:
                    continue

                auth_type = AuthType(auth_type_str)

                # Process credentials based on auth type
                if auth_type == AuthType.API_KEY:
                    api_key = auth_config.get("api_key")
                    if api_key:
                        api_key = await self.secrets_manager.interpolate_secrets(api_key)
                        if api_key:
                            self.add_credentials(service_id, auth_type, {"api_key": api_key})

                elif auth_type == AuthType.BEARER:
                    token = auth_config.get("token")
                    if token:
                        token = await self.secrets_manager.interpolate_secrets(token)
                        if token:
                            self.add_credentials(service_id, auth_type, {"token": token})

                elif auth_type == AuthType.BASIC:
                    username = auth_config.get("username")
                    password = auth_config.get("password")
                    if username and password:
                        username = await self.secrets_manager.interpolate_secrets(username)
                        password = await self.secrets_manager.interpolate_secrets(password)
                        if username and password:
                            self.add_credentials(service_id, auth_type, {
                                "username": username,
                                "password": password
                            })

                # Add more auth types as needed...

                logger.debug(f"Loaded formation credentials for {service_id} ({auth_type})")

            except Exception as e:
                logger.warning(f"Failed to load formation credentials for service: {e}")

    def add_credentials(self, agent_id: str, auth_type: AuthType, credentials: Dict[str, Any]):
        """
        Add or update credentials for a specific agent

        Args:
            agent_id: The target agent identifier
            auth_type: Type of authentication
            credentials: Authentication credentials
        """
        try:
            self._credentials[agent_id] = AuthCredentials(auth_type, credentials)
            logger.info(f"Added credentials for {agent_id} ({auth_type})")
        except ValueError as e:
            logger.error(f"Failed to add credentials for {agent_id}: {e}")
            raise

    def get_credentials(self, agent_id: str) -> Optional[AuthCredentials]:
        """
        Get credentials for a specific agent

        Args:
            agent_id: The target agent identifier

        Returns:
            AuthCredentials if available, None otherwise
        """
        return self._credentials.get(agent_id)

    def has_credentials(self, agent_id: str) -> bool:
        """Check if credentials are available for an agent"""
        return agent_id in self._credentials

    async def apply_authentication(
        self, agent_id: str, auth_type: AuthType, headers: Dict[str, str], required: bool = False
    ) -> Tuple[bool, Dict[str, str]]:
        """
        Apply authentication to HTTP headers

        Args:
            agent_id: Target agent identifier
            auth_type: Required authentication type
            headers: HTTP headers to modify
            required: Whether authentication is required

        Returns:
            Tuple of (success: bool, updated_headers: Dict[str, str])
        """
        # If no auth required, return as-is
        if auth_type == AuthType.NONE:
            logger.debug(f"No authentication required for {agent_id}")
            return True, headers

        # Check if we have credentials
        creds = self.get_credentials(agent_id)
        if not creds:
            if required:
                logger.error(f"No credentials available for {agent_id} (requires {auth_type})")
                return False, headers
            else:
                logger.warning(f"No credentials for {agent_id}, proceeding without auth")
                return True, headers

        # Verify credential type matches requirement
        if creds.auth_type != auth_type:
            logger.error(
                f"Credential type mismatch for {agent_id}: have {creds.auth_type}, need {auth_type}"
            )
            if required:
                return False, headers
            else:
                return True, headers

        # Apply authentication based on type
        updated_headers = headers.copy()

        try:
            if auth_type == AuthType.API_KEY:
                api_key = creds.credentials["api_key"]
                # Common API key header patterns
                if "api_key_header" in creds.credentials:
                    header_name = creds.credentials["api_key_header"]
                else:
                    # Default to common patterns
                    header_name = "X-API-Key"

                updated_headers[header_name] = api_key
                logger.debug(f"Applied API key authentication for {agent_id}")

            elif auth_type == AuthType.BEARER:
                token = creds.credentials["token"]
                updated_headers["Authorization"] = f"Bearer {token}"
                logger.debug(f"Applied Bearer token authentication for {agent_id}")

            elif auth_type == AuthType.BASIC:
                import base64

                username = creds.credentials["username"]
                password = creds.credentials["password"]
                credentials_str = f"{username}:{password}"
                encoded_credentials = base64.b64encode(credentials_str.encode()).decode()
                updated_headers["Authorization"] = f"Basic {encoded_credentials}"
                logger.debug(f"Applied Basic authentication for {agent_id}")

            elif auth_type == AuthType.OAUTH2:
                # For OAuth2, we might need to get a token first
                token = await self._get_oauth2_token(creds.credentials)
                if token:
                    updated_headers["Authorization"] = f"Bearer {token}"
                    logger.debug(f"Applied OAuth2 authentication for {agent_id}")
                else:
                    logger.error(f"Failed to get OAuth2 token for {agent_id}")
                    return False, headers

            elif auth_type == AuthType.HMAC:
                # HMAC signature authentication - need URL, method, and payload
                # This will be handled by the new method with additional parameters
                logger.error(
                    "HMAC authentication requires URL, method, and payload"
                    " - use apply_authentication_with_context instead"
                )
                return False, headers

            elif auth_type == AuthType.JWT:
                # JWT authentication
                token = self._create_jwt_token(creds.credentials, agent_id)
                if token:
                    updated_headers["Authorization"] = f"Bearer {token}"
                    logger.debug(f"Applied JWT authentication for {agent_id}")
                else:
                    logger.error(f"Failed to create JWT token for {agent_id}")
                    return False, headers

            return True, updated_headers

        except Exception as e:
            logger.error(f"Failed to apply authentication for {agent_id}: {e}")
            return False, headers

    async def apply_authentication_with_context(
        self,
        agent_id: str,
        auth_type: AuthType,
        headers: Dict[str, str],
        url: str,
        method: str = "POST",
        payload: Optional[str] = None,
        required: bool = False,
    ) -> Tuple[bool, Dict[str, str]]:
        """
        Apply authentication with full request context (needed for HMAC)

        Args:
            agent_id: Target agent identifier
            auth_type: Required authentication type
            headers: HTTP headers to modify
            url: Request URL
            method: HTTP method
            payload: Request payload (if any)
            required: Whether authentication is required

        Returns:
            Tuple of (success: bool, updated_headers: Dict[str, str])
        """
        # If no auth required, return as-is
        if auth_type == AuthType.NONE:
            logger.debug(f"No authentication required for {agent_id}")
            return True, headers

        # Check if we have credentials
        creds = self.get_credentials(agent_id)
        if not creds:
            if required:
                logger.error(f"No credentials available for {agent_id} (requires {auth_type})")
                return False, headers
            else:
                logger.warning(f"No credentials for {agent_id}, proceeding without auth")
                return True, headers

        # Verify credential type matches requirement
        if creds.auth_type != auth_type:
            logger.error(
                f"Credential type mismatch for {agent_id}: have {creds.auth_type}, need {auth_type}"
            )
            if required:
                return False, headers
            else:
                return True, headers

        # Apply authentication based on type
        updated_headers = headers.copy()

        try:
            if auth_type == AuthType.HMAC:
                success = self._apply_hmac_auth(updated_headers, creds, url, method, payload)
                if success:
                    logger.debug(f"Applied HMAC authentication for {agent_id}")
                    return True, updated_headers
                else:
                    logger.error(f"Failed to apply HMAC authentication for {agent_id}")
                    return False, headers

            elif auth_type == AuthType.JWT:
                token = self._create_jwt_token(creds.credentials, agent_id)
                if token:
                    updated_headers["Authorization"] = f"Bearer {token}"
                    logger.debug(f"Applied JWT authentication for {agent_id}")
                    return True, updated_headers
                else:
                    logger.error(f"Failed to create JWT token for {agent_id}")
                    return False, headers

            else:
                # Fall back to the standard method for other auth types
                return await self.apply_authentication(agent_id, auth_type, headers, required)

        except Exception as e:
            logger.error(f"Failed to apply authentication for {agent_id}: {e}")
            return False, headers

    def _apply_hmac_auth(
        self,
        headers: Dict[str, str],
        credentials: AuthCredentials,
        url: str,
        method: str,
        payload: Optional[str] = None,
    ) -> bool:
        """Apply HMAC signature authentication"""
        try:
            secret = credentials.credentials["secret"]
            timestamp = str(int(time.time()))
            nonce = str(uuid.uuid4())

            # Create signature string: method + url + timestamp + nonce + payload_hash
            payload_hash = ""
            if payload:
                payload_hash = hashlib.sha256(payload.encode()).hexdigest()

            signature_string = f"{method.upper()}\n{url}\n{timestamp}\n{nonce}\n{payload_hash}"

            # Create HMAC signature
            signature = hmac.new(
                secret.encode(), signature_string.encode(), hashlib.sha256
            ).hexdigest()

            # Add headers
            headers["X-Signature"] = signature
            headers["X-Timestamp"] = timestamp
            headers["X-Nonce"] = nonce

            # Optional: add the signature string for debugging (in non-production)
            if os.getenv("A2A_DEBUG_HMAC") == "true":
                headers["X-Debug-Signature-String"] = signature_string

            return True

        except Exception as e:
            logger.error(f"HMAC signature generation failed: {e}")
            return False

    def _create_jwt_token(self, credentials: Dict[str, Any], agent_id: str) -> Optional[str]:
        """Create a JWT token for authentication"""
        if not JWT_AVAILABLE:
            logger.error("JWT functionality not available - install PyJWT and cryptography")
            return None

        try:
            private_key = credentials["private_key"]
            algorithm = credentials.get("algorithm", "RS256")
            issuer = credentials.get("issuer", f"agent-{agent_id}")
            audience = credentials.get("audience", "a2a-network")

            # Create JWT claims
            now = int(time.time())
            claims = {
                "iss": issuer,  # Issuer
                "aud": audience,  # Audience
                "iat": now,  # Issued at
                "exp": now + 3600,  # Expires in 1 hour
                "jti": str(uuid.uuid4()),  # JWT ID
                "sub": agent_id,  # Subject (agent identifier)
            }

            # Add custom claims if provided
            if "custom_claims" in credentials:
                claims.update(credentials["custom_claims"])

            # Parse private key
            if isinstance(private_key, str):
                if private_key.startswith("-----BEGIN"):
                    # PEM format key
                    key = serialization.load_pem_private_key(
                        private_key.encode(),
                        password=None,
                    )
                else:
                    # Assume it's a base64 encoded key or similar
                    key = private_key
            else:
                key = private_key

            # Create and sign JWT
            token = jwt.encode(claims, key, algorithm=algorithm)
            return token

        except Exception as e:
            logger.error(f"JWT token creation failed: {e}")
            return None

    async def _get_oauth2_token(self, oauth_creds: Dict[str, Any]) -> Optional[str]:
        """
        Get an OAuth2 access token using client credentials flow

        Args:
            oauth_creds: OAuth2 credentials containing client_id, client_secret, token_url

        Returns:
            Access token if successful, None otherwise
        """
        try:
            token_url = oauth_creds["token_url"]
            client_id = oauth_creds["client_id"]
            client_secret = oauth_creds["client_secret"]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code == 200:
                    token_data = response.json()
                    return token_data.get("access_token")
                else:
                    logger.error(
                        f"OAuth2 token request failed: {response.status_code} {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"OAuth2 token request failed: {e}")
            return None

    def remove_credentials(self, agent_id: str):
        """Remove credentials for an agent"""
        if agent_id in self._credentials:
            del self._credentials[agent_id]
            logger.info(f"Removed credentials for {agent_id}")

    def list_agents_with_credentials(self) -> Dict[str, AuthType]:
        """Get a list of agents that have credentials configured"""
        return {agent_id: creds.auth_type for agent_id, creds in self._credentials.items()}


# Global auth manager instance
_auth_manager = None


def get_auth_manager(secrets_manager: "SecretsManager") -> A2AAuthManager:
    """
    Get the global authentication manager instance with SecretsManager.

    Args:
        secrets_manager: Required SecretsManager instance for credential access

    Returns:
        A2AAuthManager instance configured with secrets
    """
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = A2AAuthManager(secrets_manager)
    return _auth_manager
