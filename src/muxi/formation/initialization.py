"""
Formation initialization utilities.

This module contains all the initialization logic for the Formation class,
handling all infrastructure and service setup. This ensures proper separation
of concerns where Formation handles operations and Overlord handles intelligence.

The initialization order is critical:
1. Observability MUST be initialized first
2. Then other services can be initialized
"""

from typing import Any, Dict, Optional

from ..datatypes.clarification import ClarificationConfig, QuestionStyle
from ..datatypes.exceptions import ConfigurationValidationError
from ..datatypes.memory import BufferMemoryConfig, WorkingMemoryConfig
from ..datatypes.observability import EventLevel
from ..services import observability
from ..services.memory.working import WorkingMemory
from ..services.observability.context import set_event_logger
from ..services.observability.logger import EventLogger
from .config.document_processing import DocumentProcessingConfig
from .documents.storage.chunk_manager import DocumentChunkManager


def _resolve_embedding_model_name(explicit_model: str = None, formation: Any = None) -> str:
    """
    Resolve the embedding model name from configuration.

    Args:
        explicit_model: Explicitly configured embedding model name
        formation: Formation instance to check for capability models

    Returns:
        The resolved embedding model name or None if not configured
    """
    # First check if an explicit model is provided
    if explicit_model:
        return explicit_model

    # Otherwise, check formation capability models
    if formation and hasattr(formation, "_capability_models"):
        embedding_config = formation._capability_models.get("embedding", {})
        return embedding_config.get("model")

    return None


def initialize_observability(formation) -> None:
    """
    Initialize observability/logging configuration FIRST.

    This MUST be the first initialization to ensure all subsequent
    events go to the configured destination instead of stdout.
    """
    # Use the pre-configured logging config
    logging_config = formation._logging_config if hasattr(formation, "_logging_config") else {}

    # Determine event logger configuration
    event_logger = None

    # Only create custom logger if logging is enabled and has file output
    if logging_config.get("enabled", True):
        streams = logging_config.get("streams", [])

        # Find file stream configuration
        for stream in streams:
            if stream.get("transport") == "file" and stream.get("destination"):
                # Parse level
                level_str = stream.get("level", "info").lower()
                valid_levels = [level.value for level in EventLevel]
                level = EventLevel(level_str) if level_str in valid_levels else EventLevel.INFO

                # Create EventLogger with file output
                event_logger = EventLogger(
                    level=level,
                    output="file",
                    output_config={"path": stream.get("destination")},
                    events=(stream.get("events", ["*"]) if stream.get("events") != ["*"] else None),
                )

                break

    # Create ObservabilityManager with appropriate configuration
    if event_logger:
        # Use custom event logger
        formation._observability_manager = observability.ObservabilityManager(
            {"enabled": True, "event_logger": event_logger}
        )
        # CRITICAL: Set the logger in context so observe() uses it
        set_event_logger(event_logger)

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "observability",
                "output": "file",
                "path": event_logger.output_config.get("path"),
            },
            description=f"Observability initialized with file output: {event_logger.output_config.get('path')}",
        )
    else:
        # Use default stdout logger
        formation._observability_manager = observability.ObservabilityManager({})


