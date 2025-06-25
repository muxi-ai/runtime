"""
Configuration initialization utilities for the Overlord.

This module contains all the initialization logic extracted from the main Overlord class
to improve maintainability and separation of concerns.
"""

from typing import Any, Dict, Optional

from ...services.observability.utils import detect_stream_protocol
from ...services.memory.short_term import ShortTermMemory
from ...datatypes.clarification import ClarificationConfig, QuestionStyle
from ...services import observability


async def initialize_llm_config(overlord) -> None:
    """
    Initialize LLM configuration from formation config.

    This processes the new capability-based LLM schema and sets up model
    resolution for different capabilities like text, vision, transcription, etc.
    """
    # Use the pre-configured LLM config from configured_services
    # This already has secrets interpolated by the Formation
    if hasattr(overlord, "_configured_services") and overlord._configured_services:
        llm_config = overlord._configured_services.get("llm_config", {})
    else:
        llm_config = overlord.formation_config.get("llm", {})

    # Initialize model cache for capability-based resolution
    overlord._model_cache = {}
    overlord._capability_models = {}

    # Process models by capability
    models_config = llm_config.get("models", [])
    for model_config in models_config:
        for capability, model_name in model_config.items():
            if capability in ["api_key", "settings"]:
                continue  # Skip metadata

            overlord._capability_models[capability] = {
                "model": model_name,
                "api_key": model_config.get("api_key"),
                "settings": model_config.get("settings", {}),
            }

    # Store global settings and api_keys for later use
    overlord._global_llm_settings = llm_config.get("settings", {})
    overlord._global_api_keys = llm_config.get("api_keys", {})

    capabilities = list(overlord._capability_models.keys())
    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={"capabilities": capabilities, "capability_count": len(capabilities)},
        description=f"LLM configuration initialized with {len(capabilities)} capabilities",
    )


async def initialize_auth_config(overlord) -> None:
    """
    Initialize auth configuration from formation config.

    This processes the auth.api_keys structure and updates the overlord's
    API keys if they are provided in the formation config.
    """
    auth_config = overlord.formation_config.get("auth", {})
    auth_api_keys = auth_config.get("api_keys", {})

    # Update admin and user API keys from formation config if provided
    if "admin_key" in auth_api_keys:
        admin_key = auth_api_keys["admin_key"]
        # Interpolate secrets if needed
        if admin_key and "${{ secrets." in admin_key:
            try:
                interpolated_config = await overlord.interpolate_secrets({"admin_key": admin_key})
                admin_key = interpolated_config.get("admin_key", admin_key)
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.FAILED_INITIALIZATION,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "admin_key"},
                    description=f"Failed to interpolate admin_key secret: {str(e)}",
                )

        overlord.admin_api_key = admin_key

    if "client_key" in auth_api_keys:
        client_key = auth_api_keys["client_key"]
        # Interpolate secrets if needed
        if client_key and "${{ secrets." in client_key:
            try:
                interpolated_config = await overlord.interpolate_secrets({"client_key": client_key})
                client_key = interpolated_config.get("client_key", client_key)
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.FAILED_INITIALIZATION,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "client_key"},
                    description=f"Failed to interpolate client_key secret: {str(e)}",
                )

        overlord.client_api_key = client_key


async def initialize_memory_config(overlord) -> None:
    """
    Initialize memory configuration from formation config.

    This processes the memory.working and memory.persistent configuration
    and initializes or updates the overlord's memory systems according
    to the new schema specifications.
    """
    # Use the pre-configured memory config from configured_services
    # This already has secrets interpolated by the Formation
    if hasattr(overlord, "_configured_services") and overlord._configured_services:
        memory_config = overlord._configured_services.get("memory_config", {})
    else:
        memory_config = overlord.formation_config.get("memory", {})

    if not memory_config:
        return

    # Initialize buffer memory configuration
    # (moved from working.buffer to top-level)
    buffer_config = memory_config.get("buffer", {})
    if buffer_config and not overlord.buffer_memory:
        await _initialize_buffer_memory(overlord, buffer_config)
        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={"memory_type": "buffer", "buffer_config": buffer_config},
            description="Initializing buffer memory from configuration",
        )

    # Initialize persistent memory configuration
    persistent_config = memory_config.get("persistent", {})
    if persistent_config and not overlord.long_term_memory:
        await _initialize_persistent_memory(overlord, persistent_config)
        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={"memory_type": "persistent", "persistent_config": persistent_config},
            description="Initializing persistent memory from configuration",
        )


