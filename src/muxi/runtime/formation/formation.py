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
#   formation.stop_overlord()  # Graceful shutdown
#   formation.stop()           # Full cleanup
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

    def __init__(self):
        """
        Initialize Formation platform.

        Sets up the operational foundation for the Muxi runtime without
        loading any specific configuration. Call load() to load a formation
        configuration and start_overlord() to boot the intelligence layer.
        """
        # Core state
        self.config: Optional[Dict[str, Any]] = None
        self.overlord = None

        # Operational services
        self.formation_id: str = "default-formation"
        self._is_running: bool = False

        # Service management
        self.secrets_manager: Optional[SecretsManager] = None
        self._formation_path: Optional[str] = None

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
            config_path: Path to formation YAML file or directory

        Raises:
            ValueError: If configuration is invalid or cannot be loaded
            FileNotFoundError: If configuration file/directory does not exist
        """
        if self._is_running:
            raise RuntimeError("Cannot load configuration while overlord is running. Stop first.")

        try:
            # Emit formation loading started event
            observability.observe(
                event_type=observability.SystemEvents.OVERLORD_INITIALIZING,
                level=observability.EventLevel.INFO,
                data={"formation_path": config_path},
                description=f"Starting formation loading from {config_path}",
            )

            # Store formation path for secrets management
            self._formation_path = config_path

            # Initialize secrets manager
            self.secrets_manager = SecretsManager(config_path)

            # Validate configuration
            validation_result = self._validate_config(config_path)
            if not validation_result["is_valid"]:
                error_msg = f"Formation validation failed:\n{validation_result['detailed_report']}"
                raise ValueError(error_msg)

            # Log warnings if any
            if validation_result["warnings"]:
                error_msg = f"Formation validation warnings:\n{validation_result['detailed_report']}"
                raise ValueError(error_msg)

            # Load configuration
            self.config = asyncio.run(self._load_config(config_path))

            # Set formation ID
            self.formation_id = self.config.get("formation_id", "default-formation")
            set_formation_id(self.formation_id)

            # Prepare services (but don't start them yet)
            self._prepare_services()

        except Exception:
            # Clean up on failure
            self.config = None
            self.secrets_manager = None
            raise

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
        Load formation configuration from file.

        Args:
            config_path: Path to formation configuration

        Returns:
            Loaded configuration dictionary
        """
        formation_loader = FormationLoader()
        return await formation_loader.load(config_path, self.secrets_manager)

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
            raise ValueError("LLM configuration must be a dictionary")

    def _setup_memory_config(self) -> None:
        """Setup and validate memory configuration."""
        self._memory_config = self.config.get("memory", {})

        # Validate memory configuration structure
        if not isinstance(self._memory_config, dict):
            raise ValueError("Memory configuration must be a dictionary")

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
            raise ValueError("Agents configuration must be a list")

        # Validate each agent configuration
        for i, agent_config in enumerate(self._agents_config):
            if not isinstance(agent_config, dict):
                raise ValueError(f"Agent {i} configuration must be a dictionary")
            if not agent_config.get("id"):
                raise ValueError(f"Agent {i} must have an 'id' field")

    async def ensure_secrets_manager(self) -> bool:
        """
        Ensure the SecretsManager is initialized and ready to use.

        Returns:
            bool: True if SecretsManager is available, False otherwise
        """
        if not self.secrets_manager:
            return False

        try:
            await self.secrets_manager.initialize_encryption()
            return True
        except Exception as e:
            print(f"Warning: Failed to initialize secrets manager: {e}")
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
        except Exception as e:
            print(f"Warning: Failed to store secret '{name}': {e}")
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
        except Exception as e:
            print(f"Warning: Failed to get secret '{name}': {e}")
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
        except Exception as e:
            print(f"Warning: Failed to list secrets: {e}")
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
        except Exception as e:
            print(f"Warning: Failed to delete secret '{name}': {e}")
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
            print(f"Warning: Failed to interpolate secrets: {e}")
            return config

    def start_overlord(self):
        """
        Start services and return configured overlord instance.

        Initializes all services based on the loaded configuration and creates
        a fully configured overlord instance. The overlord receives pre-configured
        services and is ready for intelligent operations.

        Returns:
            Configured Overlord instance ready for intelligent operations

        Raises:
            RuntimeError: If no configuration loaded or overlord already running
        """
        # TODO: Phase 3 - Implement service handoff to overlord
        raise NotImplementedError("Overlord startup will be implemented in Phase 3")

    def stop_overlord(self) -> None:
        """
        Gracefully stop overlord - finish conversations and cleanup.

        Allows the overlord to complete any ongoing conversations, save state,
        and perform graceful shutdown. This is the preferred method for stopping
        the overlord in production environments.
        """
        # TODO: Phase 3 - Implement graceful overlord shutdown
        raise NotImplementedError("Graceful shutdown will be implemented in Phase 3")

    def kill_overlord(self) -> None:
        """
        Immediately terminate overlord - stop NOW regardless of state.

        Forces immediate termination of the overlord without waiting for
        conversations to complete or state to be saved. Use for emergency
        situations or when graceful shutdown fails.
        """
        # TODO: Phase 3 - Implement immediate overlord termination
        raise NotImplementedError("Immediate termination will be implemented in Phase 3")

    def stop(self) -> None:
        """
        Stop formation infrastructure and cleanup resources.

        Performs final cleanup of formation-level resources including services,
        configurations, and connections. Call this after stopping the overlord
        to ensure complete cleanup.
        """
        try:
            # Stop overlord if still running (gracefully)
            if self._is_running:
                self.stop_overlord()

            # Cleanup formation resources
            self.config = None
            self.secrets_manager = None
            self._configured_services.clear()
            self._api_keys.clear()

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
            print(f"Warning: Error during formation cleanup: {e}")

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