def initialize_llm_config(formation) -> None:
    """
    Initialize LLM configuration from formation config.

    This processes the capability-based LLM schema and sets up model
    resolution for different capabilities like text, vision, transcription, etc.

    Requirements:
    - The 'text' capability MUST be configured (no fallback)
    - Other capabilities default to the text model if not configured

    Raises:
        ConfigurationValidationError: If the 'text' capability is not configured
    """
    llm_config = formation._llm_config if hasattr(formation, "_llm_config") else {}

    # Initialize model cache for capability-based resolution
    formation._model_cache = {}
    formation._capability_models = {}

    # Process models by capability
    models_config = llm_config.get("models", [])
    for model_config in models_config:
        for capability, model_name in model_config.items():
            if capability in ["api_key", "settings"]:
                continue  # Skip metadata

            formation._capability_models[capability] = {
                "model": model_name,
                "api_key": model_config.get("api_key"),
                "settings": model_config.get("settings", {}),
            }

    # Store global settings and api_keys for later use
    formation._global_llm_settings = llm_config.get("settings", {})
    formation._global_api_keys = llm_config.get("api_keys", {})

    # CRITICAL: Ensure text model is configured
    if "text" not in formation._capability_models:
        raise ConfigurationValidationError(
            ["Missing required LLM capability 'text' in formation.llm.models"],
            details={
                "required_capability": "text",
                "configured_capabilities": list(formation._capability_models.keys()),
                "help": "You must configure at least: llm.models[0].text = 'provider/model-name'",
            },
        )

    # Get text model configuration for fallback
    text_model_config = formation._capability_models["text"]

    # Define common capabilities that should default to text model if not configured
    common_capabilities = ["vision", "audio", "documents", "embedding"]
    capabilities_using_text_fallback = []

    # Apply text model as default for unconfigured common capabilities
    for capability in common_capabilities:
        if capability not in formation._capability_models:
            formation._capability_models[capability] = {
                "model": text_model_config["model"],
                "api_key": text_model_config.get("api_key"),
                "settings": text_model_config.get("settings", {}),
            }
            capabilities_using_text_fallback.append(capability)

    capabilities = list(formation._capability_models.keys())

    # Log initialization with details about fallbacks
    log_data = {
        "service": "llm",
        "capabilities": capabilities,
        "capability_count": len(capabilities),
        "text_model": text_model_config["model"],
    }

    if capabilities_using_text_fallback:
        log_data["capabilities_using_text_fallback"] = capabilities_using_text_fallback
        description = (
            f"LLM configuration initialized with {len(capabilities)} capabilities. "
            f"Using text model '{text_model_config['model']}' as fallback for: "
            f"{', '.join(capabilities_using_text_fallback)}"
        )
    else:
        description = f"LLM configuration initialized with {len(capabilities)} capabilities"

    observability.observe(
        event_type=observability.SystemEvents.INITIALIZING,
        level=observability.EventLevel.INFO,
        data=log_data,
        description=description,
    )


def initialize_memory_systems(formation) -> None:
    """
    Initialize all memory systems including buffer, working, and persistent memory.
    """
    memory_config = formation._memory_config if hasattr(formation, "_memory_config") else {}

    # Initialize working memory configuration
    working_config = memory_config.get("working", {})
    _initialize_working_memory(formation, working_config)

    # Initialize buffer memory
    buffer_config = memory_config.get("buffer", {})
    _initialize_buffer_memory(formation, buffer_config)

    # Initialize persistent memory if configured
    persistent_config = memory_config.get("persistent", {})
    if persistent_config and persistent_config.get("connection_string"):
        _initialize_persistent_memory(formation, persistent_config)


def _initialize_working_memory(formation, working_config: Dict[str, Any]) -> None:
    """Initialize working memory configuration with defaults."""
    try:
        # Create WorkingMemoryConfig with provided config
        config = WorkingMemoryConfig(**working_config)

        # Store the working memory configuration
        formation._working_memory_config = config

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "working_memory",
                "mode": config.mode,
                "max_memory_mb": str(config.max_memory_mb),
                "vector_dimension": config.vector_dimension,
            },
            description=f"Working memory configured in {config.mode} mode",
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "working_memory"},
            description=f"Failed to initialize working memory: {str(e)}",
        )
        raise