async def _initialize_buffer_memory(overlord, buffer_config: Dict[str, Any]) -> None:
    """Initialize buffer memory from configuration."""
    try:
        # Extract buffer configuration
        size = buffer_config.get("size", 10)
        multiplier = buffer_config.get("multiplier", 10)
        vector_search = buffer_config.get("vector_search", True)
        dimension = buffer_config.get("vector_dimension", 1536)
        mode = buffer_config.get("mode", "local")
        remote_config = buffer_config.get("remote", {})

        # Get embedding model for vector search if enabled
        embedding_model = None
        if vector_search:
            try:
                embedding_model = await overlord.get_model_for_capability("embedding")
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.FAILED_INITIALIZATION,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "embedding_model"},
                    description=f"Failed to initialize embedding model for buffer memory: {str(e)}",
                )
                vector_search = False

        # Create buffer memory instance
        overlord.buffer_memory = ShortTermMemory(
            max_size=size,
            buffer_multiplier=multiplier,
            dimension=dimension,
            model=embedding_model,
            mode=mode,
            remote=remote_config if mode == "remote" else None,
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.FAILED_INITIALIZATION,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "config_type": "buffer_memory"},
            description=f"Failed to initialize buffer memory: {str(e)}",
        )
        raise


async def _initialize_persistent_memory(overlord, persistent_config: Dict[str, Any]) -> None:
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
                    event_type=observability.ErrorEvents.FAILED_INITIALIZATION,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "persistent_memory_secrets"},
                    description=f"Failed to interpolate persistent memory secrets: {str(e)}",
                )
                return

        # Get embedding model
        embedding_model = None
        if embedding_model_name:
            try:
                # Create model from specific name override
                embedding_model = await overlord.create_model(model=embedding_model_name)
            except Exception as e:
                #  Warning - TODO: add observability
                # ErrorEvents.FAILED_INITIALIZATION (embedding model)
                _ = e  # remove this after implementing observability
                try:
                    # Fall back to default embedding capability
                    embedding_model = await overlord.get_model_for_capability("embedding")
                except Exception as e2:
                    #  Warning - TODO: add observability
                    # ErrorEvents.FAILED_INITIALIZATION (embedding model)
                    _ = e2  # remove this after implementing observability

        # Determine memory type based on connection string
        if connection_string.startswith("postgresql://") or connection_string.startswith(
            "postgres://"
        ):
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.INFO,
                data={"database_type": "postgresql", "memory_type": "persistent"},
                description="Initializing persistent memory with PostgreSQL backend",
            )
            from ...services.memory.memobase import Memobase
            from ...services.memory.long_term import LongTermMemory
            from ...services.db import get_database_manager

            # PostgreSQL means multi-user mode
            overlord.is_multi_user = True

            # Create ONE DatabaseManager for the Formation
            db_manager = get_database_manager(connection_string)

            # Store db_manager on overlord for scheduler access
            overlord.db_manager = db_manager

            # Create LongTermMemory using the shared DatabaseManager
            long_term_memory = LongTermMemory(
                db_manager=db_manager, embedding_model=embedding_model
            )

            # Create Memobase with the LongTermMemory instance
            # Note: Memobase is still needed for user context management features
            overlord.long_term_memory = Memobase(long_term_memory=long_term_memory)

        elif connection_string.startswith("sqlite://") or connection_string.endswith(".db"):
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.INFO,
                data={"database_type": "sqlite", "memory_type": "persistent"},
                description="Initializing persistent memory with SQLite backend",
            )
            from ...services.memory.sqlite import SQLiteMemory
            from ...services.db import get_database_manager

            # SQLite means single-user mode
            overlord.is_multi_user = False

            # Remove sqlite:// prefix if present
            db_path = connection_string.replace("sqlite://", "")
            overlord.long_term_memory = SQLiteMemory(db_path=db_path)

            # Create DatabaseManager for scheduler access (SQLite)
            db_manager = get_database_manager(connection_string)
            overlord.db_manager = db_manager

            # Set the embedding provider after initialization
            if embedding_model:
                try:
                    embedding_llm = await overlord.get_model_for_capability("embedding")
                    overlord.long_term_memory.embedding_provider = embedding_llm
                except Exception as e:
                    #  Warning - TODO: add observability
                    # ErrorEvents.FAILED_INITIALIZATION (embedding provider)
                    _ = e  # remove this after implementing observability

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "config_type": "persistent_memory"},
            description=f"Critical error during persistent memory initialization: {str(e)}",
        )
        raise


