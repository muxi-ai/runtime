# =============================================================================
# FORMATION - OPERATIONAL LIFECYCLE MANAGEMENT
# =============================================================================
# Title:        Formation - Muxi Runtime Operational Platform
# Description:  Handles configuration loading, service initialization, and overlord lifecycle
# Role:         Operations layer that manages infrastructure and coordinates services
# Usage:        formation = Formation(); formation.load("config.yaml"); muxi = formation.start_overlord()
# Author:       Muxi Framework Team
#
# The Formation manages the operational lifecycle of the Muxi runtime, handling all
# infrastructure concerns and service coordination. It separates operational concerns
# from intelligence concerns, providing a clean interface between platform management
# and intelligent decision-making.
#
# Usage Pattern:
#
#   from muxi.runtime import Formation
#
#   formation = Formation()
#   formation.load("my-formation.yaml")
#   muxi = formation.start_overlord()
#
#   # Use the intelligence
#   response = muxi.chat("Hello!")
#
#   # Cleanup
#   formation.stop_overlord()    # Graceful shutdown
#   # formation.kill_overlord()  # Immediate shutdown
#   formation.stop()             # Full cleanup
#
# =============================================================================

import asyncio
from typing import Any, Dict, List, Optional, Union

# Configuration imports
from .config.validation import validate_formation
from .config.formation_loader import FormationLoader

# Service imports
from ..services import observability
from ..services.secrets.secrets_manager import SecretsManager

# Validation imports
from ..utils import DependencyValidator

# Async operation imports
from ..utils.async_operation_manager import get_operation_manager, execute_with_timeout
from ..datatypes.async_operations import TimeoutConfig, CancellationToken

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
    add_error_context,
)