def _initialize_buffer_memory(formation, buffer_config: Dict[str, Any]) -> None:
    """Initialize buffer memory from configuration with defaults."""
    try:
        # Create BufferMemoryConfig with provided config
        config = BufferMemoryConfig(**buffer_config)

        # Extract configuration values
        size = config.size
        multiplier = config.multiplier
        vector_search = config.vector_search
        dimension = config.vector_dimension
        mode = config.mode
        remote_config = config.remote

        # Get embedding model for vector search if enabled
        embedding_model = None
        if vector_search:
            embedding_model_name = _resolve_embedding_model_name(formation=formation)
            if embedding_model_name:
                # Pass the model name to WorkingMemory
                # It will create the LLM instance lazily when needed
                embedding_model = embedding_model_name
            else:
                # Disable vector search if no embedding model configured
                vector_search = False

        # Get formation_id from formation instance
        formation_id = getattr(formation, "formation_id", "default-formation")

        # Create buffer memory instance
        formation._buffer_memory = WorkingMemory(
            formation_id=formation_id,
            max_size=size,
            buffer_multiplier=multiplier,
            dimension=dimension,
            model=embedding_model,
            mode=mode,
            remote=remote_config.model_dump() if remote_config and mode == "remote" else None,
        )

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "buffer_memory",
                "size": size,
                "multiplier": multiplier,
                "vector_search": vector_search,
                "mode": mode,
            },
            description=f"Buffer memory initialized with size {size}",
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "buffer_memory"},
            description=f"Failed to initialize buffer memory: {str(e)}",
        )
        raise


def _initialize_persistent_memory(formation, persistent_config: Dict[str, Any]) -> None:
    """
    Initializes the persistent memory system for the formation based on the provided configuration.

    Determines the memory backend (PostgreSQL, SQLite, or Memobase) from the
    connection string, checks for uninterpolated secrets, and passes the
    formation ID and embedding model name to the memory constructor.
    Stores the resulting memory instance and database manager (if available)
    on the formation. Emits observability events for both success and failure.
    Persistent memory initialization errors are logged but do not interrupt execution.
    """
    try:
        connection_string = persistent_config.get("connection_string")
        formation_id = getattr(formation, "formation_id", "default-formation")

        # Check if connection string still contains uninterpolated secrets
        # This should not happen as secrets are interpolated during formation loading
        if "${{ secrets." in connection_string:
            raise ValueError(
                f"Connection string contains uninterpolated secrets: {connection_string}. "
                "Secrets should be interpolated during formation loading."
            )

        # Get embedding model configuration
        embedding_model_name = _resolve_embedding_model_name(
            explicit_model=persistent_config.get("embedding_model"), formation=formation
        )

        # For now, we'll pass the model name and let the memory systems handle model creation
        # This avoids the async initialization issue

        # Determine the type of persistent memory based on connection string
        if connection_string.startswith("postgresql://"):
            # PostgreSQL memory
            from ..services.memory.long_term import LongTermMemory
            from ..services.db import get_database_manager

            # Create database manager
            db_manager = get_database_manager(connection_string)
            formation._db_manager = db_manager

            formation._long_term_memory = LongTermMemory(
                db_manager=db_manager,
                formation_id=formation_id,
                embedding_model=embedding_model_name,
            )
            formation._is_multi_user = True
            memory_type = "PostgreSQL"

        elif connection_string.endswith(".db") or "sqlite" in connection_string:
            # SQLite memory with database manager for credentials
            from ..services.memory.sqlite import SQLiteMemory
            from ..services.db import get_database_manager

            # Create database manager for SQLite (needed for credentials table)
            # Check if connection string already has sqlite:// prefix
            if connection_string.startswith("sqlite://"):
                db_connection_string = connection_string
            else:
                db_connection_string = f"sqlite:///{connection_string}"

            db_manager = get_database_manager(db_connection_string)
            formation._db_manager = db_manager

            formation._long_term_memory = SQLiteMemory(
                db_path=connection_string,
                formation_id=formation_id,
                embedding_model=embedding_model_name,
            )
            formation._is_multi_user = False  # SQLite is single-user mode
            memory_type = "SQLite"

        else:
            # Default to Memobase
            from ..services.memory.memobase import Memobase
            from ..services.db import get_database_manager

            # Create database manager
            db_manager = get_database_manager(connection_string)
            formation._db_manager = db_manager

            formation._long_term_memory = Memobase(
                connection_string=connection_string,
                formation_id=formation_id,
                embedding_model=embedding_model_name,
            )
            formation._is_multi_user = True  # PostgreSQL/Memobase is multi-user mode
            memory_type = "Memobase"

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "persistent_memory",
                "type": memory_type,
                "multi_user": getattr(formation, "_is_multi_user", False),
            },
            description=f"Persistent memory initialized with {memory_type}",
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "persistent_memory"},
            description=f"Failed to initialize persistent memory: {str(e)}",
        )
        # Don't raise - persistent memory is optional


