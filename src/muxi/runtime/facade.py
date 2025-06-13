# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Muxi - Simplified Framework Facade
# Description:  High-level interface for the Muxi Framework
# Role:         Entry point for declarative usage of the framework
# Usage:        Primary way to use Muxi with configuration files
# Author:       Muxi Framework Team
#
# The Muxi facade is the main entry point for using the framework in a
# declarative, configuration-driven way. It provides:
#
# 1. Simplified Initialization
#    - Creates memory systems from configuration
#    - Sets up overlord with memory integration
#    - Handles environment variable integration
#
# 2. Configuration-Based Agent Creation
#    - Creates agents from YAML/JSON configurations
#    - Connects MCP servers based on configuration
#    - Manages model creation and initialization
#
# 3. Easy Server Operation
#    - Provides methods to start the API server
#    - Handles authentication setup
#    - Configures multi-user support
#
# 4. Memory Management
#    - Creates appropriate memory systems based on configuration
#    - Supports various storage backends (SQLite, PostgreSQL)
#    - Enables context memory for user profiles
#
# This facade is typically used as the main entry point in applications:
#
#   from muxi import muxi
#
#   app = muxi(
#       buffer_size=10,
#       long_term="sqlite:///data/memory.db"
#   )
#
#   app.add_agent("assistant", "configs/assistant.yaml")
#   app.run(host="0.0.0.0", port=5050)
#
# This file contains the Muxi class implementation that provides the
# configuration-driven interface to the framework's components.
# =============================================================================

import os
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from .agent import Agent
from .overlord import Overlord
from .memory.short_term import ShortTermMemory
from .memory.long_term import LongTermMemory
from .memory.memobase import Memobase
from .memory.sqlite import SQLiteMemory
from .config.loader import ConfigLoader
from .llm import LLM


