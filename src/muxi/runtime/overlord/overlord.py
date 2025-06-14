# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Overlord 2.0 - Intelligent Multi-Agent Orchestration System
# Description:  Advanced AI coordination engine with intelligent workflow orchestration
# Role:         The autonomous backbone of the Muxi framework's multi-agent architecture
# Usage:        Primary conversation partner for users with seamless agent coordination
# Author:       Muxi Framework Team
#
# The Overlord 2.0 is an intelligent orchestration system that transforms MUXI from
# a simple agent router into an autonomous multi-agent coordinator. Users interact
# with a single, consistent persona that seamlessly delegates complex tasks to
# specialized agents behind the scenes.
#
# Core Capabilities:
#
# 1. Intelligent Workflow Orchestration
#    - Automatic complexity analysis of user requests
#    - AI-powered task decomposition into multi-agent workflows
#    - Plan preview and approval workflows for complex tasks
#    - DAG-based execution with dependency resolution
#    - Real-time progress tracking and coordination
#
# 2. Seamless Agent Coordination
#    - Capability-based intelligent agent selection
#    - Multi-agent workflow execution with state management
#    - Advanced response synthesis from multiple agent outputs
#    - Graceful fallback to simple routing for basic requests
#
# 3. Enhanced Memory Systems
#    - Centralized buffer memory for conversation context
#    - Long-term memory with multi-user support (Memobase)
#    - Intelligent user information extraction across all interactions
#    - Context preservation across complex workflows
#
# 4. External Integration & Tools
#    - MCP (Model Context Protocol) server integration
#    - A2A (Agent-to-Agent) communication with external formations
#    - Secure API access and secrets management
#    - Dynamic tool discovery and registration
#
# 5. User Experience Excellence
#    - Persona-first architecture - users never feel "transferred"
#    - Natural language plan explanations with approval workflows
#    - Consistent voice across simple and complex interactions
#    - Transparent progress updates for long-running tasks
#
# Usage Examples:
#
# Simple Interaction (Direct Routing):
#   overlord = Overlord()
#   response = await overlord.chat("What's the weather today?")
#   # → Routes directly to weather agent, maintains overlord persona
#
# Complex Workflow (Automatic Decomposition):
#   response = await overlord.chat("Research AI trends and write a comprehensive report")
#   # → Automatically decomposes into: research → analysis → writing workflow
#   # → Coordinates multiple agents seamlessly behind the scenes
#   # → Returns unified response as if from single assistant
#
# Plan Approval Workflow:
#   response = await overlord.chat("Refactor my auth system. Show me your plan first.")
#   # → Detects approval request, generates human-readable plan
#   # → Presents plan for user review before execution
#   # → Handles approval/rejection/modification workflow
#
# Configuration-based Setup:
#   app = muxi(buffer_size=50, enable_workflow=True)
#   app.add_agent("researcher", "configs/researcher.yaml")
#   app.add_agent("writer", "configs/writer.yaml")
#   response = await app.chat("Create a business plan for sustainable packaging")
#   # → Intelligent orchestration across multiple specialists
#
# This implementation represents the culmination of Tasks 3.2, 3.4, and 3.6,
# transforming MUXI into a truly autonomous multi-agent orchestration system.
# =============================================================================

import asyncio
import hashlib
import time
from typing import Any, Dict, List, Optional, Union
import datetime
import os


from .. import observability
from ..agent import Agent
from ..mcp.message import MCPMessage
from ..mcp.service import MCPService
from ..memory.short_term import ShortTermMemory
from ..memory.long_term import LongTermMemory
from ..memory.memobase import Memobase
from ..llm import LLM
from ..a2a.registry_client import A2ARegistryClient
from ..a2a.formation_server import A2AFormationServer

# A2A models imported when needed
from ..secrets_manager import SecretsManager
from ..utils.id_generator import generate_nanoid

# Enhanced workflow capabilities
from .workflow import (
    RequestAnalyzer,
    TaskDecomposer,
    WorkflowExecutor,
    ApprovalManager,
    ProgressTracker,
    Workflow,
)

# NEW: Import multimodal and synthesis components
from .workflow.multimodal import MultiModalFusionEngine, MultiModalWorkflowIntegrator
from .workflow.synthesis import AdvancedResponseSynthesizer, ResponseQualityAssessor

# NEW: Import interactive elements and enhanced multimodal integration
from .workflow.interactive import InteractiveElementGenerator, ResponseFormatter, MediaIntegrator
from .workflow.multimodal_integration import (
    WorkflowMultiModalProcessor,
    TaskInputProcessor,
    TaskOutputProcessor,
)

# NEW: Import intelligent caching system
from .caching import IntelligentCacheManager

# NEW: Import parallel workflow optimization
from .parallel import ParallelWorkflowOptimizer

# NEW: Import Phase 3 intelligence components
from .intelligence import (
    UserPreferenceEngine,
    AdaptiveResponseGenerator,
)

# NEW: Import Phase 4.1 resilience components
from .resilience import (
    ResilientWorkflowManager,
    ResilienceConfig,
)

# Document Processing Components (Tasks 3.7-3.9)
from .document_storage import (
    DocumentChunkManager,
    DocumentMetadataStore,
    DocumentReferenceSystem,
)
from .document_experience import (
    DocumentAcknowledgmentGenerator,
    DocumentSummarizer,
    DocumentErrorHandler,
)
from .document_workflow import (
    DocumentWorkflowIntegrator,
    DocumentCrossReferenceManager,
    DocumentContextPreserver,
)

# Async Orchestration Components (Task 4)
from .async_patterns import (
    RequestTracker,
    WebhookManager,
    TimeEstimator,
)

# Unified Response Components (Phase 3)
from ..utils.response_converter import create_unified_response, extract_user_content