def initialize_document_processing(formation) -> None:
    """
    Initializes the document processing configuration and chunk manager for the formation.

    Creates a `DocumentProcessingConfig` from the formation's LLM configuration and uses it
    to initialize a `DocumentChunkManager`, which is stored on the formation. Emits an
    observability event on success or a warning event if initialization fails.
    """
    try:
        # Create document processing configuration
        # Pass the llm_config instead of document_processing_config
        llm_config = formation._llm_config if hasattr(formation, "_llm_config") else {}
        config = DocumentProcessingConfig(llm_config)

        # Initialize document chunk manager
        formation._document_chunk_manager = DocumentChunkManager(document_config=config)

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "document_processing",
                "chunk_size": config.get_chunk_size(),
                "chunk_overlap": config.get_chunk_overlap(),
                "enabled": config.is_enabled(),
            },
            description="Document processing initialized",
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "document_processing"},
            description=f"Failed to initialize document processing: {str(e)}",
        )


async def initialize_mcp_services(formation) -> None:
    """
    Initialize MCP service and register configured MCP servers.

    This function:
    1. Gets the singleton MCP service instance
    2. Stores the MCP servers for later registration by overlord
    3. Registers MCP servers immediately so agents can see which use user credentials
    4. Emits observability events for tracking
    """
    try:
        from ..services.mcp import MCPService

        # Get the singleton MCP service
        mcp_service = MCPService.get_instance()
        formation._mcp_service = mcp_service

        # Get MCP configuration
        # The servers are in formation._mcp_config which comes from config["mcp"]
        mcp_config = formation._mcp_config if hasattr(formation, "_mcp_config") else {}
        servers = mcp_config.get("servers", [])

        # Store the servers in formation for later access by overlord
        formation._mcp_servers = servers

        # Log MCP server configuration
        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "mcp",
                "server_count": len(servers),
                "user_configured": len(servers),
            },
            description=f"Found {len(servers)} MCP servers to configure",
        )

        # Register MCP servers immediately so agents can see which use user credentials
        await formation._register_mcp_servers()

    except Exception as e:
        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.ERROR,
            data={
                "service": "mcp",
                "error": str(e),
            },
            description=f"Failed to initialize MCP service: {str(e)}",
        )
        # Don't raise - MCP is optional functionality


async def initialize_artifact_service(formation, overlord) -> None:
    """Initialize the artifact generation service."""
    try:
        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={"service": "artifact"},
            description="Initializing artifact generation service",
        )

        # Import and initialize the artifact service
        from .artifacts.artifact_service import get_artifact_service

        artifact_service = get_artifact_service()

        # Store the service in formation and overlord
        formation._artifact_service = artifact_service
        overlord.artifact_service = artifact_service

        observability.observe(
            event_type=observability.SystemEvents.SERVICE_STARTED,
            level=observability.EventLevel.INFO,
            data={"service": "artifact"},
            description="Artifact generation service initialized successfully",
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "artifact"},
            description=f"Failed to initialize artifact service: {str(e)}",
        )
        raise


