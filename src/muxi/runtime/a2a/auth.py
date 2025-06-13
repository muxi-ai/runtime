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

import base64

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

from ..observability import EventType, EventLevel, ObservabilityManager

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
        # Log credential validation
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_AUTH_VALIDATION,
                level=EventLevel.DEBUG,
                message="Validating A2A authentication credentials",
                data={
                    "auth_type": self.auth_type.value,
                    "credential_keys": list(self.credentials.keys())
                }
            )
        except Exception:
            pass

        if self.auth_type == AuthType.API_KEY:
            if "api_key" not in self.credentials:
                # Log validation error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="API key authentication validation failed",
                        data={
                            "auth_type": self.auth_type.value,
                            "missing_credential": "api_key"
                        }
                    )
                except Exception:
                    pass
                raise ValueError(
                    "API key authentication requires 'api_key' credential"
                )
        elif self.auth_type == AuthType.BEARER:
            if "token" not in self.credentials:
                # Log validation error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="Bearer authentication validation failed",
                        data={
                            "auth_type": self.auth_type.value,
                            "missing_credential": "token"
                        }
                    )
                except Exception:
                    pass
                raise ValueError(
                    "Bearer authentication requires 'token' credential"
                )
        elif self.auth_type == AuthType.BASIC:
            if ("username" not in self.credentials or
                    "password" not in self.credentials):
                # Log validation error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="Basic authentication validation failed",
                        data={
                            "auth_type": self.auth_type.value,
                            "missing_credentials": [
                                cred for cred in ["username", "password"]
                                if cred not in self.credentials
                            ]
                        }
                    )
                except Exception:
                    pass
                raise ValueError(
                    "Basic authentication requires 'username' and 'password' "
                    "credentials"
                )
        elif self.auth_type == AuthType.OAUTH2:
            required = ["client_id", "client_secret"]
            missing = [req for req in required if req not in self.credentials]
            if missing:
                # Log validation error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="OAuth2 authentication validation failed",
                        data={
                            "auth_type": self.auth_type.value,
                            "missing_credentials": missing
                        }
                    )
                except Exception:
                    pass
                raise ValueError(f"OAuth2 authentication requires: {missing}")
        elif self.auth_type == AuthType.HMAC:
            if "secret" not in self.credentials:
                # Log validation error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="HMAC authentication validation failed",
                        data={
                            "auth_type": self.auth_type.value,
                            "missing_credential": "secret"
                        }
                    )
                except Exception:
                    pass
                raise ValueError(
                    "HMAC authentication requires 'secret' credential"
                )
        elif self.auth_type == AuthType.JWT:
            if "private_key" not in self.credentials:
                # Log validation error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="JWT authentication validation failed",
                        data={
                            "auth_type": self.auth_type.value,
                            "missing_credential": "private_key"
                        }
                    )
                except Exception:
                    pass
                raise ValueError(
                    "JWT authentication requires 'private_key' credential"
                )
            if not JWT_AVAILABLE:
                # Log validation error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="JWT authentication dependencies not available",
                        data={
                            "auth_type": self.auth_type.value,
                        }
                    )
                except Exception:
                    pass
                raise ValueError(
                    "JWT authentication requires 'PyJWT' and 'cryptography' "
                    "packages"
                )

        # Log successful validation
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_AUTH_VALIDATION,
                level=EventLevel.INFO,
                message="A2A authentication credentials validated successfully",
                data={
                    "auth_type": self.auth_type.value,
                    "credential_count": len(self.credentials)
                }
            )
        except Exception:
            pass


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
        self._oauth2_tokens: Dict[str, Dict[str, Any]] = {}

        logger.debug("Initialized A2A auth manager with secrets")

        # Log initialization
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_AUTH_INITIALIZED,
                level=EventLevel.INFO,
                message="A2A authentication manager initialized",
                data={
                    "secrets_manager_type": type(secrets_manager).__name__,
                    "credentials_loaded": self._credentials_loaded
                }
            )
        except Exception:
            pass

    async def ensure_credentials_loaded(self):
        """Ensure credentials are loaded from secrets manager."""
        # Log credential loading check
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_CREDENTIAL_LOADED,
                level=EventLevel.DEBUG,
                message="Checking if A2A credentials need loading",
                data={
                    "credentials_loaded": self._credentials_loaded,
                    "current_credentials_count": len(self._credentials)
                }
            )
        except Exception:
            pass

        if not self._credentials_loaded:
            await self._load_default_credentials()
            self._credentials_loaded = True

            # Log credentials loaded
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.A2A_CREDENTIAL_LOADED,
                    level=EventLevel.INFO,
                    message="A2A credentials loaded successfully",
                    data={
                        "credentials_count": len(self._credentials),
                        "service_ids": list(self._credentials.keys())
                    }
                )
            except Exception:
                pass

    async def _load_default_credentials(self):
        """Load default credentials from secrets manager only."""
        logger.debug("Loading A2A credentials from secrets manager...")

        # Log credential loading start
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_CREDENTIAL_LOADED,
                level=EventLevel.INFO,
                message="Starting A2A default credentials loading",
                data={"source": "secrets_manager"}
            )
        except Exception:
            pass

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
        loaded_count = 0
        failed_count = 0

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
                    loaded_count += 1

                    # Log successful credential load
                    try:
                        observability = ObservabilityManager.get_instance()
                        observability.log_event(
                            event_type=EventType.A2A_CREDENTIAL_LOADED,
                            level=EventLevel.DEBUG,
                            message="A2A service credentials loaded",
                            data={
                                "service_id": service_id,
                                "auth_type": auth_type.value,
                                "credential_keys": list(credentials.keys())
                            }
                        )
                    except Exception:
                        pass
                else:
                    logger.warning(f"No credentials found for {service_id}")
                    failed_count += 1

            except Exception as e:
                logger.warning(f"Failed to load credentials for {service_id}: {e}")
                failed_count += 1

                # Log credential loading error
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="Failed to load A2A service credentials",
                        data={
                            "service_id": service_id,
                            "auth_type": config.get("auth_type", "unknown"),
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
                except Exception:
                    pass

        # Log overall credential loading results
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_CREDENTIAL_LOADED,
                level=EventLevel.INFO,
                message="A2A default credentials loading completed",
                data={
                    "total_services": len(credential_configs),
                    "loaded_count": loaded_count,
                    "failed_count": failed_count,
                    "loaded_services": list(self._credentials.keys())
                }
            )
        except Exception:
            pass

    async def _load_single_credential(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load a single credential from secrets manager."""
        secret_name = config["secret_name"]

        # Log credential loading attempt
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_CREDENTIAL_LOADED,
                level=EventLevel.DEBUG,
                message="Loading single A2A credential",
                data={
                    "service_id": service_id,
                    "secret_name": secret_name,
                    "auth_type": config["auth_type"].value
                }
            )
        except Exception:
            pass

        try:
            secret_value = await self.secrets_manager.get_secret(secret_name)
            if secret_value:
                auth_type = config["auth_type"]
                if auth_type == AuthType.API_KEY:
                    return {"api_key": secret_value}
                elif auth_type == AuthType.BEARER:
                    return {"token": secret_value}
                elif auth_type == AuthType.HMAC:
                    return {"secret": secret_value}

                # Log successful credential load
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.A2A_CREDENTIAL_LOADED,
                        level=EventLevel.DEBUG,
                        message="Single A2A credential loaded successfully",
                        data={
                            "service_id": service_id,
                            "secret_name": secret_name,
                            "auth_type": auth_type.value
                        }
                    )
                except Exception:
                    pass
            else:
                # Log missing credential
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.WARNING,
                        message="A2A credential not found in secrets",
                        data={
                            "service_id": service_id,
                            "secret_name": secret_name,
                            "auth_type": config["auth_type"].value
                        }
                    )
                except Exception:
                    pass

        except Exception as e:
            # Log credential loading error
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Failed to load single A2A credential",
                    data={
                        "service_id": service_id,
                        "secret_name": secret_name,
                        "auth_type": config["auth_type"].value,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
            logger.warning(f"Failed to load credential {secret_name}: {e}")

        return None

    async def _load_oauth2_credentials(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load OAuth2 credentials from secrets manager."""
        secret_names = config["secret_names"]

        # Log OAuth2 credential loading attempt
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_CREDENTIAL_LOADED,
                level=EventLevel.DEBUG,
                message="Loading OAuth2 A2A credentials",
                data={
                    "service_id": service_id,
                    "secret_names": list(secret_names.keys()),
                    "auth_type": "oauth2"
                }
            )
        except Exception:
            pass

        credentials = {}
        missing_secrets = []

        for cred_key, secret_name in secret_names.items():
            try:
                secret_value = await self.secrets_manager.get_secret(secret_name)
                if secret_value:
                    credentials[cred_key] = secret_value
                else:
                    missing_secrets.append(secret_name)
            except Exception as e:
                logger.warning(f"Failed to load OAuth2 secret {secret_name}: {e}")
                missing_secrets.append(secret_name)

        if missing_secrets:
            # Log missing OAuth2 credentials
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.WARNING,
                    message="Missing OAuth2 A2A credentials",
                    data={
                        "service_id": service_id,
                        "missing_secrets": missing_secrets,
                        "loaded_credentials": list(credentials.keys())
                    }
                )
            except Exception:
                pass
            return None

        # Log successful OAuth2 credential load
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_CREDENTIAL_LOADED,
                level=EventLevel.DEBUG,
                message="OAuth2 A2A credentials loaded successfully",
                data={
                    "service_id": service_id,
                    "credential_count": len(credentials),
                    "credential_keys": list(credentials.keys())
                }
            )
        except Exception:
            pass

        return credentials

    async def _load_jwt_credentials(
        self, service_id: str, config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Load JWT credentials from secrets manager."""
        secret_name = config["secret_name"]
        extra_config = config.get("extra_config", {})

        # Log JWT credential loading attempt
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_CREDENTIAL_LOADED,
                level=EventLevel.DEBUG,
                message="Loading JWT A2A credentials",
                data={
                    "service_id": service_id,
                    "secret_name": secret_name,
                    "auth_type": "jwt",
                    "extra_config_keys": list(extra_config.keys())
                }
            )
        except Exception:
            pass

        try:
            private_key = await self.secrets_manager.get_secret(secret_name)
            if private_key:
                credentials = {"private_key": private_key}
                credentials.update(extra_config)

                # Log successful JWT credential load
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.A2A_CREDENTIAL_LOADED,
                        level=EventLevel.DEBUG,
                        message="JWT A2A credentials loaded successfully",
                        data={
                            "service_id": service_id,
                            "secret_name": secret_name,
                            "credential_keys": list(credentials.keys())
                        }
                    )
                except Exception:
                    pass

                return credentials
            else:
                # Log missing JWT credential
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.WARNING,
                        message="JWT A2A credential not found in secrets",
                        data={
                            "service_id": service_id,
                            "secret_name": secret_name
                        }
                    )
                except Exception:
                    pass

        except Exception as e:
            # Log JWT credential loading error
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Failed to load JWT A2A credential",
                    data={
                        "service_id": service_id,
                        "secret_name": secret_name,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
            logger.warning(f"Failed to load JWT credential {secret_name}: {e}")

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
                username = creds.credentials["username"]
                password = creds.credentials["password"]
                credentials_str = f"{username}:{password}"
                encoded_credentials = base64.b64encode(credentials_str.encode()).decode()
                updated_headers["Authorization"] = f"Basic {encoded_credentials}"
                logger.debug(f"Applied Basic authentication for {agent_id}")

            elif auth_type == AuthType.OAUTH2:
                # For OAuth2, we might need to get a token first
                token = await self._get_oauth2_token(agent_id, creds)
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

    async def _get_oauth2_token(
        self, service_id: str, credentials: AuthCredentials
    ) -> Optional[str]:
        """Get or refresh OAuth2 token."""
        # Log OAuth2 token request
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_AUTH_APPLIED,
                level=EventLevel.DEBUG,
                message="Requesting OAuth2 token for A2A authentication",
                data={
                    "service_id": service_id,
                    "auth_type": "oauth2"
                }
            )
        except Exception:
            pass

        # Check if we have a cached token that's still valid
        cached_token = self._oauth2_tokens.get(service_id)
        if cached_token and cached_token["expires_at"] > time.time():
            # Log cached token usage
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.A2A_AUTH_APPLIED,
                    level=EventLevel.DEBUG,
                    message="Using cached OAuth2 token for A2A authentication",
                    data={
                        "service_id": service_id,
                        "expires_at": cached_token["expires_at"],
                        "time_remaining": cached_token["expires_at"] - time.time()
                    }
                )
            except Exception:
                pass
            return cached_token["access_token"]

        # Request new token
        try:
            creds = credentials.credentials
            token_url = creds.get("token_url", "")
            client_id = creds.get("client_id", "")
            client_secret = creds.get("client_secret", "")
            scope = creds.get("scope", "")

            if not all([token_url, client_id, client_secret]):
                # Log missing OAuth2 configuration
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="Missing OAuth2 configuration for A2A authentication",
                        data={
                            "service_id": service_id,
                            "has_token_url": bool(token_url),
                            "has_client_id": bool(client_id),
                            "has_client_secret": bool(client_secret)
                        }
                    )
                except Exception:
                    pass
                logger.error(f"Missing OAuth2 configuration for {service_id}")
                return None

            # Make token request
            import aiohttp
            async with aiohttp.ClientSession() as session:
                data = {
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
                if scope:
                    data["scope"] = scope

                async with session.post(token_url, data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        access_token = token_data.get("access_token")
                        expires_in = token_data.get("expires_in", 3600)

                        if access_token:
                            # Cache the token
                            self._oauth2_tokens[service_id] = {
                                "access_token": access_token,
                                "expires_at": time.time() + expires_in - 60,  # 60s buffer
                            }

                            # Log successful OAuth2 token acquisition
                            try:
                                observability = ObservabilityManager.get_instance()
                                observability.log_event(
                                    event_type=EventType.A2A_AUTH_APPLIED,
                                    level=EventLevel.INFO,
                                    message=(
                                        "OAuth2 token acquired successfully "
                                        "for A2A authentication"
                                    ),
                                    data={
                                        "service_id": service_id,
                                        "expires_in": expires_in,
                                        "token_url": token_url
                                    }
                                )
                            except Exception:
                                pass

                            return access_token
                        else:
                            # Log missing access token in response
                            try:
                                observability = ObservabilityManager.get_instance()
                                observability.log_event(
                                    event_type=EventType.ERROR_RETRY_ATTEMPTED,
                                    level=EventLevel.ERROR,
                                    message="OAuth2 response missing access token",
                                    data={
                                        "service_id": service_id,
                                        "token_url": token_url,
                                        "response_keys": list(token_data.keys())
                                    }
                                )
                            except Exception:
                                pass
                    else:
                        # Log OAuth2 request failure
                        try:
                            observability = ObservabilityManager.get_instance()
                            observability.log_event(
                                event_type=EventType.ERROR_RETRY_ATTEMPTED,
                                level=EventLevel.ERROR,
                                message="OAuth2 token request failed",
                                data={
                                    "service_id": service_id,
                                    "token_url": token_url,
                                    "status_code": response.status,
                                    "response_text": await response.text()
                                }
                            )
                        except Exception:
                            pass
                        logger.error(
                            f"OAuth2 token request failed for {service_id}: "
                            f"{response.status}"
                        )

        except Exception as e:
            # Log OAuth2 token request error
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Exception during OAuth2 token request",
                    data={
                        "service_id": service_id,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
            logger.error(f"Failed to get OAuth2 token for {service_id}: {e}")

        return None

    def _generate_hmac_signature(
        self, secret: str, method: str, url: str, body: str
    ) -> str:
        """Generate HMAC signature for request."""
        # Log HMAC signature generation
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_AUTH_APPLIED,
                level=EventLevel.DEBUG,
                message="Generating HMAC signature for A2A authentication",
                data={
                    "method": method,
                    "url": url,
                    "body_length": len(body)
                }
            )
        except Exception:
            pass

        try:
            timestamp = str(int(time.time()))
            string_to_sign = f"{method}\n{url}\n{body}\n{timestamp}"

            signature = hmac.new(
                secret.encode(), string_to_sign.encode(), hashlib.sha256
            ).hexdigest()

            # Log successful HMAC signature generation
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.A2A_AUTH_APPLIED,
                    level=EventLevel.DEBUG,
                    message="HMAC signature generated successfully",
                    data={
                        "method": method,
                        "url": url,
                        "timestamp": timestamp,
                        "signature_length": len(signature)
                    }
                )
            except Exception:
                pass

            return signature

        except Exception as e:
            # Log HMAC signature generation error
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Failed to generate HMAC signature",
                    data={
                        "method": method,
                        "url": url,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
            logger.error(f"Failed to generate HMAC signature: {e}")
            return ""

    def _generate_jwt_token(self, credentials: AuthCredentials) -> Optional[str]:
        """Generate JWT token."""
        # Log JWT token generation
        try:
            observability = ObservabilityManager.get_instance()
            observability.log_event(
                event_type=EventType.A2A_AUTH_APPLIED,
                level=EventLevel.DEBUG,
                message="Generating JWT token for A2A authentication",
                data={
                    "credential_keys": list(credentials.credentials.keys())
                }
            )
        except Exception:
            pass

        try:
            import jwt

            creds = credentials.credentials
            private_key = creds.get("private_key", "")
            algorithm = creds.get("algorithm", "RS256")
            issuer = creds.get("issuer", "")
            subject = creds.get("subject", "")
            audience = creds.get("audience", "")
            expires_in = creds.get("expires_in", 3600)

            if not private_key:
                # Log missing private key
                try:
                    observability = ObservabilityManager.get_instance()
                    observability.log_event(
                        event_type=EventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="Missing private key for JWT token generation",
                        data={
                            "algorithm": algorithm,
                            "has_issuer": bool(issuer),
                            "has_subject": bool(subject),
                            "has_audience": bool(audience)
                        }
                    )
                except Exception:
                    pass
                logger.error("Missing private key for JWT token generation")
                return None

            # Create JWT payload
            now = int(time.time())
            payload = {
                "iat": now,
                "exp": now + expires_in,
            }

            if issuer:
                payload["iss"] = issuer
            if subject:
                payload["sub"] = subject
            if audience:
                payload["aud"] = audience

            # Generate token
            token = jwt.encode(payload, private_key, algorithm=algorithm)

            # Log successful JWT token generation
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.A2A_AUTH_APPLIED,
                    level=EventLevel.INFO,
                    message="JWT token generated successfully",
                    data={
                        "algorithm": algorithm,
                        "expires_in": expires_in,
                        "has_issuer": bool(issuer),
                        "has_subject": bool(subject),
                        "has_audience": bool(audience),
                        "token_length": len(token)
                    }
                )
            except Exception:
                pass

            return token

        except Exception as e:
            # Log JWT token generation error
            try:
                observability = ObservabilityManager.get_instance()
                observability.log_event(
                    event_type=EventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Failed to generate JWT token",
                    data={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "algorithm": (
                            creds.get("algorithm", "RS256")
                            if 'creds' in locals() else "unknown"
                        )
                    }
                )
            except Exception:
                pass
            logger.error(f"Failed to generate JWT token: {e}")

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
