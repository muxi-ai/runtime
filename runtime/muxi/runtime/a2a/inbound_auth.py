"""
A2A Inbound Authentication Module

Handles authentication for incoming Agent-to-Agent requests to the formation server.
Supports multiple authentication types and credential validation.
Now uses SecretsManager exclusively for secure credential storage.
"""

import logging
import base64
import hashlib
import hmac
import time
from typing import Dict, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from fastapi import Request, Header

if TYPE_CHECKING:
    from ..secrets import SecretsManager

logger = logging.getLogger(__name__)


class InboundAuthType(str, Enum):
    """Supported inbound authentication types"""

    NONE = "none"
    API_KEY = "apiKey"
    BEARER = "bearer"
    BASIC = "basic"
    HMAC = "hmac"


@dataclass
class InboundCredential:
    """Container for inbound authentication credentials"""

    auth_type: InboundAuthType
    credential_data: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True


class A2AInboundAuthenticator:
    """
    Handles authentication for incoming A2A requests to the formation server.
    Uses SecretsManager exclusively for credential storage.
    """

    def __init__(self, auth_mode: str = "none", secrets_manager: Optional["SecretsManager"] = None):
        """
        Initialize the inbound authenticator

        Args:
            auth_mode: Default authentication mode for the formation
            secrets_manager: Optional SecretsManager for credential access
        """
        self.auth_mode = InboundAuthType(auth_mode)
        self.secrets_manager = secrets_manager
        self.credentials: Dict[str, InboundCredential] = {}
        self.api_keys: Dict[str, str] = {}  # api_key -> client_id mapping
        self.bearer_tokens: Dict[str, str] = {}  # token -> client_id mapping
        self.basic_auth: Dict[str, str] = {}  # username -> password mapping
        self.hmac_secrets: Dict[str, str] = {}  # client_id -> secret mapping

        logger.info(f"Initialized A2A inbound authenticator with mode: {self.auth_mode}")

    async def initialize_credentials(self):
        """Initialize credentials from SecretsManager if available"""
        if self.secrets_manager:
            await self._load_credentials_from_secrets()
        else:
            logger.warning("No SecretsManager provided - no credentials will be available")

    async def _load_credentials_from_secrets(self):
        """Load credentials from SecretsManager only"""
        if not self.secrets_manager:
            logger.warning("SecretsManager not available for credential loading")
            return

        logger.debug("Loading A2A inbound credentials from secrets manager...")

        # Define credential mappings for expected external clients
        credential_configs = {
            "external-client-1": {
                "auth_type": InboundAuthType.API_KEY,
                "secret_name": "ALLOWED_API_KEY_1",
                "description": "External client using API key"
            },
            "external-client-2": {
                "auth_type": InboundAuthType.BEARER,
                "secret_name": "ALLOWED_BEARER_TOKEN_1",
                "description": "External client using Bearer token"
            },
            "external-client-3": {
                "auth_type": InboundAuthType.BASIC,
                "secret_names": {
                    "username": "ALLOWED_BASIC_USER",
                    "password": "ALLOWED_BASIC_PASS"
                },
                "description": "External client using Basic auth"
            },
            "external-client-4": {
                "auth_type": InboundAuthType.HMAC,
                "secret_name": "ALLOWED_HMAC_SECRET",
                "description": "External client using HMAC signature"
            }
        }

        for client_id, config in credential_configs.items():
            try:
                auth_type = config["auth_type"]

                if auth_type == InboundAuthType.BASIC:
                    # Handle Basic auth (requires username and password)
                    credential_data = await self._load_basic_credentials(config)
                else:
                    # Handle single credential cases (API_KEY, BEARER, HMAC)
                    credential_data = await self._load_single_inbound_credential(config)

                if credential_data:
                    self.add_client_credential(
                        client_id=client_id,
                        auth_type=auth_type,
                        credential_data=credential_data,
                        description=config["description"]
                    )
                    logger.debug(f"Loaded inbound credential for {client_id} ({auth_type})")
                else:
                    logger.warning(f"No credentials found for {client_id}")

            except Exception as e:
                logger.warning(f"Failed to load credentials for {client_id}: {e}")

    async def _load_single_inbound_credential(
        self, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load a single credential from secrets manager"""
        secret_name = config["secret_name"]
        auth_type = config["auth_type"]

        try:
            secret_value = await self.secrets_manager.get_secret(secret_name)
            if secret_value:
                if auth_type == InboundAuthType.API_KEY:
                    return {"api_key": secret_value}
                elif auth_type == InboundAuthType.BEARER:
                    return {"token": secret_value}
                elif auth_type == InboundAuthType.HMAC:
                    return {"secret": secret_value}
        except Exception as e:
            logger.warning(f"Failed to get secret {secret_name}: {e}")

        return None

    async def _load_basic_credentials(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Load Basic auth credentials from secrets manager"""
        secret_names = config["secret_names"]
        credentials = {}

        for key, secret_name in secret_names.items():
            try:
                secret_value = await self.secrets_manager.get_secret(secret_name)
                if secret_value:
                    credentials[key] = secret_value
                else:
                    logger.warning(f"Secret {secret_name} not found for Basic auth {key}")
                    return None
            except Exception as e:
                logger.warning(f"Failed to get secret {secret_name}: {e}")
                return None

        # Return credentials only if we have both username and password
        if "username" in credentials and "password" in credentials:
            return credentials

        return None

    def add_client_credential(
        self,
        client_id: str,
        auth_type: InboundAuthType,
        credential_data: Dict[str, Any],
        description: str = "",
    ):
        """
        Add credentials for a client that will authenticate to us

        Args:
            client_id: Unique identifier for the client
            auth_type: Type of authentication the client will use
            credential_data: Authentication data (keys, passwords, etc.)
            description: Human-readable description
        """

        if auth_type == InboundAuthType.API_KEY:
            if "api_key" not in credential_data:
                raise ValueError("API key authentication requires 'api_key' in credential_data")
            self.api_keys[credential_data["api_key"]] = client_id

        elif auth_type == InboundAuthType.BEARER:
            if "token" not in credential_data:
                raise ValueError("Bearer authentication requires 'token' in credential_data")
            self.bearer_tokens[credential_data["token"]] = client_id

        elif auth_type == InboundAuthType.BASIC:
            if "username" not in credential_data or "password" not in credential_data:
                raise ValueError("Basic authentication requires 'username' and 'password'")
            self.basic_auth[credential_data["username"]] = credential_data["password"]

        elif auth_type == InboundAuthType.HMAC:
            if "secret" not in credential_data:
                raise ValueError("HMAC authentication requires 'secret' in credential_data")
            self.hmac_secrets[client_id] = credential_data["secret"]

        self.credentials[client_id] = InboundCredential(
            auth_type=auth_type, credential_data=credential_data, description=description
        )

        logger.info(f"Added inbound credential for {client_id} ({auth_type})")

    async def authenticate_request(
        self,
        request: Request,
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None),
        x_signature: Optional[str] = Header(None),
        x_timestamp: Optional[str] = Header(None),
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Authenticate an incoming request based on the formation's auth mode

        Args:
            request: FastAPI request object
            authorization: Authorization header (Bearer/Basic)
            x_api_key: API key header
            x_signature: HMAC signature header
            x_timestamp: Timestamp for HMAC validation

        Returns:
            Tuple of (authenticated: bool, client_id: Optional[str], error: Optional[str])
        """

        # If no authentication required, allow all requests
        if self.auth_mode == InboundAuthType.NONE:
            return True, "anonymous", None

        try:
            if self.auth_mode == InboundAuthType.API_KEY:
                return await self._authenticate_api_key(x_api_key)

            elif self.auth_mode == InboundAuthType.BEARER:
                return await self._authenticate_bearer(authorization)

            elif self.auth_mode == InboundAuthType.BASIC:
                return await self._authenticate_basic(authorization)

            elif self.auth_mode == InboundAuthType.HMAC:
                return await self._authenticate_hmac(request, x_signature, x_timestamp)

            else:
                return False, None, f"Unsupported auth mode: {self.auth_mode}"

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False, None, f"Authentication failed: {str(e)}"

    async def _authenticate_api_key(
        self, api_key: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using API key"""
        if not api_key:
            return False, None, "Missing API key header (X-API-Key)"

        client_id = self.api_keys.get(api_key)
        if client_id:
            logger.debug(f"API key authentication successful for {client_id}")
            return True, client_id, None
        else:
            logger.warning(f"Invalid API key attempted: {api_key[:8]}...")
            return False, None, "Invalid API key"

    async def _authenticate_bearer(
        self, authorization: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using Bearer token"""
        if not authorization:
            return False, None, "Missing Authorization header"

        if not authorization.startswith("Bearer "):
            return False, None, "Authorization header must start with 'Bearer '"

        token = authorization[7:]  # Remove "Bearer " prefix
        client_id = self.bearer_tokens.get(token)

        if client_id:
            logger.debug(f"Bearer token authentication successful for {client_id}")
            return True, client_id, None
        else:
            logger.warning(f"Invalid bearer token attempted: {token[:16]}...")
            return False, None, "Invalid bearer token"

    async def _authenticate_basic(
        self, authorization: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using Basic authentication"""
        if not authorization:
            return False, None, "Missing Authorization header"

        if not authorization.startswith("Basic "):
            return False, None, "Authorization header must start with 'Basic '"

        try:
            # Decode base64 credentials
            encoded_creds = authorization[6:]  # Remove "Basic " prefix
            decoded_creds = base64.b64decode(encoded_creds).decode("utf-8")
            username, password = decoded_creds.split(":", 1)

            # Check credentials
            if username in self.basic_auth and self.basic_auth[username] == password:
                logger.debug(f"Basic authentication successful for {username}")
                return True, username, None
            else:
                logger.warning(f"Invalid basic auth attempted for user: {username}")
                return False, None, "Invalid username or password"

        except Exception as e:
            logger.warning(f"Basic auth decode error: {e}")
            return False, None, "Invalid basic authentication format"

    async def _authenticate_hmac(
        self, request: Request, signature: Optional[str], timestamp: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using HMAC signature"""
        if not signature or not timestamp:
            return False, None, "Missing HMAC signature or timestamp headers"

        try:
            # Check timestamp to prevent replay attacks (5 minute window)
            request_time = int(timestamp)
            current_time = int(time.time())

            if abs(current_time - request_time) > 300:  # 5 minutes
                return False, None, "Request timestamp too old"

            # Get request body for signature verification
            body = await request.body()

            # Try to verify against all HMAC secrets
            for client_id, secret in self.hmac_secrets.items():
                # Create expected signature
                message = f"{request.method}|{request.url.path}|{timestamp}|{body.decode()}"
                expected_signature = hmac.new(
                    secret.encode(), message.encode(), hashlib.sha256
                ).hexdigest()

                if hmac.compare_digest(signature, expected_signature):
                    logger.debug(f"HMAC authentication successful for {client_id}")
                    return True, client_id, None

            logger.warning("Invalid HMAC signature attempted")
            return False, None, "Invalid HMAC signature"

        except Exception as e:
            logger.warning(f"HMAC auth error: {e}")
            return False, None, f"HMAC authentication failed: {str(e)}"

    def get_auth_requirements(self) -> Dict[str, Any]:
        """Get authentication requirements for external clients"""
        return {
            "auth_mode": self.auth_mode.value,
            "required": self.auth_mode != InboundAuthType.NONE,
            "description": self._get_auth_description(),
        }

    def _get_auth_description(self) -> str:
        """Get human-readable description of auth requirements"""
        descriptions = {
            InboundAuthType.NONE: "No authentication required",
            InboundAuthType.API_KEY: "Requires X-API-Key header with valid API key",
            InboundAuthType.BEARER: "Requires Authorization: Bearer <token> header",
            InboundAuthType.BASIC: "Requires Authorization: Basic <credentials> header",
            InboundAuthType.HMAC: "Requires X-Signature and X-Timestamp headers with HMAC-SHA256",
        }
        return descriptions.get(self.auth_mode, "Unknown authentication type")

    def list_clients(self) -> Dict[str, Dict[str, Any]]:
        """List all configured client credentials (for admin purposes)"""
        result = {}
        for client_id, cred in self.credentials.items():
            result[client_id] = {
                "auth_type": cred.auth_type.value,
                "description": cred.description,
                "enabled": cred.enabled,
            }
        return result

    def remove_client(self, client_id: str):
        """Remove a client's credentials"""
        if client_id in self.credentials:
            cred = self.credentials[client_id]

            # Remove from appropriate lookup table
            if cred.auth_type == InboundAuthType.API_KEY:
                api_key = cred.credential_data.get("api_key")
                if api_key in self.api_keys:
                    del self.api_keys[api_key]

            elif cred.auth_type == InboundAuthType.BEARER:
                token = cred.credential_data.get("token")
                if token in self.bearer_tokens:
                    del self.bearer_tokens[token]

            elif cred.auth_type == InboundAuthType.BASIC:
                username = cred.credential_data.get("username")
                if username in self.basic_auth:
                    del self.basic_auth[username]

            elif cred.auth_type == InboundAuthType.HMAC:
                if client_id in self.hmac_secrets:
                    del self.hmac_secrets[client_id]

            del self.credentials[client_id]
            logger.info(f"Removed inbound credential for {client_id}")
        else:
            logger.warning(f"Client {client_id} not found for removal")
