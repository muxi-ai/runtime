# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Overlord - Formation-First Multi-Agent Orchestration System
# Description:  Configuration-driven AI coordination engine with intelligent agent routing
# Role:         Central orchestrator for formation-based multi-agent architectures
# Usage:        Load formation YAML files to define agents, then coordinate conversations
# Author:       Muxi Framework Team
#
# The Overlord is a formation-first orchestration system that manages multi-agent
# conversations through declarative YAML configuration. All agents, memory systems,
# and integrations are defined in formation files, promoting reproducible and
# maintainable AI architectures.
#
# Core Architecture:
#
# 1. Formation-First Design
#    - All configuration defined in formation YAML files
#    - Agents created automatically from formation specifications
#    - Centralized configuration management with secrets interpolation
#    - Environment-specific formation variants supported
#
# 2. Intelligent Agent Coordination
#    - Capability-based intelligent agent selection and routing
#    - Multi-agent conversation orchestration with context preservation
#    - Graceful fallback mechanisms for agent unavailability
#    - Consistent overlord persona across all interactions
#
# 3. Centralized Memory Systems
#    - Shared buffer memory for conversation context across agents
#    - Long-term memory with multi-user support (Memobase integration)
#    - Automatic user information extraction and context building
#    - Memory isolation and sharing controls per formation
#
# 4. External Integration Framework
#    - MCP (Model Context Protocol) server integration for tool access
#    - A2A (Agent-to-Agent) communication with external formations
#    - Secure secrets management with environment interpolation
#    - Dynamic service discovery and registration
#
# 5. Production-Ready Features
#    - Async/sync conversation modes with intelligent switching
#    - Document processing with workflow integration
#    - Comprehensive logging and observability hooks
#    - Graceful error handling and circuit breaker patterns
#
# Formation-First Usage:
#
# Basic Setup:
#   overlord = Overlord()
#   await overlord.load_formation_from_path("formation.yaml")
#   response = await overlord.chat("Hello, how can you help me?")
#   # → Automatically routes to appropriate agent based on formation config
#
# Development Testing:
#   overlord = Overlord()
#   await overlord.load_formation_from_path("formation.yaml")
#   response = await overlord.run_agent("Debug this code", "code-assistant")
#   # → Directly invoke specific agent for testing
#
# Formation File Structure:
#   # formation.yaml
#   agents:
#     - id: assistant
#       system_message: "You are a helpful assistant"
#       llm_models:
#         - text: "openai/gpt-4o"
#   memory:
#     buffer:
#       enabled: true
#       size: 50
#   a2a:
#     inbound:
#       enabled: true
#
# The formation-first approach ensures consistent, reproducible deployments
# while maintaining the flexibility for complex multi-agent orchestration.
# =============================================================================

import asyncio
import base64
import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional, Set, Union, AsyncGenerator
import os

from ..agents import Agent
from ..background.request_tracker import RequestStatus
from ...services import observability
from ...datatypes.response import MuxiResponse
from ...datatypes.clarification import ClarificationRequest, ClarificationResponse
from ...services.mcp.service import MCPService
from ...services.memory.short_term import ShortTermMemory
from ...services.memory.long_term import LongTermMemory
from ...services.memory.memobase import Memobase
from ...services.llm import LLM
from ...services.a2a.registry_client import A2ARegistryClient
from ...services.a2a.server import A2AServer
from ..memory.credential_resolver import CredentialResolver
from .agent_router import AgentRouter
from .chat_orchestrator import ChatOrchestrator
from .mcp_coordinator import MCPCoordinator
from .a2a_coordinator import A2ACoordinator
from ...services.scheduler.service import SchedulerService

# A2A models imported when needed
from ...services.secrets.secrets_manager import SecretsManager
from ...utils.id_generator import generate_nanoid

# Built-in MCP imports
from ...services.mcp.built_in import list_builtin_mcps

# Enhanced workflow capabilities
from ..workflow import (
    RequestAnalyzer,
    TaskDecomposer,
    WorkflowExecutor,
    ApprovalManager,
    ProgressTracker,
    Workflow,
)

# Utility functions
from ..utils import (
    generate_api_key,
    normalize_external_id,
)

# Configuration Management
from .secrets_manager import SecretsInterpolator

# Memory Management
from ..memory import (
    BufferMemoryManager,
    PersistentMemoryManager,
    UserContextManager,
    ExtractionCoordinator,
)

# Dynamic Agent Management
from .active_agents_tracker import ActiveAgentsTracker
from ...datatypes.exceptions import (
    AgentNotFoundError,
    AgentHasDependentsError,
    OverlordShuttingDownError,
)

# Import multimodal and synthesis components
from ...services.multimodal import MultiModalFusionEngine, WorkflowMultiModalProcessor
from ..workflow.synthesis import AdvancedResponseSynthesizer, ResponseQualityAssessor

# Import interactive elements and enhanced multimodal integration
from ..workflow.interactive import InteractiveElementGenerator, ResponseFormatter, MediaIntegrator
from ...services.multimodal import (
    TaskInputProcessor,
    TaskOutputProcessor,
)

# Import intelligent caching system
from ..caching import IntelligentCacheManager

# Import parallel workflow optimization
from ..parallel import ParallelWorkflowOptimizer

# Import intelligence components
from ..intelligence import (
    UserPreferenceEngine,
    AdaptiveResponseGenerator,
)

# Resilience components
from ..resilience import (
    ResilientWorkflowManager,
    ResilienceConfig,
)

# Document Processing Components
from ..documents.storage import (
    DocumentChunkManager,
    DocumentMetadataStore,
    DocumentReferenceSystem,
)
from ..documents.experience import (
    DocumentAcknowledgmentGenerator,
    DocumentSummarizer,
    DocumentErrorHandler,
)
from ..documents.workflow import (
    DocumentWorkflowIntegrator,
    DocumentCrossReferenceManager,
    DocumentContextPreserver,
)

# Async Orchestration Components
from ..background import (
    RequestTracker,
    WebhookManager,
    TimeEstimator,
)

# Unified Response Components
from ...datatypes.clarification import ClarificationConfig, QuestionStyle, ClarificationResultStatus
from ...utils.user_dirs import set_formation_id

# Import MarkItDown - required dependency
from markitdown import MarkItDown

