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
import hashlib
import time
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
import datetime
import os

from ..agents import Agent
from ..background.request_tracker import RequestState, RequestStatus
from ...services import observability
from ...datatypes.response import MuxiResponse
from ...services.mcp.service import MCPService
from ...services.memory.short_term import ShortTermMemory
from ...services.memory.long_term import LongTermMemory
from ...services.memory.memobase import Memobase
from ...services.llm import LLM
from ...services.a2a.registry_client import A2ARegistryClient
from ...services.a2a.server import A2AServer

# A2A models imported when needed
from ...services.secrets.secrets_manager import SecretsManager
from ...utils.id_generator import generate_nanoid

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

# Configuration Management (Phase 2)
from .secrets_manager import SecretsInterpolator

# Memory Management (Phase 3)
from ..memory import (
    BufferMemoryManager,
    PersistentMemoryManager,
    UserContextManager,
    ExtractionCoordinator,
)

# NEW: Import multimodal and synthesis components
from ...services.multimodal import MultiModalFusionEngine, WorkflowMultiModalProcessor
from ..workflow.synthesis import AdvancedResponseSynthesizer, ResponseQualityAssessor

# NEW: Import interactive elements and enhanced multimodal integration
from ..workflow.interactive import InteractiveElementGenerator, ResponseFormatter, MediaIntegrator
from ...services.multimodal import (
    TaskInputProcessor,
    TaskOutputProcessor,
)

# NEW: Import intelligent caching system
from ..caching import IntelligentCacheManager

# NEW: Import parallel workflow optimization
from ..parallel import ParallelWorkflowOptimizer

# NEW: Import Phase 3 intelligence components
from ..intelligence import (
    UserPreferenceEngine,
    AdaptiveResponseGenerator,
)

# NEW: Import Phase 4.1 resilience components
from ..resilience import (
    ResilientWorkflowManager,
    ResilienceConfig,
)

# Document Processing Components (Tasks 3.7-3.9)
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

# Async Orchestration Components (Task 4)
from ..background import (
    RequestTracker,
    WebhookManager,
    TimeEstimator,
)

