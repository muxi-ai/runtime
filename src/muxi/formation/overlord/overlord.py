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
import json
import signal
import sys
from contextlib import contextmanager, suppress
import threading
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union, AsyncGenerator
import os

from ..agents import Agent
from ..background.request_tracker import RequestStatus
from ..clarification import create_clarification_system, ClarificationContext
from .clarification_handler import ClarificationHandler
from ...services import observability
from ...datatypes.response import MuxiResponse
from ...datatypes.clarification import ClarificationRequest, ClarificationResponse, RequestType
from ...services.mcp.service import MCPService
from ...services.memory.working import WorkingMemory
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
from ..initialization import initialize_artifact_service
from ...datatypes.exceptions import RegistryConfigurationError

# A2A models imported when needed
from ...services.secrets.secrets_manager import SecretsManager

# Built-in MCP imports
from ...services.mcp.built_in import list_builtin_mcps

# Enhanced workflow capabilities
from ..workflow import (
    ApprovalManager,
    ProgressTracker,
    RequestAnalyzer,
    TaskDecomposer,
    WorkflowManager,
)
from ..workflow.resilient_executor import ResilientWorkflowExecutor

from ..workflow.config import (
    ComplexityConfig,
    ErrorRecoveryStrategy,
    ObservabilityConfig,
    ResourceConfig,
    RetryConfig,
    RoutingConfig,
    TaskRoutingStrategy,
    TimeoutConfig,
    WorkflowBehaviorConfig,
    WorkflowConfig,
    WorkflowConfigManager,
)

from ...datatypes.workflow import ApprovalStatus, Workflow, WorkflowStatus, RequestAnalysis
from ...datatypes.task_status import TaskStatus

# Utility functions
from ..utils import generate_api_key

# Configuration Management
from .secrets_manager import SecretsInterpolator

# Memory Management
from ..memory import (
    BufferMemoryManager,
    ExtractionCoordinator,
    PersistentMemoryManager,
    UserContextManager,
)