_MARKITDOWN_INSTANCE = None
_MARKITDOWN_LOCK = threading.Lock()


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
        client_api_key (str): API key for user-level access
        admin_api_key (str): API key for admin-level access
        formation_config (Dict[str, Any]): Formation configuration including A2A settings
        external_registry_client (Optional[A2ARegistryClient]): Client for external A2A registries
        a2a_server (Optional[A2AServer]): Server for A2A formation

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
        # Pre-configured services from Formation
        secrets_manager: Optional[SecretsManager] = None,
        formation_config: Optional[Dict[str, Any]] = None,
        configured_services: Optional[Dict[str, Any]] = None,
        api_keys: Optional[Dict[str, str]] = None,
        # Intelligence-specific parameters
        buffer_memory: Optional[ShortTermMemory] = None,
        long_term_memory: Optional[Union[LongTermMemory, Memobase]] = None,
        auto_extract_user_info: bool = True,
        extraction_model: Optional[LLM] = None,
        request_timeout: int = 60,
        # Enhanced workflow parameters (intelligence concerns)
        enable_workflow_by_default: bool = False,
        complexity_threshold: float = 7.0,
    ):
        """
        Initialize the overlord with pre-configured services from Formation.

        The overlord constructor now focuses purely on intelligence concerns.
        All operational setup (configuration loading, service initialization,
        resource management) is handled by Formation before creating the overlord.

        Args:
            secrets_manager: Pre-configured SecretsManager instance from Formation
            formation_config: Formation configuration dict from Formation
            configured_services: Pre-configured service instances from Formation
            api_keys: Pre-generated API keys from Formation

            buffer_memory: Optional buffer memory for short-term context across all agents.
            long_term_memory: Optional long-term memory for persistent storage across all agents.
            auto_extract_user_info: Whether to automatically extract user information from conversations.
            extraction_model: Optional model to use for automatic information extraction.
            request_timeout: Default timeout in seconds for MCP server requests.

            enable_workflow_by_default: Whether to enable intelligent workflow orchestration by default.
            complexity_threshold: Complexity threshold (1-10 scale) for automatically triggering workflow orchestration.
        """

        # ===================================================================
        # INTELLIGENCE CONCERNS - Agent management and routing
        # ===================================================================

        # Initialize agent storage and metadata (intelligence concerns)
        self.agents: Dict[str, Agent] = {}
        self.agent_descriptions: Dict[str, str] = {}  # Agent descriptions for routing
        self.agent_metadata: Dict[str, Dict[str, Any]] = {}  # Enhanced metadata
        self._user_id_cache = {}  # User ID caching for routing
        self._agent_expertise: Dict[str, Dict[str, Any]] = {}  # Expertise registry

        # Recent document tracking for immediate context
        # Structure: {session_id: [documents]}
        # Note: This is a fast-access cache. Cleanup is handled automatically by buffer memory FIFO
        self._recent_documents_by_session: Dict[str, List[Dict[str, Any]]] = {}
        self._max_recent_documents_per_session = 10  # Default: keep last 10 documents per session
        self._default_session_id = "default"  # For requests without session_id
        self._max_sessions = 100  # Maximum number of sessions to track before LRU eviction

        # Dynamic Agent Management - Ultra-simple "delete when done" tracking
        self.active_agent_tracker = ActiveAgentsTracker()

        # Agent routing system
        self.agent_router = AgentRouter(self)

        # Use pre-initialized observability manager from Formation
        # This ensures all events go to the configured destination
        self.observability_manager = (
            configured_services.get("observability_manager") if configured_services else None
        )
        if not self.observability_manager:
            # This should never happen in normal flow - Formation always provides observability_manager
            raise RuntimeError(
                "ObservabilityManager not provided by Formation. "
                "This indicates a critical initialization error."
            )

        # Chat orchestration system
        self.chat_orchestrator = ChatOrchestrator(self)

        # Pending clarifications tracking
        self._pending_clarifications: Dict[str, Dict[str, Any]] = {}

        # MCP coordination system with configuration
        mcp_config = configured_services.get("mcp_config") if configured_services else None
        self.mcp_coordinator = MCPCoordinator(self, config=mcp_config)

        # A2A coordination system with configuration
        a2a_config = configured_services.get("a2a_config") if configured_services else None
        self.a2a_coordinator = A2ACoordinator(self, config=a2a_config)

        # Set up callbacks for actual deletion
        self.active_agent_tracker._delete_agent = self._actually_delete_agent
        self.active_agent_tracker._shutdown_overlord = self._actually_shutdown_overlord

        # ===================================================================
        # PRE-CONFIGURED SERVICES - Accept from Formation
        # ===================================================================

        # Accept pre-configured services from Formation
        self.secrets_manager = secrets_manager
        self.formation_config = formation_config or {}
        self._configured_services = configured_services or {}

        # Set formation_id for unified response format
        self.formation_id = self.formation_config.get("formation_id", "default-formation")
        set_formation_id(self.formation_id)

        # Initialize credential resolver if database is configured
        self.credential_resolver = None
        if configured_services:
            db_manager = configured_services.get("db_manager")
            if (
                db_manager
                and hasattr(db_manager, "async_session_maker")
                and db_manager.async_session_maker
            ):
                # Calculate formation_id_hash (consistent with memory services)
                formation_id_hash = hashlib.sha256(self.formation_id.encode()).hexdigest()

                self.credential_resolver = CredentialResolver(
                    async_session_maker=db_manager.async_session_maker,
                    formation_id=self.formation_id,
                    formation_id_hash=formation_id_hash,
                )

        # Accept pre-generated API keys from Formation
        api_keys = api_keys or {}
        self.client_api_key = api_keys.get("user")
        self.admin_api_key = api_keys.get("admin")

        # Track whether keys were provided or need generation
        self._client_key_auto_generated = self.client_api_key is None
        self._admin_key_auto_generated = self.admin_api_key is None

        # Generate keys if not provided by Formation
        if self.client_api_key is None:
            self.client_api_key = generate_api_key("user")
        if self.admin_api_key is None:
            self.admin_api_key = generate_api_key("admin")

        # ===================================================================
        # MEMORY COORDINATION - Intelligence concerns
        # ===================================================================

        # Use pre-initialized memory systems from Formation or provided parameters
        self.buffer_memory = (
            configured_services.get("buffer_memory") if configured_services else buffer_memory
        )
        self.long_term_memory = (
            configured_services.get("long_term_memory") if configured_services else long_term_memory
        )

        # Configure extraction settings (intelligence concerns)
        self.auto_extract_user_info = auto_extract_user_info
        self.extraction_model = extraction_model
        self.memory_extractor = None  # Will be initialized later

        # Multi-user mode configuration from Formation
        self.is_multi_user = (
            configured_services.get("is_multi_user", False) if configured_services else False
        )

        # Track message counts per user for extraction (intelligence)
        self.message_counts = {}  # Maps user_id to message count for throttling extraction

        # ===================================================================
        # WORKFLOW ORCHESTRATION - Intelligence concerns
        # ===================================================================

        # Initialize enhanced workflow capabilities (intelligence concerns)
        self.enable_workflow_by_default = enable_workflow_by_default
        self.complexity_threshold = complexity_threshold

        # Initialize workflow components (intelligence concerns)
        self.request_analyzer = RequestAnalyzer(llm=extraction_model)
        self.request_analyzer.complexity_threshold = complexity_threshold
        self.task_decomposer = TaskDecomposer(llm=extraction_model)
        self.workflow_executor = WorkflowExecutor(agent_registry=self.agents)
        self.approval_manager = ApprovalManager()
        self.progress_tracker = ProgressTracker()

        # Active workflows tracking (intelligence concerns)
        self.active_workflows: Dict[str, Workflow] = {}
        self.pending_approvals: Dict[str, Workflow] = {}

        # Setup progress tracking
        self.workflow_executor.add_progress_callback(self.progress_tracker.update_workflow_progress)

        # ===================================================================
        # MULTIMODAL INTELLIGENCE - Intelligence concerns
        # ===================================================================

        # Initialize multimodal and synthesis components (intelligence concerns)
        self.multimodal_fusion_engine = MultiModalFusionEngine(llm=extraction_model)
        self.quality_assessor = ResponseQualityAssessor(llm=extraction_model)
        self.response_synthesizer = AdvancedResponseSynthesizer(
            llm=extraction_model, quality_assessor=self.quality_assessor
        )

        # Initialize interactive elements and enhanced multimodal integration (intelligence concerns)
        self.interactive_generator = InteractiveElementGenerator()
        self.response_formatter = ResponseFormatter(self.interactive_generator)
        self.media_integrator = MediaIntegrator()

        # Enhanced multimodal processors (intelligence concerns)
        self.workflow_multimodal_processor = WorkflowMultiModalProcessor(
            fusion_engine=self.multimodal_fusion_engine
        )
        self.task_input_processor = TaskInputProcessor(fusion_engine=self.multimodal_fusion_engine)
        self.task_output_processor = TaskOutputProcessor(
            fusion_engine=self.multimodal_fusion_engine
        )

        # ===================================================================
        # CACHING AND OPTIMIZATION - Intelligence concerns
        # ===================================================================

        # Use pre-initialized cache manager from Formation
        self.cache_manager = (
            configured_services.get("cache_manager") if configured_services else None
        )
        if not self.cache_manager:
            # Fallback initialization if not provided
            self.cache_manager = IntelligentCacheManager(
                enable_analytics=True,
                enable_memory_optimization=True,
                embedding_service=self.extraction_model,  # Use extraction model for embeddings
            )

        # Initialize parallel workflow optimizer (intelligence concerns)
        self.parallel_optimizer = ParallelWorkflowOptimizer(sensitivity_threshold=0.5)

        # ===================================================================
        # USER EXPERIENCE INTELLIGENCE - Intelligence concerns
        # ===================================================================

        # Initialize User Experience Intelligence components (intelligence concerns)
        self.user_preference_engine = UserPreferenceEngine(overlord=self)
        self.adaptive_response_generator = AdaptiveResponseGenerator(overlord=self)

        # Initialize resilience components (intelligence concerns)
        resilience_config = ResilienceConfig(**self.formation_config.get("resilience", {}))
        self.resilient_workflow_manager = ResilientWorkflowManager(resilience_config)

        # ===================================================================
        # DOCUMENT PROCESSING INTELLIGENCE - Intelligence concerns
        # ===================================================================

        # Initialize document processing components (intelligence concerns)
        # Use pre-initialized document chunk manager from Formation
        self.document_chunker: Optional[DocumentChunkManager] = (
            configured_services.get("document_chunk_manager") if configured_services else None
        )

        self.document_metadata_store: Optional[DocumentMetadataStore] = None
        self.document_reference_system: Optional[DocumentReferenceSystem] = None
        self.document_acknowledger: Optional[DocumentAcknowledgmentGenerator] = None
        self.document_summarizer: Optional[DocumentSummarizer] = None
        self.document_error_handler: Optional[DocumentErrorHandler] = None
        self.document_workflow_integrator: Optional[DocumentWorkflowIntegrator] = None
        self.document_cross_referencer: Optional[DocumentCrossReferenceManager] = None
        self.document_context_preserver: Optional[DocumentContextPreserver] = None

        # ===================================================================
        # ASYNC REQUEST HANDLING - Intelligence concerns
        # ===================================================================

        # Use pre-initialized async components from Formation
        self.request_tracker = (
            configured_services.get("request_tracker") if configured_services else None
        )
        if not self.request_tracker:
            self.request_tracker = RequestTracker()

        self.webhook_manager = (
            configured_services.get("webhook_manager") if configured_services else None
        )
        if not self.webhook_manager:
            async_config = self.formation_config.get("async", {})
            self.webhook_manager = WebhookManager(
                default_retries=async_config.get("webhook_retries", 3),
                default_timeout=async_config.get("webhook_timeout", 10),
            )

        # Time estimator is intelligence-specific, keep local initialization
        self.time_estimator = TimeEstimator(self.request_analyzer)

        # Async configuration (intelligence concerns)
        async_config = self.formation_config.get("async", {})
        self.async_threshold_seconds = async_config.get("threshold_seconds", 30)
        self.async_enable_estimation = async_config.get("enable_estimation", True)
        self.async_webhook_url = async_config.get("webhook_url")

        # Track background tasks to ensure they complete before shutdown
        self._background_tasks: Set[asyncio.Task] = set()

        # Get database manager from Formation if available
        self.db_manager = configured_services.get("db_manager") if configured_services else None

        # ===================================================================
        # CLARIFICATION INTELLIGENCE - Intelligence concerns
        # ===================================================================

        # Use pre-initialized clarification config from Formation
        self.clarification_config = (
            configured_services.get("clarification_config") if configured_services else None
        )
        if not self.clarification_config:
            # Fallback to defaults
            self.clarification_config = ClarificationConfig(
                max_questions=5, style=QuestionStyle.CONVERSATIONAL, persist_learned_info=False
            )

        # ===================================================================
        # SERVICE REFERENCES - References to pre-configured services
        # ===================================================================

        # Service references (will be configured from Formation)
        self.external_registry_client: Optional[A2ARegistryClient] = None
        self.inbound_registry_client: Optional[A2ARegistryClient] = None
        self.a2a_server: Optional[A2AServer] = None
        self.mcp_service = MCPService.get_instance()  # Get existing instance
        self.scheduler_service: Optional[SchedulerService] = None

        # Initialize agent tracking for delayed external registration
        self.pending_external_registrations = set()

        # Set request timeout
        self.request_timeout = request_timeout

        # ===================================================================
        # INTELLIGENCE COORDINATORS - Intelligence concerns
        # ===================================================================

        # Initialize intelligence coordination managers
        self.secrets_interpolator = SecretsInterpolator(self)
        self.buffer_memory_manager = BufferMemoryManager(self)
        self.persistent_memory_manager = PersistentMemoryManager(self)
        self.user_context_manager = UserContextManager(self)
        self.extraction_coordinator = ExtractionCoordinator(self)

        # ===================================================================
        # INTELLIGENCE MODELS AND CACHE - Intelligence concerns
        # ===================================================================

        # Initialize model cache and capability models for intelligence routing
        self._model_cache: Dict[str, LLM] = {}
        self._capability_models: Dict[str, str] = {}

        # Load default persona from file (intelligence concerns)
        self._load_default_persona()

        # ===================================================================
        # POST-INITIALIZATION SETUP
        # ===================================================================

        # Memory extractor is now initialized by Formation

        # NOTE: Service initialization will be handled by Formation
        # The overlord constructor now focuses purely on intelligence setup

    def _create_tracked_task(self, coro, name: Optional[str] = None) -> asyncio.Task:
        """Create a task and track it for proper cleanup during shutdown."""

        task = asyncio.create_task(coro)
        if name:
            task.set_name(name)

        # Track the task
        self._background_tasks.add(task)

        # Log task creation
        observability.observe(
            event_type=observability.SystemEvents.SERVICE_STARTED,  # Use existing event type
            level=observability.EventLevel.INFO,
            data={
                "task_name": name or "unnamed",
                "total_tasks": len(self._background_tasks),
            },
            description=f"Created tracked background task: {name or 'unnamed'}",
        )

        # Remove from set when done
        def task_done_callback(task):
            self._background_tasks.discard(task)

            # Check if task had an exception
            exception_str = None
            try:
                if task.exception():
                    exception_str = str(task.exception())
            except asyncio.CancelledError:
                #  Warning - TODO: add observability
                # SystemEvents.CANCELLED (task)
                exception_str = "CancelledError"
            except Exception as e:
                exception_str = str(e)

            # Log task completion
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,  # Reuse existing event type
                level=(
                    observability.EventLevel.INFO
                    if not exception_str
                    else observability.EventLevel.ERROR
                ),
                data={
                    "task_name": task.get_name() if hasattr(task, "get_name") else "unnamed",
                    "remaining_tasks": len(self._background_tasks),
                    "exception": exception_str,
                    "completed": True,  # Indicate this is a completion event
                },
                description=(
                    "Background task completed: "
                    f"{task.get_name() if hasattr(task, 'get_name') else 'unnamed'}"
                ),
            )

        task.add_done_callback(task_done_callback)

        return task

    async def _wait_for_background_tasks(self, timeout: float = 30.0):
        """Wait for all background tasks to complete with timeout."""
        if not self._background_tasks:
            return

        # Create a copy to avoid modification during iteration
        tasks = list(self._background_tasks)

        try:
            # Wait for all tasks with timeout
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
        except asyncio.TimeoutError:
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()

            # Wait for cancellation to complete
            await asyncio.gather(*tasks, return_exceptions=True)

    def start(self) -> None:
        """Start all overlord services including cache manager."""
        try:
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an event loop, schedule the async startup as a task
                startup_task = loop.create_task(self._async_startup())
                # Store the task so we can wait for it if needed
                self._startup_task = startup_task
            except RuntimeError:
                # No event loop running, we can use asyncio.run()
                asyncio.run(self._async_startup())
                self._startup_task = None

        except Exception:
            #  Error - TODO: add observability
            #  ErrorEvents.INTERNAL_ERROR (overlord)
            raise

    async def _async_startup(self) -> None:
        """Async startup logic extracted to a separate method."""
        # Services are now initialized by Formation before Overlord creation
        # Only handle intelligence-specific initialization here

        # LLM configuration is already initialized by Formation
        # Just copy the configuration for local use
        if hasattr(self, "_configured_services") and self._configured_services:
            llm_config = self._configured_services.get("llm_config", {})
            self._model_cache = {}
            self._capability_models = {}

            # Process models by capability
            models_config = llm_config.get("models", [])
            for model_config in models_config:
                for capability, model_name in model_config.items():
                    if capability in ["api_key", "settings"]:
                        continue
                    self._capability_models[capability] = {
                        "model": model_name,
                        "api_key": model_config.get("api_key"),
                        "settings": model_config.get("settings", {}),
                    }

            self._global_llm_settings = llm_config.get("settings", {})
            self._global_api_keys = llm_config.get("api_keys", {})

        # Initialize the routing model (async) - now that LLM config is ready
        await self._initialize_routing_model()

        # Cache manager is already started by Formation
        # No need to start it again

        # Observability system is already initialized and ready (no async start needed)

        # Load agents from formation configuration
        # Load agents from formation's pre-processed configuration
        await self._load_agents_from_formation()

        # Document processing configuration is now initialized by Formation
        if hasattr(self, "_configured_services") and self._configured_services:
            self.document_processing_config = self._configured_services.get(
                "document_processing_config"
            )
            self.document_chunker = self._configured_services.get("document_chunker")

        # A2A services are now initialized by Formation
        # Start A2A formation server if initialized by Formation
        if hasattr(self, "a2a_server") and self.a2a_server:
            await self.a2a_coordinator._start_a2a_server()

        # Process pending external agent registrations if available
        if (
            hasattr(self, "inbound_registry_client")
            and self.inbound_registry_client
            and hasattr(self, "pending_external_registrations")
        ):
            await self.a2a_coordinator._process_pending_agent_registrations()

        # Start scheduler service if enabled
        if hasattr(self, "formation_config") and self.formation_config.get("scheduler", {}).get(
            "enabled", False
        ):
            # Validate that database connection is available for scheduler
            if not hasattr(self, "db_manager") or not self.db_manager:
                raise ValueError(
                    "Scheduler is enabled but no database connection is configured. "
                    "Please configure 'memory.persistent.connection_string' in formation.yaml "
                    "or disable scheduler with 'scheduler.enabled: false'"
                )

            self.scheduler_service = await SchedulerService.get_instance(self)
            await self.scheduler_service.start()

        #  Info - TODO: add observability
        #  SystemEvents.STARTED (overlord)

    async def ensure_started(self) -> None:
        """Ensure that the overlord startup is complete.

        This method can be called to wait for async startup to complete
        when the overlord was started from within an existing event loop.
        """
        if hasattr(self, "_startup_task") and self._startup_task:
            await self._startup_task

    async def _load_agents_from_formation(self) -> None:
        """
        Load agents from formation's pre-processed configuration.

        This method creates Agent instances from the formation's agent configurations
        that were already validated and processed by the Formation class.
        """
        observability.observe(
            event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
            level=observability.EventLevel.DEBUG,
            data={"configured_services_keys": list(self._configured_services.keys())},
            description="Starting agent loading from formation",
        )

        # Get agents configuration from configured services
        agents_config = self._configured_services.get("agents_config", [])

        observability.observe(
            event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
            level=observability.EventLevel.DEBUG,
            data={"agents_count": len(agents_config)},
            description=f"Found {len(agents_config)} agents in formation configuration",
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
                    continue

                # Create agent from configuration
                agent = await self._create_agent_from_config(agent_config)

                # Add to agents dictionary
                self.agents[agent_id] = agent

                # Store agent metadata for routing
                self.agent_descriptions[agent_id] = agent_config.get("description", "")
                self.agent_metadata[agent_id] = {
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

    async def _create_agent_from_config(self, agent_config: Dict[str, Any]):
        """
        Create an Agent instance from configuration.

        Args:
            agent_config: Agent configuration dictionary from formation

        Returns:
            Agent: Configured agent instance
        """
        # Get or create LLM model for the agent
        try:
            # Try to use overlord's model creation (it should be initialized by now)
            model = await self.get_model_for_capability("text")
        except Exception as e:
            # Configuration error - text capability must be properly configured
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "agent_id": agent_config.get("id", "unknown"),
                    "capability": "text",
                    "config_type": "llm_model",
                },
                description=(
                    f"Failed to get text model for agent {agent_config.get('id', 'unknown')}: "
                    f"{str(e)}. LLM configuration with text capability is mandatory."
                ),
            )
            raise ValueError(
                f"LLM text capability configuration is mandatory for agent creation. Error: {str(e)}"
            )

        # Create agent instance
        agent = Agent(
            model=model,
            overlord=self,
            agent_id=agent_config.get("id"),
            name=agent_config.get("name"),
            system_message=agent_config.get("system_message"),
            knowledge_config=agent_config.get("knowledge"),
        )

        return agent

    def _load_default_persona(self) -> None:
        """Load the default persona from the system_persona.md file."""
        try:
            # Get the path to the system_persona.md file relative to this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            persona_path = os.path.join(current_dir, "utils", "system_persona.md")

            if os.path.exists(persona_path):
                with open(persona_path, "r", encoding="utf-8") as f:
                    self._default_persona = f.read().strip()
            else:
                # Fallback if file doesn't exist
                fallback = "You are a friendly and helpful assistant."
                self._default_persona = fallback
                msg = f"Persona file not found at {persona_path}, using fallback"
                #  Warning - TODO: add observability
                # SystemEvents.FAILED_INITIALIZATION (persona)
                _ = msg  # remove this after implementing observability

        except Exception as e:
            # Fallback if there's an error reading the file
            fallback = "You are a friendly and helpful assistant."
            self._default_persona = fallback
            #  Warning - TODO: add observability
            # ErrorEvents.INTERNAL_ERROR
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
            #  Warning - TODO: add observability
            # SystemEvents.FAILED_INITIALIZATION (system_message)
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

        # Add built-in MCP system prompts if enabled
        builtin_mcp_prompts = self._get_builtin_mcp_prompts()
        if builtin_mcp_prompts:
            system_message += f"\n\n## Built-in Tools\n\n{builtin_mcp_prompts}"

        # Combine technical instructions with persona
        return (
            f"<system-message>\n{system_message}\n</system-message>\n\n"
            f"<persona>\n{persona}\n</persona>"
        )

    async def _initialize_buffer_memory(self, buffer_config: Dict[str, Any]) -> None:
        """Initialize buffer memory from configuration."""
        # Import Formation's initialization functions dynamically to avoid circular imports
        from ..initialization import initialize_buffer_memory

        # Get the formation instance
        formation = getattr(self, "_formation_instance", None)
        if not formation:
            # If no formation instance, create a minimal one for initialization
            # This is a fallback scenario that shouldn't normally happen
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"config_type": "buffer_memory"},
                description="No formation instance found during buffer memory initialization",
            )
            # Use None as formation - the initialization function should handle this
            formation = None

        await initialize_buffer_memory(formation, self, buffer_config)

    async def _initialize_persistent_memory(self, persistent_config: Dict[str, Any]) -> None:
        """Initialize persistent memory from configuration."""
        # Import Formation's initialization functions dynamically to avoid circular imports
        from ..initialization import initialize_persistent_memory

        # Get the formation instance
        formation = getattr(self, "_formation_instance", None)
        if not formation:
            # If no formation instance, create a minimal one for initialization
            # This is a fallback scenario that shouldn't normally happen
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"config_type": "persistent_memory"},
                description="No formation instance found during persistent memory initialization",
            )
            # Use None as formation - the initialization function should handle this
            formation = None

        await initialize_persistent_memory(formation, self, persistent_config)

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
                #  Warning - TODO: add observability
                # ErrorEvents.FAILED_INITIALIZATION (api_key)
                _ = e  # remove this after implementing observability
        # Create model instance
        model = LLM(model=model_name, api_key=final_api_key, **final_settings)

        # Cache the model
        self._model_cache[cache_key] = model

        return model

    async def _initialize_routing_model(self):
        """Initialize the model used for agent routing decisions."""
        try:
            # Get overlord configuration from formation config
            overlord_config = self.formation_config.get("overlord", {})

            # Set custom persona if provided
            overlord_persona = overlord_config.get("persona")
            self.routing_persona = overlord_persona

            # Get overlord.llm config structure
            llm_config = overlord_config.get("llm", {})
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

            # Response configuration
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

            # Streaming configuration
            self.streaming = overlord_config.get("streaming", True)

            # Initialize cache expiry tracking if TTL is configured
            if self.routing_cache_ttl > 0:
                self._routing_cache_expiry: Dict[str, float] = {}

            #  Info - TODO: add observability
            #  SystemEvents.STARTED (overlord routing)
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
            # If initialization fails, log error and raise
            #  Error - TODO: add observability
            # ErrorEvents.FAILED_INITIALIZATION (overlord routing)
            _ = e  # remove this after implementing observability
            raise RuntimeError("Failed to initialize routing model from overlord.llm config") from e

    async def create_model(
        self,
        model: str = "openai/gpt-4o",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_retries: Optional[int] = None,
        fallback_model: Optional[str] = None,
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
            max_retries: Maximum retry attempts for the same model. If None, uses
                formation defaults.
            fallback_model: Fallback model if primary model fails. If None, uses
                formation defaults.
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
                #  Warning - TODO: add observability
                # ErrorEvents.FAILED_INITIALIZATION (api_key)
                _ = e  # remove this after implementing observability
                # Continue with original api_key

        # Apply global LLM settings with parameter overrides
        final_max_retries = max_retries or self._global_llm_settings.get("max_retries", 3)
        final_fallback_model = fallback_model or self._global_llm_settings.get("fallback_model")

        # Create and return a new model instance
        return LLM(
            model=model,
            api_key=final_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=final_max_retries,
            fallback_model=final_fallback_model,
            **kwargs,
        )

    # ===================================================================
    # MEMORY ACCESS METHODS
    # ===================================================================

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
        return await self.buffer_memory_manager.add_to_buffer_memory(message, metadata, agent_id)

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
        return await self.persistent_memory_manager.add_to_long_term_memory(
            content, metadata, embedding, agent_id, user_id
        )

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
        return await self.buffer_memory_manager.search_buffer_memory(
            query, agent_id, k, use_long_term, user_id, filter_metadata
        )

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
        await self.buffer_memory_manager.clear_buffer_memory(agent_id)
        if clear_long_term:
            await self.persistent_memory_manager.clear_long_term_memory(user_id, agent_id)

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

        #  Info - TODO: add observability
        # SystemEvents.MEMORY_CLEAR

    # ===================================================================
    # AGENT MANAGEMENT
    # ===================================================================

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
            #  Error - TODO: add observability
            # ErrorEvents.RESOURCE_NOT_FOUND
            raise ValueError(f"No agent with ID '{agent_id}' exists")

        return self.agents[agent_id]

    async def remove_agent(self, agent_id: str) -> bool:
        """
        Remove agent using "delete when done" pattern - actual deletion happens when safe.

        This method marks an agent for removal but only deletes it when it's not busy
        handling requests. This prevents dangling request IDs and ensures graceful
        agent removal.

        Args:
            agent_id: The ID of the agent to remove.

        Returns:
            True if the agent was marked for removal successfully.

        Raises:
            AgentNotFoundError: If no agent with the given ID exists.
            AgentHasDependentsError: If other agents depend on this agent.
        """
        if agent_id not in self.agents:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

        # Check for dependent agents
        dependent_agents = self._get_dependent_agents(agent_id)
        if dependent_agents:
            raise AgentHasDependentsError(
                f"Cannot remove agent '{agent_id}' - other agents depend on it: {dependent_agents}"
            )

        # Mark for deletion - actual removal happens when no longer active
        await self.active_agent_tracker.mark_agent_for_deletion(agent_id)

        if await self.active_agent_tracker.is_agent_busy(agent_id):
            observability.observe(
                event_type=observability.SystemEvents.AGENT_REMOVED,
                level=observability.EventLevel.INFO,
                data={"agent_id": agent_id, "removal_status": "deferred", "reason": "agent_busy"},
                description=f"Agent '{agent_id}' marked for deletion - will be removed when current request completes",
            )
        else:
            observability.observe(
                event_type=observability.SystemEvents.AGENT_REMOVED,
                level=observability.EventLevel.INFO,
                data={"agent_id": agent_id, "removal_status": "immediate", "reason": "agent_idle"},
                description=f"Agent '{agent_id}' removed immediately (not busy)",
            )

        return True

    async def _actually_delete_agent(self, agent_id: str):
        """Actually delete the agent (called by active_agent_tracker)."""
        if agent_id in self.agents:
            # Deregister from external registries if configured
            if hasattr(self, "external_registry_client") and self.external_registry_client:

                async def _deregister_with_error_handling():
                    """Wrapper to handle errors in background deregistration."""
                    try:
                        await self.a2a_coordinator.deregister_agent_from_external_registry(agent_id)
                        observability.observe(
                            event_type=observability.SystemEvents.AGENT_DEREGISTRATION_COMPLETED,
                            level=observability.EventLevel.DEBUG,
                            data={"agent_id": agent_id, "registry": "external"},
                            description=f"Successfully deregistered agent {agent_id} from external registry",
                        )
                    except Exception as e:
                        # Log error but don't fail the removal
                        observability.observe(
                            event_type=observability.ErrorEvents.INTERNAL_ERROR,
                            level=observability.EventLevel.WARNING,
                            data={
                                "agent_id": agent_id,
                                "error_type": type(e).__name__,
                                "error_message": str(e),
                                "operation": "external_deregistration",
                            },
                            description=f"Failed to deregister agent {agent_id} from external registry: {str(e)}",
                        )

                # Create tracked task with error handling
                self._create_tracked_task(
                    _deregister_with_error_handling(), name=f"deregister_agent_{agent_id}"
                )

            # Invalidate all cached responses for this agent
            try:
                invalidated_count = await self.cache_manager.invalidate_cache(agent_id=agent_id)
                observability.observe(
                    event_type=observability.SystemEvents.MEMORY_DELETION_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={"agent_id": agent_id, "invalidated_count": invalidated_count},
                    description=f"Successfully invalidated {invalidated_count} cached responses for agent '{agent_id}'",
                )
            except Exception as e:
                # Don't fail agent deletion if cache invalidation fails
                observability.observe(
                    event_type=observability.SystemEvents.MEMORY_DELETION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"agent_id": agent_id, "error": str(e)},
                    description=f"Failed to invalidate cache for agent '{agent_id}': {str(e)}",
                )

            # Cleanup agent if it has cleanup logic
            agent = self.agents[agent_id]
            if hasattr(agent, "cleanup"):
                await agent.cleanup()

            # Remove the agent
            del self.agents[agent_id]

            # Update default agent if necessary
            if hasattr(self, "default_agent_id") and self.default_agent_id == agent_id:
                # Set the first available agent as default, or None if no agents remain
                self.default_agent_id = next(iter(self.agents)) if self.agents else None

            observability.observe(
                event_type=observability.SystemEvents.AGENT_INITIALIZED,  # Using closest available event
                level=observability.EventLevel.INFO,
                data={"agent_id": agent_id, "action": "deleted"},
                description=f"Agent '{agent_id}' successfully deleted",
            )

    async def _actually_shutdown_overlord(self):
        """Actually shutdown overlord (called by active_agent_tracker)."""

        # Wait for background tasks to complete
        if hasattr(self, "_background_tasks") and self._background_tasks:
            observability.observe(
                event_type=observability.SystemEvents.OVERLORD_SHUTDOWN,
                level=observability.EventLevel.INFO,
                data={"background_tasks_count": len(self._background_tasks)},
                description=f"Waiting for {len(self._background_tasks)} background tasks to complete",
            )

            # Wait for tasks with a reasonable timeout
            await self._wait_for_background_tasks(timeout=30.0)

        # Stop scheduler service if running
        if hasattr(self, "scheduler_service") and self.scheduler_service:
            try:
                await self.scheduler_service.stop()
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "service": "scheduler"},
                    description=f"Error stopping scheduler service: {e}",
                )

        observability.observe(
            event_type=observability.SystemEvents.OVERLORD_SHUTDOWN,
            level=observability.EventLevel.INFO,
            data={"active_requests": 0},
            description="Overlord shutdown complete - no active requests remaining",
        )
        # Additional cleanup logic here if needed

    def _get_dependent_agents(self, agent_id: str) -> List[str]:
        """Find agents that depend on the given agent."""
        dependents = []
        for other_agent_id, other_agent in self.agents.items():
            if other_agent_id != agent_id:
                # Check if other agent has dependencies configuration
                if hasattr(other_agent, "config") and isinstance(other_agent.config, dict):
                    dependencies = other_agent.config.get("dependencies", [])
                    if agent_id in dependencies:
                        dependents.append(other_agent_id)
        return dependents

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

    async def select_agent_for_message(self, message: str, request_id: Optional[str] = None) -> str:
        """
        Select the most appropriate agent for a given message using intelligent routing.

        This method analyzes the content of a message and determines which agent is best
        suited to handle it, based on agent descriptions and capabilities. It uses the
        routing model to make this determination with intelligent fallbacks.

        Args:
            message: The message to route. This is the user's message or query
                that needs to be directed to an appropriate agent.
            request_id: Optional request ID for request-scoped agent exclusion

        Returns:
            The ID of the selected agent. This will always be a valid agent ID
            registered with this overlord.

        Raises:
            ValueError: If no agents are available in the overlord.
        """
        return await self.agent_router.select_agent_for_message(message, request_id)

    async def list_agents(self) -> Dict[str, Dict[str, Any]]:
        """
        List all registered agents with their status information.

        Returns a dictionary containing information about all registered agents
        including their descriptions, registration status, and current activity status.
        This is useful for getting an overview of available agents in the formation.

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary where keys are agent IDs and values
                contain agent information including 'description', 'default' status,
                'status' (idle/busy/pending_deletion), and 'is_busy' flag.

        Example:
            >>> agents = await overlord.list_agents()
            >>> print(agents)
            {
                'assistant': {
                    'description': 'General purpose assistant',
                    'default': True,
                    'status': 'idle',
                    'is_busy': False
                },
                'researcher': {
                    'description': 'Research specialist',
                    'default': False,
                    'status': 'busy',
                    'is_busy': True
                }
            }
        """
        agent_info = {}
        for agent_id in self.agents.keys():
            is_busy = await self.active_agent_tracker.is_agent_busy(agent_id)
            pending_deletions = await self.active_agent_tracker.get_pending_deletions()
            is_pending_deletion = agent_id in pending_deletions

            status = "busy" if is_busy else "idle"
            if is_pending_deletion:
                status = "pending_deletion"

            agent_info[agent_id] = {
                "description": self.agent_descriptions.get(agent_id, ""),
                "default": agent_id == getattr(self, "default_agent_id", None),
                "status": status,
                "is_busy": is_busy,
            }

        return agent_info

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
        return self.a2a_coordinator.get_available_agents_for_a2a(
            requesting_agent_id=requesting_agent_id, capability_filter=capability_filter
        )

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
        await self.extraction_coordinator.handle_user_information_extraction(
            user_message, agent_response, user_id, agent_id, extraction_model
        )

    async def get_user_context(
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
        return await self.user_context_manager.get_user_context(user_id, agent_id)

    async def add_user_context(
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
        return await self.user_context_manager.add_user_context(
            user_id, knowledge, source, importance, agent_id
        )

    async def clear_user_context(
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
        return await self.user_context_manager.clear_user_context(user_id, keys, agent_id)

    async def _add_to_long_term_memory(
        self,
        content: str,
        metadata: Dict[str, Any],
        internal_user_id: Optional[int],
        user_id: Optional[str],
    ) -> None:
        """
        Helper method to add content to long-term memory, handling both Memobase and LongTermMemory interfaces.

        Args:
            content: The content to store
            metadata: Metadata to associate with the content
            internal_user_id: Internal user ID for Memobase
            user_id: External user ID for LongTermMemory
        """
        try:
            if isinstance(self.long_term_memory, Memobase):
                await self.long_term_memory.add(
                    content=content,
                    metadata=metadata,
                    user_id=internal_user_id,
                    external_user_id=user_id,
                )
            else:
                # LongTermMemory expects external_user_id
                await self.long_term_memory.add(
                    content=content, metadata=metadata, external_user_id=user_id
                )
        except Exception as e:
            # Log memory storage error but don't propagate to avoid breaking conversation flow
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "memory_type": type(self.long_term_memory).__name__,
                    "content_length": len(content) if content else 0,
                    "user_id": str(user_id) if user_id else None,
                    "internal_user_id": internal_user_id,
                },
                description=f"Failed to add content to long-term memory: {str(e)}",
            )

    async def add_message_to_memory(
        self,
        content: str,
        role: str,
        timestamp: float,
        agent_id: str,
        user_id: Any = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
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
            metadata = {
                "role": role,
                "timestamp": timestamp,
                "agent_id": agent_id,
                "user_id": str(user_id) if user_id is not None else None,
                "session_id": session_id,
                "request_id": request_id,
            }

            self.buffer_memory.add(content, metadata=metadata)

        # Add to long-term memory if we have a valid user_id and multi-user support
        if self.is_multi_user and user_id is not None and self.long_term_memory:
            try:
                internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
            except Exception as e:
                #  Error - TODO: add observability
                # ErrorEvents.INTERNAL_ERROR
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
                    context_memory = await self.get_user_context(user_id=internal_user_id)

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

                        # Store the enhanced content using helper method
                        await self._add_to_long_term_memory(
                            content=enhanced_content,
                            metadata=metadata,
                            internal_user_id=internal_user_id,
                            user_id=user_id,
                        )
                    else:
                        # Store the original content using helper method
                        await self._add_to_long_term_memory(
                            content=content,
                            metadata=metadata,
                            internal_user_id=internal_user_id,
                            user_id=user_id,
                        )
                except Exception as e:
                    # Log error and fall back to original message
                    #  Error - TODO: add observability
                    # ConversationEvents.MEMORY_LONG_TERM_ENHANCEMENT_FAILED
                    _ = e  # remove this after implementing observability
                    # Fallback to original content using helper method
                    await self._add_to_long_term_memory(
                        content=content,
                        metadata=metadata,
                        internal_user_id=internal_user_id,
                        user_id=user_id,
                    )
            else:
                # For non-user messages, just store directly using helper method
                await self._add_to_long_term_memory(
                    content=content,
                    metadata=metadata,
                    internal_user_id=internal_user_id,
                    user_id=user_id,
                )

            #  Info - TODO: add observability
            # ConversationEvents.MEMORY_LONG_TERM_ENHANCED

    # ===================================================================
    # DOCUMENT PROCESSING ORCHESTRATION
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

        Document Storage Foundation
        - Parse and chunk documents using DocumentChunkManager
        - Store in enhanced buffer memory with DocumentAwareBufferMemory
        - Index for semantic search with ShortTermMemory

        Document User Experience
        - Generate persona-consistent acknowledgments
        - Provide document summaries and error handling

        Document Workflow Integration
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

            #  Info - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_STARTED
            #     f"Processing {len(attachments)} document(s) for user request: "
            #     f"{user_request[:100]}..."
            # )

            # Document Storage Foundation.7)
            processed_docs = await self._process_document_storage_phase(
                attachments, user_id, context
            )

            # Document User Experience.8)
            acknowledgment = await self._process_document_experience_phase(
                processed_docs, user_request, context
            )

            # Document Workflow Integration.9)
            to_return = acknowledgment  # default return value
            if self._requires_document_workflow(user_request):
                workflow_result = await self._process_document_workflow_phase(
                    processed_docs, user_request, context
                )

                # Generate final response with citations
                final_response = await self._generate_final_document_response(
                    acknowledgment, workflow_result, processed_docs
                )
                to_return = final_response

            #  Info - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_COMPLETED

            # Store processed documents for immediate access by agents
            # Get session_id from context or use default
            session_id = (
                context.get("session_id")
                if context and context.get("session_id")
                else self._default_session_id
            )

            # Initialize session storage if needed
            if session_id not in self._recent_documents_by_session:
                # Check if we need to evict old sessions (LRU)
                if len(self._recent_documents_by_session) >= self._max_sessions:
                    # Find and remove the least recently used session
                    # (session with oldest document timestamp)
                    oldest_session = None
                    oldest_time = float("inf")

                    for sid, docs in self._recent_documents_by_session.items():
                        if docs:
                            latest_doc_time = max(d.get("timestamp", 0) for d in docs)
                            if latest_doc_time < oldest_time:
                                oldest_time = latest_doc_time
                                oldest_session = sid
                        else:
                            # Empty session, remove immediately
                            oldest_session = sid
                            break

                    if oldest_session:
                        del self._recent_documents_by_session[oldest_session]

                self._recent_documents_by_session[session_id] = []

            current_request_docs = []
            for doc in processed_docs:
                if doc.get("content"):  # Only store if we have actual content
                    doc_entry = {
                        "doc_id": doc["doc_id"],
                        "filename": doc["filename"],
                        "content": doc["content"],
                        "modality": doc.get("modality", "text"),
                        "timestamp": time.time(),
                        "user_request": user_request,
                        "request_id": context.get("request_id") if context else None,
                        "session_id": session_id,
                    }
                    current_request_docs.append(doc_entry)
                    self._recent_documents_by_session[session_id].append(doc_entry)

            # Ensure we keep at least all documents from current request
            # If current request has more than max_recent_documents, increase the limit temporarily
            min_docs_to_keep = max(
                self._max_recent_documents_per_session, len(current_request_docs)
            )

            # Keep the most recent documents per session, ensuring all from current request are included
            if len(self._recent_documents_by_session[session_id]) > min_docs_to_keep:
                # Remove oldest documents, but keep at least min_docs_to_keep
                self._recent_documents_by_session[session_id] = self._recent_documents_by_session[
                    session_id
                ][-min_docs_to_keep:]

            return to_return

        except Exception as e:
            #  Error - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_FAILED
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
        Document Storage Foundation

        Process and store documents with intelligent chunking and indexing.
        Now supports multimodal content through content type detection.
        """
        processed_docs = []

        for attachment in attachments:
            try:
                filename = attachment.get("filename", "unknown")
                content = attachment.get("content", "")
                content_type = attachment.get("content_type", "text/plain")

                #  Info - TODO: add observability

                # Determine content modality based on content_type
                if content_type.startswith("image/"):
                    # Process image using vision model
                    image_analysis = await self._process_image_content(attachment)
                    # Enhance content with searchable context
                    enhanced_content = (
                        f"Image Analysis of {filename}:\n{image_analysis}\n\n"
                        "[This is an image file containing visual content that has been analyzed. "
                        "The analysis above describes what is visible in the image including objects, "
                        "people, colors, and scenes.]"
                    )
                    chunks = [
                        {
                            "content": enhanced_content,
                            "metadata": {
                                "filename": filename,
                                "modality": "image",
                                "content_type": content_type,
                                "size": len(content),
                                "original_analysis": image_analysis,
                            },
                        }
                    ]

                elif content_type.startswith("audio/"):
                    # Process audio using transcription model
                    audio_analysis = await self._process_audio_content(attachment)
                    chunks = [
                        {
                            "content": audio_analysis,
                            "metadata": {
                                "filename": filename,
                                "modality": "audio",
                                "content_type": content_type,
                                "size": len(content),
                            },
                        }
                    ]

                elif content_type.startswith("video/"):
                    # Process video using video model
                    video_analysis = await self._process_video_content(attachment)
                    chunks = [
                        {
                            "content": video_analysis,
                            "metadata": {
                                "filename": filename,
                                "modality": "video",
                                "content_type": content_type,
                                "size": len(content),
                            },
                        }
                    ]

                else:
                    # Check if we should use MarkItDown for conversion
                    should_use_markitdown = False
                    markitdown_extensions = [".pdf", ".docx", ".pptx", ".xlsx", ".html"]
                    file_ext = os.path.splitext(filename)[1].lower()

                    if file_ext in markitdown_extensions:
                        global _MARKITDOWN_INSTANCE

                        # Thread-safe singleton initialization
                        if _MARKITDOWN_INSTANCE is None:
                            with _MARKITDOWN_LOCK:
                                # Double-check pattern: check again inside the lock
                                if _MARKITDOWN_INSTANCE is None:
                                    _MARKITDOWN_INSTANCE = MarkItDown()

                        markitdown = _MARKITDOWN_INSTANCE
                        should_use_markitdown = True

                    if should_use_markitdown:
                        try:
                            # Convert document to markdown using MarkItDown
                            # Create a temporary file for binary content
                            import tempfile

                            tmp_path = None
                            try:
                                with tempfile.NamedTemporaryFile(
                                    suffix=file_ext, delete=False
                                ) as tmp:
                                    tmp.write(
                                        content if isinstance(content, bytes) else content.encode()
                                    )
                                    tmp_path = tmp.name

                                # Convert with MarkItDown
                                result = markitdown.convert(tmp_path)
                                extracted_content = result.text_content
                            finally:
                                # Always clean up temp file
                                if tmp_path and os.path.exists(tmp_path):
                                    os.unlink(tmp_path)
                            # Now chunk the extracted text
                            if self.document_chunker:
                                doc_chunks = await self.document_chunker.chunk_document(
                                    content=extracted_content,
                                    filename=filename,
                                    strategy="adaptive",
                                )
                                # Convert DocumentChunk objects to expected format
                                chunks = [
                                    {"content": chunk.content, "metadata": chunk.metadata}
                                    for chunk in doc_chunks
                                ]
                            else:
                                # Simple chunking of extracted text
                                chunks = [
                                    {
                                        "content": extracted_content,
                                        "metadata": {"filename": filename, "converted": True},
                                    }
                                ]

                            observability.observe(
                                event_type=observability.SystemEvents.INITIALIZING,
                                level=observability.EventLevel.INFO,
                                data={
                                    "service": "document_processing",
                                    "filename": filename,
                                    "extracted_chars": len(extracted_content),
                                    "file_extension": file_ext,
                                },
                                description=f"Successfully extracted {len(extracted_content)} chars from {filename}",
                            )

                        except Exception as e:
                            observability.observe(
                                event_type=observability.ErrorEvents.GENERIC_ERROR,
                                level=observability.EventLevel.WARNING,
                                data={
                                    "service": "document_processing",
                                    "filename": filename,
                                    "file_extension": file_ext,
                                    "error": str(e),
                                    "fallback": "binary_chunking",
                                },
                                description=f"MarkItDown conversion failed for {filename}: {e}",
                            )
                            # Fall back to binary chunking
                            chunks = [{"content": content, "metadata": {"filename": filename}}]
                    else:
                        # Process as text document using existing chunking
                        if self.document_chunker:
                            doc_chunks = await self.document_chunker.chunk_document(
                                content=content, filename=filename, strategy="adaptive"
                            )
                            # Convert DocumentChunk objects to expected format
                            chunks = [
                                {"content": chunk.content, "metadata": chunk.metadata}
                                for chunk in doc_chunks
                            ]
                        else:
                            # Fallback simple chunking
                            observability.observe(
                                event_type=observability.SystemEvents.INITIALIZING,
                                level=observability.EventLevel.DEBUG,
                                data={
                                    "service": "document_processing",
                                    "filename": filename,
                                    "reason": "document_chunker_not_available",
                                    "fallback": "simple_chunking",
                                },
                                description=f"Using fallback chunking for {filename}",
                            )
                            chunks = [{"content": content, "metadata": {"filename": filename}}]

                # Store metadata
                internal_user_id = None
                if user_id is not None:
                    try:
                        internal_user_id = await self._enhance_existing_user_id_conversion(user_id)
                    except Exception as e:
                        #  Warning - TODO: add observability
                        # ConversationEvents.DOCUMENT_PROCESSING_FAILED
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
                    # Merge chunk metadata with document metadata
                    chunk_specific_metadata = chunk.get("metadata", {})
                    chunk_metadata = {
                        **doc_metadata,
                        **chunk_specific_metadata,  # Include modality-specific metadata
                        "chunk_index": i,
                        "doc_id": doc_id,
                        "role": "document",
                        "timestamp": time.time(),
                        "searchable": True,  # Mark as searchable content
                    }

                    chunk_content = chunk.get("content", "")

                    result = await self.add_to_buffer_memory(
                        message=chunk_content, metadata=chunk_metadata
                    )

                # Add to processed docs list with actual content
                processed_docs.append(
                    {
                        "doc_id": doc_id,
                        "filename": filename,
                        "chunks": len(chunks),
                        "metadata": doc_metadata,
                        "content": [
                            chunk.get("content", "") for chunk in chunks
                        ],  # Store actual content
                        "modality": chunk_specific_metadata.get("modality", "text"),
                    }
                )

            except Exception as e:
                #  Error - TODO: add observability
                # ConversationEvents.DOCUMENT_PROCESSING_FAILED
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
        Document User Experience

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
            #  Error - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_FAILED
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
        Document Workflow Integration

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
                # Search buffer memory for relevant context
                search_results = await self.buffer_memory_manager.search_buffer_memory(
                    query=user_request,
                    k=5,
                    filter_metadata={"role": "document"},  # Search only document chunks
                )
                # Process search results

                if search_results:
                    relevant_content = "\n".join([r["text"] for r in search_results[:3]])
                    return f"Based on the uploaded documents:\n\n{relevant_content}"
                else:
                    # Try without filter to see if documents are in memory at all
                    all_results = await self.buffer_memory_manager.search_buffer_memory(
                        query=user_request, k=5
                    )
                    print(
                        f"All results (no filter): {len(all_results) if all_results else 0} found"
                    )
                    if all_results:
                        print(f"First result metadata: {all_results[0].get('metadata', {})}")

                    return (
                        "I've processed your documents but couldn't find specific "
                        "information related to your request."
                    )

        except Exception as e:
            #  Error - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_FAILED
            import traceback

            print(f"Document workflow error: {e}")
            print(f"Traceback: {traceback.format_exc()}")
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
            #  Error - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_FAILED
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

        Args:
            user_request: The user's request text to analyze

        Returns:
            True if the request suggests document analysis/processing is needed
        """
        # Keywords that suggest the user wants to do something with the documents
        WORKFLOW_KEYWORDS = {
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
        }

        user_request_lower = user_request.lower()
        return any(keyword in user_request_lower for keyword in WORKFLOW_KEYWORDS)

    async def _process_image_content(self, attachment: Dict[str, Any]) -> str:
        """
        Process image content using vision-capable LLM.

        Args:
            attachment: File attachment with image content

        Returns:
            Processed image analysis as text
        """
        try:
            # Validate content size (20MB limit)
            content = attachment.get("content", "")
            if isinstance(content, str):
                content_size = len(content.encode("utf-8"))
            else:
                content_size = len(content) if isinstance(content, bytes) else 0

            max_size = 20 * 1024 * 1024  # 20MB
            if content_size > max_size:
                return f"Image {attachment.get('filename')} exceeds the maximum file size limit of 20MB"
            # Get the vision model from capability models
            vision_model_config = None
            if hasattr(self, "_capability_models") and "vision" in self._capability_models:
                vision_model_config = self._capability_models["vision"]
                print(f"Found vision model config: {vision_model_config}")

            if vision_model_config:
                # Create LLM instance for vision
                from ...services.llm import LLM

                # Get the model name and API key
                model_name = vision_model_config["model"]
                api_key = vision_model_config.get("api_key")

                # If no specific API key, try to get from global keys
                if not api_key and hasattr(self, "_global_api_keys"):
                    # Extract provider from model name (e.g., "openai/gpt-4o-mini" -> "openai")
                    provider = model_name.split("/")[0] if "/" in model_name else "openai"
                    print(f"Looking for API key for provider: {provider}")
                    print(f"Available providers: {list(self._global_api_keys.keys())}")
                    api_key = self._global_api_keys.get(provider)

                if not api_key:
                    return f"No API key found for vision model {model_name}"

                # Create vision LLM instance
                vision_llm = LLM(
                    model=model_name, api_key=api_key, **vision_model_config.get("settings", {})
                )
                # Prepare the message with image
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Please analyze this image and describe what you see in detail. "
                                    "Include objects, people, colors, scene description, "
                                    "and any text visible in the image."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{attachment.get('content_type')};base64,{base64.b64encode(attachment.get('content')).decode() if isinstance(attachment.get('content'), bytes) else attachment.get('content')}"  # noqa: E501
                                },
                            },
                        ],
                    }
                ]

                # Call the vision model
                response = await vision_llm.chat(messages)

                if hasattr(response, "content"):
                    return response.content
                else:
                    return str(response)
            else:
                # No vision model available
                return f"Image {attachment.get('filename')} uploaded but vision analysis is not currently available"

        except Exception as e:
            print(f"Error processing image with vision model: {e}")
            import traceback

            traceback.print_exc()
            return f"Failed to analyze image {attachment.get('filename')}: {str(e)}"

    async def _process_audio_content(self, attachment: Dict[str, Any]) -> str:
        """
        Process audio content using transcription-capable LLM.

        Args:
            attachment: File attachment with audio content

        Returns:
            Processed audio transcription/analysis as text
        """
        try:
            # Validate content size (20MB limit)
            content = attachment.get("content", "")
            if isinstance(content, str):
                content_size = len(content.encode("utf-8"))
            else:
                content_size = len(content) if isinstance(content, bytes) else 0

            max_size = 2 * 1024 * 1024 * 1024  # 2GB
            if content_size > max_size:
                return (
                    f"Audio {attachment.get('filename')} exceeds the maximum file size limit of 2GB"
                )
            # Get the transcription model from capability models
            transcription_model_config = None
            if hasattr(self, "_capability_models") and "audio" in self._capability_models:
                transcription_model_config = self._capability_models["audio"]
                print(f"Found audio/transcription model config: {transcription_model_config}")

            if transcription_model_config:
                # Create LLM instance for transcription
                # Get the model name and API key
                model_name = transcription_model_config["model"]
                api_key = transcription_model_config.get("api_key")

                # If no specific API key, try to get from global keys
                if not api_key and hasattr(self, "_global_api_keys"):
                    # Extract provider from model name (e.g., "openai/whisper-1" -> "openai")
                    provider = model_name.split("/")[0] if "/" in model_name else "openai"
                    api_key = self._global_api_keys.get(provider)

                if not api_key:
                    return f"No API key found for transcription model {model_name}"

                # Create LLM instance for transcription
                transcription_llm = LLM(
                    model=model_name,
                    api_key=api_key,
                    timeout=300.0,  # 5 minutes for large audio processing
                    **transcription_model_config.get("settings", {}),
                )

                # Get the audio content
                audio_content = attachment.get("content")
                filename = attachment.get("filename", "")

                if isinstance(audio_content, str):
                    # If it's base64 encoded, decode it
                    import base64

                    audio_content = base64.b64decode(audio_content)

                # Create a file-like object with proper extension for format detection
                import io

                # Create a BytesIO object and give it a name attribute for format detection
                audio_file = io.BytesIO(audio_content)
                audio_file.name = filename  # This helps onellm detect the format

                # Transcribe the audio
                transcribed_text = await transcription_llm.transcribe(audio_file)

                return f"Audio transcription of {attachment.get('filename')}: {transcribed_text}"
            else:
                # No transcription model available
                return f"Audio {attachment.get('filename')} uploaded but audio transcription is not currently available"

        except Exception as e:
            print(f"Error processing audio with transcription model: {e}")
            import traceback

            traceback.print_exc()
            return f"Failed to transcribe audio {attachment.get('filename')}: {str(e)}"

    def get_document_session_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics about document storage by session.

        Returns:
            Dictionary with session statistics
        """
        stats = {}
        current_time = time.time()

        for session_id, docs in self._recent_documents_by_session.items():
            if docs:
                oldest = min(docs, key=lambda x: x.get("timestamp", 0))
                newest = max(docs, key=lambda x: x.get("timestamp", 0))

                stats[session_id] = {
                    "document_count": len(docs),
                    "oldest_document_age": current_time - oldest.get("timestamp", 0),
                    "newest_document_age": current_time - newest.get("timestamp", 0),
                    "total_size": sum(len(str(doc.get("content", ""))) for doc in docs),
                    "modalities": list(set(doc.get("modality", "text") for doc in docs)),
                }

        return stats

    def get_recent_documents(
        self,
        session_id: Optional[str] = None,
        max_age_seconds: int = 300,
        request_id: Optional[str] = None,
        include_all_sessions: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get recently uploaded documents for agent context.

        Args:
            session_id: Session ID to get documents for (uses default if None)
            max_age_seconds: Maximum age of documents to return (default 5 minutes)
            request_id: Optional request ID to filter documents from a specific request
            include_all_sessions: If True, returns documents from all sessions (for cross-session analysis)

        Returns:
            List of recent documents with their processed content
        """
        current_time = time.time()
        recent_docs = []

        # Determine which sessions to check
        if include_all_sessions:
            sessions_to_check = list(self._recent_documents_by_session.keys())
        else:
            session_id = session_id or self._default_session_id
            sessions_to_check = (
                [session_id] if session_id in self._recent_documents_by_session else []
            )

        # Collect documents from relevant sessions
        for sid in sessions_to_check:
            for doc in self._recent_documents_by_session.get(sid, []):
                # Check age
                if current_time - doc.get("timestamp", 0) > max_age_seconds:
                    continue

                # Check request_id if specified
                if request_id and doc.get("request_id") != request_id:
                    continue

                recent_docs.append(doc)

        # Sort by timestamp (most recent first)
        recent_docs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        return recent_docs

    async def _process_video_content(self, attachment: Dict[str, Any]) -> str:
        """
        Process video content using video-capable LLM.

        Args:
            attachment: File attachment with video content

        Returns:
            Processed video analysis as text
        """
        try:
            # Validate content size (20MB limit)
            content = attachment.get("content", "")
            if isinstance(content, str):
                content_size = len(content.encode("utf-8"))
            else:
                content_size = len(content) if isinstance(content, bytes) else 0

            max_size = 2 * 1024 * 1024 * 1024  # 2GB
            if content_size > max_size:
                return (
                    f"Video {attachment.get('filename')} exceeds the maximum file size limit of 2GB"
                )
            # Get the video model from capability models
            video_model_config = None
            if hasattr(self, "_capability_models") and "video" in self._capability_models:
                video_model_config = self._capability_models["video"]
                print(f"Found video model config: {video_model_config}")

            if video_model_config:
                # Create LLM instance for video
                # Get the model name and API key
                model_name = video_model_config["model"]
                api_key = video_model_config.get("api_key")

                # If no specific API key, try to get from global keys
                if not api_key and hasattr(self, "_global_api_keys"):
                    # Extract provider from model name
                    provider = model_name.split("/")[0] if "/" in model_name else "openai"
                    api_key = self._global_api_keys.get(provider)

                if not api_key:
                    return f"No API key found for video model {model_name}"

                # Create LLM instance for video processing with extended timeout for large files
                video_llm = LLM(
                    model=model_name,
                    api_key=api_key,
                    timeout=300.0,  # 5 minutes for large video processing
                    **video_model_config.get("settings", {}),
                )

                # Get the video content
                video_content = attachment.get("content")
                filename = attachment.get("filename", "video")

                # Send video to the model - video-capable models (like Gemini) will
                # analyze both visual content and audio tracks automatically

                try:
                    # Prepare the message with video content
                    # Some models may accept video directly, others may need frames
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Please analyze this video comprehensively. "
                                        "Include details about scenes, actions, people, objects, "
                                        "any text visible, and the overall context of the video. "
                                        "If the video contains audio, please also transcribe any speech "
                                        "and describe important sounds or music."
                                    ),
                                },
                                {
                                    "type": "image_url",  # Some models accept video as image_url
                                    "image_url": {
                                        "url": f"data:{attachment.get('content_type')};base64,{base64.b64encode(video_content).decode() if isinstance(video_content, bytes) else video_content}"  # noqa: E501
                                    },
                                },
                            ],
                        }
                    ]

                    # Try to analyze as video/image
                    response = await video_llm.chat(messages)

                    if hasattr(response, "content"):
                        video_analysis = response.content
                    else:
                        video_analysis = str(response)

                    return f"Video analysis of {filename}:\n{video_analysis}"

                except Exception as e:
                    # If direct video analysis fails, return a more informative message
                    return (
                        f"Video analysis of {filename} failed: {str(e)}\n\n"
                        f"The model {model_name} may not support video input. "
                        f"For video analysis, please use a video-capable model such as "
                        f"Google Gemini (google/gemini-pro-vision) which can analyze "
                        f"both video content and audio tracks."
                    )
            else:
                # No video model available
                return f"Video {attachment.get('filename')} uploaded but video analysis is not currently available"

        except Exception as e:
            print(f"Error processing video with video model: {e}")
            import traceback

            traceback.print_exc()
            return f"Failed to analyze video {attachment.get('filename')}: {str(e)}"

    # ===================================================================
    # ASYNC REQUEST-RESPONSE ORCHESTRATION)
    # ===================================================================

    async def chat(
        self,
        message: str,
        agent_name: Optional[str] = None,
        user_id: Any = None,
        session_id: Optional[str] = None,  # Optional session ID for tracking
        use_async: Optional[bool] = None,  # None=intelligent, True=force async, False=force sync
        webhook_url: Optional[str] = None,  # Optional webhook URL
        threshold_seconds: Optional[float] = None,  # Optional threshold override
        stream: Optional[bool] = None,  # None=use config, True=force stream, False=no stream
        files: Optional[List[Dict[str, Any]]] = None,  # Optional file attachments
    ) -> Union[str, Dict[str, Any], AsyncGenerator[str, None]]:
        """
        Enhanced chat with async support for long-running agentic tasks and file attachments.

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
            stream: Optional streaming behavior. None=use formation config, True=force streaming,
                False=disable streaming. Only applies to sync processing.
            files: Optional list of file attachments. Each file should be a dict with:
                - filename: Name of the file
                - content: File content (text or bytes)
                - content_type: MIME type of the file
                - size: File size in bytes

        Returns:
            For sync processing: str with the agent's response content, or
                AsyncGenerator if streaming
            For async processing: Dict with request_id, status, and processing info
        """
        return await self.chat_orchestrator.chat(
            message=message,
            agent_name=agent_name,
            user_id=user_id,
            session_id=session_id,
            use_async=use_async,
            webhook_url=webhook_url,
            threshold_seconds=threshold_seconds,
            stream=stream,
            files=files,
        )

    async def _execute_async_request(
        self,
        request_id: str,
        message: str,
        agent_name: Optional[str],
        user_id: Any,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Execute async request in background.

        This method runs the actual chat processing in the background for async requests,
        updating the request tracker with progress and delivering webhook notifications
        upon completion or failure.
        """

        observability.observe(
            event_type=observability.ConversationEvents.ASYNC_PROCESSING_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "request_id": request_id,
                "message_length": len(message),
                "agent_name": agent_name,
                "user_id": str(user_id) if user_id else None,
                "session_id": session_id,
            },
            description=f"Starting async processing for request {request_id}",
        )

        try:
            start_time = time.time()

            # Check if clarification is needed before processing
            try:
                clarification_result = await self._check_clarification_needs_async(
                    message, user_id, agent_name
                )
            except Exception as e:
                print(f"⚠️ Clarification check failed: {type(e).__name__}: {str(e)}")
                clarification_result = None

            if clarification_result:
                clarification_question, clarification_request_id = clarification_result

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
                        #  Info - TODO: add observability
                        # ConversationEvents.CLARIFICATION_REQUEST_SENT
                        #   f"Request {request_id}: Clarification question sent via webhook"
                        # )
                        return  # Exit early, wait for clarification response
                    else:
                        #  Error - TODO: add observability
                        # ConversationEvents.CLARIFICATION_FAILED
                        #     f"Request {request_id}: Failed to send clarification via webhook"
                        # )
                        # Fall back to regular processing
                        await self.request_tracker.update_request(
                            request_id, RequestStatus.PROCESSING
                        )
                else:
                    #  Warning - TODO: add observability
                    # ConversationEvents.CLARIFICATION_FAILED
                    #     f"Request {request_id}: No webhook URL for clarification, "
                    #     "proceeding with regular processing"
                    # )
                    # No webhook available, proceed with regular processing
                    await self.request_tracker.update_request(request_id, RequestStatus.PROCESSING)

            # Process using existing sync infrastructure
            result = await self._process_sync_chat(
                message, agent_name, user_id, session_id=session_id, request_id=request_id
            )
            processing_time = time.time() - start_time

            # Extract result content
            result_content = result.content if hasattr(result, "content") else str(result)
            await self.request_tracker.update_request(
                request_id, RequestStatus.COMPLETED, result=result_content
            )

            # Emit async processing completed event
            observability.observe(
                event_type=observability.ConversationEvents.ASYNC_PROCESSING_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "request_id": request_id,
                    "processing_time": processing_time,
                    "result_size": len(str(result_content)),
                },
                description=f"Request {request_id}: Completed async processing in {processing_time:.2f}s",
            )

            # Emit REQUEST_COMPLETED event for async requests
            # This is needed because the track_request context manager doesn't emit it for async
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "request_id": request_id,
                    "duration_ms": int(processing_time * 1000),
                    "session_id": session_id,
                    "user_id": str(user_id) if user_id else None,
                },
                description=f"Request {request_id} completed in {int(processing_time * 1000)}ms",
            )

            # Send webhook notification if URL is configured
            webhook_url = await self._get_webhook_url_for_request(request_id)
            if webhook_url:
                observability.observe(
                    event_type=observability.ConversationEvents.WEBHOOK_SENT,
                    level=observability.EventLevel.INFO,
                    data={
                        "request_id": request_id,
                        "webhook_url": webhook_url,
                        "result_size": len(str(result_content)),
                        "processing_time": processing_time,
                    },
                    description=f"Starting webhook delivery for request {request_id}",
                )

                success = await self.webhook_manager.deliver_completion(
                    webhook_url=webhook_url,
                    request_id=request_id,
                    result=result_content,
                    processing_time=processing_time,
                    processing_mode="async",  # indicate this was async processing
                    user_id=user_id,  # include user identifier
                    formation_id=self.formation_id,  # include formation identifier
                )

                if success:
                    observability.observe(
                        event_type=observability.ConversationEvents.WEBHOOK_SENT,
                        level=observability.EventLevel.INFO,
                        data={
                            "request_id": request_id,
                            "webhook_url": webhook_url,
                            "delivered": True,
                        },
                        description=f"Webhook delivered successfully for request {request_id}",
                    )
                else:
                    observability.observe(
                        event_type=observability.ConversationEvents.WEBHOOK_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={
                            "request_id": request_id,
                            "webhook_url": webhook_url,
                        },
                        description=f"Webhook delivery failed for request {request_id}",
                    )
            else:
                observability.observe(
                    event_type=observability.ConversationEvents.WEBHOOK_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"request_id": request_id},
                    description=f"Request {request_id}: No webhook URL configured, skipping notification",
                )

            # Auto-remove completed request AFTER webhook delivery
            await self.request_tracker.remove_request(request_id)

        except Exception as e:
            import traceback

            tb = traceback.extract_tb(e.__traceback__)
            last_frame = tb[-1] if tb else None

            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "request_id": request_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc(),
                    "error_line": last_frame.lineno if last_frame else None,
                    "error_file": last_frame.filename if last_frame else None,
                    "processing_mode": "async",
                },
                description=f"Error in async request {request_id}: {type(e).__name__}: {str(e)}",
            )

            await self.request_tracker.update_request(
                request_id, RequestStatus.FAILED, error=str(e)
            )

            # Send failure webhook if URL is configured
            # NOTE: Must get webhook URL BEFORE removing request from tracker
            webhook_url = await self._get_webhook_url_for_request(request_id)
            if webhook_url:
                await self.webhook_manager.deliver_completion(
                    webhook_url=webhook_url,
                    request_id=request_id,
                    error=str(e),
                    processing_mode="async",  # indicate this was async processing
                    user_id=user_id,  # include user identifier
                    formation_id=self.formation_id,  # include formation identifier
                )
                #  Info - TODO: add observability
                # ConversationEvents.WEBHOOK_DELIVERED + ConversationEvents.RESPONSE_DELIVERED
            else:
                #  Error - TODO: add observability
                # ConversationEvents.WEBHOOK_FAILED
                _ = None  # remove this after implementing observability

            # Auto-remove failed request AFTER webhook delivery
            await self.request_tracker.remove_request(request_id)

    async def _process_sync_chat(
        self,
        message: str,
        agent_name: Optional[str],
        user_id: Any,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> MuxiResponse:
        """
        Process chat synchronously using existing infrastructure.

        This method handles the actual chat processing using the existing overlord
        infrastructure for agent selection and message processing. It maintains
        compatibility with the current system while providing a clean interface
        for both sync and async execution paths.

        ENHANCED: Now detects and handles agent clarification requests.
        """
        # Use existing agent selection logic if no specific agent requested
        if agent_name is None:
            # Emit agent selection started event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_AGENT_SELECTION_STARTED,
                level=observability.EventLevel.INFO,
                data={"message": message[:200]},
                description="Starting agent selection process",
            )

            agent_name = await self.select_agent_for_message(message, request_id=request_id)

            # Emit agent selection completed event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_AGENT_SELECTED,
                level=observability.EventLevel.INFO,
                data={"selected_agent": agent_name},
                description=f"Agent selection completed: {agent_name}",
            )

        # Check if overlord is accepting new requests
        if not await self.active_agent_tracker.can_accept_new_requests():
            raise OverlordShuttingDownError(
                "❌ Overlord is shutting down - not accepting new requests"
            )

        # Get the selected agent and process the message
        agent = self.get_agent(agent_name)

        # Mark agent as busy
        await self.active_agent_tracker.mark_agent_busy(agent_name)

        try:
            # ENHANCED: Convert user_id to int using flexible user ID handling
            user_id_int = None
            if user_id is not None:
                # Use enhanced conversion that accepts any external user ID format
                user_id_int = await self._enhance_existing_user_id_conversion(user_id)

            # Process the message using the agent
            result = await agent.process_message(
                message,
                user_id=user_id_int,
                session_id=session_id,
                request_id=request_id,
            )

            # Mark agent as idle
            await self.active_agent_tracker.mark_agent_idle(agent_name)

        except Exception:
            # On error, still mark agent as idle
            await self.active_agent_tracker.mark_agent_idle(agent_name)
            raise
        finally:
            # Clean up request-specific exclusions
            if request_id:
                await self.active_agent_tracker.cleanup_request(request_id)

        # Check if agent response contains clarification request
        agent_clarification = await self._check_agent_clarification_request(result, user_id_int)
        if agent_clarification:
            # Agent needs clarification - transform it into user clarification
            return await self._handle_agent_clarification_request(
                agent_clarification, result, message, agent_name, user_id_int
            )

        return result

    async def _check_agent_clarification_request(
        self, agent_response: MuxiResponse, user_id: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Check if agent response contains a clarification request.

        Args:
            agent_response: The response from the agent
            user_id: User identifier

        Returns:
            Clarification request metadata if found, None otherwise
        """
        try:
            # Check if response has clarification metadata
            if not hasattr(agent_response, "metadata") or not agent_response.metadata:
                return None

            metadata = agent_response.metadata
            if not isinstance(metadata, dict):
                return None

            # Check for agent clarification request structure
            if (
                metadata.get("needs_clarification")
                and metadata.get("clarification_type") == "information_request"
            ):
                return metadata

            return None

        except Exception as e:
            # Log error but don't block processing
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_PROCESSING_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "phase": "agent_clarification_check",
                },
                description=f"Error checking agent clarification request: {str(e)}",
            )
            return None

    async def _handle_agent_clarification_request(
        self,
        clarification_metadata: Dict[str, Any],
        agent_response: MuxiResponse,
        original_message: str,
        agent_name: str,
        user_id_int: Optional[int],
    ) -> MuxiResponse:
        """
        Handle agent clarification request by converting it to user clarification.

        Args:
            clarification_metadata: The clarification request from agent
            agent_response: Original agent response
            original_message: User's original message
            agent_name: Name of the agent requesting clarification
            user_id_int: Internal user ID

        Returns:
            MuxiResponse with clarification question for user
        """
        try:
            # Extract required information from agent request
            required_info = clarification_metadata.get("required_info", {})
            agent_reasoning = clarification_metadata.get("agent_reasoning", "")

            # Generate clarification question for user
            clarification_question = await self._generate_user_clarification_question(
                required_info, agent_reasoning, agent_response.content
            )

            # Create clarification response
            clarification_response = MuxiResponse(
                role="assistant",
                content=clarification_question,
                metadata={
                    "requires_clarification": True,
                    "clarification_source": "agent_request",
                    "agent_name": agent_name,
                    "original_agent_response": agent_response.content,
                    "required_info": required_info,
                    "agent_reasoning": agent_reasoning,
                    "original_message": original_message,
                },
            )

            # Emit clarification event
            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_GENERATED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_name": agent_name,
                    "required_info_categories": list(required_info.keys()),
                    "clarification_source": "agent_request",
                },
                description=f"Agent {agent_name} requested clarification from user",
            )

            return clarification_response

        except Exception as e:
            # Log error and return original response
            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "agent_name": agent_name,
                },
                description=f"Failed to handle agent clarification request: {str(e)}",
            )

            # Return original agent response if clarification handling fails
            return agent_response

    async def _generate_user_clarification_question(
        self, required_info: Dict[str, str], agent_reasoning: str, original_agent_response: str
    ) -> str:
        """
        Generate a user-friendly clarification question from agent requirements.

        Args:
            required_info: Dictionary of required information categories and questions
            agent_reasoning: Agent's reasoning for needing clarification
            original_agent_response: The agent's original response

        Returns:
            Formatted clarification question for the user
        """
        if not required_info:
            return (
                "I need some additional information to help you better. "
                "Could you provide more details?"
            )

        # Create introduction
        intro = (
            "I'd like to help you with that! To provide the most accurate response, "
            "I need some additional information:"
        )

        # Format questions
        questions = []
        for category, question in required_info.items():
            # Ensure question ends with question mark
            if not question.endswith("?"):
                question += "?"
            questions.append(f"• {question}")

        # Combine parts
        clarification_parts = [intro]
        clarification_parts.extend(questions)

        # Add reasoning if provided
        if agent_reasoning:
            clarification_parts.append(f"\n{agent_reasoning}")

        return "\n\n".join(clarification_parts)

    async def process_agent_clarification_response(
        self,
        clarification_response: str,
        clarification_metadata: Dict[str, Any],
        user_id: Any = None,
    ) -> MuxiResponse:
        """
        Process user's response to agent clarification request.

        Args:
            clarification_response: User's response to clarification questions
            clarification_metadata: Original clarification metadata
            user_id: User identifier

        Returns:
            Final response after re-processing with clarification
        """
        try:
            # Extract original context
            original_message = clarification_metadata.get("original_message", "")
            agent_name = clarification_metadata.get("agent_name")

            # Enhance original message with clarification response
            enhanced_message = f"{original_message}\n\nAdditional context: {clarification_response}"

            # Re-process with enhanced message
            result = await self._process_sync_chat(enhanced_message, agent_name, user_id)

            # Emit completion event
            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_name": agent_name,
                    "clarification_source": "agent_request",
                },
                description=f"Agent clarification completed for {agent_name}",
            )

            return result

        except Exception as e:
            # Log error and return error response
            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                },
                description=f"Failed to process agent clarification response: {str(e)}",
            )

            return MuxiResponse(
                role="assistant",
                content=(
                    "I apologize, but I encountered an error processing your additional "
                    "information. Please try again."
                ),
            )

    async def handle_missing_credential(
        self, service: str, user_id: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[ClarificationRequest]:
        """
        Handle missing credential by generating a clarification request.

        This method is called when a MissingCredentialError is raised during
        tool execution. It generates an appropriate clarification request that
        can be presented to the user.

        Args:
            service: The service name that requires credentials (e.g., "github")
            user_id: The user ID who needs to provide credentials
            context: Optional context about why the credential is needed

        Returns:
            ClarificationRequest or None if clarification is disabled
        """
        try:
            # Check if clarification is enabled
            if not self._clarification_config_obj or not self._clarification_config_obj.enabled:
                observability.observe(
                    event_type=observability.ConversationEvents.CLARIFICATION_SKIPPED,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": service,
                        "user_id": user_id,
                        "reason": "clarification_disabled",
                    },
                    description="Clarification disabled - cannot request missing credential",
                )
                return None

            # Import credential handler
            from ..clarification.credential_handler import CredentialClarificationHandler

            # Create credential clarification handler
            handler = CredentialClarificationHandler()

            # Generate clarification request
            clarification_request = handler.generate_credential_request(
                service=service, context=context
            )

            # Store the clarification request for this user/session
            # This allows us to handle the response when it comes back
            session_id = context.get("session_id") if context else None
            if session_id:
                self._pending_clarifications[session_id] = {
                    "type": "credential",
                    "service": service,
                    "user_id": user_id,
                    "request": clarification_request,
                    "handler": handler,
                    "timestamp": time.time(),
                }

            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_REQUESTED,
                level=observability.EventLevel.INFO,
                data={
                    "clarification_type": "credential",
                    "service": service,
                    "user_id": user_id,
                    "has_context": bool(context),
                },
                description=f"Requesting {service} credentials from user",
            )

            return clarification_request

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"service": service, "user_id": user_id, "error": str(e)},
                description=f"Failed to generate credential clarification: {str(e)}",
            )
            return None

    async def process_credential_clarification_response(
        self,
        response: ClarificationResponse,
        service: str,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Process a user's response to a credential clarification request.

        Args:
            response: The clarification response from the user
            service: The service the credential is for
            user_id: The user providing the credential
            session_id: Optional session ID

        Returns:
            True if credential was successfully stored, False otherwise
        """
        try:
            # Get the pending clarification info
            if session_id and session_id in self._pending_clarifications:
                clarification_info = self._pending_clarifications[session_id]
                if (
                    clarification_info.get("type") == "credential"
                    and clarification_info.get("service") == service
                ):
                    handler = clarification_info.get("handler")

                    # Parse the credential from the response
                    if handler:
                        credential_data = handler.parse_credential_response(response, service)

                        if credential_data and self.credential_resolver:
                            # Store the credential
                            await self.credential_resolver.store_credential(
                                user_id=user_id, service=service, credentials=credential_data
                            )

                            # Clean up pending clarification
                            del self._pending_clarifications[session_id]

                            observability.observe(
                                event_type=observability.SystemEvents.CREDENTIAL_UPDATE,
                                level=observability.EventLevel.INFO,
                                data={
                                    "service": service,
                                    "user_id": user_id,
                                    "credential_type": (
                                        list(credential_data.keys())[0]
                                        if credential_data
                                        else "unknown"
                                    ),
                                },
                                description=f"Successfully stored {service} credentials for user",
                            )

                            return True

            return False

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"service": service, "user_id": user_id, "error": str(e)},
                description=f"Failed to process credential clarification response: {str(e)}",
            )
            return False

    async def _process_streaming_chat(
        self,
        message: str,
        agent_name: Optional[str],
        user_id: Any,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Process chat with streaming response.

        This method uses the sync chat processing logic to ensure consistent behavior
        across streaming and non-streaming modes. It processes the request through
        _process_sync_chat to get the complete response, then streams it in chunks.

        Args:
            message: User's message to process
            agent_name: Optional specific agent to use (None for auto-selection)
            user_id: User identifier for memory and context
            session_id: Optional session ID for context
            request_id: Optional request ID for tracking

        Yields:
            str: Content chunks streamed from the complete response

        Note:
            This ensures identical processing logic between streaming and non-streaming
            modes, including agent selection, busy tracking, clarification handling,
            and memory management.
        """
        try:
            # Get the full response using sync processing logic
            # This ensures consistent processing including:
            # - Agent selection and routing
            # - Agent busy/idle tracking
            # - Clarification request handling
            # - Memory context and storage
            # - Error handling
            result = await self._process_sync_chat(
                message=message,
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
            )

            # Extract content from MuxiResponse
            content = result.content if hasattr(result, "content") else str(result)

            # Stream the response in chunks
            chunk_size = 50  # Characters per chunk
            for i in range(0, len(content), chunk_size):
                chunk = content[i:(i + chunk_size)]
                yield chunk
                # Small delay for streaming effect
                await asyncio.sleep(0.01)

        except Exception as e:
            # Handle streaming errors gracefully
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "agent": agent_name, "context": "streaming"},
                description=f"Streaming error: {str(e)}",
            )

            # Yield error message to user
            yield f"Error during streaming: {str(e)}"

    async def _handle_post_streaming_tasks(
        self, message: str, response: str, agent_name: str, user_id_int: Optional[int]
    ) -> None:
        """
        Handle memory storage and observability after streaming completes.

        This method runs asynchronously after streaming to handle tasks that
        shouldn't block the real-time stream, such as memory storage and
        user information extraction.

        Args:
            message: Original user message
            response: Complete response that was streamed
            agent_name: Name of the agent that processed the message
            user_id_int: Internal user ID for memory operations
        """
        try:
            # Add messages to memory
            current_time = time.time()

            # Store user message
            await self.add_message_to_memory(
                content=message,
                role="user",
                timestamp=current_time,
                agent_id=agent_name,
                user_id=user_id_int,
            )

            # Store agent response
            await self.add_message_to_memory(
                content=response,
                role="assistant",
                timestamp=current_time + 0.1,  # Slight offset for ordering
                agent_id=agent_name,
                user_id=user_id_int,
            )

            # Handle user information extraction if enabled
            if user_id_int and user_id_int != 0:  # Skip for anonymous users
                await self.handle_user_information_extraction(
                    user_message=message,
                    agent_response=response,
                    user_id=user_id_int,
                    agent_id=agent_name,
                )

            # Emit completion event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_PROCESSING_COMPLETED,
                level=observability.EventLevel.INFO,
                data={"agent": agent_name, "streaming": True},
                description=f"Streaming chat completed successfully with agent {agent_name}",
            )

        except Exception as e:
            # Log post-processing errors but don't propagate them
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_PROCESSING_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "agent": agent_name, "phase": "post_streaming"},
                description=f"Error in post-streaming tasks: {str(e)}",
            )

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
            #  Error - TODO: add observability
            # ErrorEvents.RESOURCE_UNAVAILABLE
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
            #  Error - TODO: add observability
            # ErrorEvents.RESOURCE_NOT_FOUND
            _ = e  # remove this after implementing observability
            return None

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
                return None

            # Get user context for analysis
            user_id_int = None
            if user_id is not None:
                user_id_int = await self._enhance_existing_user_id_conversion(user_id)

            user_context = {}
            if user_id_int:
                user_context = await self.get_user_context(user_id_int, agent_name)

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
                #  Debug - TODO: add observability
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

                #  Info - TODO: add observability
                return clarification_text, request.request_id

            return None

        except Exception as e:
            #  Warning - TODO: add observability
            # ConversationEvents.CLARIFICATION_FAILED
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

            # Get the request state
            request_state = await self.request_tracker.get_request(request_id)
            if not request_state:
                #  Error - TODO: add observability
                # ConversationEvents.CLARIFICATION_FAILED
                return False

            if request_state.status != RequestStatus.AWAITING_CLARIFICATION:
                #  Error - TODO: add observability
                # ConversationEvents.CLARIFICATION_FAILED
                return False

            # Process the clarification response
            if request_state.clarification_request_id:
                from ..clarification import ClarificationManager

                manager = ClarificationManager(overlord=self)
                result = await manager.process_user_response(
                    request_state.clarification_request_id, clarification_response
                )

                if result.status == ClarificationResultStatus.COMPLETE:
                    # Resume processing with complete parameters
                    #  Info - TODO: add observability
                    # ConversationEvents.CLARIFICATION_COMPLETED
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
                    self._create_tracked_task(
                        self._execute_async_request(
                            request_id,
                            enhanced_message,
                            None,  # Agent already selected
                            request_state.user_id,
                        ),
                        name=f"execute_async_request_{request_id}",
                    )
                    return True

                elif result.status == ClarificationResultStatus.CONTINUE:
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
                            #  Info - TODO: add observability
                            # ConversationEvents.WEBHOOK_SENT + CLARIFICATION_REQUEST_SENT
                            _ = None  # remove this after implementing observability
                            #     f"Request {request_id}: Additional clarification question sent"
                            # )
                        else:
                            #  Error - TODO: add observability
                            # ConversationEvents.WEBHOOK_FAILED + CLARIFICATION_FAILED
                            _ = None  # remove this after implementing observability
                            #     f"Request {request_id}: Failed to send additional clarification"
                            # )

                    return True

                else:
                    #  Error - TODO: add observability
                    # ConversationEvents.CLARIFICATION_FAILED
                    _ = None  # remove this after implementing observability
                    #     f"Request {request_id}: Clarification failed: {result.error_message}"
                    # )

                    # Mark request as failed
                    await self.request_tracker.update_request(
                        request_id,
                        RequestStatus.FAILED,
                        error=f"Clarification failed: {result.error_message}",
                    )

                    # Auto-remove failed request to prevent memory buildup
                    await self.request_tracker.remove_request(request_id)

                    return False

            return False

        except Exception as e:
            #  Error - TODO: add observability
            # ConversationEvents.CLARIFICATION_FAILED
            _ = e  # remove this after implementing observability

            # Mark request as failed on error
            try:

                await self.request_tracker.update_request(
                    request_id, RequestStatus.FAILED, error=f"Clarification processing error: {e}"
                )

                # Auto-remove failed request to prevent memory buildup
                await self.request_tracker.remove_request(request_id)
            except Exception:
                pass  # Avoid nested exceptions

            return False

    async def _enhance_existing_user_id_conversion(self, external_user_id: Any) -> int:
        """
        Enhanced version of existing user ID conversion logic.

        This method accepts external user IDs in any format (string, UUID, integer, etc.)
        and maps them to consistent internal integer IDs for compatibility with existing
        overlord components. The conversion maintains consistency across sessions by:
        1. Normalizing external IDs to string format
        2. Creating deterministic hashes for lookup
        3. Using database storage for persistence
        4. Falling back to synthetic IDs if database fails

        The method handles anonymous users (None/0) by returning 0, maintains a cache
        for performance, and creates new user records as needed.

        Args:
            external_user_id: User ID from external system (any type/format)

        Returns:
            Internal integer user ID for use with existing components:
            - 0 for anonymous users
            - Positive integers for identified users
            - Consistent across multiple calls with same external ID

        Raises:
            No exceptions - uses fallback mechanisms for robustness
        """
        # Handle anonymous users (existing behavior) - return 0 for consistency
        if external_user_id is None or external_user_id == 0:
            return 0

        # Convert to string for consistent processing across all ID types
        external_id_str = normalize_external_id(external_user_id)

        # Use enhanced resolution to get internal ID and isolation key
        internal_id, isolation_key = await self._resolve_flexible_user_id(external_id_str)

        # Return only the internal ID (isolation_key used internally)
        return internal_id

    async def _resolve_flexible_user_id(self, external_id_str: str) -> tuple[int, str]:
        """
        Resolve external user ID to internal ID and isolation key.

        This method converts a normalized external user ID string to an internal integer
        ID and creates an isolation key for database operations. The process involves:
        1. Creating a deterministic hash of the external ID for fast lookups
        2. Checking the overlord's user ID cache for existing mappings
        3. Querying/creating database records if not cached
        4. Generating synthetic IDs as fallback if database operations fail

        The isolation key is used for multi-tenancy and helps isolate user data
        across different external systems or formations.

        Args:
            external_id_str: Normalized external user ID string (already validated)

        Returns:
            Tuple of (internal_id, isolation_key) where:
            - internal_id: Integer ID for use with existing overlord components
            - isolation_key: String key for data isolation and multi-tenancy
        """
        # Create deterministic hash for fast lookup (truncated to 16 chars for storage)
        external_id_hash = hashlib.sha256(external_id_str.encode()).hexdigest()[:16]

        # Check cache first to avoid database queries for repeated lookups
        if external_id_hash in self._user_id_cache:
            cached_record = self._user_id_cache[external_id_hash]
            return cached_record["internal_id"], cached_record["isolation_key"]

        # Find existing user or create new record in database
        user_record = await self._find_or_create_user(external_id_str, external_id_hash)

        # Cache the result to improve performance for subsequent lookups
        self._user_id_cache[external_id_hash] = user_record

        # Return the internal ID and isolation key for use by calling code
        return user_record["internal_id"], user_record["isolation_key"]

    async def _find_or_create_user(self, external_id_str: str, external_id_hash: str) -> dict:
        """
        Find existing user or create new user record.

        This method attempts to find an existing user record in the database using the
        external ID hash. If no record exists, it creates a new user entry with a
        generated nano ID. The method handles various database connection types and
        provides robust fallback behavior if database operations fail.

        The method leverages existing database connections from the overlord's
        long-term memory systems to maintain consistency with the rest of the framework.

        Args:
            external_id_str: Normalized external user ID (original string)
            external_id_hash: Hash of external ID for fast lookup (16 characters)

        Returns:
            User record dict containing:
            - internal_id: Integer ID for database operations
            - isolation_key: String key for multi-tenant data isolation

        Fallback Behavior:
            If database operations fail, generates synthetic IDs based on hash
            to maintain functionality without persistent storage.
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

                    # Generate a nano_id for the user_id column
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
            #  Warning - TODO: add observability
            # ErrorEvents.RESOURCE_NOT_FOUND
            _ = e  # remove this after implementing observability

        # Fallback: generate synthetic internal ID based on hash
        # This maintains functionality even if database operations fail
        MAX_SYNTHETIC_ID = 1000000  # Keep synthetic IDs reasonable
        synthetic_id = abs(hash(external_id_hash)) % MAX_SYNTHETIC_ID

        return {
            "internal_id": synthetic_id,
            "isolation_key": f"user_{synthetic_id}_{external_id_hash[:8]}",
        }

    def _get_builtin_mcp_prompts(self) -> str:
        """
        Get system prompt additions for enabled built-in MCP servers.

        Returns:
            Concatenated system prompts for all enabled built-in MCPs
        """
        # Get runtime configuration from configured services
        runtime_config = self.configured_services.get("runtime_config", {})
        builtin_mcps_config = runtime_config.get("built_in_mcps", True)

        # If built-in MCPs are disabled, return empty string
        if builtin_mcps_config is False:
            return ""

        # Get all available built-in MCPs
        try:
            available_mcps = list_builtin_mcps()

            # Determine which MCPs are enabled
            enabled_mcps = []

            if isinstance(builtin_mcps_config, bool) and builtin_mcps_config:
                # Simple mode - all enabled
                enabled_mcps = list(available_mcps.keys())
            elif isinstance(builtin_mcps_config, list):
                # Granular mode - only specified MCPs
                enabled_mcps = [
                    mcp_name for mcp_name in builtin_mcps_config if mcp_name in available_mcps
                ]

            # Load system prompts for enabled MCPs
            prompts = []

            for mcp_name in enabled_mcps:
                mcp_path = available_mcps[mcp_name]
                # Look for corresponding .md file
                prompt_path = mcp_path.with_suffix(".md")

                if prompt_path.exists():
                    try:
                        with open(prompt_path, "r", encoding="utf-8") as f:
                            prompt_content = f.read().strip()
                            if prompt_content:
                                prompts.append(prompt_content)
                    except Exception as e:
                        # Log warning about failed prompt loading
                        observability.observe(
                            event_type=observability.SystemEvents.BUILTIN_MCP_PROMPT_LOAD_FAILED,
                            level=observability.EventLevel.WARNING,
                            data={
                                "mcp_name": mcp_name,
                                "prompt_path": str(prompt_path),
                                "error": str(e),
                            },
                            description=f"Failed to load system prompt for built-in MCP '{mcp_name}': {e}",
                        )

            # Join all prompts with double newlines
            return "\n\n".join(prompts)

        except Exception as e:
            # Log error and return empty string to not break startup
            observability.observe(
                event_type=observability.SystemEvents.BUILTIN_MCP_INITIALIZATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "builtin_mcps_config": str(builtin_mcps_config)},
                description=f"Failed to initialize built-in MCP prompts: {e}",
            )
            return ""

    async def remember_user_info(
        self,
        user_id: str,
        properties: Union[dict, str],
    ) -> str:
        """Store user properties as contextual memory.

        Args:
            user_id: External user identifier
            properties: Dictionary of user properties to remember, or a string prompt

        Returns:
            A string response confirming the memory was saved
        """
        # Handle both dict and string inputs
        if isinstance(properties, dict):
            # Convert properties to first-person prompt with JSON
            try:
                # Use compact JSON format to minimize tokens
                json_str = json.dumps(properties, separators=(",", ":"), default=str)
            except (TypeError, ValueError) as e:
                # Fallback to string representation if JSON serialization fails
                observability.observe(
                    event_type=observability.SystemEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "properties_type": type(properties).__name__},
                    description="Failed to serialize properties to JSON, using string representation",
                )
                json_str = str(properties)

            prompt = (
                f"Here's my updated information: {json_str}. "
                "Please save this information in your memory. "
                "Once you're done storing this, reply only with 'Memories saved'."
            )
        else:
            # Use string directly as prompt, append instruction
            prompt = (
                f"{properties}. "
                "Please save this information in your memory. "
                "Once you're done storing this, reply only with 'Memories saved'."
            )

        # Use chat function with synchronous mode to ensure completion
        result = await self.chat(user_id=user_id, message=prompt, use_async=False)

        # Handle async generator to ensure non-streaming response
        if hasattr(result, "__aiter__"):
            # Collect all chunks from async generator
            chunks = []
            async for chunk in result:
                chunks.append(chunk)
            return "".join(chunks)

        return result
