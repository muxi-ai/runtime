"""
A2A Inbound Authentication Module

Handles authentication for incoming Agent-to-Agent requests to the formation server.
Implements STRICT auth type validation to fix critical security vulnerability.
Uses SDK security schemes for protocol compliance.
"""

import base64
import os
import json
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from fastapi import Request, Header

# We implement SDK-style authentication without importing SDK modules
# since they're not available on the server side

from ... import observability
from ...secrets import SecretsManager


class InboundAuthType(str, Enum):
    """Supported inbound authentication types"""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"


@dataclass
class InboundCredential:
    """Container for inbound authentication credentials"""

    auth_type: InboundAuthType
    credential_data: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True


class A2AInboundAuthenticator:
    """
    SDK-based authenticator for incoming A2A requests.

    Implements STRICT auth type enforcement to fix critical security bug
    where mismatched auth types (e.g., API key sent to Bearer-only server)
    were incorrectly accepted.
    """

    def __init__(self, auth_mode: str = "none", secrets_manager: Optional[SecretsManager] = None):
        """
        Initialize the inbound authenticator

        Args:
            auth_mode: Authentication mode for the formation (strictly enforced)
            secrets_manager: Optional SecretsManager for credential access
        """
        try:
            self.auth_mode = InboundAuthType(auth_mode)
            self.secrets_manager = secrets_manager
            self.schemes: Dict[str, Any] = {}  # SDK schemes for validation
            self.credentials: Dict[str, InboundCredential] = {}
            self.api_keys: Dict[str, str] = {}  # api_key -> client_id mapping
            self.bearer_tokens: Dict[str, str] = {}  # token -> client_id mapping
            self.basic_auth: Dict[str, str] = {}  # username -> password mapping

            # Emit initialization event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_INITIALIZED,
                level=observability.EventLevel.INFO,
                description=f"A2A inbound authenticator initialized with mode: {self.auth_mode}",
                data={
                    "auth_mode": self.auth_mode.value,
                    "has_secrets_manager": secrets_manager is not None,
                },
            )

        except Exception as e:
            # Emit error event for initialization failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to initialize A2A inbound authenticator: {str(e)}",
                data={"auth_mode": auth_mode, "error": str(e)},
            )
            raise

    async def initialize_credentials(self):
        """Initialize credentials from SecretsManager if available"""
        try:
            # Emit credential initialization start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description="Starting A2A inbound credential initialization",
                data={
                    "has_secrets_manager": self.secrets_manager is not None,
                    "auth_mode": self.auth_mode.value,
                },
            )

            if self.secrets_manager:
                await self._load_credentials_from_secrets()
            else:
                # Emit warning for missing secrets manager
                observability.observe(
                    event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                    level=observability.EventLevel.WARNING,
                    description="No SecretsManager provided - no credentials will be available",
                    data={"auth_mode": self.auth_mode.value},
                )

            # Emit successful initialization event
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description="A2A inbound credential initialization completed",
                data={
                    "credentials_count": len(self.credentials),
                    "api_keys_count": len(self.api_keys),
                    "bearer_tokens_count": len(self.bearer_tokens),
                    "basic_auth_count": len(self.basic_auth),
                },
            )

        except Exception as e:
            # Emit error event for credential initialization failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to initialize A2A inbound credentials: {str(e)}",
                data={"auth_mode": self.auth_mode.value, "error": str(e)},
            )
            raise

    def _load_credential_configurations(self) -> Dict[str, Dict[str, Any]]:
        """
        Load credential configurations from environment variables or config file.

        This method checks for configurations in the following order:
        1. Environment variable A2A_INBOUND_CREDENTIALS (JSON string)
        2. Config file specified by A2A_INBOUND_CONFIG_PATH
        3. Default fallback configurations

        Returns:
            Dictionary of credential configurations keyed by client ID
        """
        credential_configs = {}

        # Try to load from environment variable (JSON string)
        env_config = os.environ.get('A2A_INBOUND_CREDENTIALS')
        if env_config:
            try:
                credential_configs = json.loads(env_config)
                observability.observe(
                    event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                    level=observability.EventLevel.INFO,
                    description="Loaded A2A inbound credentials from environment",
                    data={"client_count": len(credential_configs)}
                )
                return credential_configs
            except json.JSONDecodeError as e:
                observability.observe(
                    event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                    level=observability.EventLevel.WARNING,
                    description=f"Failed to parse A2A_INBOUND_CREDENTIALS: {str(e)}",
                    data={"error": str(e)}
                )

        # Try to load from config file
        config_path = os.environ.get('A2A_INBOUND_CONFIG_PATH')
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    credential_configs = config_data.get('inbound_credentials', {})
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                        level=observability.EventLevel.INFO,
                        description=f"Loaded A2A inbound credentials from file: {config_path}",
                        data={"client_count": len(credential_configs)}
                    )
                    return credential_configs
            except (json.JSONDecodeError, IOError) as e:
                observability.observe(
                    event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                    level=observability.EventLevel.WARNING,
                    description=f"Failed to load config from {config_path}: {str(e)}",
                    data={"error": str(e), "config_path": config_path}
                )

        # Load individual client configs from environment variables
        # Format: A2A_CLIENT_<ID>_TYPE, A2A_CLIENT_<ID>_SECRET, etc.
        client_prefix = "A2A_CLIENT_"
        client_ids = set()

        # Find all unique client IDs from environment variables
        for key in os.environ:
            if key.startswith(client_prefix):
                parts = key[len(client_prefix):].split('_')
                if parts:
                    client_ids.add(parts[0])

        # Build configurations for each client
        for client_id in client_ids:
            auth_type = os.environ.get(f"{client_prefix}{client_id}_TYPE")
            if not auth_type:
                continue

            config = {
                "auth_type": InboundAuthType(auth_type.lower()),
                "description": os.environ.get(f"{client_prefix}{client_id}_DESC", f"Client {client_id}")
            }

            # Handle different auth types
            if auth_type.lower() in ["api_key", "bearer"]:
                secret_name = os.environ.get(f"{client_prefix}{client_id}_SECRET")
                if secret_name:
                    config["secret_name"] = secret_name
            elif auth_type.lower() == "basic":
                username_secret = os.environ.get(f"{client_prefix}{client_id}_USERNAME_SECRET")
                password_secret = os.environ.get(f"{client_prefix}{client_id}_PASSWORD_SECRET")
                if username_secret and password_secret:
                    config["secret_names"] = {
                        "username": username_secret,
                        "password": password_secret
                    }

            credential_configs[client_id.lower()] = config

        if credential_configs:
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description="Loaded A2A inbound credentials from individual environment variables",
                data={"client_count": len(credential_configs)}
            )
            return credential_configs

        # Default fallback configurations (for backward compatibility)
        # These can be overridden by setting the environment variables
        default_configs = {
            "external-client-1": {
                "auth_type": InboundAuthType.API_KEY,
                "secret_name": os.environ.get("A2A_DEFAULT_API_KEY_SECRET", "ALLOWED_API_KEY_1"),
                "description": "External client using API key",
            },
            "external-client-2": {
                "auth_type": InboundAuthType.BEARER,
                "secret_name": os.environ.get("A2A_DEFAULT_BEARER_SECRET", "ALLOWED_BEARER_TOKEN_1"),
                "description": "External client using Bearer token",
            },
            "external-client-3": {
                "auth_type": InboundAuthType.BASIC,
                "secret_names": {
                    "username": os.environ.get("A2A_DEFAULT_BASIC_USER_SECRET", "ALLOWED_BASIC_USER"),
                    "password": os.environ.get("A2A_DEFAULT_BASIC_PASS_SECRET", "ALLOWED_BASIC_PASS"),
                },
                "description": "External client using Basic auth",
            },
        }

        # Only use defaults if explicitly enabled
        if os.environ.get("A2A_USE_DEFAULT_CLIENTS", "false").lower() == "true":
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description="Using default A2A inbound credential configurations",
                data={"client_count": len(default_configs)}
            )
            return default_configs

        # Return empty dict if no configurations found
        observability.observe(
            event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
            level=observability.EventLevel.WARNING,
            description="No A2A inbound credential configurations found",
            data={}
        )
        return {}

    async def _load_credentials_from_secrets(self):
        """Load credentials from SecretsManager only"""
        try:
            if not self.secrets_manager:
                # Emit warning for missing secrets manager
                observability.observe(
                    event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                    level=observability.EventLevel.WARNING,
                    description="SecretsManager not available for credential loading",
                    data={"auth_mode": self.auth_mode.value},
                )
                return

            # Load credential configurations from environment or config file
            credential_configs = self._load_credential_configurations()

            successful_loads = 0
            failed_loads = 0

            for client_id, config in credential_configs.items():
                try:
                    auth_type = config["auth_type"]

                    if auth_type == InboundAuthType.BASIC:
                        # Handle Basic auth (requires username and password)
                        credential_data = await self._load_basic_credentials(config)
                    else:
                        # Handle single credential cases (API_KEY, BEARER)
                        credential_data = await self._load_single_inbound_credential(config)

                    if credential_data:
                        self.add_client_credential(
                            client_id=client_id,
                            auth_type=auth_type,
                            credential_data=credential_data,
                            description=config["description"],
                        )

                        # Emit successful credential load event
                        observability.observe(
                            event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                            level=observability.EventLevel.INFO,
                            description=f"Loaded inbound credential for {client_id}",
                            data={
                                "client_id": client_id,
                                "auth_type": auth_type.value,
                                "description": config["description"],
                            },
                        )

                        successful_loads += 1
                    else:
                        # Emit warning for missing credentials
                        observability.observe(
                            event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                            level=observability.EventLevel.WARNING,
                            description=f"No credentials found for {client_id}",
                            data={"client_id": client_id, "auth_type": auth_type.value},
                        )
                        failed_loads += 1

                except Exception as e:
                    # Emit error event for individual credential load failure
                    observability.observe(
                        event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                        level=observability.EventLevel.ERROR,
                        description=f"Failed to load credentials for {client_id}: {str(e)}",
                        data={"client_id": client_id, "error": str(e)},
                    )
                    failed_loads += 1

            # Emit summary event
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description="A2A inbound credential loading completed",
                data={
                    "successful_loads": successful_loads,
                    "failed_loads": failed_loads,
                    "total_clients": len(credential_configs),
                },
            )

        except Exception as e:
            # Emit error event for credential loading failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to load credentials from secrets: {str(e)}",
                data={"auth_mode": self.auth_mode.value, "error": str(e)},
            )
            raise

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
        except Exception as e:
            # Emit error event for secret retrieval failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get secret {secret_name}: {str(e)}",
                data={"secret_name": secret_name, "auth_type": auth_type.value, "error": str(e)},
            )

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
                    # Emit warning for missing secret
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                        level=observability.EventLevel.WARNING,
                        description=f"Secret {secret_name} not found for Basic auth {key}",
                        data={"secret_name": secret_name, "key": key, "auth_type": "basic"},
                    )
                    return None
            except Exception as e:
                # Emit error event for secret retrieval failure
                observability.observe(
                    event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description=f"Failed to get secret {secret_name}: {str(e)}",
                    data={
                        "secret_name": secret_name,
                        "key": key,
                        "auth_type": "basic",
                        "error": str(e),
                    },
                )
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
        try:
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

            # Store the credential
            self.credentials[client_id] = InboundCredential(
                auth_type=auth_type,
                credential_data=credential_data,
                description=description,
                enabled=True,
            )

            # Emit credential addition event
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description=f"Added client credential for {client_id}",
                data={
                    "client_id": client_id,
                    "auth_type": auth_type.value,
                    "description": description,
                    "total_credentials": len(self.credentials),
                },
            )

        except Exception as e:
            # Emit error event for credential addition failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to add client credential for {client_id}: {str(e)}",
                data={"client_id": client_id, "auth_type": auth_type.value, "error": str(e)},
            )
            raise

    async def authenticate_request(
        self,
        request: Request,
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None),
        x_signature: Optional[str] = Header(None),
        x_timestamp: Optional[str] = Header(None),
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Authenticate request with STRICT type checking.

        CRITICAL BUG FIX: Rejects any auth type that doesn't match configured mode.
        Previously, server configured for Bearer would accept API keys.

        Returns:
            Tuple of (authenticated, client_id, error_message)
        """
        try:
            # Emit authentication start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATING,
                level=observability.EventLevel.DEBUG,
                description=f"Starting A2A inbound authentication with mode: {self.auth_mode}",
                data={
                    "auth_mode": self.auth_mode.value,
                    "has_authorization": authorization is not None,
                    "has_api_key": x_api_key is not None,
                    "has_signature": x_signature is not None,
                    "has_timestamp": x_timestamp is not None,
                },
            )

            if self.auth_mode == InboundAuthType.NONE:
                # Emit no authentication event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.DEBUG,
                    description="A2A authentication bypassed (mode: none)",
                    data={"auth_mode": "none"},
                )
                return True, "anonymous", None

            # CRITICAL: Reject any auth type that doesn't match configured mode
            elif self.auth_mode == InboundAuthType.BEARER:
                if x_api_key:  # API key provided for bearer-only server
                    return False, None, "Server requires Bearer authentication, not API key"
                if not authorization or not authorization.startswith("Bearer "):
                    return False, None, "Bearer authentication required"
                result = await self._authenticate_bearer(authorization)

            elif self.auth_mode == InboundAuthType.API_KEY:
                if authorization and authorization.startswith("Bearer "):
                    return False, None, "Server requires API key authentication, not Bearer"
                if not x_api_key:
                    return False, None, "API key required in X-API-Key header"
                result = await self._authenticate_api_key(x_api_key)

            elif self.auth_mode == InboundAuthType.BASIC:
                if x_api_key:
                    return False, None, "Server requires Basic authentication, not API key"
                if authorization and authorization.startswith("Bearer "):
                    return False, None, "Server requires Basic authentication, not Bearer"
                if not authorization or not authorization.startswith("Basic "):
                    return False, None, "Basic authentication required"
                result = await self._authenticate_basic(authorization)

            else:
                error_msg = f"Unsupported authentication mode: {self.auth_mode}"
                # Emit unsupported auth mode event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description=error_msg,
                    data={"auth_mode": self.auth_mode.value},
                )
                return False, None, error_msg

            # Emit authentication result event
            authenticated, client_id, error_message = result
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                level=observability.EventLevel.INFO if authenticated else observability.EventLevel.WARNING,
                description=f"A2A inbound authentication {'successful' if authenticated else 'failed'}",  # noqa: E501
                data={
                    "auth_mode": self.auth_mode.value,
                    "authenticated": authenticated,
                    "client_id": client_id,
                    "error_message": error_message,
                },
            )

            return result

        except Exception as e:
            # Emit error event for authentication failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"A2A inbound authentication error: {str(e)}",
                data={"auth_mode": self.auth_mode.value, "error": str(e)},
            )
            return False, None, f"Authentication error: {str(e)}"

    async def _authenticate_api_key(
        self, api_key: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using API key"""
        try:
            if not api_key:
                return False, None, "API key required but not provided"

            client_id = self.api_keys.get(api_key)
            if client_id:
                # Emit successful API key authentication
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.INFO,
                    description=f"API key authentication successful for client {client_id}",
                    data={"client_id": client_id, "auth_type": "api_key"},
                )
                return True, client_id, None
            else:
                # Emit failed API key authentication
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description="API key authentication failed: invalid key",
                    data={"auth_type": "api_key", "api_key_provided": True},
                )
                return False, None, "Invalid API key"

        except Exception as e:
            # Emit error event for API key authentication failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"API key authentication error: {str(e)}",
                data={"auth_type": "api_key", "error": str(e)},
            )
            return False, None, f"API key authentication error: {str(e)}"

    async def _authenticate_bearer(
        self, authorization: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using Bearer token"""
        try:
            if not authorization:
                return False, None, "Authorization header required but not provided"

            if not authorization.startswith("Bearer "):
                return False, None, "Invalid authorization header format"

            token = authorization[7:]  # Remove "Bearer " prefix
            client_id = self.bearer_tokens.get(token)

            if client_id:
                # Emit successful Bearer authentication
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.INFO,
                    description=f"Bearer token authentication successful for client {client_id}",
                    data={"client_id": client_id, "auth_type": "bearer"},
                )
                return True, client_id, None
            else:
                # Emit failed Bearer authentication
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description="Bearer token authentication failed: invalid token",
                    data={"auth_type": "bearer", "token_provided": True},
                )
                return False, None, "Invalid Bearer token"

        except Exception as e:
            # Emit error event for Bearer authentication failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Bearer token authentication error: {str(e)}",
                data={"auth_type": "bearer", "error": str(e)},
            )
            return False, None, f"Bearer authentication error: {str(e)}"

    async def _authenticate_basic(
        self, authorization: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Authenticate using Basic authentication"""
        try:
            if not authorization:
                return False, None, "Authorization header required but not provided"

            if not authorization.startswith("Basic "):
                return False, None, "Invalid authorization header format"

            try:
                encoded_credentials = authorization[6:]  # Remove "Basic " prefix
                decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
                username, password = decoded_credentials.split(":", 1)
            except (ValueError, UnicodeDecodeError):
                return False, None, "Invalid Basic authentication format"

            stored_password = self.basic_auth.get(username)
            if stored_password and stored_password == password:
                # Emit successful Basic authentication
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.INFO,
                    description=f"Basic authentication successful for user {username}",
                    data={"username": username, "auth_type": "basic"},
                )
                return True, username, None
            else:
                # Emit failed Basic authentication
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description=f"Basic authentication failed for user {username}",
                    data={
                        "username": username,
                        "auth_type": "basic",
                        "user_exists": username in self.basic_auth,
                    },
                )
                return False, None, "Invalid username or password"

        except Exception as e:
            # Emit error event for Basic authentication failure
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Basic authentication error: {str(e)}",
                data={"auth_type": "basic", "error": str(e)},
            )
            return False, None, f"Basic authentication error: {str(e)}"

    def get_auth_requirements(self) -> Dict[str, Any]:
        """Get authentication requirements for API documentation"""
        try:
            requirements = {
                "auth_mode": self.auth_mode.value,
                "description": self._get_auth_description(),
                "required_headers": [],
            }

            if self.auth_mode == InboundAuthType.API_KEY:
                requirements["required_headers"] = ["X-API-Key"]
            elif self.auth_mode == InboundAuthType.BEARER:
                requirements["required_headers"] = ["Authorization"]
            elif self.auth_mode == InboundAuthType.BASIC:
                requirements["required_headers"] = ["Authorization"]

            # Emit auth requirements request event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATING,
                level=observability.EventLevel.DEBUG,
                description="A2A authentication requirements requested",
                data={
                    "auth_mode": self.auth_mode.value,
                    "required_headers": requirements["required_headers"],
                },
            )

            return requirements

        except Exception as e:
            # Emit error event for auth requirements failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get auth requirements: {str(e)}",
                data={"auth_mode": self.auth_mode.value, "error": str(e)},
            )
            raise

    def _get_auth_description(self) -> str:
        """Get human-readable description of authentication requirements"""
        descriptions = {
            InboundAuthType.NONE: "No authentication required",
            InboundAuthType.API_KEY: "API key required in X-API-Key header",
            InboundAuthType.BEARER: "Bearer token required in Authorization header",
            InboundAuthType.BASIC: "Basic authentication required in Authorization header",
        }
        return descriptions.get(self.auth_mode, "Unknown authentication mode")

    def list_clients(self) -> Dict[str, Dict[str, Any]]:
        """List all configured clients (without sensitive data)"""
        try:
            clients = {}
            for client_id, credential in self.credentials.items():
                clients[client_id] = {
                    "auth_type": credential.auth_type.value,
                    "description": credential.description,
                    "enabled": credential.enabled,
                }

            # Emit client list request event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATING,
                level=observability.EventLevel.DEBUG,
                description="A2A client list requested",
                data={"total_clients": len(clients), "auth_mode": self.auth_mode.value},
            )

            return clients

        except Exception as e:
            # Emit error event for client list failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to list clients: {str(e)}",
                data={"auth_mode": self.auth_mode.value, "error": str(e)},
            )
            raise

    def remove_client(self, client_id: str):
        """Remove a client and its credentials"""
        try:
            if client_id not in self.credentials:
                # Emit client not found event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description=f"Attempted to remove non-existent client: {client_id}",
                    data={"client_id": client_id, "auth_mode": self.auth_mode.value},
                )
                raise ValueError(f"Client {client_id} not found")

            credential = self.credentials[client_id]
            auth_type = credential.auth_type

            # Remove from appropriate mapping
            if auth_type == InboundAuthType.API_KEY:
                api_key = credential.credential_data.get("api_key")
                if api_key and api_key in self.api_keys:
                    del self.api_keys[api_key]
            elif auth_type == InboundAuthType.BEARER:
                token = credential.credential_data.get("token")
                if token and token in self.bearer_tokens:
                    del self.bearer_tokens[token]
            elif auth_type == InboundAuthType.BASIC:
                username = credential.credential_data.get("username")
                if username and username in self.basic_auth:
                    del self.basic_auth[username]

            # Remove from credentials
            del self.credentials[client_id]

            # Emit successful client removal event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                level=observability.EventLevel.INFO,
                description=f"Client {client_id} removed successfully",
                data={
                    "client_id": client_id,
                    "auth_type": auth_type.value,
                    "remaining_clients": len(self.credentials),
                },
            )

        except Exception as e:
            # Emit error event for client removal failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to remove client {client_id}: {str(e)}",
                data={"client_id": client_id, "auth_mode": self.auth_mode.value, "error": str(e)},
            )
            raise