# Utility imports
from .utils import generate_api_key
from ..utils.user_dirs import set_formation_id
import shlex


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

        # Dependency validation
        self._dependency_validator = DependencyValidator()

        # Service configuration (prepared for overlord handoff)
        self._configured_services: Dict[str, Any] = {}
        self._api_keys: Dict[str, str] = {}

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

    def load(self, config_path: str) -> None:
        """
        Load and validate formation configuration.

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
        """
        if self._is_running:
            raise OverlordStateError(
                "running",
                "stopped",
                {"operation": "load_configuration", "config_path": config_path},
            )

        try:
            # Emit formation loading started event
            observability.observe(
                event_type=observability.SystemEvents.OVERLORD_INITIALIZING,
                level=observability.EventLevel.INFO,
                data={"formation_path": config_path},
                description=f"Starting formation loading from {config_path}",
            )

            # Normalize and validate config path (file or directory)
            normalized_path = self._normalize_config_path(config_path)

            # Store formation path for secrets management
            self._formation_path = normalized_path

            # Initialize secrets manager
            self.secrets_manager = SecretsManager(normalized_path)

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

            # Load configuration
            self.config = asyncio.run(self._load_config(normalized_path))

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

            # Set formation ID
            self.formation_id = self.config.get("formation_id", "default-formation")
            set_formation_id(self.formation_id)

            # Prepare services (but don't start them yet)
            self._prepare_services()

        except (
            ConfigurationNotFoundError,
            ConfigurationValidationError,
            ConfigurationLoadError,
            DependencyValidationError,
            OverlordStateError,
        ) as e:
            # Clean up on known failure types
            self.config = None
            self.secrets_manager = None
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
            str: Normalized path to formation.yaml file

        Raises:
            ConfigurationNotFoundError: If neither file nor directory exists
            ConfigurationValidationError: If directory exists but has no formation.yaml
        """
        import os

        if not os.path.exists(config_path):
            raise ConfigurationNotFoundError(
                config_path, {"operation": "normalize_config_path", "attempted_path": config_path}
            )

        # If it's a file, return as-is
        if os.path.isfile(config_path):
            if not config_path.endswith((".yaml", ".yml")):
                raise ConfigurationValidationError(
                    [f"Formation file must be YAML format (.yaml or .yml): {config_path}"],
                    {"config_path": config_path, "operation": "validate_file_extension"},
                )
            return config_path

        # If it's a directory, look for formation.yaml
        if os.path.isdir(config_path):
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
                        f"Create a formation.yaml file in the directory '{config_path}' or "
                        "provide the direct path to your formation configuration file"
                    ),
                    "example": f"Try: formation.load('{config_path}/formation.yaml') or create the missing file",
                },
            )

        raise ConfigurationValidationError(
            [f"Config path must be a file or directory, got: {type(config_path).__name__}"],
            {
                "config_path": config_path,
                "operation": "validate_config_path",
                "suggestion": "Provide either a path to a formation.yaml file or a directory containing formation.yaml",
                "examples": [
                    "formation.load('path/to/formation.yaml')",
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

    async def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load formation configuration from file with timeout and retry support.

        Args:
            config_path: Path to formation configuration

        Returns:
            Loaded configuration dictionary

        Raises:
            ConfigurationLoadError: If configuration loading fails after retries
        """

        async def _load_operation():
            """Load configuration with timeout and error handling for retry logic."""

            async def _timeout_operation():
                formation_loader = FormationLoader()
                return await formation_loader.load(config_path, self.secrets_manager)

            result = await execute_with_timeout(
                _timeout_operation,
                operation_type="config_load",
                description=f"Loading formation configuration from {config_path}",
                timeout=self._timeout_config.config_load_timeout,
                cancellation_token=self._formation_cancellation_token,
            )

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
                    # Check if the error is retryable (e.g., network issues, file system issues)
                    error_str = str(result.error).lower()
                    if any(
                        pattern in error_str
                        for pattern in ["network", "connection", "timeout", "temporary"]
                    ):
                        raise NetworkTransientError(
                            f"Configuration loading failed: {result.error}",
                            details={
                                "config_path": config_path,
                                "original_error": str(result.error),
                            },
                        )
                    else:
                        # Non-retryable error - re-raise as is
                        raise result.error

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
                a2a_config_obj = A2AServiceSchema(
                    enabled=self._a2a_config.get("enabled", True),
                    server_enabled=self._a2a_config.get("server", {}).get("enabled", False),
                    server_host=self._a2a_config.get("server", {}).get("host", "0.0.0.0"),
                    server_port=self._a2a_config.get("server", {}).get("port", 8080),
                    external_registry_enabled=self._a2a_config.get("external_registry", {}).get(
                        "enabled", False
                    ),
                    registry_url=self._a2a_config.get("external_registry", {}).get("url"),
                    registration_timeout=self._a2a_config.get("external_registry", {}).get(
                        "timeout", 30.0
                    ),
                    require_auth=self._a2a_config.get("security", {}).get("require_auth", False),
                    allowed_origins=self._a2a_config.get("security", {}).get("allowed_origins"),
                )
                a2a_config_obj.validate()
            except Exception as e:
                print(
                    f"Warning: Invalid A2A configuration, using defaults. "
                    f"Validation error: {str(e)}. "
                    f"Config values: server_enabled={self._a2a_config.get('server', {}).get('enabled')}, "
                    f"server_port={self._a2a_config.get('server', {}).get('port')}, "
                    f"external_registry_enabled={self._a2a_config.get('outbound', {}).get('registries') is not None}, "
                    f"require_auth={self._a2a_config.get('security', {}).get('require_auth')}",
                    flush=True,
                )
                a2a_config_obj = A2AServiceSchema()

        # Create comprehensive service bundle for overlord handoff
        self._configured_services = {
            "formation_config": self.config,
            "secrets_manager": self.secrets_manager,
            "formation_path": self._formation_path,
            "api_keys": self._api_keys.copy(),
            # Service-specific configurations (validated and preprocessed)
            "llm_config": self._llm_config,
            "memory_config": self._memory_config,
            "mcp_config": mcp_config_obj,  # Standardized config object
            "a2a_config": a2a_config_obj,  # Standardized config object
            "logging_config": self._logging_config,
            "clarification_config": self._clarification_config,
            "document_processing_config": self._document_processing_config,
            "scheduler_config": self._scheduler_config,
            "runtime_config": self._runtime_config,
            "agents_config": self._agents_config,
        }

    def _setup_auth(self) -> None:
        """
        Setup authentication keys for the formation.

        Generates or uses configured API keys for user and admin access.
        """
        auth_config = self.config.get("auth", {}) if self.config else {}

        # Generate or use configured API keys
        self._api_keys["user"] = auth_config.get("user_api_key") or generate_api_key("user")
        self._api_keys["admin"] = auth_config.get("admin_api_key") or generate_api_key("admin")

    def _setup_llm_config(self) -> None:
        """Setup and validate LLM configuration."""
        self._llm_config = self.config.get("llm", {})

        # Validate basic LLM structure
        if not isinstance(self._llm_config, dict):
            raise ConfigurationValidationError(
                ["LLM configuration must be a dictionary"],
                {
                    "current_type": type(self._llm_config).__name__,
                    "suggestion": "Update your formation.yaml to have 'llm:' as a dictionary section",
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
                    "suggestion": "Add LLM configuration to your formation.yaml",
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
                    "suggestion": "Update your formation.yaml to have 'memory:' as a dictionary section",
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
        self._clarification_config = self.config.get("clarification", {})

        # Validate clarification structure
        if not isinstance(self._clarification_config, dict):
            raise ValueError("Clarification configuration must be a dictionary")

    def _setup_document_processing_config(self) -> None:
        """Setup and validate document processing configuration."""
        self._document_processing_config = self.config.get("document_processing", {})

        # Validate document processing structure
        if not isinstance(self._document_processing_config, dict):
            raise ValueError("Document processing configuration must be a dictionary")

    def _setup_scheduler_config(self) -> None:
        """Setup and validate scheduler configuration."""
        self._scheduler_config = self.config.get("scheduler", {})

        # Validate scheduler structure
        if not isinstance(self._scheduler_config, dict):
            raise ConfigurationValidationError(
                ["Scheduler configuration must be a dictionary"],
                {
                    "current_type": type(self._scheduler_config).__name__,
                    "suggestion": "Update your formation.yaml to have 'scheduler:' as a dictionary section",
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
        if self._scheduler_config.get("enabled", False):
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
                    "suggestion": "Update your formation.yaml to have 'runtime:' as a dictionary section",
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
                    "suggestion": "Update your formation.yaml to have 'agents:' as a list of agent configurations",
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
        except Exception as e:
            print(f"❌ Unexpected error retrieving secret '{name}': {e}")
            print("💡 Suggestion: Verify secrets manager is properly initialized")
            return None

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

    def start_overlord(self):
        """
        Start services and return configured overlord instance.

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
        """
        if not self.config:
            raise OverlordStateError(
                "no_config",
                "config_loaded",
                {"operation": "start_overlord", "formation_id": self.formation_id},
            )

        # Return existing overlord if already running (one formation = one overlord)
        if self._is_running and self._overlord is not None:
            print("⚠️  Warning: Overlord is already running. Returning existing instance.")
            print("   Use stop_overlord() first if you need to restart with new configuration.")
            return self._overlord

        try:
            # Import overlord when needed to avoid circular imports
            from .overlord.overlord import Overlord

            # Prepare services for handoff
            self._prepare_services()

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
                complexity_threshold=self.config.get("complexity_threshold", 7.0),
            )

            # Mark as running
            self._is_running = True

            # Register built-in MCP servers if enabled
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # Schedule the coroutine in the existing loop
                task = loop.create_task(self._register_builtin_mcps())
                # Store task reference to prevent garbage collection
                self._builtin_mcp_task = task
                # Wait for registration to complete to avoid race conditions
                # Use a timeout to prevent blocking indefinitely
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run_coroutine_threadsafe, task, loop)
                        future.result(timeout=30)  # 30 second timeout
                except Exception as e:
                    # Log error but don't fail startup
                    observability.observe(
                        event_type=observability.ErrorEvents.MCP_SERVER_REGISTRATION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(e)},
                        description=f"Built-in MCP registration task failed to complete: {e}"
                    )
            except RuntimeError:
                # No event loop running, create one
                asyncio.run(self._register_builtin_mcps())

            return self._overlord

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
                        "Validate your formation.yaml syntax",
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

    def stop_overlord(self, timeout_seconds: float = 30.0) -> None:
        """
        Gracefully stop overlord - finish conversations and cleanup.

        Allows the overlord to complete any ongoing conversations, save state,
        and perform graceful shutdown. Uses the ActiveAgentsTracker to wait for
        all agents to finish their current work before shutting down.

        Args:
            timeout_seconds: Maximum time to wait for graceful shutdown before forcing termination
        """
        if not self._is_running or not self._overlord:
            return  # Already stopped or never started

        try:
            # Use the new graceful shutdown functionality
            asyncio.run(self._overlord.active_agent_tracker.mark_overlord_for_shutdown())

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
                asyncio.run(wait_for_shutdown())
                print("✅ Overlord shutdown gracefully - all agents finished their work")
            except TimeoutError:
                print(
                    f"⚠️  Graceful shutdown timed out after {timeout_seconds}s - forcing termination"
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
            # Force immediate cleanup without waiting
            self._overlord = None
            self._is_running = False

        except Exception as e:
            print(f"❌ Error during immediate overlord termination: {e}")
            print("💡 Suggestion: Formation cleanup will continue despite this error")
            # Force cleanup regardless of errors
            self._overlord = None
            self._is_running = False

    def stop(self) -> None:
        """
        Stop formation infrastructure and cleanup resources.

        Performs final cleanup of formation-level resources including services,
        configurations, and connections. Call this after stopping the overlord
        to ensure complete cleanup.
        """
        try:
            # Cancel all active operations first
            if self._formation_cancellation_token:
                self._formation_cancellation_token.cancel()

            # Stop overlord if still running (gracefully)
            if self._is_running:
                self.stop_overlord()

            # Cleanup formation resources
            self.config = None
            self.secrets_manager = None
            self._configured_services.clear()
            self._api_keys.clear()

            # Clean up async operation management
            self._formation_cancellation_token = None

            # Clear individual service configurations
            self._llm_config.clear()
            self._memory_config.clear()
            self._mcp_config.clear()
            self._a2a_config.clear()
            self._logging_config.clear()
            self._clarification_config.clear()
            self._document_processing_config.clear()
            self._scheduler_config.clear()
            self._agents_config.clear()

        except Exception as e:
            print(f"❌ Error during formation cleanup: {e}")
            print("💡 Suggestion: Some resources may not have been properly cleaned up")

    @property
    def is_running(self) -> bool:
        """Check if overlord is currently running."""
        return self._is_running

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
                loaded_config = await formation_loader.load(schema, self.secrets_manager)

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

        else:
            raise TypeError(f"Schema must be dict or str, got {type(schema).__name__}")

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

    async def _register_builtin_mcps(self) -> None:
        """
        Register built-in MCP servers based on runtime configuration.

        This method checks the runtime configuration and registers any enabled
        built-in MCP servers with the overlord's MCP service.
        """
        if not self._overlord or not self._overlord.mcp_service:
            return

        # Get built-in MCP configuration
        builtin_mcps_config = self._runtime_config.get("built_in_mcps", True)

        # Import built-in MCP registry
        from ..services.mcp.built_in import list_builtin_mcps
        import sys

        # Get all available built-in MCPs
        available_mcps = list_builtin_mcps()

        # Determine which MCPs to register
        mcps_to_register = []

        if isinstance(builtin_mcps_config, bool):
            # Simple mode - all on or all off
            if builtin_mcps_config:
                mcps_to_register = list(available_mcps.keys())
        elif isinstance(builtin_mcps_config, list):
            # Granular mode - only specified MCPs
            mcps_to_register = [
                mcp_name for mcp_name in builtin_mcps_config if mcp_name in available_mcps
            ]

        # Register each enabled MCP
        for mcp_name in mcps_to_register:
            mcp_path = available_mcps[mcp_name]

            # Check if the script exists
            if not mcp_path.exists():
                observability.observe(
                    event_type=observability.ErrorEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "mcp_name": mcp_name,
                        "mcp_path": str(mcp_path),
                        "error": "Script file not found",
                    },
                    description=f"Built-in MCP script not found: {mcp_path}",
                )
                continue

            try:
                # Register the MCP server with properly escaped command
                await self._overlord.mcp_service.register_mcp_server(
                    server_id=f"builtin-{mcp_name}",
                    command=f"{shlex.quote(sys.executable)} {shlex.quote(str(mcp_path))}",
                    transport_type="command",
                    request_timeout=30,
                )

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={
                        "mcp_name": mcp_name,
                        "server_id": f"builtin-{mcp_name}",
                        "mcp_path": str(mcp_path),
                    },
                    description=f"Built-in MCP server registered: {mcp_name}",
                )

            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "mcp_name": mcp_name,
                        "server_id": f"builtin-{mcp_name}",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Failed to register built-in MCP server {mcp_name}: {e}",
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
                event_type=observability.ErrorEvents.MCP_SERVER_REGISTRATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"timeout": timeout},
                description=f"Built-in MCP registration timed out after {timeout} seconds"
            )
            return False
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.MCP_SERVER_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Built-in MCP registration failed: {e}"
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