# Dynamic Agent Management
from .active_agents_tracker import ActiveAgentsTracker
from ...datatypes.exceptions import (
    AgentHasDependentsError,
    AgentNotFoundError,
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

# Memory collections that should be created for each user/formation
MEMORY_COLLECTIONS = {
    "conversations": "Stores conversation history and context",
    "user_info": "Stores extracted user information and preferences",
    "tools": "Stores tool usage patterns and results",
    "feedback": "Stores user feedback and ratings",
    "documents": "Stores document content and metadata",
    "workflows": "Stores workflow execution history and patterns",
}

# Define success states for cleaner status checks
SUCCESS_STATES = {TaskStatus.COMPLETED, TaskStatus.DONE}
SUCCESS_STATE_VALUES = {TaskStatus.COMPLETED.value, TaskStatus.DONE.value, "completed", "done"}


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
        buffer_memory (Optional[WorkingMemory]): Working memory for recent context
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
        workflow_manager (WorkflowManager): Centralized workflow state and lifecycle management
    """

    def __init__(
        self,
        # Pre-configured services from Formation
        secrets_manager: Optional[SecretsManager] = None,
        formation_config: Optional[Dict[str, Any]] = None,
        configured_services: Optional[Dict[str, Any]] = None,
        api_keys: Optional[Dict[str, str]] = None,
        # Intelligence-specific parameters
        buffer_memory: Optional[WorkingMemory] = None,
        long_term_memory: Optional[Union[LongTermMemory, Memobase]] = None,
        auto_extract_user_info: bool = True,
        extraction_model: Optional[LLM] = None,
        request_timeout: int = 60,
        # Enhanced workflow parameters (intelligence concerns)
        enable_workflow_by_default: bool = False,
        complexity_threshold: float = 7.0,
        plan_approval_threshold: float = 7.0,
        workflow_config: Optional[WorkflowConfig] = None,
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

            buffer_memory: Optional buffer memory for working context across all agents.
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
        self._agent_expertise: Dict[str, Dict[str, Any]] = {}  # Expertise registry

        # Lock for concurrent agent runtime additions
        # Note: This uses asyncio.Lock which assumes all calls occur within the same event loop.
        # Cross-thread calls are not supported - use the Formation's thread-safe methods instead.
        self._agent_add_lock = asyncio.Lock()

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

        # Initialize A2A cache manager for filtering support
        from ...services.a2a.cache_manager import A2ACacheManager

        self.a2a_cache_manager = A2ACacheManager()

        # A2A coordination system with configuration
        a2a_config = configured_services.get("a2a_config") if configured_services else None
        self.a2a_coordinator = A2ACoordinator(self, config=a2a_config)

        # Initialize A2A ClientFactory for transport management
        self._initialize_a2a_client_factory()

        # Initialize unified A2A messaging
        from .a2a_messaging import UnifiedA2AMessaging

        self.unified_a2a = UnifiedA2AMessaging(self)

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
            if db_manager and hasattr(db_manager, "AsyncSession") and db_manager.AsyncSession:
                # Get text LLM model from formation config
                llm_model = None
                try:
                    llm_config = configured_services.get("llm_config", {})
                    models_config = llm_config.get("models", [])

                    # Find the text model (guaranteed to exist by initialize_llm_config)
                    for model_config in models_config:
                        if isinstance(model_config, dict) and "text" in model_config:
                            llm_model = model_config["text"]
                            break

                    if not llm_model:
                        # This should not happen if initialize_llm_config ran successfully
                        observability.observe(
                            event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                            level=observability.EventLevel.WARNING,
                            data={"error": "Text model not found in LLM config"},
                            description="Expected text model in formation config but not found",
                        )
                except Exception as e:
                    # Log the error but don't fail - credential resolver can work without LLM
                    observability.observe(
                        event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(e), "config_type": "llm_config"},
                        description=f"Error extracting text model from config: {str(e)}",
                    )

                self.credential_resolver = CredentialResolver(
                    async_session_maker=db_manager.AsyncSession,
                    formation_id=self.formation_id,
                    llm_model=llm_model,
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

        # Set extraction_model from formation config if not explicitly provided
        if extraction_model is None and self.formation_config:
            # Check for extraction_model in features section of formation config
            extraction_model = self.formation_config.get("features", {}).get(
                "extraction_model", None
            )

            # If still None, check if we should use the overlord's default LLM model
            if extraction_model is None:
                # Try to get the default model from overlord config
                overlord_config = self.formation_config.get("overlord", {})
                llm_config = overlord_config.get("llm", {})
                default_model = llm_config.get("model")
                if default_model:
                    # We'll create this model later during async initialization
                    # For now, just store the config
                    extraction_model = default_model
                else:
                    # If no overlord config, try to use the first text model from llm.models
                    try:
                        llm_models = self.formation_config.get("llm", {}).get("models", [])
                        for model_config in llm_models:
                            if isinstance(model_config, dict) and "text" in model_config:
                                extraction_model = model_config["text"]
                                break
                    except (TypeError, AttributeError) as e:
                        # Log error but continue - extraction model is optional
                        observability.observe(
                            event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                            level=observability.EventLevel.DEBUG,
                            data={"error": str(e), "config_type": "extraction_model"},
                            description=f"Could not extract text model for extraction: {str(e)}",
                        )

        self.extraction_model = extraction_model
        self.memory_extractor = None  # Will be initialized later

        # Initialize extractor if auto-extraction is enabled
        if self.auto_extract_user_info:
            from ...services.memory.extractor import MemoryExtractor

            # Store default model for extractor fallback
            self.default_model = None  # Will be set during async initialization
            self.extractor = MemoryExtractor(
                overlord=self,
                extraction_model=None,  # Will use default_model fallback
                auto_extract=True,
            )
        else:
            self.extractor = None

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
        self.auto_decomposition = enable_workflow_by_default  # Initialize from parameter
        self.complexity_threshold = complexity_threshold
        self.plan_approval_threshold = plan_approval_threshold

        # Create or use provided workflow configuration
        self.workflow_config = workflow_config or WorkflowConfig(
            complexity=ComplexityConfig(
                threshold=complexity_threshold,
                method="heuristic",  # Default to heuristic
            ),
            error_recovery_strategy=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
        )

        # Initialize workflow configuration manager
        self.workflow_config_manager = WorkflowConfigManager(self.workflow_config)

        # Initialize workflow components with enhanced configuration
        # Note: extraction_model might be a string at this point, not an LLM object
        # We'll update the LLM later in _initialize_extraction_model()
        self.request_analyzer = RequestAnalyzer(
            llm=None,  # Will be set later in _initialize_extraction_model()
            complexity_method=self.workflow_config.complexity_method,
            complexity_threshold=self.workflow_config.complexity_threshold,
            complexity_weights=self.workflow_config.complexity_weights,
        )

        # Initialize planning filter now that request_analyzer is available
        if hasattr(self, "a2a_coordinator") and self.a2a_coordinator:
            self.a2a_coordinator.initialize_planning_filter()

        # TaskDecomposer will be initialized after MCP service is available
        self.approval_manager = ApprovalManager()
        # Use ResilientWorkflowExecutor for better error handling
        self.workflow_executor = ResilientWorkflowExecutor(
            agent_registry=self.agents, config=self.workflow_config
        )
        self.progress_tracker = ProgressTracker()

        # Initialize workflow manager for centralized workflow tracking
        self.workflow_manager = WorkflowManager()

        # Setup progress tracking
        self.workflow_executor.add_progress_callback(self.progress_tracker.update_workflow_progress)

        # Initialize SOP system placeholders - will be set up after workflow config is loaded
        self.sop_system = None
        self._sop_formation_path = None  # Store path for lazy initialization

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

        # Create the complete clarification system
        # create_clarification_system expects (overlord, model) as positional args
        clarification_components = create_clarification_system(
            self, None  # overlord instance  # model will be set later
        )

        # Unpack the components
        self.clarification_analyzer = clarification_components["analyzer"]
        self.clarification_manager = clarification_components["manager"]
        self.clarification_question_generator = clarification_components["generator"]
        self.clarification_response_parser = clarification_components["parser"]
        self.clarification_parameter_enricher = clarification_components["enricher"]
        self.clarification_proactive_detector = clarification_components["proactive_detector"]
        self.clarification_mode_manager = clarification_components["mode_manager"]
        self.clarification_plan_analyzer = clarification_components["plan_analyzer"]

        observability.observe(
            event_type="service.initialized",
            level=observability.EventLevel.INFO,
            data={"service": "clarification", "components": list(clarification_components.keys())},
            description="Clarification system initialized with all components",
        )

        # Initialize the ClarificationHandler with delegation pattern
        self.clarification_handler = ClarificationHandler(self)

        # ===================================================================
        # SERVICE REFERENCES - References to pre-configured services
        # ===================================================================

        # Service references (will be configured from Formation)
        self.external_registry_client: Optional[A2ARegistryClient] = None
        self.inbound_registry_client: Optional[A2ARegistryClient] = None
        self.a2a_server: Optional[A2AServer] = None
        # a2a_cache_manager will be initialized earlier in __init__ at line 385
        self.mcp_service = MCPService.get_instance()  # Get existing instance
        self.scheduler_service: Optional[SchedulerService] = None

        # Initialize TaskDecomposer now that MCP service is available
        self.task_decomposer = TaskDecomposer(
            llm=None, agent_registry=self.agents, mcp_service=self.mcp_service  # Will be set later
        )

        # Initialize agent tracking for delayed external registration
        self.pending_external_registrations = set()

        # Set request timeout
        self.request_timeout = request_timeout

        # Initialize clarification tracking with TTL
        self._clarification_ttl_seconds = 3600  # 1 hour TTL for pending clarifications
        self._clarification_cleanup_interval_seconds = 300  # 5 minutes cleanup check interval
        self._clarification_cleanup_task: Optional[asyncio.Task] = None

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
            level=observability.EventLevel.DEBUG,
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
                    observability.EventLevel.DEBUG
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

    def _ensure_sop_system(self) -> bool:
        """Lazily initialize SOP system if needed.

        Returns:
            True if SOP system is available, False otherwise
        """

        # If already initialized, return its status
        if self.sop_system is not None:
            return self.sop_system.enabled

        # If no path stored, can't initialize
        if not self._sop_formation_path:
            return False

        # Try to initialize now
        try:
            from muxi.formation.workflow.sops import SOPSystem

            self.sop_system = SOPSystem(Path(self._sop_formation_path))

            if self.sop_system.enabled:
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "sop_system",
                        "sop_count": len(self.sop_system.sops),
                        "formation_path": str(self._sop_formation_path),
                        "lazy_init": True,
                    },
                    description=f"SOP system lazily initialized with {len(self.sop_system.sops)} SOPs",
                )
                return True
            else:
                return False

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={
                    "service": "sop_system",
                    "error": str(e),
                    "formation_path": str(self._sop_formation_path),
                },
                description=f"Failed to initialize SOP system: {e}",
            )
            self.sop_system = None
            return False

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

        # Initialize the extraction model (async) if configured
        await self._initialize_extraction_model()

        # Cache manager is already started by Formation
        # No need to start it again

        # Observability system is already initialized and ready (no async start needed)

        # Load agents from formation configuration
        # Load agents from formation's pre-processed configuration
        await self._load_agents_from_formation()

        # Initialize SOP system indexing if enabled
        if self._ensure_sop_system():
            try:
                await self.sop_system.initialize_index()
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "sop_indexing",
                        "sop_count": len(self.sop_system.sops),
                        "indexed": True,
                    },
                    description="SOP system indexed for semantic search",
                )
            except Exception as e:
                # Log but don't fail startup if SOP indexing fails
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={
                        "service": "sop_indexing",
                        "error": str(e),
                    },
                    description=f"SOP indexing failed (will retry on first search): {e}",
                )

        # Initialize registry client if external registry is configured
        if self.a2a_coordinator.external_registry_enabled:
            # Get registry URLs from configuration
            inbound_registries = (
                self.formation_config.get("a2a", {}).get("inbound", {}).get("registries", [])
            )
            outbound_registries = (
                self.formation_config.get("a2a", {}).get("outbound", {}).get("registries", [])
            )

            # Use inbound registries for agent registration, fall back to outbound if not specified
            registry_urls = inbound_registries or outbound_registries

            if registry_urls:
                try:
                    # Use SDK implementation directly (no more backward compatibility)
                    self.inbound_registry_client = A2ARegistryClient(registries=registry_urls)
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                        level=observability.EventLevel.INFO,
                        data={"registries": registry_urls, "implementation": "SDK"},
                        description=(
                            f"Initialized SDK registry client "
                            f"with {len(registry_urls)} registries"
                        ),
                    )

                    # Check registry health according to startup policy
                    if hasattr(self.a2a_coordinator, "config") and self.a2a_coordinator.config:
                        a2a_config = self.a2a_coordinator.config

                        # Collect all registry configs for policy checking
                        all_registry_configs = []
                        for reg in a2a_config.registries:
                            if hasattr(reg, "__dict__"):
                                # RegistryConfig object
                                all_registry_configs.append(
                                    {
                                        "url": reg.url,
                                        "required": reg.required,
                                        "health_check_timeout_seconds": reg.health_check_timeout_seconds,
                                    }
                                )
                            elif isinstance(reg, dict):
                                all_registry_configs.append(reg)
                            else:
                                # String URL
                                all_registry_configs.append({"url": str(reg), "required": False})

                        # Check registries with configured policy
                        should_continue, health_status = (
                            await self.inbound_registry_client.check_registries_with_policy(
                                startup_policy=a2a_config.startup_policy,
                                retry_timeout_seconds=a2a_config.retry_timeout_seconds,
                                registry_configs=all_registry_configs,
                            )
                        )

                        if not should_continue:
                            # Formation should not start due to registry failures
                            unreachable_registries = [
                                url for url, is_healthy in health_status.items() if not is_healthy
                            ]

                            # Log for observability
                            observability.observe(
                                event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                                level=observability.EventLevel.ERROR,
                                data={
                                    "startup_policy": a2a_config.startup_policy,
                                    "health_status": health_status,
                                    "registry_configs": all_registry_configs,
                                },
                                description=(
                                    f"Formation startup aborted: Required registries are "
                                    f"unreachable (policy: {a2a_config.startup_policy})"
                                ),
                            )

                            # Raise a special exception with user-friendly formatting
                            raise RegistryConfigurationError(
                                policy=a2a_config.startup_policy,
                                unreachable_registries=unreachable_registries,
                            )

                        # Log health status for monitoring
                        healthy_count = sum(
                            1 for is_healthy in health_status.values() if is_healthy
                        )
                        unhealthy_count = len(health_status) - healthy_count

                        observability.observe(
                            event_type=observability.SystemEvents.A2A_HEALTH_CHECK_COMPLETED,
                            level=(
                                observability.EventLevel.INFO
                                if healthy_count > 0
                                else observability.EventLevel.WARNING
                            ),
                            data={
                                "healthy_registries": healthy_count,
                                "unhealthy_registries": unhealthy_count,
                                "health_status": health_status,
                                "startup_policy": a2a_config.startup_policy,
                            },
                            description=f"Registry health check complete: {healthy_count}/{len(health_status)} healthy",
                        )

                    # Process pending external agent registrations
                    if (
                        hasattr(self, "pending_external_registrations")
                        and self.pending_external_registrations
                    ):
                        await self.a2a_coordinator.process_pending_registrations()

                except RuntimeError:
                    # Re-raise RuntimeError for policy failures
                    raise
                except RegistryConfigurationError:
                    # Re-raise registry configuration errors - these are critical
                    raise
                except Exception as e:
                    # Log error but don't fail startup - formation can work without external registry
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "registries": registry_urls,
                            "operation": "registry_client_init",
                        },
                        description=(
                            f"Failed to initialize external registry client: {str(e)}. "
                            "Formation will continue without external A2A."
                        ),
                    )
                    # Set to None to indicate registry is not available
                    self.inbound_registry_client = None

        # Update TaskDecomposer with loaded agents
        if hasattr(self, "task_decomposer") and self.task_decomposer:
            self.task_decomposer.agent_registry = self.agents

        # Update workflow executor with loaded agents
        if hasattr(self, "workflow_executor") and self.workflow_executor:
            self.workflow_executor.agent_registry = self.agents

        # Document processing configuration is now initialized by Formation
        if hasattr(self, "_configured_services") and self._configured_services:
            self.document_processing_config = self._configured_services.get(
                "document_processing_config"
            )
            self.document_chunker = self._configured_services.get("document_chunker")

        # A2A services are now initialized by Formation
        # Start A2A formation server if coordinator exists
        if hasattr(self, "a2a_coordinator") and self.a2a_coordinator:
            await self.a2a_coordinator._start_a2a_server()

        # Process pending external agent registrations if available
        if (
            hasattr(self, "inbound_registry_client")
            and self.inbound_registry_client
            and hasattr(self, "pending_external_registrations")
        ):
            await self.a2a_coordinator.process_pending_registrations()

        # MCP servers are now registered by Formation in its event loop
        # Just get the MCP service from configured services
        if hasattr(self, "_configured_services") and self._configured_services:
            mcp_service = self._configured_services.get("mcp_service")
            if mcp_service:
                self.mcp_service = mcp_service
                self.mcp_coordinator = mcp_service  # Alias for compatibility
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.INFO,
                    data={"service": "mcp", "source": "formation"},
                    description="MCP service received from Formation",
                )

        # Initialize artifact service
        formation_instance = getattr(self, "_formation_instance", None)
        if formation_instance:
            try:
                await initialize_artifact_service(formation_instance, self)
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.INFO,
                    data={"service": "artifact"},
                    description="Artifact service initialized",
                )
            except Exception as e:
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={"service": "artifact", "error": str(e)},
                    description=f"Failed to initialize artifact service: {e}",
                )
                # Continue execution even if artifact service fails
        else:
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_WARNING,
                level=observability.EventLevel.WARNING,
                data={"service": "artifact"},
                description="Artifact service not initialized: formation instance not available",
            )

        # Update clarification system components with actual services
        # Update with actual LLM model
        if hasattr(self, "_capability_models") and self._capability_models.get("text"):
            text_config = self._capability_models.get("text")
            if isinstance(text_config, dict) and "model" in text_config:
                # Create actual LLM instance for clarification
                try:
                    clarification_llm = await self.create_model(
                        model=text_config["model"],
                        temperature=0.3,  # Lower temperature for clarification analysis
                        max_tokens=100,   # Small responses for clarification
                        api_key=text_config.get("api_key"),
                    )

                    # Set the LLM for all clarification components
                    self.clarification_analyzer.model = clarification_llm
                    if self.clarification_question_generator:
                        self.clarification_question_generator.model = clarification_llm
                    if self.clarification_proactive_detector:
                        self.clarification_proactive_detector.model = clarification_llm
                    if self.clarification_plan_analyzer:
                        self.clarification_plan_analyzer.model = clarification_llm

                    observability.observe(
                        event_type="service.started",
                        level=observability.EventLevel.INFO,
                        data={"service": "clarification_llm", "model": text_config["model"]},
                        description=f"Created LLM for clarification: {text_config['model']}",
                    )
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(e)},
                        description=f"Failed to create clarification LLM: {e}",
                    )

        # Update with actual managers
        if hasattr(self, "mcp_coordinator") and self.mcp_coordinator:
            mcp_manager = getattr(self.mcp_coordinator, "mcp_manager", None)
            self.clarification_analyzer.mcp_manager = mcp_manager

        if hasattr(self, "buffer_memory_manager"):
            self.clarification_analyzer.memory_manager = self.buffer_memory_manager
            if self.clarification_parameter_enricher:
                self.clarification_parameter_enricher.memory_manager = self.buffer_memory_manager

        observability.observe(
            event_type="service.updated",
            level=observability.EventLevel.INFO,
            data={"service": "clarification", "updated_components": ["llm", "managers"]},
            description="Clarification system updated with actual services",
        )

        # Start clarification cleanup task
        if not self._clarification_cleanup_task or self._clarification_cleanup_task.done():
            self._clarification_cleanup_task = self._create_tracked_task(
                self.clarification_handler.cleanup_stale_clarifications(), name="clarification_cleanup"
            )
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "ttl_seconds": self._clarification_ttl_seconds,
                    "check_interval_seconds": self._clarification_cleanup_interval_seconds,
                },
                description="Started clarification cleanup task",
            )

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

                # Add to pending external registrations if external A2A is enabled
                if self.a2a_coordinator.external_registry_enabled:
                    self.pending_external_registrations.add(agent_id)

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

    @contextmanager
    def _disable_parallel_execution_temporarily(self):
        """
        Context manager to temporarily disable parallel execution for workflows.

        This is particularly useful for SOP workflows that require sequential
        execution to ensure proper data flow between dependent tasks.

        Usage:
            with self._disable_parallel_execution_temporarily():
                # Execute workflow with parallel execution disabled
                result = await self.workflow_executor.execute_workflow(...)
        """
        if not self.workflow_executor or not hasattr(self.workflow_executor, 'config'):
            # No workflow executor or config, nothing to do
            yield
            return

        original_setting = self.workflow_executor.config.behavior.enable_parallel_execution
        try:
            self.workflow_executor.config.behavior.enable_parallel_execution = False
            yield
        finally:
            self.workflow_executor.config.behavior.enable_parallel_execution = original_setting

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

        # Set agent role and specialties from config
        agent.role = agent_config.get("role", "general")
        agent.specialties = agent_config.get("specialties", [])

        # Register agent-specific MCP servers if configured
        # This will fail fast if any MCP server cannot be initialized
        await self._register_agent_mcp_servers(
            agent_config.get("id"), agent_config.get("mcp_servers", [])
        )

        return agent

    def _print_mcp_initialization_error(
        self,
        server_id: str,
        agent_id: str = None,
        error_msg: str = None,
        is_timeout: bool = False,
        is_auth_error: bool = False,
    ) -> None:
        """Print a formatted MCP initialization error message.

        Args:
            server_id: The MCP server ID (required)
            agent_id: The agent ID (optional, None for formation-level MCP)
            error_msg: Optional error message
            is_timeout: Whether this is a timeout error
            is_auth_error: Whether this is an authentication error
        """
        print("\n❌ FORMATION INITIALIZATION FAILED\n")

        if is_timeout:
            print(f"   MCP server '{server_id}' registration timed out after 10 seconds")
            print("   This usually indicates an authentication failure (401)")
        else:
            if agent_id:
                print(f"   Agent: {agent_id}")
            print(f"   MCP Server: {server_id}")
            if is_auth_error:
                print("   Error: Authentication failed (401 Unauthorized)")
            elif error_msg:
                print(f"   Error: {error_msg[:200]}")

        print("\n   📋 TO FIX THIS:")
        print("   1. Check that credentials are configured correctly")
        print("   2. For Linear MCP: Ensure LINEAR_MCP_TOKEN is valid in secrets.enc")
        print("   3. Verify the token has not expired")
        print("   4. Regenerate token if needed")

        if not is_timeout:
            print("\n   Formation cannot start with broken MCP configurations.")
            print("   Please fix the issue and try again.")

        print()

    async def _register_agent_mcp_servers(
        self, agent_id: str, mcp_servers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Register MCP servers for a specific agent.

        Args:
            agent_id: The ID of the agent
            mcp_servers: List of MCP server configurations

        Returns:
            Dict with registration results including failed servers
        """
        results = {"successful": [], "failed": []}

        if not mcp_servers or not self.mcp_service:
            return results

        observability.observe(
            event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_STARTED,
            level=observability.EventLevel.INFO,
            data={"agent_id": agent_id, "server_count": len(mcp_servers)},
            description=f"Registering {len(mcp_servers)} MCP servers for agent {agent_id}",
        )

        for server_config in mcp_servers:
            try:
                server_id = server_config.get("id", "unknown")

                # Skip inactive servers
                if not server_config.get("active", True):
                    continue

                # Prepare registration parameters
                registration_params = {
                    "server_id": server_id,  # Use original server_id for agent-specific registrations
                    "agent_id": agent_id,  # Pass agent ID for proper registration
                }

                # Determine server type and set appropriate parameter
                if "command" in server_config:
                    # Command-based server
                    registration_params["command"] = server_config["command"]
                    if "args" in server_config:
                        registration_params["args"] = server_config["args"]
                elif "url" in server_config:
                    # HTTP/SSE server
                    registration_params["url"] = server_config["url"]
                elif "endpoint" in server_config:
                    # HTTP server with endpoint notation
                    registration_params["url"] = server_config["endpoint"]
                else:
                    continue

                # Add optional parameters
                if "auth" in server_config:
                    registration_params["credentials"] = server_config["auth"]

                if "timeout_seconds" in server_config:
                    registration_params["request_timeout"] = server_config["timeout_seconds"]

                if "type" in server_config:
                    registration_params["transport_type"] = server_config["type"]

                # Register the MCP server with process-level timeout
                # This may raise MCPConnectionError if connection fails
                # Note: MCP library v1.12.3 has issues with 401 errors causing hangs
                # So we use a process-level timeout to detect and handle hangs

                # Create a timeout handler that captures the current server_id
                current_server_id = server_id  # Capture in local scope
                current_agent_id = agent_id  # Capture in local scope

                def timeout_handler(signum, frame):
                    self._print_mcp_initialization_error(
                        server_id=current_server_id, agent_id=current_agent_id, is_timeout=True
                    )
                    sys.exit(1)

                # Use platform-appropriate timeout mechanism
                if hasattr(signal, "SIGALRM"):
                    # Unix/Linux/Mac: Use signal-based timeout
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    try:
                        signal.alarm(10)  # 10-second timeout
                        await self.mcp_service.register_mcp_server(**registration_params)
                    finally:
                        # Always cancel the alarm and restore old handler
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)
                else:
                    # Windows or other platforms: Use asyncio timeout
                    try:
                        await asyncio.wait_for(
                            self.mcp_service.register_mcp_server(**registration_params),
                            timeout=10.0,
                        )
                    except asyncio.TimeoutError:
                        self._print_mcp_initialization_error(
                            server_id=current_server_id, agent_id=current_agent_id, is_timeout=True
                        )
                        sys.exit(1)

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={"agent_id": agent_id, "server_id": server_id},
                    description=f"MCP server {server_id} registered for agent {agent_id}",
                )

                results["successful"].append(server_id)

            except (asyncio.CancelledError, Exception) as e:
                # Fail fast - MCP server registration failed
                server_id = server_config.get("id", "unknown")
                error_msg = str(e)

                # Determine error type for better messaging
                is_auth_error = "401" in error_msg or "unauthorized" in error_msg.lower()
                is_cancelled = "cancelled" in error_msg.lower() or isinstance(
                    e, asyncio.CancelledError
                )

                # Log the error using observability
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "agent_id": agent_id,
                        "server_id": server_id,
                        "error": error_msg,
                        "is_auth_error": is_auth_error,
                        "is_cancelled": is_cancelled,
                    },
                    description=f"Cannot start formation: MCP server '{server_id}' failed for agent '{agent_id}'",
                )

                # Print clear error message using helper
                self._print_mcp_initialization_error(
                    server_id=server_id,
                    agent_id=agent_id,
                    error_msg=error_msg if not (is_auth_error or is_cancelled) else None,
                    is_auth_error=is_auth_error or is_cancelled,
                )

                # Exit the program cleanly to allow proper cleanup
                sys.exit(1)

        return results

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

        # Add artifact system prompt (always enabled)
        from pathlib import Path

        artifact_prompt_path = Path(__file__).parent.parent / "artifacts" / "prompt.md"
        try:
            if artifact_prompt_path.exists():
                artifact_prompt = artifact_prompt_path.read_text(encoding="utf-8")
                system_message += f"\n\n## File Generation (Always Available)\n\n{artifact_prompt}"
        except (IOError, OSError, UnicodeDecodeError) as e:
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_WARNING,
                level=observability.EventLevel.WARNING,
                data={"service": "artifact", "file": str(artifact_prompt_path), "error": str(e)},
                description=f"Failed to read artifact prompt file: {e}",
            )
            # Continue without artifact prompt - system message construction continues gracefully

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

            # Configure overlord behavior from flattened structure

            # Caching configuration
            caching_config = overlord_config.get("caching", {})
            self.routing_cache_enabled = caching_config.get("enabled", True)
            self.routing_cache_ttl = caching_config.get("ttl", 3600)

            # Additional configuration fields from LLM section
            self.max_extraction_tokens = llm_config.get("max_extraction_tokens", 500)

            # Response configuration
            response_config = overlord_config.get("response", {})
            self.response_format = response_config.get("format", "markdown")
            self.use_interactive_elements = response_config.get("interactive_elements", True)
            self.streaming = response_config.get("streaming", True)

            # Resilience is handled by the resilient workflow executor

            # Load workflow configuration
            workflow_config_data = overlord_config.get("workflow", {})

            # Core workflow settings
            self.auto_decomposition = workflow_config_data.get("auto_decomposition", True)
            self.plan_approval_threshold = workflow_config_data.get("plan_approval_threshold", 7)

            # Now that workflow config is loaded, set up SOP system path if workflows are enabled
            if self.auto_decomposition:
                formation_path = self._configured_services.get("formation_path")
                if formation_path:
                    self._sop_formation_path = formation_path
                    observability.observe(
                        event_type=observability.SystemEvents.SERVICE_STARTED,
                        level=observability.EventLevel.INFO,
                        data={
                            "service": "sop_system_init",
                            "auto_decomposition": self.auto_decomposition,
                            "formation_path": str(formation_path),
                            "status": "deferred",
                        },
                        description=f"SOP system initialization deferred (path={formation_path})",
                    )
            if workflow_config_data:
                # Create WorkflowConfig from formation data
                # Parse retry configuration
                retry_data = workflow_config_data.get("retry", {})
                retry_config = RetryConfig(
                    max_attempts=retry_data.get("max_attempts", 3),
                    initial_delay=retry_data.get("initial_delay", 1.0),
                    backoff_factor=retry_data.get("backoff_factor", 2.0),
                    max_delay=retry_data.get("max_delay", 60.0),
                )

                # Parse timeout configuration
                timeout_data = workflow_config_data.get("timeouts", {})
                timeout_config = TimeoutConfig(
                    task_timeout=timeout_data.get("task_timeout", 300.0),
                    workflow_timeout=timeout_data.get("workflow_timeout", 3600.0),
                    phase_timeout=timeout_data.get("phase_timeout", 600.0),
                    enable_adaptive_timeout=timeout_data.get("enable_adaptive_timeout", True),
                    timeout_multiplier=timeout_data.get("timeout_multiplier", 1.5),
                )

                # Create enhanced workflow config with nested structure
                self.workflow_config = WorkflowConfig(
                    complexity=ComplexityConfig(
                        method=workflow_config_data.get("complexity_method", "heuristic"),
                        threshold=workflow_config_data.get(
                            "complexity_threshold", self.complexity_threshold
                        ),
                        weights=workflow_config_data.get(
                            "complexity_weights", {"heuristic": 0.4, "llm": 0.4, "custom": 0.2}
                        ),
                    ),
                    routing=RoutingConfig(
                        strategy=TaskRoutingStrategy(
                            workflow_config_data.get("routing_strategy", "capability_based")
                        ),
                        enable_agent_affinity=workflow_config_data.get(
                            "enable_agent_affinity", True
                        ),
                    ),
                    behavior=WorkflowBehaviorConfig(
                        enable_parallel_execution=workflow_config_data.get(
                            "parallel_execution", True
                        ),
                        max_parallel_tasks=workflow_config_data.get("max_parallel_tasks", 5),
                        enable_partial_results=workflow_config_data.get(
                            "enable_partial_results", True
                        ),
                    ),
                    resources=ResourceConfig(
                        enable_limits=workflow_config_data.get("enable_resource_limits", False),
                        max_memory_per_task_mb=workflow_config_data.get("max_memory_per_task_mb"),
                        max_cpu_per_task=workflow_config_data.get("max_cpu_per_task"),
                    ),
                    observability=ObservabilityConfig(
                        enable_detailed_logging=workflow_config_data.get(
                            "enable_detailed_logging", True
                        ),
                        enable_metrics_collection=workflow_config_data.get(
                            "enable_metrics_collection", True
                        ),
                    ),
                    error_recovery_strategy=ErrorRecoveryStrategy(
                        workflow_config_data.get("error_recovery", "retry_with_backoff")
                    ),
                    retry_config=retry_config,
                    timeout=timeout_config,
                )

                # Update the workflow executor with new config
                if hasattr(self, "workflow_executor"):
                    self.workflow_executor.config = self.workflow_config
                if hasattr(self, "workflow_config_manager"):
                    self.workflow_config_manager.base_config = self.workflow_config
                # Update the request analyzer with new config
                if hasattr(self, "request_analyzer"):
                    self.request_analyzer.complexity_method = self.workflow_config.complexity_method
                    self.request_analyzer.complexity_threshold = (
                        self.workflow_config.complexity_threshold
                    )
                    self.request_analyzer.complexity_weights = (
                        self.workflow_config.complexity_weights
                    )

            # Initialize cache expiry tracking if TTL is configured
            if self.routing_cache_ttl > 0:
                self._routing_cache_expiry: Dict[str, float] = {}

            #  Info - TODO: add observability
            #  SystemEvents.STARTED (overlord routing)
            #     f"✅ Initialized overlord routing with "
            #     f"cache_enabled={self.routing_cache_enabled}, "
            #     f"ttl={self.routing_cache_ttl}, "
            #     f"max_extraction_tokens={self.max_extraction_tokens}, "
            #     f"response_format={self.response_format}, "
            #     f"interactive_elements={self.use_interactive_elements}, "
            #     f"auto_decomposition={self.auto_decomposition}, "
            #     f"plan_approval_threshold={self.plan_approval_threshold}"
            # )

        except Exception as e:
            # If initialization fails, log error and raise
            #  Error - TODO: add observability
            # ErrorEvents.FAILED_INITIALIZATION (overlord routing)
            _ = e  # remove this after implementing observability
            raise RuntimeError("Failed to initialize routing model from overlord.llm config") from e

    async def _initialize_extraction_model(self):
        """Initialize the extraction model as an LLM object if needed."""
        try:
            # Only initialize if extraction_model is a string (model name)
            if self.extraction_model and isinstance(self.extraction_model, str):
                # Get overlord configuration for default settings
                overlord_config = self.formation_config.get("overlord", {})
                llm_config = overlord_config.get("llm", {})

                # Create the extraction model with appropriate settings
                self.extraction_model = await self.create_model(
                    model=self.extraction_model,
                    temperature=llm_config.get("settings", {}).get("temperature", 0.2),
                    max_tokens=llm_config.get("settings", {}).get("max_tokens", 2000),
                    api_key=llm_config.get("api_key"),
                )

                # Re-initialize components that use the extraction model
                if hasattr(self, "request_analyzer"):
                    self.request_analyzer.llm = self.extraction_model
                    observability.observe(
                        event_type=observability.ServerEvents.SERVER_STARTED,
                        level=observability.EventLevel.INFO,
                        data={
                            "component": "request_analyzer",
                            "has_llm": self.request_analyzer.llm is not None,
                        },
                        description=f"Updated request_analyzer LLM: {self.request_analyzer.llm is not None}",
                    )
                if hasattr(self, "task_decomposer"):
                    # Use overlord.llm.model if available, fallback to text model
                    decomposer_model = None

                    # First try: overlord.llm.model
                    if hasattr(self, "routing_model") and self.routing_model:
                        decomposer_model = self.routing_model
                        model_source = "overlord.llm.model"
                    # Second try: text capability model
                    elif hasattr(self, "_capability_models") and "text" in self._capability_models:
                        text_model_config = self._capability_models["text"]
                        if isinstance(text_model_config, dict) and "model" in text_model_config:
                            # Create model instance from text capability
                            decomposer_model = await self.create_model(
                                model=text_model_config["model"],
                                temperature=text_model_config.get("settings", {}).get(
                                    "temperature", 0.7
                                ),
                                max_tokens=text_model_config.get("settings", {}).get(
                                    "max_tokens", 2000
                                ),
                                api_key=text_model_config.get("api_key"),
                            )
                            model_source = "llm.models.text"
                        elif isinstance(text_model_config, str):
                            # Simple string model name
                            decomposer_model = await self.create_model(model=text_model_config)
                            model_source = "llm.models.text"
                    # Final fallback: extraction model
                    else:
                        decomposer_model = self.extraction_model
                        model_source = "extraction_model_fallback"

                    self.task_decomposer.llm = decomposer_model
                    observability.observe(
                        event_type=observability.ServerEvents.SERVER_STARTED,
                        level=observability.EventLevel.INFO,
                        data={
                            "component": "task_decomposer",
                            "has_llm": self.task_decomposer.llm is not None,
                            "model_source": model_source,
                        },
                        description=(
                            f"Updated task_decomposer LLM from {model_source}: "
                            f"{self.task_decomposer.llm is not None}"
                        ),
                    )
                if hasattr(self, "multimodal_fusion_engine"):
                    self.multimodal_fusion_engine.llm = self.extraction_model
                if hasattr(self, "quality_assessor"):
                    self.quality_assessor.llm = self.extraction_model
                if hasattr(self, "context_aware_response_generator"):
                    self.context_aware_response_generator.llm = self.extraction_model

                # Update the extractor's model if it exists
                if hasattr(self, "extractor") and self.extractor and self.auto_extract_user_info:
                    self.extractor.extraction_model = self.extraction_model

                # Also set default_model for fallback
                self.default_model = self.extraction_model

        except Exception as e:
            # If initialization fails, log error but don't fail completely
            # The extraction model is optional
            _ = e  # remove this after implementing observability
            # Just keep the extraction_model as None or string
            pass

    async def _initialize_collections(self):
        """Ensure required collections exist in long-term memory."""
        if self.long_term_memory:
            # Use the predefined collections with their descriptions
            for collection_name, description in MEMORY_COLLECTIONS.items():
                try:
                    # Check if this is a Memobase instance (wraps LongTermMemory)
                    if hasattr(self.long_term_memory, "long_term_memory"):
                        # Access the underlying LongTermMemory instance
                        ltm = self.long_term_memory.long_term_memory

                        # The LongTermMemory class ensures collections exist when adding memories
                        # For PostgreSQL/SQLite backends, collections are created on first use
                        # We'll log the intended collections for visibility
                        observability.observe(
                            event_type=observability.SystemEvents.INITIALIZING,
                            level=observability.EventLevel.DEBUG,
                            data={
                                "collection_name": collection_name,
                                "description": description,
                                "memory_type": "long_term",
                                "backend": type(ltm).__name__,
                            },
                            description=f"Collection '{collection_name}' registered: {description}",
                        )
                    else:
                        # Direct LongTermMemory instance (SQLite)
                        observability.observe(
                            event_type=observability.SystemEvents.INITIALIZING,
                            level=observability.EventLevel.DEBUG,
                            data={
                                "collection_name": collection_name,
                                "description": description,
                                "memory_type": "sqlite",
                                "backend": type(self.long_term_memory).__name__,
                            },
                            description=f"Collection '{collection_name}' registered: {description}",
                        )

                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"collection_name": collection_name, "error": str(e)},
                        description=f"Failed to register collection '{collection_name}': {str(e)}",
                    )

    def _initialize_a2a_client_factory(self):
        """Initialize the A2A ClientFactory with AgentTransport registered."""
        try:
            from a2a.client import ClientFactory, ClientConfig
            from ...services.a2a.agent_transport import AgentTransport

            # Create client factory with default configuration
            config = ClientConfig()
            self.client_factory = ClientFactory(config)

            # Register agent transport for direct agent communication
            agent_transport = AgentTransport(overlord=self)
            self.client_factory.register("agent", agent_transport)

            # Log successful initialization
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.INFO,
                data={
                    "factory": "ClientFactory",
                    "transports": ["agent", "jsonrpc", "rest", "grpc"],
                },
                description="A2A ClientFactory initialized with AgentTransport",
            )

        except Exception as e:
            # Log error but don't fail - A2A is optional
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e)},
                description=f"Failed to initialize A2A ClientFactory: {str(e)}",
            )
            self.client_factory = None

    async def send_a2a_message(
        self,
        source_agent_id: str,
        target_agent_info: Dict[str, Any],
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        wait_for_response: bool = True,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Send A2A message using unified protocol with appropriate transport.

        This method provides the interface for agents to send messages to other agents
        (internal or external) using the same A2A protocol. The transport is determined
        by the target agent's URL.

        Args:
            source_agent_id: ID of the sending agent
            target_agent_info: Agent info dict with 'url' field (agent:// or http://)
            message: Message content (string or dict)
            message_type: Type of message (request, response, etc.)
            context: Optional context data
            wait_for_response: Whether to wait for a response
            timeout: Timeout in seconds

        Returns:
            Response from target agent if wait_for_response is True
        """
        if not target_agent_info.get("url"):
            raise ValueError("Target agent info must include 'url' field")

        return await self.unified_a2a.send_a2a_message(
            source_agent_id=source_agent_id,
            target_agent_url=target_agent_info["url"],
            message=message,
            message_type=message_type,
            context=context,
            wait_for_response=wait_for_response,
            timeout=timeout,
        )

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

        This method stores a message in the working buffer memory, which maintains
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

    async def add_agent_runtime(self, processed_config: Dict[str, Any]) -> None:
        """
        Atomically add a new agent to the overlord at runtime.

        This method handles the complete agent addition process including:
        - Agent creation and validation
        - State updates with proper locking
        - Workflow component updates
        - Rollback on failure

        Note: This method uses asyncio.Lock and assumes all calls occur within
        the same event loop. For cross-thread operations, use Formation's
        thread-safe methods instead.

        Args:
            processed_config: Processed agent configuration dictionary
                            (after secrets processing and validation)

        Raises:
            ValueError: If agent ID is missing or already exists
            RuntimeError: If agent creation fails
        """
        agent_id = processed_config.get("id")
        if not agent_id:
            raise ValueError("Agent configuration missing 'id' field")

        # Acquire lock for thread-safe agent addition
        async with self._agent_add_lock:
            # Check if agent already exists (double-check inside lock)
            if agent_id in self.agents:
                raise ValueError(f"Agent with id '{agent_id}' already exists in overlord")

            # Track original state for rollback
            agent_created = False
            metadata_added = False
            workflow_updated = False

            try:
                # Create the agent instance first (before any mutations)
                agent = await self._create_agent_from_config(processed_config)

                # Now perform all critical mutations together
                # Add to agents dictionary atomically
                self.agents[agent_id] = agent
                agent_created = True

                # Store agent metadata for routing
                self.agent_descriptions[agent_id] = processed_config.get("description", "")
                self.agent_metadata[agent_id] = {
                    "name": processed_config.get("name", agent_id),
                    "role": processed_config.get("role", "general"),
                    "specialties": processed_config.get("specialties", []),
                    "system_message": processed_config.get("system_message", ""),
                }
                metadata_added = True

                # Update workflow components only after all critical operations succeed
                # Store previous state for potential rollback
                prev_agent_registry = None
                if hasattr(self, "task_decomposer") and self.task_decomposer is not None:
                    if hasattr(self.task_decomposer, "agent_registry"):
                        prev_agent_registry = self.task_decomposer.agent_registry.copy()

                await self._update_workflow_components_for_agent(agent_id, agent)
                workflow_updated = True

                # Log successful addition
                observability.observe(
                    event_type=observability.SystemEvents.AGENT_ADDED,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": agent_id,
                        "agent_name": processed_config.get("name", agent_id),
                        "source": processed_config.get("source", "unknown"),
                    },
                    description=f"Agent '{agent_id}' successfully added to overlord at runtime",
                )

            except Exception as e:
                # Rollback on failure - reverse order of operations

                # Rollback workflow components if they were updated
                if workflow_updated:
                    try:
                        # Remove agent from workflow components
                        if hasattr(self, "task_decomposer") and self.task_decomposer is not None:
                            if hasattr(self.task_decomposer, "agent_registry"):
                                # Remove the agent from registry
                                self.task_decomposer.agent_registry.pop(agent_id, None)

                        if hasattr(self, "workflow_executor") and self.workflow_executor is not None:
                            if hasattr(self.workflow_executor, "agent_registry"):
                                self.workflow_executor.agent_registry.pop(agent_id, None)
                    except Exception as rollback_error:
                        # Log rollback failure but continue with other rollbacks
                        observability.observe(
                            event_type=observability.ErrorEvents.WARNING,
                            level=observability.EventLevel.WARNING,
                            data={
                                "agent_id": agent_id,
                                "rollback_error": str(rollback_error),
                            },
                            description=f"Failed to rollback workflow components for agent '{agent_id}'",
                        )

                # Rollback metadata
                if metadata_added:
                    self.agent_metadata.pop(agent_id, None)
                    self.agent_descriptions.pop(agent_id, None)

                # Rollback agent creation
                if agent_created and agent_id in self.agents:
                    del self.agents[agent_id]

                # Log the failure
                observability.observe(
                    event_type=observability.ErrorEvents.AGENT_CREATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "agent_id": agent_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Failed to add agent '{agent_id}' to overlord: {str(e)}",
                )

                # Re-raise with context
                raise RuntimeError(f"Failed to add agent '{agent_id}' to overlord: {str(e)}") from e

    async def _update_workflow_components_for_agent(self, agent_id: str, agent: Any) -> None:
        """
        Update all workflow components when an agent is added.

        This method ensures all workflow-related components are properly updated
        when a new agent is added to the overlord.

        Args:
            agent_id: The ID of the newly added agent
            agent: The agent instance

        Raises:
            AttributeError: If critical workflow components have unexpected structure
        """
        update_failures = []

        # Update task decomposer's agent registry
        if hasattr(self, "task_decomposer") and self.task_decomposer is not None:
            try:
                # Ensure task decomposer has agent_registry attribute
                if not hasattr(self.task_decomposer, "agent_registry"):
                    raise AttributeError(
                        "TaskDecomposer missing expected 'agent_registry' attribute"
                    )

                # Update the registry with current agents
                self.task_decomposer.agent_registry = self.agents

            except AttributeError as e:
                # This is a critical error - the component structure has changed
                update_failures.append(("task_decomposer", e))
                observability.observe(
                    event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={
                        "component": "task_decomposer",
                        "agent_id": agent_id,
                        "error": str(e),
                        "error_type": "AttributeError",
                    },
                    description=f"Task decomposer has unexpected structure: {str(e)}",
                )
            except Exception as e:
                # Log unexpected errors but continue
                observability.observe(
                    event_type=observability.SystemEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "component": "task_decomposer",
                        "agent_id": agent_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Unexpected error updating task decomposer for agent '{agent_id}': {str(e)}",
                )

        # Update workflow executor's agent registry
        if hasattr(self, "workflow_executor") and self.workflow_executor is not None:
            try:
                # Ensure workflow executor has agent_registry attribute
                if not hasattr(self.workflow_executor, "agent_registry"):
                    raise AttributeError(
                        "WorkflowExecutor missing expected 'agent_registry' attribute"
                    )

                # Update the registry with current agents
                self.workflow_executor.agent_registry = self.agents

            except AttributeError as e:
                # This is a critical error - the component structure has changed
                update_failures.append(("workflow_executor", e))
                observability.observe(
                    event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={
                        "component": "workflow_executor",
                        "agent_id": agent_id,
                        "error": str(e),
                        "error_type": "AttributeError",
                    },
                    description=f"Workflow executor has unexpected structure: {str(e)}",
                )
            except Exception as e:
                # Log unexpected errors but continue
                observability.observe(
                    event_type=observability.SystemEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "component": "workflow_executor",
                        "agent_id": agent_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Unexpected error updating workflow executor for agent '{agent_id}': {str(e)}",
                )

        # If there were critical structural errors, raise them
        if update_failures:
            error_msg = "; ".join([f"{comp}: {err}" for comp, err in update_failures])
            raise AttributeError(f"Critical workflow component structure errors: {error_msg}")

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

    async def _deregister_agent_from_external_registry(self, agent_id: str):
        """Helper to deregister a single agent from external registry."""
        if hasattr(self, "a2a_coordinator") and self.a2a_coordinator.external_registry_enabled:
            if hasattr(self, "inbound_registry_client") and self.inbound_registry_client:
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

    async def _deregister_all_agents_from_external_registry(self):
        """Helper to deregister all agents from external registry."""
        if hasattr(self, "a2a_coordinator") and self.a2a_coordinator.external_registry_enabled:
            if hasattr(self, "inbound_registry_client") and self.inbound_registry_client:
                # Deregister all agents concurrently
                # Create a static copy of keys to avoid RuntimeError if dict changes during iteration
                deregistration_tasks = []
                for agent_id in list(self.agents.keys()):
                    task = self.a2a_coordinator.deregister_agent_from_external_registry(agent_id)
                    deregistration_tasks.append(task)

                if deregistration_tasks:
                    # Wait for all deregistrations with timeout
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*deregistration_tasks, return_exceptions=True),
                            timeout=5.0,
                        )
                    except asyncio.TimeoutError:
                        pass  # Continue even if deregistration times out

    async def _actually_delete_agent(self, agent_id: str):
        """Actually delete the agent (called by active_agent_tracker)."""
        if agent_id in self.agents:
            # Deregister from external registries if configured
            self._create_tracked_task(
                self._deregister_agent_from_external_registry(agent_id),
                name=f"deregister_agent_{agent_id}",
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

        # Deregister all agents from external registry before shutdown
        await self._deregister_all_agents_from_external_registry()

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
            user_message: The message to analyze (may be enhanced with context).
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

    async def extract_user_information(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        agent_id: str,
        extraction_model=None,
    ) -> None:
        """Extract user information from conversation (delegates to handle method)."""
        await self.handle_user_information_extraction(
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
        user_id: Optional[str],
    ) -> None:
        """
        Helper method to add content to long-term memory.

        Args:
            content: The content to store
            metadata: Metadata to associate with the content
            user_id: External user ID
        """
        try:
            # Both Memobase and LongTermMemory now use external_user_id
            await self.long_term_memory.add(
                content=content,
                metadata=metadata,
                external_user_id=user_id,
            )
        except Exception as e:
            # Log memory storage error but don't propagate to avoid breaking conversation flow
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "memory_type": type(self.long_term_memory).__name__,
                    "content_length": len(content) if content else 0,
                    "user_id": str(user_id) if user_id else None,
                    "external_user_id": user_id,
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
        # Normalize user_id - lowercase and strip whitespace
        if user_id is not None:
            user_id = str(user_id).lower().strip()

        # Override user_id to "0" for single-user mode (SQLite)
        # This ensures consistent user isolation in single-user deployments
        if not self.is_multi_user:
            user_id = "0"

        # Always add to buffer memory regardless of user context
        if self.buffer_memory_manager:
            metadata = {
                "role": role,
                "timestamp": timestamp,
                "agent_id": agent_id,
                "user_id": str(user_id) if user_id is not None else None,
                "session_id": session_id,
                "request_id": request_id,
            }
            await self.buffer_memory_manager.add_to_buffer_memory(content, metadata, agent_id)

        # NOTE: We do NOT store raw messages in long-term memory
        # Only extracted facts should be in long-term memory
        # Raw messages are stored in buffer memory only

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
        - Index for semantic search with WorkingMemory

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
                doc_metadata = {
                    "filename": filename,
                    "upload_time": time.time(),
                    "user_id": str(user_id) if user_id is not None else None,
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
                    await self.buffer_memory_manager.search_buffer_memory(query=user_request, k=5)

                    return (
                        "I've processed your documents but couldn't find specific "
                        "information related to your request."
                    )

        except Exception:
            #  Error - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_FAILED
            # Document workflow error - logged via observability
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
            # Error processing image - logged via observability
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
            # Error processing audio - logged via observability
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
            # Error processing video - logged via observability
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
        # Override user_id to "0" for single-user mode (SQLite)
        # This ensures consistent user isolation in single-user deployments
        # Do this EARLY before any other processing
        if not self.is_multi_user:
            user_id = "0"
        elif user_id is not None:
            # Normalize user_id - lowercase and strip whitespace
            user_id = str(user_id).lower().strip()

        # Force use_async=False if no webhook URL is configured in formation
        # (and no webhook_url provided in this call)
        async_webhook_url = self.formation_config.get("async", {}).get("webhook_url", webhook_url)
        if use_async is not False and async_webhook_url is None:
            use_async = False

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
                    # Store clarification question in buffer memory before sending webhook
                    try:
                        await self.add_message_to_memory(
                            content=clarification_question,
                            role="assistant",
                            timestamp=time.time(),
                            agent_id="overlord",
                            user_id=user_id,
                            session_id=session_id,
                            request_id=request_id,
                        )
                    except Exception as e:
                        # Log but don't fail on memory storage error
                        print(f"Failed to store clarification question in buffer memory: {e}")

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

            # Store assistant response in buffer memory (fire-and-forget)
            try:
                await self.add_message_to_memory(
                    content=result_content,
                    role="assistant",
                    timestamp=time.time(),
                    agent_id=agent_name or "overlord",
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                )
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_WORKING_UPDATED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "request_id": request_id,
                        "role": "assistant",
                        "async_response": True,
                    },
                    description=f"Stored async response in buffer memory for request {request_id}",
                )
            except Exception as e:
                # Log error but don't fail the async request
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_WORKING_UPDATE_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "request_id": request_id,
                        "error": str(e),
                        "role": "assistant",
                    },
                    description=f"Failed to store async response in buffer memory: {e}",
                )

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

        finally:
            # Auto-remove failed request AFTER webhook delivery
            await self.request_tracker.remove_request(request_id)

            # Always remove from async requests set when the method completes
            # This ensures cleanup happens regardless of success or failure
            self.observability_manager._async_requests.discard(request_id)

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
        # Debug: Entry point
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "_process_sync_chat_entry",
                "agent_name": agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "message_preview": message[:50],
            },
            description=f"_process_sync_chat ENTRY: agent={agent_name}, session={session_id}",
        )
        # Check if this might be a credential response (e.g., GitHub token)
        contains_token = await self.clarification_handler.looks_like_credential_token(message) if session_id else False

        # Check if this might be a clarification response
        is_clarification_response = False
        if session_id and session_id in self._pending_clarifications:
            # If there's a pending clarification, ANY response should be treated as a clarification response
            # What else could it be? The user is responding to our clarification question.
            is_clarification_response = True
            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                level=observability.EventLevel.DEBUG,
                data={
                    "session_id": session_id,
                    "clarification_type": self._pending_clarifications[session_id].get("type"),
                    "is_clarification_response": is_clarification_response,
                },
                description=f"Found pending clarification for session {session_id}",
            )

        if session_id and (contains_token or is_clarification_response):
            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                level=observability.EventLevel.INFO,
                data={
                    "session_id": session_id,
                    "contains_token": contains_token,
                    "is_clarification_response": is_clarification_response,
                    "message_preview": message[:100],
                },
                description="Entering clarification handling block",
            )

            # Check if we have a pending credential request for this session
            if session_id in self._pending_clarifications:
                clarification_info = self._pending_clarifications[session_id]

                if clarification_info.get("type") == "credential":
                    service = clarification_info.get("service")
                    # Store the credential
                    if self.credential_resolver:
                        try:
                            # Store the credential using the correct method
                            # Store as-is: string credentials remain strings, JSON remains JSON
                            # First try to extract token from text
                            extracted_token = await self.clarification_handler.extract_token_from_text(message)
                            if extracted_token:
                                cleaned_message = extracted_token
                            else:
                                cleaned_message = message.strip().strip('"').strip("'")

                            # Check if it looks like JSON
                            try:
                                import json

                                # Try to parse as JSON
                                parsed = json.loads(cleaned_message)
                                # If it's already a dict/list, use it as-is
                                if isinstance(parsed, (dict, list)):
                                    credential_value = parsed
                                else:
                                    # If it parsed to a primitive (string, number, bool), use the original string
                                    credential_value = cleaned_message
                            except (json.JSONDecodeError, ValueError):
                                # Not JSON, store as plain string
                                credential_value = cleaned_message

                            await self.credential_resolver.store_credential(
                                user_id=user_id,
                                service=service,
                                credentials=credential_value,
                                mcp_service=self.mcp_service,
                            )

                            # Asynchronously update credential name with smart discovery
                            # This happens after storage so credentials are available for MCP
                            async def update_credential_name():
                                try:
                                    print(
                                        f"\n\n[DEBUG] Starting async credential name update for {service}/{user_id}"
                                    )
                                    # Re-initialize MCP connection with new credentials
                                    # and discover the account name
                                    await self.credential_resolver.update_credential_name_with_discovery(
                                        user_id=user_id,
                                        service=service,
                                        mcp_service=self.mcp_service,
                                    )
                                except Exception:
                                    # Silent failure - credential still works with generic name
                                    pass

                            # Fire and forget - don't wait for completion
                            asyncio.create_task(update_credential_name())

                            # Get the original message that triggered the clarification
                            original_message = clarification_info.get("original_message")

                            # Clean up pending clarification
                            del self._pending_clarifications[session_id]

                            # If we have the original message, retry it now with credentials stored
                            if original_message:
                                # Recursively call _process_sync_chat with the original message
                                return await self._process_sync_chat(
                                    message=original_message,
                                    user_id=user_id,
                                    session_id=session_id,
                                    request_id=request_id,
                                    agent_name=agent_name,
                                )
                            else:
                                # Fallback if no original message stored
                                return MuxiResponse(
                                    role="assistant",
                                    content=(
                                        f"Thank you! I've saved your {service.capitalize()} credentials. "
                                        "You can now retry your request."
                                    ),
                                )
                        except Exception as e:

                            observability.observe(
                                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                                level=observability.EventLevel.ERROR,
                                data={"error": str(e), "service": service},
                                description=f"Failed to store credential: {str(e)}",
                            )
                            return MuxiResponse(
                                role="assistant",
                                content=(
                                    "I encountered an error saving your credentials. "
                                    "Please try again or contact support if the issue persists."
                                ),
                            )

                elif clarification_info.get("type") == "ambiguous_credential":
                    # Handle ambiguous credential selection response
                    service = clarification_info.get("service")
                    user_id = clarification_info.get("user_id")
                    available_credentials = clarification_info.get("available_credentials", [])
                    ordered_credentials = clarification_info.get("ordered_credentials", [])

                    # Parse the user's selection
                    selected_credential = None
                    try:
                        # Extract just the user's message from the formatted context
                        actual_message = message
                        if "=== CURRENT REQUEST ===" in message and "User:" in message:
                            # Extract the user's actual message from the formatted context
                            lines = message.split("\n")
                            for i, line in enumerate(lines):
                                if line.strip() == "=== CURRENT REQUEST ===" and i + 1 < len(lines):
                                    next_line = lines[i + 1].strip()
                                    if next_line.startswith("User:"):
                                        actual_message = next_line[
                                            5:
                                        ].strip()  # Remove "User: " prefix
                                        break

                        import re

                        numbers = re.findall(r"\d+", actual_message.strip())
                        if numbers:
                            # User selected by number
                            choice_index = int(numbers[0]) - 1  # Convert to 0-based index
                            if ordered_credentials and 0 <= choice_index < len(ordered_credentials):
                                # Use ordered credentials
                                selected_idx = (
                                    ordered_credentials[choice_index] - 1
                                )  # ordered_credentials is 1-based
                                if 0 <= selected_idx < len(available_credentials):
                                    selected_credential = available_credentials[selected_idx]
                            elif 0 <= choice_index < len(available_credentials):
                                # Fallback to original order
                                selected_credential = available_credentials[choice_index]
                        else:
                            # User selected by name
                            message_lower = actual_message.lower().strip()
                            for cred in available_credentials:
                                if (
                                    cred["name"].lower() in message_lower
                                    or message_lower in cred["name"].lower()
                                ):
                                    selected_credential = cred
                                    break

                        if selected_credential and self.credential_resolver:
                            # Debug logging

                            # Store the selected credential in MCP service cache
                            # Get the MCP service - it's a singleton so should be the same everywhere
                            mcp_service = MCPService.get_instance()
                            if mcp_service:
                                # Get server list and check which one matches our service
                                server_ids = await mcp_service.list_servers()

                                # Find the server that matches this service
                                # For GitHub, we expect server_id like "github-mcp"
                                matching_server = None
                                for server_id in server_ids:
                                    if service.lower() in server_id.lower():
                                        matching_server = server_id
                                        break

                                if matching_server:
                                    # Cache the selected credential
                                    if matching_server not in mcp_service.user_credentials:
                                        mcp_service.user_credentials[matching_server] = {}

                                    # Store the resolved credential in the expected format
                                    # Handle both "credential_data" and "credentials" keys
                                    credential_data = selected_credential.get(
                                        "credential_data"
                                    ) or selected_credential.get("credentials")

                                    mcp_service.user_credentials[matching_server][user_id] = {
                                        "type": "bearer",
                                        "token": credential_data,
                                    }

                            # Get the original message and clean up
                            original_message = clarification_info.get("original_message")
                            del self._pending_clarifications[session_id]

                            # Retry the original message with the selected credential
                            if original_message:
                                # Just retry with the original message - the credential is already cached
                                # The agent doesn't need to know about the clarification that happened

                                return await self._process_sync_chat(
                                    message=original_message,
                                    user_id=user_id,
                                    session_id=session_id,
                                    request_id=request_id,
                                    agent_name=agent_name,
                                )
                            else:
                                return MuxiResponse(
                                    role="assistant",
                                    content=(
                                        f"Thank you! I've selected the {selected_credential['name']} account. "
                                        "You can now retry your request."
                                    ),
                                )
                        else:
                            # Selection parsing failed
                            return MuxiResponse(
                                role="assistant",
                                content=(
                                    "I didn't understand your selection. "
                                    "Please respond with a number (e.g., '1') or the account name."
                                ),
                            )

                    except Exception as e:
                        observability.observe(
                            event_type=observability.ErrorEvents.INTERNAL_ERROR,
                            level=observability.EventLevel.ERROR,
                            data={"error": str(e), "service": service},
                            description=f"Failed to process credential selection: {str(e)}",
                        )
                        return MuxiResponse(
                            role="assistant",
                            content="I encountered an error processing your selection. Please try again.",
                        )

                elif clarification_info.get("type") in ["reactive", "proactive"]:
                    # Handle general clarification response through the manager
                    observability.observe(
                        event_type=observability.ConversationEvents.CLARIFICATION_RESPONSE_RECEIVED,
                        level=observability.EventLevel.INFO,
                        data={
                            "session_id": session_id,
                            "clarification_type": clarification_info.get("type"),
                        },
                        description=f"Processing {clarification_info.get('type')} clarification response",
                    )

                    response_result = None
                    if self.clarification_manager:
                        try:
                            response_result = await self.clarification_manager.process_user_response(
                                user_id=str(user_id),
                                request_id=clarification_info.get("request_id"),
                                user_response=message,
                            )
                        except Exception as e:
                            observability.observe(
                                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                                level=observability.EventLevel.WARNING,
                                data={"error": str(e)},
                                description=f"Failed to process clarification response: {e}",
                            )

                    # Fallback if no manager or processing failed
                    if not response_result:
                        # Simple fallback: combine original message with response
                        original_message = clarification_info.get("original_message", "")
                        # Remove trailing punctuation to avoid double periods
                        original_message = original_message.rstrip(".,!?;:")
                        enhanced_message = f"{original_message}. {message}"

                        # Clean up
                        del self._pending_clarifications[session_id]

                        # Process with enhanced context
                        return await self._process_sync_chat(
                            message=enhanced_message,
                            agent_name=agent_name,
                            user_id=user_id,
                            session_id=session_id,
                            request_id=request_id,
                        )

                    if response_result.get("status") == "complete":
                        # Clarification complete - process enhanced request
                        original_message = clarification_info.get("original_message", "")
                        collected_info = response_result.get("collected_info", {})

                        # Enrich the original message with collected information
                        if self.clarification_parameter_enricher and collected_info:
                            try:
                                user_context = {}
                                if hasattr(self, "user_context_manager"):
                                    user_context = await self.user_context_manager.get_user_context(
                                        user_id
                                    )

                                enriched_params = (
                                    await self.clarification_parameter_enricher.enrich_from_context(
                                        missing_params=collected_info,
                                        user_context=user_context,
                                        user_intent=original_message,
                                    )
                                )
                                collected_info.update(enriched_params)
                            except Exception as e:
                                observability.observe(
                                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                                    level=observability.EventLevel.WARNING,
                                    data={"error": str(e)},
                                    description=f"Parameter enrichment failed: {e}",
                                )

                        # Build enhanced message
                        enhanced_message = self._build_enhanced_message(
                            original_message, collected_info
                        )

                        # Clean up
                        del self._pending_clarifications[session_id]

                        observability.observe(
                            event_type=observability.ConversationEvents.CLARIFICATION_COMPLETED,
                            level=observability.EventLevel.INFO,
                            data={"collected_info": list(collected_info.keys())},
                            description="Clarification complete, processing enhanced request",
                        )

                        # Process with enhanced context
                        return await self._process_sync_chat(
                            message=enhanced_message,
                            agent_name=agent_name,
                            user_id=user_id,
                            session_id=session_id,
                            request_id=request_id,
                        )

                    elif response_result.get("status") == "needs_more":
                        # Need more clarification
                        next_question = response_result.get(
                            "next_question", "Could you provide more details?"
                        )

                        # Update pending clarification
                        self._pending_clarifications[session_id]["questions_asked"] = (
                            response_result.get("questions_asked", [])
                        )

                        return MuxiResponse(
                            role="assistant",
                            content=next_question,
                            metadata={
                                "clarification": True,
                                "questions_remaining": response_result.get("questions_remaining"),
                            },
                        )
                    else:
                        # Unexpected status - fallback
                        original_message = clarification_info.get("original_message", "")
                        # Remove trailing punctuation to avoid double periods
                        original_message = original_message.rstrip(".,!?;:")
                        enhanced_message = f"{original_message}. {message}"

                        # Clean up
                        del self._pending_clarifications[session_id]

                        # Process with enhanced context
                        return await self._process_sync_chat(
                            message=enhanced_message,
                            agent_name=agent_name,
                            user_id=user_id,
                            session_id=session_id,
                            request_id=request_id,
                        )

                elif clarification_info.get("type") == "workflow_approval":
                    # Handle workflow approval response
                    observability.observe(
                        event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                        level=observability.EventLevel.INFO,
                        data={
                            "session_id": session_id,
                            "workflow_id": clarification_info.get("workflow_id"),
                            "message": message[:100],
                        },
                        description="Processing workflow approval response",
                    )

                    workflow_id = clarification_info.get("workflow_id")
                    original_message = clarification_info.get("original_message")

                    # Retrieve workflow from pending approvals
                    workflow = self.workflow_manager.get_pending_approval(workflow_id)

                    observability.observe(
                        event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                        level=observability.EventLevel.INFO,
                        data={
                            "workflow_id": workflow_id,
                            "workflow_found": workflow is not None,
                            "pending_approvals_keys": list(
                                self.workflow_manager.pending_approvals.keys()
                            ),
                        },
                        description=f"Looking up workflow {workflow_id} in pending approvals",
                    )

                    if workflow:
                        try:
                            # Process approval response using approval manager
                            # Returns a tuple: (ApprovalStatus, Optional[str])
                            approval_status, instructions = (
                                await self.approval_manager.process_approval_response(
                                    workflow=workflow, user_response=message
                                )
                            )

                            # Handle different approval outcomes
                            if approval_status == ApprovalStatus.APPROVED:
                                # Clean up pending states
                                del self._pending_clarifications[session_id]
                                self.workflow_manager.remove_pending_approval(workflow_id)

                                # NEW: Check if execution should be async now that approval is obtained
                                should_execute_async = await self._should_execute_workflow_async(
                                    workflow, original_message or message
                                )

                                if should_execute_async:
                                    # Execute asynchronously with webhook notification
                                    return await self._execute_workflow_async(
                                        workflow=workflow,
                                        message=original_message or message,
                                        user_id=user_id,
                                        session_id=session_id,
                                        request_id=request_id,
                                    )
                                else:
                                    # Execute synchronously (existing code)
                                    return await self._execute_workflow(
                                        workflow=workflow,
                                        message=original_message or message,
                                        user_id=user_id,
                                        session_id=session_id,
                                        request_id=request_id,
                                    )

                            elif approval_status == ApprovalStatus.REJECTED:
                                # Clean up pending states
                                del self._pending_clarifications[session_id]
                                self.workflow_manager.remove_pending_approval(workflow_id)

                                # Return rejection acknowledgment
                                return MuxiResponse(
                                    role="assistant",
                                    content=(
                                        "I understand. I've cancelled the workflow. "
                                        "Please let me know if you'd like me to try a different approach "
                                        "or if you have a different request."
                                    ),
                                    metadata={
                                        "workflow_cancelled": True,
                                        "workflow_id": workflow_id,
                                    },
                                )

                            elif approval_status == ApprovalStatus.MODIFIED:
                                # For modification requests, we need to handle this differently
                                # since process_approval_response only returns status and instructions
                                # Keep clarification state active and ask for more details
                                return MuxiResponse(
                                    role="assistant",
                                    content=(
                                        "I understand you'd like me to modify the plan. "
                                        f"{instructions if instructions else ''}\n"
                                        "Could you please specify what changes you'd like me to make? "
                                        "For example:\n"
                                        "- Add or remove specific steps\n"
                                        "- Change the order of operations\n"
                                        "- Use different tools or approaches\n"
                                        "- Adjust any parameters or settings"
                                    ),
                                    metadata={
                                        "workflow_id": workflow_id,
                                        "awaiting_modification_details": True,
                                        "requires_user_response": True,
                                    },
                                )

                            elif approval_status == ApprovalStatus.AWAITING_APPROVAL:
                                # Unclear response - ask for clarification
                                return MuxiResponse(
                                    role="assistant",
                                    content=instructions
                                    or (
                                        "I didn't understand your response to the workflow plan. "
                                        "Please respond with:\n"
                                        "- 'yes' or 'proceed' to approve the plan\n"
                                        "- 'no' or 'reject' to cancel it\n"
                                        "- Specific modifications you'd like me to make"
                                    ),
                                    metadata={
                                        "workflow_id": workflow_id,
                                        "approval_required": True,
                                        "requires_user_response": True,
                                    },
                                )
                            else:
                                # Unexpected status
                                return MuxiResponse(
                                    role="assistant",
                                    content=(
                                        "I encountered an unexpected response from the approval system. "
                                        "Please try again."
                                    ),
                                    metadata={
                                        "error": "unexpected_approval_status",
                                        "status": str(approval_status),
                                    },
                                )

                        except Exception as e:
                            observability.observe(
                                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                                level=observability.EventLevel.ERROR,
                                data={"error": str(e), "workflow_id": workflow_id},
                                description=f"Failed to process workflow approval: {str(e)}",
                            )
                            return MuxiResponse(
                                role="assistant",
                                content=(
                                    "I encountered an error processing your approval response. "
                                    "Please try again or let me know if you'd like to start over."
                                ),
                            )
                    else:
                        # Workflow not found - it may have expired or been cleaned up
                        del self._pending_clarifications[session_id]
                        return MuxiResponse(
                            role="assistant",
                            content=(
                                "I couldn't find the workflow you're responding to. "
                                "It may have expired. Please restate your request if you'd like me to try again."
                            ),
                        )

                # Handle general clarifications (reactive/proactive) with multi-turn support
                elif clarification_info.get("type") in ["reactive", "proactive", "multi_turn"]:
                    # Check if we should use the new multi-turn handler
                    # This handles rejection, multi-turn sequences, etc.
                    multi_turn_response = await self.clarification_handler.handle_clarification_response_v2(
                        message=message,
                        session_id=session_id
                    )

                    if multi_turn_response:
                        # Return the clarification response (could be another question, cancellation, etc.)
                        return multi_turn_response
                    else:
                        # None means clarification resolved, continue processing
                        # Get the combined/resolved message to process
                        if isinstance(self._pending_clarifications.get(session_id), ClarificationContext):
                            context = self._pending_clarifications[session_id]
                            # Build combined message from context
                            message = context.original_intent
                            # Message will be processed normally below
                        # If we get here, clarification was resolved and we continue with normal processing

        # ===================================================================
        # CLARIFICATION CHECK - MUST HAPPEN BEFORE ANY AGENT SELECTION
        # ===================================================================
        # Check if clarification is needed for ambiguous requests
        if not is_clarification_response and not agent_name and self.clarification_analyzer:
            # Check for proactive clarification requests first
            proactive_request = None
            if self.clarification_proactive_detector:
                try:
                    proactive_request = (
                        await self.clarification_proactive_detector.detect_proactive_request(
                            message
                        )
                    )
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(e)},
                        description=f"Proactive detection failed: {e}",
                    )

            if proactive_request:
                # Handle proactive clarification mode
                await self.clarification_mode_manager.set_mode(
                    user_id=user_id, mode="proactive", goal=proactive_request.goal
                )

                # Generate first question
                first_question = await self.clarification_question_generator.generate_question(
                    missing_info={"goal_details": "Understanding your requirements"},
                    style=self.clarification_config.style,
                )

                self._pending_clarifications[session_id] = {
                    "type": "proactive",
                    "original_message": message,
                    "mode": "proactive",
                    "user_id": user_id,
                    "created_at": time.time(),
                }

                return MuxiResponse(
                    role="assistant",
                    content=first_question,
                    metadata={"clarification": True, "mode": "proactive"},
                )

            # Analyze for missing information (reactive mode)
            try:
                # Extract the actual user message from formatted context if needed
                actual_message = message
                if "=== CURRENT REQUEST ===" in message and "User:" in message:
                    # Extract the user's actual message from the formatted context
                    lines = message.split("\n")
                    for i, line in enumerate(lines):
                        if line.strip() == "=== CURRENT REQUEST ===" and i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line.startswith("User:"):
                                actual_message = next_line[5:].strip()  # Remove "User: " prefix
                                break

                user_context = {}
                if hasattr(self, "user_context_manager"):
                    user_context = await self.user_context_manager.get_user_context(user_id)

                available_tools = []
                if hasattr(self, "mcp_coordinator"):
                    # Get all tools from the registry
                    tool_registry = self.mcp_coordinator.get_tool_registry()
                    available_tools = []
                    for server_tools in tool_registry.values():
                        available_tools.extend(server_tools.keys())

                analysis_result = await self.clarification_analyzer.analyze_request(
                    user_message=actual_message,  # Use extracted message
                    intent="general",  # Will be inferred from message
                    available_tools=available_tools,
                    user_context=user_context,
                    style=self.clarification_config.style,  # Pass the configured style
                )

                # Check if clarification is needed
                # analysis_result is an InformationAnalysis object, not a dict
                if analysis_result.missing_info:
                    # Create clarification request
                    clarification_request = await self.clarification_manager.start_clarification(
                        user_id=str(user_id),
                        agent_id="overlord",
                        request_type=RequestType.REASONING,
                        intent="general",
                        tool_name=None,
                        provided_info={},
                    )

                    # The first missing_info item now contains the actual clarification question from the LLM
                    if analysis_result.missing_info and isinstance(analysis_result.missing_info[0], str):
                        # Use the question directly from the analyzer
                        question = analysis_result.missing_info[0]
                    else:
                        # Fallback to generic question if something goes wrong
                        question = "Could you please provide more details about what you're looking for?"

                    # Store pending clarification
                    self._pending_clarifications[session_id] = {
                        "type": "reactive",
                        "request_id": clarification_request.request_id,
                        "original_message": message,
                        "missing_info": analysis_result.missing_info,
                        "user_id": user_id,
                        "created_at": time.time(),
                    }

                    return MuxiResponse(
                        role="assistant",
                        content=question,
                        metadata={
                            "clarification": True,
                            "missing_info": (
                                analysis_result.missing_info
                                if isinstance(analysis_result.missing_info, list)
                                else list(analysis_result.missing_info.keys())
                            ),
                        },
                    )
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "traceback": traceback.format_exc()},
                    description=f"Clarification analysis failed: {e}",
                )

        # ===================================================================
        # GENERAL CLARIFICATION CHECK (Before Workflow Analysis)
        # ===================================================================

        # Check if clarification is needed (before workflow analysis)
        if (
            not is_clarification_response
            and not agent_name
            and self.clarification_analyzer
            and session_id
        ):
            try:
                # Check for proactive clarification requests first
                proactive_request = None
                if self.clarification_proactive_detector:
                    proactive_request = (
                        await self.clarification_proactive_detector.detect_proactive_request(
                            message
                        )
                    )

                if proactive_request:
                    # Handle proactive clarification mode
                    if self.clarification_mode_manager:
                        await self.clarification_mode_manager.set_mode(
                            user_id=user_id, mode="proactive", goal=proactive_request.goal
                        )

                    # Generate first question
                    first_question = (
                        "I'd be happy to help you. "
                        "Let me ask you some questions to better understand your needs."
                    )
                    if self.clarification_question_generator:
                        first_question = (
                            await self.clarification_question_generator.generate_question(
                                missing_info={"goal_details": "Understanding your requirements"},
                                style=self.clarification_config.style,
                            )
                        )

                    self._pending_clarifications[session_id] = {
                        "type": "proactive",
                        "original_message": message,
                        "mode": "proactive",
                        "user_id": user_id,
                        "created_at": time.time(),
                    }

                    return MuxiResponse(
                        role="assistant",
                        content=first_question,
                        metadata={"clarification": True, "mode": "proactive"},
                    )

                # Analyze for missing information (reactive mode)
                available_tools = []
                if hasattr(self, "mcp_coordinator") and self.mcp_coordinator:
                    try:
                        # Get all tools from the registry
                        tool_registry = self.mcp_coordinator.get_tool_registry()
                        available_tools = []
                        for server_tools in tool_registry.values():
                            available_tools.extend(server_tools.keys())
                    except Exception:
                        pass  # Continue without tools

                user_context = {}
                if hasattr(self, "user_context_manager"):
                    try:
                        user_context = await self.user_context_manager.get_user_context(user_id)
                    except Exception:
                        pass  # Continue without context

                analysis_result = await self.clarification_analyzer.analyze_request(
                    user_message=message,
                    intent="general",  # Will be inferred from message
                    available_tools=available_tools,
                    user_context=user_context,
                )

                # Check if clarification is needed
                if analysis_result and analysis_result.missing_info:
                    # Create clarification request
                    clarification_request = None
                    if self.clarification_manager:
                        clarification_request = (
                            await self.clarification_manager.start_clarification(
                                user_id=str(user_id),
                                agent_id="overlord",
                                request_type=RequestType.REASONING,
                                intent="general",
                                tool_name=None,
                                provided_info={},
                            )
                        )

                    # Generate clarification question
                    question = "Could you please provide more details?"
                    if self.clarification_question_generator:
                        # For reasoning clarification, use the first missing info item
                        missing_context = (
                            analysis_result.missing_info[0]
                            if analysis_result.missing_info
                            else "more details"
                        )
                        question_obj = await self.clarification_question_generator.generate_reasoning_question(
                            intent="general",
                            missing_context=missing_context,
                            user_background={},
                            style=self.clarification_config.style
                        )
                        question = question_obj.question_text

                    # Store pending clarification
                    self._pending_clarifications[session_id] = {
                        "type": "reactive",
                        "request_id": (
                            clarification_request.request_id if clarification_request else None
                        ),
                        "original_message": message,
                        "missing_info": analysis_result.missing_info,
                        "user_id": user_id,
                        "created_at": time.time(),
                    }

                    observability.observe(
                        event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                        level=observability.EventLevel.INFO,
                        data={
                            "missing_info": (
                                analysis_result.missing_info
                                if isinstance(analysis_result.missing_info, list)
                                else list(analysis_result.missing_info.keys())
                            ),
                            "question": question[:100],
                        },
                        description="General clarification needed",
                    )

                    return MuxiResponse(
                        role="assistant",
                        content=question,
                        metadata={
                            "clarification": True,
                            "missing_info": (
                                analysis_result.missing_info
                                if isinstance(analysis_result.missing_info, list)
                                else list(analysis_result.missing_info.keys())
                            ),
                        },
                    )

            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e)},
                    description=f"Clarification check failed: {e}",
                )
                # Continue without clarification on error

        # ===================================================================
        # WORKFLOW ANALYSIS AND DECOMPOSITION
        # ===================================================================

        observability.observe(
            event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
            level=observability.EventLevel.INFO,
            data={
                "session_id": session_id,
                "agent_name": agent_name,
                "auto_decomposition": self.auto_decomposition,
                "is_clarification_response": is_clarification_response,
                "has_pending_clarifications": (
                    session_id in self._pending_clarifications if session_id else False
                ),
                "message_preview": message[:100],
            },
            description="Checking workflow analysis conditions",
        )

        # Debug: Immediate next step
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "debug_next_step",
                "checkpoint": "after_checking_conditions",
            },
            description="DEBUG: About to evaluate workflow conditions",
        )

        # Check if we should analyze for workflow complexity
        # Only trigger if:
        # 1. No specific agent was requested (agent_name is None)
        # 2. auto_decomposition is enabled
        # 3. Not a clarification response

        # Debug: Log the decision with more detail
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "workflow_analysis_decision",
                "agent_name": agent_name,
                "agent_name_is_none": agent_name is None,
                "auto_decomposition": self.auto_decomposition,
                "is_clarification_response": is_clarification_response,
                "should_analyze": agent_name is None
                and self.auto_decomposition
                and not is_clarification_response,
                "session_id": session_id,
                "has_pending_clarifications": (
                    session_id in self._pending_clarifications if session_id else False
                ),
                "message_preview": message[:50],
            },
            description=(
                f"WORKFLOW DECISION: agent_name={agent_name}, auto_decomp={self.auto_decomposition}, "
                f"clarification={is_clarification_response}, "
                f"SHOULD_TRIGGER={agent_name is None and self.auto_decomposition and not is_clarification_response}"
            ),
        )

        # Check for workflow analysis and decomposition (complexity-based routing)
        if agent_name is None and self.auto_decomposition and not is_clarification_response:
            # Analyze request complexity
            try:
                analysis = await self.request_analyzer.analyze_request(message)

                # Check if complexity exceeds threshold
                # Use workflow config threshold if available, otherwise fall back to overlord threshold
                threshold = (
                    self.workflow_config.complexity_threshold
                    if hasattr(self, "workflow_config")
                    else self.complexity_threshold
                )

                # Debug logging
                observability.observe(
                    event_type=observability.ServerEvents.SERVER_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "workflow_analysis_result",
                        "complexity_score": analysis.complexity_score,
                        "threshold": threshold,
                        "exceeds_threshold": analysis.complexity_score >= threshold,
                        "requires_decomposition": analysis.requires_decomposition,
                        "requires_approval": analysis.requires_approval,
                    },
                    description=(
                        f"Workflow analysis: score={analysis.complexity_score}, "
                        f"threshold={threshold}, trigger={analysis.complexity_score >= threshold}"
                    ),
                )

                if analysis.complexity_score >= threshold:
                    # Process with workflow orchestration
                    return await self._process_with_workflow(
                        message=message,
                        analysis=analysis,
                        user_id=user_id,
                        session_id=session_id,
                        request_id=request_id,
                    )
            except Exception as e:
                # Log error but continue with normal flow
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "phase": "workflow_analysis"},
                    description=f"Failed to analyze request for workflow: {str(e)}",
                )
                # Fall through to normal agent selection

        # Use existing agent selection logic if no specific agent requested
        if agent_name is None:
            # Add debug info about why we're here
            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                level=observability.EventLevel.WARNING,
                data={
                    "session_id": session_id,
                    "is_clarification_response": is_clarification_response,
                    "has_pending_clarifications": (
                        session_id in self._pending_clarifications if session_id else False
                    ),
                    "pending_clarification_type": (
                        self._pending_clarifications.get(session_id, {}).get("type")
                        if session_id and session_id in self._pending_clarifications
                        else None
                    ),
                    "message": message[:100],
                },
                description="Agent selection triggered - check if this should have been handled as clarification",
            )

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
            # Process the message using the agent
            result = await agent.process_message(
                message,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
            )

            # Mark agent as idle
            await self.active_agent_tracker.mark_agent_idle(agent_name)

        except Exception as e:
            # On error, still mark agent as idle
            await self.active_agent_tracker.mark_agent_idle(agent_name)

            # Check if this is a credential error that needs clarification
            from ..memory.credential_resolver import (
                MissingCredentialError,
                AmbiguousCredentialError,
            )

            if isinstance(e, MissingCredentialError):
                # Store pending clarification if we have a session
                if session_id:
                    self._pending_clarifications[session_id] = {
                        "type": "credential",
                        "service": e.service,
                        "user_id": e.user_id,
                        "timestamp": time.time(),
                        "original_message": message,
                    }

                # Return a simple response asking for credentials

                service_display = e.service.capitalize()
                if e.service == "github":
                    service_display = "GitHub"

                return MuxiResponse(
                    role="assistant",
                    content=(
                        f"I need access to your {service_display} credentials to complete this task. "
                        f"Could you please provide your {service_display} personal access token?"
                    ),
                    metadata={
                        "clarification_requested": True,
                        "clarification_type": "missing_credential",
                        "service": e.service,
                        "user_id": e.user_id,
                        "session_id": session_id,
                    },
                )

            elif isinstance(e, AmbiguousCredentialError):
                # Store pending clarification if we have a session
                if session_id:
                    self._pending_clarifications[session_id] = {
                        "type": "ambiguous_credential",
                        "service": e.service,
                        "user_id": e.user_id,
                        "timestamp": time.time(),
                        "original_message": message,
                        "available_credentials": e.available_credentials,
                        "ordered_credentials": e.ordered_credentials,
                    }
                else:
                    # No session_id, log warning
                    pass

                # Generate clarification question
                service_display = e.service.capitalize()
                if e.service == "github":
                    service_display = "GitHub"

                # Format the credential options
                if e.ordered_credentials:
                    # Use LLM ordering
                    ordered_names = []
                    for idx in e.ordered_credentials:
                        if 1 <= idx <= len(e.available_credentials):
                            ordered_names.append(e.available_credentials[idx - 1]["name"])
                else:
                    # Fallback to original order
                    ordered_names = [cred["name"] for cred in e.available_credentials]

                options_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(ordered_names)])

                return MuxiResponse(
                    role="assistant",
                    content=(
                        f"I found multiple {service_display} accounts for you. "
                        f"Which account would you like to use?\n\n"
                        f"Available accounts:\n{options_text}"
                    ),
                    metadata={
                        "clarification_requested": True,
                        "clarification_type": "ambiguous_credential",
                        "service": e.service,
                        "user_id": e.user_id,
                        "session_id": session_id,
                    },
                )

            raise
        finally:
            # Clean up request-specific exclusions
            if request_id:
                await self.active_agent_tracker.cleanup_request(request_id)

        # Check if agent response contains clarification request
        agent_clarification = await self._check_agent_clarification_request(result, user_id)
        if agent_clarification:
            # Agent needs clarification - transform it into user clarification
            return await self._handle_agent_clarification_request(
                agent_clarification, result, message, agent_name, user_id
            )

        return result

    async def would_need_workflow_approval(self, message: str, agent_name: Optional[str]) -> bool:
        """
        Quick check if request would need workflow approval.

        This is used by the async decision logic to avoid going async
        before user approval is obtained.
        """
        # No workflow if auto_decomposition disabled or specific agent requested
        if not self.auto_decomposition or agent_name is not None:
            return False

        try:
            # Use existing request analyzer
            analysis = await self.request_analyzer.analyze_request(message)

            # Would need approval if complex enough for workflow AND approval
            return (
                analysis.complexity_score >= self.complexity_threshold
                and analysis.complexity_score >= self.plan_approval_threshold
            )
        except Exception:
            # If analysis fails, assume no approval needed (safe default)
            return False

    async def _process_with_workflow(
        self,
        message: str,
        analysis: RequestAnalysis,
        user_id: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        stream: bool = False,
    ) -> Union[MuxiResponse, AsyncGenerator[str, None]]:
        """
        Process a complex request using workflow orchestration.

        This method handles requests that exceed the complexity threshold by:
        1. Determining if user approval is needed based on plan_approval_threshold
        2. Decomposing the request into a multi-agent workflow
        3. Either executing immediately or routing through approval flow

        Args:
            message: The user's original message
            analysis: RequestAnalysis object containing complexity score and decomposition hints
            user_id: User identifier
            session_id: Optional session identifier
            request_id: Optional request identifier
            stream: If True, stream workflow execution progress

        Returns:
            If stream=False: MuxiResponse containing either workflow results or approval request
            If stream=True: AsyncGenerator yielding progress updates
        """
        # Validate inputs
        self._validate_workflow_inputs(message, user_id, session_id, request_id)
        self._validate_workflow_analysis(analysis)

        try:
            # Emit workflow orchestration started event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_WORKFLOW_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "complexity_score": analysis.complexity_score,
                    "user_id": user_id,
                    "session_id": session_id,
                    "workflow_triggered": True,
                },
                description=f"Starting workflow orchestration (complexity: {analysis.complexity_score})",
            )

            # Determine if approval is needed
            needs_approval = analysis.complexity_score >= self.plan_approval_threshold

            observability.observe(
                event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                level=observability.EventLevel.INFO,
                data={
                    "complexity_score": analysis.complexity_score,
                    "plan_approval_threshold": self.plan_approval_threshold,
                    "needs_approval": needs_approval,
                    "message_preview": message[:100],
                },
                description=f"Workflow approval decision: {'REQUIRED' if needs_approval else 'NOT REQUIRED'}",
            )

            # Check for relevant SOPs (only if SOP system exists and is enabled)
            workflow = None
            if self._ensure_sop_system():
                relevant_sops = await self.sop_system.find_relevant_sops(message, top_k=1)
                relevant_sop = relevant_sops[0] if relevant_sops else None

                # Log SOP discovery
                if relevant_sop:
                    observability.observe(
                        observability.ConversationEvents.SOP_MATCHED,
                        observability.EventLevel.INFO,
                        {
                            "sop_id": relevant_sop["id"],
                            "sop_name": relevant_sop["name"],
                            "relevance_score": relevant_sop.get("relevance_score", 0),
                            "mode": relevant_sop.get("mode", "template"),
                            "message_preview": message[:100],
                        },
                        description=f"Matched SOP '{relevant_sop['name']}' for request",
                    )

                if relevant_sop:
                    mode = relevant_sop.get("mode", "template")
                    bypass_approval = relevant_sop.get("bypass_approval", True)

                    # Build enhanced message with SOP content
                    if mode == "template":
                        intro = "Follow this Standard Operating Procedure EXACTLY. Do not skip steps or improvise."  # noqa: E501
                        outro = "Create an optimized workflow that executes every step while minimizing unnecessary operations."  # noqa: E501
                    else:  # guide mode
                        intro = "Use this Standard Operating Procedure as guidance while optimizing for efficiency."  # noqa: E501
                        outro = "Create an optimized workflow that achieves the SOP goals while minimizing unnecessary operations."  # noqa: E501

                    # Create enhanced message with SOP content
                    enhanced_message = (
                        f"{intro}\n\n"
                        f"<sop>\n{relevant_sop.get('content', '')}\n</sop>\n\n"
                        "<directives>\nThe following directives in the SOP should be interpreted:\n"
                        "- [agent:name] - Route to the specified agent\n"
                        "- [mcp:tool] - Use the specified MCP tool\n"
                        "- [file:path] - Include the specified file content\n"
                        "- [critical] - This step cannot be optimized away\n"
                        "</directives>\n\n"
                        f"<user_request>\n{message}\n</user_request>\n\n"
                        f"{outro}"
                    )

                    # Pass to decomposer with SOP context
                    workflow = await self.task_decomposer.decompose_request(
                        request=enhanced_message,
                        context={
                            "available_agents": list(self.agents.keys()),
                            "sop_mode": mode,
                            "sop_id": relevant_sop["id"],
                        },
                        analysis=analysis,
                        requires_approval=needs_approval if not bypass_approval else False,
                    )

                    # Log SOP execution
                    observability.observe(
                        event_type=observability.ConversationEvents.SOP_EXECUTED,
                        level=observability.EventLevel.INFO,
                        data={
                            "sop_id": relevant_sop["id"],
                            "sop_name": relevant_sop["name"],
                            "workflow_id": workflow.id if workflow else None,
                            "mode": mode,
                            "bypass_approval": bypass_approval,
                        },
                        description=f"Passed SOP '{relevant_sop['name']}' to decomposer in {mode} mode",
                    )

            # Fall back to standard decomposition if no SOP found
            if workflow is None:
                # Decompose the request into a workflow
                observability.observe(
                    event_type=observability.ServerEvents.SERVER_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "task_decomposer",
                        "has_llm": self.task_decomposer.llm is not None,
                        "available_agents": list(self.agents.keys()),
                    },
                    description=f"Starting task decomposition (LLM: {self.task_decomposer.llm is not None})",
                )

                workflow = await self.task_decomposer.decompose_request(
                    request=message,
                    context={"available_agents": list(self.agents.keys())},
                    analysis=analysis,
                    requires_approval=needs_approval,
                )

            observability.observe(
                event_type=observability.ServerEvents.SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "service": "task_decomposer_complete",
                    "workflow_id": workflow.id if workflow else None,
                    "task_count": len(workflow.tasks) if workflow else 0,
                },
                description=f"Task decomposition complete: {len(workflow.tasks) if workflow else 0} tasks",
            )

            # Store workflow for tracking
            workflow_id = workflow.id

            # Debug: About to track workflow
            observability.observe(
                event_type=observability.ServerEvents.SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={"service": "track_workflow_call", "workflow_id": workflow_id},
                description="About to call workflow_manager.track_workflow",
            )

            self.workflow_manager.track_workflow(workflow, user_id)

            # Debug: After tracking workflow
            observability.observe(
                event_type=observability.ServerEvents.SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={"service": "track_workflow_complete", "workflow_id": workflow_id},
                description="workflow_manager.track_workflow completed successfully",
            )

            # Note: user_id is tracked separately in active_workflows
            # The Workflow model doesn't support user_id as an attribute

            if needs_approval:
                # Route to approval handler
                observability.observe(
                    event_type=observability.ServerEvents.SERVER_STARTED,
                    level=observability.EventLevel.INFO,
                    data={"service": "workflow_approval", "workflow_id": workflow_id},
                    description="Routing to workflow approval handler",
                )
                return await self._handle_workflow_approval(
                    workflow=workflow,
                    message=message,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                )
            else:
                # Execute immediately without approval
                observability.observe(
                    event_type=observability.ServerEvents.SERVER_STARTED,
                    level=observability.EventLevel.INFO,
                    data={"service": "workflow_execution", "workflow_id": workflow_id},
                    description="Executing workflow without approval",
                )

                # Debug: About to call _execute_workflow
                observability.observe(
                    event_type=observability.ServerEvents.SERVER_STARTED,
                    level=observability.EventLevel.INFO,
                    data={"service": "execute_workflow_call", "workflow_id": workflow_id},
                    description="About to call _execute_workflow",
                )

                result = await self._execute_workflow(
                    workflow=workflow,
                    message=message,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    stream=stream,
                )

                # Debug: _execute_workflow completed
                observability.observe(
                    event_type=observability.ServerEvents.SERVER_STARTED,
                    level=observability.EventLevel.INFO,
                    data={"service": "execute_workflow_complete", "workflow_id": workflow_id},
                    description="_execute_workflow completed successfully",
                )

                return result

        except Exception as e:
            # Clean up on error
            if "workflow_id" in locals():
                failed_workflow = self.workflow_manager.get_active_workflow(workflow_id)
                if failed_workflow:
                    # Mark as failed and move to history
                    if hasattr(failed_workflow, "status"):
                        failed_workflow.status = WorkflowStatus.FAILED
                    if hasattr(failed_workflow, "completed_at"):
                        failed_workflow.completed_at = datetime.now()
                    if hasattr(failed_workflow, "error_message"):
                        failed_workflow.error_message = str(e)

                    self.workflow_manager.complete_workflow(workflow_id, failed_workflow)

            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "phase": "workflow_processing"},
                description=f"Failed to process workflow: {str(e)}",
            )

            # Fall back to simple response
            return MuxiResponse(
                role="assistant",
                content=(
                    "I encountered an error while planning a complex workflow for your request. "
                    "Let me try a simpler approach to help you."
                ),
                metadata={
                    "error": "workflow_processing_failed",
                    "fallback": True,
                },
            )

    async def _handle_workflow_approval(
        self,
        workflow: Workflow,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> MuxiResponse:
        """
        Handle workflow approval flow.

        Stores the pending workflow and generates an approval message for the user.
        If session_id is provided, stores clarification info for handling the response.
        """
        # Debug: Entry point
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={"service": "workflow_approval_handler", "workflow_id": workflow.id},
            description="Entered _handle_workflow_approval method",
        )

        # Validate inputs
        self._validate_workflow_inputs(message, user_id, session_id, request_id)
        self._validate_workflow_object(workflow)

        # Debug: After validation
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={"service": "workflow_approval_validation", "workflow_id": workflow.id},
            description="Validation completed successfully",
        )

        # Store pending workflow
        self.workflow_manager.add_pending_approval(workflow)

        # Debug: After storing workflow
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={"service": "workflow_approval_stored", "workflow_id": workflow.id},
            description="Workflow stored for approval",
        )

        # Generate approval message using approval manager
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={"service": "approval_manager_call", "workflow_id": workflow.id},
            description="About to call ApprovalManager.present_plan_for_approval",
        )

        approval_message = await self.approval_manager.present_plan_for_approval(workflow)

        # Debug: After approval manager call
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "approval_manager_complete",
                "workflow_id": workflow.id,
                "message_length": len(approval_message) if approval_message else 0,
            },
            description="ApprovalManager.present_plan_for_approval completed successfully",
        )

        # Store clarification info if session_id exists
        if session_id:
            self._pending_clarifications[session_id] = {
                "type": "workflow_approval",
                "workflow_id": workflow.id,
                "original_message": message,
                "user_id": user_id,
                "request_id": request_id,
            }

        # Debug: Before returning response
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "workflow_approval_response",
                "workflow_id": workflow.id,
                "has_session": session_id is not None,
            },
            description="About to return MuxiResponse with approval message",
        )

        # Return response with approval message
        response = MuxiResponse(
            role="assistant",
            content=approval_message,
            metadata={
                "workflow_id": workflow.id,
                "approval_required": True,
                "requires_user_response": True,
            },
        )

        # Debug: Final success
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={"service": "workflow_approval_success", "workflow_id": workflow.id},
            description="_handle_workflow_approval completed successfully",
        )

        return response

    async def _should_execute_workflow_async(
        self, workflow: Workflow, original_message: str
    ) -> bool:
        """
        Determine if approved workflow should execute asynchronously.

        This re-applies the async decision logic after approval is obtained.
        """
        # Get async configuration
        async_webhook_url = self.formation_config.get("async", {}).get("webhook_url")
        threshold_seconds = getattr(self, "async_threshold_seconds", 30)

        # Need webhook URL for async execution
        if not async_webhook_url:
            return False

        # Need time estimator
        if not hasattr(self, "time_estimator") or not self.time_estimator:
            return False

        try:
            # Re-estimate execution time (workflow execution only, not planning)
            context = {
                "workflow_id": workflow.id,
                "task_count": len(workflow.tasks),
                "complexity_scores": [
                    task.get("estimated_complexity", 3) for task in workflow.tasks.values()
                ],
            }

            estimated_time = await self.time_estimator.estimate_processing_time(
                request=f"Execute workflow: {original_message}",
                context=context,
            )

            if estimated_time is None:
                return False

            should_async = estimated_time > threshold_seconds

            # Log the decision
            observability.observe(
                event_type=observability.ConversationEvents.ASYNC_THRESHOLD_DETECTED,
                level=observability.EventLevel.INFO,
                data={
                    "workflow_id": workflow.id,
                    "estimated_time": estimated_time,
                    "threshold_seconds": threshold_seconds,
                    "decision": "async" if should_async else "sync",
                    "phase": "post_approval_execution",
                },
                description=f"Post-approval async decision: {'async' if should_async else 'sync'}",
            )

            return should_async

        except Exception as e:
            # Default to sync if estimation fails
            observability.observe(
                event_type=observability.ConversationEvents.ASYNC_PROCESSING_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "workflow_id": workflow.id},
                description="Post-approval time estimation failed, using sync execution",
            )
            return False

    # Method removed - decomposer handles SOP conversion now

    async def _execute_workflow_async(
        self,
        workflow: Workflow,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute approved workflow asynchronously with webhook notification.
        """
        # Get webhook URL from configuration
        webhook_url = self.formation_config.get("async", {}).get("webhook_url")

        # Mark request as async for observability
        if hasattr(self, "observability_manager"):
            self.observability_manager.mark_request_async(request_id)

        # Return immediate response
        response_data = {
            "request_id": request_id,
            "status": "processing",
            "message": (
                "Your workflow has been approved and is now running in the background. "
                "I'll notify you when it's complete."
            ),
            "workflow_id": workflow.id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Execute workflow in background
        asyncio.create_task(
            self._execute_workflow_background(
                workflow=workflow,
                message=message,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                webhook_url=webhook_url,
            )
        )

        return response_data

    async def _execute_workflow_background(
        self,
        workflow: Workflow,
        message: str,
        user_id: str,
        session_id: Optional[str],
        request_id: Optional[str],
        webhook_url: str,
    ):
        """Execute workflow in background and send webhook notification."""
        try:
            # Execute the workflow normally
            result = await self._execute_workflow(
                workflow=workflow,
                message=message,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
            )

            # Send success webhook (reuse existing webhook logic if available)
            await self._send_completion_webhook(
                webhook_url=webhook_url,
                request_id=request_id,
                status="completed",
                result=result,
                workflow_id=workflow.id,
            )

        except Exception as e:
            # Send error webhook
            await self._send_completion_webhook(
                webhook_url=webhook_url,
                request_id=request_id,
                status="failed",
                error=str(e),
                workflow_id=workflow.id,
            )

    async def _send_completion_webhook(
        self,
        webhook_url: str,
        request_id: Optional[str],
        status: str,
        workflow_id: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Send webhook notification for completed workflow."""
        try:
            import aiohttp
            from datetime import datetime

            payload = {
                "request_id": request_id,
                "workflow_id": workflow_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if result:
                payload["result"] = result
            if error:
                payload["error"] = error

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status != 200:
                        observability.observe(
                            event_type=observability.ConversationEvents.ASYNC_PROCESSING_FAILED,
                            level=observability.EventLevel.WARNING,
                            data={
                                "webhook_url": webhook_url,
                                "status_code": response.status,
                                "request_id": request_id,
                            },
                            description=f"Webhook notification failed with status {response.status}",
                        )
                    else:
                        observability.observe(
                            event_type=observability.ConversationEvents.ASYNC_THRESHOLD_DETECTED,
                            level=observability.EventLevel.INFO,
                            data={
                                "webhook_url": webhook_url,
                                "request_id": request_id,
                                "status": status,
                            },
                            description="Webhook notification sent successfully",
                        )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.ASYNC_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "webhook_url": webhook_url,
                    "error": str(e),
                    "request_id": request_id,
                },
                description=f"Failed to send webhook notification: {str(e)}",
            )

    async def _execute_workflow(
        self,
        workflow: Workflow,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        stream: bool = False,
    ) -> Union[MuxiResponse, AsyncGenerator[str, None]]:
        """
        Execute a workflow immediately without approval.

        This method orchestrates the execution of complex multi-task workflows,
        tracking progress and synthesizing results into a coherent response.

        Args:
            workflow: Workflow to execute
            message: The user's original message
            user_id: User identifier
            session_id: Optional session identifier
            request_id: Optional request identifier
            stream: If True, stream progress updates; if False, return complete response

        Returns:
            If stream=False: MuxiResponse with complete results
            If stream=True: AsyncGenerator yielding progress updates
        """
        # Validate inputs
        self._validate_workflow_inputs(message, user_id, session_id, request_id)
        self._validate_workflow_object(workflow)

        if stream:
            # Return async generator for streaming
            return self._execute_workflow_streaming(
                workflow=workflow,
                message=message,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
            )

        # Non-streaming execution continues below
        workflow_id = workflow.id

        # Track workflow in active workflows
        self.workflow_manager.track_workflow(workflow, user_id)

        try:
            # Setup progress tracking callback
            def progress_callback(wf_id: str, wf: Any):
                """Internal callback to track workflow progress."""
                if wf_id == workflow_id:
                    # Update our tracked workflow
                    self.workflow_manager.update_workflow_status(workflow_id, wf)

                    # Log progress
                    observability.observe(
                        event_type=observability.ConversationEvents.OVERLORD_TASK_DECOMPOSED,
                        level=observability.EventLevel.INFO,
                        data={
                            "workflow_id": workflow_id,
                            "status": (
                                wf.status.value if hasattr(wf.status, "value") else str(wf.status)
                            ),
                            "progress": self.workflow_executor.get_workflow_progress(workflow_id),
                        },
                        description=f"Workflow {workflow_id} progress update",
                    )

            # Add progress callback
            self.workflow_executor.add_progress_callback(progress_callback)

            # Build execution context
            execution_context = {
                "user_id": user_id,
                "session_id": session_id,
                "request_id": request_id,
                "original_message": message,
            }

            # Check if this is an SOP workflow (has sequential dependencies)
            # and force sequential execution for proper data passing
            is_sop_workflow = False
            if workflow.tasks:
                # Check if tasks have sequential dependencies (characteristic of SOP workflows)
                tasks_with_deps = [t for t in workflow.tasks.values() if t.dependencies]
                if tasks_with_deps:
                    # If most tasks have dependencies, it's likely an SOP workflow
                    is_sop_workflow = len(tasks_with_deps) >= len(workflow.tasks) - 1

            if is_sop_workflow:
                # Temporarily disable parallel execution for SOP workflows
                # to ensure proper data flow between dependent tasks
                original_parallel_setting = (
                    self.workflow_executor.config.behavior.enable_parallel_execution
                )
                self.workflow_executor.config.behavior.enable_parallel_execution = False
                observability.observe(
                    event_type=observability.ConversationEvents.OVERLORD_ROUTING_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "workflow_id": workflow_id,
                        "task_count": len(workflow.tasks),
                        "user_id": user_id,
                        "execution_mode": "sequential",
                        "reason": "SOP workflow with task dependencies",
                    },
                    description=f"Starting SEQUENTIAL execution of SOP workflow {workflow_id}",
                )
            else:
                original_parallel_setting = None

            # Execute workflow with resilience support
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_ROUTING_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "workflow_id": workflow_id,
                    "task_count": len(workflow.tasks),
                    "user_id": user_id,
                },
                description=f"Starting execution of workflow {workflow_id}",
            )

            # Use the ResilientWorkflowExecutor directly (which has our capability fixes)
            # The resilient_workflow_manager has architectural issues with workflow execution
            completed_workflow = await self.workflow_executor.execute_workflow(
                workflow, context=execution_context
            )

            # Collect all task results
            task_results = []
            for task in completed_workflow.tasks.values():
                # Handle both enum objects and string values due to use_enum_values=True
                # Check for both COMPLETED and DONE statuses (both are success states)
                if task.status in SUCCESS_STATE_VALUES or task.status in SUCCESS_STATES:
                    task_result = {
                        "task_id": task.id,
                        "description": task.description,
                        "outputs": task.result or {},
                        "status": "completed",
                    }
                    task_results.append(task_result)
                elif task.status in {TaskStatus.FAILED, TaskStatus.FAILED.value, "failed"}:
                    task_result = {
                        "task_id": task.id,
                        "description": task.description,
                        "error": task.error_message or "Unknown error",
                        "status": "failed",
                    }
                    task_results.append(task_result)

            # Synthesize final response from task results
            final_response = await self._synthesize_workflow_results(
                task_results, message, workflow
            )

            # Collect artifacts from all tasks
            all_artifacts = []
            for task in completed_workflow.tasks.values():
                # Check if task completed successfully and has result (both COMPLETED and DONE are success states)
                if task.status in SUCCESS_STATE_VALUES or task.status in SUCCESS_STATES:
                    if task.result and isinstance(task.result, dict):
                        # Check if artifacts are in the result
                        if "artifacts" in task.result:
                            artifacts_output = task.result["artifacts"]
                            if isinstance(artifacts_output, dict) and "result" in artifacts_output:
                                artifact_list = artifacts_output["result"]
                                if isinstance(artifact_list, list):
                                    all_artifacts.extend(artifact_list)

            # Add artifacts to final response if any were collected
            if all_artifacts:
                final_response.artifacts = all_artifacts

            # Add workflow metadata
            final_response.metadata = final_response.metadata or {}
            final_response.metadata.update(
                {
                    "workflow_id": workflow_id,
                    "workflow_status": (
                        completed_workflow.status.value
                        if hasattr(completed_workflow.status, "value")
                        else str(completed_workflow.status)
                    ),
                    "total_tasks": len(workflow.tasks),
                    "completed_tasks": len(
                        [t for t in task_results if t.get("status") == "completed"]
                    ),
                    "failed_tasks": len([t for t in task_results if t.get("status") == "failed"]),
                    "execution_time": (
                        (
                            completed_workflow.completed_at - completed_workflow.started_at
                        ).total_seconds()
                        if completed_workflow.completed_at and completed_workflow.started_at
                        else None
                    ),
                }
            )

            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_ROUTING_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "workflow_id": workflow_id,
                    "status": (
                        completed_workflow.status.value
                        if hasattr(completed_workflow.status, "value")
                        else str(completed_workflow.status)
                    ),
                    "task_results": len(task_results),
                },
                description=f"Workflow {workflow_id} execution complete",
            )

            # Restore original parallel execution setting if it was changed for SOP workflow
            if original_parallel_setting is not None:
                self.workflow_executor.config.behavior.enable_parallel_execution = (
                    original_parallel_setting
                )

            return final_response

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_ROUTING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow_id,
                    "error": str(e),
                    "user_id": user_id,
                },
                description=f"Error executing workflow {workflow_id}: {str(e)}",
            )

            return MuxiResponse(
                role="assistant",
                content=(
                    f"I encountered an error while executing the workflow: {str(e)}. "
                    "Please try again or simplify your request."
                ),
                metadata={
                    "workflow_id": workflow_id,
                    "error": str(e),
                    "workflow_status": "failed",
                },
            )

        finally:
            # Restore original parallel execution setting if it was changed for SOP workflow
            if original_parallel_setting is not None:
                self.workflow_executor.config.behavior.enable_parallel_execution = (
                    original_parallel_setting
                )

            # Move workflow to history and update metrics
            completed_workflow = self.workflow_manager.get_active_workflow(workflow_id)
            if completed_workflow:
                self.workflow_manager.complete_workflow(workflow_id, completed_workflow)

    async def _execute_workflow_streaming(
        self,
        workflow: Workflow,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Execute a workflow with streaming progress updates.

        This method streams real-time updates as the workflow progresses,
        showing which tasks are being executed and their results.

        Args:
            workflow: Workflow to execute
            message: The user's original message
            user_id: User identifier
            session_id: Optional session identifier
            request_id: Optional request identifier

        Yields:
            Progress updates and partial results as strings
        """
        # Validate inputs (redundant but ensures safety)
        self._validate_workflow_inputs(message, user_id, session_id, request_id)
        self._validate_workflow_object(workflow)

        workflow_id = workflow.id

        # Track workflow in active workflows
        self.workflow_manager.track_workflow(workflow, user_id)

        try:
            # Yield initial workflow information
            yield f"🔄 Starting workflow: {workflow_id}\n"
            yield f"📋 Total tasks: {len(workflow.tasks)}\n\n"

            # Track completed content for final synthesis
            completed_tasks = []

            # Setup streaming progress callback
            def streaming_progress_callback(
                wf_id: str, wf: Any, task_update: Optional[Dict[str, Any]] = None
            ):
                """Callback that queues progress updates for streaming."""
                if wf_id == workflow_id and task_update:
                    # Queue the update for streaming
                    progress_queue.put_nowait(task_update)

            # Create a queue for progress updates
            import asyncio

            progress_queue = asyncio.Queue()

            # Build execution context
            execution_context = {
                "user_id": user_id,
                "session_id": session_id,
                "request_id": request_id,
                "original_message": message,
            }

            # Check if this is an SOP workflow and force sequential execution
            is_sop_workflow = False
            if workflow.tasks:
                tasks_with_deps = [t for t in workflow.tasks.values() if t.dependencies]
                if tasks_with_deps:
                    is_sop_workflow = len(tasks_with_deps) >= len(workflow.tasks) - 1

            if is_sop_workflow:
                original_parallel_setting = (
                    self.workflow_executor.config.behavior.enable_parallel_execution
                )
                self.workflow_executor.config.behavior.enable_parallel_execution = False
            else:
                original_parallel_setting = None

            # Start workflow execution in background
            execution_task = asyncio.create_task(
                self.workflow_executor.execute_workflow_streaming(
                    workflow,
                    context=execution_context,
                    progress_callback=streaming_progress_callback,
                )
            )

            # Stream progress updates while workflow executes
            workflow_complete = False
            while not workflow_complete or not progress_queue.empty():
                try:
                    # Wait for progress update with timeout
                    update = await asyncio.wait_for(progress_queue.get(), timeout=0.5)

                    # Format and yield the update
                    if update.get("type") == "task_started":
                        task_id = update.get("task_id")
                        agent_id = update.get("agent_id")
                        description = update.get("description", "")
                        yield f"\n🚀 Starting Task [{task_id}] - {description}\n"
                        if agent_id:
                            yield f"   Agent: {agent_id}\n"

                    elif update.get("type") == "task_progress":
                        task_id = update.get("task_id")
                        progress = update.get("progress", "")
                        yield f"   ⏳ {progress}\n"

                    elif update.get("type") == "task_completed":
                        task_id = update.get("task_id")
                        status = update.get("status", "unknown")
                        outputs = update.get("outputs", {})

                        if status == "completed":
                            yield f"   ✅ Task [{task_id}] completed\n"
                            # Store for final synthesis
                            completed_tasks.append(
                                {
                                    "task_id": task_id,
                                    "description": update.get("description", ""),
                                    "outputs": outputs,
                                    "status": "completed",
                                }
                            )
                            # Yield task outputs if available
                            if outputs and isinstance(outputs, dict):
                                for key, value in outputs.items():
                                    if isinstance(value, str) and len(value) > 100:
                                        # Truncate long outputs
                                        yield f"      {key}: {value[:100]}...\n"
                                    else:
                                        yield f"      {key}: {value}\n"
                        else:
                            yield f"   ❌ Task [{task_id}] failed: {update.get('error', 'Unknown error')}\n"
                            completed_tasks.append(
                                {
                                    "task_id": task_id,
                                    "description": update.get("description", ""),
                                    "error": update.get("error", "Unknown error"),
                                    "status": "failed",
                                }
                            )

                    elif update.get("type") == "workflow_completed":
                        workflow_complete = True
                        yield "\n✨ Workflow completed!\n"

                except asyncio.TimeoutError:
                    # Check if execution is done
                    if execution_task.done():
                        workflow_complete = True
                        # Check for any exception
                        try:
                            completed_workflow = await execution_task
                        except Exception as e:
                            yield f"\n❌ Workflow failed: {str(e)}\n"
                            return

            # Get the completed workflow
            if not execution_task.done():
                completed_workflow = await execution_task
            else:
                completed_workflow = execution_task.result()

            # Synthesize final summary
            yield "\n📊 Final Summary:\n"
            yield "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

            # Synthesize results into coherent response
            if completed_tasks:
                final_response = await self._synthesize_workflow_results(
                    completed_tasks, message, workflow
                )

                # Stream the synthesized response
                if hasattr(final_response, "content"):
                    content = final_response.content
                    if isinstance(content, str):
                        # Stream in chunks for better UX
                        chunk_size = 100
                        for i in range(0, len(content), chunk_size):
                            yield content[i:i + chunk_size]
                            await asyncio.sleep(0.01)  # Small delay for smooth streaming
                    else:
                        yield str(content)
                else:
                    yield str(final_response)

            # Final metrics
            completed_count = len([t for t in completed_tasks if t.get("status") == "completed"])
            failed_count = len([t for t in completed_tasks if t.get("status") == "failed"])

            yield "\n\n📈 Execution Stats:\n"
            yield f"   - Total tasks: {len(workflow.tasks)}\n"
            yield f"   - Completed: {completed_count}\n"
            yield f"   - Failed: {failed_count}\n"

            if hasattr(completed_workflow, "completed_at") and hasattr(
                completed_workflow, "started_at"
            ):
                if completed_workflow.completed_at and completed_workflow.started_at:
                    execution_time = (
                        completed_workflow.completed_at - completed_workflow.started_at
                    ).total_seconds()
                    yield f"   - Execution time: {execution_time:.2f}s\n"

        except Exception as e:
            # Stream error to user
            yield f"\n❌ Error executing workflow: {str(e)}\n"

            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_ROUTING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow_id,
                    "error": str(e),
                    "user_id": user_id,
                    "streaming": True,
                },
                description=f"Error in streaming workflow execution: {str(e)}",
            )

        finally:
            # Restore original parallel execution setting if it was changed for SOP workflow
            if original_parallel_setting is not None:
                self.workflow_executor.config.behavior.enable_parallel_execution = (
                    original_parallel_setting
                )

            # Move workflow to history and update metrics
            completed_workflow = self.workflow_manager.get_active_workflow(workflow_id)
            if completed_workflow:
                self.workflow_manager.complete_workflow(workflow_id, completed_workflow)

    async def _synthesize_workflow_results(
        self,
        task_results: List[Dict[str, Any]],
        original_request: str,
        workflow: Workflow,
    ) -> MuxiResponse:
        """
        Synthesize task results into a coherent final response.

        This method takes the outputs from all workflow tasks and combines them
        into a unified response that addresses the user's original request.

        Args:
            task_results: List of task results with outputs
            original_request: User's original request
            workflow: The executed workflow

        Returns:
            MuxiResponse with synthesized content
        """
        # Validate inputs
        if not isinstance(task_results, list):
            raise ValueError("Task results must be a list")
        if not original_request or not isinstance(original_request, str):
            raise ValueError("Original request must be a non-empty string")
        self._validate_workflow_object(workflow)

        try:
            # Check if we have any successful results
            successful_results = [r for r in task_results if r.get("status") == "completed"]

            if not successful_results:
                # All tasks failed
                failed_tasks = [r for r in task_results if r.get("status") == "failed"]
                error_summary = "\n".join(
                    [
                        f"- {task.get('description', 'Task')}: {task.get('error', 'Unknown error')}"
                        for task in failed_tasks
                    ]
                )

                return MuxiResponse(
                    role="assistant",
                    content=(
                        f"I encountered errors while processing your request. "
                        f"Here's what went wrong:\n\n{error_summary}\n\n"
                        f"Please try rephrasing your request or breaking it into smaller parts."
                    ),
                    metadata={"synthesis_method": "error_summary"},
                )

            # Try to use LLM for intelligent synthesis if available
            synthesis_model_config = (
                self._capability_models.get("text") if hasattr(self, "_capability_models") else None
            )

            if synthesis_model_config:
                # Prepare synthesis prompt
                synthesis_prompt = self._create_synthesis_prompt(
                    original_request, successful_results, task_results
                )

                try:
                    # Create LLM instance for synthesis
                    from ...services.llm import LLM

                    # Extract just the model name from the config
                    model_name = (
                        synthesis_model_config.get("model")
                        if isinstance(synthesis_model_config, dict)
                        else synthesis_model_config
                    )
                    synthesis_llm = LLM(
                        model=model_name,
                        temperature=0.7,
                        max_tokens=2000,
                    )

                    # Use LLM to synthesize results
                    synthesis_response = await synthesis_llm.chat(
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a helpful assistant that synthesizes multiple task results "
                                    "into a coherent, comprehensive response. Focus on addressing the user's "
                                    "original request while incorporating all relevant information from the tasks."
                                ),
                            },
                            {"role": "user", "content": synthesis_prompt},
                        ],
                        metadata={
                            "operation": "workflow_synthesis",
                            "workflow_id": workflow.id,
                        },
                    )

                    if synthesis_response:
                        return MuxiResponse(
                            role="assistant",
                            content=synthesis_response,
                            metadata={"synthesis_method": "llm_synthesis"},
                        )

                except Exception as e:
                    # Log but continue with fallback
                    observability.observe(
                        event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(e), "workflow_id": workflow.id},
                        description=f"LLM synthesis failed, using fallback: {str(e)}",
                    )

            # Fallback: Simple concatenation with structure
            return self._fallback_synthesis(original_request, successful_results, task_results)

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "workflow_id": workflow.id},
                description=f"Error synthesizing workflow results: {str(e)}",
            )

            # Emergency fallback
            return MuxiResponse(
                role="assistant",
                content=(
                    f"I completed the workflow with {len(successful_results)} successful tasks, "
                    f"but encountered an error while preparing the final response. "
                    f"The tasks were completed successfully, but I couldn't synthesize the results properly."
                ),
                metadata={"synthesis_method": "emergency_fallback", "error": str(e)},
            )

    def _create_synthesis_prompt(
        self,
        original_request: str,
        successful_results: List[Dict[str, Any]],
        all_results: List[Dict[str, Any]],
    ) -> str:
        """Create prompt for LLM synthesis of task results."""
        prompt_parts = [
            f"Original User Request: {original_request}",
            "",
            "Workflow Execution Summary:",
            "",
        ]

        # Add successful task results with only key outcomes
        for i, result in enumerate(successful_results, 1):
            task_desc = result.get("description", "Unknown task")
            prompt_parts.append(f"Task {i}: {task_desc}")

            # Extract only key actionable outcomes from outputs
            outputs = result.get("outputs", {})
            key_outcomes = self._extract_key_outcomes(outputs, task_desc)

            if key_outcomes:
                prompt_parts.append(f"Key Outcomes: {key_outcomes}")
            else:
                # For tasks without specific outcomes, just note completion
                prompt_parts.append("Status: Completed successfully")
            prompt_parts.append("")

        # Note any failed tasks
        failed_tasks = [r for r in all_results if r.get("status") == "failed"]
        if failed_tasks:
            prompt_parts.append("Failed Tasks:")
            for task in failed_tasks:
                prompt_parts.append(
                    f"- {task.get('description', 'Task')}: {task.get('error', 'Unknown error')}"
                )
            prompt_parts.append("")

        prompt_parts.extend(
            [
                "Based on the original user request and the task results above, provide an appropriate response:",
                "",
                "- If this appears to be a conversational request (greeting, casual inquiry, social interaction, etc.),",  # noqa: E501
                "  provide a natural, conversational response. Respond directly as if having a conversation,",
                "  not describing what tasks were completed.",
                "",
                "- If this is a task-oriented request with concrete deliverables, provide a brief confirmation that:",
                "  1. Confirms what was accomplished (focus on concrete outcomes like created issues, documents, etc.)",
                "  2. Mentions any specific IDs, URLs, or references the user needs",
                "  3. Acknowledges any failures if relevant",
                "  4. Keep it concise - 2-3 sentences maximum",
                "",
                "Response:",
            ]
        )

        return "\n".join(prompt_parts)

    def _extract_key_outcomes(self, outputs: Dict[str, Any], task_description: str) -> str:
        """
        Extract only key actionable outcomes from task outputs.

        This method looks for specific patterns like issue IDs, URLs, document titles,
        etc. rather than including all the raw content.

        Args:
            outputs: Task outputs dictionary
            task_description: Description of the task for context

        Returns:
            String with key outcomes or empty string if none found
        """
        key_items = []

        # Convert outputs to string for pattern matching if needed
        output_str = str(outputs) if outputs else ""

        # Look for Linear issue patterns (MX-123 format)
        import re

        linear_pattern = r"MX-\d+"
        linear_matches = re.findall(linear_pattern, output_str)
        if linear_matches:
            key_items.append(f"Linear issues: {', '.join(set(linear_matches))}")

        # Look for URLs (especially Linear URLs)
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+linear[^\s<>"{}|\\^`\[\]]*'
        url_matches = re.findall(url_pattern, output_str, re.IGNORECASE)
        if url_matches:
            # Just include first URL to keep it concise
            key_items.append(f"URL: {url_matches[0]}")

        # Check for specific outcome fields in outputs dict
        if isinstance(outputs, dict):
            # Common outcome fields to check
            outcome_fields = [
                "issue_id",
                "issue_url",
                "document_id",
                "file_path",
                "created_id",
                "updated_id",
                "ticket_id",
                "pr_url",
                "issue_number",
                "pull_request",
                "artifact_id",
            ]

            for field in outcome_fields:
                if field in outputs and outputs[field]:
                    # Capitalize and format the field name nicely
                    field_name = field.replace("_", " ").title()
                    key_items.append(f"{field_name}: {outputs[field]}")

            # Check for creation confirmations
            if outputs.get("created") or outputs.get("success"):
                if "linear" in task_description.lower():
                    key_items.append("Linear issue created successfully")
                elif "document" in task_description.lower():
                    key_items.append("Document created successfully")
                elif "file" in task_description.lower():
                    key_items.append("File created successfully")

        # If we found key items, join them; otherwise return empty string
        return "; ".join(key_items) if key_items else ""

    def _fallback_synthesis(
        self,
        original_request: str,
        successful_results: List[Dict[str, Any]],
        all_results: List[Dict[str, Any]],
    ) -> MuxiResponse:
        """Fallback synthesis when LLM is not available."""
        response_parts = []

        # Start with a brief summary
        task_count = len(successful_results)
        if task_count > 0:
            response_parts.append(
                f"✅ Successfully completed {task_count} task{'s' if task_count != 1 else ''}"
            )
            response_parts.append("")

        # Extract key outcomes from successful tasks
        key_outcomes = []
        for result in successful_results:
            task_desc = result.get("description", "Task")
            outputs = result.get("outputs", {})
            outcomes = self._extract_key_outcomes(outputs, task_desc)
            if outcomes:
                key_outcomes.append(f"• {task_desc}: {outcomes}")

        if key_outcomes:
            response_parts.append("**Key Outcomes:**")
            response_parts.extend(key_outcomes)
            response_parts.append("")

        # Note any failed tasks briefly
        failed_tasks = [r for r in all_results if r.get("status") == "failed"]
        if failed_tasks:
            response_parts.append(
                f"⚠️ {len(failed_tasks)} task{'s' if len(failed_tasks) != 1 else ''} failed:"
            )
            for task in failed_tasks:
                response_parts.append(
                    f"• {task.get('description', 'Task')}: {task.get('error', 'Unknown error')}"
                )

        return MuxiResponse(
            role="assistant",
            content="\n".join(response_parts),
            metadata={"synthesis_method": "structured_concatenation"},
        )

    # ===================================================================
    # VALIDATION METHODS FOR TYPE SAFETY
    # ===================================================================

    def _validate_workflow_inputs(
        self,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Validate inputs for workflow processing.

        Args:
            message: User message to process
            user_id: User identifier
            session_id: Optional session identifier
            request_id: Optional request identifier

        Raises:
            ValueError: If inputs are invalid
        """
        if not message or not isinstance(message, str):
            raise ValueError("Message must be a non-empty string")

        if not user_id or not isinstance(user_id, str):
            raise ValueError("User ID must be a non-empty string")

        if session_id is not None and not isinstance(session_id, str):
            raise ValueError("Session ID must be a string if provided")

        if request_id is not None and not isinstance(request_id, str):
            raise ValueError("Request ID must be a string if provided")

    def _validate_workflow_analysis(self, analysis: RequestAnalysis) -> None:
        """
        Validate workflow analysis results.

        Args:
            analysis: Request analysis results

        Raises:
            ValueError: If analysis is invalid
        """
        if not isinstance(analysis, RequestAnalysis):
            raise ValueError("Analysis must be a RequestAnalysis instance")

        if not (1.0 <= analysis.complexity_score <= 10.0):
            raise ValueError("Complexity score must be between 1.0 and 10.0")

        if not analysis.required_capabilities:
            raise ValueError("Analysis must include required capabilities")

    def _validate_workflow_object(self, workflow: Workflow) -> None:
        """
        Validate workflow object integrity.

        Args:
            workflow: Workflow to validate

        Raises:
            ValueError: If workflow is invalid
        """
        if not isinstance(workflow, Workflow):
            raise ValueError("Workflow must be a Workflow instance")

        if not workflow.id:
            raise ValueError("Workflow must have an ID")

        if not workflow.tasks:
            raise ValueError("Workflow must have at least one task")

        # Validate task dependencies
        task_ids = set(workflow.tasks.keys())
        for task in workflow.tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    raise ValueError(f"Task {task.id} has invalid dependency: {dep_id}")

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
        user_id: Any,
    ) -> MuxiResponse:
        """
        Handle agent clarification request by converting it to user clarification.

        Args:
            clarification_metadata: The clarification request from agent
            agent_response: Original agent response
            original_message: User's original message
            agent_name: Name of the agent requesting clarification
            user_id: External user ID

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

            # Check if this is a credential clarification response
            if (
                self.clarification_manager
                and user_id
                and user_id in self.clarification_manager._user_to_request
            ):
                request_id = self.clarification_manager._user_to_request[user_id]
                if request_id in self.clarification_manager.active_requests:
                    clarification_request = self.clarification_manager.active_requests[request_id]

                    # Check if this is a credential selection clarification
                    if (
                        clarification_request.context
                        and clarification_request.context.get("reason") == "ambiguous_credential"
                    ):

                        # Parse the credential selection from the response
                        selected_credential = await self._parse_credential_selection(
                            clarification_response, clarification_request
                        )

                        if selected_credential:
                            # Store the selected credential for this user and service
                            service = clarification_request.context.get("service")
                            if service and self.mcp_service:
                                # Find the server that uses this service
                                for server_id, config in self.mcp_service.servers.items():
                                    if (
                                        config.get("uses_user_credentials")
                                        and service in server_id.lower()
                                    ):
                                        # Cache the selected credential
                                        if server_id not in self.mcp_service.user_credentials:
                                            self.mcp_service.user_credentials[server_id] = {}

                                        # Store the resolved credential
                                        self.mcp_service.user_credentials[server_id][
                                            user_id
                                        ] = selected_credential
                                        break

                            # Clear the clarification request since it's resolved
                            del self.clarification_manager.active_requests[request_id]
                            del self.clarification_manager._user_to_request[user_id]

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

    async def _parse_credential_selection(
        self, clarification_response: str, clarification_request
    ) -> Optional[Dict[str, Any]]:
        """
        Parse user's credential selection response and retrieve the actual credential.

        Args:
            clarification_response: User's response (e.g., "1", "ranaroussi", etc.)
            clarification_request: The original clarification request with context

        Returns:
            The selected credential data, or None if parsing failed
        """
        try:
            # Get the ordered credentials from the clarification context

            # Handle different types of clarification info
            if isinstance(clarification_request, dict):
                # Direct dictionary access
                ordered_credentials = clarification_request.get("ordered_credentials", [])
                service = clarification_request.get("service")
                user_id = clarification_request.get("user_id")
            else:
                # Object attribute access
                ordered_credentials = clarification_request.context.get("ordered_credentials", [])
                service = clarification_request.context.get("service")
                user_id = clarification_request.user_id

            if not ordered_credentials or not service or not user_id:
                return None

            # Try to parse the response as a number first
            import re

            numbers = re.findall(r"\d+", clarification_response.strip())
            if numbers:
                try:
                    choice_index = int(numbers[0]) - 1  # Convert to 0-based index
                    if 0 <= choice_index < len(ordered_credentials):
                        selected_name = ordered_credentials[choice_index]
                    else:
                        return None
                except (ValueError, IndexError):
                    return None
            else:
                # Try to match the response directly to a credential name
                response_lower = clarification_response.lower().strip()
                selected_name = None
                for cred_name in ordered_credentials:
                    if cred_name.lower() in response_lower or response_lower in cred_name.lower():
                        selected_name = cred_name
                        break

                if not selected_name:
                    return None

            # Now retrieve the actual credential from the database
            if self.credential_resolver:
                try:
                    # Get all credentials for this user and service
                    all_credentials = await self.credential_resolver.get_user_credentials(
                        user_id, service
                    )

                    # Find the credential with the matching name
                    for cred in all_credentials:
                        if cred.get("name") == selected_name:
                            # Return the credential in the format expected by MCP service
                            return {"type": "bearer", "token": cred.get("credential_data")}

                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.ERROR,
                        data={"error": str(e), "service": service, "user_id": user_id},
                        description=f"Failed to retrieve selected credential: {str(e)}",
                    )

            return None

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Failed to parse credential selection: {str(e)}",
            )
            return None

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
            if not self.clarification_config or not self.clarification_config.enabled:
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
                service=service, user_id=user_id, agent_id="system", context=context
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
                event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
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
                            # Validate credential data structure before storing
                            if self._validate_credential_data(credential_data, service):
                                # Store the credential
                                await self.credential_resolver.store_credential(
                                    user_id=user_id,
                                    service=service,
                                    credentials=credential_data,
                                    mcp_service=self.mcp_service,
                                )

                                # Asynchronously update credential name with smart discovery
                                async def update_name():
                                    with suppress(Exception):
                                        # Attempt to update credential name, but don't fail if it doesn't work
                                        await self.credential_resolver.update_credential_name_with_discovery(
                                            user_id=user_id,
                                            service=service,
                                            mcp_service=self.mcp_service,
                                        )

                                asyncio.create_task(update_name())
                            else:
                                observability.observe(
                                    event_type=observability.ErrorEvents.VALIDATION_FAILED,
                                    level=observability.EventLevel.ERROR,
                                    data={
                                        "service": service,
                                        "user_id": user_id,
                                        "credential_keys": (
                                            list(credential_data.keys())
                                            if isinstance(credential_data, dict)
                                            else "invalid_type"
                                        ),
                                        "validation_error": "invalid_credential_structure",
                                    },
                                    description=f"Invalid credential data structure for {service}",
                                )
                                return False

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

    def _validate_credential_data(self, credential_data: Any, service: str) -> bool:
        """
        Validate credential data structure before storing.

        Args:
            credential_data: The credential data to validate
            service: The service the credential is for

        Returns:
            True if credential data is valid, False otherwise
        """
        # Must be a non-empty dictionary
        if not isinstance(credential_data, dict):
            return False

        if not credential_data:
            return False

        # Validate that all keys are strings
        for key in credential_data.keys():
            if not isinstance(key, str) or not key.strip():
                return False

        # Validate that all values are non-empty strings
        for value in credential_data.values():
            if not isinstance(value, str) or not value.strip():
                return False

        # Service-specific validation
        common_credential_fields = {
            "token",
            "api_key",
            "key",
            "secret",
            "password",
            "access_token",
            "auth_token",
            "bearer_token",
            "client_id",
            "client_secret",
            "app_key",
            "app_secret",
        }

        # Ensure at least one field matches common credential patterns
        has_valid_field = any(
            key.lower().replace("_", "").replace("-", "")
            in {field.replace("_", "").replace("-", "") for field in common_credential_fields}
            for key in credential_data.keys()
        )

        if not has_valid_field:
            return False

        # Basic length validation - credentials should be reasonably long
        for value in credential_data.values():
            if len(value.strip()) < 8:  # Minimum reasonable credential length
                return False

        return True

    def _build_enhanced_message(self, original_message: str, collected_info: dict) -> str:
        """
        Build enhanced message with collected information from clarification.

        Args:
            original_message: The original user message
            collected_info: Information collected during clarification

        Returns:
            Enhanced message combining original and collected info
        """
        if not collected_info:
            return original_message

        # Format collected info as context
        context_parts = [original_message]
        for key, value in collected_info.items():
            # Format key nicely (e.g., "tool_name" -> "tool name")
            formatted_key = key.replace("_", " ").title()
            context_parts.append(f"{formatted_key}: {value}")

        return ". ".join(context_parts)

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
            # Use the initialized analyzer (not hasattr check)
            if not self.clarification_analyzer:
                return None

            # Get user context for analysis
            user_context = {}
            if user_id is not None and hasattr(self, "user_context_manager"):
                try:
                    user_context = await self.user_context_manager.get_user_context(user_id)
                except Exception:
                    pass  # Continue without context

            # Get available tools for analysis
            available_tools = []
            if hasattr(self, "mcp_coordinator") and self.mcp_coordinator:
                try:
                    # Get all tools from the registry
                    tool_registry = self.mcp_coordinator.get_tool_registry()
                    available_tools = []
                    for server_tools in tool_registry.values():
                        available_tools.extend(server_tools.keys())
                except Exception:
                    pass  # Continue without tools

            # Analyze request for missing information
            analysis_result = await self.clarification_analyzer.analyze_request(
                user_message=message,
                intent="general",
                available_tools=available_tools,
                user_context=user_context
            )

            # Check if clarification is needed
            if analysis_result and analysis_result.missing_info:
                # Create clarification request
                clarification_request = None
                if self.clarification_manager:
                    clarification_request = await self.clarification_manager.start_clarification(
                        user_id=str(user_id),
                        agent_id="overlord",
                        request_type=RequestType.REASONING,
                        intent="general",
                        tool_name=None,
                        provided_info={}
                    )

                # Generate clarification question
                question = "Could you please provide more details?"
                if self.clarification_question_generator:
                    # For reasoning clarification, use the first missing info item
                    missing_context = (
                        analysis_result.missing_info[0]
                        if analysis_result.missing_info
                        else "more details"
                    )
                    question_obj = await self.clarification_question_generator.generate_reasoning_question(
                        intent="general",
                        missing_context=missing_context,
                        user_background={},
                        style=self.clarification_config.style
                    )
                    question = question_obj.question_text

                request_id = (
                    clarification_request.request_id
                    if clarification_request
                    else f"clarify_{user_id}_{time.time()}"
                )

                observability.observe(
                    event_type=observability.ConversationEvents.CLARIFICATION_REQUEST_SENT,
                    level=observability.EventLevel.INFO,
                    data={
                        "request_id": request_id,
                        "missing_info": (
                            analysis_result.missing_info
                            if isinstance(analysis_result.missing_info, list)
                            else list(analysis_result.missing_info.keys())
                        ),
                    },
                    description="Async clarification needed",
                )

                return (question, request_id)

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

            # Store user's clarification response in buffer memory
            try:
                await self.add_message_to_memory(
                    content=clarification_response,
                    role="user",
                    timestamp=time.time(),
                    agent_id="overlord",
                    user_id=request_state.user_id,
                    session_id=request_state.session_id,
                    request_id=request_id,
                )
            except Exception as e:
                # Log but don't fail on memory storage error
                print(f"Failed to store clarification response in buffer memory: {e}")

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

                    # Store follow-up clarification question in buffer memory
                    try:
                        await self.add_message_to_memory(
                            content=result.next_question,
                            role="assistant",
                            timestamp=time.time(),
                            agent_id="overlord",
                            user_id=request_state.user_id,
                            session_id=request_state.session_id,
                            request_id=request_id,
                        )
                    except Exception as e:
                        print(
                            f"Failed to store follow-up clarification question in buffer memory: {e}"
                        )

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

                    # Remove from async requests set even on failure
                    self.observability_manager._async_requests.discard(request_id)
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

                # Remove from async requests set even on failure
                self.observability_manager._async_requests.discard(request_id)

            except Exception:
                pass  # Avoid nested exceptions

            return False

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

    # =========================================================================
    # WORKFLOW STATUS ENDPOINTS - Phase 2, Stream 2
    # =========================================================================

    def get_workflow_status(self, workflow_id: str) -> Optional[Workflow]:
        """
        Get the status of a specific workflow.

        Args:
            workflow_id: Unique workflow identifier

        Returns:
            Workflow object with current status or None if not found
        """
        return self.workflow_manager.get_workflow(workflow_id)

    def list_workflows(
        self,
        user_id: Optional[str] = None,
        status: Optional[WorkflowStatus] = None,
        limit: int = 100,
        offset: int = 0,
        include_active: bool = True,
        include_history: bool = True,
    ) -> List[Workflow]:
        """
        List workflows with optional filters.

        Args:
            user_id: Filter by user ID (requires user_id in workflow metadata)
            status: Filter by workflow status
            limit: Maximum number of workflows to return
            offset: Number of workflows to skip
            include_active: Include currently active workflows
            include_history: Include historical workflows

        Returns:
            List of workflows matching the filters
        """
        # Get workflows from workflow manager
        workflows = self.workflow_manager.get_workflows(
            include_active=include_active,
            include_history=include_history,
            include_pending=include_active,  # Include pending with active
            user_id=user_id,
            status=status,
            limit=limit + offset,  # Get extra for offset
        )

        # Apply pagination
        return workflows[offset:offset + limit]

    async def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel an active workflow.

        Args:
            workflow_id: Workflow to cancel

        Returns:
            True if workflow was cancelled, False if not found or already completed
        """
        # Use workflow manager to cancel the workflow
        success = self.workflow_manager.cancel_workflow(workflow_id)

        if success:
            # Notify workflow executor to stop execution
            await self.workflow_executor.cancel_workflow(workflow_id)

        return success

    def get_workflow_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated workflow metrics.

        Returns:
            Dictionary containing workflow statistics
        """
        return self.workflow_manager.get_metrics()

    def get_active_workflow_ids(self) -> List[str]:
        """
        Get IDs of all currently active workflows.

        Returns:
            List of active workflow IDs
        """
        return self.workflow_manager.get_active_workflow_ids()

    def clear_workflow_history(self, older_than_days: int = 30) -> int:
        """
        Clear old workflows from history.

        Args:
            older_than_days: Clear workflows older than this many days

        Returns:
            Number of workflows cleared
        """
        return self.workflow_manager.clear_workflow_history(older_than_days)
