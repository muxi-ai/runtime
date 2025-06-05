"""
A2A Inbound Authentication Module

Handles authentication for incoming Agent-to-Agent requests to the formation server.
Supports multiple authentication types and credential validation.
"""

import logging
import os
import base64
import hashlib
import hmac
import time
from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass, field
from enum import Enum
from fastapi import HTTPException, Request, Header

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
    Handles authentication for incoming A2A requests to the formation server
    """

    def __init__(self, auth_mode: str = "none"):
        """
        Initialize the inbound authenticator

        Args:
            auth_mode: Default authentication mode for the formation
        """
        self.auth_mode = InboundAuthType(auth_mode)
        self.credentials: Dict[str, InboundCredential] = {}
        self.api_keys: Dict[str, str] = {}  # api_key -> client_id mapping
        self.bearer_tokens: Dict[str, str] = {}  # token -> client_id mapping
        self.basic_auth: Dict[str, str] = {}  # username -> password mapping
        self.hmac_secrets: Dict[str, str] = {}  # client_id -> secret mapping

        self._load_default_credentials()

        logger.info(f"Initialized A2A inbound authenticator with mode: {self.auth_mode}")

    def _load_default_credentials(self):
        """Load default credentials for testing external agents"""

        # Example credentials that external agents might use to authenticate to us
        default_credentials = {
            "external-client-1": {
                "auth_type": InboundAuthType.API_KEY,
                "api_key": os.getenv("ALLOWED_API_KEY_1", "test-external-key-123"),
                "description": "Test external client using API key"
            },
            "external-client-2": {
                "auth_type": InboundAuthType.BEARER,
                "token": os.getenv("ALLOWED_BEARER_TOKEN_1", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test"),
                "description": "Test external client using Bearer token"
            },
            "external-client-3": {
                "auth_type": InboundAuthType.BASIC,
                "username": os.getenv("ALLOWED_BASIC_USER", "external_user"),
                "password": os.getenv("ALLOWED_BASIC_PASS", "external_pass123"),
                "description": "Test external client using Basic auth"
            },
            "external-client-4": {
                "auth_type": InboundAuthType.HMAC,
                "secret": os.getenv("ALLOWED_HMAC_SECRET", "shared-secret-key-456"),
                "description": "Test external client using HMAC signature"
            }
        }

        for client_id, cred_info in default_credentials.items():
            auth_type = cred_info["auth_type"]

            if auth_type == InboundAuthType.API_KEY:
                self.api_keys[cred_info["api_key"]] = client_id

            elif auth_type == InboundAuthType.BEARER:
                self.bearer_tokens[cred_info["token"]] = client_id

            elif auth_type == InboundAuthType.BASIC:
                self.basic_auth[cred_info["username"]] = cred_info["password"]

            elif auth_type == InboundAuthType.HMAC:
                self.hmac_secrets[client_id] = cred_info["secret"]

            self.credentials[client_id] = InboundCredential(
                auth_type=auth_type,
                credential_data=cred_info,
                description=cred_info["description"]
            )

            logger.debug(f"Loaded inbound credential for {client_id} ({auth_type})")

    def add_client_credential(
        self,
        client_id: str,
        auth_type: InboundAuthType,
        credential_data: Dict[str, Any],
        description: str = ""
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
            auth_type=auth_type,
            credential_data=credential_data,
            description=description
        )

        logger.info(f"Added inbound credential for {client_id} ({auth_type})")

    async def authenticate_request(
        self,
        request: Request,
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None),
        x_signature: Optional[str] = Header(None),
        x_timestamp: Optional[str] = Header(None)
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

    async def _authenticate_api_key(self, api_key: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
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

    async def _authenticate_bearer(self, authorization: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
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

    async def _authenticate_basic(self, authorization: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using Basic authentication"""
        if not authorization:
            return False, None, "Missing Authorization header"

        if not authorization.startswith("Basic "):
            return False, None, "Authorization header must start with 'Basic '"

        try:
            # Decode base64 credentials
            encoded_creds = authorization[6:]  # Remove "Basic " prefix
            decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
            username, password = decoded_creds.split(':', 1)

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
        self,
        request: Request,
        signature: Optional[str],
        timestamp: Optional[str]
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
                    secret.encode(),
                    message.encode(),
                    hashlib.sha256
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
            "description": self._get_auth_description()
        }

    def _get_auth_description(self) -> str:
        """Get human-readable description of auth requirements"""
        descriptions = {
            InboundAuthType.NONE: "No authentication required",
            InboundAuthType.API_KEY: "Requires X-API-Key header with valid API key",
            InboundAuthType.BEARER: "Requires Authorization: Bearer <token> header",
            InboundAuthType.BASIC: "Requires Authorization: Basic <credentials> header",
            InboundAuthType.HMAC: "Requires X-Signature and X-Timestamp headers with HMAC-SHA256"
        }
        return descriptions.get(self.auth_mode, "Unknown authentication type")

    def list_clients(self) -> Dict[str, Dict[str, Any]]:
        """List all configured client credentials (for admin purposes)"""
        result = {}
        for client_id, cred in self.credentials.items():
            result[client_id] = {
                "auth_type": cred.auth_type.value,
                "description": cred.description,
                "enabled": cred.enabled
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
