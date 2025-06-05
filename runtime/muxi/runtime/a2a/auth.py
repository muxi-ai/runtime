"""
A2A Authentication Module

Handles authentication for external Agent-to-Agent communication.
Supports multiple authentication types as defined in the A2A protocol:
- API Key authentication
- Bearer token authentication
- OAuth2 client credentials
- Basic authentication
- No authentication
"""

import logging
import os
import time
import hmac
import hashlib
import uuid
from enum import Enum
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import httpx

# JWT and cryptography imports
try:
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

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
                raise ValueError("Basic authentication requires 'username' and 'password' credentials")
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
    Manages authentication credentials and applies authentication to HTTP requests
    """

    def __init__(self):
        """Initialize the authentication manager"""
        self._credentials: Dict[str, AuthCredentials] = {}
        self._load_default_credentials()

    def _load_default_credentials(self):
        """Load default credentials from environment variables"""
        # Load common credentials from environment
        default_creds = {
            # Example API key for billing service
            "external-billing-service": AuthCredentials(
                auth_type=AuthType.API_KEY,
                credentials={"api_key": os.getenv("BILLING_API_KEY", "test-billing-key-123")}
            ),

            # Example bearer token for analytics
            "analytics-engine": AuthCredentials(
                auth_type=AuthType.BEARER,
                credentials={"token": os.getenv("ANALYTICS_TOKEN", "test-analytics-jwt-token")}
            ),

            # Example OAuth2 for notification hub
            "notification-hub": AuthCredentials(
                auth_type=AuthType.OAUTH2,
                credentials={
                    "client_id": os.getenv("NOTIFICATION_CLIENT_ID", "test-client-id"),
                    "client_secret": os.getenv("NOTIFICATION_CLIENT_SECRET", "test-client-secret"),
                    "token_url": os.getenv("NOTIFICATION_TOKEN_URL", "https://notify.cloudservice.net/oauth/token")
                }
            ),

            # Example API key for document processor
            "document-processor": AuthCredentials(
                auth_type=AuthType.API_KEY,
                credentials={"api_key": os.getenv("DOCUMENT_API_KEY", "test-doc-api-key-456")}
            ),

            # Example HMAC for secure messaging service
            "secure-messaging": AuthCredentials(
                auth_type=AuthType.HMAC,
                credentials={"secret": os.getenv("SECURE_MESSAGING_SECRET", "test-hmac-secret-123")}
            ),

            # Example JWT for auth service
            "auth-service": AuthCredentials(
                auth_type=AuthType.JWT,
                credentials={
                    "private_key": os.getenv("AUTH_SERVICE_PRIVATE_KEY", self._get_test_private_key()),
                    "algorithm": "RS256",
                    "issuer": "muxi-a2a",
                    "audience": "a2a-network"
                }
            )
        }

        for agent_id, creds in default_creds.items():
            try:
                self._credentials[agent_id] = creds
                logger.debug(f"Loaded default credentials for {agent_id} ({creds.auth_type})")
            except ValueError as e:
                logger.warning(f"Failed to load credentials for {agent_id}: {e}")

    def _get_test_private_key(self) -> str:
        """Generate a test RSA private key for JWT signing (development only)"""
        if not JWT_AVAILABLE:
            return "test-private-key-placeholder"

        try:
            # Generate a small RSA key for testing (1024 bit is fast but not secure)
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=1024,
            )

            # Serialize to PEM format
            pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            return pem.decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to generate test private key: {e}")
            return "test-private-key-placeholder"

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
        self,
        agent_id: str,
        auth_type: AuthType,
        headers: Dict[str, str],
        required: bool = False
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
            logger.error(f"Credential type mismatch for {agent_id}: have {creds.auth_type}, need {auth_type}")
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
                logger.error("HMAC authentication requires URL, method, and payload - use apply_authentication_with_context")
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
        required: bool = False
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
            logger.error(f"Credential type mismatch for {agent_id}: have {creds.auth_type}, need {auth_type}")
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
        payload: Optional[str] = None
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
                secret.encode(),
                signature_string.encode(),
                hashlib.sha256
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
                        "client_secret": client_secret
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code == 200:
                    token_data = response.json()
                    return token_data.get("access_token")
                else:
                    logger.error(f"OAuth2 token request failed: {response.status_code} {response.text}")
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

def get_auth_manager() -> A2AAuthManager:
    """Get the global authentication manager instance"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = A2AAuthManager()
    return _auth_manager
