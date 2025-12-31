# =============================================================================
# FORMATION - OPERATIONAL LIFECYCLE MANAGEMENT
# =============================================================================
# Title:        Formation - Muxi Runtime Operational Platform
# Description:  Handles configuration loading, service initialization, and overlord lifecycle
# Role:         Operations layer that manages infrastructure and coordinates services
# Usage:        formation = Formation(); formation.load("config.afs"); muxi = formation.start_overlord()
# Author:       Muxi Framework Team
#
# The Formation manages the operational lifecycle of the Muxi runtime, handling all
# infrastructure concerns and service coordination. It separates operational concerns
# from intelligence concerns, providing a clean interface between platform management
# and intelligent decision-making.
#
# Usage Pattern:
#
#   from muxi.runtime import Formation  # noqa: E402
#
#   formation = Formation()
#   formation.load("my-formation.afs")
#   muxi = formation.start_overlord()
#
#   # Use the intelligence
#   response = muxi.chat("Hello!")
#
#   # Cleanup
#   formation.stop_overlord()    # Graceful shutdown
#   # formation.kill_overlord()  # Immediate shutdown
#   formation.shutdown()         # Full cleanup
#
# =============================================================================

import asyncio
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
import yaml
from pathlib import Path
import os
import re
import copy
import shlex
import threading
import atexit
import sys


# Configuration imports
from .config.validation import (
    validate_formation,
    validate_user_credentials_requirements_async,
)
from .config.formation_loader import FormationLoader

# Service imports
from ..services import observability
from ..services.secrets.secrets_manager import SecretsManager
from ..services.mcp.transports.base import (
    MCPConnectionError,
    MCPRequestError,
    MCPTimeoutError,
    MCPCancelledError,
)

# Validation imports
from ..utils import DependencyValidator

# Async operation imports
from ..utils.async_operation_manager import get_operation_manager, execute_with_timeout
from ..datatypes.async_operations import TimeoutConfig, CancellationToken, OperationStatus

# Retry logic imports
from ..utils.retry_manager import get_retry_manager
from ..datatypes.retry import (
    RetryConfig,
    RetryStrategy,
    NetworkTransientError,
    ServiceTransientError,
)

# Exception imports
from ..datatypes.exceptions import (
    ConfigurationNotFoundError,
    ConfigurationValidationError,
    ConfigurationLoadError,
    OverlordImportError,
    OverlordStartupError,
    OverlordStateError,
    DependencyValidationError,
    RegistryConfigurationError,
    add_error_context,
)

# Utility imports
from .utils import generate_api_key
from ..utils.user_dirs import set_formation_id

# Type checking imports
if TYPE_CHECKING:
    from .server import FormationServer

# Formation initialization imports
from .initialization import (
    initialize_observability,
    enable_conversation_logging,
    initialize_llm_config,
    initialize_memory_systems,
    initialize_background_services,
    initialize_mcp_services,
    initialize_clarification_config,
    initialize_document_processing_config,
    load_agents_from_configuration,
)