async def initialize_logging_config(overlord) -> None:
    """
    Initialize logging configuration from formation config.

    This processes the multi-stream logging configuration and configures
    the logging system for the formation.
    """
    # Use the pre-configured logging config from configured_services
    # This already has secrets interpolated by the Formation
    if hasattr(overlord, "_configured_services") and overlord._configured_services:
        logging_config = overlord._configured_services.get("logging_config", {})
    else:
        logging_config = overlord.formation_config.get("logging", {})

    if not logging_config:
        return

    try:
        # Extract global logging settings
        enabled = logging_config.get("enabled", True)
        streams = logging_config.get("streams", [])

        # Only configure logging if enabled
        if not enabled:
            #  Info - TODO: add observability
            # SystemEvents.INITIALIZING (logging - "disabled")
            return

        if not streams:
            #  Info - TODO: add observability
            # SystemEvents.INITIALIZING (logging - "no streams configured")
            return

        # Process each stream
        processed_streams = []
        for stream in streams:
            try:
                processed_stream = await _process_logging_stream(overlord, stream)
                if processed_stream:
                    processed_streams.append(processed_stream)
            except Exception as e:
                #  Warning - TODO: add observability
                # SystemEvents.FAILED_INITIALIZATION (logging)
                _ = e  # remove this after implementing observability
                continue

        # Store processed logging configuration
        overlord._logging_config = {"enabled": enabled, "streams": processed_streams}

    except Exception as e:
        #  Warning - TODO: add observability
        # ErrorEvents.INTERNAL_ERROR (logging)
        _ = e  # remove this after implementing observability
        raise