class Muxi:
    """
    Main facade for the MUXI Framework.

    This class provides a simplified interface for creating and managing agents,
    setting up MCP servers, and starting the API server with minimal code.
    It handles the complexity of initializing framework components based on
    declarative configuration.
    """

    def __init__(
        self,
        buffer_size: Optional[Union[int, ShortTermMemory]] = None,
        buffer_multiplier: int = 10,
        long_term_memory: Optional[Union[str, bool, LongTermMemory, Memobase]] = None,
        credential_db_connection_string: Optional[str] = None,
        user_api_key: Optional[str] = None,
        admin_api_key: Optional[str] = None,
    ):
        """
        Initialize the declarative interface for Muxi Framework.

        Creates memory systems and an overlord based on the provided configuration.
        This constructor handles the various ways memory can be specified, creating
        appropriate memory systems based on the input types.

        Args:
            buffer_size: Context window size configuration
                - If an integer, specifies the number of messages to keep in the window
                - If a ShortTermMemory instance, used directly
            buffer_multiplier: Multiplier for the buffer capacity (default: 10)
                - The actual buffer size will be buffer_size * buffer_multiplier
            long_term_memory: Long-term memory configuration
                - If a string, treated as a connection string or file path
                - If True, creates a default SQLite database in the current directory
                - If an instance of LongTermMemory or Memobase, used directly
            credential_db_connection_string: Connection string for the credential database
                (can also be set via MUXI_DB_CONNECTION_STRING environment variable)
            user_api_key: Optional API key for user-level access
            admin_api_key: Optional API key for admin-level access
        """
        # Store connection string for memory systems
        self._credential_db_connection_string = credential_db_connection_string

        # Create memory systems from configurations
        buffer_mem, long_term_mem = self._create_memory_systems(
            {
                "buffer_memory": buffer_size,
                "buffer_multiplier": buffer_multiplier,
                "long_term_memory": long_term_memory,
            }
        )

        # Create overlord with memory systems
        self.overlord = Overlord(
            buffer_memory=buffer_mem,
            long_term_memory=long_term_mem,
            user_api_key=user_api_key,
            admin_api_key=admin_api_key,
        )

        # Initialize config loader
        self.config_loader = ConfigLoader()

    def _create_buffer_memory(
        self,
        buffer_config: Optional[Union[int, Dict[str, Any], ShortTermMemory]],
        buffer_multiplier: int = 10,
    ) -> Optional[ShortTermMemory]:
        """
        Create a buffer memory object from configuration.

        This internal method handles various ways buffer memory can be specified
        and creates the appropriate ShortTermMemory instance. It supports direct
        instance passing, integer sizes, or dictionary configurations.

        Args:
            buffer_config: Buffer memory configuration. Can be:
                - An integer (context window size)
                - A dictionary with 'window_size' and optional 'buffer_multiplier'
                - A ShortTermMemory instance
                - None (no buffer memory)
            buffer_multiplier: Multiplier for the buffer capacity (default: 10)

        Returns:
            Configured ShortTermMemory instance or None if buffer_config is None.
        """
        if buffer_config is None:
            return None

        if isinstance(buffer_config, int):
            # Create buffer memory with specified size and multiplier
            return ShortTermMemory(max_size=buffer_config, buffer_multiplier=buffer_multiplier)

        if isinstance(buffer_config, dict):
            # Extract window_size and buffer_multiplier from dict
            window_size = buffer_config.get("window_size", 5)
            config_multiplier = buffer_config.get("buffer_multiplier", buffer_multiplier)

            # Create buffer with specified parameters
            return ShortTermMemory(max_size=window_size, buffer_multiplier=config_multiplier)

        # Assume it's already a ShortTermMemory instance
        return buffer_config

    def _create_long_term_memory(
        self,
        long_term_config: Optional[Union[str, bool, LongTermMemory, Memobase]],
        credential_db_connection_string: Optional[str] = None,
    ) -> Optional[Union[LongTermMemory, Memobase]]:
        """
        Create a long-term memory object from configuration.

        This internal method handles various ways long-term memory can be specified
        and creates the appropriate memory instance. It supports direct instance
        passing, connection strings, boolean flags, or paths to SQLite databases.

        Args:
            long_term_config: Long-term memory configuration. Can be:
                - A connection string (postgresql:// or sqlite://)
                - True (use default SQLite)
                - A LongTermMemory or Memobase instance
                - None (no long-term memory)
            credential_db_connection_string: Optional database connection string to use if
                long_term_config doesn't specify one.

        Returns:
            Configured memory instance or None if long_term_config is None or invalid.
        """
        if long_term_config is None:
            return None

        # If it's already a LongTermMemory or Memobase instance, use it directly
        if isinstance(long_term_config, (LongTermMemory, Memobase)):
            return long_term_config

        # Handle string connection specifications
        if isinstance(long_term_config, str):
            # Postgres connection string
            if long_term_config.startswith(("postgresql://", "postgres://")):
                try:
                    # Create long-term memory with database connection
                    memory = LongTermMemory(connection_string=long_term_config)

                    # Wrap with Memobase for multi-user support
                    memobase = Memobase(long_term_memory=memory)
                    logger.info("Created Postgres long-term memory with connection string")
                    return memobase
                except Exception as e:
                    # Log the error but continue without long-term memory
                    logger.error(f"Error creating Postgres long-term memory: {e}")
                    return None

            # SQLite connection string format (sqlite:///path/to/db)
            elif long_term_config.startswith("sqlite:///"):
                try:
                    # Extract the path: remove 'sqlite:///' prefix
                    db_path = long_term_config[10:]
                    memory = SQLiteMemory(db_path=db_path)
                    logger.info(f"Created SQLite long-term memory at {db_path}")
                    return memory
                except Exception as e:
                    # Log the error but continue without long-term memory
                    logger.error(f"Error creating SQLite long-term memory: {e}")
                    return None

            # Plain SQLite path
            else:
                try:
                    memory = SQLiteMemory(db_path=long_term_config)
                    logger.info(f"Created SQLite long-term memory at {long_term_config}")
                    return memory
                except Exception as e:
                    # Log the error but continue without long-term memory
                    logger.error(f"Error creating SQLite long-term memory: {e}")
                    return None

        # Boolean true - use connection string or default SQLite database
        elif long_term_config is True:
            # First try to use provided connection string
            conn_str = credential_db_connection_string or self.credential_db_connection_string
            if conn_str and (
                conn_str.startswith("postgresql://") or conn_str.startswith("postgres://")
            ):
                try:
                    # Create long-term memory with database connection
                    memory = LongTermMemory(connection_string=conn_str)

                    # Wrap with Memobase for multi-user support
                    memobase = Memobase(long_term_memory=memory)
                    logger.info("Created Postgres long-term memory with provided connection string")
                    return memobase
                except Exception as e:
                    # Log the error but fall back to SQLite
                    logger.error(
                        f"Error creating Postgres long-term memory, falling back to SQLite: {e}"
                    )

            # Fall back to SQLite
            try:
                db_path = os.path.join(os.getcwd(), "muxi.db")
                memory = SQLiteMemory(db_path=db_path)
                logger.info(f"Created default SQLite long-term memory at {db_path}")
                return memory
            except Exception as e:
                # Log the error but continue without long-term memory
                logger.error(f"Error creating default SQLite long-term memory: {e}")
                return None

        # If we get here, we don't know how to handle the configuration
        logger.warning(f"Unrecognized long-term memory configuration: {long_term_config}")
        return None

    @property
    def credential_db_connection_string(self) -> Optional[str]:
        """
        Get the credential database connection string.

        This property provides access to the credential database connection string,
        attempting to load it from encrypted secrets if it hasn't been explicitly
        provided during initialization.

        Returns:
            Optional[str]: Credential database connection string if available, None otherwise.
        """
        if self._credential_db_connection_string is None:
            # Try to load from encrypted secrets if not already set
            if (
                hasattr(self, 'config_loader')
                and self.config_loader
                and hasattr(self.config_loader, 'secrets_manager')
            ):
                try:
                    secrets_manager = self.config_loader.secrets_manager
                    self._credential_db_connection_string = secrets_manager.get_secret(
                        "POSTGRES_DATABASE_URL"
                    )
                except Exception:
                    # Fallback to None if secrets not available
                    pass

        return self._credential_db_connection_string

    def _get_connection_string(self, required: bool = True) -> Optional[str]:
        """
        Get the database connection string for operations that may require it.

        Args:
            required: Whether the connection string is required. If True and no
                connection string is available, raises an exception.

        Returns:
            Optional[str]: Database connection string if available.

        Raises:
            ValueError: If required is True and no connection string is available.
        """
        connection_string = self.credential_db_connection_string

        if required and not connection_string:
            raise ValueError(
                "Database connection string is required for this operation. "
                "Please provide it when initializing Muxi or set POSTGRES_DATABASE_URL "
                "in your environment."
            )

        return connection_string

    async def add_agent(self, name: str, path: str, env_file: Optional[str] = None) -> Agent:
        """
        Add an agent from a configuration file.

        This method loads an agent configuration from a file, creates the
        necessary components, and adds the agent to the overlord. It supports
        both YAML and JSON configuration formats.

        Args:
            name: Name for the agent. Will override any name in the config file.
            path: Path to the configuration file. Can be absolute or relative.
            env_file: Optional path to a .env file for environment variables
                needed by the configuration.

        Returns:
            The created agent instance.

        Raises:
            FileNotFoundError: If the configuration file doesn't exist.
            ValueError: If the configuration is invalid or components can't be created.
        """
        # Load environment file if provided
        if env_file:
            from dotenv import load_dotenv

            load_dotenv(env_file)

        # Load and process configuration
        config = self.config_loader.load_and_process(path)

        # Override name if provided
        if name:
            config["name"] = name
        else:
            # If name not provided, use name from config
            name = config.get("name", Path(path).stem)

        # Create the model (using the whole config to support both formats)
        model = self._create_model(config)

        # Extract description or use system message as fallback
        description = config.get("description", config.get("system_message", ""))

        # Create the agent
        agent = self.overlord.create_agent(
            agent_id=name,
            model=model,
            system_message=config.get("system_message", ""),
            description=description,
        )

        # If we have buffer memory and it doesn't have a model set,
        # set the model to enable vector search capabilities
        if (
            self.overlord.buffer_memory
            and hasattr(self.overlord.buffer_memory, "model")
            and self.overlord.buffer_memory.model is None
        ):
            self.overlord.buffer_memory.model = model
            logger.info(f"Enabled vector search in buffer memory using {model.model_name}")

        # Connect MCP servers if specified
        mcp_servers = config.get("mcp_servers", [])
        if mcp_servers:
            await self._connect_mcp_servers(agent, mcp_servers)

        return agent

    def _create_model(self, model_config: Dict[str, Any]) -> LLM:
        """
        Create a model from the configuration.

        This internal method creates a language model instance based on the
        provided configuration. Uses OneLLM to support multiple providers
        through a unified interface with "provider/model-name" format.

        Args:
            model_config: Model configuration dictionary containing the 'llm' section
                with model, API key, and other parameters.

        Returns:
            The model instance ready for use with agents.
        """
        if "llm" not in model_config:
            raise ValueError(
                "Model configuration must contain 'llm' section with 'model' parameter"
            )

        # Get configuration from llm section
        llm_config = model_config["llm"]
        model_name = llm_config.get("model")
        api_key = llm_config.get("api_key")
        temperature = llm_config.get("temperature", 0.7)
        max_tokens = llm_config.get("max_tokens")

        # Get any additional params
        kwargs = {k: v for k, v in llm_config.items()
                  if k not in ["model", "api_key", "temperature", "max_tokens"]}

        return self.overlord.create_model(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    def _create_memory_systems(self, memory_config: Dict[str, Any]) -> tuple:
        """
        Create memory systems from the configuration.

        This internal method handles the creation of both buffer memory and
        long-term memory systems based on the provided configuration.

        Args:
            memory_config: Memory configuration dictionary with keys for
                buffer_memory, buffer_multiplier, and long_term_memory.

        Returns:
            tuple: (buffer_memory, long_term_memory) - instances of the
                appropriate memory systems or None if not configured.
        """
        # Create buffer memory
        buffer_config = memory_config.get("buffer_memory")
        buffer_multiplier = memory_config.get("buffer_multiplier", 10)
        buffer_memory = self._create_buffer_memory(
            buffer_config=buffer_config, buffer_multiplier=buffer_multiplier
        )

        # Create long-term memory if enabled
        long_term_config = memory_config.get("long_term_memory")
        long_term_memory = self._create_long_term_memory(
            long_term_config, self.credential_db_connection_string
        )

        return buffer_memory, long_term_memory

    async def _connect_mcp_servers(self, agent: Agent, mcp_servers: List[Dict[str, Any]]) -> None:
        """
        Connect MCP servers to an agent.

        This internal method processes MCP server configurations and connects them
        to the specified agent, handling credential resolution from encrypted secrets
        instead of environment variables.

        Args:
            agent: The agent to connect MCP servers to.
            mcp_servers: List of MCP server configurations, each containing name,
                URL, and optional credential information.
        """
        for server in mcp_servers:
            name = server.get("name")
            url = server.get("url")
            # Support both 'auth' (new) and 'credentials' (legacy) fields
            credentials = server.get("auth", []) or server.get("credentials", [])

            if name and url:
                # Process credentials
                processed_credentials = {}
                for cred in credentials:
                    cred_id = cred.get("id")
                    param_name = cred.get("param_name")
                    required = cred.get("required", False)

                    # Check for encrypted secrets first, then env_fallback as last resort
                    value = None

                    # Try encrypted secrets if available
                    if (
                        hasattr(self, 'config_loader')
                        and self.config_loader
                        and hasattr(self.config_loader, 'secrets_manager')
                    ):
                        try:
                            # Convert to standard secret name format
                            secret_name = cred_id.upper() if cred_id else None
                            if secret_name:
                                value = self.config_loader.secrets_manager.get_secret(secret_name)
                        except Exception:
                            # Continue to fallback if secrets not available
                            pass

                    # Check for env_fallback as last resort (for backward compatibility)
                    if not value:
                        env_var = cred.get("env_fallback")
                        if env_var:
                            import os
                            value = os.getenv(env_var)

                    if value:
                        processed_credentials[param_name] = value
                        continue

                    # Missing required credential
                    if required:
                        logger.warning(
                            f"Required credential {cred_id} for MCP server " f"{name} not found"
                        )
                        continue

                # Connect to the MCP server
                try:
                    # Assuming agent has a method to connect to MCP server
                    # Replace with actual method if different
                    if hasattr(agent, "connect_mcp_server"):
                        await agent.connect_mcp_server(name, url, processed_credentials)
                        logger.info(f"Connected to MCP server: {name}")
                    else:
                        logger.warning(
                            f"Agent {agent.name} does not have connect_mcp_server method."
                        )

                except Exception as e:
                    logger.error(f"Error connecting to MCP server {name}: {e}")
            else:
                logger.warning(f"Invalid MCP server configuration: {server}")

    async def chat(
        self,
        message: str,
        agent_name: Optional[str] = None,
        user_id: Optional[str] = None,
        use_async: Optional[bool] = None,
        webhook_url: Optional[str] = None,
        threshold_seconds: Optional[float] = None
    ) -> Union[str, Dict[str, Any]]:
        """
        Send a message to an agent and get a response.

        This is the primary method for interacting with agents through the facade.
        It handles message routing, processing, and response extraction, with full
        support for async request-response patterns for long-running tasks.

        Args:
            message: The message to send to the agent.
            agent_name: Optional name of the agent to use. If None, the overlord
                will select the most appropriate agent for the message.
            user_id: Optional user ID for multi-user support. Enables user-specific
                memory and context.
            use_async: Optional async mode control:
                - None (default): Intelligent async decision based on time estimation
                - True: Force async processing with immediate request_id return
                - False: Force synchronous processing
            webhook_url: Optional webhook URL for async completion notifications.
                Overrides formation-level default webhook URL.
            threshold_seconds: Optional threshold override for async decision making.
                Overrides formation-level default threshold.

        Returns:
            For sync responses: The agent's response as a string.
            For async responses: Dict with request_id and status information.
        """
        # Emit facade request received event
        try:
            from .observability import EventType, EventLevel, ObservabilityManager
            observability_manager = ObservabilityManager.get_instance()
            if observability_manager:
                await observability_manager.event_logger.emit_event(
                    EventType.REQUEST_RECEIVED,
                    level=EventLevel.INFO,
                    data={
                        "message_length": len(message),
                        "agent_name": agent_name,
                        "user_id": user_id,
                        "use_async": use_async,
                        "has_webhook_url": webhook_url is not None,
                        "threshold_seconds": threshold_seconds,
                    },
                    description=f"Facade chat request received for agent: {agent_name or 'auto'}",
                )
        except Exception:
            pass  # Don't let observability errors break the flow

        # Process the message through the overlord with all parameters
        response = await self.overlord.chat(
            message=message,
            agent_name=agent_name,
            user_id=user_id,
            use_async=use_async,
            webhook_url=webhook_url,
            threshold_seconds=threshold_seconds
        )

        # Emit facade response completion event
        try:
            if observability_manager:
                is_async_response = isinstance(response, dict) and "request_id" in response
                await observability_manager.event_logger.emit_event(
                    EventType.REQUEST_COMPLETED,
                    level=EventLevel.INFO,
                    data={
                        "is_async_response": is_async_response,
                        "response_type": type(response).__name__,
                        "response_length": len(str(response)),
                        "agent_name": agent_name,
                        "user_id": user_id,
                    },
                    description=f"Facade chat response completed (async: {is_async_response})",
                )
        except Exception:
            pass  # Don't let observability errors break the flow

        # Handle async response (dict with request_id)
        if isinstance(response, dict) and "request_id" in response:
            return response

        # Handle sync response (MCPMessage)
        if hasattr(response, 'content'):
            if isinstance(response.content, str):
                return response.content
            elif isinstance(response.content, dict) and "text" in response.content:
                return response.content["text"]
            else:
                # Fallback to string representation
                return str(response.content)

        # Fallback for unexpected response format
        return str(response)

    def add_user_context_memory(self, user_id: int, knowledge: Dict[str, Any]) -> None:
        """
        Add context memory for a specific user.

        This method stores structured information about a user that can be used
        to personalize agent responses. Requires a multi-user memory system.

        Args:
            user_id: User ID to associate the knowledge with. Used to identify
                the specific user in multi-user environments.
            knowledge: Knowledge to add (any serializable dictionary). Typically
                contains user preferences, facts, and other contextual information.

        Raises:
            ValueError: If overlord doesn't have multi-user memory support.
        """
        # Use overlord's long-term memory if it's multi-user
        if hasattr(self.overlord, "is_multi_user") and self.overlord.is_multi_user:
            if hasattr(self.overlord.long_term_memory, "add_user_context_memory"):
                # Assuming add_context_memory is async now based on Memobase
                asyncio.create_task(
                    self.overlord.long_term_memory.add_user_context_memory(user_id, knowledge)
                )
                return

        # Fallback removed as it's less likely to be correct with current structure

        raise ValueError(
            "No suitable long-term memory found for user context. Make sure Muxi is "
            "initialized with a Memobase-compatible memory (PostgreSQL connection)."
        )

    def start_server(self, host: str = "0.0.0.0", port: int = 5000, **kwargs) -> None:
        """
        Start the API server.

        This method starts the MUXI API server with the specified host and port.
        It delegates to the run_server function from src.muxi.runtime.run.

        Args:
            host: Host address to bind to. Default "0.0.0.0" binds to all interfaces.
            port: Port number to bind to.
            **kwargs: Additional arguments to pass to the API server.
        """
        # Import here to avoid circular imports
        from .run import run_server

        # Start the server
        run_server(host=host, port=port, **kwargs)

    def run(self, **kwargs) -> None:
        """
        Start the MUXI server with the current configuration.

        This method is a convenient shorthand for starting the server through
        the overlord, which handles displaying a splash screen and API keys.

        Args:
            **kwargs: Additional arguments to pass to the server
                - host: Host to bind the server to (default: "0.0.0.0")
                - port: Port to bind the server to (default: 5050)
                - reload: Whether to enable auto-reload for development (default: True)
                - mcp: Whether to enable MCP functionality (default: False)
        """
        # Start the server using the overlord's run method
        self.overlord.run(**kwargs)

    def get_agent(self, agent_id: str) -> Agent:
        """
        Get an agent by ID.

        This method retrieves a specific agent from the overlord.

        Args:
            agent_id: The ID of the agent to get.

        Returns:
            The requested agent instance.

        Raises:
            ValueError: If no agent with the given ID exists.
        """
        return self.overlord.get_agent(agent_id)
