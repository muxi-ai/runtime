"""
A2A Outbound Authentication Module

Handles authentication for outgoing Agent-to-Agent requests using the A2A SDK.
Supports authentication types as defined in the A2A protocol:
- API Key authentication
- Bearer token authentication
- Basic authentication
- No authentication

Now integrated with A2A SDK security schemes for protocol compliance.
"""

import base64
from enum import Enum
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

# A2A SDK imports
from a2a.types import (
    SecurityScheme,
    APIKeySecurityScheme,
    HTTPAuthSecurityScheme,
)

from ...secrets import SecretsManager
from ... import observability


class AuthType(str, Enum):
    """Supported authentication types for A2A communication"""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"


@dataclass
class AuthCredentials:
    """Container for authentication credentials"""

    auth_type: AuthType
    credentials: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate credentials based on auth type"""
        # Log credential validation
        observability.observe(
            event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
            level=observability.EventLevel.DEBUG,
            description="Validating A2A authentication credentials",
            data={
                "auth_type": self.auth_type.value,
                "credential_keys": list(self.credentials.keys()),
            },
        )

        if self.auth_type == AuthType.API_KEY:
            if "api_key" not in self.credentials:
                # Log validation error
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="API key authentication validation failed",
                    data={"auth_type": self.auth_type.value, "missing_credential": "api_key"},
                )
                raise ValueError("API key authentication requires 'api_key' credential")
        elif self.auth_type == AuthType.BEARER:
            if "token" not in self.credentials:
                # Log validation error
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="Bearer authentication validation failed",
                    data={"auth_type": self.auth_type.value, "missing_credential": "token"},
                )
                raise ValueError("Bearer authentication requires 'token' credential")
        elif self.auth_type == AuthType.BASIC:
            if "username" not in self.credentials or "password" not in self.credentials:
                # Log validation error
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="Basic authentication validation failed",
                    data={
                        "auth_type": self.auth_type.value,
                        "missing_credentials": [
                            cred
                            for cred in ["username", "password"]
                            if cred not in self.credentials
                        ],
                    },
                )
                raise ValueError(
                    "Basic authentication requires 'username' and 'password' " "credentials"
                )

        # Log successful validation
        observability.observe(
            event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
            level=observability.EventLevel.INFO,
            description="A2A authentication credentials validated successfully",
            data={"auth_type": self.auth_type.value, "credential_count": len(self.credentials)},
        )


class A2AAuthManager:
    """
    Manages authentication for outbound A2A requests using SDK security schemes.

    Replaces custom authentication with A2A SDK-compliant security schemes
    for better protocol compliance and maintainability.
    """

    def __init__(self, secrets_manager: SecretsManager):
        """
        Initialize A2A authentication manager with SecretsManager.

        Args:
            secrets_manager: Required SecretsManager instance for credential access
        """
        if not secrets_manager:
            raise ValueError("SecretsManager is required for A2A authentication")

        self.secrets_manager = secrets_manager
        self.schemes: Dict[str, SecurityScheme] = {}
        self._credentials: Dict[str, AuthCredentials] = {}
        self._credentials_loaded = False

        # Log initialization
        observability.observe(
            event_type=observability.SystemEvents.A2A_AUTH_INITIALIZED,
            level=observability.EventLevel.INFO,
            description="A2A authentication manager initialized",
            data={
                "secrets_manager_type": type(secrets_manager).__name__,
                "credentials_loaded": self._credentials_loaded,
            },
        )

    async def ensure_credentials_loaded(self):
        """Ensure credentials are loaded from secrets manager."""
        # Log credential loading check
        observability.observe(
            event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
            level=observability.EventLevel.DEBUG,
            description="Checking if A2A credentials need loading",
            data={
                "credentials_loaded": self._credentials_loaded,
                "current_credentials_count": len(self._credentials),
            },
        )

        if not self._credentials_loaded:
            await self._load_default_credentials()
            self._credentials_loaded = True

            # Log credentials loaded
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description="A2A credentials loaded successfully",
                data={
                    "credentials_count": len(self._credentials),
                    "service_ids": list(self._credentials.keys()),
                },
            )

    def create_scheme(self, auth_config: Dict[str, Any]) -> Optional[SecurityScheme]:
        """
        Create an SDK security scheme from auth configuration.

        Args:
            auth_config: Authentication configuration dict

        Returns:
            SDK SecurityScheme or None if auth type not supported
        """
        auth_type = auth_config.get("type")

        if auth_type == "api_key":
            return APIKeySecurityScheme(
                api_key=auth_config["key"], header_name=auth_config.get("header", "X-API-Key")
            )
        elif auth_type == "bearer":
            return HTTPAuthSecurityScheme(scheme="bearer", token=auth_config["token"])
        elif auth_type == "basic":
            return HTTPAuthSecurityScheme(
                scheme="basic", username=auth_config["username"], password=auth_config["password"]
            )

        return None

    async def _load_default_credentials(self):
        """Load default credentials from secrets manager only."""
        # Log credential loading start
        observability.observe(
            event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
            level=observability.EventLevel.INFO,
            description="Starting A2A default credentials loading",
            data={"source": "secrets_manager"},
        )

        # Define credential mappings: service_id -> secret configurations
        credential_configs = {
            # API Key services
            "external-billing-service": {
                "auth_type": AuthType.API_KEY,
                "secret_name": "BILLING_API_KEY",
            },
            "document-processor": {
                "auth_type": AuthType.API_KEY,
                "secret_name": "DOCUMENT_API_KEY",
            },
            # Bearer token services
            "analytics-engine": {"auth_type": AuthType.BEARER, "secret_name": "ANALYTICS_TOKEN"},
            # Basic auth services
            "legacy-api": {
                "auth_type": AuthType.BASIC,
                "secret_names": {
                    "username": "LEGACY_API_USERNAME",
                    "password": "LEGACY_API_PASSWORD",
                },
            },
        }

        # Load credentials for each service
        loaded_count = 0
        failed_count = 0

        for service_id, config in credential_configs.items():
            try:
                auth_type = config["auth_type"]

                if auth_type == AuthType.BASIC:
                    # Handle Basic auth multi-credential case
                    credentials = await self._load_basic_credentials(service_id, config)
                else:
                    # Handle single credential cases (API_KEY, BEARER)
                    credentials = await self._load_single_credential(service_id, config)

                if credentials:
                    self._credentials[service_id] = AuthCredentials(auth_type, credentials)
                    loaded_count += 1

                    # Log successful credential load
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                        level=observability.EventLevel.DEBUG,
                        description="A2A service credentials loaded",
                        data={
                            "service_id": service_id,
                            "auth_type": auth_type.value,
                            "credential_keys": list(credentials.keys()),
                        },
                    )
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1

                # Log credential loading error
                observability.observe(
                    event_type=observability.SystemEvents.A2A_CREDENTIALS_LOAD_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="Failed to load A2A service credentials",
                    data={
                        "service_id": service_id,
                        "auth_type": config.get("auth_type", "unknown"),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

        # Log overall credential loading results
        observability.observe(
            event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
            level=observability.EventLevel.INFO,
            description="A2A default credentials loading completed",
            data={
                "total_services": len(credential_configs),
                "loaded_count": loaded_count,
                "failed_count": failed_count,
                "loaded_services": list(self._credentials.keys()),
            },
        )

    async def _load_single_credential(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load a single credential from secrets manager."""
        secret_name = config["secret_name"]

        # Log credential loading attempt
        observability.observe(
            event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
            level=observability.EventLevel.DEBUG,
            description="Loading single A2A credential",
            data={
                "service_id": service_id,
                "secret_name": secret_name,
                "auth_type": config["auth_type"].value,
            },
        )

        try:
            secret_value = await self.secrets_manager.get_secret(secret_name)
            if secret_value:
                auth_type = config["auth_type"]
                if auth_type == AuthType.API_KEY:
                    return {"api_key": secret_value}
                elif auth_type == AuthType.BEARER:
                    return {"token": secret_value}

                # Log successful credential load
                observability.observe(
                    event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                    level=observability.EventLevel.DEBUG,
                    description="Single A2A credential loaded successfully",
                    data={
                        "service_id": service_id,
                        "secret_name": secret_name,
                        "auth_type": auth_type.value,
                    },
                )
            else:
                # Log missing credential
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    description="A2A credential not found in secrets",
                    data={
                        "service_id": service_id,
                        "secret_name": secret_name,
                        "auth_type": config["auth_type"].value,
                    },
                )

        except Exception as e:
            # Log credential loading error
            observability.observe(
                event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
                level=observability.EventLevel.ERROR,
                description="Failed to load single A2A credential",
                data={
                    "service_id": service_id,
                    "secret_name": secret_name,
                    "auth_type": config["auth_type"].value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

        return None

    async def _load_basic_credentials(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load Basic auth credentials from secrets manager."""
        secret_names = config.get("secret_names", {})
        credentials = {}

        for key, secret_name in secret_names.items():
            try:
                secret_value = await self.secrets_manager.get_secret(secret_name)
                if secret_value:
                    credentials[key] = secret_value
                else:
                    return None
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    description="Failed to load Basic auth credential",
                    data={
                        "service_id": service_id,
                        "secret_name": secret_name,
                        "error": str(e),
                    },
                )
                return None

        if "username" in credentials and "password" in credentials:
            return credentials

        return None

    def _get_credential_key_for_auth_type(self, auth_type: AuthType) -> str:
        """Get the credential dictionary key for a given auth type."""
        if auth_type == AuthType.API_KEY:
            return "api_key"
        elif auth_type == AuthType.BEARER:
            return "token"
        else:
            raise ValueError(f"Unsupported single credential auth type: {auth_type}")

    async def load_credentials_from_formation_config(self, formation_config: Dict[str, Any]):
        """
        Load A2A credentials from formation configuration and create SDK schemes.

        Services can be defined in a2a/*.afs files (auto-discovered) or inline in formation.afs.

        Expected format (same schema for both):
          id: "external-api"
          name: "External API"
          description: "External API service"
          url: "https://api.external.com"
          auth:
            type: "api_key"
            key: "${{ secrets.EXTERNAL_API_KEY }}"
        """
        if not formation_config:
            return

        a2a_config = formation_config.get("a2a", {})
        outbound_config = a2a_config.get("outbound", {})
        services = outbound_config.get("services", [])

        for service_config in services:
            try:
                service_id = service_config.get("id")
                auth_config = service_config.get("auth", {})

                if not service_id or not auth_config:
                    continue

                auth_type_str = auth_config.get("type")
                if not auth_type_str:
                    continue

                # Interpolate secrets in auth config
                interpolated_config = {}
                for key, value in auth_config.items():
                    if isinstance(value, str) and "${{" in value:
                        interpolated_value = await self.secrets_manager.interpolate_secrets(value)
                        if interpolated_value:
                            interpolated_config[key] = interpolated_value
                    else:
                        interpolated_config[key] = value

                # Create SDK security scheme
                scheme = self.create_scheme(interpolated_config)
                if scheme:
                    self.schemes[service_id] = scheme

                    # Also store in legacy format for compatibility
                    auth_type = AuthType(auth_type_str)
                    if auth_type == AuthType.API_KEY:
                        self.add_credentials(
                            service_id,
                            auth_type,
                            {
                                "api_key": interpolated_config.get("key"),
                                "api_key_header": interpolated_config.get("header", "X-API-Key"),
                            },
                        )
                    elif auth_type == AuthType.BEARER:
                        self.add_credentials(
                            service_id, auth_type, {"token": interpolated_config.get("token")}
                        )
                    elif auth_type == AuthType.BASIC:
                        self.add_credentials(
                            service_id,
                            auth_type,
                            {
                                "username": interpolated_config.get("username"),
                                "password": interpolated_config.get("password"),
                            },
                        )

                    # Log successful service configuration processing
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                        level=observability.EventLevel.DEBUG,
                        description="A2A service configuration processed successfully",
                        data={
                            "service_id": service_id,
                            "auth_type": auth_type_str,
                            "scheme_type": type(scheme).__name__,
                        },
                    )

            except Exception as e:
                # Log formation configuration processing warning
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    description="Failed to process A2A service configuration",
                    data={
                        "service_id": service_id or "unknown",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

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
            # Log successful credential addition
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_LOADED,
                level=observability.EventLevel.INFO,
                description="A2A credentials added successfully",
                data={
                    "agent_id": agent_id,
                    "auth_type": auth_type.value,
                    "credential_count": len(credentials),
                },
            )
        except ValueError as e:
            # Log credential validation error
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                description="A2A credential validation failed during addition",
                data={
                    "agent_id": agent_id,
                    "auth_type": auth_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
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
        return agent_id in self._credentials or agent_id in self.schemes

    def get_scheme(self, service_id: str) -> Optional[SecurityScheme]:
        """Get SDK security scheme for a service"""
        return self.schemes.get(service_id)

    async def apply_sdk_authentication(
        self, service_id: str, headers: Dict[str, str], required: bool = False
    ) -> Tuple[bool, Dict[str, str]]:
        """
        Apply SDK-based authentication to HTTP headers.

        Args:
            service_id: Target service identifier
            headers: HTTP headers to modify
            required: Whether authentication is required

        Returns:
            Tuple of (success: bool, updated_headers: Dict[str, str])
        """
        scheme = self.get_scheme(service_id)
        if not scheme:
            if required:
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="A2A SDK authentication failed - missing required scheme",
                    data={"service_id": service_id, "required": True},
                )
                return False, headers
            else:
                return True, headers

        try:
            # Apply SDK scheme authentication based on type
            updated_headers = headers.copy()

            if isinstance(scheme, APIKeySecurityScheme):
                # APIKeySecurityScheme stores the actual values, not the spec
                # Get api_key from the stored credentials instead
                creds = self.get_credentials(service_id)
                if creds and creds.auth_type == AuthType.API_KEY:
                    api_key = creds.credentials.get("api_key")
                    header_name = creds.credentials.get("api_key_header", "X-API-Key")
                    if api_key:
                        updated_headers[header_name] = api_key

            elif isinstance(scheme, HTTPAuthSecurityScheme):
                # HTTPAuthSecurityScheme stores the actual values
                creds = self.get_credentials(service_id)
                if creds:
                    if creds.auth_type == AuthType.BEARER:
                        token = creds.credentials.get("token")
                        if token:
                            updated_headers["Authorization"] = f"Bearer {token}"
                    elif creds.auth_type == AuthType.BASIC:
                        username = creds.credentials.get("username")
                        password = creds.credentials.get("password")
                        if username and password:
                            credentials_str = f"{username}:{password}"
                            encoded_credentials = base64.b64encode(credentials_str.encode()).decode()
                            updated_headers["Authorization"] = f"Basic {encoded_credentials}"

            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                level=observability.EventLevel.DEBUG,
                description="A2A SDK authentication applied successfully",
                data={
                    "service_id": service_id,
                    "scheme_type": type(scheme).__name__,
                    "headers_added": [k for k in updated_headers.keys() if k not in headers],
                },
            )

            return True, updated_headers

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                description="A2A SDK authentication failed with exception",
                data={
                    "service_id": service_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False, headers

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
            # Log no auth required
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                level=observability.EventLevel.DEBUG,
                description="A2A authentication not required",
                data={"agent_id": agent_id, "auth_type": "none"},
            )
            return True, headers

        # Check if we have credentials
        creds = self.get_credentials(agent_id)
        if not creds:
            if required:
                # Log missing required credentials error
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="A2A authentication failed - missing required credentials",
                    data={"agent_id": agent_id, "auth_type": auth_type.value, "required": True},
                )
                return False, headers
            else:
                # Log missing optional credentials warning
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.WARNING,
                    description="A2A authentication skipped - missing optional credentials",
                    data={"agent_id": agent_id, "auth_type": auth_type.value, "required": False},
                )
                return True, headers

        # Verify credential type matches requirement
        if creds.auth_type != auth_type:
            # Log credential type mismatch error
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                description="A2A authentication failed - credential type mismatch",
                data={
                    "agent_id": agent_id,
                    "expected_auth_type": auth_type.value,
                    "available_auth_type": creds.auth_type.value,
                },
            )
            #  f"Credential type mismatch for {agent_id}: have {creds.auth_type}, need {auth_type}"
            # )
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
                # Log API key authentication success
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.DEBUG,
                    description="A2A API key authentication applied successfully",
                    data={"agent_id": agent_id, "auth_type": "api_key", "header_name": header_name},
                )

            elif auth_type == AuthType.BEARER:
                token = creds.credentials["token"]
                updated_headers["Authorization"] = f"Bearer {token}"
                # Log bearer token authentication success
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.DEBUG,
                    description="A2A bearer token authentication applied successfully",
                    data={"agent_id": agent_id, "auth_type": "bearer"},
                )

            elif auth_type == AuthType.BASIC:
                username = creds.credentials["username"]
                password = creds.credentials["password"]
                credentials_str = f"{username}:{password}"
                encoded_credentials = base64.b64encode(credentials_str.encode()).decode()
                updated_headers["Authorization"] = f"Basic {encoded_credentials}"
                # Log basic authentication success
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.DEBUG,
                    description="A2A basic authentication applied successfully",
                    data={"agent_id": agent_id, "auth_type": "basic", "username": username},
                )

            return True, updated_headers

        except Exception as e:
            # Log authentication exception
            observability.observe(
                event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                description="A2A authentication failed with exception",
                data={
                    "agent_id": agent_id,
                    "auth_type": auth_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False, headers

    def remove_credentials(self, agent_id: str):
        """Remove credentials for an agent"""
        if agent_id in self._credentials:
            auth_type = self._credentials[agent_id].auth_type
            del self._credentials[agent_id]
            # Log credential removal
            observability.observe(
                event_type=observability.SystemEvents.A2A_CREDENTIAL_REMOVED,
                level=observability.EventLevel.INFO,
                description="A2A credentials removed for agent",
                data={"agent_id": agent_id, "auth_type": auth_type.value},
            )

    def list_agents_with_credentials(self) -> Dict[str, AuthType]:
        """Get a list of agents that have credentials configured"""
        return {agent_id: creds.auth_type for agent_id, creds in self._credentials.items()}


# Global auth manager instance
_auth_manager = None


def get_auth_manager(secrets_manager: SecretsManager) -> A2AAuthManager:
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
