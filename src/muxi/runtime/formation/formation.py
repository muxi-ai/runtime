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
from typing import Any, Dict, List, Optional

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

    def __init__(self, timeout_config: Optional[TimeoutConfig] = None):
        """
        Initialize Formation platform.

        Sets up the operational foundation for the Muxi runtime without
        loading any specific configuration. Call load() to load a formation
        configuration and start_overlord() to boot the intelligence layer.

        Args:
            timeout_config: Optional timeout configuration for async operations
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

            raise ConfigurationNotFoundError(config_path, {
                "operation": "find_formation_config",
                "directory_checked": config_path,
                "suggestion": (
                    f"Create a formation.yaml file in the directory '{config_path}' or "
                    "provide the direct path to your formation configuration file"
                ),
                "example": f"Try: formation.load('{config_path}/formation.yaml') or create the missing file"
            })

        raise ConfigurationValidationError(
            [f"Config path must be a file or directory, got: {type(config_path).__name__}"],
            {
                "config_path": config_path,
                "operation": "validate_config_path",
                "suggestion": "Provide either a path to a formation.yaml file or a directory containing formation.yaml",
                "examples": [
                    "formation.load('path/to/formation.yaml')",
                    "formation.load('path/to/formation/directory')"
                ]
            }
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
        Load formation configuration from file with timeout support.

        Args:
            config_path: Path to formation configuration

        Returns:
            Loaded configuration dictionary

        Raises:
            TimeoutError: If configuration loading times out
            CancellationError: If operation is cancelled
        """
        async def _load_operation():
            formation_loader = FormationLoader()
            return await formation_loader.load(config_path, self.secrets_manager)

        result = await execute_with_timeout(
            _load_operation,
            operation_type="config_load",
            description=f"Loading formation configuration from {config_path}",
            timeout=self._timeout_config.config_load_timeout,
            cancellation_token=self._formation_cancellation_token
        )

        if not result.is_success:
            if result.was_timeout:
                raise ConfigurationLoadError(
                    f"❌ Configuration loading timed out after {result.elapsed_time:.1f}s",
                    {
                        "config_path": config_path,
                        "timeout": self._timeout_config.config_load_timeout,
                        "suggestion": "Try increasing config_load_timeout or check file system performance",
                        "next_steps": [
                            f"Increase timeout: Formation(timeout_config=TimeoutConfig("
                            f"config_load_timeout={self._timeout_config.config_load_timeout * 2}))",
                            "Check if the configuration file is accessible",
                            "Verify network connectivity if loading from remote location"
                        ]
                    }
                )
            elif result.was_cancelled:
                raise ConfigurationLoadError(
                    "❌ Configuration loading was cancelled",
                    {
                        "config_path": config_path,
                        "suggestion": "Operation was cancelled - check if Formation is being shut down"
                    }
                )
            else:
                # Re-raise the original error
                raise result.error

        return result.result

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
        self._setup_agents_config()

        # Create comprehensive service bundle for overlord handoff
        self._configured_services = {
            "formation_config": self.config,
            "secrets_manager": self.secrets_manager,
            "formation_path": self._formation_path,
            "api_keys": self._api_keys.copy(),
            # Service-specific configurations (validated and preprocessed)
            "llm_config": self._llm_config,
            "memory_config": self._memory_config,
            "mcp_config": self._mcp_config,
            "a2a_config": self._a2a_config,
            "logging_config": self._logging_config,
            "clarification_config": self._clarification_config,
            "document_processing_config": self._document_processing_config,
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
                            "models": [{"name": "gpt-4"}]
                        }
                    }
                }
            )

        # Validate required LLM fields
        if not self._llm_config:
            raise ConfigurationValidationError(
                ["LLM configuration cannot be empty - at least one LLM provider must be configured"],
                {
                    "suggestion": "Add LLM configuration to your formation.yaml",
                    "required_sections": ["api_keys", "models"],
                    "example": {
                        "llm": {
                            "api_keys": {
                                "openai": "sk-your-openai-key",
                                "anthropic": "sk-ant-your-anthropic-key"
                            },
                            "models": [
                                {"name": "gpt-4", "provider": "openai"},
                                {"name": "claude-3-sonnet", "provider": "anthropic"}
                            ]
                        }
                    }
                }
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
                                "anthropic": "sk-ant-your-anthropic-key"
                            }
                        }
                    }
                )

            # Validate that at least one API key is provided
            if not api_keys:
                raise ConfigurationValidationError(
                    ["LLM 'api_keys' section cannot be empty - at least one provider API key required"],
                    {
                        "suggestion": "Add at least one API key for an LLM provider",
                        "supported_providers": ["openai", "anthropic", "azure", "cohere"],
                        "example": {
                            "api_keys": {
                                "openai": "sk-your-openai-key"
                            }
                        },
                        "how_to_get_keys": {
                            "openai": "Get your API key from https://platform.openai.com/api-keys",
                            "anthropic": "Get your API key from https://console.anthropic.com/"
                        }
                    }
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
                    "example": {
                        "memory": {
                            "type": "local",
                            "path": "./memory"
                        }
                    }
                }
            )

        # Validate memory type and required fields
        if self._memory_config:
            memory_type = self._memory_config.get("type")
            if memory_type and memory_type not in ["local", "memobase", "sqlite"]:
                raise ConfigurationValidationError(
                    [f"Unsupported memory type '{memory_type}'. Supported types: local, memobase, sqlite"],
                    {
                        "current_type": memory_type,
                        "supported_types": ["local", "memobase", "sqlite"],
                        "suggestion": "Choose a supported memory type",
                        "examples": {
                            "local": {"type": "local", "path": "./memory"},
                            "sqlite": {"type": "sqlite", "database": "memory.db"},
                            "memobase": {"type": "memobase", "connection_string": "postgresql://..."}
                        }
                    }
                )

            # Validate memobase-specific configuration
            if memory_type == "memobase":
                if "connection_string" not in self._memory_config:
                    raise ConfigurationValidationError(
                        ["Memobase memory configuration missing required 'connection_string' field"],
                        {
                            "memory_type": "memobase",
                            "missing_field": "connection_string",
                            "suggestion": "Add a PostgreSQL connection string for Memobase",
                            "example": {
                                "memory": {
                                    "type": "memobase",
                                    "connection_string": "postgresql://user:password@localhost:5432/memobase"
                                }
                            },
                            "setup_help": "Install PostgreSQL and create a database for Memobase storage"
                        }
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
                                "description": "General purpose assistant"
                            }
                        ]
                    }
                }
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
                            "description": "Agent description"
                        }
                    }
                )

            if not agent_config.get("id"):
                raise ConfigurationValidationError(
                    [f"Agent {i} must have an 'id' field"],
                    {
                        "agent_position": i,
                        "missing_field": "id",
                        "suggestion": "Add a unique 'id' field to identify the agent",
                        "example": {"id": "my-agent", "name": "My Agent"}
                    }
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
                        "examples": ["assistant", "code-reviewer", "data_analyst"]
                    }
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
                        )
                    }
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
                        "example": {"id": agent_id, "name": "My Assistant Agent"}
                    }
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
                            "specialist": "Domain-specific expert agent"
                        }
                    }
                )

    async def ensure_secrets_manager(self) -> bool:
        """
        Ensure the SecretsManager is initialized and ready to use with timeout support.

        Returns:
            bool: True if SecretsManager is available, False otherwise
        """
        if not self.secrets_manager:
            return False

        async def _initialize_operation():
            await self.secrets_manager.initialize_encryption()
            return True

        try:
            result = await execute_with_timeout(
                _initialize_operation,
                operation_type="secrets_operation",
                description="Initializing secrets manager encryption",
                timeout=self._timeout_config.secrets_operation_timeout,
                cancellation_token=self._formation_cancellation_token
            )

            if result.is_success:
                return result.result
            else:
                if result.was_timeout:
                    print(f"❌ Secrets manager initialization timed out after {result.elapsed_time:.1f}s")
                    print("💡 Suggestion: Increase secrets_operation_timeout or check system performance")
                elif result.was_cancelled:
                    print("❌ Secrets manager initialization was cancelled")
                else:
                    print(f"❌ Failed to initialize secrets manager: {result.error}")
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
            print("💡 Suggestion: Check your secret references use format: ${{ secrets.SECRET_NAME }}")
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
                        "Try reinstalling the formation package"
                    ]
                }
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
                        f"Review configuration at: {self._formation_path}"
                    ]
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
                        "Consider restarting the formation process"
                    ]
                },
            ) from e

    def stop_overlord(self) -> None:
        """
        Gracefully stop overlord - finish conversations and cleanup.

        Allows the overlord to complete any ongoing conversations, save state,
        and perform graceful shutdown. This is the preferred method for stopping
        the overlord in production environments.
        """
        if not self._is_running or not self._overlord:
            return  # Already stopped or never started

        try:
            # TODO: Implement graceful shutdown when overlord has cleanup methods
            # For now, we'll just clean up the references
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