def initialize_background_services(formation) -> None:
    """
    Initializes background services for the formation, including cache management,
    request tracking, and webhook handling.

    On failure, emits a warning-level observability event with error details.
    """
    try:
        # Cache manager removed - was never actually used

        # Initialize request tracker
        from .background import RequestTracker

        formation._request_tracker = RequestTracker()

        # Initialize webhook manager
        from .background import WebhookManager

        webhook_config = formation.config.get("async", {})
        formation._webhook_manager = WebhookManager(
            default_retries=webhook_config.get("webhook_retries", 3),
            default_timeout=webhook_config.get("webhook_timeout", 30),
        )

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={"services": ["cache_manager", "request_tracker", "webhook_manager"]},
            description="Background services initialized",
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "background_services"},
            description=f"Failed to initialize background services: {str(e)}",
        )


def initialize_clarification_config(formation) -> None:
    """Initialize clarification configuration."""
    clarification_config = (
        formation._clarification_config if hasattr(formation, "_clarification_config") else {}
    )

    if not clarification_config:
        # Use default clarification config
        formation._clarification_config_obj = ClarificationConfig()
        return

    try:
        # Create ClarificationConfig from formation config
        formation._clarification_config_obj = ClarificationConfig(
            enabled=clarification_config.get("enabled", True),
            max_questions=clarification_config.get("max_questions", 5),
            question_style=QuestionStyle(clarification_config.get("question_style", "numbered")),
            require_all_answers=clarification_config.get("require_all_answers", False),
            context_retention=clarification_config.get("context_retention", "full"),
            auto_clarify_threshold=clarification_config.get("auto_clarify_threshold", 0.3),
        )

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "clarification",
                "enabled": formation._clarification_config_obj.enabled,
                "max_questions": formation._clarification_config_obj.max_questions,
            },
            description="Clarification configuration initialized",
        )

    except Exception as e:
        # Use default on error
        formation._clarification_config_obj = ClarificationConfig()
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "clarification"},
            description=f"Failed to initialize clarification config, using defaults: {str(e)}",
        )


def initialize_document_processing_config(formation) -> None:
    """
    Initializes the document processing configuration and chunk manager for the formation.

    Creates a `DocumentProcessingConfig` from the formation's LLM configuration
    and assigns it to the formation. Initializes a `DocumentChunkManager`
    with this configuration and assigns it to both `_document_chunker` and
    `_document_chunk_manager` for compatibility. Emits an observability event
    if document processing is enabled. On failure, logs a warning and falls
    back to a default configuration.
    """
    try:
        # Use the pre-configured LLM config
        llm_config = formation._llm_config if hasattr(formation, "_llm_config") else {}

        # Create document processing configuration instance using unified schema
        formation._document_processing_config = DocumentProcessingConfig(llm_config)

        # Log the configuration details
        enabled = formation._document_processing_config.is_enabled()
        if enabled:
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.INFO,
                data={
                    "service": "document_processing",
                    "enabled": enabled,
                    "settings": formation._document_processing_config.get_settings(),
                },
                description="Document processing configuration initialized",
            )

        # Initialize DocumentChunkManager with the configuration
        formation._document_chunker = DocumentChunkManager(formation._document_processing_config)
        # Also set as _document_chunk_manager for backwards compatibility
        formation._document_chunk_manager = formation._document_chunker

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "document_processing"},
            description=f"Failed to initialize document processing config: {str(e)}",
        )

        # Fall back to default configuration
        formation._document_processing_config = DocumentProcessingConfig({})