# Unified Response Components (Phase 3)
from ...utils.response_converter import create_unified_response, extract_user_content
from ...datatypes.clarification import ClarificationConfig, QuestionStyle
from ...utils.user_dirs import set_formation_id


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
        self._routing_cache: Dict[str, str] = {}  # Cache for message routing decisions
        self._user_id_cache = {}  # User ID caching for routing
        self._agent_expertise: Dict[str, Dict[str, Any]] = {}  # Expertise registry

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

        # Accept pre-generated API keys from Formation
        api_keys = api_keys or {}
        self.user_api_key = api_keys.get("user")
        self.admin_api_key = api_keys.get("admin")

        # Track whether keys were provided or need generation
        self._user_key_auto_generated = self.user_api_key is None
        self._admin_key_auto_generated = self.admin_api_key is None

        # Generate keys if not provided by Formation
        if self.user_api_key is None:
            self.user_api_key = generate_api_key("user")
        if self.admin_api_key is None:
            self.admin_api_key = generate_api_key("admin")

        # ===================================================================
        # MEMORY COORDINATION - Intelligence concerns
        # ===================================================================

        # Store centralized memory systems for intelligence coordination
        self.buffer_memory = buffer_memory
        self.long_term_memory = long_term_memory

        # Configure extraction settings (intelligence concerns)
        self.auto_extract_user_info = auto_extract_user_info
        self.extraction_model = extraction_model
        self.memory_extractor = None  # Will be initialized later

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

        # Initialize intelligent caching system (intelligence concerns)
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
        # These will be properly configured from Formation services
        self.document_chunker: Optional[DocumentChunkManager] = None
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

        # Initialize async request-response components (intelligence concerns)
        self.request_tracker = RequestTracker()
        async_config = self.formation_config.get("async", {})
        self.webhook_manager = WebhookManager(
            default_retries=async_config.get("webhook_retries", 3),
            default_timeout=async_config.get("webhook_timeout", 10),
        )
        self.time_estimator = TimeEstimator(self.request_analyzer)

        # Async configuration (intelligence concerns)
        self.async_threshold_seconds = async_config.get("threshold_seconds", 30)
        self.async_enable_estimation = async_config.get("enable_estimation", True)
        self.async_webhook_url = async_config.get("webhook_url")

        # ===================================================================
        # CLARIFICATION INTELLIGENCE - Intelligence concerns
        # ===================================================================

        # Initialize clarification configuration with defaults (intelligence concerns)
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

    async def start(self) -> None:
        """Start all overlord services including cache manager."""
        try:
            # Initialize the routing model (async)
            await self._initialize_routing_model()

            # Start cache manager
            await self.cache_manager.start()

            # Initialize observability system (gets reconfigured after formation config)
            self.observability_manager = observability.ObservabilityManager()
            await self.observability_manager.start()

            # A2A services are now initialized by Formation
            # Start A2A formation server if initialized by Formation
            if hasattr(self, "a2a_server") and self.a2a_server:
                await self._start_a2a_server()

            # Process pending external agent registrations if available
            if (
                hasattr(self, "inbound_registry_client")
                and self.inbound_registry_client
                and hasattr(self, "pending_external_registrations")
            ):
                await self._process_pending_agent_registrations()

            #  Info - TODO: add observability
            #  SystemEvents.STARTED (overlord)

        except Exception:
            #  Error - TODO: add observability
            #  ErrorEvents.INTERNAL_ERROR (overlord)
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

        # Combine technical instructions with persona
        return (
            f"<system-message>\n{system_message}\n</system-message>\n\n"
            f"<persona>\n{persona}\n</persona>"
        )

        try:
            # Only initialize if document processing is enabled
            if (
                not hasattr(self, "document_processing_config")
                or not self.document_processing_config.is_enabled()
            ):
                return

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

        except Exception as e:
            #  Warning - TODO: add observability
            # ErrorEvents.FAILED_INITIALIZATION (document processing components)
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
        from .initialization import _initialize_buffer_memory

        await _initialize_buffer_memory(self, buffer_config)

    async def _initialize_persistent_memory(self, persistent_config: Dict[str, Any]) -> None:
        """Initialize persistent memory from configuration."""
        from .initialization import _initialize_persistent_memory

        await _initialize_persistent_memory(self, persistent_config)

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
                #  Warning - TODO: add observability
                # ErrorEvents.FAILED_INITIALIZATION (api_key)
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
    # SECRETS MANAGEMENT
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
            except Exception as e:
                # Log warning but don't fail the removal
                #  Error - TODO: add observability
                # ErrorEvents.INTERNAL_ERROR
                _ = e  # remove this after implementing observability

        # Remove the agent
        del self.agents[agent_id]

        # Update default agent if necessary
        if self.default_agent_id == agent_id:
            # Set the first available agent as default, or None if no agents remain
            self.default_agent_id = next(iter(self.agents)) if self.agents else None

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
                #  Info - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_COMPLETED
            except Exception as e:
                # Fall back to intelligent selection if model creation fails
                #  Warning - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_FAILED
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
                #  Warning - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_COMPLETED
                # Routing model returned invalid agent. Selected best available agent
            else:
                #  Info - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_COMPLETED
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
            #  Warning - TODO: add observability
            # ConversationEvents.OVERLORD_ROUTING_FAILED
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

        #  Info - TODO: add observability
        # ConversationEvents.OVERLORD_ROUTING_STARTED
        # Get enhanced agent descriptions with metadata
        agent_descriptions = []
        for agent_id in self.agents.keys():
            # Use enhanced metadata
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

        # Get persona from config or use default
        custom_persona = getattr(self, "routing_persona", None)

        # Create complete system message using persona
        complete_system_message = self._create_overlord_system_message(custom_persona)

        # Add current date/time to the prompt
        current_time = datetime.datetime.now()
        date_time_str = current_time.strftime("Today is %d %m %Y, %H:%M")
        prompt = f"{complete_system_message}\n\n<date-time>\n{date_time_str}\n</date-time>\n\n"

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

        # Keywords for simple agent matching heuristics
        AGENT_MATCHING_KEYWORDS = {
            "business",
            "writer",
            "assistant",
            "help",
            "support",
            "analysis",
            "research",
        }

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
            for keyword in AGENT_MATCHING_KEYWORDS:
                if keyword in message_lower and keyword in description_lower:
                    score += 1

            if score > best_score:
                best_score = score
                best_match = agent_id

        # If no good match found, return the first agent
        best_match = best_match or next(iter(self.agents))

        #  Info - TODO: add observability
        # ConversationEvents.OVERLORD_ROUTING_COMPLETED
        # Selected best available agent: '{best_match}'
        return best_match

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
            # Default to True if not specified
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
                #  Warning - TODO: add observability
                # SystemEvents.MCP_SERVER_REGISTRATION_FAILED
                _ = e  # remove this after implementing observability
                # Continue with original auth

        # Register the server with the MCP service
        res = await self.mcp_service.register_mcp_server(
            server_id=server_id,
            url=url,
            command=command,
            credentials=final_auth,
            model=model,
            request_timeout=timeout,
        )

        #  Info - TODO: add observability
        # ConversationEvents.MCP_SERVER_REGISTERED
        return res

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
        res = await self.mcp_service.list_tools(server_id=server_id)

        # Info - TODO: add observability
        # SystemEvents.MCP_TOOL_DISCOVERY_COMPLETED
        return res

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
                    #  Error - TODO: add observability
                    # ConversationEvents.MEMORY_LONG_TERM_ENHANCEMENT_FAILED
                    _ = e  # remove this after implementing observability
                    await self.long_term_memory.add(
                        content=content, metadata=metadata, user_id=internal_user_id
                    )
            else:
                # For non-user messages, just store directly
                await self.long_term_memory.add(
                    content=content, metadata=metadata, user_id=internal_user_id
                )

            #  Info - TODO: add observability
            # ConversationEvents.MEMORY_LONG_TERM_ENHANCED

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
        - Index for semantic search with ShortTermMemory

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

            #  Info - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_STARTED
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
        Phase 1: Document Storage Foundation (Task 3.7)

        Process and store documents with intelligent chunking and indexing.
        """
        processed_docs = []

        for attachment in attachments:
            try:
                filename = attachment.get("filename", "unknown")
                content = attachment.get("content", "")

                #  Info - TODO: add observability

                # Chunk the document using adaptive strategies
                if self.document_chunker:
                    chunks = await self.document_chunker.chunk_document(
                        content=content, filename=filename, strategy="adaptive"
                    )
                else:
                    # Fallback simple chunking
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
            #  Error - TODO: add observability
            # ConversationEvents.DOCUMENT_PROCESSING_FAILED
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

    # ===================================================================
    # ASYNC REQUEST-RESPONSE ORCHESTRATION (Task 4)
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
    ) -> Union[str, Dict[str, Any], AsyncGenerator[str, None]]:
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
            stream: Optional streaming behavior. None=use formation config, True=force streaming,
                False=disable streaming. Only applies to sync processing.

        Returns:
            For sync processing: str with the agent's response content, or
                AsyncGenerator if streaming
            For async processing: Dict with request_id, status, and processing info
        """
        # Generate unique request ID for all requests (for tracking and logging)
        request_id = f"req_{generate_nanoid()}"
        timestamp = time.time()

        # Start request tracking with observability
        async with self.observability_manager.track_request(
            request_id=request_id,
            formation_id=self.formation_id,
            user_id=str(user_id) if user_id is not None else None,
        ):
            # Emit request received event
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_RECEIVED,
                level=observability.EventLevel.INFO,
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
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_VALIDATED,
                level=observability.EventLevel.INFO,
                data={
                    "message_valid": len(message.strip()) > 0,
                    "agent_exists": agent_name is None or agent_name in self.agents,
                },
                description=f"Request {request_id} validated",
            )

            # Use provided values or formation defaults
            webhook_url = webhook_url or self.async_webhook_url
            threshold_seconds = threshold_seconds or self.async_threshold_seconds

            # Determine streaming behavior
            use_streaming = stream if stream is not None else self.streaming

            # Async decision logic
            if use_async is False:
                use_async_mode = False  # Force synchronous
            elif use_async is True:
                use_async_mode = True  # Force asynchronous
                #  Debug - TODO: add observability
            else:  # use_async is None - intelligent decision
                if self.async_enable_estimation:
                    estimated_time = await self.time_estimator.estimate_processing_time(message)
                    use_async_mode = self.time_estimator.should_use_async(
                        estimated_time, threshold_seconds
                    )
                    #  Info - TODO: add observability
                    # ConversationEvents.ASYNC_THRESHOLD_DETECTED
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

                #  Info - TODO: add observability
                # ConversationEvents.ASYNC_PROCESSING_STARTED
                #     f"Request {request_id}: Started async processing "
                #     f"(estimated: {estimated_time:.1f}s)"
                # )

                initial_state = RequestState(
                    id=request_id,
                    status=RequestStatus.PROCESSING,
                    start_time=timestamp,
                    webhook_url=webhook_url,
                    estimated_completion=estimated_time,
                    user_id=user_id,
                    session_id=session_id,
                )
                await self.request_tracker.track_request(request_id, initial_state)

                # Start background processing
                asyncio.create_task(
                    self._execute_async_request(request_id, message, agent_name, user_id)
                )

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
                if use_streaming:
                    # Return streaming generator
                    return self._process_streaming_chat(message, agent_name, user_id)
                else:
                    # Non-streaming synchronous processing
                    start_time = time.time()

                    result = await self._process_sync_chat(message, agent_name, user_id)
                    processing_time = time.time() - start_time

                    # Emit performance monitoring completed event
                    observability.observe(
                        event_type=observability.SystemEvents.PERFORMANCE_DURATION_RECORDED,
                        level=observability.EventLevel.DEBUG,
                        data={
                            "operation": "sync_chat",
                            "processing_time": processing_time,
                            "message_length": len(message),
                            "performance_score": "good" if processing_time < 5.0 else "slow",
                            "phase": "completed",
                        },
                        description=f"Performance monitoring completed: {processing_time:.2f}s",
                    )

                    # Extract user-facing content from result
                    result_content = result.content if hasattr(result, "content") else str(result)
                    user_content = extract_user_content(result_content)

                    # Create unified response for internal consistency (streaming, observability)
                    # Note: unified_response is created for internal tracking but not returned
                    _ = create_unified_response(
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

                    # For sync mode, extract and return just the string content for user convenience
                    if user_content and len(user_content) > 0:
                        first_item = user_content[0]
                        if isinstance(first_item, dict) and "text" in first_item:
                            return first_item["text"]
                        elif isinstance(first_item, str):
                            return first_item

                    # Fallback to empty string
                    return ""

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

            # NEW: Check if clarification is needed before processing
            clarification_result = await self._check_clarification_needs_async(
                message, user_id, agent_name
            )

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
            result = await self._process_sync_chat(message, agent_name, user_id)
            processing_time = time.time() - start_time

            # Extract result content
            result_content = result.content if hasattr(result, "content") else str(result)

            await self.request_tracker.update_request(
                request_id, RequestStatus.COMPLETED, result=result_content
            )

            #  Info - TODO: add observability
            # ConversationEvents.ASYNC_PROCESSING_COMPLETED
            #  f"Request {request_id}: Completed async processing in {processing_time:.2f}s"

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
                    #  Info - TODO: add observability
                    # ConversationEvents.WEBHOOK_DELIVERED + ConversationEvents.RESPONSE_DELIVERED
                    _ = None  # remove this after implementing observability
                else:
                    #  Warning - TODO: add observability
                    # ConversationEvents.WEBHOOK_FAILED
                    _ = None  # remove this after implementing observability
            else:
                #  Error - TODO: add observability
                # ConversationEvents.WEBHOOK_FAILED
                _ = None  # remove this after implementing observability
                #     f"Request {request_id}: No webhook URL configured, skipping notification"
                # )

        except Exception as e:
            #  Warning - TODO: add observability
            # ErrorEvents.WARNING
            _ = e  # remove this after implementing observability

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
                #  Info - TODO: add observability
                # ConversationEvents.WEBHOOK_DELIVERED + ConversationEvents.RESPONSE_DELIVERED
            else:
                #  Error - TODO: add observability
                # ConversationEvents.WEBHOOK_FAILED
                _ = None  # remove this after implementing observability

    async def _process_sync_chat(
        self, message: str, agent_name: Optional[str], user_id: Any
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

            agent_name = await self.select_agent_for_message(message)

            # Emit agent selection completed event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_AGENT_SELECTED,
                level=observability.EventLevel.INFO,
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
        result = await agent.process_message(message, user_id=user_id_int)

        # NEW: Check if agent response contains clarification request
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

    async def _process_streaming_chat(
        self, message: str, agent_name: Optional[str], user_id: Any
    ) -> AsyncGenerator[str, None]:
        """
        Process chat with streaming response.

        This method handles streaming chat processing, yielding content chunks as they
        are generated by the agent's model. It follows the same agent selection and
        processing logic as sync chat but returns an AsyncGenerator for real-time
        streaming responses.

        Args:
            message: User's message to process
            agent_name: Optional specific agent to use (None for auto-selection)
            user_id: User identifier for memory and context

        Yields:
            str: Content chunks as they are generated by the model

        Note:
            Memory storage and observability events are handled after streaming
            completes to avoid blocking the stream.
        """
        # Use existing agent selection logic if no specific agent requested
        if agent_name is None:
            # Emit agent selection started event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_AGENT_SELECTION_STARTED,
                level=observability.EventLevel.INFO,
                data={"message": message[:200]},
                description="Starting agent selection process for streaming",
            )

            agent_name = await self.select_agent_for_message(message)

            # Emit agent selection completed event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_AGENT_SELECTED,
                level=observability.EventLevel.INFO,
                data={"selected_agent": agent_name},
                description=f"Agent selection completed for streaming: {agent_name}",
            )

        # Get the selected agent
        agent = self.get_agent(agent_name)

        # Convert user_id to int using flexible user ID handling
        user_id_int = None
        if user_id is not None:
            user_id_int = await self._enhance_existing_user_id_conversion(user_id)

        # Check if agent's model supports streaming
        if not hasattr(agent.model, "stream") or not callable(getattr(agent.model, "stream")):
            # Fallback to sync processing if streaming not supported
            result = await agent.process_message(message, user_id=user_id_int)
            result_content = result.content if hasattr(result, "content") else str(result)
            yield result_content
            return

        # Process the message with streaming enabled
        full_response = ""
        try:
            # Use agent's streaming capability
            async for chunk in agent.model.stream(message):
                if chunk:
                    full_response += chunk
                    yield chunk

            # After streaming completes, handle memory storage and observability
            # This happens asynchronously to not block the stream
            asyncio.create_task(
                self._handle_post_streaming_tasks(message, full_response, agent_name, user_id_int)
            )

        except Exception as e:
            # Handle streaming errors gracefully
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_PROCESSING_ERROR,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "agent": agent_name},
                description=f"Streaming error in agent {agent_name}: {str(e)}",
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
            #  Warning - TODO: add observability
            # ErrorEvents.RESOURCE_UNAVAILABLE
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
                from ...datatypes.clarification import ClarificationResultStatus

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
                    asyncio.create_task(
                        self._execute_async_request(
                            request_id,
                            enhanced_message,
                            None,  # Agent already selected
                            request_state.user_id,
                        )
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

    # The following operational setup methods have been moved to Formation:
    # - _initialize_memory_extractor() -> Formation handles memory extractor setup
    # - _initialize_external_registry_client() -> Formation handles A2A client setup
    # - _initialize_inbound_registry_client() -> Formation handles A2A registration setup
    # - _initialize_a2a_server() -> Formation handles A2A server setup

    async def _start_a2a_server(self) -> None:
        """
        Start the A2A formation server.

        This method starts the FastAPI-based HTTP server that hosts A2A services,
        allowing external formations to discover and communicate with this formation's
        agents. The server runs asynchronously and provides REST endpoints for:
        - Agent discovery and capability queries
        - Message routing to local agents
        - Health checks and status monitoring

        The server only starts if it was previously initialized in the configuration.
        If startup fails, an error is logged but the overlord continues operating
        without A2A server capabilities.

        Side Effects:
            - Starts HTTP server on configured host/port
            - Emits observability events for server startup success/failure
            - Makes local agents discoverable to external formations
        """
        try:
            if self.a2a_server:
                await self.a2a_server.start()

                #  Info - TODO: add observability
                # SystemEvents.A2A_SERVER_STARTED

        except Exception as e:
            #  Error - TODO: add observability
            # SystemEvents.A2A_SERVER_START_FAILED
            _ = e  # remove this after implementing observability

    async def _process_pending_agent_registrations(self) -> None:
        """
        Process pending external agent registrations.

        This method handles registration of agents with external A2A registries that
        were created before the A2A system was fully initialized. During overlord
        startup, agents may be created before the registry clients are available,
        so their registration is deferred until this method is called.

        The method processes all agents in the pending_external_registrations set
        and registers them concurrently with the external registry. Failed
        registrations are logged but don't prevent other registrations from proceeding.

        Side Effects:
            - Registers pending agents with external registries
            - Clears the pending_external_registrations set
            - Emits observability events for registration completion
        """
        try:
            # Skip if no registry client or no pending registrations
            if not self.inbound_registry_client or not hasattr(
                self, "pending_external_registrations"
            ):
                return

            # Collect registration tasks for concurrent execution
            registration_tasks = []

            for agent_id in self.pending_external_registrations:
                # Only register agents that still exist in the registry
                if agent_id in self.agents:
                    # Create async registration task for this agent
                    task = self._register_agent_with_external_registry(agent_id)
                    registration_tasks.append(task)

            # Execute all registrations concurrently to minimize latency
            if registration_tasks:
                await asyncio.gather(*registration_tasks, return_exceptions=True)

                # Clear the pending registrations set now that processing is complete
                self.pending_external_registrations.clear()

                #  Info - TODO: add observability
                # SystemEvents.A2A_AGENT_REGISTRATIONS_COMPLETED

        except Exception as e:
            #  Error - TODO: add observability
            # SystemEvents.A2A_AGENT_REGISTRATION_FAILED
            _ = e  # remove this after implementing observability

    async def _register_agent_with_external_registry(self, agent_id: str) -> None:
        """
        Register a single agent with external registry.

        This method registers a local agent with an external A2A registry, making it
        discoverable and accessible to other formations. The registration includes
        the agent's metadata such as description, capabilities, and current status.

        The method handles registration failures gracefully, logging errors without
        stopping the registration process for other agents.

        Args:
            agent_id: ID of the agent to register. Must exist in self.agents.

        Side Effects:
            - Sends registration request to external registry
            - Emits observability events for registration success/failure
            - Makes the agent discoverable to external formations
        """
        try:
            # Skip if no registry client available or agent doesn't exist
            if not self.inbound_registry_client or agent_id not in self.agents:
                return

            # Get the agent instance for metadata extraction
            agent = self.agents[agent_id]

            # Create agent registration payload with all relevant metadata
            agent_info = {
                "agent_id": agent_id,
                "formation_id": self.formation_id,
                "description": self.agent_descriptions.get(agent_id, ""),
                "capabilities": getattr(agent, "capabilities", []),
                "status": "active",  # All registered agents are considered active
            }

            # Send registration request to external registry
            await self.inbound_registry_client.register_agent(agent_info)

            #  Info - TODO: add observability
            # SystemEvents.A2A_AGENT_REGISTERED

        except Exception as e:
            #  Warning - TODO: add observability
            # SystemEvents.A2A_AGENT_REGISTRATION_FAILED
            _ = e  # remove this after implementing observability

    async def deregister_agent_from_external_registry(self, agent_id: str) -> None:
        """
        Deregister an agent from external registry.

        Args:
            agent_id: ID of the agent to deregister
        """
        try:
            if not self.inbound_registry_client:
                return

            await self.inbound_registry_client.deregister_agent(agent_id, self.formation_id)

            #  Info - TODO: add observability
            # SystemEvents.A2A_AGENT_DEREGISTERED

        except Exception as e:
            #  Warning - TODO: add observability
            # SystemEvents.A2A_AGENT_DEREGISTRATION_FAILED
            _ = e  # remove this after implementing observability
