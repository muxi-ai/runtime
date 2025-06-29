"""
Formation initialization utilities.

This module contains all the initialization logic for the Formation class,
handling all infrastructure and service setup. This ensures proper separation
of concerns where Formation handles operations and Overlord handles intelligence.

The initialization order is critical:
1. Observability MUST be initialized first
2. Then other services can be initialized
"""

from typing import Any, Dict

from ..datatypes.clarification import ClarificationConfig, QuestionStyle
from ..datatypes.memory import BufferMemoryConfig, WorkingMemoryConfig
from ..datatypes.observability import EventLevel
from ..services import observability
from ..services.memory.short_term import ShortTermMemory
from ..services.observability.context import set_event_logger
from ..services.observability.logger import EventLogger
from .config.document_processing import DocumentProcessingConfig
from .documents.storage.chunk_manager import DocumentChunkManager


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

    capabilities = list(formation._capability_models.keys())
    observability.observe(
        event_type=observability.SystemEvents.INITIALIZING,
        level=observability.EventLevel.INFO,
        data={
            "service": "llm",
            "capabilities": capabilities,
            "capability_count": len(capabilities),
        },
        description=f"LLM configuration initialized with {len(capabilities)} capabilities",
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
        if vector_search and hasattr(formation, "_capability_models"):
            # TODO: Create embedding model from capability
            # For now, disable vector search if no model available
            vector_search = False

        # Create buffer memory instance
        formation._buffer_memory = ShortTermMemory(
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
    """Initialize persistent memory from configuration."""
    try:
        connection_string = persistent_config.get("connection_string")

        # Interpolate secrets if needed
        if "${{ secrets." in connection_string:
            # For now, skip interpolation in sync context
            # TODO: Make interpolate_secrets synchronous
            pass

        # Determine the type of persistent memory based on connection string
        if connection_string.startswith("postgresql://"):
            # PostgreSQL memory
            from ..services.memory.long_term import LongTermMemory

            formation._long_term_memory = LongTermMemory(
                connection_string=connection_string,
                embedding_model=None,  # TODO: Add embedding model
            )
            formation._is_multi_user = True
            memory_type = "PostgreSQL"

        elif connection_string.endswith(".db") or "sqlite" in connection_string:
            # SQLite memory
            from ..services.memory.sqlite import SQLiteMemory

            formation._long_term_memory = SQLiteMemory(
                db_path=connection_string, embedding_model=None  # TODO: Add embedding model
            )
            memory_type = "SQLite"

        else:
            # Default to Memobase
            from ..services.memory.memobase import Memobase

            formation._long_term_memory = Memobase(
                connection_string=connection_string,
                embedding_model=None,  # TODO: Add embedding model
            )
            memory_type = "Memobase"

        # Store database manager for scheduler
        if hasattr(formation._long_term_memory, "db_manager"):
            formation._db_manager = formation._long_term_memory.db_manager

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
    """Initialize document processing components."""
    doc_config = (
        formation._document_processing_config
        if hasattr(formation, "_document_processing_config")
        else {}
    )

    if not doc_config or not doc_config.get("enabled", True):
        return

    try:
        # Create document processing configuration
        config = DocumentProcessingConfig(**doc_config)

        # Initialize document chunk manager
        formation._document_chunk_manager = DocumentChunkManager(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            max_chunks_per_doc=config.max_chunks_per_doc,
            storage_backend=config.storage_backend,
        )

        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "document_processing",
                "chunk_size": config.chunk_size,
                "chunk_overlap": config.chunk_overlap,
                "backend": config.storage_backend,
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


def initialize_background_services(formation) -> None:
    """Initialize background services like cache, request tracking, webhooks."""
    try:
        # Initialize cache manager
        from .caching import IntelligentCacheManager

        formation._cache_manager = IntelligentCacheManager(
            enable_analytics=True,
            ttl_seconds=3600,
            max_cache_size_mb=100,
            eviction_policy="lru",
            formation_id=formation.formation_id,
        )
        # Cache manager will be started later if needed

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