def load_agents_from_configuration(formation) -> None:
    """
    Load agents from formation configuration.

    This method reads the agents_config and creates pre-configured
    agent definitions that the Overlord will instantiate when needed.
    """
    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.DEBUG,
        data={"agents_count": len(formation._agents_config)},
        description=f"Processing {len(formation._agents_config)} agents from configuration",
    )

    if not formation._agents_config:
        # No agents configured - this is valid for some formations
        observability.observe(
            event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
            level=observability.EventLevel.INFO,
            data={"agent_count": 0},
            description="No agents configured in formation",
        )
        return

    # Process each agent configuration
    processed_count = 0
    for agent_config in formation._agents_config:
        try:
            agent_id = agent_config.get("id")
            if not agent_id:
                observability.observe(
                    event_type=observability.SystemEvents.AGENT_INITIALIZED,
                    level=observability.EventLevel.WARNING,
                    data={"error": "Agent missing ID"},
                    description="Skipping agent without ID",
                )
                continue

            # Validate agent configuration has required fields
            if not agent_config.get("name"):
                agent_config["name"] = agent_id

            processed_count += 1

            observability.observe(
                event_type=observability.SystemEvents.AGENT_INITIALIZED,
                level=observability.EventLevel.DEBUG,
                data={
                    "agent_id": agent_id,
                    "name": agent_config.get("name", agent_id),
                    "role": agent_config.get("role", "general"),
                },
                description=f"Agent '{agent_id}' configuration processed",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.AGENT_INITIALIZED,
                level=observability.EventLevel.ERROR,
                data={"agent_id": agent_config.get("id", "unknown"), "error": str(e)},
                description=f"Failed to process agent configuration: {str(e)}",
            )
            continue

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={"agent_count": processed_count},
        description=f"Processed {processed_count} agent configurations",
    )


async def initialize_buffer_memory(formation, overlord, buffer_config: Dict[str, Any]) -> None:
    """Initialize buffer memory from configuration with defaults."""

    try:
        # Create BufferMemoryConfig with provided config, using defaults for missing values
        config = BufferMemoryConfig(**buffer_config)

        # Extract configuration values from the validated config
        size = config.size
        multiplier = config.multiplier
        vector_search = config.vector_search
        dimension = config.vector_dimension
        mode = config.mode
        remote_config = config.remote

        # Get embedding model for vector search if enabled
        embedding_model = None
        if vector_search:
            try:
                embedding_model = await overlord.get_model_for_capability("embedding")
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "embedding_model"},
                    description=f"Failed to initialize embedding model for buffer memory: {str(e)}",
                )
                vector_search = False

        # Create buffer memory instance
        buffer_memory = WorkingMemory(
            formation_id=overlord.formation_id,
            max_size=size,
            buffer_multiplier=multiplier,
            dimension=dimension,
            model=embedding_model,
            mode=mode,
            remote=remote_config.model_dump() if remote_config and mode == "remote" else None,
        )

        # Store on both formation and overlord for now (during transition)
        formation._buffer_memory = buffer_memory
        overlord.buffer_memory = buffer_memory

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "config_type": "buffer_memory"},
            description=f"Failed to initialize buffer memory: {str(e)}",
        )
        raise


async def _get_embedding_model(
    overlord, embedding_model_name: Optional[str] = None
) -> Optional[Any]:
    """Get embedding model with fallback to default capability.

    Args:
        overlord: The overlord instance
        embedding_model_name: Optional specific model name to use

    Returns:
        The embedding model instance or None if initialization fails
    """
    embedding_model = None

    if embedding_model_name:
        try:
            # Create model from specific name override
            embedding_model = await overlord.create_model(model=embedding_model_name)
        except Exception as e:
            # Log the specific model failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "model_name": embedding_model_name,
                    "config_type": "embedding_model",
                },
                description=f"Failed to create embedding model '{embedding_model_name}': {str(e)}",
            )
            # Fall back to default embedding capability
            try:
                embedding_model = await overlord.get_model_for_capability("embedding")
            except Exception as e2:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e2), "config_type": "embedding_model"},
                    description=f"Failed to initialize default embedding model: {str(e2)}",
                )
    else:
        # No specific model requested, use default capability
        try:
            embedding_model = await overlord.get_model_for_capability("embedding")
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "config_type": "embedding_model"},
                description=f"Failed to initialize default embedding model: {str(e)}",
            )

    return embedding_model