class Formation:
    """
    Formation - Operational Platform for Muxi Runtime

    Handles all operational concerns including configuration loading, service
    initialization, and overlord lifecycle management. Separates infrastructure
    concerns from intelligence concerns.

    The Formation acts as the operational platform that:
    - Loads and validates formation configurations
    - Initializes and coordinates all services
    - Creates and manages overlord instances
    - Handles resource cleanup and shutdown
    """

    def __init__(
        self,
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize Formation platform.

        Sets up the operational foundation for the Muxi runtime without
        loading any specific configuration. Call load() to load a formation
        configuration and start_overlord() to boot the intelligence layer.

        Args:
            timeout_config: Optional timeout configuration for async operations
            retry_config: Optional retry configuration for transient failures
        """
        # Core state
        self.config: Optional[Dict[str, Any]] = None
        self._overlord = None  # Will hold the running overlord instance

        # Operational services
        self.formation_id: str = "default-formation"
        self._is_running: bool = False

        # Service management
        self.secrets_manager: Optional[SecretsManager] = None
        self._formation_path: Optional[str] = None

        # Async operation management
        self._timeout_config = timeout_config or TimeoutConfig()
        self._operation_manager = get_operation_manager()
        self._formation_cancellation_token: Optional[CancellationToken] = None

        # Retry logic management
        self._retry_config = retry_config or RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=1.0,
            max_delay=30.0,
        )
        self._retry_manager = get_retry_manager()

        # Built-in MCP registration tracking
        self._builtin_mcp_task: Optional[asyncio.Task] = None

        # Formation server instance tracking
        self._formation_server: Optional["FormationServer"] = None

        # Thread safety for config modifications
        self._config_lock = threading.Lock()

        # Async lock for config modifications (async operations)
        # Initialized in load() since asyncio.Lock requires event loop
        self._async_config_lock: Optional[asyncio.Lock] = None

        # Dependency validation
        self._dependency_validator = DependencyValidator()

        # Service configuration (prepared for overlord handoff)
        self._configured_services: Dict[str, Any] = {}
        self._api_keys: Dict[str, str] = {}
        self._generated_api_keys: Dict[str, str] = {}

        # Individual service configurations (prepared during setup)
        self._llm_config: Dict[str, Any] = {}
        self._memory_config: Dict[str, Any] = {}
        self._mcp_config: Dict[str, Any] = {}
        self._a2a_config: Dict[str, Any] = {}
        self._logging_config: Dict[str, Any] = {}
        self._clarification_config: Dict[str, Any] = {}
        self._document_processing_config: Dict[str, Any] = {}
        self._scheduler_config: Dict[str, Any] = {}
        self._runtime_config: Dict[str, Any] = {}
        self._agents_config: list = []

        # Track secrets in use
        self._secrets_in_use: set[str] = set()

        # Track secret placeholder mappings
        self._secret_placeholders: Dict[str, str] = {}

        # Registry of MCP servers that use user credentials
        self._mcp_servers_with_user_credentials: Dict[str, Dict[str, Any]] = {}

    def set_secrets_manager(self, secrets_manager: SecretsManager) -> None:
        """
        Inject a pre-configured SecretsManager instance.

        This method enables dependency injection for testing and advanced scenarios
        where a custom SecretsManager configuration is needed.

        Args:
            secrets_manager: Pre-configured SecretsManager instance
        """
        self.secrets_manager = secrets_manager
        # Init event - no observability emission during init phase (replaced by InitEventFormatter)

    def _get_primary_registry_url(self, a2a_config: Dict[str, Any]) -> Optional[str]:
        """
        Get the primary registry URL from A2A configuration.

        Preference order:
        1. First URL from inbound registries (preferred for receiving requests)
        2. First URL from outbound registries (fallback)
        3. None if no registries configured

        Args:
            a2a_config: The A2A configuration dictionary

        Returns:
            The primary registry URL or None if not configured

        Raises:
            ValueError: If registry URL is malformed
        """
        # Check inbound registries first (preferred)
        inbound_registries = a2a_config.get("inbound", {}).get("registries", [])
        if inbound_registries and inbound_registries[0]:
            url = inbound_registries[0]
            # Validate URL format
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError(
                    f"Invalid registry URL format: {url}. Must start with http:// or https://"
                )
            return url

        # Fall back to outbound registries
        outbound_registries = a2a_config.get("outbound", {}).get("registries", [])
        if outbound_registries and outbound_registries[0]:
            url = outbound_registries[0]
            # Validate URL format
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError(
                    f"Invalid registry URL format: {url}. Must start with http:// or https://"
                )
            return url

        return None

    def _is_external_registry_enabled(self, a2a_config: Dict[str, Any]) -> bool:
        """
        Check if external registry is enabled based on configuration.

        External registry is considered enabled if either inbound or outbound
        registries are configured.

        Args:
            a2a_config: The A2A configuration dictionary

        Returns:
            True if external registry should be enabled
        """
        return bool(a2a_config.get("inbound", {}).get("registries")) or bool(
            a2a_config.get("outbound", {}).get("registries")
        )

    def _get_inbound_auth_key(self, inbound_config: Dict[str, Any]) -> Optional[str]:
        """
        Extract the authentication key from inbound configuration.

        Args:
            inbound_config: The inbound configuration dictionary

        Returns:
            The authentication key based on auth type, or None if not configured
        """
        auth_config = inbound_config.get("auth", {})
        auth_type = auth_config.get("type", "none")

        if auth_type == "bearer":
            return auth_config.get("token")
        elif auth_type == "api_key":
            return auth_config.get("key")
        elif auth_type == "basic":
            # For basic auth, the server handles username/password separately
            return None
        elif auth_type == "custom":
            # Custom auth uses headers dict
            return None
        else:
            # For "none" or unknown types
            return None

    async def load(self, config_path: str) -> None:
        """
        Load and validate formation configuration (async).

        This is an asynchronous coroutine that must be awaited when called.

        Loads a formation configuration from file or directory, validates the
        schema, and prepares all services for initialization. Does not start
        services - call start_overlord() to boot the intelligence layer.

        Args:
            config_path: Path to formation YAML file or directory structure

        Raises:
            ConfigurationNotFoundError: If configuration file/directory does not exist
            ConfigurationValidationError: If configuration is invalid
            ConfigurationLoadError: If configuration cannot be loaded
            DependencyValidationError: If required dependencies are missing

        Example:
            formation = Formation()
            await formation.load("path/to/formation.afs")  # Must await!
        """
        if self._is_running:
            raise OverlordStateError(
                "running",
                "stopped",
                {"operation": "load_configuration", "config_path": config_path},
            )

        try:
            # Import at start of method for availability everywhere
            from ..datatypes.observability import InitEventFormatter
            from ..services import observability

            # Disable observability during initialization (prevent JSON mixing with formatted output)
            observability.disable()

            # Normalize and validate config path (file or directory)
            normalized_path = self._normalize_config_path(config_path)

            # Store formation path for secrets management
            self._formation_path = normalized_path

            # Initialize secrets manager with directory path
            # If normalized_path is a file, use its directory; otherwise use the path itself

            # Initialize SecretsManager if not already injected via dependency injection
            if not hasattr(self, "secrets_manager") or self.secrets_manager is None:
                # Initialize secrets_dir with default to prevent UnboundLocalError
                secrets_dir = normalized_path
                try:
                    if os.path.isfile(normalized_path):
                        secrets_dir = os.path.dirname(normalized_path)
                    else:
                        secrets_dir = normalized_path

                    # Ensure the secrets directory exists and is accessible
                    if not os.path.exists(secrets_dir):
                        os.makedirs(secrets_dir, exist_ok=True)

                    self.secrets_manager = SecretsManager(secrets_dir)

                    # Initialize encryption immediately so secrets can be used during config loading
                    await self.secrets_manager.initialize_encryption()

                    # Init event - no observability emission during init phase (replaced by InitEventFormatter)
                    pass

                except Exception as e:
                    # Log the SecretsManager initialization failure
                    observability.observe(
                        event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=observability.EventLevel.ERROR,
                        data={
                            "error": str(e),
                            "secrets_dir": secrets_dir,
                            "config_path": config_path,
                        },
                        description=f"Failed to initialize SecretsManager: {str(e)}",
                    )
                    raise ConfigurationLoadError(
                        f"Failed to initialize SecretsManager for formation at {secrets_dir}: {str(e)}",
                        {"config_path": config_path, "secrets_dir": secrets_dir},
                    )
            else:
                # SecretsManager was already injected
                # Init event - no observability emission during init phase (replaced by InitEventFormatter)
                pass

            # Validate configuration (fail fast with detailed messages)
            validation_result = self._validate_config(normalized_path)
            if not validation_result["is_valid"]:
                raise ConfigurationValidationError(
                    [validation_result["detailed_report"]], {"config_path": normalized_path}
                )

            # Log warnings if any
            if validation_result["warnings"]:
                raise ConfigurationValidationError(
                    [validation_result["detailed_report"]],
                    {"config_path": normalized_path, "type": "warnings"},
                )

            # Load configuration asynchronously
            self.config = await self._load_config(config_path, normalized_path)

            # Validate user credentials requirements (ensure database is configured if needed)
            try:
                await validate_user_credentials_requirements_async(
                    self.config, self.secrets_manager
                )
            except ValueError as e:
                raise ConfigurationValidationError(
                    [str(e)],
                    {"config_path": normalized_path, "validation_type": "user_credentials"},
                ) from e

            # Validate dependencies before proceeding
            dependency_result = self._dependency_validator.validate_formation_dependencies(
                self.config
            )
            if not dependency_result.is_valid:
                # Generate helpful error message with installation suggestions
                suggestions = self._dependency_validator.get_installation_suggestions(
                    dependency_result.missing_dependencies
                )
                error_details = {
                    "config_path": normalized_path,
                    "errors": dependency_result.errors,
                    "missing_dependencies": [
                        dep.name for dep in dependency_result.missing_dependencies
                    ],
                    "installation_suggestions": suggestions,
                }
                raise DependencyValidationError(dependency_result.errors, error_details)

            # Set formation ID (check both 'id' and 'formation_id' for compatibility)
            # Normalize to lowercase and strip whitespace
            formation_id = self.config.get("id") or self.config.get(
                "formation_id", "default-formation"
            )
            self.formation_id = formation_id.lower().strip()
            set_formation_id(self.formation_id)

            # Ensure formation_id is in config for Overlord
            self.config["formation_id"] = self.formation_id

            # Initialize async config lock for thread-safe config modifications from async handlers
            if self._async_config_lock is None:
                self._async_config_lock = asyncio.Lock()

            # Prepare services (but don't start them yet)
            self._prepare_services()

            # Initialize all services (observability first!)
            await self._initialize_services()

        except ConfigurationNotFoundError as e:
            # Clean up and show formatted error
            self.config = None
            self.secrets_manager = None
            from ..datatypes.observability import InitFailureInfo
            path = str(e).replace("Formation configuration not found: ", "")
            failure = InitFailureInfo(
                component="Could not load formation configuration",
                problem=f"Configuration file not found at: {path}",
                context="",
                causes=[
                    "The file path is incorrect or misspelled",
                    "The formation directory doesn't exist yet",
                    "The formation.afs file is missing from the directory"
                ],
                fixes=[
                    f"Double-check the path: {path}",
                    "Verify the path you passed to formation.load()",
                    "Make sure formation.afs exists in that directory"
                ],
                technical=str(e)
            )
            print("\n" + InitEventFormatter.format_fail(failure))
            raise e
        except (
            ConfigurationValidationError,
            ConfigurationLoadError,
            DependencyValidationError,
            OverlordStateError,
        ) as e:
            # Clean up and show formatted error
            self.config = None
            self.secrets_manager = None
            from ..datatypes.observability import InitFailureInfo
            error_msg = str(e).split('\n')[0].replace("❌ ", "")
            failure = InitFailureInfo(
                component="Formation configuration is invalid",
                problem=error_msg,
                context="",
                causes=[
                    "The YAML syntax is incorrect",
                    "Required fields are missing from your configuration",
                    "Field values don't match expected format"
                ],
                fixes=[
                    "Check your formation.afs for syntax errors (indentation, colons, quotes)",
                    "Compare with a working example formation",
                    "Make sure all required fields are present (llm, agents, etc.)"
                ],
                technical=str(e)
            )
            print("\n" + InitEventFormatter.format_fail(failure))
            raise e
        except Exception as e:
            # Clean up on failure - convert unexpected error to FormationError
            self.config = None
            self.secrets_manager = None
            formation_error = add_error_context(
                e,
                {
                    "operation": "load_configuration",
                    "config_path": config_path,
                    "formation_id": self.formation_id,
                },
            )
            raise formation_error from e

    def _normalize_config_path(self, config_path: str) -> str:
        """
        Normalize config path to handle both file and directory inputs.

        Args:
            config_path: Path to formation YAML file or directory

        Returns:
            str: Normalized path to formation.afs file

        Raises:
            ConfigurationNotFoundError: If neither file nor directory exists
            ConfigurationValidationError: If directory exists but has no formation.afs
        """

        if not os.path.exists(config_path):
            raise ConfigurationNotFoundError(
                config_path, {"operation": "normalize_config_path", "attempted_path": config_path}
            )

        # If it's a file, return as-is
        if os.path.isfile(config_path):
            if not config_path.endswith((".afs", ".yaml", ".yml")):
                raise ConfigurationValidationError(
                    [f"Formation file must be AFS/YAML format (.afs, .yaml, or .yml): {config_path}"],
                    {"config_path": config_path, "operation": "validate_file_extension"},
                )
            return config_path

        # If it's a directory, look for formation config file
        # Priority: .afs (preferred) > .yaml > .yml
        if os.path.isdir(config_path):
            formation_file_afs = os.path.join(config_path, "formation.afs")
            if os.path.isfile(formation_file_afs):
                return formation_file_afs

            formation_file = os.path.join(config_path, "formation.yaml")
            if os.path.isfile(formation_file):
                return formation_file

            # Try formation.yml as fallback
            formation_file_yml = os.path.join(config_path, "formation.yml")
            if os.path.isfile(formation_file_yml):
                return formation_file_yml

            raise ConfigurationNotFoundError(
                config_path,
                {
                    "operation": "find_formation_config",
                    "directory_checked": config_path,
                    "suggestion": (
                        f"Create a formation.afs file in the directory '{config_path}' or "
                        "provide the direct path to your formation configuration file"
                    ),
                    "example": f"Try: formation.load('{config_path}/formation.afs') or create the missing file",
                },
            )

        raise ConfigurationValidationError(
            [f"Config path must be a file or directory, got: {type(config_path).__name__}"],
            {
                "config_path": config_path,
                "operation": "validate_config_path",
                "suggestion": "Provide either a path to a formation.afs file or a directory containing formation.afs",
                "examples": [
                    "formation.load('path/to/formation.afs')",
                    "formation.load('path/to/formation/directory')",
                ],
            },
        )

    def _validate_config(self, config_path: str) -> Dict[str, Any]:
        """
        Validate formation configuration.

        Args:
            config_path: Path to formation configuration

        Returns:
            Dict containing validation results
        """
        try:
            validation_result = validate_formation(config_path, self.secrets_manager)

            return {
                "is_valid": validation_result.is_valid,
                "errors": validation_result.errors,
                "warnings": validation_result.warnings,
                "suggestions": validation_result.suggestions,
                "summary": validation_result.summary(),
                "detailed_report": validation_result.detailed_report(),
            }

        except Exception as e:
            return {
                "is_valid": False,
                "errors": [str(e)],
                "warnings": [],
                "suggestions": [],
                "summary": f"❌ Validation failed: {str(e)}",
                "detailed_report": f"Validation failed with exception: {str(e)}",
            }

    def _load_config_sync(self, config_path: str, normalized_config_path: str) -> Dict[str, Any]:
        """
        Load formation configuration from file synchronously.

        Args:
            config_path: Original path passed to load() (directory or file)
            normalized_config_path: Normalized path to formation.afs file

        Returns:
            Loaded configuration dictionary

        Raises:
            ConfigurationLoadError: If configuration loading fails
        """

        try:
            if os.path.isdir(config_path):
                # Modular formation - discover agents from directory
                return self._load_modular_formation_sync(config_path)
            else:
                # Flattened formation - load directly
                with open(normalized_config_path, "r") as f:
                    config = yaml.safe_load(f)

                # Interpolate secrets if we have a secrets manager
                if self.secrets_manager:
                    # Do secret interpolation synchronously
                    config = self._interpolate_secrets_sync(config)

                return config

        except Exception as e:
            raise ConfigurationLoadError(
                f"Failed to load configuration from {config_path}",
                {"config_path": config_path, "error": str(e)},
            )

    def _load_modular_formation_sync(self, directory_path: str) -> Dict[str, Any]:
        """
        Load a modular formation synchronously by discovering component files.

        Args:
            directory_path: Path to the formation directory

        Returns:
            Complete formation configuration with discovered components
        """
        formation_dir = Path(directory_path)

        # Load main formation config file (priority: .afs > .yaml > .yml)
        main_config_path = formation_dir / "formation.afs"
        if not main_config_path.exists():
            main_config_path = formation_dir / "formation.yaml"
        if not main_config_path.exists():
            main_config_path = formation_dir / "formation.yml"

        if not main_config_path.exists():
            raise FileNotFoundError(f"Main formation config (formation.afs/yaml/yml) not found in directory: {directory_path}")

        with open(main_config_path, "r") as f:
            config = yaml.safe_load(f)

        # Interpolate secrets in main config
        if self.secrets_manager:
            config = self._interpolate_secrets_sync(config)

        # Discover agents from agents/ directory
        agents_dir = formation_dir / "agents"
        if agents_dir.exists() and agents_dir.is_dir():
            if "agents" not in config:
                config["agents"] = []

            # Load each agent file (support .afs, .yaml, .yml)
            for agent_file in sorted(agents_dir.glob("*.afs")) + sorted(agents_dir.glob("*.yaml")) + sorted(agents_dir.glob("*.yml")):
                try:
                    with open(agent_file, "r") as f:
                        agent_config = yaml.safe_load(f)

                    # Interpolate secrets in agent config
                    if self.secrets_manager:
                        agent_config = self._interpolate_secrets_sync(agent_config)

                    # Ensure agent has an ID
                    if "id" not in agent_config:
                        agent_config["id"] = agent_file.stem

                    # Check if agent is active (default to True)
                    if agent_config.get("active", True):
                        config["agents"].append(agent_config)

                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"agent_file": str(agent_file), "error": str(e)},
                        description=f"Failed to load agent file {agent_file}: {e}",
                    )
                    continue

        # NOTE: MCP server discovery is now handled by FormationLoader
        # This eliminates duplicate MCP server registration that was happening
        # when both Formation and FormationLoader processed the mcp/ directory

        # Discover A2A services from a2a/ directory
        a2a_dir = formation_dir / "a2a"
        if a2a_dir.exists() and a2a_dir.is_dir():
            # Initialize A2A structure if not present
            if "a2a" not in config:
                config["a2a"] = {}
            if "outbound" not in config["a2a"]:
                config["a2a"]["outbound"] = {}
            if "services" not in config["a2a"]["outbound"]:
                config["a2a"]["outbound"]["services"] = []

            # Load each A2A service file (support .afs, .yaml, .yml)
            for a2a_file in sorted(a2a_dir.glob("*.afs")) + sorted(a2a_dir.glob("*.yaml")) + sorted(a2a_dir.glob("*.yml")):
                try:
                    with open(a2a_file, "r") as f:
                        a2a_config = yaml.safe_load(f)

                    # Interpolate secrets in A2A config
                    if self.secrets_manager:
                        a2a_config = self._interpolate_secrets_sync(a2a_config)

                    # Ensure A2A service has an ID
                    if "id" not in a2a_config:
                        a2a_config["id"] = a2a_file.stem

                    # Check if service is active (default to True)
                    if a2a_config.get("active", True):
                        config["a2a"]["outbound"]["services"].append(a2a_config)
                        pass  # REMOVED: init-phase observe() call

                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"a2a_file": str(a2a_file), "error": str(e)},
                        description=f"Failed to load A2A file {a2a_file}: {e}",
                    )
                    continue

        return config

    def _interpolate_secrets_sync(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synchronously interpolate secrets in configuration.

        Args:
            config: Configuration dictionary with potential secret references

        Returns:
            Configuration with secrets interpolated
        """
        interpolated_secrets = set()

        def interpolate_value(value):
            """Recursively interpolate secrets in a value."""
            if isinstance(value, str):
                # Look for ${{ secrets.SECRET_NAME }} pattern
                pattern = r"\$\{\{\s*secrets\.(\w+)\s*\}\}"
                matches = re.findall(pattern, value)

                for secret_name in matches:
                    try:
                        secret_value = self.secrets_manager.get_secret_sync(secret_name)
                        if secret_value is None:
                            raise ValueError(
                                f"Secret '{secret_name}' not found in secrets manager. "
                                f"Please add it using: python -m muxi.utils.secrets add {secret_name}"
                            )
                        value = value.replace(f"${{{{ secrets.{secret_name} }}}}", secret_value)
                        interpolated_secrets.add(secret_name)
                    except ValueError:
                        # Re-raise ValueError for missing secrets
                        raise
                    except Exception as e:
                        # Fail fast on any other error
                        raise RuntimeError(
                            f"Failed to retrieve secret '{secret_name}': {type(e).__name__}: {str(e)}"
                        )

                return value
            elif isinstance(value, dict):
                return {k: interpolate_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [interpolate_value(item) for item in value]
            else:
                return value

        # Deep copy to avoid modifying original
        result = interpolate_value(copy.deepcopy(config))

        # Log final success only if we interpolated any secrets
        if interpolated_secrets:
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_COMPLETED,
                level=observability.EventLevel.INFO,
                description="Secret interpolation completed successfully for formation configuration",
                data={
                    "operation_type": "formation_interpolation",
                    "secret_count": len(interpolated_secrets),
                    "secrets_interpolated": sorted(list(interpolated_secrets)),
                    "success": True,
                },
            )

        return result

    async def _load_config(self, config_path: str, normalized_config_path: str) -> Dict[str, Any]:
        """
        Load formation configuration from file with timeout and retry support.

        Args:
            config_path: Original path passed to load() (directory or file)
            normalized_config_path: Normalized path to formation.afs file

        Returns:
            Loaded configuration dictionary

        Raises:
            ConfigurationLoadError: If configuration loading fails after retries
        """

        async def _load_operation():
            """Load configuration with timeout and error handling for retry logic."""

            # Determine the correct path for FormationLoader
            # If original config_path was a directory, use it directly for modular loading

            if os.path.isdir(config_path):
                # Modular formation - pass directory path
                loader_path = config_path
            else:
                # Flattened formation - use normalized file path
                loader_path = normalized_config_path

            async def _timeout_operation():
                formation_loader = FormationLoader()
                config, secrets_in_use, placeholder_registry = await formation_loader.load(
                    loader_path, self.secrets_manager
                )
                # Store the secrets in use set
                self._secrets_in_use = secrets_in_use
                # Store the placeholder registry
                self._secret_placeholders = placeholder_registry
                return config

            result = await execute_with_timeout(
                _timeout_operation,
                operation_type="config_load",
                description=f"Loading formation configuration from {config_path}",
                timeout=self._timeout_config.config_load_timeout,
                cancellation_token=self._formation_cancellation_token,
            )

            # Check if operation succeeded (handle both enum and string status)
            status_value = (
                result.status.value if isinstance(result.status, OperationStatus) else result.status
            )
            if status_value == "completed" and result.result is not None:
                # Operation completed successfully with a result
                return result.result

            if not result.is_success:
                if result.was_timeout:
                    raise NetworkTransientError(
                        f"Configuration loading timed out after {result.elapsed_time:.1f}s",
                        retry_after=2.0,
                        details={
                            "config_path": config_path,
                            "timeout": self._timeout_config.config_load_timeout,
                            "suggestion": "Try increasing config_load_timeout or check file system performance",
                        },
                    )
                elif result.was_cancelled:
                    raise ConfigurationLoadError(
                        "❌ Configuration loading was cancelled",
                        {
                            "config_path": config_path,
                            "suggestion": "Operation was cancelled - check if Formation is being shut down",
                        },
                    )
                else:
                    # Check if we have an error message
                    if result.error:
                        error_str = result.error.lower()
                        if any(
                            pattern in error_str
                            for pattern in ["network", "connection", "timeout", "temporary"]
                        ):
                            raise NetworkTransientError(
                                f"Configuration loading failed: {result.error}",
                                details={
                                    "config_path": config_path,
                                    "original_error": result.error,
                                },
                            )
                        else:
                            # Non-retryable error
                            raise ConfigurationLoadError(
                                f"❌ Configuration loading failed: {result.error}",
                                {"config_path": config_path},
                            )
                    else:
                        # No error message but operation failed
                        raise ConfigurationLoadError(
                            f"❌ Configuration loading failed with status: {result.status}",
                            {
                                "config_path": config_path,
                                "status": (
                                    result.status.value
                                    if hasattr(result.status, "value")
                                    else str(result.status)
                                ),
                                "is_success": result.is_success,
                                "result": result.result,
                                "metadata": result.metadata,
                            },
                        )

            return result.result

        # Use retry logic for configuration loading
        retry_result = await self._retry_manager.execute_with_retry(
            _load_operation, config=self._retry_config, operation_name="configuration_loading"
        )

        if retry_result.success:
            if retry_result.was_retried:
                print(
                    f"✅ Configuration loaded successfully after {retry_result.total_attempts} attempts"
                )
            return retry_result.result
        else:
            error = retry_result.error

            # Convert retry failure to ConfigurationLoadError with enhanced context
            if isinstance(error, NetworkTransientError):
                raise ConfigurationLoadError(
                    f"❌ Configuration loading failed after {retry_result.total_attempts} attempts: {error}",
                    {
                        "config_path": config_path,
                        "attempts": retry_result.total_attempts,
                        "total_time": f"{retry_result.total_elapsed_time:.1f}s",
                        "suggestion": error.details.get(
                            "suggestion", "Check network connectivity and file accessibility"
                        ),
                        "next_steps": [
                            f"Increase timeout: Formation(timeout_config=TimeoutConfig("
                            f"config_load_timeout={self._timeout_config.config_load_timeout * 2}))",
                            "Check if the configuration file is accessible",
                            "Verify network connectivity if loading from remote location",
                            f"Increase retry attempts: Formation(retry_config=RetryConfig("
                            f"max_attempts={self._retry_config.max_attempts * 2}))",
                        ],
                    },
                )
            else:
                # Re-raise the original error if it's already a ConfigurationLoadError
                if isinstance(error, ConfigurationLoadError):
                    raise error
                else:
                    raise ConfigurationLoadError(
                        f"❌ Configuration loading failed: {error}",
                        {
                            "config_path": config_path,
                            "attempts": retry_result.total_attempts,
                            "suggestion": "Check configuration file format and accessibility",
                        },
                    ) from error

    def _prepare_services(self) -> None:
        """
        Prepare services based on configuration without starting them.

        This analyzes the configuration and prepares service configurations
        that will be passed to the overlord during startup.
        """
        if not self.config:
            raise RuntimeError("No configuration loaded. Call load() first.")

        # Generate API keys
        self._setup_auth()

        # Prepare and validate service configurations
        self._setup_llm_config()
        self._setup_memory_config()
        self._setup_mcp_config()
        self._setup_a2a_config()
        self._setup_logging_config()
        self._setup_clarification_config()
        self._setup_document_processing_config()
        self._setup_scheduler_config()
        self._setup_runtime_config()
        self._setup_agents_config()

        # Create standardized configuration objects
        from ..datatypes.schema import MCPServiceSchema, A2AServiceSchema

        # Create MCP configuration object
        mcp_config_obj = None
        if self._mcp_config:
            try:
                mcp_config_obj = MCPServiceSchema(
                    enabled=self._mcp_config.get("enabled", True),
                    max_concurrent_servers=self._mcp_config.get("max_concurrent_servers", 10),
                    default_timeout=self._mcp_config.get("default_timeout", 30.0),
                    retry_attempts=self._mcp_config.get("retry_attempts", 3),
                    retry_delay=self._mcp_config.get("retry_delay", 1.0),
                )
                mcp_config_obj.validate()
            except Exception as e:
                print(
                    f"Warning: Invalid MCP configuration, using defaults. "
                    f"Validation error: {str(e)}. "
                    f"Config values: max_concurrent_servers={self._mcp_config.get('max_concurrent_servers')}, "
                    f"default_timeout={self._mcp_config.get('default_timeout')}, "
                    f"retry_attempts={self._mcp_config.get('retry_attempts')}, "
                    f"retry_delay={self._mcp_config.get('retry_delay')}",
                    flush=True,
                )
                mcp_config_obj = MCPServiceSchema()

        # Create A2A configuration object
        a2a_config_obj = None
        if self._a2a_config:
            try:
                # Collect registries from both inbound and outbound
                all_registries = []

                # Add outbound registries
                outbound_registries = self._a2a_config.get("outbound", {}).get("registries", [])
                for reg in outbound_registries:
                    if isinstance(reg, str):
                        all_registries.append(reg)
                    elif isinstance(reg, dict):
                        all_registries.append(reg)

                # Add inbound registries
                inbound_registries = self._a2a_config.get("inbound", {}).get("registries", [])
                for reg in inbound_registries:
                    if isinstance(reg, str):
                        all_registries.append(reg)
                    elif isinstance(reg, dict):
                        all_registries.append(reg)

                # Get startup policies (prefer outbound, fall back to inbound)
                startup_policy = self._a2a_config.get("outbound", {}).get(
                    "startup_policy"
                ) or self._a2a_config.get("inbound", {}).get("startup_policy", "lenient")
                retry_timeout = self._a2a_config.get("outbound", {}).get(
                    "retry_timeout_seconds"
                ) or self._a2a_config.get("inbound", {}).get("retry_timeout_seconds", 30)

                a2a_config_obj = A2AServiceSchema(
                    enabled=self._a2a_config.get("enabled", True),
                    # Map inbound configuration to server settings
                    server_enabled=self._a2a_config.get("inbound", {}).get("enabled", False),
                    server_host=self._a2a_config.get("inbound", {}).get("host", "0.0.0.0"),
                    server_port=self._a2a_config.get("inbound", {}).get("port", 8181),
                    # Enable external registry if inbound or outbound registries are configured
                    external_registry_enabled=self._is_external_registry_enabled(self._a2a_config),
                    # Use the primary registry URL from configuration (legacy support)
                    registry_url=self._get_primary_registry_url(self._a2a_config),
                    registration_timeout=self._a2a_config.get("external_registry", {}).get(
                        "timeout", 30.0
                    ),
                    # New registry configuration
                    startup_policy=startup_policy,
                    retry_timeout_seconds=retry_timeout,
                    registries=all_registries,
                    # Map authentication from inbound.auth configuration
                    require_auth=(
                        self._a2a_config.get("inbound", {}).get("auth", {}).get("type", "none")
                        != "none"
                    ),
                    auth_mode=self._a2a_config.get("inbound", {})
                    .get("auth", {})
                    .get("type", "none"),
                    shared_key=self._get_inbound_auth_key(self._a2a_config.get("inbound", {})),
                    allowed_origins=self._a2a_config.get("security", {}).get("allowed_origins"),
                    # Map outbound configuration
                    default_timeout_seconds=self._a2a_config.get("outbound", {}).get(
                        "default_timeout_seconds", 30
                    ),
                    default_retry_attempts=self._a2a_config.get("outbound", {}).get(
                        "default_retry_attempts", 3
                    ),
                )
                a2a_config_obj.validate()
            except Exception as e:
                print(
                    f"Warning: Invalid A2A configuration, using defaults. "
                    f"Validation error: {str(e)}. "
                    f"Config values: inbound_enabled={self._a2a_config.get('inbound', {}).get('enabled')}, "
                    f"inbound_port={self._a2a_config.get('inbound', {}).get('port')}, "
                    f"external_registry_enabled={self._is_external_registry_enabled(self._a2a_config)}, "
                    f"require_auth={self._a2a_config.get('security', {}).get('require_auth')}",
                    flush=True,
                )
                a2a_config_obj = A2AServiceSchema()

        # Update service bundle for overlord handoff (don't overwrite!)
        # For formation_path, ensure we pass the directory (not the file)
        formation_dir = self._formation_path
        if formation_dir and os.path.isfile(formation_dir):
            formation_dir = os.path.dirname(formation_dir)

        self._configured_services.update(
            {
                "formation_config": self.config,
                "mcp_servers_with_user_credentials": self._mcp_servers_with_user_credentials,
                "secrets_manager": self.secrets_manager,
                "formation_path": formation_dir,  # Pass directory, not file
                "api_keys": self._api_keys.copy(),
                # Service-specific configurations (validated and preprocessed)
                "llm_config": self._llm_config,
                "memory_config": self._memory_config,
                "mcp_config": mcp_config_obj,  # Standardized config object
                "mcp_servers": getattr(self, "_mcp_servers", []),  # Actual server configurations
                "a2a_config": a2a_config_obj,  # Standardized config object
                "logging_config": self._logging_config,
                "clarification_config": self._clarification_config,
                "document_processing_config": self._document_processing_config,
                "scheduler_config": self._scheduler_config,
                "runtime_config": self._runtime_config,
                "agents_config": self._agents_config,
            }
        )

    async def _initialize_services(self) -> None:
        """
        Initializes all core and auxiliary services required for the Formation
        runtime after configuration is loaded.

        This method must be called after `_prepare_services()`.
        It initializes services in a specific order to ensure dependencies
        are satisfied, starting with observability, followed by LLM configuration,
        memory systems, document processing configuration, background services,
        clarification configuration, and agent loading. Updates the internal
        registry of configured services with initialized instances.
        """
        # 1. Initialize observability FIRST
        # This ensures all subsequent events go to the configured file
        initialize_observability(self)

        # 2. Initialize PromptLoader (fail fast if prompts missing)
        from .prompts.loader import PromptLoader
        try:
            PromptLoader.initialize()
            # Init event - no observability emission during init phase (replaced by InitEventFormatter)
        except FileNotFoundError as e:
            observability.observe(
                event_type=observability.ErrorEvents.FORMATION_INITIALIZATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Formation initialization failed: {e}",
            )
            raise RuntimeError(f"Cannot start formation: {e}")
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                level=observability.EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Unexpected error loading prompts: {e}",
            )
            raise

        # 3. Initialize LLM configuration
        initialize_llm_config(self)

        # 4. Initialize memory systems
        initialize_memory_systems(self)

        # 5. Initialize document processing configuration
        initialize_document_processing_config(self)

        # 6. Initialize background services
        initialize_background_services(self)

        # 7. Initialize MCP services (now async to register servers immediately)
        await initialize_mcp_services(self)

        # 8. Initialize clarification configuration
        initialize_clarification_config(self)

        # 9. Load agents configuration
        load_agents_from_configuration(self)

        # 10. Start observability manager (enables event processing and logging)
        if hasattr(self, "_observability_manager") and self._observability_manager:
            await self._observability_manager.start()

        # Update configured services with initialized instances
        self._configured_services.update(
            {
                "observability_manager": getattr(self, "_observability_manager", None),
                "buffer_memory": getattr(self, "_buffer_memory", None),
                "long_term_memory": getattr(self, "_long_term_memory", None),
                "working_memory_config": getattr(self, "_working_memory_config", None),
                "document_chunk_manager": getattr(self, "_document_chunk_manager", None),
                "request_tracker": getattr(self, "_request_tracker", None),
                "webhook_manager": getattr(self, "_webhook_manager", None),
                "clarification_config": getattr(self, "_clarification_config_obj", None),
                "document_processing_config": getattr(self, "_document_processing_config", None),
                "document_chunker": getattr(self, "_document_chunker", None),
                "db_manager": getattr(self, "_db_manager", None),
                "is_multi_user": getattr(self, "_is_multi_user", False),
                "mcp_service": getattr(self, "_mcp_service", None),
            }
        )

        # REMOVE - line 1268 (redundant with InitEventFormatter section 10: Formation ready)

    def _setup_auth(self) -> None:
        """
        Setup authentication keys for the formation.

        Generates or uses configured API keys for user and admin access.

        This method is idempotent - if keys already exist, it won't regenerate them.
        This is important because _prepare_services() may be called multiple times
        (once during load(), again during start_overlord()).
        """
        # If keys already exist, don't regenerate (idempotent)
        if self._api_keys.get("client") and self._api_keys.get("admin"):
            return

        # Get server config
        server_config = self.config.get("server", {}) if self.config else {}

        # Get API keys from server config
        api_keys_config = server_config.get("api_keys", {})

        # Track which keys were generated vs provided
        generated_keys = {}

        # Handle client key
        client_key = api_keys_config.get("client_key")
        if client_key:
            self._api_keys["client"] = client_key
        else:
            self._api_keys["client"] = generate_api_key("client")
            generated_keys["client"] = self._api_keys["client"]

        # Handle admin key
        admin_key = api_keys_config.get("admin_key")
        if admin_key:
            self._api_keys["admin"] = admin_key
        else:
            self._api_keys["admin"] = generate_api_key("admin")
            generated_keys["admin"] = self._api_keys["admin"]

        # Store generated keys for later display
        self._generated_api_keys = generated_keys

        # Store server configuration for later use
        self._server_config = {
            "host": server_config.get("host", "127.0.0.1"),
            "port": server_config.get("port", 8271),
            "access_log": server_config.get("access_log", False),
            "api_keys": self._api_keys,
        }

    def _setup_llm_config(self) -> None:
        """Setup and validate LLM configuration."""
        self._llm_config = self.config.get("llm", {})

        # Validate basic LLM structure
        if not isinstance(self._llm_config, dict):
            raise ConfigurationValidationError(
                ["LLM configuration must be a dictionary"],
                {
                    "current_type": type(self._llm_config).__name__,
                    "suggestion": "Update your formation.afs to have 'llm:' as a dictionary section",
                    "example": {
                        "llm": {
                            "api_keys": {"openai": "your-api-key"},
                            "models": [{"name": "gpt-4"}],
                        }
                    },
                },
            )

        # Validate required LLM fields
        if not self._llm_config:
            raise ConfigurationValidationError(
                [
                    "LLM configuration cannot be empty - at least one LLM provider must be configured"
                ],
                {
                    "suggestion": "Add LLM configuration to your formation.afs",
                    "required_sections": ["api_keys", "models"],
                    "example": {
                        "llm": {
                            "api_keys": {
                                "openai": "sk-your-openai-key",
                                "anthropic": "sk-ant-your-anthropic-key",
                            },
                            "models": [
                                {"name": "gpt-4", "provider": "openai"},
                                {"name": "claude-3-sonnet", "provider": "anthropic"},
                            ],
                        }
                    },
                },
            )

        # Validate LLM structure (api_keys, models, settings)
        if "api_keys" in self._llm_config:
            api_keys = self._llm_config["api_keys"]
            if not isinstance(api_keys, dict):
                raise ConfigurationValidationError(
                    ["LLM 'api_keys' section must be a dictionary"],
                    {
                        "current_type": type(api_keys).__name__,
                        "suggestion": "Update the 'api_keys' section to be a dictionary of provider names and API keys",
                        "example": {
                            "api_keys": {
                                "openai": "sk-your-openai-key",
                                "anthropic": "sk-ant-your-anthropic-key",
                            }
                        },
                    },
                )

            # Validate that at least one API key is provided
            if not api_keys:
                raise ConfigurationValidationError(
                    [
                        "LLM 'api_keys' section cannot be empty - at least one provider API key required"
                    ],
                    {
                        "suggestion": "Add at least one API key for an LLM provider",
                        "supported_providers": ["openai", "anthropic", "azure", "cohere"],
                        "example": {"api_keys": {"openai": "sk-your-openai-key"}},
                        "how_to_get_keys": {
                            "openai": "Get your API key from https://platform.openai.com/api-keys",
                            "anthropic": "Get your API key from https://console.anthropic.com/",
                        },
                    },
                )

        if "models" in self._llm_config:
            models = self._llm_config["models"]
            if not isinstance(models, list):
                raise ValueError("LLM 'models' section must be a list")

            # Validate each model configuration
            for i, model_config in enumerate(models):
                if not isinstance(model_config, dict):
                    raise ValueError(f"LLM model {i} configuration must be a dictionary")

        if "settings" in self._llm_config:
            settings = self._llm_config["settings"]
            if not isinstance(settings, dict):
                raise ValueError("LLM 'settings' section must be a dictionary")

    def _setup_memory_config(self) -> None:
        """Setup and validate memory configuration."""
        self._memory_config = self.config.get("memory", {})

        # Validate memory configuration structure
        if not isinstance(self._memory_config, dict):
            raise ConfigurationValidationError(
                ["Memory configuration must be a dictionary"],
                {
                    "current_type": type(self._memory_config).__name__,
                    "suggestion": "Update your formation.afs to have 'memory:' as a dictionary section",
                    "example": {"memory": {"type": "local", "path": "./memory"}},
                },
            )

        # Validate memory type and required fields
        if self._memory_config:
            memory_type = self._memory_config.get("type")
            if memory_type and memory_type not in ["local", "memobase", "sqlite"]:
                raise ConfigurationValidationError(
                    [
                        f"Unsupported memory type '{memory_type}'. Supported types: local, memobase, sqlite"
                    ],
                    {
                        "current_type": memory_type,
                        "supported_types": ["local", "memobase", "sqlite"],
                        "suggestion": "Choose a supported memory type",
                        "examples": {
                            "local": {"type": "local", "path": "./memory"},
                            "sqlite": {"type": "sqlite", "database": "memory.db"},
                            "memobase": {
                                "type": "memobase",
                                "connection_string": "postgresql://...",
                            },
                        },
                    },
                )

            # Validate memobase-specific configuration
            if memory_type == "memobase":
                if "connection_string" not in self._memory_config:
                    raise ConfigurationValidationError(
                        [
                            "Memobase memory configuration missing required 'connection_string' field"
                        ],
                        {
                            "memory_type": "memobase",
                            "missing_field": "connection_string",
                            "suggestion": "Add a PostgreSQL connection string for Memobase",
                            "example": {
                                "memory": {
                                    "type": "memobase",
                                    "connection_string": "postgresql://user:password@localhost:5432/memobase",
                                }
                            },
                            "setup_help": "Install PostgreSQL and create a database for Memobase storage",
                        },
                    )

    def _setup_mcp_config(self) -> None:
        """Setup and validate MCP (Model Context Protocol) configuration."""
        self._mcp_config = self.config.get("mcp", {})

        # Validate MCP structure
        if not isinstance(self._mcp_config, dict):
            raise ValueError("MCP configuration must be a dictionary")

        # Add built-in MCP servers to the regular MCP servers list
        self._add_builtin_mcps_to_config()

    def _add_builtin_mcps_to_config(self) -> None:
        """
        Add built-in MCP servers to the regular MCP servers configuration.

        This method checks the runtime configuration for enabled built-in MCPs
        and adds them to the regular MCP servers list, allowing them to be
        registered through the normal MCP registration process.
        """
        # Get runtime config for built-in MCPs
        runtime_config = self.config.get("runtime", {})
        builtin_mcps_config = runtime_config.get("built_in_mcps", True)

        # Skip if built-in MCPs are disabled
        if builtin_mcps_config is False:
            return

        # Import built-in MCP registry
        from ..services.mcp.built_in import list_builtin_mcps

        # Get all available built-in MCPs
        available_mcps = list_builtin_mcps()

        # Determine which MCPs to add
        mcps_to_add = []

        if isinstance(builtin_mcps_config, bool) and builtin_mcps_config:
            # Simple mode - all built-in MCPs enabled
            mcps_to_add = list(available_mcps.keys())
        elif isinstance(builtin_mcps_config, list):
            # Granular mode - only specified MCPs
            mcps_to_add = [
                mcp_name for mcp_name in builtin_mcps_config if mcp_name in available_mcps
            ]

        # Initialize MCP servers list if not present
        if "servers" not in self._mcp_config:
            self._mcp_config["servers"] = []

        # Add each enabled built-in MCP to the servers list
        for mcp_name in mcps_to_add:
            mcp_path = available_mcps[mcp_name]

            # Check if the script exists
            if not mcp_path.exists():
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "mcp_name": mcp_name,
                        "mcp_path": str(mcp_path),
                        "error": "Script file not found",
                    },
                    description=f"Built-in MCP script not found: {mcp_path}",
                )
                continue

            # Create MCP server configuration
            # Quote the path to handle spaces properly
            quoted_path = shlex.quote(str(mcp_path))
            mcp_server_config = {
                "id": f"builtin-{mcp_name}",
                "command": f"python {quoted_path}",
                "description": f"Built-in MCP server: {mcp_name}",
            }

            # Add to servers list
            self._mcp_config["servers"].append(mcp_server_config)

            pass  # REMOVED: init-phase observe() call

    def _setup_a2a_config(self) -> None:
        """Setup and validate Agent-to-Agent configuration."""
        self._a2a_config = self.config.get("a2a", {})

        # Validate A2A structure
        if not isinstance(self._a2a_config, dict):
            raise ValueError("A2A configuration must be a dictionary")

    def _setup_logging_config(self) -> None:
        """Setup and validate logging configuration."""
        self._logging_config = self.config.get("logging", {})

        # Validate logging structure
        if not isinstance(self._logging_config, dict):
            raise ValueError("Logging configuration must be a dictionary")

    def _setup_clarification_config(self) -> None:
        """Setup and validate clarification configuration."""
        # Clarification config is under overlord.clarification in formation YAML
        overlord_config = self.config.get("overlord", {})
        self._clarification_config = overlord_config.get("clarification", {})

        # Validate clarification structure
        if not isinstance(self._clarification_config, dict):
            raise ValueError("Clarification configuration must be a dictionary")

    def _setup_document_processing_config(self) -> None:
        """
        Ensures the `_document_processing_config` attribute exists on the instance, initializing it to `None` if absent.

        This method does not load or validate the document processing configuration;
        initialization is deferred to `initialize_document_processing_config`.
        """
        # Document processing config is initialized later by initialize_document_processing_config
        # For now, just ensure the attribute exists
        if not hasattr(self, "_document_processing_config"):
            self._document_processing_config = None

    def _setup_scheduler_config(self) -> None:
        """
        Sets up and validates the scheduler configuration from the loaded formation config.

        Raises:
            ConfigurationValidationError: If the scheduler configuration is not a
            dictionary or if required fields are invalid.
        """
        self._scheduler_config = self.config.get("scheduler", {})

        # Validate scheduler structure
        if not isinstance(self._scheduler_config, dict):
            raise ConfigurationValidationError(
                ["Scheduler configuration must be a dictionary"],
                {
                    "current_type": type(self._scheduler_config).__name__,
                    "suggestion": "Update your formation.afs to have 'scheduler:' as a dictionary section",
                    "example": {
                        "scheduler": {
                            "enabled": True,
                            "timezone": "UTC",
                            "check_interval_minutes": 1,
                        }
                    },
                },
            )

        # Validate scheduler specific fields if enabled
        if self._scheduler_config.get("enabled", True):
            check_interval = self._scheduler_config.get("check_interval_minutes", 1)

            if not isinstance(check_interval, int) or check_interval < 1:
                raise ConfigurationValidationError(
                    ["Scheduler check_interval_minutes must be a positive integer"],
                    {
                        "current_value": check_interval,
                        "suggestion": "Set check_interval_minutes to a positive integer (recommended: 1-60)",
                        "example": {"scheduler": {"check_interval_minutes": 1}},
                    },
                )

    def _setup_runtime_config(self) -> None:
        """Setup and validate runtime configuration."""
        self._runtime_config = self.config.get("runtime", {})

        # Validate runtime structure
        if not isinstance(self._runtime_config, dict):
            raise ConfigurationValidationError(
                ["Runtime configuration must be a dictionary"],
                {
                    "current_type": type(self._runtime_config).__name__,
                    "suggestion": "Update your formation.afs to have 'runtime:' as a dictionary section",
                    "example": {
                        "runtime": {"built_in_mcps": True}  # or ["file-generation", "web-search"]
                    },
                },
            )

    def _setup_agents_config(self) -> None:
        """Setup and validate agents configuration."""
        self._agents_config = self.config.get("agents", [])

        # Validate agents structure
        if not isinstance(self._agents_config, list):
            raise ConfigurationValidationError(
                ["Agents configuration must be a list"],
                {
                    "current_type": type(self._agents_config).__name__,
                    "suggestion": "Update your formation.afs to have 'agents:' as a list of agent configurations",
                    "example": {
                        "agents": [
                            {
                                "id": "assistant",
                                "name": "AI Assistant",
                                "type": "chat",
                                "description": "General purpose assistant",
                            }
                        ]
                    },
                },
            )

        # Validate individual agent configurations
        agent_ids = set()
        for i, agent_config in enumerate(self._agents_config):
            if not isinstance(agent_config, dict):
                raise ConfigurationValidationError(
                    [f"Agent {i} configuration must be a dictionary"],
                    {
                        "agent_position": i,
                        "current_type": type(agent_config).__name__,
                        "suggestion": "Each agent must be a dictionary with required fields",
                        "required_fields": ["id", "name"],
                        "example": {
                            "id": "my-agent",
                            "name": "My Agent",
                            "type": "chat",
                            "description": "Agent description",
                        },
                    },
                )

            if not agent_config.get("id"):
                raise ConfigurationValidationError(
                    [f"Agent {i} must have an 'id' field"],
                    {
                        "agent_position": i,
                        "missing_field": "id",
                        "suggestion": "Add a unique 'id' field to identify the agent",
                        "example": {"id": "my-agent", "name": "My Agent"},
                    },
                )

            agent_id = agent_config["id"]
            if not isinstance(agent_id, str) or not agent_id.strip():
                raise ConfigurationValidationError(
                    [f"Agent {i} 'id' must be a non-empty string"],
                    {
                        "agent_position": i,
                        "current_id": agent_id,
                        "current_type": type(agent_id).__name__,
                        "suggestion": (
                            "Agent ID must be a non-empty string "
                            "(letters, numbers, hyphens, underscores)"
                        ),
                        "examples": ["assistant", "code-reviewer", "data_analyst"],
                    },
                )

            # Check for duplicate agent IDs
            if agent_id in agent_ids:
                raise ConfigurationValidationError(
                    [f"Duplicate agent ID '{agent_id}' found at position {i}"],
                    {
                        "duplicate_id": agent_id,
                        "agent_position": i,
                        "suggestion": "Each agent must have a unique ID",
                        "fix": (
                            f"Change the ID of agent {i} to something unique like "
                            f"'{agent_id}_2' or '{agent_id}_v2'"
                        ),
                    },
                )
            agent_ids.add(agent_id)

            # Validate required agent fields
            if "name" not in agent_config:
                raise ConfigurationValidationError(
                    [f"Agent '{agent_id}' missing required 'name' field"],
                    {
                        "agent_id": agent_id,
                        "missing_field": "name",
                        "suggestion": "Add a human-readable 'name' field for the agent",
                        "example": {"id": agent_id, "name": "My Assistant Agent"},
                    },
                )

            # Validate agent type if specified
            agent_type = agent_config.get("type")
            if agent_type and agent_type not in ["chat", "workflow", "specialist"]:
                raise ConfigurationValidationError(
                    [
                        f"Agent '{agent_id}' has unsupported type '{agent_type}'. "
                        "Supported types: chat, workflow, specialist"
                    ],
                    {
                        "agent_id": agent_id,
                        "current_type": agent_type,
                        "supported_types": ["chat", "workflow", "specialist"],
                        "suggestion": "Choose a supported agent type or remove the 'type' field to use default",
                        "type_descriptions": {
                            "chat": "Interactive conversational agent",
                            "workflow": "Multi-step task automation agent",
                            "specialist": "Domain-specific expert agent",
                        },
                    },
                )

    async def ensure_secrets_manager(self) -> bool:
        """
        Ensure the SecretsManager is initialized and ready to use with timeout and retry support.

        Returns:
            bool: True if SecretsManager is available, False otherwise
        """
        if not self.secrets_manager:
            return False

        # Check if already initialized
        if self.secrets_manager.is_initialized:
            return True

        async def _initialize_operation():
            """Initialize secrets manager with timeout support."""

            async def _timeout_operation():
                await self.secrets_manager.initialize_encryption()
                return True

            result = await execute_with_timeout(
                _timeout_operation,
                operation_type="secrets_operation",
                description="Initializing secrets manager encryption",
                timeout=self._timeout_config.secrets_operation_timeout,
                cancellation_token=self._formation_cancellation_token,
            )

            if result.is_success:
                return result.result
            else:
                if result.was_timeout:
                    raise ServiceTransientError(
                        f"Secrets manager initialization timed out after {result.elapsed_time:.1f}s",
                        retry_after=2.0,
                        details={
                            "timeout": self._timeout_config.secrets_operation_timeout,
                            "suggestion": "Increase secrets_operation_timeout or check system performance",
                        },
                    )
                elif result.was_cancelled:
                    raise ServiceTransientError(
                        "Secrets manager initialization was cancelled",
                        details={
                            "suggestion": "Operation was cancelled - check if Formation is being shut down"
                        },
                    )
                else:
                    # Re-raise the original error for retry logic to handle
                    raise result.error

        try:
            # Use retry logic for secrets manager initialization
            retry_result = await self._retry_manager.execute_with_retry(
                _initialize_operation,
                config=self._retry_config,
                operation_name="secrets_manager_initialization",
            )

            if retry_result.success:
                if retry_result.was_retried:
                    print(
                        f"✅ Secrets manager initialized successfully after {retry_result.total_attempts} attempts"
                    )
                return retry_result.result
            else:
                error = retry_result.error
                print(
                    f"❌ Failed to initialize secrets manager after {retry_result.total_attempts} attempts: {error}"
                )

                # Provide specific suggestions based on error type
                if isinstance(error, ServiceTransientError):
                    if error.details and "suggestion" in error.details:
                        print(f"💡 Suggestion: {error.details['suggestion']}")
                else:
                    print("💡 Suggestion: Check if encryption dependencies are properly installed")
                    print("   Try: pip install cryptography")
                return False

        except Exception as e:
            print(f"❌ Unexpected error initializing secrets manager: {e}")
            return False

    async def store_secret(self, name: str, value: str) -> bool:
        """
        Store a secret in the formation's secrets manager.

        Args:
            name: Name of the secret (will be normalized to uppercase)
            value: Secret value to store

        Returns:
            bool: True if successful, False otherwise
        """
        if not await self.ensure_secrets_manager():
            return False

        try:
            await self.secrets_manager.store_secret(name, value)
            return True
        except (ValueError, TypeError) as e:
            print(f"❌ Invalid secret data for '{name}': {e}")
            print("💡 Suggestion: Ensure secret name and value are valid strings")
            return False
        except PermissionError as e:
            print(f"❌ Permission denied storing secret '{name}': {e}")
            print("💡 Suggestion: Check file permissions for secrets storage directory")
            return False
        except Exception as e:
            print(f"❌ Unexpected error storing secret '{name}': {e}")
            print("💡 Suggestion: Try 'formation.ensure_secrets_manager()' to reinitialize")
            return False

    async def get_secret(self, name: str) -> Optional[str]:
        """
        Retrieve a secret from the formation's secrets manager.

        Args:
            name: Name of the secret to retrieve

        Returns:
            Optional[str]: Secret value if found, None otherwise
        """
        if not await self.ensure_secrets_manager():
            return None

        try:
            return await self.secrets_manager.get_secret(name)
        except (ValueError, TypeError) as e:
            print(f"❌ Invalid secret name '{name}': {e}")
            print("💡 Suggestion: Secret names should be alphanumeric strings")
            return None
        except KeyError:
            # Secret not found - this is normal, don't warn
            return None
        except PermissionError as e:
            print(f"❌ Permission denied accessing secret '{name}': {e}")
            print("💡 Suggestion: Check file permissions for secrets storage")
            return None

    def get_secrets_count(self) -> int:
        """
        Get the count of secrets currently in use by the formation.

        Returns:
            int: Number of secrets in use
        """
        return len(self._secrets_in_use) if hasattr(self, "_secrets_in_use") else 0

    def is_secret_in_use(self, secret_name: str) -> bool:
        """
        Check if a secret is being used in the current formation configuration.

        Args:
            secret_name: Name of the secret to check

        Returns:
            bool: True if the secret is in use, False otherwise
        """
        # Normalize the secret name the same way SecretsManager does
        import re

        normalized_name = re.sub(r"[^A-Z0-9_]", "_", secret_name.upper())
        normalized_name = re.sub(r"_+", "_", normalized_name)
        normalized_name = normalized_name.strip("_")

        # Check if the secret is in our tracked set
        return normalized_name in self._secrets_in_use

    def track_used_secrets(self, secret_names: set[str]) -> None:
        """
        Track additional secrets as being in use by the formation.

        This method is used to update the set of secrets that are actively
        being used by agents or other components in the formation.

        Args:
            secret_names: Set of secret names to track as in-use
        """
        import re

        # Normalize secret names the same way as is_secret_in_use
        normalized_names = set()
        for name in secret_names:
            normalized_name = re.sub(r"[^A-Z0-9_]", "_", name.upper())
            normalized_name = re.sub(r"_+", "_", normalized_name)
            normalized_name = normalized_name.strip("_")
            normalized_names.add(normalized_name)

        if hasattr(self, "_secrets_in_use"):
            self._secrets_in_use.update(normalized_names)
        else:
            self._secrets_in_use = normalized_names

    async def list_secrets(self) -> List[str]:
        """
        List all secret names in the formation's secrets manager.

        Returns:
            List[str]: List of secret names
        """
        if not await self.ensure_secrets_manager():
            return []

        try:
            return await self.secrets_manager.list_secrets()
        except PermissionError as e:
            print(f"Warning: Permission denied listing secrets: {e}")
            return []
        except Exception as e:
            print(f"Warning: Unexpected error listing secrets: {e}")
            return []

    async def delete_secret(self, name: str) -> bool:
        """
        Delete a secret from the formation's secrets manager.

        Args:
            name: Name of the secret to delete

        Returns:
            bool: True if successful, False otherwise
        """
        if not await self.ensure_secrets_manager():
            return False

        try:
            await self.secrets_manager.delete_secret(name)
            return True
        except (ValueError, TypeError) as e:
            print(f"Warning: Invalid secret name '{name}': {e}")
            return False
        except KeyError:
            # Secret not found - this is normal for delete operations
            print(f"Info: Secret '{name}' not found (already deleted)")
            return True
        except PermissionError as e:
            print(f"Warning: Permission denied deleting secret '{name}': {e}")
            return False
        except Exception as e:
            print(f"Warning: Unexpected error deleting secret '{name}': {e}")
            return False

    async def interpolate_secrets(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpolate secrets in a configuration dictionary.

        Args:
            config: Configuration dictionary that may contain ${{ secrets.NAME }} references

        Returns:
            Dict[str, Any]: Configuration with secrets interpolated
        """
        if not await self.ensure_secrets_manager():
            return config

        try:
            return await self.secrets_manager.interpolate_secrets(config)
        except Exception as e:
            print(f"❌ Failed to interpolate secrets: {e}")
            print(
                "💡 Suggestion: Check your secret references use format: ${{ secrets.SECRET_NAME }}"
            )
            return config

    def _has_stdio_mcp_servers(self) -> bool:
        """Check if any registered MCP servers use stdio transport."""
        if not hasattr(self, "_mcp_service") or not self._mcp_service:
            return False

        # Check if connections attribute exists before accessing it
        if not hasattr(self._mcp_service, "connections"):
            return False

        # Check if any active connections use command transport
        for conn in self._mcp_service.connections.values():
            if conn.get("transport_type") == "command":
                return True
        return False

    def _has_any_mcp_servers(self) -> bool:
        """Check if any MCP servers are registered."""
        if not hasattr(self, "_mcp_service") or not self._mcp_service:
            return False

        # Check if connections attribute exists before accessing it
        if not hasattr(self._mcp_service, "connections"):
            return False

        # Return True if there are any connections
        return len(self._mcp_service.connections) > 0

    def suppress_mcp_errors_on_exit(self) -> None:
        """
        Register an atexit handler to suppress MCP async generator errors.

        This method registers a handler that will be called when Python exits,
        which uses os._exit() to skip the cleanup phase where MCP async generator
        errors occur. This is useful when you know your application will exit
        and you want to avoid seeing the errors.

        This now handles ALL MCP server types (stdio, HTTP SSE, and streamable HTTP).

        Example:
            formation = Formation()
            formation.suppress_mcp_errors_on_exit()  # Register handler
            await formation.load("formation.afs")
            # ... use formation normally ...
            # Errors will be suppressed when Python exits
        """
        # Check if handler is already registered to avoid duplicates
        if hasattr(self, "_atexit_handler_registered") and self._atexit_handler_registered:
            return

        # Store the original exit code
        self._exit_code = 0

        def _clean_exit_handler():
            # Check if we have ANY MCP servers (not just stdio)
            if self._has_any_mcp_servers():
                # Flush outputs
                sys.stdout.flush()
                sys.stderr.flush()
                # Use stored exit code or current process exit code
                exit_code = getattr(self, "_exit_code", 0)
                if hasattr(sys, "_exitcode") and sys._exitcode is not None:
                    exit_code = sys._exitcode
                # Skip Python cleanup with proper exit code
                os._exit(exit_code)

        # Register the handler and store reference
        self._atexit_handler = _clean_exit_handler
        atexit.register(self._atexit_handler)
        self._atexit_handler_registered = True

    def remove_mcp_exit_handler(self) -> None:
        """Remove the registered atexit handler if it exists."""
        if hasattr(self, "_atexit_handler") and self._atexit_handler_registered:
            try:
                atexit.unregister(self._atexit_handler)
                self._atexit_handler_registered = False
            except ValueError:
                # Handler was not registered, ignore
                pass

    def _resolve_initialization_credentials(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Replace user.credentials.X with secrets.USER_CREDENTIALS_X for initialization.

        This method transforms user credential placeholders to initialization secret patterns
        that can be resolved during formation startup when there's no user context.

        Args:
            auth_config: Authentication configuration that may contain user credential placeholders

        Returns:
            Auth config with user credential patterns replaced by initialization secret patterns

        Example:
            Input:  {"token": "${{ user.credentials.github }}"}
            Output: {"token": "${{ secrets.USER_CREDENTIALS_GITHUB }}"}
        """
        if not auth_config:
            return auth_config

        USER_CREDENTIAL_PATTERN = re.compile(r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}")

        def transform_recursive(data: Any) -> Any:
            """Recursively transform credential placeholders in nested data structures."""
            if isinstance(data, dict):
                # Process dictionary recursively
                transformed_dict = {}
                for key, value in data.items():
                    transformed_dict[key] = transform_recursive(value)
                return transformed_dict
            elif isinstance(data, list):
                # Process list recursively
                return [transform_recursive(item) for item in data]
            elif isinstance(data, str):
                # Check if this is a user credential placeholder
                match = USER_CREDENTIAL_PATTERN.match(data)
                if match:
                    service_name = match.group(1)
                    # Transform to initialization secret pattern
                    # user.credentials.github -> secrets.USER_CREDENTIALS_GITHUB
                    initialization_secret = f"USER_CREDENTIALS_{service_name.upper()}"
                    return f"${{{{ secrets.{initialization_secret} }}}}"
                else:
                    return data
            else:
                # Non-string, non-dict, non-list values pass through
                return data

        return transform_recursive(auth_config)

    async def _register_mcp_servers(self) -> None:
        """Register MCP servers in Formation's event loop."""
        if not hasattr(self, "_mcp_service") or not self._mcp_service:
            return

        if not hasattr(self, "_mcp_servers") or not self._mcp_servers:
            return

        pass  # REMOVED: init-phase observe() call

        # Track failed registrations
        failed_servers = []
        successful_servers = []
        skipped_servers = []

        # Register each server
        for server_config in self._mcp_servers:
            try:
                server_id = server_config.get("id", "unknown")

                # Skip inactive servers
                if not server_config.get("active", True):
                    skipped_servers.append(server_id)
                    continue

                # Prepare registration parameters
                registration_params = {
                    "server_id": server_id,
                }

                # Determine server type and set appropriate parameter
                if "command" in server_config:
                    # Command-based server
                    command = server_config["command"]
                    # Pass args separately if provided
                    if "args" in server_config:
                        registration_params["args"] = server_config["args"]
                    registration_params["command"] = command
                elif "url" in server_config:
                    # HTTP/SSE server
                    registration_params["url"] = server_config["url"]
                elif "endpoint" in server_config:
                    # HTTP server with endpoint notation
                    registration_params["url"] = server_config["endpoint"]
                else:
                    observability.observe(
                        event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "server_id": server_id,
                            "error": "No command or url specified",
                        },
                        description=f"Invalid MCP server config: {server_id}",
                    )
                    failed_servers.append(server_id)
                    continue

                # Add optional parameters
                if "auth" in server_config:
                    # Check if auth contains user credentials
                    original_auth = server_config["auth"]
                    USER_CREDENTIAL_PATTERN = re.compile(
                        r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}"
                    )

                    # Helper function to check if auth contains user credentials
                    def contains_user_credentials(data: Any) -> bool:
                        if isinstance(data, dict):
                            for value in data.values():
                                if contains_user_credentials(value):
                                    return True
                        elif isinstance(data, list):
                            for item in data:
                                if contains_user_credentials(item):
                                    return True
                        elif isinstance(data, str):
                            if USER_CREDENTIAL_PATTERN.search(data):
                                return True
                        return False

                    # If auth contains user credentials, we need special handling
                    if contains_user_credentials(original_auth):
                        # Transform user credentials to formation secrets for initial connection
                        # This allows MCP server to connect and discover tools
                        transformed_auth = self._resolve_initialization_credentials(original_auth)

                        # Interpolate the transformed secrets
                        if hasattr(self, "secrets_manager") and self.secrets_manager:
                            final_auth = await self.secrets_manager.interpolate_secrets(
                                transformed_auth
                            )
                            registration_params["credentials"] = final_auth
                        else:
                            registration_params["credentials"] = transformed_auth

                        # IMPORTANT: Store original auth config for runtime resolution
                        registration_params["original_credentials"] = original_auth

                        # Build registry entry for this server
                        # Extract first service name from auth config (recursive)
                        def _find_service_name(obj: Any) -> Optional[str]:
                            if isinstance(obj, str):
                                m = USER_CREDENTIAL_PATTERN.search(obj)
                                return m.group(1) if m else None
                            if isinstance(obj, dict):
                                for v in obj.values():
                                    found = _find_service_name(v)
                                    if found:
                                        return found
                            if isinstance(obj, list):
                                for v in obj:
                                    found = _find_service_name(v)
                                    if found:
                                        return found
                            return None

                        service_name = _find_service_name(original_auth)

                        if service_name:
                            # Add to user credential server registry
                            self._mcp_servers_with_user_credentials[server_id] = {
                                "service": service_name,
                                "server_id": server_id,
                                "accept_inline": original_auth.get("accept_inline", False),
                                "auth_type": original_auth.get("type", "bearer"),
                                "uses_user_credentials": True,
                            }

                            pass  # REMOVED: init-phase observe() call
                        else:
                            pass  # REMOVED: init-phase observe() call
                    else:
                        # No user credentials, interpolate secrets normally
                        if hasattr(self, "secrets_manager") and self.secrets_manager:
                            # Use async interpolation since we're in an async method
                            final_auth = await self.secrets_manager.interpolate_secrets(
                                original_auth
                            )
                            registration_params["credentials"] = final_auth
                        else:
                            registration_params["credentials"] = original_auth

                if "timeout_seconds" in server_config:
                    registration_params["request_timeout"] = server_config["timeout_seconds"]
                if "transport_type" in server_config:
                    registration_params["transport_type"] = server_config["transport_type"]

                # Register the server via MCP service
                await self._mcp_service.register_mcp_server(**registration_params)

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTERED,
                    level=observability.EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "description": server_config.get("description", ""),
                    },
                    description=f"MCP server registered: {server_id}",
                )
                successful_servers.append(server_id)

            except (MCPConnectionError, MCPTimeoutError, MCPCancelledError) as e:
                # MCP registration failures - continue with graceful degradation
                server_id = server_config.get("id", "unknown")
                error_msg = str(e)

                # Check for authentication errors to provide better messaging
                is_auth_error = (
                    "401" in error_msg
                    or "unauthorized" in error_msg.lower()
                    or "authentication" in error_msg.lower()
                )

                # Log the failure but don't crash the formation
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,  # Changed from ERROR to WARNING
                    data={
                        "server_id": server_id,
                        "error": error_msg,
                        "error_type": type(e).__name__,
                        "is_authentication_failure": is_auth_error,
                    },
                    description=f"MCP server '{server_id}' unavailable: {error_msg}",
                )

                # Print user-friendly error message
                from ..datatypes.observability import InitEventFormatter
                if is_auth_error:
                    print(InitEventFormatter.format_warn(
                        f"MCP server: {server_id}",
                        "authentication failed - check credentials"
                    ))
                else:
                    print(InitEventFormatter.format_warn(
                        f"MCP server: {server_id}",
                        f"connection failed - {error_msg}"
                    ))

                failed_servers.append(server_id)
                continue  # Continue with other servers instead of crashing

            except MCPRequestError as e:
                # Configuration errors - continue with graceful degradation
                server_id = server_config.get("id", "unknown")
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,  # Changed from ERROR to WARNING
                    data={
                        "server_id": server_id,
                        "error": str(e),
                        "error_type": "MCPRequestError",
                        "note": "Check server configuration",
                    },
                    description=f"Invalid MCP server configuration: {str(e)}",
                )

                # Print user-friendly error message
                from ..datatypes.observability import InitEventFormatter
                print(InitEventFormatter.format_warn(
                    f"MCP server: {server_id}",
                    f"invalid configuration - {str(e)}"
                ))

                failed_servers.append(server_id)
                continue  # Continue with other servers instead of crashing

            except Exception as e:
                # Catch any other unexpected errors during MCP registration
                server_id = server_config.get("id", "unknown")
                error_msg = str(e)

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "server_id": server_id,
                        "error": error_msg,
                        "error_type": type(e).__name__,
                        "is_unexpected_error": True,
                    },
                    description=f"Unexpected error registering MCP server '{server_id}': {error_msg}",
                )

                # Print user-friendly error message
                from ..datatypes.observability import InitEventFormatter
                print(InitEventFormatter.format_warn(
                    f"MCP server: {server_id}",
                    f"registration failed - {error_msg}"
                ))

                failed_servers.append(server_id)
                continue  # Continue with other servers instead of crashing

        # Add observability event for failed/skipped servers
        if failed_servers or skipped_servers:
            pass  # REMOVED: init-phase observe() call

        # Show info message if there were failures
        if failed_servers:
            from ..datatypes.observability import InitEventFormatter
            print(InitEventFormatter.format_info(
                "MCP initialization complete",
                f"{len(successful_servers)} server(s) connected, {len(failed_servers)} failed"
            ))

    async def start_overlord(self):
        """
        Start services and return configured overlord instance (async).

        This is an asynchronous coroutine that must be awaited when called.

        Initializes all services based on the loaded configuration and creates
        a fully configured overlord instance. The overlord receives pre-configured
        services and is ready for intelligent operations.

        Note: One formation = one overlord. If overlord is already running,
        returns the existing instance with a soft warning.

        Returns:
            Configured Overlord instance ready for intelligent operations

        Raises:
            OverlordStateError: If no configuration loaded
            OverlordImportError: If Overlord class cannot be imported
            OverlordStartupError: If overlord fails to start

        Example:
            formation = Formation()
            await formation.load("path/to/formation.afs")
            overlord = await formation.start_overlord()  # Must await!
        """
        if not self.config:
            raise OverlordStateError(
                "no_config",
                "config_loaded",
                {"operation": "start_overlord", "formation_id": self.formation_id},
            )

        # Return existing overlord if already running (one formation = one overlord)
        if self._is_running and self._overlord is not None:
            from ..datatypes.observability import InitEventFormatter
            print(InitEventFormatter.format_warn(
                "Formation is already running",
                "returning existing instance (call stop_overlord() first to restart)"
            ))
            return self._overlord

        # Track startup time for summary
        import time
        start_time = time.time()

        # Import for formatted output
        from ..datatypes.observability import InitEventFormatter
        from ..services import observability

        try:
            # Import overlord when needed to avoid circular imports
            from .overlord.overlord import Overlord

            # Prepare services for handoff
            self._prepare_services()

            # Get workflow configuration (check overlord.workflow first, then root workflow)
            overlord_config = self.config.get("overlord", {})
            workflow_config = overlord_config.get("workflow", self.config.get("workflow", {}))

            # Create overlord with pre-configured services
            self._overlord = Overlord(
                # Pre-configured services from Formation
                secrets_manager=self.secrets_manager,
                formation_config=self.config,
                configured_services=self._configured_services,
                api_keys=self._api_keys,
                # Intelligence-specific parameters from configuration
                buffer_memory=None,  # Will be configured by overlord based on our config
                long_term_memory=None,  # Will be configured by overlord based on our config
                auto_extract_user_info=self.config.get("auto_extract_user_info", True),
                extraction_model=None,  # Will be configured by overlord based on our config
                request_timeout=self.config.get("request_timeout", 60),
                # Enhanced workflow parameters from configuration
                enable_workflow_by_default=self.config.get("enable_workflow_by_default", False),
                complexity_threshold=workflow_config.get("complexity_threshold", 7.0),
                plan_approval_threshold=workflow_config.get("plan_approval_threshold", 7.0),
            )

            # Set the formation instance reference for memory initialization
            self._overlord._formation_instance = self

            # Mark as running
            self._is_running = True

            # Start the overlord (loads agents, initializes services)
            # Since we're now async, we can directly await the startup
            await self._overlord._async_startup()

            # MCP servers are already registered during _initialize_services()

            # Automatically suppress MCP exit errors if we have MCP servers
            if self._has_any_mcp_servers():
                self.suppress_mcp_errors_on_exit()
                pass  # REMOVED: init-phase observe() call

            # A2A initialization happens through the Overlord's A2ACoordinator
            # No separate service initialization needed here

            # Print startup summary
            duration = time.time() - start_time

            # Count services (rough estimate based on what's configured)
            service_count = 1  # overlord itself
            if self._configured_services:
                service_count += len(
                    [
                        s
                        for s in self._configured_services.keys()
                        if self._configured_services[s] is not None
                    ]
                )

            # Count warnings/errors from observability (we'll use 0 for now as a placeholder)
            print(InitEventFormatter.format_ok("Formation initialized successfully", f"in {duration:.1f}s"))

            # Enable observability now that init is complete
            # This starts the flow of JSON observability events for runtime monitoring
            observability.enable()

            return self._overlord

        except RegistryConfigurationError as e:
            # Clean up on failure - registry configuration issue
            self._is_running = False
            self._overlord = None

            # Print the user-friendly message
            print(e.user_message, file=sys.stderr)

            # Re-raise the exception for proper handling upstream
            raise

        except ImportError as e:
            # Clean up on failure - overlord import failed
            self._is_running = False
            self._overlord = None
            raise OverlordImportError(
                str(e),
                {
                    "formation_id": self.formation_id,
                    "config_path": self._formation_path,
                    "suggestion": "Verify the Overlord module is properly installed and accessible",
                    "troubleshooting": [
                        "Check if the overlord module exists in the formation directory",
                        "Verify Python path includes the formation package",
                        "Try reinstalling the formation package",
                    ],
                },
            ) from e
        except (ValueError, TypeError) as e:
            # Clean up on failure - configuration error
            self._is_running = False
            self._overlord = None
            raise OverlordStartupError(
                f"Invalid configuration: {str(e)}",
                {
                    "formation_id": self.formation_id,
                    "config_path": self._formation_path,
                    "error_type": "configuration_error",
                    "suggestion": "Review and fix the formation configuration",
                    "next_steps": [
                        "Validate your formation.afs syntax",
                        "Check required fields are present",
                        "Verify data types match expected values",
                        f"Review configuration at: {self._formation_path}",
                    ],
                },
            ) from e
        except Exception as e:
            # Clean up on failure - unexpected error
            self._is_running = False
            self._overlord = None
            formation_error = add_error_context(
                e,
                {
                    "operation": "start_overlord",
                    "formation_id": self.formation_id,
                    "config_path": self._formation_path,
                },
            )
            raise OverlordStartupError(
                str(formation_error),
                {
                    "formation_id": self.formation_id,
                    "config_path": self._formation_path,
                    "error_type": "unexpected_error",
                    "suggestion": "This appears to be an internal error",
                    "next_steps": [
                        "Try reloading the formation configuration",
                        "Check system resources (memory, disk space)",
                        "Review formation logs for additional details",
                        "Consider restarting the formation process",
                    ],
                },
            ) from e

    async def stop_overlord(self, timeout_seconds: float = 30.0) -> None:
        """
        Gracefully stop overlord - finish conversations and cleanup.

        Allows the overlord to complete any ongoing conversations, save state,
        and perform graceful shutdown. Uses the ActiveAgentsTracker to wait for
        all agents to finish their current work before shutting down.

        Args:
            timeout_seconds: Maximum time to wait for graceful shutdown before forcing termination

        Note:
            If you're using MCP servers and seeing async generator errors at exit,
            call formation.suppress_mcp_errors_on_exit() before loading the formation
            to suppress these harmless cleanup errors.
        """
        if not self._is_running or not self._overlord:
            return  # Already stopped or never started

        try:
            # Use the new graceful shutdown functionality
            await self._overlord.active_agent_tracker.mark_overlord_for_shutdown()

            # Wait for graceful shutdown with timeout
            start_time = asyncio.get_event_loop().time()

            async def wait_for_shutdown():
                tracker = self._overlord.active_agent_tracker
                while not tracker.overlord_shutting_down or not await tracker.is_idle():
                    await asyncio.sleep(0.1)
                    if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                        raise TimeoutError(
                            f"Graceful shutdown timed out after {timeout_seconds} seconds"
                        )

            try:
                await wait_for_shutdown()
                # Shutdown message removed - observability events handle this
            except TimeoutError:
                from ..datatypes.observability import InitEventFormatter
                print(InitEventFormatter.format_warn(
                    "Shutdown taking too long",
                    f"forcing termination after {timeout_seconds} seconds"
                ))

            # Disconnect MCP servers before cleanup
            if hasattr(self, "_mcp_service") and self._mcp_service:
                try:
                    await self._mcp_service.disconnect_all()
                    observability.observe(
                        event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTED,
                        level=observability.EventLevel.INFO,
                        data={"action": "disconnect_all"},
                        description="All MCP servers disconnected during Formation shutdown",
                    )
                except Exception as mcp_error:
                    observability.observe(
                        event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(mcp_error)},
                        description=f"Failed to disconnect MCP servers: {mcp_error}",
                    )

            # Dispose database engine to prevent event loop pollution in tests
            if self._overlord and hasattr(self._overlord, 'db_manager') and self._overlord.db_manager:
                try:
                    await self._overlord.db_manager.close_async()
                    observability.observe(
                        event_type=observability.SystemEvents.CLEANUP,
                        level=observability.EventLevel.INFO,
                        data={"action": "database_engine_disposed", "component": "db_manager"},
                        description="Database engine disposed during Formation shutdown",
                    )
                except Exception as db_error:
                    observability.observe(
                        event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(db_error), "operation": "database_engine_disposal"},
                        description=f"Failed to dispose database engine: {db_error}",
                    )

            # Clean up references
            self._overlord = None
            self._is_running = False

        except Exception as e:
            print(f"❌ Error during graceful overlord shutdown: {e}")
            print("💡 Suggestion: Use kill_overlord() for immediate termination if needed")
            # Force cleanup even if graceful shutdown fails
            self._overlord = None
            self._is_running = False

    async def _deregister_agents_with_timeout(self, timeout: float = 2.0) -> None:
        """
        Helper method to deregister all agents from external registry with configurable timeout.

        Args:
            timeout: Maximum time to wait for deregistration (default: 2.0 seconds)
        """
        if not self._overlord or not hasattr(
            self._overlord, "_deregister_all_agents_from_external_registry"
        ):
            return

        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_AGENT_DEREGISTERED,
                level=observability.EventLevel.INFO,
                data={"timeout": timeout, "action": "deregistration_started"},
                description="Starting agent deregistration from external registry",
            )

            await asyncio.wait_for(
                self._overlord._deregister_all_agents_from_external_registry(), timeout=timeout
            )

            observability.observe(
                event_type=observability.SystemEvents.A2A_DEREGISTERED,
                level=observability.EventLevel.INFO,
                data={},
                description="Successfully deregistered all agents from external registry",
            )

        except asyncio.TimeoutError:
            observability.observe(
                event_type=observability.ErrorEvents.CONNECTION_TIMEOUT,
                level=observability.EventLevel.WARNING,
                data={"timeout": timeout, "operation": "agent_deregistration"},
                description=f"Agent deregistration timed out after {timeout} seconds",
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "operation": "agent_deregistration"},
                description=f"Failed to deregister agents: {e}",
            )

    def _run_async_with_timeout(self, coro, timeout: float = 2.0) -> None:
        """
        Helper method to run an async coroutine with timeout, handling both cases:
        - When there's an existing event loop (create task)
        - When there's no event loop (create new loop)

        Args:
            coro: The coroutine to run
            timeout: Maximum time to wait (default: 2.0 seconds)
        """
        try:
            # Try to get the running loop
            loop = asyncio.get_running_loop()

            # Create task to run in background (fire and forget)
            task = asyncio.create_task(coro)

            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.DEBUG,
                data={"task": str(task), "timeout": timeout, "operation": "async_task_created"},
                description="Created async task in existing event loop",
            )

        except RuntimeError:
            # No running loop, create a new one
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.DEBUG,
                data={"timeout": timeout, "operation": "event_loop_created"},
                description="Creating new event loop for async operation",
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            except asyncio.TimeoutError:
                observability.observe(
                    event_type=observability.ErrorEvents.CONNECTION_TIMEOUT,
                    level=observability.EventLevel.WARNING,
                    data={"timeout": timeout, "operation": "async_with_timeout"},
                    description=f"Operation timed out after {timeout} seconds",
                )
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e)},
                    description=f"Operation failed: {e}",
                )
            finally:
                loop.close()

    def kill_overlord(self) -> None:
        """
        Immediately terminate overlord - stop NOW regardless of state.

        Forces immediate termination of the overlord without waiting for
        conversations to complete or state to be saved. Use for emergency
        situations or when graceful shutdown fails.
        """
        if not self._is_running or not self._overlord:
            return  # Already stopped or never started

        try:
            # Deregister agents from external registry if configured
            # Using helper method for cleaner structure and better observability
            self._run_async_with_timeout(
                self._deregister_agents_with_timeout(timeout=2.0), timeout=2.0
            )

            # Disconnect MCP servers immediately if present
            if hasattr(self, "_mcp_service") and self._mcp_service:
                self._run_async_with_timeout(self._mcp_service.disconnect_all(), timeout=2.0)

            # Force immediate cleanup without waiting
            self._overlord = None
            self._is_running = False

        except Exception as e:
            print(f"❌ Error during immediate overlord termination: {e}")
            print("💡 Suggestion: Formation cleanup will continue despite this error")
            # Force cleanup regardless of errors
            self._overlord = None
            self._is_running = False

    def shutdown(self, code: int = 0) -> None:
        """
        Immediately shutdown the formation and exit the process (synchronous).

        This method performs an IMMEDIATE shutdown:
        - Kills the overlord without waiting for agents to finish
        - Exits the process immediately with os._exit(code)
        - No graceful cleanup or state saving
        - Skips Python's cleanup (atexit handlers, etc.)

        Use this when:
        - You need to exit RIGHT NOW (emergency shutdown)
        - In synchronous code where you can't use await
        - In error handlers or signal handlers
        - For simple scripts that don't need graceful shutdown
        - You want a quick exit without cleanup overhead

        Compare with other shutdown methods:
        - stop(): Cleanup only, process continues
        - shutdown(): No cleanup, immediate exit (THIS METHOD)
        - ashutdown(): Graceful cleanup, then exit
        - kill(): Emergency abort, immediate exit

        For graceful shutdown, use ashutdown() instead.

        Args:
            code: Exit code (default: 0 for success, non-zero for errors)

        Example:
            formation = Formation()
            # ... some error occurs ...
            formation.shutdown(1)  # Exit immediately with error code
        """
        import sys
        import os

        # Kill overlord immediately if running
        if self._is_running:
            self.kill_overlord()

        # Flush output streams
        sys.stdout.flush()
        sys.stderr.flush()

        # Use os._exit to skip Python cleanup (including async generator cleanup)
        os._exit(code)

    async def ashutdown(self, code: int = 0) -> None:
        """
        Gracefully shutdown the formation and exit the process (async).

        This method performs a GRACEFUL shutdown:
        - Waits for agents to finish their current work (up to 5 seconds)
        - Properly disconnects from MCP servers
        - Saves state and cleans up resources
        - Then exits the process cleanly with os._exit(code)
        - Best effort: falls back to kill if graceful shutdown fails

        Use this when:
        - In production services for controlled shutdown
        - You want agents to complete their current tasks
        - You need to save state or close connections properly
        - In async applications (most modern Python code)
        - Data integrity is important

        Compare with other shutdown methods:
        - stop(): Cleanup only, process continues
        - shutdown(): No cleanup, immediate exit
        - ashutdown(): Graceful cleanup, then exit (THIS METHOD)
        - kill(): Emergency abort, immediate exit

        For immediate shutdown without waiting, use shutdown() instead.

        Args:
            code: Exit code (default: 0 for success, non-zero for errors)

        Example:
            async def main():
                formation = Formation()
                await formation.load("formation.afs")
                overlord = await formation.start_overlord()

                # ... use overlord ...

                # Graceful shutdown - agents finish their work
                await formation.ashutdown()
        """
        import sys
        import os

        # Try graceful async shutdown first
        if self._is_running:
            try:
                await self.stop_overlord(timeout_seconds=5.0)
            except Exception:
                # Fall back to immediate termination
                self.kill_overlord()

        # Flush output streams
        sys.stdout.flush()
        sys.stderr.flush()

        # Use os._exit to skip Python cleanup (including async generator cleanup)
        os._exit(code)

    def kill(self, code: int = 1) -> None:
        """
        IMMEDIATELY KILL EVERYTHING AND EXIT THE PROCESS - NUCLEAR OPTION!

        This is the most aggressive shutdown that:
        - Kills the overlord instantly (no waiting)
        - Doesn't bother with ANY cleanup
        - Skips ALL cleanup procedures
        - EXITS THE PROCESS IMMEDIATELY with os._exit(code)
        - Last resort logging attempt before exit

        Use this when:
        - You need to STOP EVERYTHING NOW
        - Emergency shutdown is required
        - Something has gone catastrophically wrong
        - You don't care about cleanup, you just want OUT
        - Second Ctrl+C in shutdown scripts
        - Deadlocks or hanging processes

        Compare with other shutdown methods:
        - stop(): Cleanup only, process continues
        - shutdown(): No cleanup, immediate exit
        - ashutdown(): Graceful cleanup, then exit
        - kill(): Emergency abort, immediate exit (THIS METHOD)

        WARNING: This is the most destructive option!

        Args:
            code: Exit code (default: 1 for error, 0 for success)

        Example:
            formation = Formation()
            await formation.load("formation.afs")
            await formation.start_overlord()

            # Something goes catastrophically wrong...
            formation.kill()  # STOP EVERYTHING AND EXIT NOW!
            # This line will never execute
        """
        import sys

        # Try to kill overlord if it exists (don't wait for anything)
        if self._is_running and self._overlord:
            try:
                self._overlord = None
                self._is_running = False
            except Exception:
                pass  # Don't care about errors when killing

        # Log that we're killing everything (if possible)
        try:
            observability.observe(
                event_type=observability.SystemEvents.CLEANUP,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "formation",
                    "action": "kill",
                    "formation_id": self.formation_id,
                    "exit_code": code,
                },
                description=f"FORMATION KILLED - EMERGENCY EXIT WITH CODE {code}",
            )
        except Exception:
            pass  # Don't care if logging fails

        # Flush output streams (try to get any final messages out)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass

        # EXIT NOW!
        os._exit(code)

    async def start_server(
        self, host: Optional[str] = None, port: Optional[int] = None, block: bool = True
    ) -> "FormationServer":
        """
        Start the Formation API server.

        This starts an HTTP server that exposes the formation's capabilities
        via REST API endpoints. The server provides both admin operations
        (formation management) and client operations (user interactions).

        Args:
            host: Override host from formation.afs (default: use config value)
            port: Override port from formation.afs (default: use config value)
            block: Whether to block until server starts (default: True)
                   If True, this method will block until the server is started.
                   If False, returns an awaitable that resolves when startup completes.

        Returns:
            FormationServer: The running server instance

        Raises:
            RuntimeError: If server configuration is missing or invalid

        Example:
            # Block mode (typical for standalone server)
            formation = Formation()
            await formation.load("my-formation.afs")
            server = await formation.start_server()  # Auto-starts overlord, then blocks

            # Non-blocking mode with proper error handling
            formation = Formation()
            await formation.load("my-formation.afs")

            try:
                server = await formation.start_server(block=False)
                print("Server started successfully!")
            except Exception as e:
                print(f"Server startup failed: {e}")

            # Continue using formation...
            await server.stop()  # Stop when done
        """
        # Ensure configuration is loaded
        if not self.config:
            raise RuntimeError("No configuration loaded. Call load() first.")

        # Ensure we have server configuration
        if not hasattr(self, "_server_config"):
            raise RuntimeError(
                "Server configuration not found. Ensure your formation.afs "
                "has a 'server' section."
            )

        # Check for existing server instance
        if self._formation_server is not None:
            if self._formation_server.is_running:
                raise RuntimeError(
                    "A Formation server is already running. "
                    "Stop the existing server before starting a new one."
                )
            else:
                # Server exists but not running, we can reuse or replace it
                observability.observe(
                    event_type=observability.ServerEvents.SERVER_RESTARTING,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "formation_api_server",
                        "action": "replacing_stopped_server",
                        "formation_id": self.formation_id,
                    },
                    description="Replacing existing stopped server instance",
                )

        # Import FormationServer here to avoid circular imports
        from .server import FormationServer

        # Get configuration values
        config_host = self._server_config.get("host", "127.0.0.1")
        config_port = self._server_config.get("port", 8271)

        # Use provided values or fall back to config
        actual_host = host or config_host
        actual_port = port or config_port

        # Create server instance with debug and access_log settings
        self._formation_server = FormationServer(
            formation=self,
            host=actual_host,
            port=actual_port,
            debug=self._server_config.get("debug", False),
            access_log=self._server_config.get("access_log", False),
        )

        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTING,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_api_server",
                "host": actual_host,
                "port": actual_port,
                "block_mode": block,
                "has_overlord": hasattr(self, "_overlord") and self._overlord is not None,
            },
            description=f"Starting Formation API server on {actual_host}:{actual_port}",
        )

        # Auto-start overlord if not already running
        if not hasattr(self, "_overlord") or self._overlord is None:
            observability.observe(
                event_type=observability.ServerEvents.OVERLORD_STARTING,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_api_server",
                    "formation_id": self.formation_id,
                    "has_overlord": False,
                    "action": "auto_starting_overlord",
                },
                description="Auto-starting overlord for Formation API server",
            )

            # Auto-start overlord for cleaner API
            await self.start_overlord()

        # Start the server
        # Don't install signal handlers - let the parent process handle them
        if block:
            await self._formation_server.start(block=True, install_signal_handlers=False)
        else:
            await self._formation_server.start(block=False, install_signal_handlers=False)

        return self._formation_server

    def is_server_running(self) -> bool:
        """
        Check if the Formation API server is currently running.

        Returns:
            bool: True if server exists and is running, False otherwise
        """
        return self._formation_server is not None and self._formation_server.is_running

    def is_overlord_running(self) -> bool:
        """
        Check if the Overlord is currently running.

        Returns:
            bool: True if overlord exists and is running, False otherwise
        """
        return self._overlord is not None

    def has_persistent_memory(self) -> bool:
        """
        Check if persistent memory is configured and available.

        Returns:
            bool: True if long-term memory is configured, False otherwise
        """
        return hasattr(self, "_long_term_memory") and self._long_term_memory is not None

    def _clear_config_dict(self, config_name: str) -> None:
        """
        Helper method to clear a configuration dictionary if it exists and has a clear method.

        Args:
            config_name: Name of the configuration attribute to clear
        """
        if hasattr(self, config_name):
            config_obj = getattr(self, config_name)
            if hasattr(config_obj, "clear"):
                config_obj.clear()

    def stop(self) -> None:
        """
        Stop formation infrastructure and cleanup resources WITHOUT exiting the process.

        This method performs resource cleanup only:
        - Cancels all active operations
        - Stops the overlord gracefully (if running)
        - Stops the API server (if running)
        - Clears all configurations and service references
        - Cleans up memory and connections
        - Your Python script continues running after this

        Use this when:
        - You want to stop the formation but continue your script
        - You need to restart the formation with different config
        - You're testing or debugging and want to clean up without exiting
        - You want full control over when your process exits

        Compare with other shutdown methods:
        - stop(): Cleanup only, process continues (THIS METHOD)
        - shutdown(): No cleanup, immediate exit
        - ashutdown(): Graceful cleanup, then exit
        - kill(): Emergency abort, immediate exit

        Example:
            formation = Formation()
            await formation.load("formation.afs")
            await formation.start_overlord()

            # Use the formation...

            formation.stop()  # Stop formation
            print("Formation stopped, doing other work...")  # Script continues
        """
        try:
            # Cancel all active operations first
            if self._formation_cancellation_token:
                self._formation_cancellation_token.cancel()

            # Stop overlord if still running (gracefully)
            if self._is_running:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.stop_overlord())
                    else:
                        asyncio.run(self.stop_overlord())
                except Exception as e:
                    print(f"   ⚠️  Cleanup warning: {e}")

            # Stop API server if running
            if hasattr(self, "_formation_server") and self._formation_server:
                if self._formation_server.is_running:
                    observability.observe(
                        event_type=observability.SystemEvents.CLEANUP,
                        level=observability.EventLevel.INFO,
                        data={
                            "service": "formation_api_server",
                            "formation_id": self.formation_id,
                            "cleanup_stage": "formation_stop",
                        },
                        description="Stopping Formation API server during formation cleanup",
                    )
                    # Run async stop in sync context
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self._formation_server.stop())
                        else:
                            asyncio.run(self._formation_server.stop())
                    except Exception as e:
                        observability.observe(
                            event_type=observability.SystemEvents.CLEANUP,
                            level=observability.EventLevel.WARNING,
                            data={
                                "service": "formation_api_server",
                                "formation_id": self.formation_id,
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "cleanup_stage": "formation_stop",
                            },
                            description=f"Error stopping Formation API server during cleanup: {e}",
                        )
                self._formation_server = None

            # Cleanup formation resources
            self.config = None
            self.secrets_manager = None
            self._configured_services.clear()
            self._api_keys.clear()

            # Clean up async operation management
            self._formation_cancellation_token = None

            # Clear individual service configurations
            # Use dict check to handle both dict and object types
            if isinstance(self._llm_config, dict):
                self._llm_config.clear()
            else:
                self._llm_config = {}

            if isinstance(self._memory_config, dict):
                self._memory_config.clear()
            else:
                self._memory_config = {}

            if isinstance(self._mcp_config, dict):
                self._mcp_config.clear()
            else:
                self._mcp_config = {}

            if isinstance(self._a2a_config, dict):
                self._a2a_config.clear()
            else:
                self._a2a_config = {}

            if isinstance(self._logging_config, dict):
                self._logging_config.clear()
            else:
                self._logging_config = {}

            if isinstance(self._clarification_config, dict):
                self._clarification_config.clear()
            else:
                self._clarification_config = {}

            # Document processing config is special - it's a DocumentProcessingConfig object
            self._document_processing_config = {}

            if isinstance(self._scheduler_config, dict):
                self._scheduler_config.clear()
            else:
                self._scheduler_config = {}

            if isinstance(self._agents_config, list):
                self._agents_config.clear()
            else:
                self._agents_config = []

        except Exception as e:
            print(f"❌ Error during formation cleanup: {e}")
            print("💡 Suggestion: Some resources may not have been properly cleaned up")

    @property
    def is_running(self) -> bool:
        """Check if overlord is currently running."""
        return self._is_running

    @property
    def secret_placeholders(self) -> Dict[str, str]:
        """Get the secret placeholder mappings (returns a copy to prevent external modification)."""
        return self._secret_placeholders.copy()

    @property
    def mcp_servers(self) -> List[Dict[str, Any]]:
        """Get the list of MCP server configurations."""
        return getattr(self, "_mcp_servers", [])

    def get_overlord(self) -> Optional[Any]:
        """
        Get the overlord instance if it's running.

        Returns:
            The overlord instance if running, None otherwise
        """
        if self._is_running and self._overlord:
            return self._overlord
        return None

    def has_secret_placeholders(self) -> bool:
        """
        Check if secret placeholders are being tracked.

        Returns:
            True if secret placeholders are initialized and not None
        """
        return hasattr(self, "_secret_placeholders") and self._secret_placeholders is not None

    def add_secret_placeholder(self, path: str, placeholder: str) -> None:
        """
        Add a secret placeholder mapping.

        Args:
            path: The configuration path (e.g., "agents[0].api_key")
            placeholder: The placeholder value to store
        """
        with self._config_lock:
            if self._secret_placeholders is not None:
                self._secret_placeholders[path] = placeholder

    def remove_secret_placeholders_for_prefix(self, prefix: str) -> None:
        """
        Remove all secret placeholders that start with the given prefix.

        Args:
            prefix: The prefix to match (e.g., "agents[0]")
        """
        with self._config_lock:
            # Check if placeholders exist and contain entries
            if self._secret_placeholders:
                keys_to_remove = [k for k in self._secret_placeholders if k.startswith(prefix)]
                for k in keys_to_remove:
                    del self._secret_placeholders[k]

    async def remove_agent_from_overlord(self, agent_id: str) -> bool:
        """
        Remove an agent from the running overlord.

        Args:
            agent_id: ID of the agent to remove

        Returns:
            True if agent was removed, False if overlord not running or agent not found
        """
        if self._is_running and self._overlord:
            if agent_id in self._overlord.agents:
                # Remove agent from overlord
                del self._overlord.agents[agent_id]

                # Also remove from active agents tracker if present
                if hasattr(self._overlord, "active_agents_tracker"):
                    self._overlord.active_agents_tracker.remove_agent(agent_id)

                return True
        return False

    def get_formation_path(self) -> Optional[str]:
        """
        Get the formation file path.

        Returns:
            The path to the formation file, or None if not set
        """
        return self._formation_path if hasattr(self, "_formation_path") else None

    def get_formation_id(self) -> str:
        """Get the formation ID."""
        return self.formation_id

    def get_config(self) -> Optional[Dict[str, Any]]:
        """Get the loaded configuration (read-only)."""
        return self.config.copy() if self.config else None

    def create_cancellation_token(self) -> CancellationToken:
        """
        Create a new cancellation token for async operations.

        Returns:
            CancellationToken: Token that can be used to cancel operations
        """
        return self._operation_manager.create_cancellation_token()

    def set_formation_cancellation_token(self, token: Optional[CancellationToken]) -> None:
        """
        Set the formation-wide cancellation token.

        Args:
            token: Cancellation token to use for formation operations
        """
        self._formation_cancellation_token = token

    def cancel_all_operations(self) -> None:
        """Cancel all active async operations in this formation."""
        if self._formation_cancellation_token:
            self._formation_cancellation_token.cancel()

    def get_timeout_config(self) -> TimeoutConfig:
        """Get the current timeout configuration."""
        return self._timeout_config

    def set_timeout_config(self, config: TimeoutConfig) -> None:
        """
        Set new timeout configuration.

        Args:
            config: New timeout configuration to use
        """
        self._timeout_config = config

    def get_retry_config(self) -> RetryConfig:
        """Get the current retry configuration."""
        return self._retry_config

    def set_retry_config(self, config: RetryConfig) -> None:
        """
        Set new retry configuration.

        Args:
            config: New retry configuration to use
        """
        self._retry_config = config

    # =============================================================================
    # DYNAMIC COMPONENT MANAGEMENT HELPERS
    # =============================================================================

    async def _resolve_schema(
        self, schema: Union[Dict[str, Any], str], schema_type: str
    ) -> Dict[str, Any]:
        """
        Resolve a schema from either inline dict or file path using FormationLoader.

        Args:
            schema: Either a dict containing the schema, or a path to YAML/JSON file
            schema_type: Type of schema for error messages ("agent" or "mcp")

        Returns:
            Dict[str, Any]: Resolved schema dictionary

        Raises:
            TypeError: If schema is not dict or str
            ValueError: If schema is invalid or file cannot be loaded
        """
        if isinstance(schema, dict):
            # Inline schema - validate it has required fields and interpolate secrets
            if "id" not in schema:
                raise ValueError(f"Inline {schema_type} schema missing required 'id' field")

            # Apply secrets interpolation to inline schema
            return await self.secrets_manager.interpolate_secrets(schema)

        elif isinstance(schema, str):
            # File path - use FormationLoader to load and process
            try:
                formation_loader = FormationLoader()
                loaded_config, _, _ = await formation_loader.load(schema, self.secrets_manager)

                # For individual components, extract the relevant section
                if schema_type == "agent":
                    # If it's a standalone agent file, return as-is
                    if "id" in loaded_config and "name" in loaded_config:
                        return loaded_config
                    # If it's a formation file, extract first agent
                    elif "agents" in loaded_config and loaded_config["agents"]:
                        return loaded_config["agents"][0]
                    else:
                        raise ValueError(f"No valid agent configuration found in {schema}")

                elif schema_type == "mcp":
                    # If it's a standalone MCP file, return as-is
                    if "id" in loaded_config and "type" in loaded_config:
                        return loaded_config
                    # If it's a formation file, extract first MCP server
                    elif (
                        "mcp" in loaded_config
                        and "servers" in loaded_config["mcp"]
                        and loaded_config["mcp"]["servers"]
                    ):
                        return loaded_config["mcp"]["servers"][0]
                    else:
                        raise ValueError(f"No valid MCP server configuration found in {schema}")

            except Exception as e:
                raise ValueError(f"Failed to load {schema_type} schema from {schema}: {e}") from e

    async def _check_agent_conflict(self, agent_schema: Dict[str, Any]) -> None:
        """
        Check if agent ID conflicts with existing agents.

        Args:
            agent_schema: Resolved agent schema

        Raises:
            ValueError: If agent ID already exists
        """
        agent_id = agent_schema["id"]

        # Check running agents
        if self._overlord:
            existing_agents = await self._overlord.list_agents()
            if agent_id in existing_agents:
                raise ValueError(f"Agent ID '{agent_id}' already exists in running formation")

        # Check for duplicates in existing agents
        existing_agent_ids = [agent["id"] for agent in self.config.get("agents", [])]
        if agent_id in existing_agent_ids:
            raise ValueError(f"Agent ID '{agent_id}' already exists in formation configuration")

    async def _check_mcp_conflict(self, mcp_schema: Dict[str, Any]) -> None:
        """
        Check if an MCP server schema conflicts with existing configuration.

        Args:
            mcp_schema: The MCP server schema to validate

        Raises:
            ValueError: If MCP server ID conflicts with existing configuration
        """
        server_id = mcp_schema.get("id")
        if not server_id:
            raise ValueError("MCP schema must include 'id' field")

        # Check for duplicates in running overlord
        if self._overlord:
            servers = await self._overlord.list_mcp_servers()
            if server_id in servers:
                raise ValueError(f"MCP server ID '{server_id}' already exists in running overlord")

        # Check for duplicates in existing MCP configuration
        existing_server_ids = []
        mcp_config = self.config.get("mcp", {})
        if "servers" in mcp_config:
            existing_server_ids.extend([server["id"] for server in mcp_config["servers"]])

        if server_id in existing_server_ids:
            raise ValueError(
                f"MCP server ID '{server_id}' already exists in formation configuration"
            )

    def _validate_agent_schema(self, agent_schema: Dict[str, Any]) -> None:
        """
        Validate agent schema structure and required fields.

        Args:
            agent_schema: The agent schema to validate

        Raises:
            ValueError: If schema is invalid or missing required fields
        """
        required_fields = ["schema", "id", "name", "description"]

        for field in required_fields:
            if field not in agent_schema:
                raise ValueError(f"Agent schema missing required field: '{field}'")

        # Validate schema version
        schema_version = agent_schema.get("schema")
        if schema_version != "1.0.0":
            raise ValueError(f"Unsupported schema version: {schema_version}. Expected: 1.0.0")

    def _validate_mcp_schema(self, mcp_schema: Dict[str, Any]) -> None:
        """
        Validate MCP server schema structure and required fields.

        Args:
            mcp_schema: The MCP server schema to validate

        Raises:
            ValueError: If schema is invalid or missing required fields
        """
        required_fields = ["schema", "id", "description", "type"]

        for field in required_fields:
            if field not in mcp_schema:
                raise ValueError(f"MCP schema missing required field: '{field}'")

        # Validate schema version
        schema_version = mcp_schema.get("schema")
        if schema_version != "1.0.0":
            raise ValueError(f"Unsupported schema version: {schema_version}. Expected: 1.0.0")

        # Validate server type and required fields
        server_type = mcp_schema.get("type")
        if server_type not in ["command", "http"]:
            raise ValueError(f"Invalid MCP server type: {server_type}. Must be 'command' or 'http'")

        if server_type == "command" and "command" not in mcp_schema:
            raise ValueError("Command-type MCP server missing 'command' field")

        if server_type == "http":
            if "endpoint" not in mcp_schema:
                raise ValueError("HTTP-type MCP server missing 'endpoint' field")

            # Validate endpoint URL format
            endpoint = mcp_schema.get("endpoint", "")
            if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
                raise ValueError(
                    f"Invalid endpoint URL: {endpoint}. Must start with http:// or https://"
                )

    # =============================================================================
    # DYNAMIC AGENT MANAGEMENT
    # =============================================================================

    async def add_agent(self, schema: Union[Dict[str, Any], str]) -> str:
        """
        Add an agent to the running overlord from a schema definition.

        Args:
            schema: Either a dict containing the agent schema,
                   or a path to YAML/JSON file

        Returns:
            The agent_id that was added

        Raises:
            OverlordStateError: If overlord is not running
            ValueError: If agent ID already exists or schema is invalid
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "add_agent", "schema_type": type(schema).__name__},
            )

        # Resolve schema from dict or file path
        agent_schema = await self._resolve_schema(schema, "agent")

        # Validate schema structure
        self._validate_agent_schema(agent_schema)

        # Check for conflicts
        await self._check_agent_conflict(agent_schema)

        # Delegate to overlord (overlord will need to handle schema-based agent creation)
        return await self._overlord.create_agent_from_schema(agent_schema)

    def remove_agent(self, agent_id: str) -> bool:
        """
        Remove an agent from the running overlord using the "delete when done" pattern.

        The agent will be marked for deletion and actually removed when it finishes
        any current work. This ensures no active requests are interrupted.

        Note: This is the synchronous version. Use remove_agent_async() for async contexts.

        Args:
            agent_id: The ID of the agent to remove

        Returns:
            True if the agent was successfully marked for removal

        Raises:
            OverlordStateError: If overlord is not running
            AgentNotFoundError: If no agent with the given ID exists
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "remove_agent", "agent_id": agent_id},
            )

        # Handle event loop properly - check if we're already in an event loop
        try:
            # Try to get the current event loop
            asyncio.get_running_loop()
            # If we're in an event loop, we need to handle this differently
            # Create a future and run it in the loop
            import threading

            result = None
            exception = None

            def run_in_thread():
                nonlocal result, exception
                try:
                    # Create a new event loop in the thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(self._overlord.remove_agent(agent_id))
                    finally:
                        new_loop.close()
                except Exception as e:
                    exception = e

            # Run in a separate thread to avoid event loop conflicts
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()

            if exception:
                raise exception
            return result

        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return asyncio.run(self._overlord.remove_agent(agent_id))

    async def remove_agent_async(self, agent_id: str) -> bool:
        """
        Remove an agent from the running overlord using the "delete when done" pattern (async version).

        The agent will be marked for deletion and actually removed when it finishes
        any current work. This ensures no active requests are interrupted.

        Args:
            agent_id: The ID of the agent to remove

        Returns:
            True if the agent was successfully marked for removal

        Raises:
            OverlordStateError: If overlord is not running
            AgentNotFoundError: If no agent with the given ID exists
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "remove_agent", "agent_id": agent_id},
            )

        return await self._overlord.remove_agent(agent_id)

    def add_agent_to_config(self, agent_config: Dict[str, Any]) -> None:
        """
        Safely add an agent to the formation config with thread synchronization.

        Args:
            agent_config: Agent configuration dictionary

        Raises:
            ValueError: If agent ID already exists
        """
        with self._config_lock:
            if not self.config:
                raise RuntimeError("Formation config not loaded")

            # Ensure agents list exists
            if "agents" not in self.config:
                self.config["agents"] = []

            # Check for existing agent ID
            agent_id = agent_config.get("id")
            if agent_id and any(a.get("id") == agent_id for a in self.config["agents"]):
                raise ValueError(f"Agent with id '{agent_id}' already exists")

            # Add agent with source tracking
            agent_config = agent_config.copy()
            agent_config["source"] = "api"
            self.config["agents"].append(agent_config)

    async def save_agent_to_file(
        self, agent_config: Dict[str, Any], auto_load: bool = False
    ) -> str:
        """
        Save an agent configuration to a YAML file in the agents/ directory.

        Args:
            agent_config: Agent configuration dictionary
            auto_load: If True, automatically load the agent into formation config and overlord

        Returns:
            str: Path to the created file

        Raises:
            ValueError: If formation path is not set
            AgentPersistenceError: If the save operation fails
        """
        if not self._formation_path:
            raise ValueError("Formation path not set - cannot save agent file")

        from .utils.agent_persistence import save_agent_to_file

        return await save_agent_to_file(
            agent_config,
            self._formation_path,
            formation=self if auto_load else None,
            auto_load=auto_load,
        )

    async def update_agent_file(
        self, agent_id: str, updates: Dict[str, Any], auto_reload: bool = False
    ) -> str:
        """
        Update an agent's YAML file with partial data and optionally reload it.

        Args:
            agent_id: ID of the agent to update
            updates: Dictionary of fields to update
            auto_reload: If True, automatically reload the agent in formation and overlord

        Returns:
            str: Path to the updated file

        Raises:
            ValueError: If formation path is not set or agent file doesn't exist
            AgentPersistenceError: If the update operation fails
        """
        if not self._formation_path:
            raise ValueError("Formation path not set - cannot update agent file")

        from .utils.agent_persistence import update_agent_file

        return await update_agent_file(
            agent_id,
            updates,
            self._formation_path,
            formation=self if auto_reload else None,
            auto_reload=auto_reload,
        )

    def update_agent_in_config(self, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Safely update an agent in the formation config with thread synchronization.

        Args:
            agent_id: ID of agent to update
            updates: Fields to update

        Returns:
            Updated agent configuration

        Raises:
            ValueError: If agent not found
        """
        with self._config_lock:
            if not self.config:
                raise RuntimeError("Formation config not loaded")

            agents = self.config.get("agents", [])
            agent = next((a for a in agents if a.get("id") == agent_id), None)

            if not agent:
                raise ValueError(f"Agent '{agent_id}' not found")

            # Apply updates
            agent.update(updates)
            return agent.copy()

    def remove_agent_from_config(self, agent_id: str) -> bool:
        """
        Safely remove an agent from the formation config with thread synchronization.

        Only agents created via API (source="api") can be removed.

        Args:
            agent_id: ID of agent to remove

        Returns:
            True if agent was removed

        Raises:
            ValueError: If agent not found or cannot be removed
        """
        with self._config_lock:
            if not self.config:
                raise RuntimeError("Formation config not loaded")

            agents = self.config.get("agents", [])
            agent_idx = next((i for i, a in enumerate(agents) if a.get("id") == agent_id), None)

            if agent_idx is None:
                raise ValueError(f"Agent '{agent_id}' not found")

            agent = agents[agent_idx]

            # Check if agent can be removed
            if agent.get("source") != "api":
                raise ValueError(
                    f"Agent '{agent_id}' was not created via API and cannot be removed"
                )

            # Remove agent
            agents.pop(agent_idx)
            return True

    async def add_agent_to_overlord(self, processed_config: Dict[str, Any]) -> None:
        """
        Add a new agent to the running overlord.

        This method creates an agent instance from the processed configuration
        and adds it to the overlord's runtime. It should be used when adding
        agents dynamically after the overlord has started.

        Args:
            processed_config: Processed agent configuration dictionary
                             (after secrets processing and validation)

        Raises:
            RuntimeError: If overlord is not running
            ValueError: If agent creation fails or agent ID already exists
        """
        if not self._is_running or not self._overlord:
            raise RuntimeError("Overlord is not running")

        # Use the overlord's public method for atomic agent addition
        # This encapsulates all the logic including:
        # - Agent creation and validation
        # - State updates with proper locking
        # - Workflow component updates
        # - Rollback on failure
        await self._overlord.add_agent_runtime(processed_config)

    async def list_agents(self) -> Dict[str, Dict[str, Any]]:
        """
        List all agents in the running overlord with their status.

        Returns:
            Dictionary mapping agent IDs to their information including status
            (idle/busy/pending_deletion)

        Raises:
            OverlordStateError: If overlord is not running
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "list_agents"},
            )

        return await self._overlord.list_agents()

    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """
        Get detailed status information for a specific agent.

        Args:
            agent_id: The ID of the agent to get status for

        Returns:
            Dictionary containing agent status information

        Raises:
            OverlordStateError: If overlord is not running
            AgentNotFoundError: If no agent with the given ID exists
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "get_agent_status", "agent_id": agent_id},
            )

        agents = await self._overlord.list_agents()
        if agent_id not in agents:
            from ..datatypes.exceptions import AgentNotFoundError

            raise AgentNotFoundError(agent_id)

        return agents[agent_id]

    # =============================================================================
    # DYNAMIC MCP SERVER MANAGEMENT
    # =============================================================================

    async def add_mcp(self, schema: Union[Dict[str, Any], str]) -> str:
        """
        Add an MCP server to the running overlord from a schema definition.

        Args:
            schema: Either a dict containing the MCP schema,
                   or a path to YAML/JSON file

        Returns:
            The server_id that was added

        Raises:
            OverlordStateError: If overlord is not running
            ValueError: If MCP server ID already exists or schema is invalid
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "add_mcp", "schema_type": type(schema).__name__},
            )

        # Resolve schema from dict or file path
        mcp_schema = await self._resolve_schema(schema, "mcp")

        # Validate schema structure
        self._validate_mcp_schema(mcp_schema)

        # Check for conflicts
        await self._check_mcp_conflict(mcp_schema)

        # Delegate to overlord (overlord will need to handle schema-based MCP creation)
        return await self._overlord.create_mcp_server_from_schema(mcp_schema)

    def remove_mcp(self, server_id: str) -> bool:
        """
        Remove an MCP server from the running overlord using the "delete when done" pattern.

        The server will be marked for deletion and actually removed when it finishes
        any current operations. This ensures no active requests are interrupted.

        Note: This is the synchronous version. Use remove_mcp_async() for async contexts.

        Args:
            server_id: The ID of the MCP server to remove

        Returns:
            True if the server was successfully marked for removal

        Raises:
            OverlordStateError: If overlord is not running
            MCPServerNotFoundError: If no server with the given ID exists
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "remove_mcp", "server_id": server_id},
            )

        # Handle event loop properly - check if we're already in an event loop
        try:
            # Try to get the current event loop
            asyncio.get_running_loop()
            # If we're in an event loop, we need to handle this differently
            # Create a future and run it in the loop

            result = None
            exception = None

            def run_in_thread():
                nonlocal result, exception
                try:
                    # Create a new event loop in the thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(
                            self._overlord.remove_mcp_server(server_id)
                        )
                    finally:
                        new_loop.close()
                except Exception as e:
                    exception = e

            # Run in a separate thread to avoid event loop conflicts
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()

            if exception:
                raise exception
            return result

        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return asyncio.run(self._overlord.remove_mcp_server(server_id))

    async def remove_mcp_async(self, server_id: str) -> bool:
        """
        Remove an MCP server from the running overlord using the "delete when done" pattern (async version).

        The server will be marked for deletion and actually removed when it finishes
        any current operations. This ensures no active requests are interrupted.

        Args:
            server_id: The ID of the MCP server to remove

        Returns:
            True if the server was successfully marked for removal

        Raises:
            OverlordStateError: If overlord is not running
            MCPServerNotFoundError: If no server with the given ID exists
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "remove_mcp", "server_id": server_id},
            )

        return await self._overlord.remove_mcp_server(server_id)

    async def list_mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        """
        List all MCP servers in the running overlord with their status.

        Returns:
            Dictionary mapping server IDs to their information including status
            (connected/disconnected/pending_deletion)

        Raises:
            OverlordStateError: If overlord is not running
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "list_mcp_servers"},
            )

        return await self._overlord.list_mcp_servers()

    async def get_mcp_status(self, server_id: str) -> Dict[str, Any]:
        """
        Get detailed status information for a specific MCP server.

        Args:
            server_id: The ID of the MCP server to get status for

        Returns:
            Dictionary containing MCP server status information

        Raises:
            OverlordStateError: If overlord is not running
            MCPServerNotFoundError: If no server with the given ID exists
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "get_mcp_status", "server_id": server_id},
            )

        servers = await self._overlord.list_mcp_servers()
        if server_id not in servers:
            from ..datatypes.exceptions import MCPServerNotFoundError

            raise MCPServerNotFoundError(server_id)

        return servers[server_id]

    # Scheduler Methods
    async def get_active_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all active scheduled jobs.

        Returns:
            List of active scheduled jobs with their details

        Raises:
            OverlordStateError: If overlord is not running
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "get_active_jobs"},
            )

        scheduler_service = await self._overlord.get_scheduler_service()
        if not scheduler_service:
            return []

        return await scheduler_service.manager.get_all_jobs(status="active")

    async def get_all_jobs(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        is_recurring: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all scheduled jobs with optional filtering.

        Args:
            status: Filter by job status ('active', 'paused', 'completed', 'failed')
            user_id: Filter by user ID
            is_recurring: Filter by job type (True for recurring, False for one-time)
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip for pagination

        Returns:
            List of scheduled jobs matching the criteria

        Raises:
            OverlordStateError: If overlord is not running
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "get_all_jobs"},
            )

        scheduler_service = await self._overlord.get_scheduler_service()
        if not scheduler_service:
            return []

        return await scheduler_service.manager.get_all_jobs(
            status=status, user_id=user_id, is_recurring=is_recurring, limit=limit, offset=offset
        )

    async def get_user_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all scheduled jobs for a specific user.

        Args:
            user_id: The user ID to get jobs for

        Returns:
            List of scheduled jobs for the user

        Raises:
            OverlordStateError: If overlord is not running
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "get_user_jobs"},
            )

        scheduler_service = await self._overlord.get_scheduler_service()
        if not scheduler_service:
            return []

        return await scheduler_service.manager.get_all_jobs(user_id=user_id)

    async def get_job_audit_trail(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get the audit trail for a specific job.

        Args:
            job_id: The job ID to get audit trail for

        Returns:
            List of audit events for the job

        Raises:
            OverlordStateError: If overlord is not running
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "get_job_audit_trail"},
            )

        scheduler_service = await self._overlord.get_scheduler_service()
        if not scheduler_service:
            return []

        return await scheduler_service.manager.get_job_audit_trail(job_id)

    async def get_recent_audit_trail(
        self, limit: int = 100, user_id: Optional[str] = None, action: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent audit trail events.

        Args:
            limit: Maximum number of events to return (default: 100)
            user_id: Filter by user ID
            action: Filter by action type

        Returns:
            List of recent audit events

        Raises:
            OverlordStateError: If overlord is not running
        """
        if not self._is_running or not self._overlord:
            raise OverlordStateError(
                "stopped",
                "running",
                {"operation": "get_recent_audit_trail"},
            )

        scheduler_service = await self._overlord.get_scheduler_service()
        if not scheduler_service:
            return []

        return await scheduler_service.manager.get_recent_audit_trail(
            limit=limit, user_id=user_id, action=action
        )

    async def wait_for_mcp_readiness(self, timeout: float = 30.0) -> bool:
        """
        Wait for built-in MCP registration to complete.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if registration completed successfully, False if timed out or failed
        """
        if not self._builtin_mcp_task:
            # No registration task running
            return True

        try:
            await asyncio.wait_for(self._builtin_mcp_task, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"timeout": timeout},
                description=f"Built-in MCP registration timed out after {timeout} seconds",
            )
            return False
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Built-in MCP registration failed: {e}",
            )
            return False

    def is_mcp_ready(self) -> bool:
        """
        Check if built-in MCP registration is complete.

        Returns:
            True if registration is complete or not needed, False if still in progress
        """
        if not self._builtin_mcp_task:
            return True
        return self._builtin_mcp_task.done()