class Overlord:
    """
    Overlord for managing agents, memory, and interactions with enhanced workflow orchestration.

    The Overlord serves as the central coordination component in the Muxi Framework.
    It manages multiple agents, provides centralized memory access, handles message routing,
    coordinates user interactions, and manages external registry communication for A2A.
    The Overlord maintains buffer and long-term memory systems that can be shared across
    agents, enabling coherent multi-agent conversations.

    Enhanced with intelligent workflow orchestration capabilities including:
    - Automatic complexity analysis of user requests
    - Intelligent decomposition into multi-agent workflows
    - Plan preview with user approval workflow
    - DAG-based execution with progress tracking
    - Graceful fallback to simple agent routing

    Key responsibilities:
    - Agent lifecycle management (creation, retrieval, removal)
    - Centralized memory management
    - Intelligent message routing and workflow orchestration
    - User authentication and authorization
    - Multi-user support
    - Tool integration via MCP
    - External A2A registry integration for cross-formation communication

    Attributes:
        agents (Dict[str, Agent]): Dictionary of registered agents, keyed by agent_id
        agent_descriptions (Dict[str, str]): Descriptions of agents used for routing
        default_agent_id (Optional[str]): ID of the default agent for unrouted messages
        buffer_memory (Optional[ShortTermMemory]): Short-term memory for recent context
        long_term_memory (Optional[Union[LongTermMemory, Memobase]]): Persistent memory system
        auto_extract_user_info (bool): Whether to automatically extract user information
        extraction_model (Optional[Model]): Model used for information extraction
        is_multi_user (bool): Whether multi-user mode is enabled
        mcp_service (MCPService): Service for managing Model Context Protocol servers
        request_timeout (int): Default timeout for MCP requests in seconds
        user_api_key (str): API key for user-level access
        admin_api_key (str): API key for admin-level access
        formation_config (Dict[str, Any]): Formation configuration including A2A settings
        external_registry_client (Optional[A2ARegistryClient]): Client for external A2A registries
        formation_server (Optional[A2AFormationServer]): Server for A2A formation

        # Enhanced workflow attributes
        enable_workflow_by_default (bool): Whether to enable workflow mode by default
        complexity_threshold (float): Complexity threshold for triggering workflows
        request_analyzer (RequestAnalyzer): Analyzes requests for complexity and decomposition
        task_decomposer (TaskDecomposer): Decomposes complex requests into workflows
        workflow_executor (WorkflowExecutor): Executes multi-agent workflows
        approval_manager (ApprovalManager): Manages plan approval workflows
        progress_tracker (ProgressTracker): Tracks workflow execution progress
        persona_manager (PersonaManager): Manages dynamic persona adaptation
        active_workflows (Dict[str, Workflow]): Currently executing workflows
        pending_approvals (Dict[str, Workflow]): Workflows awaiting user approval
    """

    def __init__(
        self,
        buffer_memory: Optional[ShortTermMemory] = None,
        long_term_memory: Optional[Union[LongTermMemory, Memobase]] = None,
        auto_extract_user_info: bool = True,
        extraction_model: Optional[LLM] = None,
        request_timeout: int = 60,
        user_api_key: Optional[str] = None,
        admin_api_key: Optional[str] = None,
        formation_config: Optional[Dict[str, Any]] = None,
        formation_path: Optional[str] = None,
        # Enhanced workflow parameters
        enable_workflow_by_default: bool = False,
        complexity_threshold: float = 7.0,
    ):
        """
        Initialize the overlord with optional centralized memory systems and enhanced workflow
        capabilities.

        The constructor sets up the Overlord with the specified memory systems and
        configuration. It initializes agent storage, memory systems, extraction settings,
        and API keys. If memory systems are not provided, the Overlord will still
        function but with limited memory capabilities.

        Args:
            buffer_memory: Optional buffer memory for short-term context across all agents.
                This memory system stores recent messages and provides context for ongoing
                conversations.
            long_term_memory: Optional long-term memory for persistent storage across all agents.
                This can be either a LongTermMemory (for basic vector storage) or a Memobase
                (for multi-user support with structured knowledge).
            auto_extract_user_info: Whether to automatically extract user information from
                conversations. When enabled, the system will analyze conversations to identify
                and store user preferences, facts, and other relevant information.
            extraction_model: Optional model to use for automatic information extraction.
                If not provided but auto_extract_user_info is True, a default model will be used.
            request_timeout: Default timeout in seconds for MCP server requests. This controls
                how long to wait for external tools to respond before timing out.
            user_api_key: Optional API key for user-level access. If not provided, a random
                key will be generated.
            admin_api_key: Optional API key for admin-level access. If not provided, a random
                key will be generated.
            formation_config: Optional formation configuration dict containing A2A settings
                and other configuration. Used to initialize external registry client.
            formation_path: Optional path to formation configuration for secrets management.
            enable_workflow_by_default: Whether to enable intelligent workflow orchestration
                by default for complex requests. When False, traditional agent routing is used
                unless explicitly overridden.
            complexity_threshold: Complexity threshold (1-10 scale) for automatically triggering
                workflow orchestration. Requests scoring above this threshold will be decomposed
                into multi-agent workflows.
        """
        # Initialize agent storage
        self.agents: Dict[str, Agent] = {}
        self.agent_descriptions: Dict[str, str] = {}  # Legacy compatibility
        self.agent_metadata: Dict[str, Dict[str, Any]] = {}  # Enhanced metadata

        self._routing_cache: Dict[str, str] = {}  # Cache for message routing decisions

        # ENHANCE existing initialization instead of adding separate service
        self._user_id_cache = {}  # Add to existing overlord caching

        # Store formation configuration for A2A and other features
        self.formation_config = formation_config or {}

        # Set formation_id for unified response format
        self.formation_id = self.formation_config.get("formation_id", "default-formation")

        # Initialize SecretsManager if formation_path is provided
        self.secrets_manager: Optional[SecretsManager] = None
        if formation_path:
            self.secrets_manager = SecretsManager(formation_path)

        # Store centralized memory systems
        self.buffer_memory = buffer_memory
        self.long_term_memory = long_term_memory

        # Configure extraction settings
        self.auto_extract_user_info = auto_extract_user_info
        self.extraction_model = extraction_model
        self.memory_extractor = None

        # Track message counts per user for extraction
        self.message_counts = {}  # Maps user_id to message count for throttling extraction

        # Initialize clarification configuration with defaults
        from ..clarification.types import ClarificationConfig, QuestionStyle

        self.clarification_config = ClarificationConfig(
            max_questions=5, style=QuestionStyle.CONVERSATIONAL, persist_learned_info=False
        )

        # Initialize external registry clients (will be set up later)
        # For discovery (outbound)
        self.external_registry_client: Optional[A2ARegistryClient] = None
        # For registration (inbound)
        self.inbound_registry_client: Optional[A2ARegistryClient] = None

        # Initialize A2A Formation Server (will be set up based on config)
        self.formation_server: Optional[A2AFormationServer] = None

        # Initialize external registries if configured in formation
        # Initialize external registry clients for inbound/outbound
        self._initialize_external_registry_client()
        self._initialize_inbound_registry_client()

        # Initialize agent tracking for delayed external registration
        self.pending_external_registrations = set()

        # Initialize the A2A Formation Server
        self._initialize_formation_server()

        # Note: Outbound services will be initialized asynchronously when needed

        # Determine if we're in multi-user mode based on memory type
        self.is_multi_user = False
        if isinstance(self.long_term_memory, Memobase):
            self.is_multi_user = True

            # Initialize memory extractor if we have a Memobase and auto-extract is enabled
            if self.auto_extract_user_info:
                try:
                    # Dynamically import to avoid circular dependencies
                    from ..memory.extractor import MemoryExtractor

                    self.memory_extractor = MemoryExtractor(
                        overlord=self,
                        extraction_model=self.extraction_model,
                        auto_extract=self.auto_extract_user_info,
                    )
                    #  Info - add observability event
                    #     "Initialized MemoryExtractor for automatic user information extraction"
                    # )
                except ImportError:
                    # Log warning but continue if extractor can't be imported
                    #  Warning - add observability event
                    #     "Could not import MemoryExtractor, automatic extraction disabled"
                    # )
                    self.auto_extract_user_info = False

        # Get/Initialize the MCP service
        self.mcp_service = MCPService.get_instance()

        # Note: Routing model will be initialized in start() method (async)

        # Set request timeout
        self.request_timeout = request_timeout

        # Set or generate API keys
        self.user_api_key = user_api_key
        self.admin_api_key = admin_api_key

        # Generate API keys if not provided
        if self.user_api_key is None:
            self.user_api_key = self._generate_api_key("user")
            self._user_key_auto_generated = True
        else:
            self._user_key_auto_generated = False

        if self.admin_api_key is None:
            self.admin_api_key = self._generate_api_key("admin")
            self._admin_key_auto_generated = True
        else:
            self._admin_key_auto_generated = False

        # Add expertise registry
        self._agent_expertise: Dict[str, Dict[str, Any]] = {}

        # Initialize model cache and capability models for LLM config
        self._model_cache: Dict[str, LLM] = {}
        self._capability_models: Dict[str, str] = {}

        # Load default persona from file
        self._load_default_persona()

        # Initialize enhanced workflow capabilities
        self.enable_workflow_by_default = enable_workflow_by_default
        self.complexity_threshold = complexity_threshold

        # Initialize workflow components
        self.request_analyzer = RequestAnalyzer(llm=extraction_model)
        self.request_analyzer.complexity_threshold = complexity_threshold

        self.task_decomposer = TaskDecomposer(llm=extraction_model)
        self.workflow_executor = WorkflowExecutor(agent_registry=self.agents)
        self.approval_manager = ApprovalManager()
        self.progress_tracker = ProgressTracker()

        # NEW: Initialize multimodal and synthesis components
        self.multimodal_fusion_engine = MultiModalFusionEngine(llm=extraction_model)
        self.multimodal_integrator = MultiModalWorkflowIntegrator(
            fusion_engine=self.multimodal_fusion_engine
        )
        self.quality_assessor = ResponseQualityAssessor(llm=extraction_model)
        self.response_synthesizer = AdvancedResponseSynthesizer(
            llm=extraction_model, quality_assessor=self.quality_assessor
        )

        # NEW: Initialize interactive elements and enhanced multimodal integration
        self.interactive_generator = InteractiveElementGenerator()
        self.response_formatter = ResponseFormatter(self.interactive_generator)
        self.media_integrator = MediaIntegrator()

        # Enhanced multimodal processors
        self.workflow_multimodal_processor = WorkflowMultiModalProcessor(
            fusion_engine=self.multimodal_fusion_engine
        )
        self.task_input_processor = TaskInputProcessor(fusion_engine=self.multimodal_fusion_engine)
        self.task_output_processor = TaskOutputProcessor(
            fusion_engine=self.multimodal_fusion_engine
        )

        # NEW: Initialize intelligent caching system
        self.cache_manager = IntelligentCacheManager(
            enable_analytics=True,
            enable_memory_optimization=True,
            embedding_service=self.extraction_model,  # Use extraction model for embeddings
        )

        # NEW: Initialize parallel workflow optimizer
        self.parallel_optimizer = ParallelWorkflowOptimizer(sensitivity_threshold=0.5)

        # NEW: Initialize Phase 3 User Experience Intelligence components
        self.user_preference_engine = UserPreferenceEngine(overlord=self)
        self.adaptive_response_generator = AdaptiveResponseGenerator(overlord=self)

        # NEW: Initialize Phase 4.1 resilience components
        resilience_config = ResilienceConfig(**self.formation_config.get("resilience", {}))
        self.resilient_workflow_manager = ResilientWorkflowManager(resilience_config)

        # Active workflows tracking
        self.active_workflows: Dict[str, Workflow] = {}
        self.pending_approvals: Dict[str, Workflow] = {}

        # Setup progress tracking
        self.workflow_executor.add_progress_callback(self.progress_tracker.update_workflow_progress)

        # NEW: Initialize document processing components (Tasks 3.7-3.9)
        # These will be properly initialized after _apply_formation_config() is called
        self.document_chunker: Optional[DocumentChunkManager] = None
        self.document_metadata_store: Optional[DocumentMetadataStore] = None
        self.document_reference_system: Optional[DocumentReferenceSystem] = None
        self.document_acknowledger: Optional[DocumentAcknowledgmentGenerator] = None
        self.document_summarizer: Optional[DocumentSummarizer] = None
        self.document_error_handler: Optional[DocumentErrorHandler] = None
        self.document_workflow_integrator: Optional[DocumentWorkflowIntegrator] = None
        self.document_cross_referencer: Optional[DocumentCrossReferenceManager] = None
        self.document_context_preserver: Optional[DocumentContextPreserver] = None

        # NEW: Initialize async request-response components (Task 4)
        self.request_tracker = RequestTracker()
        async_config = self.formation_config.get("async", {})
        self.webhook_manager = WebhookManager(
            default_retries=async_config.get("webhook_retries", 3),
            default_timeout=async_config.get("webhook_timeout", 10),
        )
        self.time_estimator = TimeEstimator(self.request_analyzer)

        # Async configuration
        self.async_threshold_seconds = async_config.get("threshold_seconds", 30)
        self.async_enable_estimation = async_config.get("enable_estimation", True)
        self.async_webhook_url = async_config.get("webhook_url")

        #  Info - add observability event
        #     "Enhanced Overlord initialized with workflow capabilities and async orchestration"
        # )

    async def start(self) -> None:
        """Start all overlord services including cache manager."""
        try:
            # Initialize the routing model (async)
            await self._initialize_routing_model()

            # Start cache manager
            if hasattr(self, "cache_manager") and self.cache_manager:
                await self.cache_manager.start()
                #  Cache manager startup - add observability event

            # Start observability system
            self.observability_manager = observability.ObservabilityManager.get_instance()
            await self.observability_manager.start()
            #  Observability startup - add observability event

            # Initialize other services if needed
            self._initialize_external_registry_client()
            self._initialize_inbound_registry_client()
            self._initialize_formation_server()

            #  Overlord services startup - add observability event
        except Exception as e:
            #  Overlord startup error - add observability event
            _ = e  # remove this after implementing observability
            raise

    def _load_default_persona(self) -> None:
        """Load the default persona from the system_persona.md file."""
        try:
            # Get the path to the system_persona.md file relative to this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            persona_path = os.path.join(current_dir, "utils", "system_persona.md")

            if os.path.exists(persona_path):
                with open(persona_path, "r", encoding="utf-8") as f:
                    self._default_persona = f.read().strip()
                #  Persona loading debug - add observability event
            else:
                # Fallback if file doesn't exist
                fallback = "You are a friendly and helpful assistant."
                self._default_persona = fallback
                msg = f"Persona file not found at {persona_path}, using fallback"
                #  Warning - add observability event
                _ = msg  # remove this after implementing observability

        except Exception as e:
            # Fallback if there's an error reading the file
            fallback = "You are a friendly and helpful assistant."
            self._default_persona = fallback
            #  Loading error - add observability event
            _ = e  # remove this after implementing observability

    def _create_overlord_system_message(self, persona: Optional[str] = None) -> str:
        """
        Create the complete system message by combining technical orchestration
        instructions with the persona.

        Args:
            persona: Optional persona text. If None, uses default persona.

        Returns:
            Complete system message with technical instructions prepended to persona.
        """
        # Load technical orchestration instructions from system_message.md
        current_dir = os.path.dirname(os.path.abspath(__file__))
        system_message_path = os.path.join(current_dir, "utils", "system_message.md")

        system_message = ""
        try:
            if os.path.exists(system_message_path):
                with open(system_message_path, "r", encoding="utf-8") as f:
                    system_message = f.read().strip()
        except Exception as e:
            #  Loading error - add observability event
            _ = e  # remove this after implementing observability
            # Fallback technical instructions
            system_message = (
                "You are the system overlord. You are responsible for routing messages "
                "to the appropriate agents and maintaining conversation coherence."
            )
        system_message += f"\n\nAlways try to use {self.response_format} in responses."

        # Use provided persona or default
        if persona is None:
            persona = getattr(self, "_default_persona", "You are a friendly and helpful assistant.")

        # Combine technical instructions with persona
        return (
            f"<system-message>\n{system_message}\n</system-message>\n\n"
            f"<persona>\n{persona}\n</persona>"
        )

    async def load_formation_from_path(self, formation_path: str) -> Dict[str, Any]:
        """
        Load formation configuration from a file or directory path.

        This method loads a formation configuration using the FormationLoader
        and applies it to the overlord. It supports both flattened formation files
        and modular formation directories.

        Args:
            formation_path: Path to formation file or directory to load

        Returns:
            Dict[str, Any]: The loaded formation configuration

        Raises:
            ValueError: If loading fails or validation errors are found
        """
        try:
            # Emit formation loading started event
            observability.emit_event(
                event_type=observability.SystemEvents.OVERLORD_INITIALIZING,
                level=observability.EventLevel.INFO,
                data={"formation_path": formation_path},
                description=f"Starting formation loading from {formation_path}",
            )

            # Import FormationLoader and validation when needed
            from ..config.formation_loader import FormationLoader
            from ..config.validation import validate_formation

            # Validate formation before loading
            #  Formation validation - add observability event
            validation_result = validate_formation(formation_path, self.secrets_manager)

            if not validation_result.is_valid:
                error_msg = (
                    f"Formation validation failed:\n" f"{validation_result.detailed_report()}"
                )
                #  Error - add observability event
                raise ValueError(error_msg)

            # Log warnings if any
            if validation_result.warnings:
                #  Warning - add observability event
                _ = None  # remove this after implementing observability
                #     f"Formation validation warnings:\n" f"{validation_result.detailed_report()}"
                # )

            # Load formation configuration
            formation_loader = FormationLoader()
            formation_config = await formation_loader.load(formation_path, self.secrets_manager)

            # Update overlord's formation config
            self.formation_config = formation_config

            #  Formation loaded - add observability event

            # Apply configuration to overlord
            await self._apply_formation_config()

            # Emit formation loading completed event
            observability.emit_event(
                event_type=observability.SystemEvents.OVERLORD_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation_id": formation_config.get("id", "unnamed"),
                    "formation_path": formation_path,
                    "agents_count": len(formation_config.get("agents", [])),
                    "mcp_servers_count": len(formation_config.get("mcp", {}).get("servers", [])),
                },
                description=(
                    f"Formation loading completed: {formation_config.get('id', 'unnamed')}"
                ),
            )

            return formation_config

        except Exception as e:
            #  Formation loading error - add observability event

            # Emit formation loading failed event
            observability.emit_event(
                event_type=observability.ErrorEvents.TIMEOUT_DETECTED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation_path": formation_path,
                    "error": str(e),
                },
                description=f"Formation loading failed: {e}",
            )

            raise

    async def validate_formation(self, formation_path: str) -> Dict[str, Any]:
        """
        Validate a formation configuration without loading it.

        Args:
            formation_path: Path to formation file or directory to validate

        Returns:
            Dict[str, Any]: Validation results with 'is_valid', 'errors', 'warnings', 'suggestions'
        """
        try:
            from ..config.validation import validate_formation

            validation_result = validate_formation(formation_path, self.secrets_manager)

            return {
                "is_valid": validation_result.is_valid,
                "errors": validation_result.errors,
                "warnings": validation_result.warnings,
                "suggestions": validation_result.suggestions,
                "summary": validation_result.summary(),
                "detailed_report": validation_result.detailed_report(),
            }

        except Exception as e:
            #  Formation validation error - add observability event
            return {
                "is_valid": False,
                "errors": [str(e)],
                "warnings": [],
                "suggestions": [],
                "summary": f"❌ Validation failed: {str(e)}",
                "detailed_report": f"Validation failed with exception: {str(e)}",
            }

    async def _apply_formation_config(self) -> None:
        """
        Apply the loaded formation configuration to the overlord.

        This method processes the formation configuration and applies relevant
        settings to the overlord, such as creating agents, registering MCP servers,
        and configuring A2A services.
        """
        config = self.formation_config

        # Initialize LLM configuration and model resolver
        await self._initialize_llm_config()

        # Initialize auth configuration
        await self._initialize_auth_config()

        # Initialize memory configuration
        await self._initialize_memory_config()

        # Initialize logging configuration
        await self._initialize_logging_config()

        # Initialize clarification configuration
        await self._initialize_clarification_config()

        # Initialize document processing configuration
        await self._initialize_document_processing_config()

        # Initialize document processing components
        await self._initialize_document_components()

        # Create agents from configuration
        agents_config = config.get("agents", [])
        for agent_config in agents_config:
            try:
                # Check if agent is active (default to True)
                agent_id = agent_config.get("id", "unknown")
                is_active = agent_config.get("active", True)

                if is_active:
                    await self._create_agent_from_config(agent_config)
                    #  Agent loaded - add observability event
                else:
                    #  Agent disabled - add observability event
                    _ = agent_id  # remove this after implementing observability
            except Exception as e:
                #  Agent creation error - add observability event
                _ = e  # remove this after implementing observability
                continue

        # Register MCP servers from configuration
        mcp_config = config.get("mcp", {})
        servers = mcp_config.get("servers", [])
        for server_config in servers:
            try:
                await self._register_mcp_server_from_config(server_config)
            except Exception as e:
                #  MCP registration error - add observability event
                _ = e  # remove this after implementing observability
                continue

        # Apply A2A configuration
        a2a_config = config.get("a2a", {})
        if a2a_config:
            try:
                await self._apply_a2a_config(a2a_config)
            except Exception as e:
                #  A2A config error - add observability event
                _ = e  # remove this after implementing observability

        #  Formation config applied - add observability event

    async def _initialize_llm_config(self) -> None:
        """
        Initialize LLM configuration from formation config.

        This processes the new capability-based LLM schema and sets up model
        resolution for different capabilities like text, vision, transcription, etc.
        """
        llm_config = self.formation_config.get("llm", {})

        # Initialize model cache for capability-based resolution
        self._model_cache = {}
        self._capability_models = {}

        # Process models by capability
        models_config = llm_config.get("models", [])
        for model_config in models_config:
            for capability, model_name in model_config.items():
                if capability in ["api_key", "settings"]:
                    continue  # Skip metadata

                self._capability_models[capability] = {
                    "model": model_name,
                    "api_key": model_config.get("api_key"),
                    "settings": model_config.get("settings", {}),
                }

        # Store global settings and api_keys for later use
        self._global_llm_settings = llm_config.get("settings", {})
        self._global_api_keys = llm_config.get("api_keys", {})

        capabilities = list(self._capability_models.keys())
        #  LLM config initialized - add observability event
        _ = capabilities  # remove this after implementing observability

    async def _initialize_auth_config(self) -> None:
        """
        Initialize auth configuration from formation config.

        This processes the auth.api_keys structure and updates the overlord's
        API keys if they are provided in the formation config.
        """
        auth_config = self.formation_config.get("auth", {})
        auth_api_keys = auth_config.get("api_keys", {})

        # Update admin and user API keys from formation config if provided
        if "admin_key" in auth_api_keys:
            admin_key = auth_api_keys["admin_key"]
            # Interpolate secrets if needed
            if admin_key and "${{ secrets." in admin_key:
                try:
                    interpolated_config = await self.interpolate_secrets({"admin_key": admin_key})
                    admin_key = interpolated_config.get("admin_key", admin_key)
                except Exception as e:
                    #  Secret interpolation warning - add observability event
                    _ = e  # remove this after implementing observability

            self.admin_api_key = admin_key
            #  Admin API key updated - add observability event

        if "user_key" in auth_api_keys:
            user_key = auth_api_keys["user_key"]
            # Interpolate secrets if needed
            if user_key and "${{ secrets." in user_key:
                try:
                    interpolated_config = await self.interpolate_secrets({"user_key": user_key})
                    user_key = interpolated_config.get("user_key", user_key)
                except Exception as e:
                    #  Secret interpolation warning - add observability event
                    _ = e  # remove this after implementing observability

            self.user_api_key = user_key
            #  User API key updated - add observability event

        if auth_api_keys:
            #  Auth config initialized - add observability event
            _ = None  # remove this after implementing observability

    async def _initialize_memory_config(self) -> None:
        """
        Initialize memory configuration from formation config.

        This processes the memory.working and memory.persistent configuration
        and initializes or updates the overlord's memory systems according
        to the new schema specifications.
        """
        memory_config = self.formation_config.get("memory", {})

        if not memory_config:
            #  Config debug - add observability event
            return

        # Initialize buffer memory configuration
        # (moved from working.buffer to top-level)
        buffer_config = memory_config.get("buffer", {})
        if buffer_config and not self.buffer_memory:
            await self._initialize_buffer_memory(buffer_config)

        # Initialize persistent memory configuration
        persistent_config = memory_config.get("persistent", {})
        if persistent_config and not self.long_term_memory:
            await self._initialize_persistent_memory(persistent_config)

        # Handle legacy short_term configuration with warning
        if "short_term" in memory_config:
            _ = None  # remove this after implementing observability
            #  Warning - add observability event
            #     "Legacy memory.short_term configuration detected. "
            #     "Please migrate to memory.working and memory.buffer structure."
            # )

        # Handle legacy long_term configuration with warning
        if "long_term" in memory_config:
            _ = None  # remove this after implementing observability
            #  Warning - add observability event
            #     "Legacy memory.long_term configuration detected. "
            #     "Please migrate to memory.persistent structure."
            # )

        if memory_config:
            #  Memory config initialized - add observability event
            _ = None  # remove this after implementing observability

    async def _initialize_logging_config(self) -> None:
        """
        Initialize logging configuration from formation config.

        This processes the multi-stream logging configuration and configures
        the logging system for the formation.
        """
        logging_config = self.formation_config.get("logging", {})

        if not logging_config:
            #  Config debug - add observability event
            return

        try:
            # Extract global logging settings
            enabled = logging_config.get("enabled", True)
            streams = logging_config.get("streams", [])

            # Only configure logging if enabled
            if not enabled:
                #  Logging config disabled - add observability event
                return

            if not streams:
                #  Logging config warning - add observability event
                return

            # Process each stream
            processed_streams = []
            for i, stream in enumerate(streams):
                try:
                    processed_stream = await self._process_logging_stream(stream, i)
                    if processed_stream:
                        processed_streams.append(processed_stream)
                except Exception as e:
                    #  Logging stream error - add observability event
                    _ = e  # remove this after implementing observability
                    continue

            # Store processed logging configuration
            self._logging_config = {"enabled": enabled, "streams": processed_streams}

            #  Info - add observability event
            #     f"✅ Initialized logging configuration "
            #     f"(enabled={enabled}, streams={len(processed_streams)})"
            # )

        except Exception as e:
            #  Logging init error - add observability event
            _ = e  # remove this after implementing observability

    async def _process_logging_stream(
        self, stream: Dict[str, Any], index: int
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single logging stream configuration.

        Args:
            stream: Stream configuration dictionary
            index: Stream index for error reporting

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
            #  Logging stream config error - add observability event
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
                #  Logging stream config error - add observability event
                return None
            processed_stream["destination"] = destination

        elif transport == "stream":
            destination = stream.get("destination")
            protocol = stream.get("protocol")

            if not destination:
                #  Logging stream config error - add observability event
                return None

            # Auto-detect protocol if not specified
            if not protocol:
                protocol = self._detect_stream_protocol(destination)

            processed_stream["destination"] = destination
            processed_stream["protocol"] = protocol

        elif transport == "trail":
            # MUXI Trail transport - special case with fixed destination
            processed_stream["destination"] = "tcps://trail.muxi.ai/ingest"
            processed_stream["protocol"] = "zmq"
            processed_stream["format"] = "msgpack"  # Trail always uses msgpack

            # Ensure auth is configured for trail
            if not auth:
                #  Error - add observability event
                return None

        else:
            #  Unsupported transport error - add observability event
            return None

        # Interpolate secrets in auth if needed
        if auth:
            try:
                interpolated_auth = await self.interpolate_secrets(auth)
                processed_stream["auth"] = interpolated_auth
            except Exception as e:
                #  Secret interpolation warning - add observability event
                _ = e  # remove this after implementing observability

        return processed_stream

    def _detect_stream_protocol(self, destination: str) -> str:
        """
        Detect stream protocol from destination URL.

        Args:
            destination: Stream destination URL

        Returns:
            Detected protocol string
        """
        if destination.startswith(("https://", "http://")):
            return "webhook"
        elif destination.startswith(("tcp://", "tcps://", "ipc://", "ipcs://")):
            return "zmq"
        elif destination.startswith(("ws://", "wss://")):
            return "websocket"
        else:
            return "zmq"  # Default fallback

    def _convert_logging_format(self, schema_format: str) -> str:
        """
        Convert SCHEMA_GUIDE.md logging format to LoggingConfig format.

        Args:
            schema_format: Format from SCHEMA_GUIDE.md ('jsonl' or 'text')

        Returns:
            Format string for LoggingConfig
        """
        if schema_format == "jsonl":
            return "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
        elif schema_format == "text":
            return "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
        else:
            # Default format
            return "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"

    async def _initialize_clarification_config(self) -> None:
        """
        Initialize clarification configuration from formation config.

        This processes the overlord.clarification configuration for intelligent
        parameter collection and applies privacy-by-default settings with
        industry-standard style preferences.
        """
        overlord_config = self.formation_config.get("overlord", {})
        clarification_config = overlord_config.get("clarification", {})

        if not clarification_config:
            #  Config debug - add observability event
            return

        try:
            from ..clarification.types import ClarificationConfig, QuestionStyle

            # Extract configuration with privacy-by-default approach
            max_questions = clarification_config.get("max_questions", 5)
            style_str = clarification_config.get("style", "conversational")
            persist_learned_info = clarification_config.get("persist_learned_info", False)

            # Validate and convert style string to enum
            try:
                style = QuestionStyle(style_str.lower())
            except ValueError:
                #  Warning - add observability event
                #     f"Invalid clarification style '{style_str}', defaulting to conversational"
                # )
                style = QuestionStyle.CONVERSATIONAL

            # Validate max_questions
            if not isinstance(max_questions, int) or max_questions < 1:
                #  Invalid config warning - add observability event
                max_questions = 5
            elif max_questions > 20:
                _ = None  # remove this after implementing observability
                #  Warning - add observability event
                #   f"max_questions '{max_questions}' is very high, consider reducing for better UX"
                # )

            # Update the overlord's clarification configuration
            self.clarification_config = ClarificationConfig(
                max_questions=max_questions, style=style, persist_learned_info=persist_learned_info
            )

            #  Info - add observability event
            #     f"✅ Initialized clarification configuration "
            #     f"(max_questions={max_questions}, style={style.value}, "
            #     f"persist_learned_info={persist_learned_info})"
            # )

        except Exception as e:
            #  Clarification init error - add observability event
            # Keep default configuration on error
            #  Default clarification config - add observability event
            _ = e  # remove this after implementing observability

        if clarification_config:
            #  Clarification config - add observability event
            _ = None  # remove this after implementing observability

    async def _initialize_document_processing_config(self) -> None:
        """
        Initialize document processing configuration from LLM models in formation config.

        This processes the unified document configuration from llm.models.documents.settings
        for use by document-related components.
        """
        try:
            # Import the document processing config module
            from ..config.document_processing import DocumentProcessingConfig

            # Extract LLM configuration from formation
            llm_config = self.formation_config.get("llm", {})

            # Create document processing configuration instance using unified schema
            self.document_processing_config = DocumentProcessingConfig(llm_config)

            # Log the configuration details
            enabled = self.document_processing_config.is_enabled()
            if enabled:
                chunk_size = self.document_processing_config.get_chunk_size()
                max_file_size = self.document_processing_config.get_max_file_size_mb()
                strategy = self.document_processing_config.get_extraction_strategy()

                #  Info - add observability event
                #     f"✅ Initialized document processing configuration "
                #     f"(enabled={enabled}, chunk_size={chunk_size}, "
                #     f"max_file_size={max_file_size}MB, strategy={strategy})"
                # )
            else:
                #  Document processing config - add observability event
                _ = None  # remove this after implementing observability

        except Exception as e:
            #  Document processing init error - add observability event
            _ = e  # remove this after implementing observability

            # Fall back to default configuration
            from ..config.document_processing import DocumentProcessingConfig

            self.document_processing_config = DocumentProcessingConfig({})

    async def _initialize_document_components(self) -> None:
        """
        Initialize document processing components based on configuration.

        This initializes all document processing components from Tasks 3.7-3.9:
        - Document Storage Foundation (3.7)
        - Document User Experience (3.8)
        - Document Workflow Integration (3.9)
        """
        try:
            # Only initialize if document processing is enabled
            if (
                not hasattr(self, "document_processing_config")
                or not self.document_processing_config.is_enabled()
            ):
                #  Document processing disabled - add observability event
                return

            #  Document processing init - add observability event

            # Subtask 3.7: Document Storage Foundation Layer
            self.document_chunker = DocumentChunkManager()
            self.document_metadata_store = DocumentMetadataStore()
            self.document_reference_system = DocumentReferenceSystem()

            # Subtask 3.8: Document User Experience Layer
            # Get the persona manager for acknowledgments
            persona_manager = getattr(self, "persona_manager", None)
            self.document_acknowledger = DocumentAcknowledgmentGenerator(persona_manager)
            self.document_summarizer = DocumentSummarizer()
            self.document_error_handler = DocumentErrorHandler()

            # Subtask 3.9: Document Workflow Integration Layer
            workflow_manager = getattr(self, "workflow_executor", None)
            self.document_workflow_integrator = DocumentWorkflowIntegrator(workflow_manager)
            self.document_cross_referencer = DocumentCrossReferenceManager()
            self.document_context_preserver = DocumentContextPreserver()

            #  Document processing components ready - add observability event

        except Exception as e:
            #  Document processing init error - add observability event
            _ = e  # remove this after implementing observability
            # Set all components to None on failure
            self.document_chunker = None
            self.document_metadata_store = None
            self.document_reference_system = None
            self.document_acknowledger = None
            self.document_summarizer = None
            self.document_error_handler = None
            self.document_workflow_integrator = None
            self.document_cross_referencer = None
            self.document_context_preserver = None

    async def _initialize_buffer_memory(self, buffer_config: Dict[str, Any]) -> None:
        """Initialize buffer memory from configuration."""
        try:
            from ..memory.short_term import ShortTermMemory

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
                    embedding_model = await self.get_model_for_capability("embedding")
                except Exception as e:
                    #  Model creation warning - add observability event
                    _ = e  # remove this after implementing observability
                    vector_search = False

            # Create buffer memory instance
            self.buffer_memory = ShortTermMemory(
                max_size=size,
                buffer_multiplier=multiplier,
                dimension=dimension,
                model=embedding_model,
                mode=mode,
                remote=remote_config if mode == "remote" else None,
            )

            #  Info - add observability event
            #     f"✅ Initialized buffer memory (size={size}, multiplier={multiplier}, "
            #     f"vector_search={vector_search}, mode={mode})"
            # )

        except Exception as e:
            #  Buffer memory init error - add observability event
            _ = e  # remove this after implementing observability

    async def _initialize_persistent_memory(self, persistent_config: Dict[str, Any]) -> None:
        """Initialize persistent memory from configuration."""
        try:
            connection_string = persistent_config.get("connection_string")
            embedding_model_name = persistent_config.get("embedding_model")

            if not connection_string:
                #  Connection string warning - add observability event
                return

            # Interpolate secrets in connection string if needed
            if "${{ secrets." in connection_string:
                try:
                    interpolated = await self.interpolate_secrets(
                        {"connection_string": connection_string}
                    )
                    connection_string = interpolated.get("connection_string", connection_string)
                except Exception as e:
                    #  Error - add observability event
                    _ = e  # remove this after implementing observability
                    return

            # Get embedding model
            embedding_model = None
            if embedding_model_name:
                try:
                    # Create model from specific name override
                    embedding_model = await self.create_model(model=embedding_model_name)
                except Exception as e:
                    #  Model creation warning - add observability event
                    _ = e  # remove this after implementing observability
                    try:
                        # Fall back to default embedding capability
                        embedding_model = await self.get_model_for_capability("embedding")
                    except Exception as e2:
                        #  Model creation warning - add observability event
                        _ = e2  # remove this after implementing observability

            # Determine memory type based on connection string
            if connection_string.startswith("postgresql://") or connection_string.startswith(
                "postgres://"
            ):
                from ..memory.memobase import Memobase

                self.long_term_memory = Memobase(
                    connection_string=connection_string, model=embedding_model
                )
                #  PostgreSQL memory initialized - add observability event
            elif connection_string.startswith("sqlite://") or connection_string.endswith(".db"):
                from ..memory.sqlite import SQLiteMemory

                # Remove sqlite:// prefix if present
                db_path = connection_string.replace("sqlite://", "")
                self.long_term_memory = SQLiteMemory(db_path=db_path)

                # Set the embedding provider after initialization
                if embedding_model:
                    try:
                        embedding_llm = await self.get_model_for_capability("embedding")
                        self.long_term_memory.embedding_provider = embedding_llm
                    except Exception as e:
                        #  Warning - add observability event
                        _ = e  # remove this after implementing observability
                        #     f"Could not set embedding provider for long-term memory: {e}"
                        # )

                #  SQLite memory initialized - add observability event
            else:
                #  Connection string format error - add observability event
                _ = None  # remove this after implementing observability

        except Exception as e:
            #  Persistent memory init error - add observability event
            _ = e  # remove this after implementing observability

    async def get_model_for_capability(
        self, capability: str, agent_id: Optional[str] = None
    ) -> LLM:
        """
        Get a model for a specific capability with optional agent override.

        This method implements the capability-based model resolution described in the schema:
        1. Check for agent-specific model override
        2. Fall back to formation default for that capability
        3. Fall back to text capability if capability not found
        4. Cache models to avoid repeated initialization

        Args:
            capability: The model capability needed (text, vision, transcription, etc.)
            agent_id: Optional agent ID for agent-specific overrides

        Returns:
            LLM instance for the specified capability

        Raises:
            ValueError: If no suitable model can be found
        """
        # Create cache key
        cache_key = f"{agent_id or 'default'}:{capability}"

        # Return cached model if available
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        model_config = None

        # Check for agent-specific model override
        if agent_id and hasattr(self, "agents") and agent_id in self.agents:
            agent = self.agents[agent_id]
            # Look for agent-specific model configuration
            # This would come from agent config in formation
            if hasattr(agent, "models") and capability in agent.models:
                model_config = agent.models[capability]

        # Fall back to formation default for this capability
        if not model_config and capability in self._capability_models:
            model_config = self._capability_models[capability]

        # Fall back to text capability if current capability not found
        if not model_config and capability != "text" and "text" in self._capability_models:
            model_config = self._capability_models["text"]
            #  Model fallback warning - add observability event

        # If still no model config, raise error
        if not model_config:
            raise ValueError(f"No model found for capability: {capability}")

        # Extract model configuration
        model_name = model_config["model"]
        api_key = model_config.get("api_key")
        model_settings = model_config.get("settings", {})

        # Apply global settings with model-specific overrides
        final_settings = {**self._global_llm_settings, **model_settings}

        # Resolve API key - model-specific > global > environment
        final_api_key = api_key
        if not final_api_key and "/" in model_name:
            provider = model_name.split("/")[0]
            final_api_key = self._global_api_keys.get(provider)

        # Interpolate secrets if needed
        if final_api_key and "${{ secrets." in final_api_key:
            try:
                interpolated_config = await self.interpolate_secrets({"api_key": final_api_key})
                final_api_key = interpolated_config.get("api_key", final_api_key)
            except Exception as e:
                #  Secret interpolation warning - add observability event
                _ = e  # remove this after implementing observability
        # Create model instance
        model = LLM(model=model_name, api_key=final_api_key, **final_settings)

        # Cache the model
        self._model_cache[cache_key] = model

        #  Model creation debug - add observability event
        return model

    async def _create_agent_from_config(self, agent_config: Dict[str, Any]) -> None:
        """
        Create an agent from configuration dict.

        Args:
            agent_config: Agent configuration dictionary
        """
        agent_id = agent_config.get("id")
        if not agent_id:
            #  Agent config missing error - add observability event
            return

        # Create model from configuration (support both new and legacy formats)
        if "llm_models" in agent_config:
            # New schema format
            llm_models = agent_config["llm_models"]
            if llm_models and len(llm_models) > 0:
                text_model = llm_models[0]  # Use first model for text capability
                model_name = text_model.get("text", "openai/gpt-4o-mini")
                settings = text_model.get("settings", {})
                model = await self.create_model(model=model_name, **settings)
            else:
                model = await self.create_model()
        else:
            # Legacy model format
            model_config = agent_config.get("model", {})
            model = await self.create_model(**model_config)

        # Extract other agent parameters
        system_message = agent_config.get("system_message")
        description = agent_config.get("description")
        name = agent_config.get("name", agent_id)
        role = agent_config.get("role")
        specialties = agent_config.get("specialties", [])

        # Create the agent
        agent = self.create_agent(
            agent_id=agent_id, model=model, system_message=system_message, description=description
        )

        # Set enhanced metadata attributes on the agent
        agent.name = name
        agent.role = role
        agent.specialties = specialties

        # Update the stored metadata with the correct values
        if agent_id in self.agent_metadata:
            self.agent_metadata[agent_id].update(
                {
                    "name": name,
                    "role": role,
                    "specialties": specialties,
                }
            )

        #  Agent created from config - add observability event
        _ = None  # remove this after implementing observability

    async def _register_mcp_server_from_config(self, server_config: Dict[str, Any]) -> None:
        """
        Register an MCP server from configuration dict.

        Args:
            server_config: MCP server configuration dictionary
        """
        server_id = server_config.get("id")
        if not server_id:
            #  MCP config missing error - add observability event
            return

        # Extract server parameters
        url = server_config.get("url")
        command = server_config.get("command")
        credentials = server_config.get("auth")

        # Register the MCP server
        await self.register_mcp_server(
            server_id=server_id, url=url, command=command, credentials=credentials
        )

        #  MCP server registered from config - add observability event

    async def _apply_a2a_config(self, a2a_config: Dict[str, Any]) -> None:
        """
        Apply A2A configuration.

        Args:
            a2a_config: A2A configuration dictionary
        """
        # Handle outbound configuration
        outbound_config = a2a_config.get("outbound", {})
        if outbound_config:
            services = outbound_config.get("services", [])
            for service_config in services:
                try:
                    # Apply outbound service configuration
                    service_id = service_config.get("id")
                    #  A2A service applied - add observability event
                except Exception as e:
                    #  A2A service error - add observability event
                    _ = e  # remove this after implementing observability

        #  A2A configuration applied - add observability event

    async def _initialize_routing_model(self):
        """Initialize the model used for agent routing decisions."""
        try:
            # Get overlord configuration from formation config
            overlord_config = self.formation_config.get("overlord", {})

            # Set custom persona if provided (with legacy support) - check at top level first
            overlord_persona = overlord_config.get("persona")
            if not overlord_persona:
                # Legacy support: fallback to system_message
                overlord_persona = overlord_config.get("system_message")

            if overlord_persona:
                self.routing_persona = overlord_persona
            else:
                self.routing_persona = None

            # Try new overlord.llm structure first
            llm_config = overlord_config.get("llm", {})
            if llm_config:
                # New overlord.llm config structure
                self.routing_model = await self.create_model(
                    model=llm_config.get("model", "openai/gpt-4o-mini"),
                    temperature=llm_config.get("settings", {}).get("temperature", 0.2),
                    max_tokens=llm_config.get("settings", {}).get("max_tokens", 2000),
                    api_key=llm_config.get("api_key"),
                )

                # Configure overlord behavior from overlord.config
                config_section = overlord_config.get("config", {})

                # Caching configuration
                caching_config = config_section.get("caching", {})
                self.routing_cache_enabled = caching_config.get("enabled", True)
                self.routing_cache_ttl = caching_config.get("ttl", 3600)

                # Additional configuration fields
                self.max_extraction_tokens = config_section.get("max_extraction_tokens", 500)
                self.max_tool_calls = config_section.get("max_tool_calls", -1)

                # Response configuration (required nested structure)
                response_config = config_section.get("response", {})
                self.response_format = response_config.get("format", "markdown")
                self.use_interactive_elements = response_config.get("interactive_elements", True)

                # Intelligence configuration
                self.learn_user_preference = config_section.get("learn_user_preference", True)
                self.adaptive_responses = config_section.get("adaptive_responses", True)

                # Resilience configuration
                self.circuit_breaker = config_section.get("circuit_breaker", True)
                self.error_recovery = config_section.get("error_recovery", True)

                # Workflow configuration
                self.auto_decomposition = config_section.get("auto_decomposition", True)
                self.plan_approval_threshold = config_section.get("plan_approval_threshold", 7)

                # Initialize cache expiry tracking if TTL is configured
                if self.routing_cache_ttl > 0:
                    self._routing_cache_expiry: Dict[str, float] = {}

            else:
                # Fall back to legacy overlord.routing structure for compatibility
                routing_data = overlord_config.get("routing", {})
                if routing_data:
                    self.routing_model = await self.create_model(
                        model=routing_data.get("model", "openai/gpt-4o-mini"),
                        temperature=routing_data.get("settings", {}).get("temperature", 0.2),
                        max_tokens=routing_data.get("settings", {}).get("max_tokens", 2000),
                        api_key=routing_data.get("api_key"),
                    )

                    # Legacy caching config
                    self.routing_cache_enabled = routing_data.get("use_caching", True)
                    self.routing_cache_ttl = routing_data.get("cache_ttl", 3600)
                    # Only override persona if not already set from top-level config
                    if not self.routing_persona:
                        self.routing_persona = routing_data.get("persona") or routing_data.get(
                            "system_message"
                        )

                    # Default values for overlord config
                    self.max_extraction_tokens = 500
                    self.max_tool_calls = -1
                    # Response config is now required - these are fallback defaults
                    self.response_format = "markdown"
                    self.use_interactive_elements = True
                    self.learn_user_preference = True
                    self.adaptive_responses = True
                    self.circuit_breaker = True
                    self.error_recovery = True
                    self.auto_decomposition = True
                    self.plan_approval_threshold = 7

                    # Initialize cache expiry tracking if TTL is configured
                    if self.routing_cache_ttl > 0:
                        self._routing_cache_expiry: Dict[str, float] = {}

                else:
                    # No overlord config - try to get text model from formation
                    try:
                        # Don't create a task, just set to None and handle later
                        self.routing_model = None
                        #  Routing model selection - add observability event
                    except Exception:
                        # Fall back to create_model with defaults
                        self.routing_model = await self.create_model()

                    # Default caching settings
                    self.routing_cache_enabled = True
                    self.routing_cache_ttl = 3600
                    # Only set to None if not already set from top-level config
                    if not hasattr(self, "routing_persona"):
                        self.routing_persona = None
                    self.max_extraction_tokens = 500
                    self.max_tool_calls = -1
                    self.response_format = "markdown"
                    self.use_interactive_elements = True
                    self.learn_user_preference = True
                    self.adaptive_responses = True
                    self.circuit_breaker = True
                    self.error_recovery = True
                    self.auto_decomposition = True
                    self.plan_approval_threshold = 7
                    self._routing_cache_expiry: Dict[str, float] = {}

            #  Info - add observability event
            #     f"✅ Initialized overlord routing with "
            #     f"cache_enabled={self.routing_cache_enabled}, "
            #     f"ttl={self.routing_cache_ttl}, "
            #     f"max_extraction_tokens={self.max_extraction_tokens}, "
            #     f"max_tool_calls={self.max_tool_calls}, "
            #     f"response_format={self.response_format}, "
            #     f"interactive_elements={self.use_interactive_elements}, "
            #     f"learn_user_preference={self.learn_user_preference}, "
            #     f"adaptive_responses={self.adaptive_responses}, "
            #     f"circuit_breaker={self.circuit_breaker}, "
            #     f"error_recovery={self.error_recovery}, "
            #     f"auto_decomposition={self.auto_decomposition}, "
            #     f"plan_approval_threshold={self.plan_approval_threshold}"
            # )

        except Exception as e:
            # If initialization fails, log error but continue (routing will fall back to default)
            #  Routing model init error - add observability event
            _ = e  # remove this after implementing observability
            self.routing_model = None
            self.routing_cache_enabled = True
            self.routing_cache_ttl = 3600
            # Only set to None if not already set from top-level config
            if not hasattr(self, "routing_persona"):
                self.routing_persona = None
            self.max_extraction_tokens = 500
            self.max_tool_calls = -1
            # Response config requires proper nested structure
            self.response_format = "markdown"
            self.use_interactive_elements = True
            self.learn_user_preference = True
            self.adaptive_responses = True
            self.circuit_breaker = True
            self.error_recovery = True
            self.auto_decomposition = True
            self.plan_approval_threshold = 7
            self._routing_cache_expiry: Dict[str, float] = {}

    async def create_model(
        self,
        model: str = "openai/gpt-4o",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLM:
        """
        Create a model instance using the unified Model class with secrets support.

        This method creates a model using the provider/model-name format and supports
        GitHub Actions-style secrets interpolation in the api_key parameter.
        It's the preferred way to create models for use with agents.

        Args:
            model: The model to use in "provider/model-name" format (e.g., "openai/gpt-4o").
                This format works across all supported providers.
            api_key: API key for the provider. Supports secrets interpolation with
                ${{ secrets.NAME }} syntax. If None, will attempt to use
                environment variables based on the provider.
            temperature: The temperature parameter for generation. Controls randomness
                where higher values produce more random outputs.
            max_tokens: Maximum tokens to generate in responses. If None, uses
                provider defaults.
            **kwargs: Additional parameters passed directly to the model.

        Returns:
            A Model instance ready to use with agents.
        """
        # Interpolate secrets in api_key if provided and contains secrets references
        final_api_key = api_key
        if api_key and "${{ secrets." in api_key:
            try:
                interpolated_config = await self.interpolate_secrets({"api_key": api_key})
                final_api_key = interpolated_config.get("api_key", api_key)
            except Exception as e:
                #  Secret interpolation warning - add observability event
                _ = e  # remove this after implementing observability
                # Continue with original api_key

        # Create and return a new model instance
        return LLM(
            model=model,
            api_key=final_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def create_agent(
        self,
        agent_id: str,
        model: LLM,
        system_message: Optional[str] = None,
        description: Optional[str] = None,
        request_timeout: Optional[int] = None,
        a2a_internal: bool = True,
        a2a_external: bool = True,
    ) -> Agent:
        """
        Create a new agent that uses the overlord's memory systems.

        This method creates a new agent instance with the specified configuration and registers
        it with the overlord. The created agent will have access to the overlord's
        centralized memory systems, enabling it to maintain context across conversations.

        Args:
            agent_id: Unique identifier for the agent. Must be unique among all registered agents.
                This ID is used for agent selection, routing, and in memory metadata.
            model: The language model to use for the agent. This model will process messages
                and generate responses for this specific agent.
            system_message: Optional system message to set agent's behavior and persona.
                This defines the agent's role, capabilities, and personality.
            description: Optional description of the agent's capabilities and purpose.
                Used for intelligent message routing to select the appropriate agent for
                specific queries. If not provided, falls back to system_message.

            request_timeout: Optional timeout in seconds for MCP requests.
                If not provided, defaults to the overlord's timeout setting.
            a2a_internal: Whether the agent participates in internal A2A communication.
            a2a_external: Whether the agent participates in external A2A communication.

        Returns:
            The created agent instance.

        Raises:
            ValueError: If an agent with the provided agent_id already exists.
        """
        if agent_id in self.agents:
            raise ValueError(f"Agent with ID '{agent_id}' already exists")

        # Create agent with reference to overlord for memory access
        agent = Agent(
            model=model,
            overlord=self,  # Pass reference to overlord
            system_message=system_message,
            agent_id=agent_id,
            request_timeout=request_timeout,  # Pass timeout parameter
            a2a_internal=a2a_internal,
            a2a_external=a2a_external,
        )

        # Add agent to overlord
        self.agents[agent_id] = agent
        self.agent_descriptions[agent_id] = description or system_message or f"Agent {agent_id}"

        # Store enhanced agent metadata for intelligent routing
        self.agent_metadata[agent_id] = {
            "name": getattr(agent, "name", agent_id),
            "role": getattr(agent, "role", None),
            "specialties": getattr(agent, "specialties", []),
            "description": description or system_message or f"Agent {agent_id}",
        }

        #  Agent created - add observability event

        # Track agents that need external registration (but don't register yet)
        a2a_config = self.formation_config.get("a2a", {}) if self.formation_config else {}
        inbound_config = a2a_config.get("inbound", {})
        inbound_enabled = inbound_config.get("enabled", False)

        if inbound_enabled and a2a_external:
            # Store for later registration after formation server starts
            if not hasattr(self, "pending_external_registrations"):
                self.pending_external_registrations = set()
            self.pending_external_registrations.add(agent_id)
            #  Info - add observability event
            #     f"Agent '{agent_id}' queued for external registration "
            #     f"after formation server starts"
            # )

        return agent

    def add_agent(
        self,
        agent: Agent,
    ) -> Agent:
        """
        Add an existing agent to the overlord.

        This method registers a pre-constructed agent with the overlord. It's useful
        when you've created an agent instance directly and need to integrate it with
        the overlord's management system.

        Args:
            agent: The agent instance to add. Must have a unique agent_id not already
                registered with this overlord.


        Returns:
            The added agent instance (same as input).

        Raises:
            ValueError: If an agent with the same agent_id already exists in the overlord.
        """
        if agent.agent_id in self.agents:
            raise ValueError(f"Agent with ID '{agent.agent_id}' already exists")

        # Store the agent
        self.agents[agent.agent_id] = agent

        # Store description for routing (legacy)
        self.agent_descriptions[agent.agent_id] = agent.system_message or ""

        # Store enhanced agent metadata for intelligent routing
        self.agent_metadata[agent.agent_id] = {
            "name": getattr(agent, "name", agent.agent_id),
            "role": getattr(agent, "role", None),
            "specialties": getattr(agent, "specialties", []),
            "description": agent.system_message or "",
        }

        #  Agent created - add observability event

        return agent

    # Memory access methods

    async def add_to_buffer_memory(
        self,
        message: Any,
        metadata: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> bool:
        """
        Add a message to the overlord's buffer memory.

        This method stores a message in the short-term buffer memory, which maintains
        context for ongoing conversations. The buffer memory provides recent message
        history and context for agents during conversation.

        Args:
            message: The message to add. Can be text or a vector embedding.
                For text messages, if buffer_memory has an embedding model,
                it will automatically generate the embedding.
            metadata: Optional metadata to associate with the message.
                Useful for filtering during retrieval (e.g., by topic, importance).
            agent_id: Optional agent ID to include in metadata.
                Used to track which agent was involved with this message.

        Returns:
            True if added successfully, False if buffer_memory is not available
            or an error occurred during addition.
        """
        if not self.buffer_memory:
            return False

        # Add agent_id to metadata for context if provided
        full_metadata = metadata or {}
        if agent_id:
            full_metadata["agent_id"] = agent_id

        # Add to buffer memory (now async)
        try:
            await self.buffer_memory.add(message, metadata=full_metadata)
            return True
        except Exception as e:
            #  Buffer memory add error - add observability event
            _ = e  # remove this after implementing observability
            return False

    async def add_to_long_term_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        agent_id: Optional[str] = None,
        user_id: Any = None,
    ) -> Optional[str]:
        """
        Add content to the overlord's long-term memory.

        This method stores information in the persistent long-term memory system,
        which maintains knowledge across sessions. Content added to long-term memory
        will be available for semantic retrieval in future conversations.

        Args:
            content: The text content to store. This should be meaningful information
                that's worth retaining for future reference.
            metadata: Optional metadata to associate with the content.
                Useful for categorization and filtering (e.g., by topic, importance).
            embedding: Optional pre-computed embedding vector.
                If provided, skips the embedding generation step.
            agent_id: Optional agent ID to include in metadata.
                Used to track which agent was the source of this information.
            user_id: Optional user ID for multi-user support.
                Required when using Memobase in multi-user mode.

        Returns:
            The ID of the newly created memory entry if successful, None otherwise.
            This ID can be used for later updating or deleting the specific memory.
        """
        if not self.long_term_memory:
            return None

        # Add agent_id to metadata for context if provided
        full_metadata = metadata or {}
        if agent_id:
            full_metadata["agent_id"] = agent_id

        # Handle multi-user case with Memobase
        if self.is_multi_user and user_id is not None:
            try:
                # ENHANCE: Use flexible user ID conversion
                internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
                memory_id = await self.long_term_memory.add(
                    content=content,
                    metadata=full_metadata,
                    embedding=embedding,
                    user_id=internal_user_id,
                )

                # Emit memory storage completed event
                observability.emit_event(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "memory_id": memory_id,
                        "memory_type": "long_term",
                        "content_length": len(content),
                    },
                    description="Long-term memory storage completed",
                )

                return memory_id
            except Exception as e:
                #  Memobase add error - add observability event
                # Emit memory storage failed event
                observability.emit_event(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCEMENT_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "memory_type": "long_term",
                        "error": str(e),
                    },
                    description=f"Long-term memory storage failed: {e}",
                )
                return None

        # Standard long-term memory case
        try:
            memory_id = await self.long_term_memory.add(
                content=content,
                metadata=full_metadata,
                embedding=embedding,
            )

            # Emit memory storage completed event
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCED,
                level=observability.EventLevel.DEBUG,
                data={
                    "memory_id": memory_id,
                    "memory_type": "long_term",
                    "content_length": len(content),
                },
                description="Long-term memory storage completed",
            )

            return memory_id
        except Exception as e:
            #  Long-term memory add error - add observability event
            # Emit memory storage failed event
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCEMENT_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "memory_type": "long_term",
                    "error": str(e),
                },
                description=f"Long-term memory storage failed: {e}",
            )
            return None

    async def search_memory(
        self,
        query: str,
        agent_id: Optional[str] = None,
        k: int = 5,
        use_long_term: bool = True,
        user_id: Any = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the overlord's memory systems for relevant information.

        This method performs a semantic search across available memory systems to find
        information relevant to the provided query. It can search both buffer memory
        (for recent context) and long-term memory (for persistent knowledge), combining
        the results into a single unified list.

        Args:
            query: The query text to search for. This will be used for semantic matching
                to find relevant information.
            agent_id: Optional agent ID to filter results by.
                Only returns memories associated with this specific agent.
            k: The number of results to return. Controls the maximum size of the result list.
            use_long_term: Whether to search long-term memory.
                If False, only searches buffer memory.
            user_id: Optional user ID for multi-user support.
                Required when using Memobase in multi-user mode.
            filter_metadata: Additional metadata filters to apply.
                Restricts results to those matching the specified metadata criteria.

        Returns:
            A list of relevant memory items, each as a dictionary with:
            - "text": The content text of the memory
            - "metadata": Associated metadata for the memory
            - "distance": Semantic distance score (lower is more relevant)
            - "source": The memory system source ("buffer" or "long_term")

            Results are sorted by relevance (lowest distance first).
        """
        # Start with empty results
        results = []

        # Prepare metadata filter
        full_filter = filter_metadata or {}
        if agent_id:
            full_filter["agent_id"] = agent_id

        # Search buffer memory if available
        if self.buffer_memory:
            try:
                # Emit memory search started event
                observability.emit_event(
                    event_type=observability.ConversationEvents.MEMORY_SHORT_TERM_LOOKUP,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "query": query[:100],
                        "memory_type": "buffer",
                        "k": k,
                        "agent_id": agent_id,
                    },
                    description="Starting buffer memory search",
                )

                # Use updated search method (now async)
                buffer_results = await self.buffer_memory.search(
                    query=query, limit=k, filter_metadata=full_filter
                )

                # Emit memory search completed event
                observability.emit_event(
                    event_type=observability.ConversationEvents.MEMORY_SHORT_TERM_RETRIEVED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "query": query[:100],
                        "memory_type": "buffer",
                        "results_count": len(buffer_results),
                    },
                    description=(f"Buffer memory search completed: {len(buffer_results)} results"),
                )

                # Convert to standard format
                for item in buffer_results:
                    results.append(
                        {
                            "text": item["content"],
                            "metadata": item["metadata"],
                            "distance": 1.0 - item["score"],  # Convert score to distance
                            "source": "buffer",
                        }
                    )
            except Exception as e:
                #  Buffer memory search error - add observability event
                _ = e  # remove this after implementing observability

        # Search long-term memory if available and enabled
        if self.long_term_memory and use_long_term:
            try:
                # Emit memory search started event
                observability.emit_event(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_LOOKUP,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "query": query[:100],
                        "memory_type": "long_term",
                        "k": k,
                        "agent_id": agent_id,
                        "user_id": str(user_id) if user_id is not None else None,
                    },
                    description="Starting long-term memory search",
                )

                # Handle multi-user case with Memobase
                if self.is_multi_user and user_id is not None:
                    # ENHANCE: Use flexible user ID conversion
                    internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
                    lt_results = await self.long_term_memory.search(
                        query=query, limit=k, user_id=internal_user_id, filter_metadata=full_filter
                    )
                # Standard long-term memory case
                else:
                    lt_results = await self.long_term_memory.search(
                        query=query, k=k, filter_metadata=full_filter
                    )

                # Emit memory search completed event
                observability.emit_event(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "query": query[:100],
                        "memory_type": "long_term",
                        "results_count": len(lt_results),
                    },
                    description=(f"Long-term memory search completed: {len(lt_results)} results"),
                )

                # Add to results in standard format
                results.extend(
                    [
                        {
                            "text": item[1].get("text", ""),
                            "metadata": item[1].get("metadata", {}),
                            "distance": item[0],
                            "source": "long_term",
                        }
                        for item in lt_results
                    ]
                )
            except Exception as e:
                #  Long-term memory search error - add observability event
                _ = e  # remove this after implementing observability

        # Sort by distance and limit to k results
        results.sort(key=lambda x: x["distance"])
        results = results[:k]

        return results

    async def clear_memory(
        self,
        clear_long_term: bool = False,
        agent_id: Optional[str] = None,
        user_id: Any = None,
    ) -> None:
        """
        Clear memory for the specified agent or user.

        This method removes items from memory systems based on the provided filters.
        It can clear both buffer memory and optionally long-term memory, with filters
        for specific agents or users.

        Args:
            clear_long_term: Whether to clear long-term memory as well.
                If False, only clears buffer memory.
            agent_id: Optional agent ID to filter by.
                Only clears memories associated with this specific agent.
            user_id: Optional user ID for multi-user support.
                Only clears memories for this specific user (requires Memobase).
        """
        filter_metadata = {}
        if agent_id:
            filter_metadata["agent_id"] = agent_id

        # Clear buffer memory
        if self.buffer_memory:
            try:
                self.buffer_memory.clear(
                    filter_metadata=filter_metadata if filter_metadata else None
                )
            except Exception as e:
                #  Buffer memory clear error - add observability event
                _ = e  # remove this after implementing observability

        # Clear long-term memory if requested
        if clear_long_term and self.long_term_memory:
            try:
                if self.is_multi_user and user_id is not None:
                    # ENHANCE: Use flexible user ID conversion
                    internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
                    # For multi-user with Memobase
                    await self.long_term_memory.clear(
                        user_id=internal_user_id,
                        filter_metadata=filter_metadata if filter_metadata else None,
                    )
                else:
                    # For standard long-term memory
                    await self.long_term_memory.clear(
                        filter_metadata=filter_metadata if filter_metadata else None
                    )
            except Exception as e:
                #  Long-term memory clear error - add observability event
                _ = e  # remove this after implementing observability

    async def clear_all_memories(self, clear_long_term: bool = False) -> None:
        """
        Clear the memories for all agents.

        This is a convenience method that clears all memory without any agent
        or user filters. It's effectively a wrapper around clear_memory()
        without an agent_id filter.

        Args:
            clear_long_term: Whether to clear long-term memories as well.
                If False, only clears buffer memory.
        """
        await self.clear_memory(clear_long_term=clear_long_term)

    # ===================================================================
    # SECRETS MANAGEMENT
    # ===================================================================

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
            #  SecretsManager init error - add observability event
            _ = e  # remove this after implementing observability
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
            #  SecretsManager unavailable - add observability event
            return False

        try:
            await self.secrets_manager.store_secret(name, value)
            return True
        except Exception as e:
            #  Secret storage error - add observability event
            _ = e  # remove this after implementing observability
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
            #  Secret retrieval error - add observability event
            _ = e  # remove this after implementing observability
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
            #  Error - add observability event
            _ = e  # remove this after implementing observability
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
            #  Error - add observability event
            _ = e  # remove this after implementing observability
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
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return config

    def get_agent(self, agent_id: Optional[str] = None) -> Agent:
        """
        Get an agent by ID.

        This method retrieves a specific agent by its ID, or the default agent
        if no ID is provided.

        Args:
            agent_id: The ID of the agent to get. If None, the default agent
                will be returned.

        Returns:
            The requested agent.

        Raises:
            ValueError: If no agent with the given ID exists, or if no default
                agent has been set when agent_id is None.
        """
        # Use default agent if no ID is provided
        if agent_id is None:
            if self.default_agent_id is None:
                raise ValueError("No default agent has been set")
            agent_id = self.default_agent_id

        # Get the agent
        if agent_id not in self.agents:
            raise ValueError(f"No agent with ID '{agent_id}' exists")

        return self.agents[agent_id]

    def remove_agent(self, agent_id: str) -> bool:
        """
        Remove an agent from the overlord.

        This method unregisters an agent and updates the default agent if necessary.
        If external registry client is configured, it also automatically deregisters
        the agent from all external registries.

        Args:
            agent_id: The ID of the agent to remove.

        Returns:
            True if the agent was removed successfully.

        Raises:
            ValueError: If no agent with the given ID exists.
        """
        if agent_id not in self.agents:
            raise ValueError(f"No agent with ID '{agent_id}' exists")

        # Deregister from external registries if configured
        if self.external_registry_client:
            try:
                # Run deregistration in background - don't block removal
                asyncio.create_task(self.deregister_agent_from_external_registry(agent_id))
                #  Debug - add observability event
            except Exception as e:
                # Log warning but don't fail the removal
                #  Warning - add observability event
                _ = e  # remove this after implementing observability

        # Remove the agent
        del self.agents[agent_id]

        # Update default agent if necessary
        if self.default_agent_id == agent_id:
            # Set the first available agent as default, or None if no agents remain
            self.default_agent_id = next(iter(self.agents)) if self.agents else None

        #  Info - add observability event

        return True

    def set_default_agent(self, agent_id: str) -> None:
        """
        Set the default agent for the overlord.

        The default agent is used when no specific agent is specified for a message,
        or when agent routing fails.

        Args:
            agent_id: The ID of the agent to set as default.
                Must refer to an agent that has been registered with this overlord.

        Raises:
            ValueError: If no agent with the given ID exists.
        """
        if agent_id not in self.agents:
            raise ValueError(f"No agent with ID '{agent_id}' exists")

        self.default_agent_id = agent_id
        #  Info - add observability event

    async def run_agent(
        self, input_text: str, agent_id: Optional[str] = None, use_memory: bool = True
    ) -> str:
        """
        Run an agent on an input text and return the text response.

        This is a high-level convenience method that handles the common case of
        sending a text message to an agent and receiving a text response.

        Args:
            input_text: The input text to process. This is the user's message
                or query that will be sent to the agent.
            agent_id: Optional ID of the agent to use. If None, the default agent will be used.
                Must refer to an agent registered with this overlord.
            use_memory: Whether to use memory for context. If True, the agent will
                have access to relevant memories when processing the message.

        Returns:
            The agent's response as a string.

        Raises:
            ValueError: If no agent with the given ID exists, or if no default
                agent has been set when agent_id is None.
        """
        # Get the agent
        agent = self.get_agent(agent_id)

        # Run the agent
        return await agent.run(input_text, use_memory=use_memory)

    def run(self, host="0.0.0.0", port=5050, reload=True, mcp=False) -> None:
        """
        Start the MUXI server with the current overlord.

        This method launches the MUXI web server, which provides a REST API for
        interacting with the overlord and its agents. The server includes
        API documentation and endpoints for chat, memory management, and agent
        operations.

        Args:
            host: Host address to bind the server to. Default "0.0.0.0" binds to all
                available network interfaces.
            port: Port to bind the server to. Default is 5050.
            reload: Whether to enable auto-reload for development. When True, the
                server will restart automatically when source files change.
            mcp: Whether to enable MCP server functionality. When True, enables
                the Model Context Protocol server for tool integrations.
        """
        try:
            # Import here to avoid circular imports
            from ..run import run_server, is_port_in_use

            # Check if port is already in use
            if is_port_in_use(port):
                msg = f"Port {port} is already in use. MUXI server cannot start."
                #  Error - add observability event
                print(f"Error: {msg}")
                print(f"Please stop any other processes using port {port} and try again.")
                return

            # Display splash screen
            if self._user_key_auto_generated or self._admin_key_auto_generated:
                self.__display_splash_screen_with_api_keys()
            else:
                self._display_splash_screen(host, port)

            # Start the server
            run_server(host=host, port=port, reload=reload, mcp=mcp)

        except Exception as e:
            #  Error - add observability event
            print(f"Error: Failed to start MUXI server: {str(e)}")

    async def select_agent_for_message(self, message: str) -> str:
        """
        Select the most appropriate agent for a given message using intelligent routing.

        This method analyzes the content of a message and determines which agent is best
        suited to handle it, based on agent descriptions and capabilities. It uses the
        routing model to make this determination with intelligent fallbacks.

        Args:
            message: The message to route. This is the user's message or query
                that needs to be directed to an appropriate agent.

        Returns:
            The ID of the selected agent. This will always be a valid agent ID
            registered with this overlord.

        Raises:
            ValueError: If no agents are available in the overlord.
        """
        # If there are no agents, raise an error
        if not self.agents:
            raise ValueError("No agents available")

        # If there's only one agent, use it
        if len(self.agents) == 1:
            return next(iter(self.agents))

        # Get caching configuration
        overlord_config = self.formation_config.get("overlord", {})
        config_section = overlord_config.get("config", {})
        caching_config = config_section.get("caching", {})

        caching_enabled = caching_config.get("enabled", True)  # Default: enabled
        cache_ttl = caching_config.get("ttl", 3600)  # Default: 3600 seconds (1 hour)

        # Check if we've seen this message before (use cached routing decision)
        if caching_enabled and message in self._routing_cache:
            cached_entry = self._routing_cache[message]

            # Check if cache entry is a simple string (old format) or dict with timestamp
            if isinstance(cached_entry, str):
                # Old format - assume it's still valid
                return cached_entry
            elif isinstance(cached_entry, dict):
                # New format with timestamp
                cached_time = cached_entry.get("timestamp", 0)
                cached_agent = cached_entry.get("agent_id")

                # Check if cache entry is still valid (within TTL)
                if time.time() - cached_time < cache_ttl:
                    return cached_agent
                else:
                    # Cache entry expired, remove it
                    del self._routing_cache[message]

        # Get routing model if not available
        routing_model = self.routing_model
        if not hasattr(self, "routing_model") or self.routing_model is None:
            try:
                # Try to get text model from formation
                routing_model = await self.get_model_for_capability("text")
                #  Routing model selection - add observability event
            except Exception as e:
                # Fall back to intelligent selection if model creation fails
                #  Routing fallback - add observability event
                _ = e  # remove this after implementing observability
                return self._select_best_available_agent(message)

        try:
            # Create a prompt for the routing model
            prompt = self._create_routing_prompt(message)

            # Query the routing model
            response = await routing_model.generate_text(prompt)

            # Parse the response
            selected_agent_id = self._parse_routing_response(response)

            # If parsing failed or the agent doesn't exist, use intelligent fallback
            if selected_agent_id is None or selected_agent_id not in self.agents:
                selected_agent_id = self._select_best_available_agent(message)
                #  Info - add observability event
                #     f"Routing model returned invalid agent. "
                #     f"Selected best available agent: '{selected_agent_id}'"
                # )
            else:
                #  Message routing - add observability event
                _ = None  # remove this after implementing observability

            # Cache the result for future identical messages (if caching is enabled)
            if caching_enabled:
                self._routing_cache[message] = {
                    "agent_id": selected_agent_id,
                    "timestamp": time.time(),
                }

            return selected_agent_id

        except Exception as e:
            # If anything goes wrong, use intelligent selection
            #  Message routing error - add observability event
            _ = e  # remove this after implementing observability
            return self._select_best_available_agent(message)

    def _create_routing_prompt(self, message: str) -> str:
        """
        Create a prompt for the routing model to determine the appropriate agent.

        This internal method constructs a prompt that instructs the LLM to select
        the most appropriate agent based on agent descriptions and the user's message.
        The prompt includes descriptions of all available agents and asks the model
        to select the best one for the given message.

        Args:
            message: The user's message that needs to be routed to an appropriate agent.

        Returns:
            A formatted prompt string for the routing model.
        """
        # Get enhanced agent descriptions with metadata
        agent_descriptions = []
        for agent_id in self.agents.keys():
            # Use enhanced metadata if available, fall back to legacy description
            if agent_id in self.agent_metadata:
                metadata = self.agent_metadata[agent_id]
                name = metadata["name"]
                role = metadata["role"]
                specialties = metadata["specialties"]
                description = metadata["description"]

                # Format: "ID: Name (Role) - Specialties: [list] - Description"
                agent_line = f"{agent_id}: {name}"
                if role:
                    agent_line += f" ({role})"
                if specialties:
                    specialty_list = ", ".join(specialties)
                    agent_line += f" - Specialties: {specialty_list}"
                if description:
                    agent_line += f" - {description}"

                agent_descriptions.append(agent_line)
            else:
                # Fallback to legacy format
                desc = self.agent_descriptions.get(agent_id, f"Agent {agent_id}")
                agent_descriptions.append(f"{agent_id}: {desc}")

        # Get persona from config or use default (with legacy support)
        custom_persona = None
        if hasattr(self, "routing_persona") and self.routing_persona:
            custom_persona = self.routing_persona
        else:
            overlord_config = self.formation_config.get("overlord", {})
            custom_persona = overlord_config.get("persona")
            if not custom_persona:
                # Legacy support: fallback to system_message
                custom_persona = overlord_config.get("system_message")

        # Create complete system message using persona
        complete_system_message = self._create_overlord_system_message(custom_persona)

        # Add current date/time to the prompt
        current_time = datetime.datetime.now()
        date_time_str = current_time.strftime("Today is %d %m %Y, %H:%M")
        prompt = f"{complete_system_message}\n\n<date-time>\n{date_time_str}\n</date-time>\n\n"

        # f"<date-time>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</date-time>\n\n" \
        # f"<user-message>{user_message}</user-message>"

        # Add available agents section
        prompt += "<available-agents>\n"
        # Add agent descriptions
        for description in agent_descriptions:
            prompt += f"- {description}\n"
        prompt += "</available-agents>\n\n"

        # Add the message
        prompt += f"<user-message>\n{message}\n</user-message>\n"

        return prompt

    def _select_best_available_agent(self, message: str) -> str:
        """
        Intelligently select the best available agent based on message content.

        This method uses simple heuristics to match message content with agent
        descriptions when the routing model fails or is unavailable.

        Args:
            message: The message to analyze for agent selection

        Returns:
            The ID of the best matching agent
        """
        if not self.agents:
            raise ValueError("No agents available")

        # If only one agent, return it
        if len(self.agents) == 1:
            return next(iter(self.agents))

        # Simple keyword matching against agent descriptions
        message_lower = message.lower()
        best_match = None
        best_score = 0

        for agent_id, description in self.agent_descriptions.items():
            if not description:
                continue

            description_lower = description.lower()
            score = 0

            # Simple keyword scoring
            keywords = [
                "business",
                "writer",
                "assistant",
                "help",
                "support",
                "analysis",
                "research",
            ]
            for keyword in keywords:
                if keyword in message_lower and keyword in description_lower:
                    score += 1

            if score > best_score:
                best_score = score
                best_match = agent_id

        # If no good match found, return the first agent
        return best_match or next(iter(self.agents))

    def _parse_routing_response(self, response: str) -> Optional[str]:
        """
        Parse the routing model's response to extract the selected agent ID.

        This internal method processes the LLM's response to identify which agent ID
        was selected. It uses various heuristics to extract the agent ID from the
        model's response, which might not always be in the exact format requested.

        Args:
            response: The raw text response from the routing model.

        Returns:
            The ID of the selected agent if successfully parsed, or None if parsing failed.
            A successful return value will be one of the agent IDs registered with this
            overlord.
        """
        # If the response is empty, return None
        if not response:
            return None

        # First, check if the response exactly matches an agent ID
        if response.strip() in self.agents:
            return response.strip()

        # Try to extract an agent ID using various heuristics
        for line in response.split("\n"):
            # Look for a clean statement like "Agent ID: xyz"
            if ":" in line:
                parts = line.split(":", 1)
                key, value = parts[0].strip().lower(), parts[1].strip()
                if "agent" in key and "id" in key:
                    if value in self.agents:
                        return value

            # Check if any agent ID is mentioned in the line
            for agent_id in self.agents:
                if agent_id in line:
                    return agent_id

        # If no agent ID was found, return None
        return None

    def list_agents(self) -> Dict[str, Dict[str, Any]]:
        """
        List all registered agents and their basic information.

        Returns a dictionary containing information about all registered agents
        including their descriptions and registration status. This is useful for
        getting an overview of available agents in the formation.

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary where keys are agent IDs and values
                contain agent information including 'description' and 'default' status.

        Example:
            >>> agents = overlord.list_agents()
            >>> print(agents)
            {
                'assistant': {'description': 'General purpose assistant', 'default': True},
                'researcher': {'description': 'Research specialist', 'default': False}
            }
        """
        return {
            agent_id: {
                "description": self.agent_descriptions.get(agent_id, ""),
                "default": agent_id == self.default_agent_id,
            }
            for agent_id in self.agents.keys()
        }

    def get_available_agents_for_a2a(
        self, requesting_agent_id: str, capability_filter: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get available agents for A2A (Agent-to-Agent) communication.

        This is the simple discovery mechanism for local formations where all agents
        are managed by the same Overlord. Agents can call this to discover other
        agents they can communicate with.

        Args:
            requesting_agent_id: ID of the agent making the discovery request
            capability_filter: Optional list of required capabilities to filter by

        Returns:
            Dict mapping agent_id to agent information including:
            - description: Agent's description
            - capabilities: Agent's available capabilities (if any)
            - status: 'active' (always active if in registry)

        Example:
            >>> # Agent A discovers other agents
            >>> available = overlord.get_available_agents_for_a2a('weather-agent')
            >>> print(available)
            {
                'calendar-agent': {
                    'description': 'Manages calendar events',
                    'capabilities': ['calendar_lookup', 'schedule_meeting'],
                    'status': 'active'
                }
            }
        """
        available_agents = {}

        for agent_id, agent in self.agents.items():
            # Don't include the requesting agent
            if agent_id == requesting_agent_id:
                continue

            # Check if agent participates in internal A2A communication
            # Default to True if not specified (backwards compatibility)
            if not getattr(agent, "a2a_internal", True):
                continue

            # Get agent capabilities if available
            capabilities = []
            if hasattr(agent, "get_capabilities"):
                capabilities = agent.get_capabilities()
            elif hasattr(agent, "capabilities"):
                capabilities = agent.capabilities

            # Apply capability filter if specified
            if capability_filter:
                if not capabilities or not any(cap in capabilities for cap in capability_filter):
                    continue

            # Add agent to available list
            available_agents[agent_id] = {
                "description": self.agent_descriptions.get(agent_id, ""),
                "capabilities": capabilities,
                "status": "active",  # If it's in the registry, it's active
            }

        return available_agents

    async def handle_user_information_extraction(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        agent_id: str,
        extraction_model: Optional[LLM] = None,
    ) -> None:
        """
        Handle the process of extracting user information from a conversation turn.

        This method centralizes the logic for automatic extraction of user information.
        When enabled, it analyzes conversation messages to identify and store important
        user details like preferences, facts, and context information.

        The extraction runs asynchronously to avoid blocking the main conversation flow,
        and uses message counting to throttle extraction frequency.

        Args:
            user_message: The latest message from the user. This is analyzed
                for information about the user.
            agent_response: The agent's response to the user. This provides
                context for understanding the user's message.
            user_id: The user's ID. Required for storing extracted information.
                Anonymous users (user_id=0) are skipped.
            agent_id: The agent's ID that handled the conversation.
                Used for metadata and context.
            extraction_model: Optional model to use for extraction.
                If provided, overrides the default extraction model.
        """
        # ENHANCE: Use flexible user ID conversion
        try:
            internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return

        # Skip extraction for anonymous users
        if internal_user_id == 0:
            return

        # Skip if extraction is disabled or not available
        if not self.auto_extract_user_info or not self.memory_extractor:
            return

        # Increment message count for this user
        self.message_counts[internal_user_id] = self.message_counts.get(internal_user_id, 0) + 1

        # Process this conversation turn for information extraction
        try:
            # Use asyncio.create_task to run extraction in background
            asyncio.create_task(
                self._run_extraction(
                    user_message=user_message,
                    agent_response=agent_response,
                    user_id=internal_user_id,
                    agent_id=agent_id,
                    message_count=self.message_counts[internal_user_id],
                    extraction_model=extraction_model,
                )
            )
            #  Debug - add observability event
        except Exception as e:
            # Log but don't fail if extraction errors occur
            #  Warning - add observability event
            _ = e  # remove this after implementing observability

    async def _run_extraction(
        self,
        user_message: str,
        agent_response: str,
        user_id: int,
        agent_id: str,
        message_count: int = 1,
        extraction_model: Optional[LLM] = None,
    ) -> None:
        """
        Run the extraction process asynchronously.

        This internal method handles the actual extraction process,
        using the MemoryExtractor to analyze the conversation turn and
        extract relevant user information.

        Args:
            user_message: The user's message to analyze.
            agent_response: The agent's response for context.
            user_id: The user's ID for storing extracted information.
            agent_id: The agent's ID for metadata.
            message_count: The current message count for this user.
                Used for throttling extraction frequency.
            extraction_model: Optional model to use for extraction.
                If provided, temporarily overrides the default model.
        """
        # Use provided extraction model if available
        if extraction_model:
            # Temporarily override the extractor's model
            original_model = self.memory_extractor.extraction_model
            self.memory_extractor.extraction_model = extraction_model

            try:
                # Process the conversation turn
                await self.memory_extractor.process_conversation_turn(
                    user_message=user_message,
                    agent_response=agent_response,
                    user_id=user_id,
                    message_count=message_count,
                )
            finally:
                # Restore the original model
                self.memory_extractor.extraction_model = original_model
        else:
            # Use the default extraction model
            await self.memory_extractor.process_conversation_turn(
                user_message=user_message,
                agent_response=agent_response,
                user_id=user_id,
                message_count=message_count,
            )

    async def get_user_context_memory(
        self, user_id: Any, agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get context memory for a specific user.

        This method retrieves structured information about a user, such as preferences,
        facts, and other contextual details that have been stored in the memory system.
        It requires multi-user support to be enabled (Memobase).

        Args:
            user_id: The user's ID to get context for. This identifies the specific
                user whose context should be retrieved.
            agent_id: Optional agent ID to scope the context. Currently not used,
                but maintained for API consistency.

        Returns:
            Dictionary of user context information. The structure depends on what
            has been stored for the user, but typically includes sections like:
            - preferences: User UI/interaction preferences
            - personal_info: User personal details
            - facts: Known facts about the user

            Returns an empty dictionary if no context exists or if multi-user
            support is not enabled.
        """
        if not self.is_multi_user or not isinstance(self.long_term_memory, Memobase):
            return {}

        # ENHANCE: Use flexible user ID conversion
        try:
            internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return {}

        return await self.long_term_memory.get_user_context_memory(user_id=internal_user_id)

    async def add_user_context_memory(
        self,
        user_id: Any,
        knowledge: Dict[str, Any],
        source: str = "manual_input",
        importance: float = 0.9,
        agent_id: Optional[str] = None,
    ) -> List[str]:
        """
        Add context memory for a specific user.

        This method stores structured information about a user, such as preferences,
        facts, and other contextual details. It requires multi-user support to be
        enabled (Memobase).

        Args:
            user_id: The user's ID. This identifies the specific user whose
                context is being updated.
            knowledge: Dictionary of information to store. Can contain nested
                structures like preferences, personal information, etc.
            source: Where this knowledge came from (e.g., "manual_input",
                "conversation", "profile_update").
            importance: Importance score (0.0 to 1.0). Higher values indicate
                more important information.
            agent_id: Optional agent ID that provided this information.
                Currently not used, but maintained for API consistency.

        Returns:
            List of memory IDs for stored information. These can be used to
            reference the specific memory items later.
            Returns an empty list if multi-user support is not enabled.
        """
        if not self.is_multi_user or not isinstance(self.long_term_memory, Memobase):
            return []

        # ENHANCE: Use flexible user ID conversion
        try:
            internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return []

        return await self.long_term_memory.add_user_context_memory(
            user_id=internal_user_id, knowledge=knowledge, source=source, importance=importance
        )

    async def clear_user_context_memory(
        self, user_id: Any, keys: Optional[List[str]] = None, agent_id: Optional[str] = None
    ) -> bool:
        """
        Clear context memory for a specific user.

        This method removes stored information about a user from the memory system.
        It requires multi-user support to be enabled (Memobase).

        Args:
            user_id: The user's ID. This identifies the specific user whose
                context should be cleared.
            keys: Optional list of specific keys to clear. If provided, only
                clears those specific keys rather than all context.
                Example: ["preferences.theme", "location"]
            agent_id: Optional agent ID that's clearing the memory.
                Currently not used, but maintained for API consistency.

        Returns:
            True if successful, False otherwise (including if multi-user
            support is not enabled).
        """
        if not self.is_multi_user or not isinstance(self.long_term_memory, Memobase):
            return False

        # ENHANCE: Use flexible user ID conversion
        try:
            internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return False

        return await self.long_term_memory.clear_user_context_memory(
            user_id=internal_user_id, keys=keys
        )

    async def register_mcp_server(
        self,
        server_id: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        auth: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: Optional[int] = None,
    ) -> str:
        """
        Register an MCP server with the centralized MCP service with secrets support.

        This method adds a Model Context Protocol (MCP) server to the overlord,
        making its tools available to agents. Supports GitHub Actions-style secrets
        interpolation in credentials. MCP servers can be external HTTP services,
        local command-line tools, or other tool providers that implement the MCP protocol.

        Args:
            server_id: Unique identifier for the MCP server. Used to reference the
                server when invoking tools or updating its configuration.
            url: URL for HTTP/SSE MCP servers. Required for web-based MCP servers,
                providing the endpoint to send MCP requests to.
            command: Command for command-line MCP servers. Required for CLI-based MCP
                servers, specifying the command to execute.
            auth: Optional authentication configuration for the MCP server.
                Supports secrets interpolation with ${{ secrets.NAME }} syntax.
                Format depends on the server's requirements.
            model: Optional model to use for this MCP handler. Some MCP servers
                require a model for processing tool invocations.
            request_timeout: Optional timeout in seconds for requests to this server.
                Defaults to the overlord's global timeout setting if not specified.

        Returns:
            The server_id of the registered server, confirming successful registration.

        Raises:
            ValueError: If neither url nor command is provided, or if both are provided.
            ConnectionError: If the MCP server cannot be contacted during registration.
        """
        # Use overlord's default timeout if none specified
        timeout = request_timeout if request_timeout is not None else self.request_timeout

        # Interpolate secrets in auth if provided
        final_auth = auth
        if auth:
            try:
                final_auth = await self.interpolate_secrets(auth)
            except Exception as e:
                #  Secret interpolation warning - add observability event
                _ = e  # remove this after implementing observability
                # Continue with original auth

        # Register the server with the MCP service
        return await self.mcp_service.register_mcp_server(
            server_id=server_id,
            url=url,
            command=command,
            credentials=final_auth,
            model=model,
            request_timeout=timeout,
        )

    async def list_mcp_tools(
        self, server_id: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        List available tools from MCP servers.

        This method retrieves information about the tools available from registered
        MCP servers, including their names, descriptions, parameters, and the servers
        they belong to.

        Args:
            server_id: Optional server ID to list tools from a specific server.
                If not provided, lists tools from all registered servers.

        Returns:
            Dictionary mapping server IDs to lists of available tools, where each
            tool is represented as a dictionary with:
            - "name": The tool's name
            - "description": The tool's description
            - "parameters": The tool's parameter schema (if any)
            - "returns": The tool's return type schema (if available)

            Example:
            {
                "weather_server": [
                    {
                        "name": "get_weather",
                        "description": "Get current weather for a location",
                        "parameters": {...}
                    }
                ]
            }
        """
        return await self.mcp_service.list_tools(server_id=server_id)

    def get_mcp_service(self) -> MCPService:
        """
        Get the centralized MCP service.

        This method provides access to the underlying MCPService instance that
        manages all MCP servers and tool invocations.

        Returns:
            The MCPService instance used by this overlord.
        """
        return self.mcp_service

    async def add_message_to_memory(
        self,
        content: str,
        role: str,
        timestamp: float,
        agent_id: str,
        user_id: Any = None,
    ) -> None:
        """
        Add a message to appropriate memory stores based on configuration.

        This method centralizes all memory operations that were previously split between
        Agent and Overlord classes. It handles adding messages to both buffer memory
        and long-term memory, with special handling for user context in multi-user mode.

        Args:
            content: The message content to store. This is the actual text message.
            role: The role of the message sender (e.g., 'user', 'assistant').
                Used for filtering and context management.
            timestamp: The timestamp of the message as a float (unix timestamp).
                Used for chronological ordering and recency calculations.
            agent_id: The ID of the agent involved in the conversation.
                Used for filtering and attribution.
            user_id: Optional user ID for multi-user support.
                Required for user context enhancement in multi-user mode.
        """
        # Always add to buffer memory regardless of user context
        if self.buffer_memory:
            metadata = {"role": role, "timestamp": timestamp, "agent_id": agent_id}

            self.buffer_memory.add(content, metadata=metadata)

        # Add to long-term memory if we have a valid user_id and multi-user support
        if self.is_multi_user and user_id is not None and self.long_term_memory:
            # ENHANCE: Use flexible user ID conversion
            try:
                internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
            except Exception as e:
                #  Error - add observability event
                _ = e  # remove this after implementing observability
                return

            # Skip for anonymous users
            if internal_user_id == 0:
                return

            metadata = {"role": role, "timestamp": timestamp, "agent_id": agent_id}

            # Enhanced message with user context if this is a user message
            if role == "user":
                try:
                    # Get user context memory
                    context_memory = await self.get_user_context_memory(user_id=internal_user_id)

                    # If context is available, enhance the message before storing
                    if context_memory:
                        # Format context memory for storage with the message
                        context_str = "User Context:\n"
                        for key, value in context_memory.items():
                            if isinstance(value, dict) and "value" in value:
                                # Handle structured context memory format
                                actual_value = value["value"]
                                context_str += f"- {key}: {actual_value}\n"
                            else:
                                # Handle simple format
                                context_str += f"- {key}: {value}\n"

                        # Store the enhanced content
                        enhanced_content = f"{context_str}\n\nUser Message: {content}"
                        metadata["enhanced"] = True
                        metadata["original_content"] = content

                        await self.long_term_memory.add(
                            content=enhanced_content, metadata=metadata, user_id=internal_user_id
                        )
                    else:
                        # Store the original content
                        await self.long_term_memory.add(
                            content=content, metadata=metadata, user_id=internal_user_id
                        )
                except Exception as e:
                    # Log error and fall back to original message
                    error_msg = "Error enhancing message with user context:"
                    #  Error - add observability event
                    _ = e  # remove this after implementing observability
                    await self.long_term_memory.add(
                        content=content, metadata=metadata, user_id=internal_user_id
                    )
            else:
                # For non-user messages, just store directly
                await self.long_term_memory.add(
                    content=content, metadata=metadata, user_id=internal_user_id
                )

    # ===================================================================
    # DOCUMENT PROCESSING ORCHESTRATION (Tasks 3.7-3.9)
    # ===================================================================

    async def process_document_upload(
        self,
        attachments: List[Dict[str, Any]],
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
        user_id: Any = None,
    ) -> str:
        """
        Enhanced document processing with full workflow integration.

        This is the main orchestration method that coordinates all document processing
        components through the three phases defined in the implementation plan:

        Phase 1: Document Storage Foundation (Task 3.7)
        - Parse and chunk documents using DocumentChunkManager
        - Store in enhanced buffer memory with DocumentAwareBufferMemory
        - Index for semantic search with DocumentSemanticIndex

        Phase 2: Document User Experience (Task 3.8)
        - Generate persona-consistent acknowledgments
        - Provide document summaries and error handling

        Phase 3: Document Workflow Integration (Task 3.9)
        - Create document-enhanced workflows
        - Execute with document context and cross-references
        - Generate final response with proper citations

        Args:
            attachments: List of attachment dictionaries containing:
                - filename: Name of the uploaded file
                - content: File content (text or bytes)
                - content_type: MIME type of the file
                - size: File size in bytes
            user_request: User's request/question about the documents
            context: Optional conversation context
            user_id: Optional user ID for multi-user support

        Returns:
            Final response string with document processing results,
            acknowledgments, and any generated insights or workflow results.
        """
        try:
            # Check if document processing is enabled
            if not self._is_document_processing_available():
                return self._generate_document_unavailable_message()

            #  Info - add observability event
            #     f"Processing {len(attachments)} document(s) for user request: "
            #     f"{user_request[:100]}..."
            # )

            # Phase 1: Document Storage Foundation (Task 3.7)
            processed_docs = await self._process_document_storage_phase(
                attachments, user_id, context
            )

            # Phase 2: Document User Experience (Task 3.8)
            acknowledgment = await self._process_document_experience_phase(
                processed_docs, user_request, context
            )

            # Phase 3: Document Workflow Integration (Task 3.9)
            if self._requires_document_workflow(user_request):
                workflow_result = await self._process_document_workflow_phase(
                    processed_docs, user_request, context
                )

                # Generate final response with citations
                final_response = await self._generate_final_document_response(
                    acknowledgment, workflow_result, processed_docs
                )
                return final_response
            else:
                # Simple case - just return acknowledgment
                return acknowledgment

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            if self.document_error_handler:
                return await self.document_error_handler.handle_document_error(
                    e, "document_upload", context or {}
                )
            else:
                return f"I encountered an error processing your documents: {str(e)}"

    async def _process_document_storage_phase(
        self,
        attachments: List[Dict[str, Any]],
        user_id: Any,
        context: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Phase 1: Document Storage Foundation (Task 3.7)

        Process and store documents with intelligent chunking and indexing.
        """
        processed_docs = []

        for attachment in attachments:
            try:
                filename = attachment.get("filename", "unknown")
                content = attachment.get("content", "")

                #  Info - add observability event

                # Chunk the document using adaptive strategies
                if self.document_chunker:
                    chunks = await self.document_chunker.chunk_document(
                        content=content, filename=filename, strategy="adaptive"
                    )
                else:
                    # Fallback simple chunking
                    chunks = [{"content": content, "metadata": {"filename": filename}}]

                # Store metadata
                # ENHANCE: Use flexible user ID conversion if available
                internal_user_id = None
                if user_id is not None:
                    try:
                        internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
                    except Exception as e:
                        #  Warning - add observability event
                        _ = e  # remove this after implementing observability
                        internal_user_id = None

                doc_metadata = {
                    "filename": filename,
                    "upload_time": time.time(),
                    "user_id": internal_user_id,
                    "chunk_count": len(chunks),
                    "original_size": len(content),
                }

                if self.document_metadata_store:
                    doc_id = await self.document_metadata_store.store_document_metadata(
                        filename, doc_metadata
                    )
                else:
                    doc_id = f"doc_{int(time.time())}"

                # Store in buffer memory with enhanced metadata
                for i, chunk in enumerate(chunks):
                    chunk_metadata = {
                        **doc_metadata,
                        "chunk_index": i,
                        "doc_id": doc_id,
                        "role": "document",
                        "timestamp": time.time(),
                    }

                    await self.add_to_buffer_memory(
                        message=chunk.get("content", ""), metadata=chunk_metadata
                    )

                # Add to processed docs list
                processed_docs.append(
                    {
                        "doc_id": doc_id,
                        "filename": filename,
                        "chunks": len(chunks),
                        "metadata": doc_metadata,
                    }
                )

                #  Info - add observability event

            except Exception as e:
                #  Error - add observability event
                _ = e  # remove this after implementing observability
                #     f"Error processing document {attachment.get('filename', 'unknown')}: {e}"
                # )
                continue

        return processed_docs

    async def _process_document_experience_phase(
        self,
        processed_docs: List[Dict[str, Any]],
        user_request: str,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """
        Phase 2: Document User Experience (Task 3.8)

        Generate persona-consistent acknowledgments and summaries.
        """
        try:
            if self.document_acknowledger:
                # Generate acknowledgment using the component
                doc_list = [(doc["doc_id"], doc["filename"]) for doc in processed_docs]
                acknowledgment = await self.document_acknowledger.generate_document_acknowledgment(
                    processed_docs=doc_list, user_request=user_request, context=context or {}
                )
            else:
                # Fallback acknowledgment
                file_list = [doc["filename"] for doc in processed_docs]
                file_names = ", ".join(file_list)
                acknowledgment = f"I've successfully processed your document(s): {file_names}. "

                if user_request:
                    acknowledgment += f"Now I can help you with: {user_request}"

            return acknowledgment

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return (
                "I've processed your documents, though I encountered some issues "
                "with the acknowledgment generation."
            )

    async def _process_document_workflow_phase(
        self,
        processed_docs: List[Dict[str, Any]],
        user_request: str,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """
        Phase 3: Document Workflow Integration (Task 3.9)

        Create and execute document-enhanced workflows.
        """
        try:
            if self.document_workflow_integrator:
                # Create document-based workflow
                doc_ids = [doc["doc_id"] for doc in processed_docs]
                workflow_result = (
                    await self.document_workflow_integrator.create_document_based_workflow(
                        documents=doc_ids, user_request=user_request, context=context or {}
                    )
                )
                return workflow_result
            else:
                # Fallback: simple memory search and response
                search_results = await self.search_memory(
                    query=user_request,
                    k=5,
                    use_long_term=False,  # Search only buffer memory with documents
                )

                if search_results:
                    relevant_content = "\n".join([r["text"] for r in search_results[:3]])
                    return f"Based on the uploaded documents:\n\n{relevant_content}"
                else:
                    return (
                        "I've processed your documents but couldn't find specific "
                        "information related to your request."
                    )

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return (
                "I processed your documents but encountered an issue generating "
                "the workflow response."
            )

    async def _generate_final_document_response(
        self, acknowledgment: str, workflow_result: str, processed_docs: List[Dict[str, Any]]
    ) -> str:
        """
        Generate the final response with proper citations and formatting.
        """
        try:
            if self.document_cross_referencer:
                # Add citations to the workflow result
                source_docs = [doc["filename"] for doc in processed_docs]
                cited_response = await self.document_cross_referencer.generate_citation_context(
                    content=workflow_result, document_sources=source_docs
                )
                return f"{acknowledgment}\n\n{cited_response}"
            else:
                # Simple concatenation
                source_list = ", ".join([doc["filename"] for doc in processed_docs])
                return f"{acknowledgment}\n\n{workflow_result}\n\n*Sources: {source_list}*"

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return f"{acknowledgment}\n\n{workflow_result}"

    def _is_document_processing_available(self) -> bool:
        """Check if document processing components are available and enabled."""
        return (
            hasattr(self, "document_processing_config")
            and self.document_processing_config
            and self.document_processing_config.is_enabled()
        )

    def _generate_document_unavailable_message(self) -> str:
        """Generate a message when document processing is not available."""
        return (
            "Document processing is not currently enabled in this formation. "
            "To enable document processing, please configure a documents model "
            "in your formation's LLM configuration."
        )

    def _requires_document_workflow(self, user_request: str) -> bool:
        """
        Determine if the user request requires complex workflow processing.

        Simple heuristic to determine if we should use workflow integration
        or just return a basic acknowledgment.
        """
        # Keywords that suggest the user wants to do something with the documents
        workflow_keywords = [
            "analyze",
            "summarize",
            "compare",
            "extract",
            "find",
            "search",
            "explain",
            "tell me",
            "what",
            "how",
            "why",
            "research",
            "review",
        ]

        user_request_lower = user_request.lower()
        return any(keyword in user_request_lower for keyword in workflow_keywords)

    # ===================================================================
    # ASYNC REQUEST-RESPONSE ORCHESTRATION (Task 4)
    # ===================================================================

    async def chat(
        self,
        message: str,
        agent_name: Optional[str] = None,
        user_id: Any = None,
        use_async: Optional[bool] = None,  # None=intelligent, True=force async, False=force sync
        webhook_url: Optional[str] = None,  # Optional webhook URL
        threshold_seconds: Optional[float] = None,  # Optional threshold override
    ) -> Union[MCPMessage, Dict[str, Any]]:
        """
        Enhanced chat with async support for long-running agentic tasks.

        This method provides the main chat interface for the overlord with intelligent
        async decision making. For requests that are expected to take a long time,
        it automatically switches to async mode and returns a request ID while
        processing continues in the background with webhook notification upon completion.

        Args:
            message: The user's message/request to process.
            agent_name: Optional specific agent to use. If None, overlord will
                select the most appropriate agent for the message.
            user_id: Optional user ID for multi-user support and context.
            use_async: Force async behavior. None=intelligent decision, True=force async,
                False=force sync. When None, uses time estimation to decide.
            webhook_url: Optional webhook URL for completion notification. Defaults
                to formation config if not provided.
            threshold_seconds: Optional threshold override for async decision. Defaults
                to formation config if not provided.

        Returns:
            For sync processing: MCPMessage with the agent's response
            For async processing: Dict with request_id, status, and processing info
        """
        # Generate unique request ID for all requests (for tracking and logging)
        request_id = f"req_{generate_nanoid()}"
        timestamp = time.time()

        #  Chat request received - add observability event

        # Start request tracking with observability
        async with self.observability_manager.track_request(
            request_id=request_id,
            formation_id=self.formation_id,
            user_id=str(user_id) if user_id is not None else None,
        ) as request_context:
            # Emit request received event
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_RECEIVED,
                level=observability.EventLevel.INFO,
                request_context=request_context,
                data={
                    "message_length": len(message),
                    "agent_name": agent_name,
                    "user_id": str(user_id) if user_id is not None else None,
                    "use_async": use_async,
                    "has_webhook": webhook_url is not None,
                },
                description=f"Request {request_id} received",
            )

            # Emit request validation event (basic validation)
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_VALIDATED,
                level=observability.EventLevel.INFO,
                request_context=request_context,
                data={
                    "message_valid": len(message.strip()) > 0,
                    "agent_exists": agent_name is None or agent_name in self.agents,
                },
                description=f"Request {request_id} validated",
            )

            # Emit routing started event
            observability.emit_event(
                event_type=observability.ConversationEvents.OVERLORD_ROUTING_STARTED,
                level=observability.EventLevel.INFO,
                request_context=request_context,
                data={"message": message[:200], "agent_name": agent_name},
                description=f"Starting routing for request {request_id}",
            )

            # Use provided values or formation defaults
            webhook_url = webhook_url or self.async_webhook_url
            threshold_seconds = threshold_seconds or self.async_threshold_seconds

            # Async decision logic
            if use_async is False:
                use_async_mode = False  # Force synchronous
                #  Debug - add observability event
            elif use_async is True:
                use_async_mode = True  # Force asynchronous
                #  Debug - add observability event
            else:  # use_async is None - intelligent decision
                if self.async_enable_estimation:
                    estimated_time = await self.time_estimator.estimate_processing_time(message)
                    use_async_mode = self.time_estimator.should_use_async(
                        estimated_time, threshold_seconds
                    )
                    #  Debug - add observability event
                    #     f"Request {request_id}: Estimated {estimated_time:.1f}s, "
                    #     f"threshold {threshold_seconds}s, async={use_async_mode}"
                    # )

            if use_async_mode:
                # Async processing path
                estimated_time = (
                    await self.time_estimator.estimate_processing_time(message)
                    if self.async_enable_estimation
                    else None
                )

                # Track async request
                from .async_patterns.request_tracker import RequestState, RequestStatus

                initial_state = RequestState(
                    id=request_id,
                    status=RequestStatus.PROCESSING,
                    start_time=timestamp,
                    webhook_url=webhook_url,
                    estimated_completion=estimated_time,
                    user_id=user_id,
                )
                await self.request_tracker.track_request(request_id, initial_state)

                # Start background processing
                asyncio.create_task(
                    self._execute_async_request(request_id, message, agent_name, user_id)
                )

                #  Info - add observability event
                #     f"Request {request_id}: Started async processing "
                #     f"(estimated: {estimated_time:.1f}s)"
                # )

                # Return immediate async response using unified format
                return create_unified_response(
                    request_id=request_id,
                    status="processing",
                    content=[],  # Empty content for processing status
                    formation_id=self.formation_id,
                    processing_mode="async",
                    processing_time=None,  # Not available yet
                    webhook_url=webhook_url,
                    error=None,
                    user_id=str(user_id) if user_id is not None else None,
                )
            else:
                # Synchronous processing path
                start_time = time.time()

                # Emit performance monitoring started event
                observability.emit_event(
                    event_type=observability.SystemEvents.PERFORMANCE_DURATION_RECORDED,
                    level=observability.EventLevel.DEBUG,
                    request_context=request_context,
                    data={
                        "operation": "sync_chat",
                        "message_length": len(message),
                        "phase": "started",
                    },
                    description="Starting performance monitoring for sync chat",
                )

                result = await self._process_sync_chat(
                    message, agent_name, user_id, request_context
                )
                processing_time = time.time() - start_time

                # Emit performance monitoring completed event
                observability.emit_event(
                    event_type=observability.SystemEvents.PERFORMANCE_DURATION_RECORDED,
                    level=observability.EventLevel.DEBUG,
                    request_context=request_context,
                    data={
                        "operation": "sync_chat",
                        "processing_time": processing_time,
                        "message_length": len(message),
                        "performance_score": "good" if processing_time < 5.0 else "slow",
                        "phase": "completed",
                    },
                    description=f"Performance monitoring completed: {processing_time:.2f}s",
                )

                #  Info - add observability event
                #     f"Request {request_id}: Completed sync processing in {processing_time:.2f}s"
                # )

                # Emit routing completed event
                observability.emit_event(
                    event_type=observability.ConversationEvents.OVERLORD_ROUTING_COMPLETED,
                    level=observability.EventLevel.INFO,
                    request_context=request_context,
                    data={"processing_time": processing_time, "mode": "sync"},
                    description=f"Routing completed for request {request_id}",
                )

                # Extract user-facing content from result
                result_content = result.content if hasattr(result, "content") else str(result)
                user_content = extract_user_content(result_content)

                # Return sync response using unified format
                return create_unified_response(
                    request_id=request_id,
                    status="completed",
                    content=user_content,
                    formation_id=self.formation_id,
                    processing_mode="sync",
                    processing_time=processing_time,
                    webhook_url=None,  # Not used for sync
                    error=None,
                    user_id=str(user_id) if user_id is not None else None,
                )

    async def _execute_async_request(
        self, request_id: str, message: str, agent_name: Optional[str], user_id: Any
    ) -> None:
        """
        Execute async request in background.

        This method runs the actual chat processing in the background for async requests,
        updating the request tracker with progress and delivering webhook notifications
        upon completion or failure.
        """
        try:
            start_time = time.time()
            #  Background processing started - add observability event

            # NEW: Check if clarification is needed before processing
            clarification_result = await self._check_clarification_needs_async(
                message, user_id, agent_name
            )

            if clarification_result:
                clarification_question, clarification_request_id = clarification_result

                # Update request status to awaiting clarification
                from .async_patterns.request_tracker import RequestStatus

                # Update request state with clarification info
                request_state = await self.request_tracker.get_request(request_id)
                if request_state:
                    request_state.clarification_question = clarification_question
                    request_state.clarification_request_id = clarification_request_id
                    request_state.original_message = message

                await self.request_tracker.update_request(
                    request_id, RequestStatus.AWAITING_CLARIFICATION
                )

                # Send clarification question via webhook
                webhook_url = await self._get_webhook_url_for_request(request_id)
                if webhook_url:
                    success = await self.webhook_manager.deliver_clarification(
                        webhook_url=webhook_url,
                        request_id=request_id,
                        clarification_question=clarification_question,
                        clarification_request_id=clarification_request_id,
                        original_message=message,
                        user_id=user_id,
                    )
                    if success:
                        #  Info - add observability event
                        #   f"Request {request_id}: Clarification question sent via webhook"
                        # )
                        return  # Exit early, wait for clarification response
                    else:
                        #  Error - add observability event
                        #     f"Request {request_id}: Failed to send clarification via webhook"
                        # )
                        # Fall back to regular processing
                        await self.request_tracker.update_request(
                            request_id, RequestStatus.PROCESSING
                        )
                else:
                    #  Warning - add observability event
                    #     f"Request {request_id}: No webhook URL for clarification, "
                    #     "proceeding with regular processing"
                    # )
                    # No webhook available, proceed with regular processing
                    await self.request_tracker.update_request(request_id, RequestStatus.PROCESSING)

            # Process using existing sync infrastructure
            result = await self._process_sync_chat(message, agent_name, user_id)
            processing_time = time.time() - start_time

            # Extract result content
            result_content = result.content if hasattr(result, "content") else str(result)

            # Update request as completed
            from .async_patterns.request_tracker import RequestStatus

            await self.request_tracker.update_request(
                request_id, RequestStatus.COMPLETED, result=result_content
            )

            #  Info - add observability event
            #     f"Request {request_id}: Completed async processing in {processing_time:.2f}s"
            # )

            # Send webhook notification if URL is configured
            webhook_url = await self._get_webhook_url_for_request(request_id)
            if webhook_url:
                success = await self.webhook_manager.deliver_completion(
                    webhook_url=webhook_url,
                    request_id=request_id,
                    result=result_content,
                    processing_time=processing_time,
                    processing_mode="async",  # NEW: indicate this was async processing
                    user_id=user_id,  # NEW: include user identifier
                )
                if success:
                    #  Webhook delivery success - add observability event
                    _ = None  # remove this after implementing observability
                else:
                    #  Webhook delivery error - add observability event
                    _ = None  # remove this after implementing observability
            else:
                #  Debug - add observability event
                _ = None  # remove this after implementing observability
                #     f"Request {request_id}: No webhook URL configured, skipping notification"
                # )

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability

            # Update request as failed
            from .async_patterns.request_tracker import RequestStatus

            await self.request_tracker.update_request(
                request_id, RequestStatus.FAILED, error=str(e)
            )

            # Send failure webhook if URL is configured
            webhook_url = await self._get_webhook_url_for_request(request_id)
            if webhook_url:
                await self.webhook_manager.deliver_completion(
                    webhook_url=webhook_url,
                    request_id=request_id,
                    error=str(e),
                    processing_mode="async",  # NEW: indicate this was async processing
                    user_id=user_id,  # NEW: include user identifier
                )

    async def _process_sync_chat(
        self, message: str, agent_name: Optional[str], user_id: Any, request_context=None
    ) -> MCPMessage:
        """
        Process chat synchronously using existing infrastructure.

        This method handles the actual chat processing using the existing overlord
        infrastructure for agent selection and message processing. It maintains
        compatibility with the current system while providing a clean interface
        for both sync and async execution paths.
        """
        # Use existing agent selection logic if no specific agent requested
        if agent_name is None:
            # Emit agent selection started event
            if request_context:
                observability.emit_event(
                    event_type=observability.ConversationEvents.OVERLORD_AGENT_SELECTION_STARTED,
                    level=observability.EventLevel.INFO,
                    request_context=request_context,
                    data={"message": message[:200]},
                    description="Starting agent selection process",
                )

            agent_name = await self.select_agent_for_message(message)

            # Emit agent selection completed event
            if request_context:
                observability.emit_event(
                    event_type=observability.ConversationEvents.OVERLORD_AGENT_SELECTED,
                    level=observability.EventLevel.INFO,
                    request_context=request_context,
                    data={"selected_agent": agent_name},
                    description=f"Agent selection completed: {agent_name}",
                )

        # Get the selected agent and process the message
        agent = self.get_agent(agent_name)

        # ENHANCED: Convert user_id to int using flexible user ID handling
        user_id_int = None
        if user_id is not None:
            # Use enhanced conversion that accepts any external user ID format
            user_id_int = await self._enhance_existing_user_id_conversion(user_id)

        # Process the message using the agent
        result = await agent.process_message(
            message, user_id=user_id_int, request_context=request_context
        )

        return result

    async def _get_webhook_url_for_request(self, request_id: str) -> Optional[str]:
        """
        Get webhook URL for a specific request.

        This method retrieves the webhook URL associated with a request,
        first checking the request's specific configuration and falling
        back to the formation default.
        """
        try:
            request_state = await self.request_tracker.get_request(request_id)
            if request_state and request_state.webhook_url:
                return request_state.webhook_url

            # Fall back to formation default
            return self.async_webhook_url
        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return self.async_webhook_url

    async def get_async_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of an async request.

        This method provides a way to check the current status of an async request,
        including completion status, results, and any errors that occurred.

        Args:
            request_id: The unique identifier for the async request

        Returns:
            Dict with request status information, or None if request not found
        """
        try:
            request_state = await self.request_tracker.get_request(request_id)

            if request_state:
                return {
                    "request_id": request_state.id,
                    "status": request_state.status.value,
                    "start_time": request_state.start_time,
                    "end_time": request_state.end_time,
                    "result": request_state.result,
                    "error": request_state.error,
                    "processing_time": (
                        request_state.end_time - request_state.start_time
                        if request_state.end_time
                        else None
                    ),
                    "estimated_completion": request_state.estimated_completion,
                    "user_id": request_state.user_id,
                }

            return None

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return None

    async def cleanup_async_requests(self, max_age_hours: float = 24) -> int:
        """
        Clean up old completed async requests.

        This method removes completed async requests that are older than the
        specified age to prevent memory buildup from request tracking.

        Args:
            max_age_hours: Maximum age in hours for keeping completed requests

        Returns:
            Number of requests cleaned up
        """
        try:
            max_age_seconds = max_age_hours * 3600
            return await self.request_tracker.cleanup_completed_requests(max_age_seconds)
        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return 0

    async def _check_clarification_needs_async(
        self, message: str, user_id: Any, agent_name: Optional[str]
    ) -> Optional[tuple[str, str]]:
        """
        Check if message needs clarification in async mode.

        Args:
            message: User's message
            user_id: User identifier
            agent_name: Selected agent name

        Returns:
            Tuple of (clarification_question, clarification_request_id) if clarification
            is needed, None if message can proceed without clarification
        """
        try:
            # Check if clarification system is available
            if not hasattr(self, "clarification_analyzer"):
                #  Debug - add observability event
                return None

            # Get user context for analysis
            user_id_int = None
            if user_id is not None:
                user_id_int = await self._enhance_existing_user_id_conversion(user_id)

            user_context = {}
            if user_id_int:
                user_context = await self.get_user_context_memory(user_id_int, agent_name)

            # Analyze message for clarification needs
            from ..clarification import (
                InformationAnalyzer,
                ClarificationQuestionGenerator,
                ClarificationManager,
                RequestType,
            )

            # Create analyzer instance
            model = await self.get_model_for_capability("clarification", agent_name)
            analyzer = InformationAnalyzer(model=model)

            # Analyze for missing information
            analysis = await analyzer.analyze_request(
                user_message=message,
                intent="general",  # Could be enhanced with intent detection
                available_tools=[],  # Could be enhanced with tool detection
                user_context=user_context,
            )

            # If no missing info, proceed
            if analysis.can_proceed and not analysis.missing_info:
                #  Debug - add observability event
                return None

            # Generate clarification question
            generator = ClarificationQuestionGenerator(model=model)
            question = await generator.generate_questions(
                missing_info=analysis.missing_info,
                available_info=analysis.available_info,
                intent="general",
                confidence_scores=analysis.confidence_scores,
                user_context=user_context,
            )

            if question and len(question) > 0:
                clarification_text = question[0].question_text

                # Start clarification tracking
                manager = ClarificationManager(overlord=self)
                request = await manager.start_clarification(
                    user_id=str(user_id),
                    agent_id=agent_name or self.default_agent_id,
                    request_type=RequestType.REASONING,
                    intent="general",
                )

                #  Info - add observability event
                return clarification_text, request.request_id

            return None

        except Exception as e:
            #  Warning - add observability event
            _ = e  # remove this after implementing observability
            # On error, proceed without clarification to avoid blocking
            return None

    async def process_async_clarification_response(
        self, request_id: str, clarification_response: str
    ) -> bool:
        """
        Process clarification response for an async request.

        Args:
            request_id: The async request ID awaiting clarification
            clarification_response: User's response to the clarification question

        Returns:
            True if processing was successfully resumed, False otherwise
        """
        try:
            # Import needed here to avoid circular imports
            from .async_patterns.request_tracker import RequestStatus

            # Get the request state
            request_state = await self.request_tracker.get_request(request_id)
            if not request_state:
                #  Error - add observability event
                return False

            if request_state.status != RequestStatus.AWAITING_CLARIFICATION:
                #  Error - add observability event
                return False

            # Process the clarification response
            if request_state.clarification_request_id:
                from ..clarification import ClarificationManager

                manager = ClarificationManager(overlord=self)
                result = await manager.process_user_response(
                    request_state.clarification_request_id, clarification_response
                )

                if result.status == "complete":
                    # Resume processing with complete parameters
                    #  Info - add observability event
                    #     f"Request {request_id}: Clarification completed, resuming processing"
                    # )

                    # Update request status back to processing
                    await self.request_tracker.update_request(request_id, RequestStatus.PROCESSING)

                    # Resume processing in background with enhanced message
                    enhanced_message = (
                        f"{request_state.original_message}\n\n"
                        f"Additional context: {clarification_response}"
                    )

                    # Schedule background processing continuation
                    import asyncio

                    asyncio.create_task(
                        self._execute_async_request(
                            request_id,
                            enhanced_message,
                            None,  # Agent already selected
                            request_state.user_id,
                        )
                    )
                    return True

                elif result.status == "continue":
                    # More clarification needed
                    #  Info - add observability event

                    # Update stored clarification question
                    request_state.clarification_question = result.next_question

                    # Send new clarification via webhook
                    webhook_url = await self._get_webhook_url_for_request(request_id)
                    if webhook_url:
                        success = await self.webhook_manager.deliver_clarification(
                            webhook_url=webhook_url,
                            request_id=request_id,
                            clarification_question=result.next_question,
                            clarification_request_id=request_state.clarification_request_id,
                            original_message=request_state.original_message,
                            user_id=request_state.user_id,
                        )
                        if success:
                            #  Info - add observability event
                            _ = None  # remove this after implementing observability
                            #     f"Request {request_id}: Additional clarification question sent"
                            # )
                        else:
                            #  Error - add observability event
                            _ = None  # remove this after implementing observability
                            #     f"Request {request_id}: Failed to send additional clarification"
                            # )

                    return True

                else:
                    #  Error - add observability event
                    _ = None  # remove this after implementing observability
                    #     f"Request {request_id}: Clarification failed: {result.error_message}"
                    # )

                    # Mark request as failed
                    await self.request_tracker.update_request(
                        request_id,
                        RequestStatus.FAILED,
                        error=f"Clarification failed: {result.error_message}",
                    )

                    return False

            return False

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability

            # Mark request as failed on error
            try:
                from .async_patterns.request_tracker import RequestStatus

                await self.request_tracker.update_request(
                    request_id, RequestStatus.FAILED, error=f"Clarification processing error: {e}"
                )
            except Exception:
                pass  # Avoid nested exceptions

            return False

    async def _enhance_existing_user_id_conversion(self, external_user_id: Any) -> int:
        """
        Enhanced version of existing user ID conversion logic.

        Accepts any external user ID format and maps to internal integer ID
        for compatibility with existing components.

        Args:
            external_user_id: User ID from external system (any type/format)

        Returns:
            Internal integer user ID for use with existing components
        """
        # Handle anonymous users (existing behavior)
        if external_user_id is None or external_user_id == 0:
            return 0

        # Convert to string for consistent processing
        external_id_str = self._normalize_external_id(external_user_id)

        # Use enhanced resolution
        internal_id, isolation_key = await self._resolve_flexible_user_id(external_id_str)

        return internal_id

    async def _resolve_flexible_user_id(self, external_id_str: str) -> tuple[int, str]:
        """
        Resolve external user ID to internal ID and isolation key.

        Args:
            external_id_str: Normalized external user ID string

        Returns:
            Tuple of (internal_id, isolation_key)
        """
        # Create hash for fast lookup (existing pattern)
        external_id_hash = hashlib.sha256(external_id_str.encode()).hexdigest()[:16]

        # Check cache first (using existing overlord caching pattern)
        if external_id_hash in self._user_id_cache:
            cached_record = self._user_id_cache[external_id_hash]
            return cached_record["internal_id"], cached_record["isolation_key"]

        # Find or create user record (leverage existing database connections)
        user_record = await self._find_or_create_user(external_id_str, external_id_hash)

        # Cache result using existing overlord cache pattern
        self._user_id_cache[external_id_hash] = user_record

        return user_record["internal_id"], user_record["isolation_key"]

    async def _find_or_create_user(self, external_id_str: str, external_id_hash: str) -> dict:
        """
        Find existing user or create new user record.

        Args:
            external_id_str: Normalized external user ID
            external_id_hash: Hash of external ID for fast lookup

        Returns:
            User record dict with internal_id and isolation_key
        """
        try:
            # Use existing database connections from overlord
            # Check if we have a database connection (leveraging existing patterns)
            db_connection = None

            if hasattr(self, "long_term_memory") and self.long_term_memory:
                if hasattr(self.long_term_memory, "db") and self.long_term_memory.db:
                    db_connection = self.long_term_memory.db
                elif (
                    hasattr(self.long_term_memory, "connection")
                    and self.long_term_memory.connection
                ):
                    db_connection = self.long_term_memory.connection

            if db_connection:
                # Try to find existing user
                query = """
                SELECT id, external_user_id, external_user_id_hash
                FROM users
                WHERE external_user_id_hash = %s
                LIMIT 1
                """

                if hasattr(db_connection, "fetchone"):
                    # Direct connection
                    cursor = db_connection.cursor()
                    cursor.execute(query, (external_id_hash,))
                    user_row = cursor.fetchone()
                elif hasattr(db_connection, "fetch_one"):
                    # AsyncPG-style connection
                    user_row = await db_connection.fetch_one(query, external_id_hash)
                else:
                    user_row = None

                if user_row:
                    # User exists, return record
                    internal_id = (
                        user_row[0] if isinstance(user_row, (list, tuple)) else user_row["id"]
                    )
                    return {
                        "internal_id": internal_id,
                        "isolation_key": f"user_{internal_id}_{external_id_hash[:8]}",
                    }
                else:
                    # Create new user
                    insert_query = """
                    INSERT INTO users (external_user_id, external_user_id_hash, user_id)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """

                    # Generate a nano_id for the user_id column (for backward compatibility)
                    nano_id = generate_nanoid()

                    if hasattr(db_connection, "fetchone"):
                        # Direct connection
                        cursor = db_connection.cursor()
                        cursor.execute(insert_query, (external_id_str, external_id_hash, nano_id))
                        new_user_row = cursor.fetchone()
                        db_connection.commit()
                        internal_id = new_user_row[0] if new_user_row else None
                    elif hasattr(db_connection, "fetch_one"):
                        # AsyncPG-style connection
                        new_user_row = await db_connection.fetch_one(
                            insert_query, external_id_str, external_id_hash, nano_id
                        )
                        internal_id = new_user_row[0] if new_user_row else None
                    else:
                        internal_id = None

                    if internal_id:
                        return {
                            "internal_id": internal_id,
                            "isolation_key": f"user_{internal_id}_{external_id_hash[:8]}",
                        }

        except Exception as e:
            #  Warning - add observability event
            _ = e  # remove this after implementing observability

        # Fallback: generate synthetic internal ID based on hash
        # This maintains functionality even if database operations fail
        synthetic_id = abs(hash(external_id_hash)) % 1000000  # Keep it reasonable
        return {
            "internal_id": synthetic_id,
            "isolation_key": f"user_{synthetic_id}_{external_id_hash[:8]}",
        }

    def _normalize_external_id(self, external_user_id: Any) -> str:
        """
        Normalize any external user ID to consistent string format.

        Args:
            external_user_id: User ID in any format

        Returns:
            Normalized string representation
        """
        if external_user_id is None:
            return "anonymous"
        elif isinstance(external_user_id, str):
            return external_user_id.strip()
        elif isinstance(external_user_id, (int, float)):
            return str(external_user_id)
        else:
            # Handle any other type (objects, etc.)
            return str(external_user_id)

    def _initialize_external_registry_client(self) -> None:
        """Initialize external registry client for outbound A2A discovery."""
        #  Debug - add observability event

    def _initialize_inbound_registry_client(self) -> None:
        """Initialize inbound registry client for A2A registration."""
        #  Debug - add observability event

    def _initialize_formation_server(self) -> None:
        """Initialize A2A formation server."""
        #  Debug - add observability event

    def _generate_api_key(self, key_type: str) -> str:
        """
        Generate a new API key with appropriate prefix.

        This internal method creates a random, secure API key with a prefix indicating
        the key type (user or admin).

        Args:
            key_type: Type of key to generate ("user" or "admin").
                Determines the prefix of the generated key.

        Returns:
            A new API key string in the format:
            - User keys: "sk_muxi_user_[random string]"
            - Admin keys: "sk_muxi_admin_[random string]"
        """
        # Generate a random string
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits
        random_part = "".join(secrets.choice(alphabet) for _ in range(24))

        # Add the appropriate prefix
        if key_type == "user":
            return f"sk_muxi_user_{random_part}"
        else:
            return f"sk_muxi_admin_{random_part}"