async def initialize_persistent_memory(
    formation, overlord, persistent_config: Dict[str, Any]
) -> None:
    """Initialize persistent memory from configuration."""
    try:
        connection_string = persistent_config.get("connection_string")
        embedding_model_name = persistent_config.get("embedding_model")

        if not connection_string:
            return

        # Interpolate secrets in connection string if needed
        if "${{ secrets." in connection_string:
            try:
                interpolated = await overlord.interpolate_secrets(
                    {"connection_string": connection_string}
                )
                connection_string = interpolated.get("connection_string", connection_string)
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "persistent_memory_secrets"},
                    description=f"Failed to interpolate persistent memory secrets: {str(e)}",
                )
                return

        # Get embedding model
        embedding_model = await _get_embedding_model(overlord, embedding_model_name)

        # Determine multi-user mode - check explicit config first, then infer from database type
        explicit_multi_user = persistent_config.get("multi_user")
        if explicit_multi_user is not None:
            is_multi_user = bool(explicit_multi_user)
        else:
            # Fall back to inferring from database type
            is_multi_user = connection_string.startswith(
                "postgresql://"
            ) or connection_string.startswith("postgres://")

        # Store multi-user mode on overlord
        overlord.is_multi_user = is_multi_user

        # Determine memory type based on connection string
        if connection_string.startswith("postgresql://") or connection_string.startswith(
            "postgres://"
        ):
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.INFO,
                data={
                    "database_type": "postgresql",
                    "memory_type": "persistent",
                    "multi_user": is_multi_user,
                },
                description=(
                    "Initializing persistent memory with PostgreSQL backend "
                    f"(multi-user: {is_multi_user})"
                ),
            )
            from ..services.memory.memobase import Memobase
            from ..services.memory.long_term import LongTermMemory
            from ..services.db import get_database_manager

            # Create ONE DatabaseManager for the Formation
            db_manager = get_database_manager(connection_string)

            # Store db_manager on both formation and overlord
            formation._db_manager = db_manager
            overlord.db_manager = db_manager

            # Create LongTermMemory using the shared DatabaseManager
            long_term_memory = LongTermMemory(
                db_manager=db_manager,
                formation_id=overlord.formation_id,
                embedding_model=embedding_model,
            )

            # Create Memobase with the LongTermMemory instance
            # Note: Memobase is still needed for user context management features
            memobase = Memobase(long_term_memory=long_term_memory)

            # Store on both formation and overlord
            formation._long_term_memory = memobase
            overlord.long_term_memory = memobase

            # Initialize required collections
            await overlord._initialize_collections()

        elif connection_string.startswith("sqlite://") or connection_string.endswith(".db"):
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.INFO,
                data={
                    "database_type": "sqlite",
                    "memory_type": "persistent",
                    "multi_user": is_multi_user,
                },
                description=(
                    "Initializing persistent memory with SQLite backend "
                    f"(multi-user: {is_multi_user})"
                ),
            )
            from ..services.memory.sqlite import SQLiteMemory
            from ..services.db import get_database_manager

            # Remove sqlite:// prefix if present
            db_path = connection_string.replace("sqlite://", "")
            sqlite_memory = SQLiteMemory(db_path=db_path, formation_id=overlord.formation_id)

            # Store on both formation and overlord
            formation._long_term_memory = sqlite_memory
            overlord.long_term_memory = sqlite_memory

            # Create DatabaseManager for scheduler access (SQLite)
            db_manager = get_database_manager(connection_string)
            formation._db_manager = db_manager
            overlord.db_manager = db_manager

            # Set the embedding provider after initialization
            if embedding_model:
                sqlite_memory.embedding_provider = embedding_model

            # Initialize required collections
            await overlord._initialize_collections()

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "config_type": "persistent_memory"},
            description=f"Critical error during persistent memory initialization: {str(e)}",
        )
        raise