async def _process_logging_stream(overlord, stream: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Process a single logging stream configuration.

    Args:
        overlord: The overlord instance
        stream: Stream configuration dictionary

    Returns:
        Processed stream configuration or None if invalid
    """
    # Extract basic stream configuration
    transport = stream.get("transport")
    level = stream.get("level", "info")
    format_type = stream.get("format", "jsonl")
    events = stream.get("events", [])
    auth = stream.get("auth", {})

    if not transport:
        #  Warning - TODO: add observability
        # SystemEvents.FAILED_INITIALIZATION
        return None

    # Process transport-specific configuration
    processed_stream = {
        "transport": transport,
        "level": level,
        "format": format_type,
        "events": events,
        "auth": auth,
    }

    if transport == "stdout":
        # No additional configuration needed for stdout
        pass

    elif transport == "file":
        destination = stream.get("destination")
        if not destination:
            #  Warning - TODO: add observability
            # SystemEvents.FAILED_INITIALIZATION
            return None
        processed_stream["destination"] = destination

    elif transport == "stream":
        destination = stream.get("destination")
        protocol = stream.get("protocol")

        if not destination:
            #  Warning - TODO: add observability
            # SystemEvents.FAILED_INITIALIZATION
            return None

        # Auto-detect protocol if not specified
        if not protocol:
            protocol = detect_stream_protocol(destination)

        processed_stream["destination"] = destination
        processed_stream["protocol"] = protocol

    elif transport == "trail":
        # MUXI Trail transport - special case with fixed destination
        processed_stream["destination"] = "tcps://trail.muxi.ai/ingest"
        processed_stream["protocol"] = "zmq"
        processed_stream["format"] = "msgpack"  # Trail always uses msgpack

        # Ensure auth is configured for trail
        if not auth:
            return None

    else:
        #  Warning - TODO: add observability
        # SystemEvents.FAILED_INITIALIZATION
        return None

    # Interpolate secrets in auth if needed
    if auth:
        try:
            interpolated_auth = await overlord.interpolate_secrets(auth)
            processed_stream["auth"] = interpolated_auth
        except Exception as e:
            #  Warning - TODO: add observability
            # ErrorEvents.INTERNAL_ERROR
            _ = e  # remove this after implementing observability

    return processed_stream


async def initialize_clarification_config(overlord) -> None:
    """
    Initialize clarification configuration from formation config.

    This processes the overlord.clarification configuration for intelligent
    parameter collection and applies privacy-by-default settings with
    industry-standard style preferences.
    """
    # Use the pre-configured clarification config from configured_services
    # This already has secrets interpolated by the Formation
    if hasattr(overlord, "_configured_services") and overlord._configured_services:
        clarification_config = overlord._configured_services.get("clarification_config", {})
    else:
        overlord_config = overlord.formation_config.get("overlord", {})
        clarification_config = overlord_config.get("clarification", {})

    if not clarification_config:
        return

    try:
        # Extract configuration with privacy-by-default approach
        max_questions = clarification_config.get("max_questions", 5)
        style_str = clarification_config.get("style", "conversational")
        persist_learned_info = clarification_config.get("persist_learned_info", False)

        # Validate and convert style string to enum
        try:
            style = QuestionStyle(style_str.lower())
        except ValueError:
            style = QuestionStyle.CONVERSATIONAL

        # Validate max_questions
        if not isinstance(max_questions, int) or max_questions < 1:
            max_questions = 5
        elif max_questions > 20:
            #  Warning - TODO: add observability
            # ErrorEvents.WARNING
            #   f"max_questions '{max_questions}' is very high, consider reducing for better UX"
            _ = max_questions  # remove this after implementing observability

        # Update the overlord's clarification configuration
        overlord.clarification_config = ClarificationConfig(
            max_questions=max_questions, style=style, persist_learned_info=persist_learned_info
        )

    except Exception as e:
        # Keep default configuration on error
        #  Warning - TODO: add observability
        # ErrorEvents.FAILED_INITIALIZATION
        _ = e  # remove this after implementing observability

    if clarification_config:
        _ = None  # remove this after implementing observability


async def initialize_document_processing_config(overlord) -> None:
    """
    Initialize document processing configuration from LLM models in formation config.

    This processes the unified document configuration from llm.models.documents.settings
    for use by document-related components.
    """
    try:
        # Import the document processing config module
        from ..config.document_processing import DocumentProcessingConfig

        # Extract LLM configuration from formation
        # Use the pre-configured LLM config from configured_services
        # This already has secrets interpolated by the Formation
        if hasattr(overlord, "_configured_services") and overlord._configured_services:
            llm_config = overlord._configured_services.get("llm_config", {})
        else:
            llm_config = overlord.formation_config.get("llm", {})

        # Create document processing configuration instance using unified schema
        overlord.document_processing_config = DocumentProcessingConfig(llm_config)

        # Log the configuration details
        enabled = overlord.document_processing_config.is_enabled()
        if enabled:
            #  Info - TODO: add observability
            # SystemEvents.INITIALIZING (document processing config + settings)
            pass

    except Exception as e:
        #  Warning - TODO: add observability
        # ErrorEvents.FAILED_INITIALIZATION
        _ = e  # remove this after implementing observability

        # Fall back to default configuration
        from ..config.document_processing import DocumentProcessingConfig

        overlord.document_processing_config = DocumentProcessingConfig({})


async def load_agents_from_configuration(overlord) -> None:
    """
    Load agents from formation configuration during overlord startup.

    This method reads the agents_config from configured_services and creates
    Agent instances for each configured agent, adding them to overlord.agents.
    """
    from ...services import observability

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.DEBUG,
        data={"configured_services_keys": list(overlord._configured_services.keys())},
        description="Starting agent loading from configuration",
    )

    # Get agents configuration from configured services
    agents_config = overlord._configured_services.get("agents_config", [])

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.DEBUG,
        data={"agents_count": len(agents_config)},
        description=f"Found {len(agents_config)} agents in configuration",
    )

    if not agents_config:
        # No agents configured - this is valid for some formations
        observability.observe(
            event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
            level=observability.EventLevel.INFO,
            data={"agent_count": 0},
            description="No agents configured in formation",
        )
        return

    # Load each agent configuration
    loaded_count = 0
    for agent_config in agents_config:
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

            # Create agent from configuration
            agent = await create_agent_from_config(overlord, agent_config)

            # Add to agents dictionary
            overlord.agents[agent_id] = agent

            # Store agent metadata for routing
            overlord.agent_descriptions[agent_id] = agent_config.get("description", "")
            overlord.agent_metadata[agent_id] = {
                "name": agent_config.get("name", agent_id),
                "role": agent_config.get("role", "general"),
                "specialties": agent_config.get("specialties", []),
                "system_message": agent_config.get("system_message", ""),
            }

            loaded_count += 1

            observability.observe(
                event_type=observability.SystemEvents.AGENT_INITIALIZED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": agent_id,
                    "name": agent_config.get("name", agent_id),
                    "role": agent_config.get("role", "general"),
                },
                description=f"Agent '{agent_id}' loaded successfully",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.AGENT_INITIALIZED,
                level=observability.EventLevel.ERROR,
                data={"agent_id": agent_config.get("id", "unknown"), "error": str(e)},
                description=f"Failed to load agent: {str(e)}",
            )
            continue

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={"agent_count": loaded_count},
        description=f"Loaded {loaded_count} agents from formation configuration",
    )


async def create_agent_from_config(overlord, agent_config: Dict[str, Any]):
    """
    Create an Agent instance from configuration.

    Args:
        overlord: The overlord instance
        agent_config: Agent configuration dictionary from formation

    Returns:
        Agent: Configured agent instance
    """
    from ..agents.agent import Agent
    from ...services.llm.service import OneLLMService

    # Get or create LLM model for the agent
    # Use overlord's model creation capability
    try:
        # Try to use overlord's model creation (it should be initialized by now)
        model = await overlord.get_model_for_capability("text")
    except Exception:
        # Fallback: create a basic model using OneLLMService
        llm_service = await OneLLMService.get_instance()
        # Use a basic text model for the agent
        model = await llm_service.get_model("gpt-4o-mini")  # Basic fallback model

    # Create agent instance
    agent = Agent(
        model=model,
        overlord=overlord,
        agent_id=agent_config.get("id"),
        name=agent_config.get("name"),
        system_message=agent_config.get("system_message"),
        knowledge_config=agent_config.get("knowledge"),
    )

    return agent
