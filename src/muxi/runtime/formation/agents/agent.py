# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Agent - AI Agent Implementation
# Description:  Core implementation of AI agents with memory and tool use
# Role:         Primary interface for language model interactions
# Usage:        Created and managed by the Overlord to process user messages
# Author:       Muxi Framework Team
#
# The Agent class is a fundamental component in the Muxi framework that:
#
# 1. Handles Direct Interactions
#    - Processes user messages and generates responses
#    - Maintains conversation context for coherent exchanges
#    - Integrates with memory systems for contextual awareness
#
# 2. Tool Integration
#    - Connects to external tools via MCP (Model Context Protocol)
#    - Parses and processes tool calls from language model responses
#    - Manages tool invocation and result incorporation
#
# 3. Memory Usage
#    - Delegates memory storage to the overlord
#    - Retrieves relevant context from memory systems
#    - Works with overlord for information extraction
#
# Agents are typically created and managed by the Overlord:
#
# Programmatic creation:
#   agent = overlord.create_agent(
#       agent_id="assistant",
#       model=model,
#       system_message="You are a helpful assistant."
#   )
#
# Direct usage:
#   response = await agent.process_message("Hello, how can you help me?")
#
# This file defines both the Agent class and the supporting MCPServer class
# for external tool integration.
# =============================================================================

import copy
import datetime
import re
import time
import traceback
from typing import Any, Callable, Deque, Dict, List, Optional, Union, cast

from ...datatypes.intent import IntentDetectionContext, IntentType
from ...datatypes.response import MuxiMessageContent, MuxiResponse
from ...services import observability, streaming
from ...services.intent import IntentDetectionService
from ...services.llm import LLM
from ...services.mcp.service import MCPService
from ...utils.fastjson import json
from ...utils.id_generator import generate_nanoid
from ...utils.security import sanitize_message_preview
from ..artifacts.extractor import extract_artifacts_from_tool_results
from ..background.cancellation import RequestCancelledException
from ..credentials import MissingCredentialError


class Agent:
    """
    An agent that interacts with users and tools.

    The Agent class manages interactions between users and language models,
    using its overlord's memory systems for context retention and retrieval.
    It can process messages, invoke tools via MCP, and maintain conversation state.
    """

    def __init__(
        self,
        model: LLM,
        overlord: Any,  # Forward reference to Overlord
        system_message: Optional[str] = None,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        request_timeout: Optional[int] = None,
        a2a_internal: bool = True,
        a2a_external: bool = True,
        knowledge_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the agent with a model, overlord, and optional parameters.

        Args:
            model: The language model for the agent to use. This model handles
                the core intelligence of the agent.
            overlord: The overlord that manages this agent. Provides
                access to memory systems and coordinates multi-agent systems.
            system_message: Optional system message to set the agent's behavior
                and persona. Defines the agent's role and capabilities.
            agent_id: Optional unique ID for the agent. If None, generates a UUID.
                Used for identification in memory systems and routing.
            name: Optional name for the agent (e.g., "Customer Service Bot").
                Used for display purposes.
            request_timeout: Optional timeout in seconds for MCP requests.
                Defaults to overlord's timeout if not specified.
            a2a_internal: Whether this agent participates in intra-formation A2A
                communication. Default True.
            a2a_external: Whether this agent participates in external A2A
                communication. Default True.
            knowledge_config: Optional configuration for agent domain knowledge.
                Contains sources and settings for the agent's knowledge base.
        """
        self.model = model
        self.overlord = overlord

        # Set up agent identification
        self.agent_id = agent_id or f"agt_{generate_nanoid()}"
        self.name = name or f"Agent-{self.agent_id}"

        # Initialize role and specialties for enhanced routing
        self.role: Optional[str] = None  # Will be set from config during agent creation
        self.specialties: List[str] = []  # Will be set from config during agent creation

        # Set up system message
        self.system_message = system_message or (
            "You are a helpful assistant that responds accurately to user queries. "
            "Provide detailed, factual responses and be transparent about uncertainty."
        )

        # Set up A2A configuration (single source of truth)
        self.a2a_internal = a2a_internal
        self.a2a_external = a2a_external

        # Set request timeout (use overlord's if not specified)
        if request_timeout is not None:
            self.request_timeout = request_timeout
        elif hasattr(overlord, "request_timeout"):
            self.request_timeout = overlord.request_timeout
        else:
            self.request_timeout = 60  # Default fallback

        # Set up MCP service access
        self._mcp_service = MCPService.get_instance()

        # Initialize knowledge handler
        self.knowledge_handler: Optional[Any] = None  # Will be KnowledgeHandler when imported
        self._knowledge_config = knowledge_config  # Store config for deferred initialization
        self._knowledge_initialized = False

        # Initialize the context with system message
        self._messages: List[Dict[str, Any]] = []

        # Initialize A2A history for loop detection and attempt limiting
        # Using collections.deque for efficient bounded history
        from collections import deque

        self._max_a2a_history_size = 20  # Keep last 20 delegation attempts
        self._a2a_history: Deque[str] = deque(maxlen=self._max_a2a_history_size)
        self._a2a_attempt_count = 0
        self._max_a2a_attempts = 3  # Prevent cascading failures

        if self.system_message:
            # Check if any MCP servers use user credentials
            user_cred_servers = []
            if self._mcp_service:
                user_cred_servers = self._mcp_service.get_user_credential_servers()

            if user_cred_servers:
                # Build explicit list
                server_list = ", ".join(f"'{server}'" for server in user_cred_servers)

                # Add instruction to the agent's system message
                auth_instruction = (
                    f"\n\nImportant MCP Authentication Guidance: "
                    f"The following MCP servers authenticate using user-specific credentials: {server_list}. "
                    f"When using tools from these servers, you MUST first use an identity discovery tool "
                    f"(such as get_me, whoami, get_authenticated_user, or similar) to identify who you are "
                    f"authenticated as before calling any other tools on that server. "
                    f"This ensures you understand the context and permissions of your actions."
                )
                enhanced_system_message = self.system_message + auth_instruction
            else:
                enhanced_system_message = self.system_message

            # Add error reporting honesty instruction
            error_reporting_instruction = (
                "\n\nIMPORTANT Error Reporting Guidelines: "
                "When you cannot fulfill a request, be honest and specific about the actual limitation. "
                "- If you lack the necessary tools: Say 'I don't have the tools needed to [specific action]' "
                "- If credentials are working (e.g., you can retrieve profile info): Don't blame credentials "
                "- If you successfully accessed some information but not all: Acknowledge what worked "
                "- Be PROACTIVE about limitations: If asked to 'list projects' but you can only search, "
                "immediately clarify: 'I can see you have X projects, but I can only search for specific "
                "ones by name, not list them all. Would you like to search for a particular project?' "
                "- Never offer to do something you cannot actually do"
            )
            enhanced_system_message = enhanced_system_message + error_reporting_instruction

            self._messages.append({"role": "system", "content": enhanced_system_message})

        # Emit agent initialization event
        pass  # REMOVED: init-phase observe() call

        # Register with A2A service for internal routing
        if self.a2a_internal:
            try:
                from ...services.a2a.client import A2AService

                a2a_service = A2AService()
                a2a_service.register_internal_handler(
                    self.agent_id, self._handle_generic_a2a_message
                )
            except Exception as e:
                # Log but don't fail agent initialization
                observability.observe(
                    event_type=observability.ErrorEvents.A2A_MESSAGE_HANDLING_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                    },
                    description=f"Failed to register agent with A2A service: {str(e)}",
                )

    def get_mcp_service(self) -> MCPService:
        """
        Get the centralized MCP service for tool integrations.

        Returns:
            The MCPService instance used by this agent for connecting to
            and interacting with external tools.
        """
        return self._mcp_service

    async def _initialize_knowledge(self, knowledge_config: Dict[str, Any]) -> None:
        """
        Initialize the knowledge handler from configuration.

        Args:
            knowledge_config: Configuration dictionary containing knowledge sources
                and settings for the agent's knowledge base.
        """
        try:
            # Build the embedding function via the shared adapter, mirroring
            # what SOP search already does (formation/workflow/sops.py).
            #
            # Why not ``self.model.generate_embeddings``?
            #   ``self.model`` is the agent's *chat* LLM (e.g. Anthropic
            #   Haiku). Earlier this code asked the chat LLM to embed text,
            #   which conceptually conflates two unrelated capabilities and
            #   in practice fell through to ``LLM.generate_embeddings``'s
            #   hardcoded ``openai/text-embedding-3-small`` default — so a
            #   formation that only declared an Anthropic chat key would
            #   silently die on knowledge ingestion with "OpenAI API key is
            #   required". Embedding capability is orthogonal to chat
            #   capability and must be resolved independently.
            #
            # Resolution order:
            #   1. ``working_memory.embedding_model_name`` — the canonical
            #      formation-wide embedding slug, populated by working
            #      memory init from ``llm.models[*].embedding`` (with
            #      fallback to the runtime default already baked into
            #      WorkingMemory).
            #   2. ``DEFAULT_EMBEDDING_MODEL`` (``local/nomic-ai/nomic-embed-text-v1.5``)
            #      — used only when working memory is unavailable. The
            #      local Nomic embedder ships in the runtime SIF so the
            #      offline path stays viable.
            #
            # The returned ``OneLLMEmbeddingAdapter`` delegates every
            # ``generate_embeddings(texts)`` call to
            # ``services.memory.embedding.embed`` — the documented "single
            # choke point" — so the knowledge handler now flows through the
            # same provider-routing, ``task``-stripping, and
            # ``EmbeddingResponse``-unpacking logic as every other
            # consumer (long-term memory, working memory, SOP search,
            # fusion engine).
            #
            # Imports are local (rather than module-top) to avoid the
            # circular import between ``agent.py`` and
            # ``formation.workflow.sops`` / ``agents.knowledge.handler``.
            from ...services.memory.embedding import DEFAULT_EMBEDDING_MODEL
            from ..workflow.sops import OneLLMEmbeddingAdapter
            from .knowledge.handler import KnowledgeHandler

            working_memory = getattr(self.overlord, "buffer_memory", None)
            # Resolution order for the knowledge-ingestion embedding model:
            #
            #   1. The formation-level ``llm.models.embedding`` capability,
            #      pulled from ``overlord._capability_models["embedding"]``.
            #      This is the model the formation author explicitly chose
            #      for high-quality knowledge / document embeddings (e.g.
            #      ``openai/text-embedding-3-small``).
            #   2. ``working_memory.embedding_model_name`` — the slug used
            #      by buffer / working memory. Per
            #      ``_initialize_buffer_memory`` this defaults to a *local*
            #      sentence-transformer (``local/nomic-ai/nomic-embed-text-v1.5``).
            #      Falling through to it for knowledge ingestion was the
            #      cause of the 8 GB+ jetsam kills on macOS during the
            #      6_knowledge tests: the formation declared
            #      ``openai/text-embedding-3-small`` but knowledge files
            #      were silently embedded with the local Nomic model,
            #      whose ONNX + CoreML compile alone allocates several
            #      gigabytes per ingest.
            #   3. ``DEFAULT_EMBEDDING_MODEL`` as a final offline fallback.
            #
            # Pulling from ``_capability_models`` first honors the
            # formation contract: when the operator declares an embedding
            # slug, knowledge ingestion uses it.
            embedding_slug: Optional[str] = None
            capability_models = getattr(self.overlord, "_capability_models", None) or {}
            embedding_cfg = capability_models.get("embedding") or {}
            if isinstance(embedding_cfg, dict):
                cap_model = embedding_cfg.get("model")
                if isinstance(cap_model, str) and cap_model:
                    embedding_slug = cap_model
            if not embedding_slug and working_memory is not None:
                slug_candidate = getattr(working_memory, "embedding_model_name", None)
                if isinstance(slug_candidate, str) and slug_candidate:
                    embedding_slug = slug_candidate
            if not embedding_slug:
                embedding_slug = DEFAULT_EMBEDDING_MODEL

            embedding_fn: Optional[Callable[..., Any]] = OneLLMEmbeddingAdapter(
                embedding_slug
            ).generate_embeddings

            # Get formation config from overlord if available
            formation_config = None
            if hasattr(self.overlord, "formation_config") and self.overlord.formation_config:
                formation_config = self.overlord.formation_config

            # Get formation_id from overlord
            formation_id = getattr(self.overlord, "formation_id", "default-formation")

            # Resolve the LLM used for reasoning-RAG tree building and
            # Method A navigation. Default is the agent's own text model
            # (PRD resolved question 1); ``knowledge.tree.model`` overrides
            # via the same alias / "provider/model" resolution as the
            # hierarchical model-selection feature. Resolution failure
            # falls back to the agent model (never blocks knowledge init).
            tree_llm = self.model
            tree_model_ref = (knowledge_config.get("tree") or {}).get("model")
            if tree_model_ref and hasattr(self.overlord, "resolve_model_override"):
                resolved = await self.overlord.resolve_model_override(
                    tree_model_ref, source="knowledge_tree"
                )
                if resolved is not None:
                    tree_llm = resolved

            # Create knowledge handler using the factory method with formation config.
            # ``working_memory`` was already resolved above when computing the
            # embedding slug; reuse it instead of re-fetching from the overlord.
            self.knowledge_handler = await KnowledgeHandler.from_agent_config(
                agent_id=self.agent_id,
                knowledge_config=knowledge_config,
                generate_embeddings_fn=embedding_fn,
                formation_config=formation_config,
                working_memory=working_memory,
                auto_inject_knowledge=True,
                formation_id=formation_id,  # Pass formation_id explicitly
                tree_llm=tree_llm,  # Reasoning-RAG tree build/navigation model
            )

            # Log successful knowledge initialization
            pass  # REMOVED: init-phase observe() call

        except Exception as e:
            # Fail fast: If knowledge is configured, it must work
            # InitEventFormatter will display the error clearly during init
            raise RuntimeError(
                f"Failed to initialize knowledge for agent '{self.agent_id}'. "
                f"Knowledge is configured but could not be loaded: {str(e)}"
            ) from e

    async def _ensure_knowledge_initialized(self) -> None:
        """
        Ensure knowledge handler is initialized if configuration is available.
        This is called on first use since constructor can't be async.
        """
        if self._knowledge_initialized or not self._knowledge_config:
            return

        await self._initialize_knowledge(self._knowledge_config)
        self._knowledge_initialized = True

    async def search_knowledge(
        self,
        query: str,
        limit: int = 5,
        include_memory: bool = True,
        unified: bool = False,
        # Enhanced coordination features (always enabled)
        deduplicate: bool = True,
        context_budget: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        """
        Search the agent's knowledge base and memory for relevant information.

        This method provides unified search across both domain knowledge sources
        and conversational memory, with enhanced coordination features always enabled.

        Args:
            query: The search query string
            limit: Maximum number of results to return per source
            include_memory: Whether to include memory search results
            unified: Return full dictionary format with separate source results
            deduplicate: Remove duplicate content between sources (always enabled)
            context_budget: Total context budget to allocate across sources

        Returns:
            List of unified results (default) or dictionary with separate source results
        """
        # Ensure knowledge handler is initialized before searching
        if self._knowledge_config and not self._knowledge_initialized:
            await self._ensure_knowledge_initialized()

        if not self.knowledge_handler:
            return {"knowledge": [], "memory": [], "unified": []} if unified else []

        try:
            # Smart query routing (always enabled)
            strategy = await self._analyze_query_for_routing(query)

            # Dynamic context budget management (always enabled)
            if context_budget:
                knowledge_limit, memory_limit = self._allocate_context_budget(
                    context_budget, strategy, limit
                )
            else:
                # Use strategy-based limits when no budget specified
                if strategy == "knowledge_only":
                    knowledge_limit, memory_limit = limit, 0
                elif strategy == "memory_only":
                    knowledge_limit, memory_limit = 0, limit
                else:  # strategy == "both"
                    knowledge_limit, memory_limit = limit, limit

            # Perform unified search with allocated limits
            results = await self.knowledge_handler.search_unified(
                query=query,
                knowledge_limit=knowledge_limit,
                memory_limit=memory_limit if include_memory else 0,
                include_memory=include_memory,
                session_id=session_id,
            )

            # Content deduplication (always enabled)
            if deduplicate and include_memory:
                results = self._deduplicate_results(results)

            # Enhanced unified ranking (always enabled)
            if include_memory:
                enhanced_unified = self._create_enhanced_unified_ranking(
                    knowledge_results=results.get("knowledge", []),
                    memory_results=results.get("memory", []),
                    query=query,
                    strategy=strategy,
                    budget=context_budget or (limit * 2),
                )
                results["unified"] = enhanced_unified

            # Return format based on unified parameter
            if unified:
                return results
            else:
                # Return enhanced unified results as the default
                return results.get("unified", results.get("knowledge", []))

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SEARCH_FAILED,
                level=observability.EventLevel.ERROR,
                data={"agent_id": self.agent_id, "error": str(e), "phase": "knowledge_search"},
                description=f"Error in enhanced knowledge search: {str(e)}",
            )
            return {"knowledge": [], "memory": [], "unified": []} if unified else []

    async def _analyze_query_for_routing(self, query: str) -> str:
        """
        Analyze query to determine optimal search strategy.

        Uses the IntentDetectionService for language-agnostic intent detection
        to determine whether to search knowledge bases, memory, or both.

        Args:
            query: The search query to analyze

        Returns:
            Search strategy: "knowledge_only", "memory_only", or "both"
        """
        # Try to use intent detection service if available
        try:
            # Get or create intent detection service
            if not hasattr(self, "_intent_detector"):
                # Use existing model instance
                llm_service = self.model

                self._intent_detector = IntentDetectionService(
                    llm_service=llm_service, enable_cache=True
                )

            # Detect query type using LLM
            # Add recent conversation context if available
            recent_messages = (
                [
                    {
                        "role": str(msg.get("role", "")),
                        "content": self._content_to_text(
                            cast(Union[str, List[MuxiMessageContent], None], msg.get("content"))
                        )[:200],
                    }
                    for msg in self._messages[-5:]
                ]
                if self._messages
                else None
            )
            context = IntentDetectionContext(
                options=None,
                recent_messages=recent_messages,
                user_language=None,
                user_timezone=None,
            )

            result = await self._intent_detector.detect_intent(
                text=query, intent_type=IntentType.QUERY_TYPE, context=context
            )

            # Map intent to strategy
            if result.confidence > 0.7:  # High confidence
                if result.intent == "knowledge":
                    return "knowledge_only"
                elif result.intent == "memory":
                    return "memory_only"
                elif result.intent == "mixed":
                    return "both"

            # Low confidence or unclear - use both
            return "both"

        except Exception as e:
            # Fall back to simple keyword-based detection
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.WARNING,
                data={"agent_id": self.agent_id, "error": str(e), "phase": "intent_detection"},
                description=f"Intent detection failed, using fallback: {str(e)}",
            )
            return self._fallback_query_routing(query)

    def _fallback_query_routing(self, query: str) -> str:
        """
        Fallback keyword-based query routing.

        Used when intent detection service is not available.
        """
        query_lower = query.lower()

        # Simple heuristics for fallback
        memory_keywords = [
            "remember",
            "last time",
            "previously",
            "you said",
            "we discussed",
            "earlier",
        ]
        knowledge_keywords = ["what is", "how to", "explain", "define", "why", "tutorial"]

        has_memory = any(keyword in query_lower for keyword in memory_keywords)
        has_knowledge = any(keyword in query_lower for keyword in knowledge_keywords)

        if has_memory and not has_knowledge:
            return "memory_only"
        elif has_knowledge and not has_memory:
            return "knowledge_only"
        else:
            return "both"

    def _allocate_context_budget(
        self, total_budget: int, strategy: str, base_limit: int
    ) -> tuple[int, int]:
        """
        Allocate context budget between knowledge and memory sources.

        Allocates context budget between knowledge and memory sources by
        intelligently distributing the available context budget based on the
        determined search strategy.

        Args:
            total_budget: Total context budget to allocate
            strategy: Search strategy ("knowledge_only", "memory_only", or "both")
            base_limit: Base limit per source when strategy is "both"

        Returns:
            Tuple of (knowledge_limit, memory_limit)
        """
        if strategy == "knowledge_only":
            return (total_budget, 0)
        elif strategy == "memory_only":
            return (0, total_budget)
        else:
            # For "both" strategy, allocate based on a balanced approach
            # Give slight preference to knowledge for factual queries
            # but ensure both sources get meaningful allocation

            if total_budget <= 2:
                # Very small budget - give one to each
                return (1, 1)
            elif total_budget <= 4:
                # Small budget - split evenly
                half = total_budget // 2
                return (half, total_budget - half)
            else:
                # Larger budget - use 60/40 split favoring knowledge
                # but ensure minimum of 2 for each source
                knowledge_portion = max(2, int(total_budget * 0.6))
                memory_portion = max(2, total_budget - knowledge_portion)

                # Adjust if we exceeded total budget
                if knowledge_portion + memory_portion > total_budget:
                    knowledge_portion = total_budget - memory_portion

                return (knowledge_portion, memory_portion)

    def _deduplicate_results(
        self, results: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Remove duplicate content between knowledge and memory results.

        Removes duplicate content between knowledge and memory results by identifying
        and removing semantically similar content between knowledge sources
        and memory to avoid redundant information in the unified results.

        Args:
            results: Dictionary with 'knowledge' and 'memory' result lists

        Returns:
            Dictionary with deduplicated results
        """
        knowledge_results = results.get("knowledge", [])
        memory_results = results.get("memory", [])

        if not knowledge_results or not memory_results:
            return results

        # Simple text-based deduplication
        # For more sophisticated deduplication, we could use embedding similarity
        deduplicated_memory = []

        # Extract content from knowledge results for comparison
        knowledge_contents = set()
        for k_result in knowledge_results:
            content = k_result.get("content", "").strip().lower()
            if content:
                # Use first 100 characters as a fingerprint
                knowledge_contents.add(content[:100])

        # Filter memory results that don't significantly overlap with knowledge
        for m_result in memory_results:
            memory_content = m_result.get("content", "").strip().lower()
            if not memory_content:
                continue

            # Check for significant overlap with knowledge content
            memory_fingerprint = memory_content[:100]
            is_duplicate = False

            for k_fingerprint in knowledge_contents:
                # Calculate simple overlap ratio
                if len(memory_fingerprint) > 0 and len(k_fingerprint) > 0:
                    # Simple string similarity check
                    overlap = self._calculate_text_overlap(memory_fingerprint, k_fingerprint)
                    if overlap > 0.7:  # 70% similarity threshold
                        is_duplicate = True
                        break

            if not is_duplicate:
                deduplicated_memory.append(m_result)

        return {"knowledge": knowledge_results, "memory": deduplicated_memory}

    def _calculate_text_overlap(self, text1: str, text2: str) -> float:
        """
        Calculate simple text overlap ratio between two strings.

        Args:
            text1: First text string
            text2: Second text string

        Returns:
            Overlap ratio between 0.0 and 1.0
        """
        if not text1 or not text2:
            return 0.0

        # Simple word-based overlap calculation
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def _create_enhanced_unified_ranking(
        self,
        knowledge_results: List[Dict[str, Any]],
        memory_results: List[Dict[str, Any]],
        query: str,
        strategy: str,
        budget: int,
    ) -> List[Dict[str, Any]]:
        """
        Create enhanced unified ranking of knowledge and memory results.

        Creates enhanced unified ranking of knowledge and memory results by intelligently
        combining and ranking results from both sources based on relevance,
        recency, and the search strategy used.

        Args:
            knowledge_results: Results from knowledge sources
            memory_results: Results from memory sources
            query: Original search query for relevance scoring
            strategy: Search strategy used
            budget: Total context budget to respect

        Returns:
            List of unified results ranked by enhanced scoring
        """
        unified_results = []

        # Add knowledge results with enhanced scoring
        for result in knowledge_results:
            enhanced_result = result.copy()
            enhanced_result["source_type"] = "knowledge"

            # Calculate enhanced score based on strategy
            base_score = result.get("relevance", result.get("score", 0.5))

            if strategy == "knowledge_only":
                # Boost knowledge scores when it's the primary source
                enhanced_score = min(1.0, base_score * 1.2)
            elif strategy == "both":
                # Standard scoring for balanced approach
                enhanced_score = base_score
            else:
                # Lower knowledge scores when memory is preferred
                enhanced_score = base_score * 0.8

            enhanced_result["enhanced_score"] = enhanced_score
            unified_results.append(enhanced_result)

        # Add memory results with enhanced scoring
        for result in memory_results:
            enhanced_result = result.copy()
            enhanced_result["source_type"] = "memory"

            # Calculate enhanced score based on strategy
            base_score = result.get("relevance", result.get("score", 0.5))

            # Memory results often have recency bonus
            recency_bonus = self._calculate_recency_bonus(result)

            if strategy == "memory_only":
                # Boost memory scores when it's the primary source
                enhanced_score = min(1.0, (base_score + recency_bonus) * 1.2)
            elif strategy == "both":
                # Add recency bonus for balanced approach
                enhanced_score = min(1.0, base_score + recency_bonus)
            else:
                # Lower memory scores when knowledge is preferred
                enhanced_score = (base_score + recency_bonus) * 0.8

            enhanced_result["enhanced_score"] = enhanced_score
            unified_results.append(enhanced_result)

        # Sort by enhanced score (descending)
        unified_results.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)

        # Respect context budget
        if len(unified_results) > budget:
            unified_results = unified_results[:budget]

        # Add ranking metadata
        for i, result in enumerate(unified_results):
            result["unified_rank"] = i + 1
            result["strategy_used"] = strategy

        return unified_results

    def _calculate_recency_bonus(self, result: Dict[str, Any]) -> float:
        """
        Calculate recency bonus for memory results.

        Args:
            result: Memory search result

        Returns:
            Recency bonus value between 0.0 and 0.3
        """
        # Look for timestamp in various possible fields
        timestamp = result.get("timestamp") or result.get("created_at") or result.get("time")

        if not timestamp:
            return 0.0

        try:
            current_time = time.time()

            # Convert timestamp to float if it's not already
            if isinstance(timestamp, str):
                # Try to parse ISO format or other common formats
                import datetime

                try:
                    dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    timestamp = dt.timestamp()
                except (ValueError, TypeError):
                    return 0.0

            # Calculate age in hours
            age_hours = (current_time - timestamp) / 3600

            # Recency bonus decreases with age
            if age_hours < 1:
                return 0.3  # Very recent (last hour)
            elif age_hours < 24:
                return 0.2  # Recent (last day)
            elif age_hours < 168:  # Last week
                return 0.1
            else:
                return 0.0  # Older than a week

        except (ValueError, TypeError, AttributeError):
            return 0.0

    def _should_bypass_planning(
        self, is_a2a_task: bool, tools: Optional[List[Dict[str, Any]]]
    ) -> bool:
        """Only bypass planning for delegated A2A tasks when no tools are available."""
        return is_a2a_task and not tools

    def _serialize_planning_result_for_synthesis(self, result: Any) -> str:
        """Serialize planning/tool results into a stable text block for synthesis."""
        if isinstance(result, dict):
            serializable_result = dict(result)
            serializable_result.pop("_artifact", None)
            try:
                return json.dumps(serializable_result, indent=2)
            except TypeError:
                return str(serializable_result)
        return str(result)

    @staticmethod
    def _collect_attached_artifact_lines(my_results: Dict[str, Any]) -> List[str]:
        """Return one human-readable line per ``_artifact`` in ``my_results``.

        ``_serialize_planning_result_for_synthesis`` strips ``_artifact`` from
        the per-result text block before showing it to the synthesis LLM.
        That means the LLM has no ground-truth signal that any file came
        through and is free to hallucinate "the file didn't make it" from
        the surrounding metadata. We restore that signal by collecting the
        filenames + format + size up front and surfacing them as a
        dedicated block in the synthesis prompt.

        Handles both ``MuxiArtifact`` Pydantic instances and dict-shaped
        artifact metadata; both shapes occur in the wild depending on the
        producer (artifact service vs. legacy fallbacks).
        """

        def _get(obj: Any, *keys: str) -> Any:
            for key in keys:
                attr_value = getattr(obj, key, None)
                if attr_value is not None:
                    return attr_value
                if isinstance(obj, dict) and obj.get(key) is not None:
                    return obj[key]
            return None

        lines: List[str] = []
        for result in my_results.values():
            if not isinstance(result, dict):
                continue
            artifact = result.get("_artifact")
            if artifact is None:
                continue

            filename = _get(artifact, "filename", "name") or "(unnamed file)"
            fmt = _get(artifact, "format")
            atype = _get(artifact, "type")
            meta = _get(artifact, "metadata")
            size_bytes = _get(meta, "size_bytes") if meta is not None else None

            descriptor_parts = [str(p) for p in (atype, fmt) if p]
            descriptor = "/".join(descriptor_parts) if descriptor_parts else None
            size_str = (
                f"{size_bytes / 1024:.1f} KB" if isinstance(size_bytes, (int, float)) else None
            )
            bracket = ", ".join(p for p in (descriptor, size_str) if p)
            lines.append(f"- {filename}" + (f" ({bracket})" if bracket else ""))
        return lines

    def _assemble_messages_from_clean_context(
        self, clean_chat_context: Dict[str, Any], system_message_base: str
    ) -> List[Dict[str, Any]]:
        """Assemble a chat-API-shaped message list from the orchestrator's bundle.

        Returns the role-turn transcript:

            [system_with_addendum, user_1, asst_1, ..., user_N, current_user]

        The system message is the agent's own ``system_message`` (passed
        in pre-enriched with auth/error-reporting instructions) plus an
        optional addendum carrying user profile, long-term memories,
        and file-processing results. Buffer history fills the role
        turns; the current user message goes at the tail. No
        ``=== CURRENT REQUEST ===`` / ``=== CONVERSATION CONTEXT ===``
        markers — those are only for the analyzer pipeline.
        """
        addendum_parts: List[str] = []
        user_profile_text = clean_chat_context.get("user_profile_text") or ""
        long_term_memories = clean_chat_context.get("long_term_memories") or ""
        file_results = clean_chat_context.get("file_results") or ""
        if user_profile_text:
            addendum_parts.append("=== USER PROFILE ===")
            addendum_parts.append(user_profile_text)
        if long_term_memories:
            if addendum_parts:
                addendum_parts.append("")
            addendum_parts.append("=== RELEVANT MEMORIES ===")
            addendum_parts.append(long_term_memories)
        if file_results:
            if addendum_parts:
                addendum_parts.append("")
            addendum_parts.append("=== FILE PROCESSING RESULTS ===")
            addendum_parts.append(file_results)

        if addendum_parts:
            system_content = system_message_base + "\n\n" + "\n".join(addendum_parts)
        else:
            system_content = system_message_base

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_content}]

        for turn in clean_chat_context.get("buffer_turns") or []:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        current_user_message = clean_chat_context.get("current_user_message") or ""
        if current_user_message:
            messages.append({"role": "user", "content": current_user_message})

        return messages

    def _get_planning_response_synthesis_system_prompt(self) -> str:
        """Return the system prompt for agent-side planning response synthesis."""
        return (
            "You are a helpful assistant preparing the final user-facing response from tool and "
            "delegated task results. Base your answer only on the provided results. Preserve "
            "explicit dates, weekdays, times, and time ranges exactly as they appear in the "
            "results. Do not rewrite absolute dates/times into relative labels like 'today', "
            "'tomorrow', or 'yesterday' unless the source results already use those exact words. "
            "If information is missing or unavailable, say so explicitly instead of guessing."
        )

    def _build_planning_response_synthesis_prompt(
        self, user_request: str, my_results: Dict[str, Any], planning_response_parts: List[str]
    ) -> str:
        """Build the user prompt for synthesizing planning execution results."""
        prompt_parts = [
            f"Original user request: {user_request}",
            "",
            "Available execution results:",
            "",
        ]

        for placeholder, result in my_results.items():
            prompt_parts.append(f"### {placeholder}")
            prompt_parts.append(self._serialize_planning_result_for_synthesis(result))
            prompt_parts.append("")

        if planning_response_parts:
            prompt_parts.append("Delegated agent responses:")
            for i, response_part in enumerate(planning_response_parts, 1):
                prompt_parts.append(f"### Response {i}")
                prompt_parts.append(str(response_part))
                prompt_parts.append("")

        attached_artifacts = self._collect_attached_artifact_lines(my_results)
        if attached_artifacts:
            prompt_parts.extend(
                [
                    "FILES ALREADY ATTACHED TO THIS RESPONSE:",
                    *attached_artifacts,
                    "",
                    "These files have been successfully generated and will surface in the user's UI",
                    "regardless of what you write below. Do NOT claim a file is missing, did not come",
                    "through, or that generation failed when this list is non-empty. You MAY mention",
                    "the filename(s) naturally in your reply.",
                    "",
                ]
            )

        prompt_parts.extend(
            [
                "Write the final response to the user.",
                "- Keep the tone natural and helpful.",
                "- Preserve explicit dates, weekdays, times, and time ranges exactly as given.",
                "- Do not turn absolute dates into relative words like 'today' or 'recently' unless the result already says that.",
                "- Mention any missing or failed data plainly instead of filling gaps with assumptions.",
            ]
        )

        return "\n".join(prompt_parts)

    async def _synthesize_planning_execution_response(
        self, user_request: str, my_results: Dict[str, Any], planning_response_parts: List[str]
    ) -> Optional[str]:
        """Build the agent's planning-execution response.

        Historically this issued an LLM call to synthesize prose from
        ``my_results`` and ``planning_response_parts``. That synthesis
        step was redundant: the overlord's ``_apply_persona`` pass
        always runs on the way back to the user and is now responsible
        for absorbing structured input (see
        ``Overlord._apply_persona`` and the workflow consolidator).

        This method now returns a deterministic, structured raw
        response — no LLM call, no extra latency. The signature is
        preserved so existing call sites and test fixtures keep
        working.
        """
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "phase": "synthesis_skipped",
                "reason": "always_skip_v2",
                "tool_result_count": len(my_results),
                "delegated_response_count": len(planning_response_parts),
            },
            description=(
                f"Agent {self.agent_id} skipped planning synthesis "
                f"(always_skip_v2: {len(my_results)} results, "
                f"{len(planning_response_parts)} delegations)"
            ),
        )

        raw_response = self._build_raw_response(my_results, planning_response_parts)
        return raw_response or None

    @staticmethod
    def _build_raw_response(
        my_results: Dict[str, Any],
        planning_response_parts: List[str],
    ) -> str:
        """Render planning execution results as a deterministic raw string.

        The output is structured for the overlord's persona LLM to
        absorb directly: each tool result rendered under its
        placeholder name, each delegated agent response appended
        verbatim, artifact filenames called out inline.

        Output format::

            ### {placeholder_1}
            {result text}

            ### {placeholder_2}
            {result text}
            Files Attached: foo.pdf, bar.png

            ### Delegated Response 1
            {delegated agent prose}

        No LLM call. No prompt template. Pure string formatting.
        """
        sections: List[str] = []

        if my_results:
            for placeholder, result in my_results.items():
                section_lines: List[str] = [f"### {placeholder}"]

                if isinstance(result, dict):
                    artifact_meta = result.get("_artifact")
                    raw_text = result.get("result", result.get("output"))
                    if isinstance(raw_text, str) and raw_text.strip():
                        section_lines.append(raw_text.strip())
                    elif isinstance(raw_text, dict):
                        for key, value in raw_text.items():
                            if value is None or value == "":
                                continue
                            section_lines.append(f"{key}: {value}")
                    elif raw_text is not None:
                        stripped = str(raw_text).strip()
                        if stripped:
                            section_lines.append(stripped)
                    else:
                        # Dict result with no result/output key — render
                        # the whole dict as key:value lines so nothing
                        # actionable disappears.
                        rendered_keys = [
                            f"{k}: {v}"
                            for k, v in result.items()
                            if k != "_artifact" and v is not None and v != ""
                        ]
                        if rendered_keys:
                            section_lines.extend(rendered_keys)
                        elif artifact_meta is None:
                            section_lines.append("(empty result)")

                    if isinstance(artifact_meta, dict):
                        filename = artifact_meta.get("filename") or artifact_meta.get("name")
                        if filename:
                            section_lines.append(f"Files Attached: {filename}")
                else:
                    section_lines.append(str(result).strip())

                sections.append("\n".join(section_lines))

        if planning_response_parts:
            # Number only the delegated parts we actually emit so the
            # persona LLM sees a contiguous 1..N sequence. Numbering by
            # the original list position would leave gaps for empty /
            # None entries (e.g. ``["", None, "X"]`` → "Delegated
            # Response 3" with no 1 or 2), which carries no semantic
            # meaning and just confuses the model.
            delegated_idx = 0
            for part in planning_response_parts:
                if not part:
                    continue
                delegated_idx += 1
                sections.append(f"### Delegated Response {delegated_idx}\n{part}")

        if not sections:
            return ""

        return "\n\n".join(sections)

    @staticmethod
    def _is_pure_artifact_result(my_results: Dict[str, Any]) -> bool:
        """Return True iff every planning result carries an ``_artifact`` key.

        A pure-artifact result means the user's intent ("create a PDF",
        "generate a chart") is satisfied by the artifact files themselves
        — there is no textual data the LLM needs to summarize. Returns
        False on empty input because an empty result set is more likely
        to indicate something went wrong (the user expects *some* output)
        than that we should silently bypass synthesis.
        """
        if not my_results:
            return False
        for result in my_results.values():
            if not isinstance(result, dict) or "_artifact" not in result:
                return False
        return True

    def _is_streaming_active(self) -> bool:
        """Return True iff the user has an alternative feedback channel.

        Two paths qualify:
          * ``overlord.response.streaming = true`` in the formation YAML
            (formation-level opt-in).
          * The current request id is registered with the streaming
            manager (per-request opt-in via the SSE/streaming endpoint).

        Used as the gate for the skip-synthesis fast path: when
        streaming is on the user has been receiving real-time tool
        progress events and a separate ~5s LLM synthesis call adds
        little value over a deterministic acknowledgment.
        """
        if self.overlord is not None and getattr(self.overlord, "streaming", False):
            return True
        try:
            from ...services.observability.context import get_current_request_context
            from ...services.streaming import streaming_manager

            ctx = get_current_request_context()
            if ctx is not None and getattr(ctx, "id", None):
                return streaming_manager.is_streaming_enabled(ctx.id)
        except Exception:
            # Streaming detection is best-effort; if it fails we fall back
            # to the safe behavior (run synthesis), so swallow.
            pass
        return False

    @staticmethod
    def _build_artifact_only_response(my_results: Dict[str, Any]) -> str:
        """Compose a short deterministic message for the skip-synthesis path.

        The wording mirrors what the LLM-driven synthesis typically produces
        for artifact responses ("Done — I've created your.pdf for you.")
        but costs zero LLM tokens. We never invent details about the
        artifact contents; the artifact itself carries the user-visible
        payload.
        """
        artifact_count = len(my_results)
        if artifact_count == 1:
            result = next(iter(my_results.values()))
            artifact_meta = result.get("_artifact") if isinstance(result, dict) else None
            filename: Optional[str] = None
            if isinstance(artifact_meta, dict):
                filename = artifact_meta.get("filename") or artifact_meta.get("name")
            if filename:
                return f"Done — I've created {filename} for you."
            return "Done — I've created the file for you."
        return f"Done — I've created {artifact_count} files for you."

    @staticmethod
    def _content_to_text(content: Union[str, List[MuxiMessageContent], None]) -> str:
        """Extract plain text from mixed internal message content."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content

        text_parts: List[str] = []
        for item in content:
            text_value = item.text if isinstance(item, MuxiMessageContent) else None
            if text_value:
                text_parts.append(text_value)

        return " ".join(text_parts)

    @staticmethod
    def _extract_current_request_text(
        user_message: str, *, include_context_lines: bool = False
    ) -> str:
        """Extract the current request section from enhanced chat prompts."""
        if not isinstance(user_message, str) or not user_message.strip():
            return ""
        if "=== CURRENT REQUEST ===" not in user_message:
            return user_message

        lines = user_message.splitlines()
        in_current_request = False
        captured_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped == "=== CURRENT REQUEST ===":
                in_current_request = True
                continue
            if not in_current_request:
                continue
            if stripped.startswith("==="):
                break
            if stripped.startswith("User:"):
                captured_lines.append(stripped[5:].strip())
                continue
            if not include_context_lines and stripped.startswith("[Context:"):
                continue
            captured_lines.append(line.rstrip())

        extracted = "\n".join(captured_lines).strip()
        return extracted or user_message

    async def _call_active_model(self, active_model: LLM, method: str, *args, **kwargs):
        """
        Invoke an LLM method on the active model with override degradation.

        When ``active_model`` is a hierarchical override (not the agent's own
        model) and the call fails, log the failure and retry once with the
        agent's default model - a model-selection problem must never crash the
        chat turn. Calls on the agent's own model propagate errors unchanged.
        """
        if active_model is self.model:
            return await getattr(self.model, method)(*args, **kwargs)

        try:
            return await getattr(active_model, method)(*args, **kwargs)
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.MODEL_OVERRIDE_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "override_model": getattr(active_model, "model", None),
                    "fallback_model": getattr(self.model, "model", None),
                    "method": method,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=(
                    f"Override model '{getattr(active_model, 'model', None)}' failed for "
                    f"agent {self.agent_id}; degrading to the agent's default model"
                ),
            )
            return await getattr(self.model, method)(*args, **kwargs)

    async def process_message(
        self,
        message: Union[str, MuxiResponse],
        user_id: Any = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        is_a2a_task: bool = False,
        clean_chat_context: Optional[Dict[str, Any]] = None,
        model_override: Optional[LLM] = None,
    ) -> MuxiResponse:
        """
        Process a message from the overlord and generate a response.

        This method handles:
        1. Converting input to MuxiResponse format
        2. Adding the message to memory via the overlord
        3. Updating conversation context
        4. Searching domain knowledge (if available)
        5. Processing the message with the model
        6. Handling any tool calls in the response
        7. Storing the response in memory
        8. Supporting agent clarification requests to overlord

        Args:
            message: The message from the overlord, either as a string or an MuxiResponse.
                Contains the content to be processed by the agent.
            user_id: Optional user ID for multi-user support. Used for memory
                isolation and user-specific context.
            clean_chat_context: Optional bundle from
                ``ChatOrchestrator._build_clean_chat_context`` carrying
                buffer history as proper role turns plus the raw
                current user message and addendum context (profile,
                long-term memories, file results). When supplied,
                ``self._messages`` is rebuilt from this bundle so the
                LLM call uses a proper chat-API-shape transcript
                instead of the accumulated marker-formatted blobs.
            model_override: Optional LLM instance to use for this call instead
                of the agent's default model (hierarchical model selection:
                trigger/SOP/skill/step overrides resolved by the caller). If
                the override model fails at call time, the agent degrades to
                its default model rather than failing the turn.

        Returns:
            The agent's response as an MuxiResponse, possibly including tool call results
            or clarification requests in metadata.
        """
        # Effective model for this call: hierarchical override (trigger/SOP/
        # skill/step, resolved upstream) or the agent's own model. All
        # response-generating LLM calls in this method go through
        # ``_call_active_model`` so an override failure degrades to the
        # agent default instead of failing the chat turn.
        active_model = model_override or self.model

        # Convert string message to MuxiResponse if needed
        if isinstance(message, str):
            user_message = message
            message_obj = MuxiResponse(role="user", content=user_message)
        else:
            message_obj = message
            user_message = self._content_to_text(message.content)

        # When the orchestrator hands us a clean role-turn bundle,
        # prefer the raw user message it carries — this is the
        # un-enhanced original text the user actually typed, while
        # ``message`` at this point is the analyzer-formatted
        # ``=== CURRENT REQUEST ===`` blob. Using the raw text in
        # the LLM transcript matches how a normal chat API call
        # looks; the analyzer blob is only used in the path before
        # we got here (clarification / planning / intent extraction).
        if clean_chat_context and clean_chat_context.get("current_user_message"):
            user_message = clean_chat_context["current_user_message"]

        content = user_message

        # Store message metadata for use in other methods (like A2A routing)
        self._current_message_metadata = (
            message_obj.metadata if hasattr(message_obj, "metadata") else None
        )

        # Store session_id for skill activation scoping
        self._current_session_id = session_id or "default"
        self._current_request_id = request_id

        # Reset A2A attempt counter for each new request to prevent cascading failures
        self._a2a_attempt_count = 0

        # Emit agent message processing event with enhanced metadata
        tool_count = len(self.tools) if hasattr(self, "tools") and self.tools else 0
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "message_length": len(user_message),
                "has_tools": tool_count > 0,
                "tool_count": tool_count,
                "model_used": getattr(active_model, "model", None) or active_model,
                "model_overridden": model_override is not None,
            },
            description=f"Agent {self.agent_id} ({self.name}) starting message processing",
        )

        # Memory storage is handled by chat orchestrator - agent should not store messages
        # This prevents duplicate storage of enhanced messages

        if clean_chat_context is not None:
            # New path (PR #161): rebuild ``self._messages`` from the
            # orchestrator's clean role-turn bundle every turn rather
            # than accumulating marker-formatted blobs in agent-instance
            # state. This produces a chat-API-shape transcript
            # (``[system, user, asst, user, asst, ..., user]``) that
            # matches how a normal direct LLM call looks — fixing the
            # double-encoded-history confusion that caused Sonnet 4.6
            # to claim missing context on simple multi-turn chats.
            #
            # Use the agent's bootstrap system message as the base
            # (already enriched with auth/error-reporting at __init__
            # time) and let the helper append profile/memories/file
            # results as a system addendum. Buffer history fills the
            # role turns; the current user message ends the list.
            base_system = (
                self._messages[0]["content"]
                if self._messages and self._messages[0].get("role") == "system"
                else self.system_message
            )
            # Strip any previously injected date prefix so we don't
            # accumulate them across turns.
            if base_system.startswith("It is now ") and ".\n" in base_system:
                base_system = base_system[base_system.index(".\n") + 2 :]
            self._messages = self._assemble_messages_from_clean_context(
                clean_chat_context, base_system
            )

        # Keep the system message current date/time fresh on every request.
        # Agents are long-lived; without this the model falls back to its training-data date.
        if self._messages and self._messages[0].get("role") == "system":
            import time as _time
            from datetime import datetime as _dt

            now = _dt.now()
            tz_name = _dt.now().astimezone().tzname() or _time.tzname[0]
            now_str = f"{now.strftime('%A, %B %d, %Y %H:%M')} ({tz_name})"
            base = self._messages[0]["content"]
            # Strip any previously injected date prefix before prepending a fresh one
            if base.startswith("It is now ") and ".\n" in base:
                base = base[base.index(".\n") + 2 :]
            self._messages[0]["content"] = f"It is now {now_str}.\n{base}"

        # Lessons learned injection (Memory Revamp Phase 2): a dynamic block
        # appended AFTER the static persona/addendum so the cache-stable
        # prefix stays intact. The block is loaded once per session and held
        # stable (no mid-session refresh); the duplicate check keeps the
        # accumulating non-clean-context path from re-appending it.
        captains_log = getattr(self.overlord, "captains_log", None) if self.overlord else None
        if (
            captains_log
            and user_id is not None
            and self._messages
            and self._messages[0].get("role") == "system"
        ):
            lessons_block = await captains_log.get_lessons_prompt_block(
                user_id, self.agent_id, session_id
            )
            if lessons_block and lessons_block not in self._messages[0]["content"]:
                self._messages[0]["content"] = f"{self._messages[0]['content']}\n\n{lessons_block}"

        # Add message to conversation context — but only if the
        # orchestrator didn't already do it for us via the clean bundle
        # rebuild above. Double-appending would put two copies of the
        # current user turn in the LLM context.
        if clean_chat_context is None:
            self._messages.append({"role": "user", "content": user_message})

        # Store current user message for credential selection context
        self._current_user_message = user_message

        # Search knowledge and memory if handler is available
        context_enhancement = ""

        # First, check for recent document uploads
        recent_docs = []
        if self.overlord and hasattr(self.overlord, "get_recent_documents"):
            # Pass session_id to get documents from the current session
            recent_docs = self.overlord.get_recent_documents(session_id=session_id)

        if self._knowledge_config:  # Check if knowledge config exists
            try:
                # Use unified search to get both knowledge and memory context
                search_results = cast(
                    Dict[str, List[Dict[str, Any]]],
                    await self.search_knowledge(
                        query=user_message,
                        limit=5,
                        include_memory=True,
                        unified=True,
                        session_id=session_id,
                    ),
                )

                # Build enhanced context from unified results
                knowledge_results = search_results.get("knowledge", [])
                memory_results = search_results.get("memory", [])

                if knowledge_results or memory_results or recent_docs:
                    # Add enhanced context to the conversation
                    enhanced_message = self._enhance_message_with_context(
                        user_message, recent_docs, knowledge_results, memory_results
                    )
                    self._messages[-1]["content"] = enhanced_message

                    # Log unified search success
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
                        level=observability.EventLevel.INFO,
                        data={
                            "agent_id": self.agent_id,
                            "knowledge_results_count": len(knowledge_results),
                            "memory_results_count": len(memory_results),
                            "recent_docs_count": len(recent_docs),
                            "query": user_message[:100],
                            "unified_search": True,
                        },
                        description=(
                            f"Context search completed for agent {self.agent_id}: "
                            f"{len(recent_docs)} recent docs, {len(knowledge_results)} knowledge, "
                            f"{len(memory_results)} memory results"
                        ),
                    )
            except Exception as e:
                # Log error but don't fail message processing
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PROCESSING_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                        "phase": "knowledge_search",
                    },
                    description=f"Knowledge search failed for agent {self.agent_id}: {str(e)}",
                )
        else:
            # No knowledge config, but still check for recent documents
            # Get recent docs again if we didn't already
            if not recent_docs and self.overlord and hasattr(self.overlord, "get_recent_documents"):
                recent_docs = self.overlord.get_recent_documents(session_id=session_id)

            if recent_docs:
                # Add enhanced context to the conversation
                enhanced_message = self._enhance_message_with_context(user_message, recent_docs)
                self._messages[-1]["content"] = enhanced_message

        # Check if we should include MCP tools
        tools: Optional[List[Dict[str, Any]]] = None
        if self.overlord and hasattr(self.overlord, "mcp_service"):
            try:
                mcp_service = self.overlord.mcp_service
                # Use agent-specific tool registry to get only tools this agent has access to
                available_tools = mcp_service.get_tool_registry(self.agent_id)

                # GBAC Phase 3: narrow the per-turn tool surface to the
                # requesting user's effective set (group tool-override
                # cascade). ``available_tools`` is the inherited view
                # (post-registry, post-attachment); the ``_shared`` registry
                # is the post-registry catalog that group allow-overrides
                # expand against — a group may supersede an attachment
                # override, but never resurrect registry-pruned tools.
                # (``mcp_service.tool_registry`` is last-write-wins across
                # per-agent re-registrations, so an attachment override
                # would narrow it; servers registered only per-agent are
                # absent from ``_shared`` and fall back to the inherited
                # view inside ``effective_tool_registry``.) No-op when the
                # formation has no groups/ directory. The filtered dict
                # feeds both the planning prompt and the LLM tool schema,
                # so a denied tool is never visible nor callable in this
                # turn.
                from ...services.gbac import enforcement as gbac_enforcement

                agent_registries = getattr(mcp_service, "agent_tool_registry", None) or {}
                # An empty _shared catalog means everything was filtered out
                # on purpose; only fall back when the key is absent entirely.
                _shared = agent_registries.get("_shared")
                available_tools = gbac_enforcement.effective_tool_registry(
                    self.agent_id,
                    available_tools,
                    catalogs=(
                        _shared
                        if _shared is not None
                        else getattr(mcp_service, "tool_registry", None)
                    ),
                )

                # Tool isolation now working with shared + agent-specific tools

                # Format tools for LLM if any are available
                if available_tools:
                    tools = []

                    for server_id, server_tools in available_tools.items():
                        for tool_name, tool_info in server_tools.items():
                            # Convert MCP tool format to OpenAI function format
                            tool_def = {
                                "type": "function",
                                "function": {
                                    "name": f"{server_id}__{tool_name}",  # Prefix with server_id
                                    "description": tool_info.get("description", ""),
                                    "parameters": tool_info.get(
                                        "inputSchema", {"type": "object", "properties": {}}
                                    ),
                                },
                            }
                            tools.append(tool_def)
                else:
                    tools = []

                # Built-in record_lesson tool (Memory Revamp Phase 2): lets the
                # agent persist a reusable rule of thumb when it hits a gotcha
                # worth remembering across sessions.
                captains_log_service = (
                    getattr(self.overlord, "captains_log", None) if self.overlord else None
                )
                if captains_log_service and captains_log_service.lessons_enabled:
                    record_lesson_tool = {
                        "type": "function",
                        "function": {
                            "name": "record_lesson",
                            "description": (
                                "Record a lesson learned: a reusable, prescriptive rule of "
                                "thumb discovered through experience (e.g. a library or "
                                "phrasing that works or fails). Use it when you hit a gotcha "
                                "worth remembering across sessions. NOT for facts about the "
                                "user or one-off events."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "rule": {
                                        "type": "string",
                                        "description": (
                                            "The prescriptive rule, phrased so it can be "
                                            "applied directly in future sessions."
                                        ),
                                    },
                                    "context": {
                                        "type": "string",
                                        "description": (
                                            "Optional clarifier for when the rule applies."
                                        ),
                                    },
                                },
                                "required": ["rule"],
                            },
                        },
                    }
                    tools.append(record_lesson_tool)

                # Built-in artifact retrieval tools (Artifact Memory Phase 2):
                # registered only when the overlord carries an enabled
                # artifact memory service. Formations without artifact
                # memory (no persistent memory, or artifacts.enabled: false)
                # see no artifact tools at all.
                from .artifact_dispatch import artifact_tools_available, build_artifact_tools

                if self.overlord and artifact_tools_available(self.overlord):
                    tools.extend(build_artifact_tools())

                # Always add the built-in generate_file tool if artifact service is available
                if self.overlord and hasattr(self.overlord, "artifact_service"):
                    generate_file_tool = {
                        "type": "function",
                        "function": {
                            "name": "generate_file",
                            "description": (
                                "Generate files by executing Python code in a sandboxed environment. "
                                "Available libraries: "
                                "matplotlib, seaborn, plotly (charts/visualizations), "
                                "reportlab, fpdf2 (PDF documents), "
                                "python-docx (Word .docx), "
                                "openpyxl, xlsxwriter (Excel .xlsx), "
                                "python-pptx (PowerPoint .pptx), "
                                "Pillow/PIL (images), "
                                "pandas, numpy, scipy (data processing), "
                                "requests (HTTP), "
                                "qrcode, python-barcode (barcodes), "
                                "lxml, markdown, csv, json (formats). "
                                "Save output files to the current directory. "
                                "Use matplotlib.use('Agg') for non-interactive plotting."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": (
                                            "Python code to execute. Must save output file(s) "
                                            "in current directory. Only use the libraries listed "
                                            "in the tool description."
                                        ),
                                    },
                                    "filename": {
                                        "type": "string",
                                        "description": "Optional filename hint for the generated file",
                                    },
                                },
                                "required": ["code"],
                            },
                        },
                    }
                    tools.append(generate_file_tool)

                # Add activate_skill tool if skill manager has skills for this agent
                if (
                    self.overlord
                    and hasattr(self.overlord, "skill_manager")
                    and self.overlord.skill_manager
                ):
                    request_id = getattr(self, "_current_request_id", None)
                    skill_tool = self.overlord.skill_manager.build_activate_skill_tool(
                        self.agent_id, request_id=request_id
                    )
                    if skill_tool:
                        tools.append(skill_tool)

                    # Add run_skill tool if RCE client is available and skills have scripts
                    if hasattr(self.overlord, "rce_client") and self.overlord.rce_client:
                        run_tool = self.overlord.skill_manager.build_run_skill_tool(
                            self.agent_id, request_id=request_id
                        )
                        if run_tool:
                            tools.append(run_tool)

            except Exception as e:
                # Log but don't fail if we can't get tools
                observability.observe(
                    event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                        "phase": "tool_discovery",
                    },
                    description=f"Failed to get MCP tools for agent {self.agent_id}: {str(e)}",
                )

        # Check if this is a workflow task using metadata
        # Workflow tasks should be marked in metadata to avoid fragile string matching
        is_workflow_task = False
        if hasattr(message_obj, "metadata") and message_obj.metadata:
            # Check for workflow task indicator in metadata
            is_workflow_task = (
                message_obj.metadata.get("is_workflow_task", False)
                or message_obj.metadata.get("task_type") == "workflow"
                or message_obj.metadata.get("source") == "workflow_executor"
            )

        # Fallback to string matching only if metadata not available (for backward compatibility)
        if not is_workflow_task and not (hasattr(message_obj, "metadata") and message_obj.metadata):
            is_workflow_task = (
                # Check for workflow context indicators
                ("## Task:" in user_message)  # Workflow task prompt format
                or ("Task Details:" in user_message)  # Another workflow indicator
                or ("Required Capabilities:" in user_message)  # Workflow metadata
                or ("THIS SPECIFIC TASK ONLY" in user_message)  # Workflow instruction
            )

        # Extract current request from enhanced message for planning
        # The enhanced message contains conversation context which confuses the planning LLM
        actual_user_request = self._extract_current_request_text(user_message)
        planning_user_request = self._extract_current_request_text(
            user_message, include_context_lines=True
        )

        # Delegated A2A tasks should still plan when they have tools available, but they
        # must not delegate again or they can loop between agents.
        bypass_planning = self._should_bypass_planning(is_a2a_task, tools)
        if bypass_planning:
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "phase": "planning_bypassed",
                    "reason": "a2a_task_detected",
                    "message_preview": (
                        user_message[:100] + "..." if len(user_message) > 100 else user_message
                    ),
                },
                description=f"Agent {self.agent_id} bypassing planning phase: a2a_task_detected",
            )

        # Variables to store planning results
        execution_plan = None
        my_results: Dict[str, Any] = {}
        planning_response_parts: List[str] = []  # Collect response parts during planning
        replan_attempted = False

        # Only plan for user messages that might need multiple steps (skip for A2A tasks only)
        if (
            self._messages
            and self._messages[-1]["role"] == "user"
            and tools
            and not bypass_planning
        ):
            try:
                # Use the extracted actual request for planning, not the full enhanced message
                execution_plan = await self._plan_before_execution(
                    planning_user_request,
                    tools,
                    allow_delegation=not is_a2a_task,
                )

                # Log the execution plan
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": self.agent_id,
                        "phase": "execution_plan_ready",
                        "has_my_steps": bool(execution_plan and execution_plan.get("my_steps")),
                        "has_delegate_steps": bool(
                            execution_plan and execution_plan.get("delegate_steps")
                        ),
                        "my_steps_count": (
                            len(execution_plan.get("my_steps", [])) if execution_plan else 0
                        ),
                        "delegate_steps_count": (
                            len(execution_plan.get("delegate_steps", [])) if execution_plan else 0
                        ),
                    },
                    description=f"Execution plan ready for {self.agent_id}",
                )

                # Reconcile my_steps with steps: the LLM sometimes produces
                # a steps array with correct tool chaining but a my_steps array
                # that skips prerequisite tools (e.g. omitting list-todo-task-lists
                # before list-todo-tasks). When steps exists and has more
                # can_i_do_this=true entries than my_steps, rebuild my_steps
                # from steps to preserve the correct ordering.
                if execution_plan and execution_plan.get("steps"):
                    canonical_steps = [
                        s for s in execution_plan["steps"] if s.get("can_i_do_this", True) is True
                    ]
                    my_steps = execution_plan.get("my_steps", [])
                    if len(canonical_steps) > len(my_steps):
                        rebuilt = []
                        for s in canonical_steps:
                            rebuilt.append(
                                {
                                    "action": s.get("action", ""),
                                    "tool_name": s.get("tool_name", ""),
                                    "parameters": s.get("parameters", {}),
                                    "output_placeholder": s.get(
                                        "output_placeholder",
                                        f"{{{s.get('tool_name', 'TOOL').upper()}_OUTPUT}}",
                                    ),
                                }
                            )
                        execution_plan["my_steps"] = rebuilt
                        observability.observe(
                            event_type=observability.ConversationEvents.AGENT_PLANNING,
                            level=observability.EventLevel.WARNING,
                            data={
                                "agent_id": self.agent_id,
                                "original_my_steps": len(my_steps),
                                "canonical_steps": len(canonical_steps),
                                "rebuilt_tools": [s.get("tool_name") for s in rebuilt],
                            },
                            description=(
                                "Rebuilt my_steps from steps array "
                                "to preserve tool chain ordering"
                            ),
                        )

                # EXECUTION PHASE: Execute my_steps first
                if execution_plan and execution_plan.get("my_steps"):
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_PLANNING,
                        level=observability.EventLevel.DEBUG,
                        data={
                            "agent_id": self.agent_id,
                            "my_steps_count": len(execution_plan.get("my_steps", [])),
                            "phase": "my_steps_execution_start",
                        },
                        description=f"Starting execution of {len(execution_plan.get('my_steps', []))} my_steps",
                    )
                    step_index = 0
                    while step_index < len(execution_plan.get("my_steps", [])):
                        step = execution_plan.get("my_steps", [])[step_index]
                        placeholder = step.get(
                            "output_placeholder",
                            f"{{{step.get('tool_name', 'TOOL').upper()}_OUTPUT}}",
                        )

                        if placeholder in my_results and not self._is_tool_execution_error(
                            my_results[placeholder]
                        ):
                            step_index += 1
                            continue

                        observability.observe(
                            event_type=observability.ConversationEvents.AGENT_PLANNING,
                            level=observability.EventLevel.DEBUG,
                            data={
                                "agent_id": self.agent_id,
                                "step": step,
                                "phase": "processing_step",
                            },
                            description=f"Processing step: {step.get('action', 'unknown')}",
                        )
                        try:
                            # Execute the tool
                            tool_name = step.get("tool_name")
                            if tool_name:
                                # Find the tool in available tools
                                selected_tool_def: Optional[Dict[str, Any]] = next(
                                    (
                                        t
                                        for t in tools
                                        if t.get("function", {}).get("name") == tool_name
                                    ),
                                    None,
                                )

                                if selected_tool_def:
                                    # Extract server_id and actual tool name if present
                                    if "__" in tool_name:
                                        server_id, actual_tool_name = tool_name.split("__", 1)
                                    else:
                                        server_id = None
                                        actual_tool_name = tool_name

                                    # Extract parameters from step configuration or use LLM to generate them
                                    parameters = dict(step.get("parameters", {}) or {})
                                    tool_schema_raw = selected_tool_def.get("function", {})
                                    if not isinstance(tool_schema_raw, dict):
                                        step_index += 1
                                        continue
                                    tool_schema: Dict[str, Any] = tool_schema_raw
                                    full_param_schema_raw = tool_schema.get("parameters", {})
                                    if not isinstance(full_param_schema_raw, dict):
                                        step_index += 1
                                        continue
                                    full_param_schema: Dict[str, Any] = full_param_schema_raw
                                    required_params = full_param_schema.get("required", [])
                                    param_properties = full_param_schema.get("properties", {})
                                    server_default_param_names: set[str] = set()
                                    if server_id and self._mcp_service:
                                        server_default_param_names = (
                                            self._get_mcp_default_param_names(server_id)
                                        )

                                    if required_params:
                                        active_skill_context = (
                                            self._get_active_skill_execution_context()
                                        )
                                        parameters = self._substitute_step_parameter_placeholders(
                                            parameters=parameters,
                                            param_properties=param_properties,
                                            full_schema=full_param_schema,
                                            action_description=step.get("action", ""),
                                            my_results=my_results,
                                            tool_name=tool_name,
                                        )

                                        context_parameters = self._resolve_parameters_from_context(
                                            required_params=required_params,
                                            param_properties=param_properties,
                                            full_schema=full_param_schema,
                                            tool_name=tool_name,
                                            action_description=step.get("action", ""),
                                            user_request=planning_user_request,
                                            my_results=my_results,
                                            runtime_context=active_skill_context,
                                        )
                                        if context_parameters:
                                            parameters = self._merge_parameter_candidates(
                                                current_parameters=parameters,
                                                candidate_parameters=context_parameters,
                                                param_properties=param_properties,
                                                full_schema=full_param_schema,
                                            )
                                            observability.observe(
                                                event_type=observability.ConversationEvents.AGENT_PLANNING,
                                                level=observability.EventLevel.DEBUG,
                                                data={
                                                    "agent_id": self.agent_id,
                                                    "tool_name": tool_name,
                                                    "context_params": context_parameters,
                                                },
                                                description=(
                                                    f"Resolved parameters from request/results for "
                                                    f"{tool_name}"
                                                ),
                                            )

                                        # Inject MCP server default parameters
                                        if server_id and self._mcp_service:
                                            mcp_defaults = self._mcp_service.server_configs.get(
                                                server_id, {}
                                            ).get("parameters", {})
                                            if mcp_defaults:
                                                parameters = self._merge_parameter_candidates(
                                                    current_parameters=parameters,
                                                    candidate_parameters=mcp_defaults,
                                                    param_properties=param_properties,
                                                    full_schema=full_param_schema,
                                                )

                                        unresolved_required_params = self._filter_unresolved_params_backed_by_server_defaults(
                                            self._get_unresolved_required_parameters(
                                                parameters,
                                                required_params,
                                                param_properties,
                                                full_param_schema,
                                            ),
                                            server_default_param_names,
                                        )

                                        if unresolved_required_params:
                                            inference_context = (
                                                self._build_parameter_inference_context(
                                                    user_request=planning_user_request,
                                                    action_description=step.get("action", ""),
                                                    my_results=my_results,
                                                    required_params=required_params,
                                                )
                                            )

                                            inferred_parameters = await self._infer_tool_parameters(
                                                tool_name=actual_tool_name,
                                                required_params=required_params,
                                                param_properties=param_properties,
                                                full_schema=full_param_schema,
                                                action_description=step.get("action", ""),
                                                user_request=inference_context,
                                            )

                                            if inferred_parameters:
                                                inferred_parameters = self._validate_inferred_parameters_against_results(
                                                    inferred_parameters=inferred_parameters,
                                                    my_results=my_results,
                                                    param_properties=param_properties,
                                                    full_schema=full_param_schema,
                                                    tool_name=tool_name,
                                                    action_description=step.get("action", ""),
                                                )

                                            if inferred_parameters:
                                                parameters = self._merge_parameter_candidates(
                                                    current_parameters=parameters,
                                                    candidate_parameters=inferred_parameters,
                                                    param_properties=param_properties,
                                                    full_schema=full_param_schema,
                                                )
                                                observability.observe(
                                                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                                                    level=observability.EventLevel.DEBUG,
                                                    data={
                                                        "agent_id": self.agent_id,
                                                        "tool_name": tool_name,
                                                        "inferred_params": inferred_parameters,
                                                    },
                                                    description=f"Inferred parameters for {tool_name}",
                                                )

                                            unresolved_required_params = self._filter_unresolved_params_backed_by_server_defaults(
                                                self._get_unresolved_required_parameters(
                                                    parameters,
                                                    required_params,
                                                    param_properties,
                                                    full_param_schema,
                                                ),
                                                server_default_param_names,
                                            )
                                    else:
                                        unresolved_required_params = []

                                    if unresolved_required_params:
                                        unresolved_placeholder_params = [
                                            param_name
                                            for param_name in unresolved_required_params
                                            if self._is_placeholder_like_value(
                                                parameters.get(param_name)
                                            )
                                        ]
                                        repaired_plan = None
                                        if not replan_attempted:
                                            replan_attempted = True
                                            repaired_plan = await self._repair_execution_plan_for_missing_parameters(
                                                user_message=planning_user_request,
                                                available_tools=tools,
                                                allow_delegation=not is_a2a_task,
                                                failed_step=step,
                                                tool_name=tool_name,
                                                unresolved_params=unresolved_required_params,
                                                current_plan=execution_plan,
                                                my_results=my_results,
                                            )

                                        if repaired_plan:
                                            execution_plan = repaired_plan
                                            step_index = 0
                                            continue

                                        unresolved_params = ", ".join(unresolved_required_params)
                                        my_results[placeholder] = {
                                            "status": "error",
                                            "error": (
                                                "Could not infer required parameters for "
                                                f"{tool_name}: {unresolved_params}. "
                                                "A discovery or lookup step may be required first."
                                            ),
                                            "tool_name": tool_name,
                                            "step_action": step.get("action", ""),
                                            "required_params": unresolved_required_params,
                                        }
                                        observability.observe(
                                            event_type=observability.ConversationEvents.AGENT_PLANNING,
                                            level=observability.EventLevel.WARNING,
                                            data={
                                                "agent_id": self.agent_id,
                                                "tool_name": tool_name,
                                                "required_params": unresolved_required_params,
                                                "reason": "cannot_infer_parameters",
                                                "unresolved_placeholder_params": (
                                                    unresolved_placeholder_params
                                                ),
                                                "active_skill_context_keys": sorted(
                                                    active_skill_context.keys()
                                                ),
                                                "successful_result_count": len(
                                                    self._get_successful_planning_results(
                                                        my_results
                                                    )
                                                ),
                                            },
                                            description=(
                                                f"Skipping planned step {tool_name} - "
                                                "cannot infer required parameters"
                                            ),
                                        )
                                        step_index += 1
                                        continue

                                    (
                                        unresolved_nonrequired_placeholder_params,
                                        unresolved_nonrequired_placeholder_leaves,
                                    ) = self._get_unresolved_nonrequired_placeholder_parameters(
                                        parameters=parameters,
                                        required_params=required_params,
                                    )

                                    if unresolved_nonrequired_placeholder_params:
                                        observability.observe(
                                            event_type=observability.ConversationEvents.AGENT_PLANNING,
                                            level=observability.EventLevel.WARNING,
                                            data={
                                                "agent_id": self.agent_id,
                                                "tool_name": tool_name,
                                                "phase": "placeholder.unresolved",
                                                "blocked_params": (
                                                    unresolved_nonrequired_placeholder_params
                                                ),
                                                "dropped_params": [],
                                                "unresolved": (
                                                    unresolved_nonrequired_placeholder_leaves
                                                ),
                                            },
                                            description=(
                                                f"{len(unresolved_nonrequired_placeholder_leaves)} "
                                                f"unresolved placeholder leaf(s) for "
                                                f"{tool_name or '(unknown)'}: "
                                                f"{', '.join(leaf['param_path'] for leaf in unresolved_nonrequired_placeholder_leaves)}; "
                                                "blocked execution for non-required "
                                                f"planner-authored param(s): "
                                                f"{', '.join(unresolved_nonrequired_placeholder_params)}"
                                            ),
                                        )

                                        repaired_plan = None
                                        if not replan_attempted:
                                            replan_attempted = True
                                            repaired_plan = await self._repair_execution_plan_for_missing_parameters(
                                                user_message=planning_user_request,
                                                available_tools=tools,
                                                allow_delegation=not is_a2a_task,
                                                failed_step=step,
                                                tool_name=tool_name,
                                                unresolved_params=(
                                                    unresolved_nonrequired_placeholder_params
                                                ),
                                                current_plan=execution_plan,
                                                my_results=my_results,
                                            )

                                        if repaired_plan:
                                            execution_plan = repaired_plan
                                            step_index = 0
                                            continue

                                        my_results[placeholder] = {
                                            "status": "error",
                                            "error": (
                                                "Could not resolve planner-authored placeholder "
                                                f"parameters for {tool_name}: "
                                                f"{', '.join(unresolved_nonrequired_placeholder_params)}. "
                                                "A prerequisite lookup/discovery step is required "
                                                "before this action."
                                            ),
                                            "tool_name": tool_name,
                                            "step_action": step.get("action", ""),
                                            "blocked_params": (
                                                unresolved_nonrequired_placeholder_params
                                            ),
                                        }
                                        observability.observe(
                                            event_type=observability.ConversationEvents.AGENT_PLANNING,
                                            level=observability.EventLevel.WARNING,
                                            data={
                                                "agent_id": self.agent_id,
                                                "tool_name": tool_name,
                                                "blocked_params": (
                                                    unresolved_nonrequired_placeholder_params
                                                ),
                                                "reason": "unresolved_placeholder_dependencies",
                                                "unresolved": (
                                                    unresolved_nonrequired_placeholder_leaves
                                                ),
                                            },
                                            description=(
                                                f"Blocking planned step {tool_name} - unresolved "
                                                "planner placeholders remain in non-required "
                                                "parameters"
                                            ),
                                        )
                                        step_index += 1
                                        continue

                                    # Final safety net: strip any placeholder-shaped values
                                    # that survived substitution / context / inference.
                                    # This prevents literal ``{{...}}`` strings from
                                    # reaching MCP when a non-required parameter was never
                                    # resolved (see Calendar BUG-1 in v0.20260416.2 report).
                                    parameters = self._strip_leftover_placeholder_parameters(
                                        parameters=parameters,
                                        required_params=required_params,
                                        tool_name=tool_name,
                                    )

                                    unknown_params = self._get_unknown_tool_parameters(
                                        parameters=parameters,
                                        tool_schema=tool_schema,
                                    )

                                    # Validate parameters against tool schema before execution
                                    is_valid, validation_error = self._validate_tool_parameters(
                                        parameters=parameters,
                                        tool_schema=tool_schema,
                                        tool_name=tool_name,
                                        server_default_param_names=server_default_param_names,
                                    )

                                    if not is_valid:
                                        observability.observe(
                                            event_type=observability.ErrorEvents.VALIDATION_FAILED,
                                            level=observability.EventLevel.ERROR,
                                            data={
                                                "agent_id": self.agent_id,
                                                "tool_name": tool_name,
                                                "parameters": parameters,
                                                "validation_error": validation_error,
                                                "step_action": step.get("action", ""),
                                            },
                                            description=(
                                                f"Parameter validation failed for {tool_name}: "
                                                f"{validation_error}"
                                            ),
                                        )

                                        repaired_plan = None
                                        if not replan_attempted:
                                            replan_attempted = True
                                            repaired_plan = await self._repair_execution_plan_for_validation_failure(
                                                user_message=planning_user_request,
                                                available_tools=tools,
                                                allow_delegation=not is_a2a_task,
                                                failed_step=step,
                                                tool_name=tool_name,
                                                validation_error=validation_error or "",
                                                blocked_params=unknown_params,
                                                current_plan=execution_plan,
                                                my_results=my_results,
                                            )

                                        if repaired_plan:
                                            execution_plan = repaired_plan
                                            step_index = 0
                                            continue

                                        # Store error result instead of executing
                                        my_results[placeholder] = {
                                            "status": "error",
                                            "error": f"Parameter validation failed: {validation_error}",
                                            "tool_name": tool_name,
                                            "step_action": step.get("action", ""),
                                            "blocked_params": unknown_params,
                                            "validation_error": validation_error,
                                        }
                                        step_index += 1
                                        continue

                                    # Check for cancellation before tool execution
                                    await self._check_cancellation(request_id)

                                    step_desc = step.get("action", f"Using {tool_name}")
                                    streaming.stream(
                                        "progress",
                                        step_desc,
                                        stage="plan_step",
                                        tool_name=tool_name,
                                        agent_name=self.agent_id,
                                        skip_rephrase=True,
                                    )

                                    # Execute the tool with validated parameters
                                    tool_result = await self.invoke_tool(
                                        tool_name=actual_tool_name,
                                        parameters=parameters,
                                        server_id=server_id,
                                        user_id=user_id,
                                    )

                                    # Store result with placeholder key
                                    my_results[placeholder] = tool_result

                                    if self._is_tool_execution_error(tool_result):
                                        observability.observe(
                                            event_type=observability.ErrorEvents.TOOL_CALL_ERROR,
                                            level=observability.EventLevel.WARNING,
                                            data={
                                                "agent_id": self.agent_id,
                                                "tool_name": tool_name,
                                                "step": step.get("action"),
                                                "phase": "planning_execution",
                                                "result": tool_result,
                                            },
                                            description=(
                                                "Planned step returned a tool error and was "
                                                "not treated as a successful execution"
                                            ),
                                        )
                                        step_index += 1
                                        continue

                                    # Log successful execution
                                    observability.observe(
                                        event_type=observability.ConversationEvents.MCP_TOOL_CALL_COMPLETED,
                                        level=observability.EventLevel.INFO,
                                        data={
                                            "agent_id": self.agent_id,
                                            "tool_name": tool_name,
                                            "step_action": step.get("action"),
                                            "phase": "planning_execution",
                                            "success": True,
                                        },
                                        description=f"Executed planned step: {step.get('action')}",
                                    )
                        except Exception as e:
                            # Re-raise credential errors to trigger clarification flow
                            from ...services.mcp.service import CredentialSelectionNeededError
                            from ..credentials import (
                                AmbiguousCredentialError,
                                MissingCredentialError,
                            )

                            if isinstance(
                                e,
                                (
                                    AmbiguousCredentialError,
                                    MissingCredentialError,
                                    CredentialSelectionNeededError,
                                ),
                            ):
                                # These need to bubble up to overlord for clarification
                                raise

                            # Store error result for placeholder replacement
                            error_result = {
                                "status": "error",
                                "error": str(e),
                                "step_action": step.get("action", ""),
                                "tool_name": tool_name,
                            }
                            my_results[placeholder] = error_result

                            observability.observe(
                                event_type=observability.ErrorEvents.TOOL_CALL_ERROR,
                                level=observability.EventLevel.WARNING,
                                data={
                                    "agent_id": self.agent_id,
                                    "error": str(e),
                                    "step": step.get("action"),
                                    "phase": "planning_execution",
                                },
                                description=f"Failed to execute planned step: {str(e)}",
                            )
                        step_index += 1

                # DELEGATION PHASE: Handle delegate_steps
                if execution_plan and execution_plan.get("delegate_steps"):
                    # We have steps to delegate - process them after my_steps
                    for delegate_step in execution_plan.get("delegate_steps", []):
                        # Get delegation prompt with placeholders replaced and
                        # prior successful tool results appended as compact context.
                        delegation_prompt = self._build_delegation_prompt_with_results(
                            delegate_step.get("delegation_prompt", user_message),
                            my_results,
                            context_hint=f"{user_message}\n{delegate_step.get('action', '')}",
                        )

                        # Request A2A assistance with enriched prompt
                        a2a_response = await self._request_a2a_assistance(
                            delegation_prompt,
                            needed_capability=delegate_step.get(
                                "capability_needed", "Unknown capability"
                            ),
                        )

                        if a2a_response:
                            # Collect A2A response
                            planning_response_parts.append(a2a_response)
                        else:
                            # A2A request failed (likely timeout or unavailable)
                            if (
                                not my_results
                                and len(execution_plan.get("delegate_steps", [])) == 1
                            ):
                                planning_response_parts.append(
                                    "I wasn't able to complete this request. "
                                    "The required service is currently unavailable. "
                                    "Please try again shortly."
                                )

                # Check if this is a simple direct response (no steps needed)
                if (
                    execution_plan
                    and not execution_plan.get("my_steps")
                    and not execution_plan.get("delegate_steps")
                ):
                    # Empty plan - handle simple requests directly
                    data_flow = execution_plan.get("data_flow", "")
                    if (
                        "direct response" in data_flow.lower()
                        or "no tools needed" in data_flow.lower()
                        or "file processing already complete" in data_flow.lower()
                    ):
                        # Generate a direct response for simple conversational requests.
                        #
                        # When the orchestrator has surfaced file-processing
                        # results (transcriptions, OCR, document text, etc.)
                        # in the enhanced prompt, the empty-plan path MUST
                        # see them — otherwise the model has no idea the
                        # user's attachment was already processed and will
                        # respond as if the attachment is missing.
                        # ``actual_user_request`` is the stripped-down form
                        # used for planning; it intentionally drops the
                        # ``=== FILE PROCESSING RESULTS ===`` section.
                        # Fall back to the full ``user_message`` only when
                        # file processing results are present so we don't
                        # inadvertently change response behavior for plain
                        # conversational requests that have user profile or
                        # memory context but no attachments. We also swap
                        # the system prompt so the LLM is told the file
                        # content has already been processed and is
                        # included below — otherwise the default system
                        # prompt's "without using any tools or files"
                        # instruction contradicts the user-message content
                        # and the LLM flakily asks the user to re-upload.
                        has_file_results = (
                            isinstance(user_message, str)
                            and "=== FILE PROCESSING RESULTS" in user_message
                        )
                        if has_file_results:
                            user_for_response = user_message
                            file_results_clause = (
                                "The user's attached file(s) have already been "
                                "processed by the runtime; the results are included "
                                "in the user message under the "
                                "`=== FILE PROCESSING RESULTS ===` section. Treat "
                                "those results as the authoritative content of the "
                                "user's attachment(s) and use them to answer the "
                                "request directly. Do not ask the user to re-upload "
                                "or re-share the file."
                            )
                            if self.system_message:
                                system_content = f"{self.system_message}\n\n{file_results_clause}"
                            else:
                                system_content = (
                                    f"You are a helpful assistant. {file_results_clause}"
                                )
                        else:
                            user_for_response = actual_user_request
                            system_content = (
                                self.system_message
                                if self.system_message
                                else (
                                    "You are a helpful assistant. Provide direct, natural responses without using any tools or files."
                                )
                            )

                        # When the orchestrator handed us a clean
                        # role-turn bundle, ``self._messages`` already
                        # contains the proper chat-API-shape transcript
                        # (system-with-addendum + buffer history +
                        # current user). Sending only ``[system, user]``
                        # here would strip the prior turns and cause
                        # honesty-trained models (e.g. Sonnet 4.6) to
                        # claim missing context on simple follow-ups.
                        # Fall back to the legacy two-message pair only
                        # when no bundle is present (e.g. SDK callers
                        # that haven't migrated, or non-chat entrypoints).
                        if clean_chat_context is not None:
                            simple_messages = list(self._messages)
                        else:
                            simple_messages = [
                                {"role": "system", "content": system_content},
                                {"role": "user", "content": user_for_response},
                            ]

                        response_obj = await self._call_active_model(
                            active_model, "chat", simple_messages
                        )
                        response_text = (
                            response_obj.content
                            if hasattr(response_obj, "content")
                            else str(response_obj)
                        )

                        response = MuxiResponse(role="assistant", content=response_text.strip())

                        observability.observe(
                            event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
                            level=observability.EventLevel.INFO,
                            data={
                                "agent_id": self.agent_id,
                                "response_type": "direct_simple_response",
                                "plan_type": "empty_plan",
                            },
                            description=f"Agent {self.agent_id} provided direct response for simple request",
                        )

                        self._messages.append(
                            {
                                "role": "assistant",
                                "content": self._content_to_text(response.content),
                            }
                        )
                        return response

                # If we handled everything through planning, skip the regular flow
                if execution_plan and (
                    execution_plan.get("my_steps") or execution_plan.get("delegate_steps")
                ):
                    # Compile response from planning execution
                    response_content = ""

                    # Check if we have any delegation responses (successful or not)
                    has_delegation_responses = bool(planning_response_parts)

                    # Check if delegation responses contain actual results (not just error messages)
                    has_successful_delegation = any(
                        part
                        for part in planning_response_parts
                        if part
                        and "delay in receiving" not in part
                        and "task may still be processing" not in part
                    )

                    # If we have successful delegation responses, prioritize those
                    synthesized_planning_response = None
                    if my_results and not has_successful_delegation:
                        # Skip-synthesis fast path: when every result is an
                        # artifact AND the user is already receiving streaming
                        # progress, the extra ~5s LLM synthesis call only
                        # adds boilerplate prose ("Here's your file:"). Use a
                        # deterministic acknowledgment instead. Saves 3-10s
                        # on artifact-heavy requests.
                        if (
                            self._is_pure_artifact_result(my_results)
                            and self._is_streaming_active()
                        ):
                            synthesized_planning_response = self._build_artifact_only_response(
                                my_results
                            )
                            observability.observe(
                                event_type=observability.ConversationEvents.AGENT_PLANNING,
                                level=observability.EventLevel.INFO,
                                data={
                                    "agent_id": self.agent_id,
                                    "phase": "synthesis_skipped",
                                    "reason": "pure_artifact_with_streaming",
                                    "artifact_count": len(my_results),
                                },
                                description=(
                                    f"Agent {self.agent_id} skipped planning synthesis "
                                    f"({len(my_results)} pure-artifact results, "
                                    f"streaming active)"
                                ),
                            )
                        else:
                            try:
                                synthesized_planning_response = (
                                    await self._synthesize_planning_execution_response(
                                        actual_user_request,
                                        my_results,
                                        planning_response_parts,
                                    )
                                )
                            except Exception as e:
                                observability.observe(
                                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                                    level=observability.EventLevel.WARNING,
                                    data={
                                        "agent_id": self.agent_id,
                                        "error": str(e),
                                        "phase": "planning_response_synthesis",
                                    },
                                    description=(
                                        "Planning response synthesis failed; "
                                        "using raw planning results"
                                    ),
                                )

                    if synthesized_planning_response:
                        response_content = synthesized_planning_response
                    # If we have successful delegation responses, prioritize those
                    elif has_successful_delegation:
                        response_content = "\n\n".join(planning_response_parts)

                        # Include local tool execution results only if we have any successful local executions
                        # my_results contains tool outputs from local (non-delegated) tool executions
                        if my_results:
                            response_content += "\n\n---\n\nAdditional information gathered:\n"
                            for placeholder, result in my_results.items():
                                if isinstance(result, dict):
                                    raw_result_text = result.get(
                                        "result", result.get("output", str(result))
                                    )
                                    result_text = (
                                        raw_result_text
                                        if isinstance(raw_result_text, str)
                                        else str(raw_result_text)
                                    )
                                else:
                                    result_text = str(result)
                                response_content += f"{result_text}\n\n"
                    else:
                        # No successful delegations, show local results first
                        if my_results:
                            for placeholder, result in my_results.items():
                                if isinstance(result, dict):
                                    raw_result_text = result.get(
                                        "result", result.get("output", str(result))
                                    )
                                    result_text = (
                                        raw_result_text
                                        if isinstance(raw_result_text, str)
                                        else str(raw_result_text)
                                    )
                                else:
                                    result_text = str(result)
                                response_content += f"{result_text}\n\n"

                        # Add any delegation messages (errors/timeouts)
                        if planning_response_parts:
                            response_content += "\n\n".join(planning_response_parts)

                    # Create response message
                    response = MuxiResponse(
                        role="assistant",
                        content=response_content.strip() or "I've completed the requested tasks.",
                    )

                    # Extract artifacts from my_results if any tools generated files
                    if my_results:
                        # Convert my_results to ToolExecutionResult format for extraction
                        from ...datatypes.clarification import ToolExecutionResult

                        tool_execution_results = []
                        for placeholder, result in my_results.items():
                            # Check if this result contains a generate_file artifact
                            if isinstance(result, dict) and "_artifact" in result:
                                # This is a generate_file result with an artifact
                                tool_exec_result = ToolExecutionResult(
                                    tool_name="generate_file",
                                    parameters={},  # Parameters not needed for extraction
                                    result=result,
                                    execution_time=0.0,
                                    success=True,
                                )
                                tool_execution_results.append(tool_exec_result)

                        # Extract artifacts if we have any tool results with artifacts
                        if tool_execution_results:
                            try:
                                artifacts = await extract_artifacts_from_tool_results(
                                    tool_execution_results
                                )
                                if artifacts:
                                    response.artifacts = artifacts
                                    observability.observe(
                                        event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
                                        level=observability.EventLevel.INFO,
                                        data={
                                            "agent_id": self.agent_id,
                                            "artifacts_count": len(artifacts),
                                            "artifact_files": [a.filename for a in artifacts],
                                            "phase": "planning_execution",
                                        },
                                        description=f"Agent {self.agent_id} extracted {len(artifacts)} artifacts from planning execution",  # noqa: E501
                                    )
                            except Exception as e:
                                observability.observe(
                                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                                    level=observability.EventLevel.WARNING,
                                    data={
                                        "agent_id": self.agent_id,
                                        "error": str(e),
                                        "phase": "planning_execution",
                                    },
                                    description=f"Failed to extract artifacts in planning: {e}",
                                )

                    # Add response to conversation context
                    self._messages.append(
                        {
                            "role": "assistant",
                            "content": self._content_to_text(response.content),
                        }
                    )

                    # Log completion
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_PLANNING,
                        level=observability.EventLevel.INFO,
                        data={
                            "agent_id": self.agent_id,
                            "phase": "planning_completed",
                            "my_steps_executed": len(my_results),
                            "delegations_made": len(
                                [
                                    s
                                    for s in execution_plan.get("delegate_steps", [])
                                    if "delegation_prompt" in s
                                ]
                            ),
                        },
                        description="Planning-based execution completed",
                    )
                    return response

            except Exception as e:
                # Re-raise credential errors to trigger clarification flow
                from ...services.mcp.service import CredentialSelectionNeededError
                from ..credentials import AmbiguousCredentialError, MissingCredentialError

                if isinstance(
                    e,
                    (
                        AmbiguousCredentialError,
                        MissingCredentialError,
                        CredentialSelectionNeededError,
                    ),
                ):
                    # These need to bubble up to overlord for clarification
                    raise

                # If planning fails, continue with normal flow
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                        "phase": "planning_phase",
                    },
                    description=f"Planning phase failed, continuing with normal flow: {str(e)}",
                )

        # Process the message with the model, including tools if available
        raw_response: Any
        if tools:
            try:
                # Get MCP configuration for message enhancement
                mcp_config = {}
                if self.overlord and hasattr(self.overlord, "_config") and self.overlord._config:
                    mcp_config = self.overlord._config.get("mcp", {})

                # Check if message enhancement is enabled
                enhance_prompts = mcp_config.get("enhance_user_prompts", True)

                # Enhance the last user message for better tool selection
                if enhance_prompts and self._messages and self._messages[-1]["role"] == "user":
                    original_message = self._messages[-1]["content"]

                    # Extract tool names for context
                    tool_names = [tool["function"]["name"] for tool in tools]
                    server_names = list(
                        set([name.split("__")[0] for name in tool_names if "__" in name])
                    )

                    # Use LLM to enhance the message for better tool selection
                    enhancement_prompt = (
                        f'The user said: "{original_message}"'
                        f"\n\nAvailable tool servers: {', '.join(server_names)}"
                        f"\nAvailable tools: {', '.join(tool_names[:10])}{'...' if len(tool_names) > 10 else ''}"
                        f"\nPlease rewrite the user's message to be more explicit and clear for tool selection, without changing the intent or meaning. "  # noqa: E501
                        'If the message mentions generic terms like "my repositories" or "my account", make it explicit that it refers to the user\'s account in the relevant service (e.g., GitHub).'  # noqa: E501
                        "\n\nIMPORTANT: Preserve any specific account names mentioned (e.g., 'lily account', 'john's account', etc). These are crucial for credential selection."  # noqa: E501
                        "\n\nImportant: Only return the enhanced message, nothing else. Do not explain or add any other text."  # noqa: E501
                    )

                    try:
                        # Create a simple message list for enhancement
                        enhancement_messages = [
                            {
                                "role": "system",
                                "content": "You are a helpful assistant that enhances user messages for clarity.",
                            },  # noqa: E501
                            {"role": "user", "content": enhancement_prompt},
                        ]

                        # Get enhanced message from LLM
                        enhancement_response = await self.model.chat(enhancement_messages)

                        if (
                            enhancement_response
                            and isinstance(enhancement_response, str)
                            and enhancement_response.strip()
                        ):  # noqa: E501
                            enhanced_message = enhancement_response.strip()

                            # Only use enhancement if it's reasonable (not too long, not empty)
                            if 10 < len(enhanced_message) < len(original_message) * 3:

                                # Update the message
                                self._messages[-1]["content"] = enhanced_message

                                # Store original for potential rollback
                                self._messages[-1]["_original_content"] = original_message
                    except Exception:
                        # If enhancement fails, just use original message
                        # Message enhancement failed, continue with original message
                        pass

                # Check for cancellation before LLM call
                await self._check_cancellation(request_id)

                # Log tool names available to the agent for this call (aids debugging hallucinated tool names)
                if tools:
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
                        level=observability.EventLevel.DEBUG,
                        data={
                            "agent_id": self.agent_id,
                            "tool_count": len(tools),
                            "tool_names": [t.get("function", {}).get("name") for t in tools],
                        },
                        description=f"Agent {self.agent_id} calling LLM with {len(tools)} tools",
                    )

                # Workflow tasks run with an isolated context: system message + task prompt only.
                # Using the full conversation history causes the model to simulate prior tool
                # call patterns (generating XML pseudo-calls) instead of invoking registered tools.
                if is_workflow_task:
                    system_msgs = [m for m in self._messages if m.get("role") == "system"]
                    last_user = next(
                        (m for m in reversed(self._messages) if m.get("role") == "user"), None
                    )
                    llm_messages = system_msgs + ([last_user] if last_user else [])
                else:
                    llm_messages = self._messages

                raw_response = await self._call_active_model(
                    active_model,
                    "chat_with_tools",
                    cast(List[Dict[str, str]], llm_messages),
                    tools=tools,
                )
            except Exception as e:
                # Log error and fallback to no tools
                observability.observe(
                    event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                        "phase": "llm_call_with_tools",
                    },
                    description=f"Failed to call LLM with tools for agent {self.agent_id}: {str(e)}",
                )
                # Check for cancellation before fallback LLM call
                await self._check_cancellation(request_id)
                # Fallback to no tools
                raw_response = await self.model.chat(cast(List[Dict[str, str]], self._messages))
        else:
            # No tools available - try A2A for non-workflow tasks
            if not is_workflow_task and self._a2a_attempt_count < self._max_a2a_attempts:
                # Increment attempt counter before making the call
                self._a2a_attempt_count += 1

                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_A2A,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "agent_id": self.agent_id,
                        "attempt_count": self._a2a_attempt_count,
                        "max_attempts": self._max_a2a_attempts,
                    },
                    description=(
                        f"Agent {self.agent_id} attempting A2A (attempt "
                        f"{self._a2a_attempt_count}/{self._max_a2a_attempts})"
                    ),
                )

                a2a_response = await self._request_a2a_assistance(user_message)

                if a2a_response:
                    # Use the A2A response as the agent's response
                    raw_response = a2a_response
                else:
                    # Check for cancellation before LLM call
                    await self._check_cancellation(request_id)
                    # Normal chat without tools
                    raw_response = await self._call_active_model(
                        active_model, "chat", cast(List[Dict[str, str]], self._messages)
                    )
            else:
                # Either workflow task or A2A attempts exhausted - respond normally
                if not is_workflow_task and self._a2a_attempt_count >= self._max_a2a_attempts:
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_A2A,
                        level=observability.EventLevel.WARNING,
                        data={
                            "agent_id": self.agent_id,
                            "attempt_count": self._a2a_attempt_count,
                            "reason": "max_attempts_reached",
                        },
                        description=f"Agent {self.agent_id} reached max A2A attempts limit",
                    )
                # Check for cancellation before LLM call
                await self._check_cancellation(request_id)
                raw_response = await self._call_active_model(
                    active_model, "chat", cast(List[Dict[str, str]], self._messages)
                )

        # Extract the actual content string from the response
        if isinstance(raw_response, str):
            content = raw_response
        elif hasattr(raw_response, "choices") and raw_response.choices:
            # Handle ChatCompletionResponse object
            message = raw_response.choices[0].message
            if isinstance(message, dict):
                content = message.get("content", "") or ""  # Handle None content
            else:
                # Handle message as object with content attribute/property
                content = getattr(message, "content", "") or ""  # Handle None content
        elif isinstance(raw_response, dict) and "choices" in raw_response:
            # Handle dict response format
            content = raw_response["choices"][0]["message"].get("content", "") or ""
        elif isinstance(raw_response, dict):
            # Handle dictionary tool result - extract meaningful content
            import json as json_lib

            # Try to extract meaningful text from the dict structure
            if "content" in raw_response:
                content_data = raw_response["content"]
                if isinstance(content_data, dict) and "content" in content_data:
                    # Handle nested content.content structure
                    nested_content = content_data["content"]
                    if isinstance(nested_content, list):
                        # Extract text from content items
                        text_parts = []
                        for item in nested_content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                        content = (
                            "\n".join(text_parts)
                            if text_parts
                            else json_lib.dumps(raw_response, indent=2)
                        )
                    else:
                        content = str(nested_content)
                else:
                    content = str(content_data)
            elif "result" in raw_response:
                content = str(raw_response["result"])
            elif "output" in raw_response:
                content = str(raw_response["output"])
            elif "text" in raw_response:
                content = str(raw_response["text"])
            else:
                # Format as readable JSON
                content = json_lib.dumps(raw_response, indent=2)
        else:
            # Try to extract content from string representation if it's embedded
            response_str = str(raw_response)
            if "content': '" in response_str or 'content": "' in response_str:
                # Try to extract content from string representation
                import re

                pattern = r"'content': '([^']*)'|\"content\": \"([^']*)\""
                content_match = re.search(pattern, response_str)
                if content_match:
                    content = content_match.group(1) or content_match.group(2)
                else:
                    content = response_str
            else:
                content = response_str

        # Clean response content to remove sandbox references and download links
        content = self._clean_response_content(content)

        # Check if agent needs clarification from user
        clarification_request = await self._check_agent_clarification_needs(content, user_message)

        # Create response message
        response = MuxiResponse(role="assistant", content=content)

        # Note: clarification_request is tracked in observability but not stored in response

        # Add response to conversation context
        self._messages.append(
            {"role": "assistant", "content": self._content_to_text(response.content)}
        )

        # Emit agent response generated event
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "response_length": len(self._content_to_text(response.content)),
                "has_clarification_request": bool(clarification_request),
            },
            description=f"Agent {self.agent_id} generated response",
        )

        # Response storage is handled by chat orchestrator - agent should not store responses
        # The agent is just an executor, not the brain

        # Start intelligent tool execution loop
        # Get MCP configuration settings
        mcp_config = {}
        if self.overlord and hasattr(self.overlord, "_config") and self.overlord._config:
            mcp_config = self.overlord._config.get("mcp", {})

        # Extract configuration with defaults
        max_iterations = mcp_config.get("max_tool_iterations", 10)
        max_total_calls = mcp_config.get("max_tool_calls", 50)
        max_repeated_errors = mcp_config.get("max_repeated_errors", 3)

        # Generate unique chain ID for this tool execution sequence
        chain_id = f"chn_{generate_nanoid()}"

        # Initialize loop variables
        iteration = 0
        total_tool_calls = 0
        error_history: List[Dict[str, Any]] = []
        current_raw_response: Any = raw_response
        current_content = content
        all_tool_execution_results: List[Any] = []  # Store all tool results for artifact extraction

        # Tool execution loop
        while iteration < max_iterations:
            # Check for tool calls in the response
            tool_calls = None
            if hasattr(current_raw_response, "choices") and current_raw_response.choices:
                message = current_raw_response.choices[0].message
                # Handle both dict and object message types
                if isinstance(message, dict):
                    if "tool_calls" in message and message["tool_calls"]:
                        tool_calls = message["tool_calls"]
                else:
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        tool_calls = message.tool_calls
            elif isinstance(current_raw_response, dict) and "choices" in current_raw_response:
                response_message = cast(
                    Dict[str, Any], current_raw_response["choices"][0]["message"]
                )
                if "tool_calls" in response_message and response_message["tool_calls"]:
                    tool_calls = response_message["tool_calls"]

            # If no tool calls, break the loop
            if not tool_calls:
                break

            # Emit tool chain iteration started event
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_STARTED,
                level=observability.EventLevel.DEBUG,
                data={
                    "agent_id": self.agent_id,
                    "chain_id": chain_id,
                    "iteration": iteration + 1,
                    "total_iterations": max_iterations,
                    "tool_calls_count": len(tool_calls),
                    "total_tool_calls_so_far": total_tool_calls,
                    "has_previous_errors": len(error_history) > 0,
                },
                description=f"Tool chain iteration {iteration + 1} started with {len(tool_calls)} tool calls",
            )

            # Execute tool calls
            tool_results = []
            current_errors = []

            for tool_call in tool_calls:
                if total_tool_calls >= max_total_calls:
                    # Add system message about limit
                    tool_results.append(
                        {
                            "tool_call_id": (
                                tool_call.id if hasattr(tool_call, "id") else tool_call["id"]
                            ),
                            "role": "tool",
                            "content": json.dumps(
                                {
                                    "error": (
                                        f"Maximum tool call limit ({max_total_calls}) reached. "
                                        "Please summarize your findings."
                                    )
                                }
                            ),
                        }
                    )
                    break

                try:
                    # Extract tool info
                    if hasattr(tool_call, "function"):
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        tool_id = tool_call.id
                    else:
                        tool_name = tool_call["function"]["name"]
                        tool_args = json.loads(tool_call["function"]["arguments"])
                        tool_id = tool_call["id"]

                    # Split server_id and actual tool name
                    if "__" in tool_name:
                        server_id, actual_tool_name = tool_name.split("__", 1)
                    else:
                        # Fallback if no server prefix
                        server_id = None
                        actual_tool_name = tool_name

                    # Emit streaming event for tool call
                    display_name = (
                        server_id.replace("-", " ").replace("_", " ").title()
                        if server_id
                        else actual_tool_name
                    )
                    streaming.stream(
                        "progress",
                        f"Using the {display_name} tool...",
                        stage="tool_call",
                        tool_name=actual_tool_name,
                        server_id=server_id,
                        skip_rephrase=True,
                    )

                    # Check for cancellation before tool execution
                    await self._check_cancellation(request_id)

                    # Invoke the tool
                    result = await self.invoke_tool(
                        tool_name=actual_tool_name,
                        parameters=tool_args,
                        server_id=server_id,
                        user_id=user_id,
                    )

                    # Store tool execution result for artifact extraction
                    from ...datatypes.clarification import ToolExecutionResult

                    # Debug log the result
                    if actual_tool_name == "generate_file":
                        observability.observe(
                            event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
                            level=observability.EventLevel.DEBUG,
                            data={
                                "tool_name": actual_tool_name,
                                "result_type": type(result).__name__,
                                "result_content": str(result)[:500],  # First 500 chars
                                "has_file_path": (
                                    "file_path" in result if isinstance(result, dict) else False
                                ),
                            },
                            description=f"generate_file result: {str(result)[:200]}",
                        )

                    tool_exec_result = ToolExecutionResult(
                        tool_name=actual_tool_name,
                        parameters=tool_args,
                        result=result,
                        execution_time=0.0,  # We don't track this currently
                        success=not isinstance(result, dict) or "error" not in result,
                    )
                    all_tool_execution_results.append(tool_exec_result)

                    total_tool_calls += 1

                    # Check if result is an error
                    is_error = False
                    if isinstance(result, dict) and "error" in result:
                        is_error = True
                        current_errors.append(
                            {
                                "tool": tool_name,
                                "error": result.get("error", "Unknown error"),
                                "iteration": iteration,
                            }
                        )

                    # Format tool result
                    # Remove non-serializable fields before JSON encoding
                    serializable_result = result.copy() if isinstance(result, dict) else result
                    if isinstance(serializable_result, dict) and "_artifact" in serializable_result:
                        serializable_result.pop("_artifact")

                    tool_results.append(
                        {
                            "tool_call_id": tool_id,
                            "role": "tool",
                            "content": json.dumps(serializable_result),
                        }
                    )

                except Exception as e:
                    # Check if this is a credential error that needs to bubble up
                    if isinstance(e, AmbiguousCredentialError):
                        # Stop processing all remaining tool calls and bubble up immediately
                        raise
                    elif isinstance(e, MissingCredentialError):
                        # Re-raise to let overlord handle the clarification
                        raise

                    error_trace = traceback.format_exc()
                    observability.observe(
                        event_type=observability.ConversationEvents.MCP_TOOL_CALL_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={
                            "agent_id": self.agent_id,
                            "chain_id": chain_id,
                            "iteration": iteration + 1,
                            "tool_name": tool_name if "tool_name" in locals() else "unknown",
                            "error": str(e),
                            "error_trace": error_trace,
                        },
                        description=f"Tool call execution failed: {str(e)}",
                    )
                    # Add error result
                    tool_results.append(
                        {
                            "tool_call_id": tool_id if "tool_id" in locals() else "unknown",
                            "role": "tool",
                            "content": json.dumps(
                                {
                                    "error": str(e),
                                    "tool_attempted": (
                                        tool_name if "tool_name" in locals() else "unknown"
                                    ),
                                }
                            ),
                        }
                    )
                    current_errors.append(
                        {
                            "tool": tool_name if "tool_name" in locals() else "unknown",
                            "error": str(e),
                            "iteration": iteration,
                        }
                    )
                    total_tool_calls += 1

            # Add tool results to messages
            if tool_results:
                # Add the assistant message with tool calls
                self._messages.append(
                    {
                        "role": "assistant",
                        "content": current_content or "",
                        "tool_calls": [
                            {
                                "id": tc.id if hasattr(tc, "id") else tc["id"],
                                "type": "function",
                                "function": {
                                    "name": (
                                        tc.function.name
                                        if hasattr(tc, "function")
                                        else tc["function"]["name"]
                                    ),
                                    "arguments": (
                                        tc.function.arguments
                                        if hasattr(tc, "function")
                                        else tc["function"]["arguments"]
                                    ),
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )

                # Add tool results
                self._messages.extend(tool_results)

                # Add errors to history
                if current_errors:
                    error_history.extend(current_errors)

                    # Check if we're making no progress
                    if self._is_making_no_progress(error_history, max_repeated_errors):
                        # Add guidance about being stuck
                        self._messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "You seem to be encountering repeated errors. "
                                    "Please either find an alternative approach or explain why "
                                    "the task cannot be completed."
                                ),
                            }
                        )

                # Add guidance for error recovery if needed
                if current_errors:
                    # Emit streaming event for tool failure retry
                    streaming.stream(
                        "thinking",
                        "That didn't work, trying another approach...",
                        stage="tool_retry",
                        failed_tools=[e["tool"] for e in current_errors],
                        skip_rephrase=True,
                    )

                    self._messages.append(
                        {
                            "role": "system",
                            "content": (
                                "The previous tool call(s) resulted in errors. "
                                "Analyze the errors carefully and determine if there are other "
                                "tools available that could help you make progress on the task. "
                                "Only make additional tool calls if they would genuinely help "
                                "resolve the issue or complete the task through an alternative approach."
                            ),
                        }
                    )

                # Get next response from model
                next_response = await self._call_active_model(
                    active_model,
                    "chat_with_tools",
                    cast(List[Dict[str, str]], self._messages),
                    tools=tools if tools else None,
                )

                # Extract content from response
                if isinstance(next_response, str):
                    current_content = next_response
                elif hasattr(next_response, "choices") and next_response.choices:
                    message = next_response.choices[0].message
                    if isinstance(message, dict):
                        current_content = message.get("content", "") or ""
                    else:
                        current_content = getattr(message, "content", "") or ""
                elif isinstance(next_response, dict) and "choices" in next_response:
                    current_content = (
                        next_response["choices"][0]["message"].get("content", "") or ""
                    )
                else:
                    current_content = str(next_response)

                # Update for next iteration
                current_raw_response = next_response
                content = current_content  # Update the main content variable

                # Check if agent is about to retry the same failed operation
                next_tool_calls = self._extract_tool_calls(next_response)
                if (
                    current_errors
                    and next_tool_calls
                    and self._is_repeating_failed_operation(next_tool_calls, error_history)
                ):
                    # Give agent one chance to reconsider
                    self._messages.append(
                        {
                            "role": "system",
                            "content": (
                                "Warning: You are about to retry an operation that just "
                                "failed with the same parameters. Please consider using a "
                                "different tool or approach to make progress."
                            ),
                        }
                    )
                    reconsider_response = await self._call_active_model(
                        active_model,
                        "chat_with_tools",
                        cast(List[Dict[str, str]], self._messages),
                        tools=tools if tools else None,
                    )

                    # Update with reconsidered response
                    if isinstance(reconsider_response, str):
                        current_content = reconsider_response
                    elif hasattr(reconsider_response, "choices") and reconsider_response.choices:
                        message = reconsider_response.choices[0].message
                        if isinstance(message, dict):
                            current_content = message.get("content", "") or ""
                        else:
                            current_content = getattr(message, "content", "") or ""
                    elif isinstance(reconsider_response, dict) and "choices" in reconsider_response:
                        current_content = (
                            reconsider_response["choices"][0]["message"].get("content", "") or ""
                        )
                    else:
                        current_content = str(reconsider_response)

                    current_raw_response = reconsider_response
                    content = current_content

            # Emit tool chain iteration completed event
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={
                    "agent_id": self.agent_id,
                    "chain_id": chain_id,
                    "iteration": iteration + 1,
                    "tool_calls_executed": len(tool_results),
                    "errors_encountered": len(current_errors),
                    "total_tool_calls": total_tool_calls,
                    "continuing": bool(self._extract_tool_calls(current_raw_response)),
                },
                description=f"Tool chain iteration {iteration + 1} completed",
            )

            iteration += 1

            # Check if we should stop due to limits
            if total_tool_calls >= max_total_calls:
                break

        # Update the response content with final content
        # Clean the content to remove sandbox references and download links
        response.content = self._clean_response_content(content)

        # Extract artifacts from tool results if any tools were executed
        if total_tool_calls > 0 and all_tool_execution_results:
            try:
                artifacts = await extract_artifacts_from_tool_results(all_tool_execution_results)
                if artifacts:
                    response.artifacts = artifacts
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
                        level=observability.EventLevel.INFO,
                        data={
                            "agent_id": self.agent_id,
                            "artifacts_count": len(artifacts),
                            "artifact_files": [a.filename for a in artifacts],
                        },
                        description=f"Agent {self.agent_id} extracted {len(artifacts)} artifacts from tool results",
                    )
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                    },
                    description=f"Failed to extract artifacts: {e}",
                )

        # Emit tool chain completed event
        if iteration > 0:  # Only emit if we actually did tool chaining
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_TOOL_CHAIN_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={
                    "agent_id": self.agent_id,
                    "chain_id": chain_id,
                    "total_iterations": iteration,
                    "total_tool_calls": total_tool_calls,
                    "total_errors": len(error_history),
                    "reached_iteration_limit": iteration >= max_iterations,
                    "reached_call_limit": total_tool_calls >= max_total_calls,
                    "stopped_due_to_repeated_errors": self._is_making_no_progress(
                        error_history, max_repeated_errors
                    ),
                },
                description=f"Tool chain completed after {iteration} iterations and {total_tool_calls} tool calls",
            )

        # Add final response to context
        self._messages.append({"role": "assistant", "content": content})

        return response

    def _format_recent_documents(self, recent_docs: List[Dict[str, Any]]) -> List[str]:
        """
        Format recent documents into context parts.

        Args:
            recent_docs: List of recent document dictionaries

        Returns:
            List of formatted context strings
        """
        context_parts = []
        context_parts.append("--- Recently Uploaded Documents ---")
        for doc in recent_docs:
            context_parts.append(f"Filename: {doc.get('filename', 'Unknown')}")
            # Join content list if it's a list
            doc_content = doc.get("content", "")
            if isinstance(doc_content, list):
                # Check if list contains bytes
                if doc_content and isinstance(doc_content[0], bytes):
                    # List of bytes - try to decode each
                    decoded_parts = []
                    for part in doc_content:
                        try:
                            decoded_parts.append(
                                part.decode("utf-8") if isinstance(part, bytes) else str(part)
                            )
                        except (UnicodeDecodeError, AttributeError) as e:
                            observability.observe(
                                event_type=observability.ErrorEvents.WARNING,
                                level=observability.EventLevel.WARNING,
                                data={
                                    "agent_id": self.agent_id,
                                    "error": str(e),
                                    "content_type": "binary_list_item",
                                },
                                description=f"Failed to decode binary content in document list: {type(e).__name__}",
                            )
                            decoded_parts.append("[Binary content]")
                    doc_content = "\n".join(decoded_parts)
                else:
                    # List of strings
                    doc_content = "\n".join(str(item) for item in doc_content)
            elif isinstance(doc_content, bytes):
                # Handle binary content - decode if possible or show placeholder
                try:
                    doc_content = doc_content.decode("utf-8")
                except (UnicodeDecodeError, AttributeError) as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.WARNING,
                        level=observability.EventLevel.WARNING,
                        data={
                            "agent_id": self.agent_id,
                            "error": str(e),
                            "content_type": "binary_file",
                        },
                        description=f"Failed to decode binary file content: {type(e).__name__}",
                    )
                    doc_content = "[Binary file content - unable to display as text]"
            context_parts.append(f"{doc_content}")
            context_parts.append("")  # Empty line between docs
        context_parts.append("--- End Recently Uploaded Documents ---")
        return context_parts

    def _enhance_message_with_context(
        self,
        content: str,
        recent_docs: Optional[List[Dict[str, Any]]] = None,
        knowledge_results: Optional[List[Dict[str, Any]]] = None,
        memory_results: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Enhance message content with context from recent documents, knowledge, and memory.

        Args:
            content: Original message content
            recent_docs: List of recent document dictionaries
            knowledge_results: List of knowledge search results
            memory_results: List of memory search results

        Returns:
            Enhanced message content with context
        """
        if not (recent_docs or knowledge_results or memory_results):
            return content

        context_parts = []

        # Add recent document uploads first (highest priority)
        if recent_docs:
            context_parts.extend(self._format_recent_documents(recent_docs))

        # Add domain knowledge context
        if knowledge_results:
            context_parts.append("--- Domain Knowledge ---")
            for result in knowledge_results:
                context_parts.append(f"• {result.get('content', '')}")
            context_parts.append("--- End Domain Knowledge ---")

        # Add memory context
        if memory_results:
            context_parts.append("--- Recent Context ---")
            for result in memory_results:
                context_parts.append(f"• {result.get('content', '')}")
            context_parts.append("--- End Recent Context ---")

        context_enhancement = "\n\n" + "\n".join(context_parts) + "\n\n"
        return f"{content}{context_enhancement}"

    def _is_making_no_progress(
        self, error_history: List[Dict[str, Any]], max_repeated_errors: int
    ) -> bool:
        """
        Check if similar errors occurred too many times.

        Args:
            error_history: List of error dictionaries with 'tool', 'error', and 'iteration'
            max_repeated_errors: Maximum number of similar errors allowed

        Returns:
            True if making no progress, False otherwise
        """
        if len(error_history) < max_repeated_errors:
            return False

        # Group errors by pattern (ignoring tool name for similarity)
        error_counts: Dict[str, int] = {}
        lookback_window = max_repeated_errors * 2  # Check recent errors
        for error in error_history[-lookback_window:]:
            # Use error message pattern as key (first 50 chars)
            key = error["error"][:50].lower()
            error_counts[key] = error_counts.get(key, 0) + 1
            if error_counts[key] >= max_repeated_errors:
                return True
        return False

    def _is_repeating_failed_operation(
        self, new_calls: List[Any], error_history: List[Dict[str, Any]]
    ) -> bool:
        """
        Check if agent is retrying exact same failed operation.

        Args:
            new_calls: List of new tool calls to be made
            error_history: History of errors

        Returns:
            True if repeating a failed operation, False otherwise
        """
        if not error_history:
            return False

        last_error = error_history[-1]
        for call in new_calls:
            # Extract tool name from call
            if hasattr(call, "function"):
                tool_name = call.function.name
            else:
                tool_name = call["function"]["name"]

            # Check if it's the same tool that just failed
            if tool_name == last_error["tool"]:
                # Could also check parameters for exact match
                return True
        return False

    def _extract_tool_calls(self, response: Any) -> List[Any]:
        """
        Extract tool calls from a model response.

        Args:
            response: The raw response from the model

        Returns:
            List of tool calls, or empty list if none found
        """
        tool_calls = []

        if hasattr(response, "choices") and response.choices:
            message = response.choices[0].message
            # Handle both dict and object message types
            if isinstance(message, dict):
                if "tool_calls" in message and message["tool_calls"]:
                    tool_calls = message["tool_calls"]
            else:
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_calls = message.tool_calls
        elif isinstance(response, dict) and "choices" in response:
            message = response["choices"][0]["message"]
            if "tool_calls" in message and message["tool_calls"]:
                tool_calls = message["tool_calls"]

        return tool_calls

    async def _check_cancellation(self, request_id: Optional[str]) -> None:
        """
        Check if the request has been cancelled and raise exception if so.

        This is called at strategic points during message processing to allow
        cooperative cancellation of long-running requests.

        Args:
            request_id: The request ID to check

        Raises:
            RequestCancelledException: If the request is cancelled
        """
        if not request_id or not self.overlord:
            return

        tracker = getattr(self.overlord, "request_tracker", None)
        if tracker and tracker.is_cancelled(request_id):
            await tracker.clear_cancelled(request_id)
            raise RequestCancelledException(request_id)

    def _clean_response_content(self, content: str) -> str:
        """
        Clean response content to remove sandbox references and download links.

        When files are generated, they are automatically attached as artifacts,
        so we don't want agents mentioning file paths or download links.

        Args:
            content: The raw response content from the agent

        Returns:
            Cleaned content without file path references
        """
        import re

        # Remove markdown download links with sandbox paths
        content = re.sub(r"\[Download[^\]]*\]\(sandbox:[^\)]+\)", "", content)
        content = re.sub(r"\[download[^\]]*\]\(sandbox:[^\)]+\)", "", content, re.IGNORECASE)

        # Remove any remaining sandbox: references
        content = re.sub(r"sandbox:[^\s\)]+", "", content)

        # Remove common phrases about download links
        replacements = [
            (r"You can download it using the link below:\s*", ""),
            (r"Click here to download[^\.\n]*\.?\s*", ""),
            (r"Download link[s]?:\s*", ""),
            (r"The file[s]? (?:is|are) available for download[^\.\n]*\.?\s*", ""),
            (r"Use the download link[s]? to access[^\.\n]*\.?\s*", ""),
        ]

        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

        # Clean up any resulting double newlines or trailing spaces
        content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)
        content = re.sub(r" +\n", "\n", content)
        content = content.strip()

        # If the content becomes too short after cleaning, add a note about attached files
        if len(content) < 20 and any(
            word in content.lower() for word in ["created", "generated", "made"]
        ):
            content += "\n\nThe file has been attached to this response."

        return content

    async def _check_agent_clarification_needs(
        self, agent_response: str, user_message: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if the agent's response indicates it needs clarification from the user.

        This method analyzes the agent's response to detect patterns that suggest
        the agent needs additional information to complete the user's request.

        Args:
            agent_response: The response generated by the agent
            user_message: The original user message being processed

        Returns:
            Dict with clarification metadata if clarification is needed, None otherwise.
            Format: {
                "needs_clarification": True,
                "clarification_type": "information_request",
                "required_info": {
                    "budget": "What's your budget range for this project?",
                    "timeline": "When do you need this completed?"
                },
                "agent_reasoning": "I need budget and timeline to provide accurate recommendations"
            }
        """
        try:
            # Patterns that suggest the agent needs clarification
            clarification_patterns = [
                # Direct requests for information
                r"(?i)(?:what(?:'s| is)|how much|when|where|which|who)\s+"
                r"(?:is|are|do|does|did|will|would|should|could|can)\s+(?:you|your)",
                r"(?i)(?:i need|i require|could you (?:please )?(?:provide|tell|specify|clarify))",
                r"(?i)(?:what(?:'s| is) your|could you specify|please (?:provide|clarify|specify))",
                # Questions about preferences or requirements
                r"(?i)(?:do you (?:prefer|want|need)|would you like|are you looking for)",
                r"(?i)(?:what (?:type|kind|sort) of|which (?:option|approach|method))",
                # Uncertainty indicators
                r"(?i)(?:i(?:'m| am) not sure|unclear|ambiguous|could mean)",
                r"(?i)(?:depends on|varies based on|need(?:s)? more "
                r"(?:information|details|context))",
                # Multiple options requiring choice
                r"(?i)(?:several (?:options|ways|approaches)|multiple (?:possibilities|choices))",
                r"(?i)(?:option [abc12]|approach [abc12]|method [abc12])",
            ]

            # Check if response contains clarification patterns
            has_clarification_pattern = any(
                re.search(pattern, agent_response) for pattern in clarification_patterns
            )

            if not has_clarification_pattern:
                return None

            # Extract specific information requests using more sophisticated parsing
            required_info = await self._extract_information_requests(agent_response, user_message)

            if not required_info:
                return None

            # Generate agent reasoning
            reasoning = await self._generate_clarification_reasoning(agent_response, required_info)

            return {
                "needs_clarification": True,
                "clarification_type": "information_request",
                "required_info": required_info,
                "agent_reasoning": reasoning,
                "original_response": agent_response,
            }

        except Exception as e:
            # Log error but don't block processing
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PROCESSING_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "error": str(e),
                    "phase": "clarification_check",
                },
                description=f"Error checking clarification needs: {str(e)}",
            )
            return None

    async def _extract_information_requests(
        self, agent_response: str, user_message: str
    ) -> Dict[str, str]:
        """
        Extract specific information requests from agent response.

        Uses the IntentDetectionService for language-agnostic clarification detection.

        Args:
            agent_response: The agent's response text
            user_message: The original user message

        Returns:
            Dictionary mapping information categories to specific questions
        """
        try:
            # Get or create intent detection service
            if not hasattr(self, "_intent_detector"):
                # Use existing model instance
                llm_service = self.model

                self._intent_detector = IntentDetectionService(
                    llm_service=llm_service, enable_cache=True
                )

            # Use intent detection for clarification categories
            context = IntentDetectionContext(
                options=None,
                recent_messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": agent_response},
                ],
                user_language=None,
                user_timezone=None,
            )

            result = await self._intent_detector.detect_intent(
                text=agent_response, intent_type=IntentType.CLARIFICATION_CATEGORY, context=context
            )

            required_info = {}

            # If we detected a clarification category with good confidence
            if result.confidence > 0.6 and result.intent != "none":
                # Extract the actual question
                question = result.extracted_question
                if not question:
                    # Fall back to extracting question from response
                    question = await self._extract_question_for_category(
                        agent_response, result.intent
                    )

                if question:
                    required_info[result.intent] = question

            # Check alternatives for additional categories
            if result.alternatives:
                for alt in result.alternatives:
                    if alt["confidence"] > 0.5 and alt["intent"] not in required_info:
                        question = await self._extract_question_for_category(
                            agent_response, alt["intent"]
                        )
                        if question:
                            required_info[alt["intent"]] = question

            return required_info

        except Exception as e:
            # Fall back to keyword-based detection
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.WARNING,
                data={"agent_id": self.agent_id, "error": str(e), "phase": "clarification_intent"},
                description=f"Intent detection for clarification failed, using fallback: {str(e)}",
            )
            return await self._fallback_extract_information_requests(agent_response, user_message)

    async def _fallback_extract_information_requests(
        self, agent_response: str, user_message: str
    ) -> Dict[str, str]:
        """
        Fallback keyword-based information request extraction.

        Used when intent detection service is not available.
        """
        # Common information categories and their question patterns
        info_categories = {
            "budget": [
                r"(?i)(?:budget|cost|price|money|funding|spend)",
                r"(?i)(?:how much|what(?:'s| is) (?:the )?(?:cost|price))",
            ],
            "timeline": [
                r"(?i)(?:when|timeline|deadline|schedule|time)",
                r"(?i)(?:how (?:long|soon)|by when)",
            ],
            "preferences": [
                r"(?i)(?:prefer|preference|like|want|style|approach)",
                r"(?i)(?:which (?:type|kind|option)|what (?:type|kind))",
            ],
            "requirements": [
                r"(?i)(?:require|requirement|need|must|should|specification)",
                r"(?i)(?:what (?:features|capabilities|functionality))",
            ],
            "scope": [
                r"(?i)(?:scope|scale|size|extent|coverage)",
                r"(?i)(?:how (?:big|large|extensive|comprehensive))",
            ],
            "location": [
                r"(?i)(?:where|location|place|region|area)",
                r"(?i)(?:which (?:location|place|area))",
            ],
        }

        required_info = {}

        # Extract questions for each category found in the response
        for category, patterns in info_categories.items():
            for pattern in patterns:
                if re.search(pattern, agent_response):
                    # Extract the actual question from the response
                    question = await self._extract_question_for_category(agent_response, category)
                    if question:
                        required_info[category] = question
                        break

        return required_info

    async def _extract_question_for_category(self, response: str, category: str) -> Optional[str]:
        """
        Extract the specific question for a given information category.

        Args:
            response: Agent's response text
            category: Information category (budget, timeline, etc.)

        Returns:
            The extracted question or a generated question for the category
        """
        # Split response into sentences
        sentences = re.split(r"[.!?]+", response)

        # Category-specific keywords to look for
        category_keywords = {
            "budget": ["budget", "cost", "price", "money", "funding", "spend"],
            "timeline": ["when", "timeline", "deadline", "schedule", "time"],
            "preferences": ["prefer", "preference", "like", "want", "style"],
            "requirements": ["require", "requirement", "need", "must", "specification"],
            "scope": ["scope", "scale", "size", "extent", "coverage"],
            "location": ["where", "location", "place", "region", "area"],
        }

        keywords = category_keywords.get(category, [])

        # Find sentence containing category keywords and question patterns
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check if sentence contains category keywords and question indicators
            has_keyword = any(keyword.lower() in sentence.lower() for keyword in keywords)
            has_question = any(
                indicator in sentence.lower()
                for indicator in ["what", "how", "when", "where", "which", "?"]
            )

            if has_keyword and (has_question or sentence.endswith("?")):
                return sentence.strip() + ("?" if not sentence.endswith("?") else "")

        # Fallback: generate a generic question for the category
        generic_questions = {
            "budget": "What's your budget range for this project?",
            "timeline": "When do you need this completed?",
            "preferences": "What are your preferences for this request?",
            "requirements": "What are your specific requirements?",
            "scope": "What's the scope of work you're looking for?",
            "location": "Where should this be implemented or focused?",
        }

        return generic_questions.get(category)

    async def _generate_clarification_reasoning(
        self, agent_response: str, required_info: Dict[str, str]
    ) -> str:
        """
        Generate reasoning for why the agent needs clarification.

        Args:
            agent_response: The agent's response
            required_info: Dictionary of required information

        Returns:
            Human-readable explanation of why clarification is needed
        """
        if len(required_info) == 1:
            category = list(required_info.keys())[0]
            return f"I need to understand your {category} to provide the most helpful response."
        elif len(required_info) == 2:
            categories = list(required_info.keys())
            return (
                f"I need to understand your {categories[0]} and {categories[1]} "
                f"to provide accurate recommendations."
            )
        else:
            categories = list(required_info.keys())
            return (
                f"I need additional information about {', '.join(categories[:-1])}, "
                f"and {categories[-1]} to give you the best possible assistance."
            )

    async def run(self, input_text: str, use_memory: bool = True) -> str:
        """
        Simplified interface to run the agent with a text input.

        Args:
            input_text: The input text to process.
            use_memory: Whether to use memory for context (default: True).

        Returns:
            The agent's response as a string.
        """
        response = await self.process_message(input_text)
        return self._content_to_text(response.content)

    async def get_relevant_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get relevant memories for a query from the overlord's memory system.

        Args:
            query: The query to search for in memory.
            limit: Maximum number of memories to return.

        Returns:
            List of relevant memory entries.
        """
        if self.overlord and hasattr(self.overlord, "get_relevant_memories"):
            return await self.overlord.get_relevant_memories(query, limit)
        return []

    def discover_agents(
        self, capability_filter: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Discover available agents in the formation.

        Args:
            capability_filter: Optional list of capabilities to filter by.

        Returns:
            Dictionary of agent_id -> agent_info for discovered agents.
        """
        if self.overlord and hasattr(self.overlord, "discover_agents"):
            return self.overlord.discover_agents(capability_filter)
        return {}

    async def invoke_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        server_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a tool via MCP.

        Args:
            tool_name: Name of the tool to invoke.
            parameters: Parameters to pass to the tool.
            server_id: Optional server ID for multi-server setups.
            user_id: Optional user ID for credential resolution.

        Returns:
            The tool execution result.

        Raises:
            Exception: If tool invocation fails or tool is not allowed.
        """

        try:
            # Skill-related tool dispatch (activate_skill, run_skill, generate_file)
            from .skill_dispatch import (
                handle_activate_skill,
                handle_generate_file_local,
                handle_generate_file_rce,
                handle_run_skill,
            )

            if (
                tool_name == "activate_skill"
                and self.overlord
                and hasattr(self.overlord, "skill_manager")
                and self.overlord.skill_manager
            ):
                return await handle_activate_skill(
                    self.agent_id,
                    parameters,
                    self.overlord,
                    self._messages,
                    getattr(self, "_current_session_id", "default"),
                )

            if (
                tool_name == "run_skill"
                and self.overlord
                and hasattr(self.overlord, "rce_client")
                and self.overlord.rce_client
                and hasattr(self.overlord, "skill_manager")
                and self.overlord.skill_manager
            ):
                return await handle_run_skill(self.agent_id, parameters, self.overlord)

            if tool_name == "record_lesson" and self.overlord:
                # Built-in lessons write path (Memory Revamp Phase 2).
                captains_log = getattr(self.overlord, "captains_log", None)
                if captains_log is None:
                    return {"success": False, "error": "Captain's log service is not available"}
                rule = (parameters.get("rule") or "").strip()
                if not rule:
                    return {"success": False, "error": "record_lesson requires a non-empty rule"}
                context_note = (parameters.get("context") or "").strip() or None
                try:
                    lesson = await captains_log.record_lesson(
                        user_id=user_id if user_id is not None else "0",
                        agent_id=self.agent_id,
                        rule=rule,
                        context=context_note,
                    )
                except ValueError as e:
                    # Lessons disabled (tool called anyway) or invalid input:
                    # report to the model instead of failing the turn.
                    return {"success": False, "error": str(e)}
                return {
                    "success": True,
                    "lesson_id": lesson["public_id"],
                    "hits": lesson["hits"],
                    "message": "Lesson recorded; it will be applied in future sessions.",
                }

            if (
                tool_name in ("get_artifact", "get_artifact_content", "get_artifact_history")
                and self.overlord
            ):
                # Artifact retrieval built-ins (Artifact Memory Phase 2).
                # User-scoped: handlers only ever see the calling user's
                # artifacts, and every failure returns a friendly error
                # instead of raising into the turn.
                from .artifact_dispatch import (
                    handle_get_artifact,
                    handle_get_artifact_content,
                    handle_get_artifact_history,
                )

                artifact_handlers = {
                    "get_artifact": handle_get_artifact,
                    "get_artifact_content": handle_get_artifact_content,
                    "get_artifact_history": handle_get_artifact_history,
                }
                return await artifact_handlers[tool_name](
                    self.agent_id, parameters, self.overlord, user_id=user_id
                )

            if tool_name == "generate_file" and self.overlord:
                code = parameters.get("code", "")
                filename = parameters.get("filename")

                rce_client = getattr(self.overlord, "rce_client", None)
                skill_manager = getattr(self.overlord, "skill_manager", None)
                use_rce = rce_client and skill_manager and "file-generation" in skill_manager.skills

                if use_rce:
                    return await handle_generate_file_rce(
                        self.agent_id, code, filename, self.overlord
                    )
                elif hasattr(self.overlord, "artifact_service"):
                    return await handle_generate_file_local(
                        self.agent_id, code, filename, self.overlord
                    )

            # Regular MCP tool invocation
            #
            # Tool result cache lookup (formation+user-scoped, 5min TTL).
            # We compute the key once and reuse it for the post-call store so
            # canonicalization differences cannot cause a hit/store mismatch.
            from ...services.mcp import tool_cache

            _cache_key: Optional[str] = None
            _formation_id = (
                getattr(self.overlord, "formation_id", "default") if self.overlord else "default"
            )
            if tool_cache.is_cacheable(tool_name):
                _cache_key = tool_cache.make_key(
                    formation_id=_formation_id,
                    tool_name=tool_name,
                    parameters=parameters,
                    server_id=server_id,
                    user_id=user_id,
                )
                _cached = tool_cache.get(_cache_key)
                if _cached is not None:
                    streaming.stream(
                        "progress",
                        f"Using cached {tool_name}...",
                        stage="tool_cache_hit",
                        tool_name=tool_name,
                        server_id=server_id,
                        agent_name=self.agent_id,
                        skip_rephrase=True,
                    )
                    observability.observe(
                        event_type=observability.ConversationEvents.MCP_TOOL_CACHE_HIT,
                        level=observability.EventLevel.INFO,
                        data={
                            "agent_id": self.agent_id,
                            "tool_name": tool_name,
                            "server_id": server_id,
                            "formation_id": _formation_id,
                            "cache_stats": tool_cache.stats(),
                        },
                        description=(f"Agent {self.agent_id} served {tool_name} from tool cache"),
                    )
                    return _cached
            else:
                tool_cache.note_skipped()

            streaming.stream(
                "progress",
                f"Using {tool_name}...",
                stage="tool_started",
                tool_name=tool_name,
                server_id=server_id,
                agent_name=self.agent_id,
                skip_rephrase=True,
            )

            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "parameters": parameters,
                },
                description=f"Agent {self.agent_id} invoking tool {tool_name}",
            )

            # Get credential resolver from overlord if available
            credential_resolver = None
            if self.overlord and hasattr(self.overlord, "credential_resolver"):
                credential_resolver = self.overlord.credential_resolver

            current_request_id = None
            if self.overlord:
                from ...services.observability.context import get_current_request_context

                request_context = get_current_request_context()
                if request_context:
                    current_request_id = request_context.id

            # Get recent conversation context for credential selection
            conversation_context = []
            if user_id:
                try:
                    # Always include the most recent user messages for context
                    for msg in self._messages[-5:]:  # Last 5 messages
                        if msg.get("role") == "user" and msg.get("content"):
                            conversation_context.append(f"User: {msg['content']}")
                        elif msg.get("role") == "assistant" and msg.get("content"):
                            # Include assistant messages that mention credentials/accounts
                            content_lower = msg["content"].lower()
                            if any(
                                word in content_lower
                                for word in [
                                    "account",
                                    "credential",
                                    "auth",
                                    "token",
                                    "api",
                                    "key",
                                    "login",
                                    "password",
                                    "secret",
                                ]
                            ):
                                conversation_context.append(f"Assistant: {msg['content'][:200]}")

                except Exception:
                    # Failed to get conversation context, continue without it
                    conversation_context = []

            # Emit tool call started event
            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "has_parameters": bool(parameters),
                    "parameter_count": len(parameters) if parameters else 0,
                },
                description=f"Agent {self.agent_id} starting tool call: {tool_name}",
            )

            if server_id:
                result = await self._mcp_service.invoke_tool(
                    server_id,
                    tool_name,
                    parameters,
                    request_timeout=self.request_timeout,
                    user_id=user_id,
                    request_id=current_request_id,
                    credential_resolver=credential_resolver,
                    conversation_context=conversation_context,
                )
                # Check cancellation after MCP call returns
                from ..background.cancellation import check_cancellation_from_context

                if self.overlord and hasattr(self.overlord, "request_tracker"):
                    await check_cancellation_from_context(self.overlord.request_tracker)
            else:
                # Try to find the tool in any available server
                servers = await self._mcp_service.list_servers()
                result = None
                for server_name in servers:
                    try:
                        result = await self._mcp_service.invoke_tool(
                            server_name,
                            tool_name,
                            parameters,
                            request_timeout=self.request_timeout,
                            user_id=user_id,
                            request_id=current_request_id,
                            credential_resolver=credential_resolver,
                            conversation_context=conversation_context,
                        )
                        break
                    except Exception:
                        continue

                if result is None:
                    raise Exception(f"Tool '{tool_name}' not found in any connected server")

                # Check cancellation after MCP call returns
                from ..background.cancellation import check_cancellation_from_context

                if self.overlord and hasattr(self.overlord, "request_tracker"):
                    await check_cancellation_from_context(self.overlord.request_tracker)

            tool_success = not self._is_tool_execution_error(result)

            # Store successful read-tool results in the cache. We deliberately
            # never cache error responses — they may reflect transient issues
            # (rate limits, network blips) and serving them from cache would
            # extend the failure window across the TTL.
            if _cache_key is not None and tool_success:
                tool_cache.set(_cache_key, result)

            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "success": tool_success,
                },
                description=(
                    f"Agent {self.agent_id} completed tool call {tool_name}"
                    if tool_success
                    else f"Agent {self.agent_id} received tool error from {tool_name}"
                ),
            )

            return result

        except Exception as e:
            # Check if this is a credential error
            from ...services.mcp.service import CredentialSelectionNeededError
            from ..credentials import AmbiguousCredentialError

            if isinstance(e, CredentialSelectionNeededError):
                # Convert to AmbiguousCredentialError and raise to overlord
                raise AmbiguousCredentialError(
                    service=e.service,
                    user_id=e.user_id,
                    available_credentials=e.available_credentials,
                    ordered_credentials=e.ordered_credentials,
                ) from e
            elif isinstance(e, AmbiguousCredentialError):
                # Re-raise to let overlord handle it
                raise

            # Original MissingCredentialError handling
            elif isinstance(e, MissingCredentialError):
                if self.overlord and hasattr(self.overlord, "handle_missing_credential"):
                    await self.overlord.handle_missing_credential(
                        service=e.service,
                        user_id=e.user_id,
                        context={
                            "agent_id": self.agent_id,
                            "tool_name": tool_name,
                            "server_id": server_id,
                        },
                    )
                    # Re-raise to let overlord handle the clarification
                    raise
            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "error": str(e),
                },
                description=f"Agent {self.agent_id} tool call failed: {str(e)}",
            )
            raise

    async def _request_a2a_assistance(
        self, user_message: str, needed_capability: Optional[str] = None
    ) -> Optional[str]:
        """
        Request A2A assistance when the agent needs capabilities it doesn't have.
        Simply passes the user message to another agent for execution.

        Args:
            user_message: The original user request
            needed_capability: Optional hint about what capability is needed

        Returns:
            The A2A response if successful, None otherwise
        """
        try:
            # Check if this is a workflow task using metadata first
            is_workflow_task = False

            # Check metadata if available (from process_message context)
            if hasattr(self, "_current_message_metadata") and self._current_message_metadata:
                is_workflow_task = (
                    self._current_message_metadata.get("is_workflow_task", False)
                    or self._current_message_metadata.get("task_type") == "workflow"
                    or self._current_message_metadata.get("source") == "workflow_executor"
                )

            # Fallback to string matching only if metadata not available
            if not is_workflow_task:
                is_workflow_task = (
                    ("## Task:" in user_message)
                    or ("Task Details:" in user_message)
                    or ("Required Capabilities:" in user_message)
                    or ("THIS SPECIFIC TASK ONLY" in user_message)
                )

            if is_workflow_task:
                # For workflow tasks, just return None to indicate we can't help
                # The workflow executor should handle reassignment
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_A2A,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": self.agent_id,
                        "phase": "a2a_bypassed",
                        "reason": "workflow_task_detected",
                        "needed_capability": needed_capability,
                    },
                    description=f"Agent {self.agent_id} bypassing A2A for workflow task",
                )
                return None
            # Check for A2A loops - prevent infinite delegation
            request_hash = f"{self.agent_id}:{needed_capability}:{user_message[:50]}"
            # Note: 'in' operator works efficiently with deque for small sizes
            if request_hash in self._a2a_history:
                observability.observe(
                    event_type=observability.ErrorEvents.A2A_MESSAGE_HANDLING_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": "A2A loop detected",
                        "capability": needed_capability,
                        "history": list(
                            self._a2a_history
                        ),  # Convert deque to list for serialization
                    },
                    description="Detected A2A loop - stopping delegation",
                )
                return None

            # Add to history (deque automatically maintains max size)
            self._a2a_history.append(request_hash)
            # Discover available agents via A2A coordinator
            if self.overlord and hasattr(self.overlord, "a2a_coordinator"):
                # Try to use unified discovery if available
                if hasattr(self.overlord.a2a_coordinator, "get_all_available_agents"):
                    available_agents = await self.overlord.a2a_coordinator.get_all_available_agents(
                        self.agent_id, include_external=True
                    )
                else:
                    available_agents = self.overlord.a2a_coordinator.get_available_agents_for_a2a(
                        self.agent_id
                    )
            else:
                available_agents = {}

            if not available_agents:
                return None

            # Find the best agent based on capabilities and preference score
            best_agent_id = None
            best_agent_info = None
            best_score = float("inf")  # Lower is better

            # Select agent based on capability match and preference score
            for agent_id, agent_info in available_agents.items():
                if agent_id == self.agent_id:  # Skip self
                    continue

                # Check if agent has the needed capability
                agent_capabilities = agent_info.get("capabilities", [])
                preference_score = agent_info.get("preference_score", 1.0)

                # If we have a specific capability need, check for it
                if needed_capability:
                    capability_match = False
                    # Check for exact or partial match
                    for cap in agent_capabilities:
                        cap_lower = cap.lower()
                        needed_lower = needed_capability.lower()
                        # Check for exact match or if capability contains the needed term
                        if (
                            cap_lower == needed_lower
                            or needed_lower in cap_lower
                            or cap_lower in needed_lower
                        ):
                            capability_match = True
                            break

                    # Check if any significant terms from the needed capability match agent capabilities
                    # Extract potential service/tool names from the needed capability (that might be service names)
                    # Use a more generic approach - look for proper nouns or technical terms
                    needed_words = needed_lower.split()
                    capability_words = [c.lower() for c in agent_capabilities]

                    # Check for any meaningful overlap between needed capability and agent capabilities
                    for word in needed_words:
                        # Skip common words
                        if len(word) > 3 and word not in [
                            "with",
                            "using",
                            "from",
                            "into",
                            "that",
                            "this",
                            "have",
                            "will",
                        ]:
                            if any(word in cap_word for cap_word in capability_words):
                                capability_match = True
                                break

                    if capability_match and preference_score < best_score:
                        best_agent_id = agent_id
                        best_agent_info = agent_info
                        best_score = preference_score
                else:
                    # No specific capability needed, just pick based on preference
                    if preference_score < best_score:
                        best_agent_id = agent_id
                        best_agent_info = agent_info
                        best_score = preference_score

            # If no capability match found, fall back to any agent
            if not best_agent_id and available_agents:
                for agent_id, agent_info in available_agents.items():
                    if agent_id != self.agent_id:
                        best_agent_id = agent_id
                        best_agent_info = agent_info
                        break

            if not best_agent_id:
                return None

            # Send A2A request for assistance
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "target_agent_id": best_agent_id,
                    "needed_capability": needed_capability,
                    "reason": "Agent needs capability it doesn't have",
                },
                description=f"Agent {self.agent_id} requesting A2A assistance from {best_agent_id}",
            )

            # Craft the A2A message using proper A2A protocol format
            from ...utils.id_generator import generate_nanoid

            a2a_message = {
                "role": "user",
                "messageId": f"msg_{generate_nanoid()}",
                "parts": [
                    {"type": "TextPart", "text": user_message},
                    {
                        "type": "DataPart",
                        "data": {
                            "action": "execute_task",
                            "original_request": user_message,
                            "needed_capability": needed_capability,
                            "requesting_agent": self.agent_id,
                            "execution_required": True,
                        },
                    },
                ],
            }

            # Log the A2A request details
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "target_agent_id": best_agent_id,
                    "message_content": a2a_message,
                    "execution_requested": True,
                },
                description=f"A2A execution request: {self.agent_id} -> {best_agent_id}",
            )

            # Use unified send_a2a_message for both internal and external agents
            # Add enriched context for external agents
            enriched_context = None
            if best_agent_info and best_agent_info.get("type") == "external":
                enriched_context = {
                    "source_formation": self.overlord.formation_id,
                    "source_agent": self.agent_id,
                    "needed_capability": needed_capability,
                    "execution_required": True,
                    "original_request": user_message,
                }

            # Send message using unified transport
            response = await self.send_a2a_message(
                target_agent_id=best_agent_id,
                message=a2a_message,
                message_type="request",
                context=enriched_context,
                wait_for_response=True,
                timeout=60,  # Give more time for complex requests
            )

            # Check cancellation after A2A call returns
            from ..background.cancellation import check_cancellation_from_context

            if self.overlord and hasattr(self.overlord, "request_tracker"):
                await check_cancellation_from_context(self.overlord.request_tracker)

            if response:
                # Initialize variables
                result_content = None
                execution_completed = False

                # Check for external A2A format (has 'status' field at top level)
                if response.get("status") == "success":
                    # External A2A response format
                    result_content = response.get("response", response.get("advice", ""))
                    execution_completed = response.get("execution_completed", False)

                # Check for internal A2A format (has 'parts' and 'metadata' fields)
                elif "parts" in response and "metadata" in response:
                    # Internal A2A response - the actual response is in metadata
                    metadata = response.get("metadata", {})

                    # Extract from metadata
                    if metadata.get("status") == "success":
                        result_content = metadata.get("response", "")
                        execution_completed = metadata.get("executed", False)

                # Process the result content if we found it
                if result_content:
                    # Handle MuxiResponse objects
                    if hasattr(result_content, "content"):
                        content_length = (
                            len(result_content.content) if result_content.content else 0
                        )
                    elif isinstance(result_content, str):
                        content_length = len(result_content)
                    else:
                        content_length = len(str(result_content)) if result_content else 0

                    # Log the A2A response
                    observability.observe(
                        event_type=observability.ConversationEvents.A2A_MESSAGE_RECEIVED,
                        level=observability.EventLevel.INFO,
                        data={
                            "agent_id": self.agent_id,
                            "source_agent_id": best_agent_id,
                            "execution_completed": execution_completed,
                            "response_length": content_length,
                        },
                        description=f"A2A response received: execution={execution_completed}",
                    )
                    # Extract string content from muxi.runtimeResponse if needed
                    if hasattr(result_content, "content"):
                        result_text = result_content.content
                    elif isinstance(result_content, dict):
                        # Handle dictionary results (e.g., from tool execution)
                        import json

                        # Try to extract meaningful content from the dict
                        if "result" in result_content:
                            result_text = result_content["result"]
                        elif "output" in result_content:
                            result_text = result_content["output"]
                        elif "content" in result_content:
                            # Handle nested content structure
                            content = result_content["content"]
                            if isinstance(content, dict) and "content" in content:
                                # Extract from nested content.content structure
                                nested_content = content["content"]
                                if isinstance(nested_content, list) and nested_content:
                                    # Extract text from content items
                                    text_parts = []
                                    for item in nested_content:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            text_parts.append(item.get("text", ""))
                                    result_text = (
                                        "\n".join(text_parts)
                                        if text_parts
                                        else json.dumps(result_content, indent=2)
                                    )
                                else:
                                    result_text = str(content)
                            else:
                                result_text = str(content)
                        else:
                            # Format as pretty JSON for readability
                            result_text = json.dumps(result_content, indent=2)
                    else:
                        result_text = str(result_content)

                    # Format the collaborative response
                    if execution_completed:
                        # Task was executed by the other agent
                        return result_text  # Return the actual execution result
                    else:
                        # Only consultation/advice was provided
                        return (
                            f"I'll collaborate with {best_agent_id} to help you with this.\n\n"
                            f"{result_text}"
                        )

            return None

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.A2A_MESSAGE_HANDLING_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "error": str(e),
                    "phase": "a2a_assistance_request",
                },
                description=f"Failed to request A2A assistance: {str(e)}",
            )
            return None

    @staticmethod
    def _parse_json_like_text(text: str) -> Any:
        """Parse a JSON-looking text blob, otherwise return the original string."""
        if not isinstance(text, str):
            return text

        cleaned = text.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            if len(parts) >= 3:
                cleaned = parts[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()

        if not cleaned or cleaned[0] not in "[{":
            return text

        try:
            return json.loads(cleaned)
        except Exception:
            return text

    def _extract_structured_planning_result_payload(self, result: Any) -> Any:
        """Best-effort extraction of structured content from a tool result."""
        candidate = result
        if isinstance(candidate, dict):
            top_level_structured = candidate.get("structuredContent")
            if top_level_structured not in (None, "", [], {}):
                return top_level_structured
            candidate = candidate.get("result", candidate.get("output", candidate))

        if isinstance(candidate, str):
            parsed = self._parse_json_like_text(candidate)
            if isinstance(parsed, (dict, list)):
                return parsed
            return candidate

        if not isinstance(candidate, dict):
            return candidate

        structured_content = candidate.get("structuredContent")
        if structured_content not in (None, "", [], {}):
            return structured_content

        # Also check for structured_content (underscore variant from ModernProtocolFeatures)
        structured_content_alt = candidate.get("structured_content")
        if structured_content_alt not in (None, "", [], {}):
            return structured_content_alt

        content = candidate.get("content")
        if isinstance(content, str):
            parsed = self._parse_json_like_text(content)
            if isinstance(parsed, (dict, list)):
                return parsed
        if isinstance(content, list):
            parsed_items: List[Any] = []
            text_chunks: List[str] = []
            for item in content:
                text_value: Optional[str] = None
                if isinstance(item, dict):
                    if item.get("structuredContent") not in (None, "", [], {}):
                        parsed_items.append(item.get("structuredContent"))
                        continue
                    if item.get("type") == "text" and isinstance(item.get("text"), str):
                        text_value = item.get("text")
                elif isinstance(item, str):
                    text_value = item

                if not text_value:
                    continue

                parsed = self._parse_json_like_text(text_value)
                if isinstance(parsed, (dict, list)):
                    parsed_items.append(parsed)
                else:
                    text_chunks.append(text_value)

            if parsed_items:
                return parsed_items[0] if len(parsed_items) == 1 else parsed_items
            if text_chunks:
                return "\n".join(text_chunks)

        return candidate

    @staticmethod
    def _iter_result_records(value: Any):
        """Yield every nested mapping inside a structured tool result."""
        if isinstance(value, dict):
            yield value
            for nested_value in value.values():
                yield from Agent._iter_result_records(nested_value)
        elif isinstance(value, list):
            for item in value:
                yield from Agent._iter_result_records(item)

    @staticmethod
    def _extract_context_hints(*texts: str, limit: int = 12) -> List[str]:
        """Extract salient file/resource hints from the request and step descriptions."""
        hints: List[str] = []
        seen: set[str] = set()
        keyword_hints = {
            "root",
            "folder",
            "file",
            "files",
            "workbook",
            "worksheet",
            "document",
            "message",
            "task",
            "site",
            "record",
            "calendar",
            "mailbox",
            "thread",
            "chat",
        }

        def add_hint(raw_hint: str) -> None:
            hint = raw_hint.strip(" \t\r\n.,:;()[]{}<>`'\"")
            if not hint:
                return
            normalized = hint.lower()
            if normalized in seen:
                return
            seen.add(normalized)
            hints.append(hint)

        filename_pattern = re.compile(
            r"(?<![\w/])([A-Za-z0-9][A-Za-z0-9 _.\-]{0,120}\.[A-Za-z0-9]{1,8})(?![\w/])"
        )
        quoted_pattern = re.compile(r"['\"]([^'\"]{2,120})['\"]")
        hashtag_pattern = re.compile(r"(?<!\w)#([A-Za-z0-9][A-Za-z0-9_.\-]{0,80})")
        mention_pattern = re.compile(r"(?<!\w)@([A-Za-z0-9][A-Za-z0-9_.\-]{0,80})")

        for text in texts:
            if not isinstance(text, str) or not text.strip():
                continue
            for match in filename_pattern.findall(text):
                add_hint(match)
            for match in quoted_pattern.findall(text):
                add_hint(match)
            for match in hashtag_pattern.findall(text):
                if re.fullmatch(r"[0-9A-Fa-f]{3,8}", match):
                    continue
                add_hint(match)
                add_hint(f"#{match}")
            for match in mention_pattern.findall(text):
                add_hint(match)
                add_hint(f"@{match}")
            lowered = text.lower()
            for keyword in keyword_hints:
                if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                    add_hint(keyword)
            if len(hints) >= limit:
                break

        return hints[:limit]

    @staticmethod
    def _extract_primary_filename_hint(*texts: str) -> Optional[str]:
        """Return the first concrete filename-like hint from the provided texts."""
        bare_filename_pattern = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.\-]{0,120}\.[A-Za-z0-9]{1,8})")
        spaced_filename_pattern = re.compile(
            r"([A-Za-z0-9][A-Za-z0-9 _.\-]{0,120}\.[A-Za-z0-9]{1,8})"
        )

        candidates: List[str] = []
        seen: set[str] = set()
        for text in texts:
            if not isinstance(text, str) or not text.strip():
                continue

            for pattern in (bare_filename_pattern, spaced_filename_pattern):
                for match in pattern.findall(text):
                    candidate = match.strip(" \t\r\n.,:;()[]{}<>`'\"")
                    if not candidate:
                        continue
                    marker = candidate.lower()
                    if marker in seen:
                        continue
                    seen.add(marker)
                    candidates.append(candidate)

        candidates.sort(key=lambda value: (value.count(" "), len(value)))
        for candidate in candidates:
            if candidate.count(" ") > 2:
                continue
            return candidate
        return None

    @staticmethod
    def _record_matches_context_hints(record: Dict[str, Any], hints: List[str]) -> bool:
        """Return True when a record appears to describe one of the requested resources."""
        if not isinstance(record, dict) or not hints:
            return False

        candidate_fields = [
            record.get("name"),
            record.get("title"),
            record.get("subject"),
            record.get("displayName"),
            record.get("display_name"),
            record.get("fileName"),
            record.get("file_name"),
            record.get("path"),
            record.get("webUrl"),
            record.get("web_url"),
            record.get("channel_name"),
            record.get("topic"),
        ]
        normalized_fields = [
            str(field).lower() for field in candidate_fields if field not in (None, "")
        ]
        if not normalized_fields:
            return False

        for hint in hints:
            normalized_hint = hint.lower()
            for field in normalized_fields:
                if normalized_hint == field or normalized_hint in field or field in normalized_hint:
                    return True
        return False

    @staticmethod
    def _infer_parameter_record_kind(
        param_name: str,
        *,
        tool_name: str = "",
        action_description: str = "",
        param_definition: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Infer whether an identifier should resolve from a file-like or folder-like record."""
        lowered_param = param_name.lower().replace("_", "")
        if not lowered_param.endswith(("itemid", "fileid", "folderid", "documentid", "workbookid")):
            return "generic"

        if lowered_param.endswith("folderid"):
            return "folder"
        if lowered_param.endswith(("fileid", "documentid", "workbookid")):
            return "file"

        description = ""
        if isinstance(param_definition, dict):
            description = str(param_definition.get("description", ""))
        context_text = " ".join(
            part
            for part in (tool_name, action_description, description)
            if isinstance(part, str) and part.strip()
        ).lower()

        if any(
            token in context_text
            for token in ("folder", "root item", "root folder", "directory", "children")
        ):
            return "folder"
        if any(
            token in context_text
            for token in ("worksheet", "workbook", "excel", "attachment", "download", "upload")
        ):
            return "file"
        if re.search(r"\.[a-z0-9]{1,8}\b", context_text):
            return "file"

        return "generic"

    @staticmethod
    def _record_matches_expected_kind(record: Dict[str, Any], expected_kind: str) -> bool:
        """Return True when a record matches the kind expected by the target parameter."""
        if expected_kind == "generic":
            return True
        if not isinstance(record, dict):
            return False

        name_value = record.get("name") or record.get("fileName") or ""
        name_text = str(name_value).lower()
        looks_like_folder = "folder" in record or "root" in record
        looks_like_file = "file" in record or bool(
            re.search(r"\.[a-z0-9]{1,8}\b$", name_text, flags=re.IGNORECASE)
        )

        if expected_kind == "folder":
            return looks_like_folder and not looks_like_file
        if expected_kind == "file":
            return looks_like_file and not looks_like_folder
        return True

    @staticmethod
    def _compact_planning_record(value: Any, depth: int = 0) -> Any:
        """Reduce large tool results to the fields most useful for follow-up planning."""
        if depth > 2:
            return "[truncated]"

        if isinstance(value, dict):
            preferred_keys = [
                "id",
                "name",
                "title",
                "subject",
                "displayName",
                "display_name",
                "driveId",
                "drive_id",
                "driveItemId",
                "drive_item_id",
                "parentReference",
                "parent_reference",
                "path",
                "webUrl",
                "web_url",
                "file",
                "folder",
                "root",
                "siteId",
                "site_id",
                "createdDateTime",
                "created_at",
                "lastModifiedDateTime",
                "updated_at",
                "channel_id",
                "channel_name",
                "topic",
                "position",
                "visibility",
                "type",
                "status",
                "description",
            ]
            compact: Dict[str, Any] = {}
            for key in preferred_keys:
                if key in value:
                    compact[key] = Agent._compact_planning_record(value[key], depth + 1)
            if not compact:
                for key, nested_value in list(value.items())[:8]:
                    compact[key] = Agent._compact_planning_record(nested_value, depth + 1)
            return compact

        if isinstance(value, list):
            return [Agent._compact_planning_record(item, depth + 1) for item in value[:3]]

        if isinstance(value, str) and len(value) > 200:
            return value[:197].rstrip() + "..."

        return value

    def _summarize_planning_result(
        self, result: Any, context_hint: str = "", limit: int = 500
    ) -> str:
        """Summarize a prior tool result for planning/replanning context."""
        payload = self._extract_structured_planning_result_payload(result)
        context_hints = self._extract_context_hints(context_hint)

        matching_records: List[Dict[str, Any]] = []
        if context_hints:
            for record in self._iter_result_records(payload):
                if not isinstance(record, dict):
                    continue
                if self._record_matches_context_hints(record, context_hints):
                    compact_record = self._compact_planning_record(record)
                    if compact_record not in matching_records:
                        matching_records.append(compact_record)
                if len(matching_records) >= 3:
                    break

        if matching_records:
            try:
                text = json.dumps({"matching_records": matching_records}, ensure_ascii=False)
            except TypeError:
                text = str({"matching_records": matching_records})
        else:
            compact_payload = self._compact_planning_record(payload)
            try:
                text = json.dumps(compact_payload, ensure_ascii=False)
            except TypeError:
                text = str(compact_payload)

        text = text.strip()
        if len(text) > limit:
            return text[: limit - 3].rstrip() + "..."
        return text

    def _build_delegation_prompt_with_results(
        self,
        delegation_prompt: str,
        my_results: Dict[str, Any],
        context_hint: str = "",
    ) -> str:
        """Enrich delegated prompts with prior successful tool results."""
        enriched_prompt = delegation_prompt.strip() if isinstance(delegation_prompt, str) else ""

        for placeholder, result in my_results.items():
            if placeholder not in enriched_prompt:
                continue
            result_text = str(result)
            if isinstance(result, dict):
                raw_result_text = result.get("result", result.get("output", str(result)))
                result_text = (
                    raw_result_text if isinstance(raw_result_text, str) else str(raw_result_text)
                )
            enriched_prompt = enriched_prompt.replace(placeholder, result_text)

        successful_results = self._get_successful_planning_results(my_results)
        if not successful_results:
            return enriched_prompt

        summary_lines: List[str] = []
        for placeholder, result in successful_results.items():
            summary = self._summarize_planning_result(result, context_hint=context_hint, limit=800)
            if summary:
                summary_lines.append(f"- {placeholder}: {summary}")

        if not summary_lines:
            return enriched_prompt

        results_block = (
            "## Prior tool results\n"
            + "\n".join(summary_lines)
            + "\n\nUse the prior tool results above when answering. "
            "If they are insufficient, say so explicitly and do not invent missing data."
        )

        if not enriched_prompt:
            return results_block
        if results_block in enriched_prompt:
            return enriched_prompt
        return f"{enriched_prompt.rstrip()}\n\n{results_block}"

    def _build_missing_parameter_replanning_feedback(
        self,
        failed_step: Dict[str, Any],
        tool_name: str,
        unresolved_params: List[str],
        current_plan: Dict[str, Any],
        my_results: Dict[str, Any],
    ) -> str:
        """Explain why the current plan failed and what the replan must fix."""
        current_tools = [
            step.get("tool_name", "")
            for step in current_plan.get("my_steps", [])
            if step.get("tool_name")
        ]
        feedback_lines = [
            "Previous execution plan could not complete because a tool step was missing",
            "required identifiers that must be discovered before the final action.",
            f"Failed step: {failed_step.get('action', '')}",
            f"Tool: {tool_name}",
            f"Missing required parameters: {', '.join(unresolved_params)}",
        ]
        if current_tools:
            feedback_lines.append(f"Current tool chain: {', '.join(current_tools)}")
        feedback_lines.extend(
            [
                "Revise the plan so prerequisite lookup/discovery steps happen before the",
                "failed tool call.",
                "A parent/root/container ID is not the same as the target resource ID.",
                "If the user named a specific resource, add the list/search step that returns",
                "that named resource itself before the final action.",
                "Do not guess missing identifiers or use placeholder values.",
            ]
        )
        if my_results:
            feedback_lines.append(
                "Reuse any existing tool results already gathered instead of repeating completed steps."
            )
        return "\n".join(feedback_lines)

    def _build_validation_failure_replanning_feedback(
        self,
        failed_step: Dict[str, Any],
        tool_name: str,
        validation_error: str,
        blocked_params: List[str],
        current_plan: Dict[str, Any],
        my_results: Dict[str, Any],
    ) -> str:
        """Explain a fail-closed validation block so replanning can correct it."""
        current_tools = [
            step.get("tool_name", "")
            for step in current_plan.get("my_steps", [])
            if step.get("tool_name")
        ]
        feedback_lines = [
            "Previous execution plan was blocked before tool execution because the",
            "planned parameters did not satisfy the tool contract.",
            f"Failed step: {failed_step.get('action', '')}",
            f"Tool: {tool_name}",
            f"Validation error: {validation_error}",
        ]
        if blocked_params:
            feedback_lines.append(f"Blocked parameters: {', '.join(blocked_params)}")
        if current_tools:
            feedback_lines.append(f"Current tool chain: {', '.join(current_tools)}")
        feedback_lines.extend(
            [
                "Revise the plan so the blocked tool step only uses parameters declared",
                "in the tool schema and only after prerequisite discovery steps have",
                "produced any required identifiers.",
                "Do not invent undeclared parameter names.",
                "Do not guess missing identifiers or leave placeholder values unresolved.",
            ]
        )
        if my_results:
            feedback_lines.append(
                "Reuse any existing tool results already gathered instead of repeating completed steps."
            )
        return "\n".join(feedback_lines)

    @staticmethod
    def _normalize_repair_plan_signature(plan: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the meaningful parts of a plan for repair/no-change checks."""
        return {
            "my_steps": [
                {
                    "action": step.get("action", ""),
                    "tool_name": step.get("tool_name", ""),
                    "parameters": step.get("parameters", {}),
                    "output_placeholder": step.get("output_placeholder", ""),
                }
                for step in plan.get("my_steps", [])
            ],
            "delegate_steps": [
                {
                    "action": step.get("action", ""),
                    "capability_needed": step.get("capability_needed", ""),
                    "delegation_prompt": step.get("delegation_prompt", ""),
                }
                for step in plan.get("delegate_steps", [])
            ],
            "data_flow": plan.get("data_flow", ""),
        }

    # Unambiguous domain tokens used by the repair-tool scorer.  Generic
    # tokens that appear in several domains (e.g. "file", "folder", "item",
    # "message", "page", "list") are intentionally excluded -- a tool whose
    # name only contains those tokens stays untagged so it does not incur a
    # cross-domain penalty against another untagged or mismatched tool.
    _DOMAIN_TOKENS: Dict[str, tuple[str, ...]] = {
        "mail": ("mail", "email", "gmail", "inbox", "mailbox"),
        "calendar": ("calendar", "event", "meeting", "appointment"),
        "drive": (
            "drive",
            "onedrive",
            "workbook",
            "worksheet",
            "spreadsheet",
            "excel",
        ),
        "sharepoint": ("sharepoint",),
        "chat": ("channel", "slack", "teams"),
        "contact": ("contact",),
        "task": ("task", "todo"),
        "note": ("notebook", "onenote"),
    }

    @classmethod
    def _get_tool_domain_tags(cls, tool_name: str) -> frozenset[str]:
        """Return the set of unambiguous domain tags inferred from a tool name.

        Matching treats ``_`` / ``-`` / ``.`` as separators and only counts
        tokens from ``_DOMAIN_TOKENS``.  Both the server prefix and the
        bare tool name are scanned -- ``todo-helper-mcp__get-default-list-id``
        carries its domain in the prefix, while ``ms365-mcp__list-mail-folders``
        carries it in the bare name.  Ambiguous tokens (file, folder, item,
        message, page, list, get, etc.) are deliberately excluded so we
        only flag confident cross-domain mismatches."""
        if not tool_name:
            return frozenset()
        normalized = re.sub(r"[^a-z0-9]+", " ", tool_name.lower())
        words = set(normalized.split())
        # ``mcp`` is the literal MCP-server suffix and must never contribute
        # a domain signal on its own.
        words.discard("mcp")
        tags: set[str] = set()
        for domain, tokens in cls._DOMAIN_TOKENS.items():
            for token in tokens:
                if token in words:
                    tags.add(domain)
                    break
        return frozenset(tags)

    @staticmethod
    def _extract_discovery_keywords(
        user_message: str, failed_step: Dict[str, Any], unresolved_params: List[str]
    ) -> set[str]:
        """Infer broad resource keywords for selecting a missing lookup/discovery tool."""
        text = f"{user_message}\n{failed_step.get('action', '')}".lower()
        keywords = {"item", "resource"}

        if re.search(r"\.[a-z0-9]{1,8}\b", text):
            keywords.update({"file", "files", "folder", "document", "workbook", "excel"})

        for token in (
            "file",
            "files",
            "folder",
            "drive",
            "item",
            "workbook",
            "excel",
            "message",
            "mail",
            "chat",
            "thread",
            "task",
            "record",
            "site",
            "calendar",
            "contact",
            "document",
        ):
            if token in text:
                keywords.add(token)

        for unresolved_param in unresolved_params:
            lowered_param = unresolved_param.lower()
            if "driveitem" in lowered_param or "file" in lowered_param:
                keywords.update({"file", "files", "folder", "item"})
            elif "message" in lowered_param:
                keywords.update({"message", "mail", "chat", "thread"})
            elif "task" in lowered_param:
                keywords.update({"task", "tasks"})
            elif "site" in lowered_param:
                keywords.update({"site", "sites"})
            elif lowered_param.endswith("id"):
                keywords.add("item")

        return keywords

    def _build_auto_discovery_repair_plan(
        self,
        *,
        user_message: str,
        available_tools: List[Dict[str, Any]],
        failed_step: Dict[str, Any],
        unresolved_params: List[str],
        current_plan: Dict[str, Any],
        my_results: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Inject a deterministic lookup step when re-planning keeps missing a discovery hop."""
        current_tools = [step.get("tool_name", "") for step in current_plan.get("my_steps", [])]
        keywords = self._extract_discovery_keywords(user_message, failed_step, unresolved_params)
        best_candidate: Optional[Dict[str, Any]] = None

        # Extract failed tool's MCP server for affinity scoring
        failed_tool_name = failed_step.get("tool_name", "")
        failed_server_id = failed_tool_name.split("__", 1)[0] if "__" in failed_tool_name else None

        for tool in available_tools or []:
            tool_fn = tool.get("function", {})
            candidate_name = tool_fn.get("name", "")
            if not candidate_name or candidate_name == failed_step.get("tool_name"):
                continue
            if candidate_name in current_tools:
                continue

            name_lower = candidate_name.lower()
            description_lower = (tool_fn.get("description") or "").lower()
            score = 0
            if any(token in name_lower for token in ("search", "find", "lookup")):
                score += 5
            if "list" in name_lower:
                score += 4
            if "get" in name_lower:
                score += 1
            if "root" in name_lower:
                score -= 2
            if any(keyword in name_lower or keyword in description_lower for keyword in keywords):
                score += 3

            # Server affinity: strongly prefer tools from the same MCP server
            # as the failed tool.  A todo-helper tool should not be chosen to
            # discover IDs for a mail or calendar tool.
            if failed_server_id and "__" in candidate_name:
                candidate_server_id = candidate_name.split("__", 1)[0]
                if candidate_server_id == failed_server_id:
                    score += 4
                else:
                    score -= 3

            # Domain affinity: even within the same MCP server, a candidate
            # operating on an unrelated resource domain (e.g. mail folders
            # when repairing a drive call) must not be chosen.  This was the
            # v0.20260416.2 Excel bug -- ``list-mail-folders`` and
            # ``search-sharepoint-sites`` were picked to repair
            # ``get-drive-root-item`` because the scorer had no notion of
            # resource domain.  The penalty is large enough to drop the
            # candidate below the ``score <= 0`` cutoff when the only
            # positive signal is a verb match on the same server.
            failed_domains = self._get_tool_domain_tags(failed_tool_name)
            candidate_domains = self._get_tool_domain_tags(candidate_name)
            if failed_domains and candidate_domains:
                if failed_domains & candidate_domains:
                    score += 4
                else:
                    score -= 15

            if score <= 0:
                continue

            tool_schema = tool_fn.get("parameters", {}) or {}
            required_params = tool_schema.get("required", [])
            param_properties = tool_schema.get("properties", {})
            candidate_params = self._resolve_parameters_from_context(
                required_params=required_params,
                param_properties=param_properties,
                full_schema=tool_schema,
                tool_name=candidate_name,
                action_description=tool_fn.get("description", ""),
                user_request=user_message,
                my_results=my_results,
                runtime_context=self._get_active_skill_execution_context(),
            )
            # Inject MCP server default parameters for discovery candidates
            if "__" in candidate_name and self._mcp_service:
                disc_server_id = candidate_name.split("__", 1)[0]
                disc_mcp_defaults = self._mcp_service.server_configs.get(disc_server_id, {}).get(
                    "parameters", {}
                )
                if disc_mcp_defaults:
                    candidate_params = self._merge_parameter_candidates(
                        current_parameters=candidate_params,
                        candidate_parameters=disc_mcp_defaults,
                        param_properties=param_properties,
                        full_schema=tool_schema,
                    )
            filename_hint = self._extract_primary_filename_hint(
                user_message, failed_step.get("action", "")
            )
            if (
                filename_hint
                and isinstance(param_properties, dict)
                and "searchQuery" in param_properties
                and not candidate_params.get("searchQuery")
                and any(token in name_lower for token in ("list", "search", "find"))
            ):
                candidate_params["searchQuery"] = filename_hint
                score += 2

            lowered_unresolved_params = {param.lower() for param in unresolved_params}
            if "driveitemid" in lowered_unresolved_params and "folder" in name_lower:
                score += 6
            unresolved_candidate_params = self._get_unresolved_required_parameters(
                candidate_params,
                required_params,
                param_properties,
                tool_schema,
            )
            if unresolved_candidate_params:
                continue

            if best_candidate is None or score > best_candidate["score"]:
                best_candidate = {
                    "score": score,
                    "tool_name": candidate_name,
                    "parameters": candidate_params,
                }

        if not best_candidate:
            return None

        tool_name = best_candidate["tool_name"]
        tool_placeholder = tool_name.upper().replace("-", "_").replace(".", "_")
        inserted_step = {
            "action": (
                f"Discover {', '.join(unresolved_params)} needed for "
                f"{failed_step.get('action', failed_step.get('tool_name', 'the final action'))}"
            ),
            "tool_name": tool_name,
            "parameters": best_candidate["parameters"],
            "output_placeholder": f"{{{{AUTO_DISCOVERY_{tool_placeholder}}}}}",
        }

        repaired_plan = copy.deepcopy(current_plan)
        my_steps = repaired_plan.setdefault("my_steps", [])
        failed_index = next(
            (
                index
                for index, step in enumerate(my_steps)
                if step.get("tool_name") == failed_step.get("tool_name")
                and step.get("action") == failed_step.get("action")
            ),
            len(my_steps),
        )
        my_steps.insert(failed_index, inserted_step)

        if repaired_plan.get("steps"):
            repaired_plan["steps"].insert(
                failed_index,
                {
                    "action": inserted_step["action"],
                    "capability_needed": "lookup/discovery",
                    "tool_name": tool_name,
                    "can_i_do_this": True,
                    "data_needed": "existing tool results",
                    "output_placeholder": inserted_step["output_placeholder"],
                },
            )

        existing_flow = repaired_plan.get("data_flow", "").strip()
        repaired_plan["data_flow"] = (
            f"{existing_flow} Added {tool_name} to discover missing parameters."
            if existing_flow
            else f"Added {tool_name} to discover missing parameters before the final action."
        )

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "phase": "repair_plan_auto_discovery_added",
                "tool_name": failed_step.get("tool_name"),
                "inserted_tool": tool_name,
                "inserted_parameters": best_candidate["parameters"],
                "unresolved_params": unresolved_params,
            },
            description=f"Added deterministic discovery step {tool_name} during repair planning",
        )
        return repaired_plan

    async def _repair_execution_plan_for_missing_parameters(
        self,
        user_message: str,
        available_tools: List[Dict[str, Any]],
        allow_delegation: bool,
        failed_step: Dict[str, Any],
        tool_name: str,
        unresolved_params: List[str],
        current_plan: Dict[str, Any],
        my_results: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Attempt one repair-planning pass when execution discovers missing IDs."""
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.WARNING,
            data={
                "agent_id": self.agent_id,
                "phase": "repair_plan_start",
                "tool_name": tool_name,
                "unresolved_params": unresolved_params,
            },
            description=(
                f"Attempting repair plan for {tool_name} due to unresolved params "
                f"{unresolved_params}"
            ),
        )

        repaired_plan = await self._plan_before_execution(
            user_message,
            available_tools,
            allow_delegation=allow_delegation,
            replanning_feedback=self._build_missing_parameter_replanning_feedback(
                failed_step=failed_step,
                tool_name=tool_name,
                unresolved_params=unresolved_params,
                current_plan=current_plan,
                my_results=my_results,
            ),
            completed_results=my_results,
        )

        current_tools = [step.get("tool_name", "") for step in current_plan.get("my_steps", [])]
        repaired_tools = [step.get("tool_name", "") for step in repaired_plan.get("my_steps", [])]
        current_signature = self._normalize_repair_plan_signature(current_plan)
        repaired_signature = self._normalize_repair_plan_signature(repaired_plan)

        if repaired_signature == current_signature:
            auto_repaired_plan = self._build_auto_discovery_repair_plan(
                user_message=user_message,
                available_tools=available_tools,
                failed_step=failed_step,
                unresolved_params=unresolved_params,
                current_plan=current_plan,
                my_results=my_results,
            )
            if auto_repaired_plan is not None:
                return auto_repaired_plan

            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "phase": "repair_plan_no_change",
                    "tool_name": tool_name,
                    "unresolved_params": unresolved_params,
                    "current_tools": current_tools,
                },
                description="Repair planning produced no meaningful tool-chain change",
            )
            return None

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "phase": "repair_plan_completed",
                "tool_name": tool_name,
                "unresolved_params": unresolved_params,
                "repaired_tools": repaired_tools,
            },
            description=f"Repair planning updated tool chain for {tool_name}",
        )
        return repaired_plan

    async def _repair_execution_plan_for_validation_failure(
        self,
        user_message: str,
        available_tools: List[Dict[str, Any]],
        allow_delegation: bool,
        failed_step: Dict[str, Any],
        tool_name: str,
        validation_error: str,
        blocked_params: List[str],
        current_plan: Dict[str, Any],
        my_results: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Attempt one repair-planning pass when validation blocks execution."""
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.WARNING,
            data={
                "agent_id": self.agent_id,
                "phase": "repair_plan_start",
                "tool_name": tool_name,
                "reason": "validation_failed",
                "blocked_params": blocked_params,
                "validation_error": validation_error,
            },
            description=(
                f"Attempting repair plan for {tool_name} due to validation failure: "
                f"{validation_error}"
            ),
        )

        repaired_plan = await self._plan_before_execution(
            user_message,
            available_tools,
            allow_delegation=allow_delegation,
            replanning_feedback=self._build_validation_failure_replanning_feedback(
                failed_step=failed_step,
                tool_name=tool_name,
                validation_error=validation_error,
                blocked_params=blocked_params,
                current_plan=current_plan,
                my_results=my_results,
            ),
            completed_results=my_results,
        )

        current_tools = [step.get("tool_name", "") for step in current_plan.get("my_steps", [])]
        repaired_tools = [step.get("tool_name", "") for step in repaired_plan.get("my_steps", [])]
        current_signature = self._normalize_repair_plan_signature(current_plan)
        repaired_signature = self._normalize_repair_plan_signature(repaired_plan)

        if repaired_signature == current_signature:
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "phase": "repair_plan_no_change",
                    "tool_name": tool_name,
                    "reason": "validation_failed",
                    "blocked_params": blocked_params,
                    "validation_error": validation_error,
                    "current_tools": current_tools,
                },
                description="Repair planning produced no meaningful tool-chain change",
            )
            return None

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "phase": "repair_plan_completed",
                "tool_name": tool_name,
                "reason": "validation_failed",
                "blocked_params": blocked_params,
                "validation_error": validation_error,
                "repaired_tools": repaired_tools,
            },
            description=f"Repair planning updated tool chain for {tool_name}",
        )
        return repaired_plan

    async def _plan_before_execution(
        self,
        user_message: str,
        available_tools: Optional[List[Dict[str, Any]]] = None,
        allow_delegation: bool = True,
        replanning_feedback: Optional[str] = None,
        completed_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Force agent to plan before executing any tools.
        Returns a structured plan for multi-step requests.
        """
        # Emit streaming event for agent planning
        streaming.stream(
            "planning",
            "Planning approach to handle the user's request...",
            stage="agent_planning",
            agent_name=self.name,
            agent_id=getattr(self, "agent_id", None),
            message_preview=sanitize_message_preview(user_message),
            has_tools=bool(available_tools),
            tool_count=len(available_tools) if available_tools else 0,
        )

        # Log available tools for debugging
        tool_names = [t.get("function", {}).get("name", "") for t in (available_tools or [])]

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.INFO,  # Changed to INFO to always see it
            data={
                "agent_id": self.agent_id,
                "phase": "planning_start",
                "available_tools": tool_names,  # Show all tools, not just first 10
                "tool_count": len(tool_names),
            },
            description=f"Agent {self.agent_id} starting planning with {len(tool_names)} tools",
        )

        streaming.stream(
            "progress",
            "Creating plan...",
            stage="creating_plan",
            agent_name=self.agent_id,
            tool_count=len(tool_names),
            skip_rephrase=True,
        )

        # Build context for planning (user message + available resources)
        # NOTE: Instructions go in system message, user content stays here
        planning_prompt = f"Request: {user_message}"

        # Inject current date/time so the planner can resolve relative references
        # like "today", "tomorrow", "next week" into concrete dates. The live
        # conversation system message gets this at line ~1005, but the planner
        # runs a separate LLM call that never sees that injection.
        try:
            import time as _time
            from datetime import datetime as _dt

            _now = _dt.now()
            _tz_name = _dt.now().astimezone().tzname() or _time.tzname[0]
            _now_str = f"{_now.strftime('%A, %B %d, %Y %H:%M')} ({_tz_name})"
            planning_prompt += (
                f"\n\n## Current date/time:\nIt is now {_now_str}. "
                "Resolve relative references like 'today', 'tomorrow', 'next week' "
                "into concrete RFC3339 dates when building tool parameters."
            )
        except Exception:
            # Never let clock/timezone lookup break planning.
            pass

        agent_system_message = getattr(self, "system_message", None)
        if isinstance(agent_system_message, str) and agent_system_message.strip():
            planning_prompt += "\n\n## Agent operating instructions:\n"
            planning_prompt += agent_system_message.strip() + "\n"

        # Section 1: Available tools (agent's own MCP tools)
        planning_prompt += "\n\n## Available tools:\n"
        tool_lines = []
        for tool in available_tools or []:
            tool_fn = tool.get("function", {})
            tool_name = tool_fn.get("name", "")
            tool_description = " ".join((tool_fn.get("description") or "").split())
            tool_parameters = tool_fn.get("parameters", {})
            required_params = tool_parameters.get("required", [])
            if "." in tool_description:
                tool_description = tool_description.split(".", 1)[0].strip() + "."
            if len(tool_description) > 120:
                tool_description = tool_description[:117].rstrip() + "..."
            if required_params:
                required_summary = ", ".join(required_params[:4])
                if len(required_params) > 4:
                    required_summary += ", ..."
                tool_description = (
                    f"{tool_description} Required params: {required_summary}."
                    if tool_description
                    else f"Required params: {required_summary}."
                )

            if tool_description:
                tool_lines.append(f"- {tool_name}: {tool_description}")
            else:
                tool_lines.append(f"- {tool_name}")
        planning_prompt += "\n".join(tool_lines)

        if completed_results:
            planning_prompt += "\n\n## Existing tool results:\n"
            for placeholder, result in completed_results.items():
                planning_prompt += (
                    f"- {placeholder}: {self._summarize_planning_result(result, user_message)}\n"
                )

        if replanning_feedback:
            planning_prompt += "\n\n## Replanning feedback:\n"
            planning_prompt += replanning_feedback.strip() + "\n"

        # Section 2: Built-in agents (internal agents in same formation)
        internal_agents = []
        external_agents = []
        if allow_delegation:
            try:
                available_agents = await self.overlord.a2a_coordinator.get_all_available_agents(
                    self.agent_id, include_external=True
                )
            except Exception as e:
                # Log but don't fail planning
                observability.observe(
                    event_type=observability.ErrorEvents.A2A_MESSAGE_HANDLING_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                        "phase": "planning_agent_discovery",
                    },
                    description=f"Failed to get available agents for planning: {str(e)}",
                )
                available_agents = {}

            for agent_id, agent_info in available_agents.items():
                if agent_info.get("type", "internal") == "internal":
                    internal_agents.append((agent_id, agent_info))
                else:
                    external_agents.append((agent_id, agent_info))

            if internal_agents:
                planning_prompt += "\n\n---\n\n## Built-in agents:\n"
                for agent_id, agent_info in internal_agents:
                    planning_prompt += f"\n### {agent_id}\n"
                    planning_prompt += f"{agent_info.get('description', 'No description')}\n\n"

                    capabilities = agent_info.get("capabilities", [])
                    if capabilities:
                        planning_prompt += "Capabilities:\n"
                        for cap in capabilities:
                            planning_prompt += f"- {cap}\n"
                    else:
                        planning_prompt += "Capabilities: None specified\n"
                    planning_prompt += "\n"

            # Section 3: Remote agents (only if external agents exist)
            if external_agents:
                planning_prompt += "---\n\n## Remote agents:\n"

                for agent_id, agent_info in external_agents:
                    planning_prompt += f"\n### {agent_id}\n"
                    planning_prompt += f"{agent_info.get('description', 'No description')}\n"
                    planning_prompt += f"Formation: {agent_info.get('formation', 'unknown')}\n\n"

                    capabilities = agent_info.get("capabilities", [])
                    if capabilities:
                        planning_prompt += "Capabilities:\n"
                        for cap in capabilities:
                            planning_prompt += f"- {cap}\n"
                    else:
                        planning_prompt += "Capabilities: None specified\n"
                    planning_prompt += "\n"

                planning_prompt += "---\n"

            # Add explicit warning when no other agents are available for delegation
            if not internal_agents and not external_agents:
                planning_prompt += "\n⚠️ CRITICAL: You are the ONLY agent in this formation!\n"
                planning_prompt += "You MUST handle all requests yourself without delegation.\n"
                planning_prompt += "Even if you lack specific tools or capabilities, provide your best effort response.\n\n"
        else:
            planning_prompt += "\n\n## Delegation policy:\n"
            planning_prompt += (
                "Delegation is disabled for this request. Use your own tools if needed, "
                "but do NOT ask another agent to handle any part of it.\n"
            )

        # Section 4: Available skills (injected into planning context)
        if (
            self.overlord
            and hasattr(self.overlord, "skill_manager")
            and self.overlord.skill_manager
        ):
            available_skill_names = self.overlord.skill_manager.get_available_skills(self.agent_id)
            if available_skill_names:
                planning_prompt += "\n\n---\n\n## Available skills:\n"
                planning_prompt += (
                    "Skills provide specialized instructions for specific tasks. "
                    "BEFORE working on a task that matches a skill, you MUST first call "
                    "the activate_skill tool with the skill name. This loads detailed "
                    "instructions into your context. Do NOT skip this step.\n\n"
                )
                for skill_name in available_skill_names:
                    skill = self.overlord.skill_manager.skills.get(skill_name)
                    if skill:
                        resources = self.overlord.skill_manager._get_resources(skill_name)
                        scripts = [r for r in resources if r.startswith("scripts/")]
                        # Don't show scripts for file-generation (uses generate_file tool instead)
                        is_builtin_fg = skill_name == "file-generation"
                        if is_builtin_fg:
                            planning_prompt += (
                                f"- **{skill.name}**: {skill.description} "
                                f"(use the generate_file tool for this, NOT run_skill)\n"
                            )
                        else:
                            script_note = f" (scripts: {', '.join(scripts)})" if scripts else ""
                            planning_prompt += (
                                f"- **{skill.name}**: {skill.description}{script_note}\n"
                            )

                # Add note about run_skill if RCE is available
                has_rce = hasattr(self.overlord, "rce_client") and self.overlord.rce_client
                has_executable = any(
                    self.overlord.skill_manager.has_scripts(n) for n in available_skill_names
                )
                if has_rce and has_executable:
                    planning_prompt += (
                        "\nSkills with scripts can be executed using the run_skill tool. "
                        "Use activate_skill first to load instructions, then run_skill "
                        "to execute the script. The command parameter must invoke one of "
                        "the skill's scripts; raw code in command WILL BE REJECTED. "
                        "Deliver code or data files via the input_files parameter.\n"
                    )
                    if "compute" in available_skill_names:
                        planning_prompt += (
                            "Example run_skill parameters for the compute skill: "
                            '{"skill_name": "compute", "command": '
                            '"python3 scripts/run_python.py main.py", "input_files": '
                            '{"main.py": "<complete python source>"}}\n'
                        )
                planning_prompt += "\n"

        from ..prompts.loader import PromptLoader

        try:
            planning_prompt += PromptLoader.get("agent_planning.md")
        except KeyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.PLANNING_TEMPLATE_MISSING,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "template_file": "agent_planning.md",
                    "error": str(e),
                },
                description="Planning template file not found: agent_planning.md",
            )
            # Raise exception to prevent silent failure
            raise FileNotFoundError(
                "Required planning template file is missing: agent_planning.md. "
                "This file is essential for the planning system to function properly."
            ) from e

        try:
            # Create messages for planning
            # System message contains instructions, user message contains the request + context
            planning_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a planning assistant. Analyze the user's request and "
                        "create a structured execution plan using the available tools and agents. "
                        "Treat explicit [Context: ...] values and agent operating instructions as "
                        "already-resolved facts that should shape the plan. "
                        "Always respond with valid JSON only."
                    ),
                },
                {"role": "user", "content": planning_prompt},
            ]

            # Get plan from LLM — use explicit max_tokens so multi-step plans
            # with many tools are not truncated by the provider's default cap.
            plan_response = await self.model.chat(
                planning_messages,
                temperature=0.1,  # Low temperature for structured output
                max_tokens=16384,
            )

            # Check cancellation after LLM call returns
            from ..background.cancellation import check_cancellation_from_context

            if self.overlord and hasattr(self.overlord, "request_tracker"):
                await check_cancellation_from_context(self.overlord.request_tracker)

            # Extract content from response
            if hasattr(plan_response, "content"):
                plan_content = plan_response.content
            elif hasattr(plan_response, "text"):
                plan_content = plan_response.text
            else:
                plan_content = str(plan_response)

            # Parse JSON response
            import json

            # Log raw response for debugging
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.INFO,  # Changed to INFO to always see it
                data={
                    "agent_id": self.agent_id,
                    "phase": "raw_response",
                    "raw_plan": plan_content[:1000] if len(plan_content) > 1000 else plan_content,
                },
                description="Raw planning response from LLM",
            )

            # Extract JSON from planning response — models may wrap the JSON
            # in markdown code fences or precede it with prose explanation.
            stripped = plan_content.strip()

            # Try 1: direct JSON parse
            plan = None
            try:
                plan = json.loads(stripped)
            except json.JSONDecodeError:
                pass

            # Try 2: extract from ```json ... ``` code fence (anywhere in response)
            if plan is None and "```" in stripped:
                import re

                fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
                if fence_match:
                    try:
                        plan = json.loads(fence_match.group(1))
                    except json.JSONDecodeError:
                        pass

            # Try 3: find the outermost { ... } containing "steps"
            if plan is None:
                brace_starts = [i for i, c in enumerate(stripped) if c == "{"]
                for start in brace_starts:
                    depth = 0
                    for i in range(start, len(stripped)):
                        if stripped[i] == "{":
                            depth += 1
                        elif stripped[i] == "}":
                            depth -= 1
                            if depth == 0:
                                candidate = stripped[start : i + 1]
                                try:
                                    obj = json.loads(candidate)
                                    if isinstance(obj, dict) and "steps" in obj:
                                        plan = obj
                                except json.JSONDecodeError:
                                    pass
                                break
                    if plan is not None:
                        break

            if plan is None:
                raise ValueError(
                    f"Could not extract valid JSON plan from LLM response "
                    f"({len(stripped)} chars)"
                )

            available_tool_names = {
                t.get("function", {}).get("name", "") for t in (available_tools or [])
            }
            plan = self._finalize_execution_plan(
                plan, available_tool_names, allow_delegation=allow_delegation
            )

            # Log the plan
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "request": (
                        user_message[:100] + "..." if len(user_message) > 100 else user_message
                    ),
                    "plan": plan,
                    "can_do_steps": len(plan.get("my_steps", [])),
                    "need_help_steps": len(plan.get("delegate_steps", [])),
                },
                description=f"Agent {self.agent_id} created execution plan",
            )

            return plan

        except Exception as e:
            # If planning fails, return a simple plan
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"agent_id": self.agent_id, "error": str(e), "phase": "execution_planning"},
                description=f"Failed to create execution plan: {str(e)}",
            )

            # Return a default plan that attempts direct execution
            if allow_delegation:
                return {
                    "steps": [{"action": user_message, "can_i_do_this": False}],
                    "my_steps": [],
                    "delegate_steps": [
                        {
                            "action": user_message,
                            "capability_needed": "unknown",
                            "delegation_prompt": user_message,
                        }
                    ],
                    "data_flow": "Direct delegation due to planning failure",
                }

            return {
                "steps": [{"action": user_message, "can_i_do_this": False}],
                "my_steps": [],
                "delegate_steps": [],
                "data_flow": "Planning failed; continue with normal tool flow",
            }

    def _finalize_execution_plan(
        self, plan: Dict[str, Any], available_tool_names: set[str], allow_delegation: bool = True
    ) -> Dict[str, Any]:
        """Normalize plan ownership between local tool steps and delegated steps."""
        # Fix any incorrect tool claims.
        for step in plan.get("steps", []):
            tool_name = step.get("tool_name", "")
            if tool_name and tool_name in available_tool_names:
                step["can_i_do_this"] = True
            elif tool_name and tool_name not in available_tool_names:
                step["can_i_do_this"] = False

        # Preserve parameters from the LLM's original my_steps block by matching
        # on tool_name.  The planning prompt only instructs the LLM to emit
        # "parameters" inside my_steps, NOT inside steps — so rebuilding my_steps
        # from steps alone would silently drop every parameter and send empty
        # argument objects to downstream tools.  A FIFO queue keyed by tool_name
        # handles plans where the same tool appears in multiple steps.
        llm_my_steps = plan.get("my_steps", []) or []
        params_by_tool: Dict[str, List[Dict[str, Any]]] = {}
        placeholders_by_tool: Dict[str, List[str]] = {}
        for llm_step in llm_my_steps:
            if not isinstance(llm_step, dict):
                continue
            tool = llm_step.get("tool_name", "")
            params = llm_step.get("parameters")
            if tool and isinstance(params, dict):
                params_by_tool.setdefault(tool, []).append(params)
            placeholder = llm_step.get("output_placeholder")
            if tool and isinstance(placeholder, str) and placeholder.strip():
                placeholders_by_tool.setdefault(tool, []).append(placeholder)

        def _pop_params(tool: str) -> Dict[str, Any]:
            queue = params_by_tool.get(tool)
            return queue.pop(0) if queue else {}

        def _pop_placeholder(tool: str) -> Optional[str]:
            queue = placeholders_by_tool.get(tool)
            return queue.pop(0) if queue else None

        # Some LLMs (notably Haiku on tight prompts) interpret the
        # "ALL steps MUST go in my_steps" instruction literally and emit
        # ``"steps": []`` while populating ``my_steps`` with the actual
        # actions. The default rebuild loop below iterates ``plan["steps"]``,
        # so when ``steps`` is empty the rebuilt list comes back empty too
        # and we'd silently overwrite the LLM's real actions with ``[]``
        # — agent then generates a narrative response pretending the work
        # happened. Detect that case up-front and treat ``my_steps`` as
        # canonical: the same tool-availability filter still applies, and
        # we keep parameters/placeholders verbatim.
        canonical_steps = plan.get("steps") or []
        my_steps_is_authoritative = not canonical_steps and any(
            isinstance(s, dict) and s.get("tool_name") for s in llm_my_steps
        )

        if my_steps_is_authoritative:
            rebuilt_my_steps: List[Dict[str, Any]] = []
            for step in llm_my_steps:
                if not isinstance(step, dict):
                    continue
                tool_name = step.get("tool_name", "")
                if not tool_name or tool_name not in available_tool_names:
                    # Drop unknown tools rather than letting them reach the
                    # executor where they'd error out as "tool not found".
                    continue
                params = step.get("parameters")
                if not isinstance(params, dict):
                    params = {}
                placeholder = step.get("output_placeholder") or (f"{{{tool_name.upper()}_OUTPUT}}")
                rebuilt_my_steps.append(
                    {
                        "action": step.get("action", ""),
                        "tool_name": tool_name,
                        "parameters": params,
                        "output_placeholder": placeholder,
                    }
                )
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.WARNING,
                data={
                    # ``agent_id`` may be absent when this finalizer is exercised
                    # directly from unit tests via ``object.__new__(Agent)``; the
                    # observability event is best-effort, so don't crash on it.
                    "agent_id": getattr(self, "agent_id", "<unknown>"),
                    "phase": "my_steps_authoritative",
                    "llm_my_steps_count": len(llm_my_steps),
                    "rebuilt_count": len(rebuilt_my_steps),
                    "rebuilt_tools": [s["tool_name"] for s in rebuilt_my_steps],
                },
                description=(
                    "Plan emitted empty 'steps' but populated 'my_steps'; "
                    "treating my_steps as canonical to preserve the LLM's "
                    "actions."
                ),
            )
        else:
            rebuilt_my_steps = []
            for step in canonical_steps:
                if not step.get("can_i_do_this"):
                    continue
                tool_name = step.get("tool_name", "")
                if tool_name not in available_tool_names:
                    continue
                # Prefer parameters already present on the unified step (rare),
                # then fall back to the LLM's my_steps entry for this tool.
                step_params = step.get("parameters")
                parameters = (
                    step_params
                    if isinstance(step_params, dict) and step_params
                    else _pop_params(tool_name)
                )
                placeholder = step.get("output_placeholder") or _pop_placeholder(tool_name)
                if not placeholder:
                    placeholder = f"{{{tool_name.upper()}_OUTPUT}}"
                rebuilt_my_steps.append(
                    {
                        "action": step["action"],
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "output_placeholder": placeholder,
                    }
                )

        plan["my_steps"] = rebuilt_my_steps

        if allow_delegation:
            plan["delegate_steps"] = [
                {
                    "action": step["action"],
                    "capability_needed": step.get("capability_needed", ""),
                    "delegation_prompt": step.get("delegation_prompt", step["action"]),
                }
                for step in plan.get("steps", [])
                if not step.get("can_i_do_this")
                or step.get("tool_name") not in available_tool_names
            ]
        else:
            plan["delegate_steps"] = []

        return plan

    async def send_a2a_message(
        self,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        wait_for_response: bool = True,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """Send A2A message using unified transport."""
        # Discover the target agent to get its URL
        available_agents = self.overlord.a2a_coordinator.get_available_agents_for_a2a(self.agent_id)

        if target_agent_id not in available_agents:
            # Try external agents as well
            all_agents = await self.overlord.a2a_coordinator.get_all_available_agents(
                self.agent_id, include_external=True
            )
            if target_agent_id in all_agents:
                available_agents[target_agent_id] = all_agents[target_agent_id]
            else:
                raise ValueError(
                    f"Agent {target_agent_id} not found in formation or external registry"
                )

        # Use unified messaging with URL
        return await self.overlord.send_a2a_message(
            source_agent_id=self.agent_id,
            target_agent_info=available_agents[target_agent_id],
            message=message,
            message_type=message_type,
            context=context,
            wait_for_response=wait_for_response,
            timeout=timeout,
        )

    async def handle_a2a_message(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Handle incoming A2A message and execute the requested task."""
        try:
            # Extract the task from the message
            task_content = ""
            if isinstance(message, dict):
                # Check if this is an A2A protocol message with parts
                if "parts" in message:
                    # Extract only the text content from TextPart, ignore DataPart metadata
                    text_parts = []
                    for part in message.get("parts", []):
                        if isinstance(part, dict) and part.get("type") == "TextPart":
                            text_parts.append(part.get("text", ""))
                    task_content = " ".join(text_parts).strip()

                    # If no text parts found, fall back to looking for task/content
                    if not task_content:
                        task_content = message.get("task", message.get("content", str(message)))
                else:
                    task_content = message.get("task", message.get("content", str(message)))
            else:
                task_content = str(message)

            # Log the incoming A2A message
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_A2A_MESSAGE_RECEIVED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "source_agent_id": source_agent_id,
                    "message_type": message_type,
                    "has_context": context is not None,
                },
                description=f"Agent {self.agent_id} received A2A message from {source_agent_id}",
            )

            # Process the task as a regular user message
            # This will trigger tool usage if needed
            # Pass is_a2a_task=True to bypass planning and execute directly
            response = await self.process_message(
                message=task_content,
                user_id=f"agent_{source_agent_id}",
                session_id=message_id or "a2a_session",
                request_id=message_id,
                is_a2a_task=True,  # This should bypass planning for delegated tasks
            )

            # Get the response content
            if hasattr(response, "content"):
                result_text = response.content
            else:
                result_text = str(response)

            return {
                "status": "success",
                "response": result_text,
                "agent_id": self.agent_id,
                "executed": True,
            }

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.A2A_MESSAGE_HANDLING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "error": str(e),
                    "source_agent_id": source_agent_id,
                },
                description=f"Failed to handle A2A message: {e}",
            )

            return {"status": "error", "error": str(e), "agent_id": self.agent_id}

    async def _handle_consultation_request(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle consultation request from another agent."""
        try:
            # Extract consultation details
            if isinstance(message, dict):
                topic = message.get("topic", "")
                question = message.get("question", "")
                details = message.get("details", {})
            else:
                topic = context.get("topic", "consultation")
                question = str(message)
                details = {}

            # Process the consultation using the agent's model
            consultation_prompt = f"""
            Agent {source_agent_id} is requesting consultation on: {topic}

            Question: {question}

            Additional context: {details}

            Please provide expert advice based on your knowledge and capabilities.
            """

            # Use the agent's model to generate consultation response
            consultation_messages = [
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": consultation_prompt},
            ]

            response = await self.model.chat(consultation_messages)

            # Extract content from response
            if isinstance(response, str):
                advice = response
            elif hasattr(response, "choices") and response.choices:
                advice = response.choices[0].message.content
            else:
                advice = str(response)

            return {
                "status": "success",
                "advice": advice,
                "topic": topic,
                "consultant_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "consultant_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

    async def _handle_information_sharing(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> None:
        """Handle information sharing from another agent."""
        try:
            # Extract shared information
            if isinstance(message, dict):
                information = message.get("information", "")
                topic = message.get("topic", "general")
                relevance = message.get("relevance_reason", "")
            else:
                information = str(message)
                topic = context.get("topic", "general")
                relevance = context.get("relevance_reason", "")

            # Store the shared information in memory via overlord
            if self.overlord and hasattr(self.overlord, "add_message_to_memory"):
                shared_content = (
                    f"Information shared by {source_agent_id} on {topic}: {information}"
                )
                if relevance:
                    shared_content += f" (Relevance: {relevance})"

                await self.overlord.add_message_to_memory(
                    content=shared_content,
                    role="system",
                    timestamp=datetime.datetime.now().timestamp(),
                    agent_id=self.agent_id,
                    metadata={
                        "source": "a2a_information_sharing",
                        "source_agent_id": source_agent_id,
                        "topic": topic,
                        "message_id": message_id,
                    },
                )

            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_PROCESSED,
                level=observability.EventLevel.INFO,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "topic": topic,
                    "action": "information_stored",
                },
                description=f"Stored shared information from {source_agent_id}",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "action": "information_sharing",
                },
                description=f"Failed to handle information sharing: {str(e)}",
            )

    async def _handle_peer_coordination(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle peer coordination request."""
        try:
            # Extract coordination details
            if isinstance(message, dict):
                coordination_type = message.get("coordination_type", "general")
                details = message.get("details", {})
            else:
                coordination_type = context.get("coordination_type", "general")
                details = {"message": str(message)}

            # Handle different coordination types
            if coordination_type == "task_handoff":
                result = await self._handle_task_handoff(source_agent_id, details)
            elif coordination_type == "synchronization":
                result = await self._handle_synchronization(source_agent_id, details)
            elif coordination_type == "parallel_coordination":
                result = await self._handle_parallel_coordination(source_agent_id, details)
            else:
                result = f"Acknowledged {coordination_type} coordination from {source_agent_id}"

            return {
                "status": "success",
                "result": result,
                "coordination_type": coordination_type,
                "coordinator_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "coordination_type": coordination_type,
                "coordinator_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

    async def _handle_task_handoff(self, source_agent_id: str, details: Dict[str, Any]) -> str:
        """Handle task handoff coordination."""
        task = details.get("task", "unknown task")
        status = details.get("status", "unknown")

        # Log the handoff
        observability.observe(
            event_type=observability.ConversationEvents.A2A_TASK_HANDOFF,
            level=observability.EventLevel.INFO,
            data={
                "source_agent_id": source_agent_id,
                "target_agent_id": self.agent_id,
                "task": task,
                "status": status,
            },
            description=f"Task handoff: {task} from {source_agent_id}",
        )

        return f"Received task handoff: {task} (status: {status})"

    async def _handle_synchronization(self, source_agent_id: str, details: Dict[str, Any]) -> str:
        """Handle synchronization coordination."""
        sync_point = details.get("sync_point", "unknown")
        return f"Synchronized at {sync_point} with {source_agent_id}"

    async def _handle_parallel_coordination(
        self, source_agent_id: str, details: Dict[str, Any]
    ) -> str:
        """Handle parallel coordination."""
        task_part = details.get("task_part", "unknown")
        return f"Coordinating parallel task: {task_part} with {source_agent_id}"

    async def _handle_generic_a2a_message(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]],
        message_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Handle generic A2A message."""
        try:
            # Check if this is a task execution request
            execution_required = False
            task_text = None

            # Parse A2A protocol message structure
            if isinstance(message, dict):
                # Check for A2A protocol format with parts
                if "parts" in message and isinstance(message["parts"], list):
                    # Extract task from TextPart
                    for part in message["parts"]:
                        if isinstance(part, dict):
                            if part.get("type") == "TextPart" and "text" in part:
                                task_text = part["text"]
                            elif part.get("type") == "DataPart" and "data" in part:
                                data = part["data"]
                                if isinstance(data, dict):
                                    execution_required = data.get("execution_required", False)
                                    # If no task_text yet, try to get it from data
                                    if not task_text:
                                        task_text = data.get("original_request", "")

                # Fallback to direct message content
                if not task_text and "message" in message:
                    task_text = message["message"]
                elif not task_text and "text" in message:
                    task_text = message["text"]
            else:
                # Simple string message
                task_text = str(message)

            # If execution is required and we have a task, execute it
            if execution_required and task_text:
                observability.observe(
                    event_type=observability.ConversationEvents.A2A_MESSAGE_RECEIVED,
                    level=observability.EventLevel.INFO,
                    data={
                        "source_agent_id": source_agent_id,
                        "target_agent_id": self.agent_id,
                        "message_id": message_id,
                        "action": "executing_task",
                        "task": task_text[:100],  # First 100 chars
                    },
                    description=f"Executing task from {source_agent_id}: {task_text[:50]}...",
                )

                # Execute the task using the agent's normal message processing
                # This will use the agent's tools and capabilities
                response = await self.process_message(
                    message=task_text,
                    user_id=f"a2a_{source_agent_id}",
                    session_id=message_id or f"a2a_session_{generate_nanoid()}",
                    request_id=message_id,
                    is_a2a_task=True,  # Mark as A2A task to prevent loops
                )

                # Extract the response content
                response_content = self._content_to_text(response.content)

                return {
                    "status": "success",
                    "response": response_content,
                    "execution_completed": True,
                    "responder_id": self.agent_id,
                    "message_id": message_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                }

            # Otherwise, fall back to consultation/acknowledgment mode
            # Extract only text content from message (exclude internal metadata)
            if isinstance(message, dict):
                # Extract only TextPart content, excluding DataPart metadata
                if "parts" in message and isinstance(message["parts"], list):
                    text_parts = []
                    for part in message["parts"]:
                        if isinstance(part, dict) and part.get("type") == "TextPart":
                            text_parts.append(part.get("text", ""))
                    message_content = " ".join(text_parts).strip()
                    # Fallback if no text parts found
                    if not message_content:
                        message_content = str(
                            message.get("task", message.get("content", str(message)))
                        )
                else:
                    # Simple message without parts structure
                    message_content = str(message.get("task", message.get("content", str(message))))
            else:
                message_content = str(message)

            # Create a prompt for the agent to handle the message
            prompt = f"""
            You received a {message_type} message from agent {source_agent_id}.

            Message content:
            {message_content}

            Context: {context or {}}

            Please provide an appropriate response or acknowledgment.
            """

            # Process with the agent's model
            response_messages = [
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": prompt},
            ]

            model_response = await self.model.chat(response_messages)

            # Extract content
            acknowledgment_response: str
            if isinstance(model_response, str):
                acknowledgment_response = model_response
            elif hasattr(model_response, "choices") and model_response.choices:
                acknowledgment_response = str(model_response.choices[0].message.content or "")
            else:
                acknowledgment_response = str(model_response)

            # Return response for request-type messages
            if message_type in ["request", "query", "consultation"]:
                return {
                    "status": "success",
                    "response": acknowledgment_response,
                    "execution_completed": False,  # Not a task execution
                    "responder_id": self.agent_id,
                    "message_id": message_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                }

            # For notifications, just log and return None
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_RECEIVED,
                level=observability.EventLevel.INFO,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "message_type": message_type,
                    "action": "acknowledged",
                },
                description=f"Processed {message_type} from {source_agent_id}",
            )

            return None

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "message_type": message_type,
                },
                description=f"Failed to process {message_type}: {str(e)}",
            )
            raise

    # A2A Convenience Methods

    async def request_consultation(
        self,
        target_agent_id: str,
        topic: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Request consultation from another agent.

        Args:
            target_agent_id: ID of the agent to consult.
            topic: Topic for consultation.
            context: Optional additional context.
            timeout: Timeout for the request.

        Returns:
            Consultation response from the target agent.
        """
        message = {
            "topic": topic,
            "question": f"I need consultation on: {topic}",
            "details": context or {},
        }

        return await self.send_a2a_message(
            target_agent_id=target_agent_id,
            message=message,
            message_type="consultation",
            context=context,
            wait_for_response=True,
            timeout=timeout,
        )

    async def share_information(
        self,
        target_agent_id: str,
        information: Union[str, Dict[str, Any]],
        topic: str,
        relevance_reason: Optional[str] = None,
    ) -> bool:
        """
        Share information with another agent.

        Args:
            target_agent_id: ID of the target agent.
            information: Information to share.
            topic: Topic of the information.
            relevance_reason: Optional reason why this information is relevant.

        Returns:
            True if information was shared successfully.
        """
        message = {"information": information, "topic": topic, "relevance_reason": relevance_reason}

        try:
            await self.send_a2a_message(
                target_agent_id=target_agent_id,
                message=message,
                message_type="information_sharing",
                context={"topic": topic},
                wait_for_response=False,
            )
            return True
        except Exception:
            return False

    async def register_expertise(
        self, expertise_areas: List[str], proficiency_levels: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Register expertise areas with the overlord for capability discovery.

        Args:
            expertise_areas: List of expertise areas.
            proficiency_levels: Optional proficiency levels for each area.

        Returns:
            True if registration was successful.
        """
        try:
            if self.overlord and hasattr(self.overlord, "register_agent_expertise"):
                await self.overlord.register_agent_expertise(
                    agent_id=self.agent_id,
                    expertise_areas=expertise_areas,
                    proficiency_levels=proficiency_levels or {},
                )
                return True
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.AGENT_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "expertise_areas": expertise_areas,
                    "error": str(e),
                },
                description=f"Failed to register expertise: {str(e)}",
            )
        return False

    async def find_expert(
        self, topic: str, min_proficiency: str = "intermediate"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Find agents with expertise in a specific topic.

        Args:
            topic: Topic to find experts for.
            min_proficiency: Minimum proficiency level required.

        Returns:
            Dictionary of agent_id -> expertise_info for matching experts.
        """
        if self.overlord and hasattr(self.overlord, "find_experts"):
            return await self.overlord.find_experts(topic, min_proficiency)
        return {}

    async def coordinate_with_peer(
        self, peer_agent_id: str, coordination_type: str, details: Dict[str, Any], timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Coordinate with a peer agent.

        Args:
            peer_agent_id: ID of the peer agent.
            coordination_type: Type of coordination (task_handoff, synchronization, etc.).
            details: Coordination details.
            timeout: Timeout for the coordination.

        Returns:
            Coordination response from the peer agent.
        """
        message = {"coordination_type": coordination_type, "details": details}

        return await self.send_a2a_message(
            target_agent_id=peer_agent_id,
            message=message,
            message_type="peer_coordination",
            context={"coordination_type": coordination_type},
            wait_for_response=True,
            timeout=timeout,
        )

    @staticmethod
    def _is_placeholder_like_value(value: Any) -> bool:
        """Return True when a value looks like an unresolved placeholder token."""
        if not isinstance(value, str):
            return False

        stripped = value.strip()
        if not stripped:
            return False

        # GUIDs in braces ({8-4-4-4-12} hex) are real values, not placeholders.
        if re.match(
            r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
            r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$",
            stripped,
        ):
            return False

        placeholder_patterns = (
            r"^\{\{[^{}]+\}\}$",
            r"^\$\{\{[^{}]+\}\}$",
            r"^<<[^<>]+>>$",
            r"^\{[A-Z0-9][A-Z0-9_.:\-]*\}$",
        )
        return any(re.match(pattern, stripped) for pattern in placeholder_patterns)

    # Non-anchored scan for ``{{...}}`` tokens embedded inside larger strings
    # (e.g. ``"{{DRAFT.body}}\n\nHappy Birthday!"``). Kept separate from
    # ``_is_placeholder_like_value`` which intentionally requires the whole
    # value to be a placeholder for the schema-aware substitution path. Used
    # by the embedded-substitution helpers and the unresolved-leaf detector
    # so partially-resolved strings still flow through the correct logging /
    # drop path.
    _EMBEDDED_PLACEHOLDER_SCAN = re.compile(r"\{\{\s*[A-Za-z0-9_\-\[\]='\"\.\s]+?\s*\}\}")

    @staticmethod
    def _contains_embedded_placeholder(value: Any) -> bool:
        """Return True when ``value`` is a string containing at least one
        ``{{...}}`` token, regardless of whether the whole value is a
        placeholder. Does not fire on pure placeholder values handled by
        :meth:`_is_placeholder_like_value` — callers check that first.
        """
        if not isinstance(value, str) or not value.strip():
            return False
        return bool(Agent._EMBEDDED_PLACEHOLDER_SCAN.search(value))

    def _substitute_embedded_placeholders(
        self,
        text: str,
        successful_results: Dict[str, Any],
    ) -> str:
        """Replace every resolvable ``{{...}}`` token inside ``text`` in place.

        Each token is resolved through the same pipeline as full-string
        placeholders (``_parse_placeholder_reference`` → predicate/field
        extraction), but the resolved value is stringified and spliced
        back into ``text``. Tokens we cannot resolve are left intact so
        :meth:`_find_unresolved_placeholder_leaves` can still flag them
        for the leftover-strip pass.

        Non-scalar resolved values are serialized with ``str()`` so MCP
        receives a deterministic string rather than a Python repr. This is
        deliberate: the LLM emitted the token inside a string context, so
        downstream consumers expect a string substitution.
        """
        if not text or not isinstance(text, str):
            return text
        if not successful_results:
            return text

        def _replace(match: re.Match) -> str:
            token = match.group(0)
            placeholder_key = token.strip()
            referenced_result = successful_results.get(placeholder_key)
            field_hint: Optional[str] = None
            predicate: Optional[Dict[str, Any]] = None
            if referenced_result is None:
                base_key, field_hint, predicate = self._parse_placeholder_reference(placeholder_key)
                if base_key != placeholder_key:
                    referenced_result = successful_results.get(base_key)
            if referenced_result is None:
                return token

            payload = self._extract_structured_planning_result_payload(referenced_result)
            if field_hint or predicate:
                resolved = self._extract_field_from_result_payload(
                    payload, field_hint, predicate=predicate
                )
            elif isinstance(payload, (str, int, float, bool)):
                resolved = payload
            else:
                # Bare ``{{FOO}}`` inside a larger string + non-scalar
                # payload: we cannot sensibly splice a dict/list into
                # free text. Leave the token intact so the unresolved
                # leaf detector flags it.
                return token

            if resolved is None:
                return token
            if isinstance(resolved, (list, dict)):
                # Same reasoning — structured values shouldn't be coerced
                # into free text without caller intent. Leave untouched.
                return token
            return str(resolved)

        return Agent._EMBEDDED_PLACEHOLDER_SCAN.sub(_replace, text)

    # LLM-invented sentinel strings indicating "the runtime should inject this
    # value later" rather than an actual resolved value.  We must treat these
    # as unresolved so that MCP server defaults, context resolution, or
    # parameter inference can overwrite them.  Matching is case-insensitive
    # and anchored to the entire stripped value.
    _SENTINEL_PLACEHOLDER_PATTERN = re.compile(
        r"^("
        r"auto[-_]injected|auto[-_]fill(?:ed)?|auto[-_]resolve(?:d)?|"
        r"from[-_]server|from[-_]context|from[-_]credentials?|"
        r"server[-_]default|runtime[-_]injected|injected[-_]by[-_]server|"
        r"to[-_]be[-_](injected|provided|resolved|filled)|"
        r"will[-_]be[-_](injected|provided)|"
        r"<[^<>]+>"
        r")$",
        re.IGNORECASE,
    )

    @staticmethod
    def _is_sentinel_placeholder_value(value: Any) -> bool:
        """Return True when a value looks like an LLM-invented 'inject this later'
        sentinel.  These strings must not override real values from server
        defaults, context, or inference."""
        if not isinstance(value, str):
            return False
        stripped = value.strip()
        if not stripped:
            return False
        return bool(Agent._SENTINEL_PLACEHOLDER_PATTERN.match(stripped))

    @staticmethod
    def _is_nonempty_parameter_candidate(value: Any) -> bool:
        """Return True when a value is plausibly usable as a resolved parameter."""
        if value is None:
            return False
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return False
            if Agent._is_placeholder_like_value(stripped):
                return False
            if Agent._is_sentinel_placeholder_value(stripped):
                return False
            return True
        if isinstance(value, (list, dict)):
            return bool(value)
        return True

    @staticmethod
    def _extract_explicit_parameter_values_from_text(
        text: str, required_params: List[str]
    ) -> Dict[str, Any]:
        """Extract explicit `param = value` mentions from user/context text."""
        if not isinstance(text, str) or not text.strip():
            return {}

        resolved: Dict[str, Any] = {}
        for required_param in required_params:
            # Build alternative forms: camelCase <-> snake_case
            param_forms = {required_param}
            # camelCase -> snake_case: "channelId" -> "channel_id"
            snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", required_param).lower()
            param_forms.add(snake)
            # snake_case -> camelCase: "channel_id" -> "channelId"
            camel = re.sub(r"_([a-z])", lambda m: m.group(1).upper(), required_param)
            param_forms.add(camel)

            found = False
            for form in param_forms:
                if found:
                    break
                patterns = [
                    rf"\b{re.escape(form)}\b\s*(?:=|:)\s*([^\s,\]\);]+)",
                    rf"\b{re.escape(form)}\b\s+is\s+([^\s,\]\);]+)",
                ]
                for pattern in patterns:
                    match = re.search(pattern, text, flags=re.IGNORECASE)
                    if not match:
                        continue
                    value = match.group(1).strip("`'\".,:;()[]<>")
                    if Agent._is_nonempty_parameter_candidate(value):
                        resolved[required_param] = value
                        found = True
                        break

        return resolved

    def _get_successful_planning_results(self, my_results: Dict[str, Any]) -> Dict[str, Any]:
        """Return only successful tool/skill results for downstream parameter binding."""
        return {
            placeholder: result
            for placeholder, result in my_results.items()
            if result is not None and not self._is_tool_execution_error(result)
        }

    def _collect_values_for_key(self, payloads: List[Any], key_name: str) -> List[Any]:
        """Collect non-empty values for a key across structured payloads."""
        values: List[Any] = []
        seen: set[str] = set()
        for payload in payloads:
            for record in self._iter_result_records(payload):
                if not isinstance(record, dict):
                    continue
                for record_key, record_value in record.items():
                    if record_key.lower() != key_name.lower():
                        continue
                    if not self._is_nonempty_parameter_candidate(record_value):
                        continue
                    marker = str(record_value)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    values.append(record_value)
        return values

    def _extract_alias_value_from_record(
        self, param_name: str, record: Dict[str, Any], expected_kind: str = "generic"
    ) -> Any:
        """Map common identifier-style params to the most likely value in a record."""
        if not isinstance(record, dict):
            return None

        lowered_param = param_name.lower()
        # Normalize snake_case → camelcase for suffix matching so both
        # "channelId" and "channel_id" are handled uniformly.
        normalized_param = lowered_param.replace("_", "")
        parent_reference = record.get("parentReference")
        if not isinstance(parent_reference, dict):
            parent_reference = {}

        if normalized_param.endswith("driveid"):
            for candidate in (
                record.get("driveId"),
                parent_reference.get("driveId"),
            ):
                if self._is_nonempty_parameter_candidate(candidate):
                    return candidate
            if self._is_nonempty_parameter_candidate(record.get("id")) and (
                "driveType" in record or "quota" in record or record.get("name") == "OneDrive"
            ):
                return record.get("id")

        if normalized_param.endswith(
            (
                "itemid",
                "fileid",
                "folderid",
                "messageid",
                "taskid",
                "recordid",
                "siteid",
                "documentid",
                "workbookid",
                "worksheetid",
                "sheetid",
                "notebookid",
                "sectionid",
                "pageid",
                "channelid",
                "teamid",
                "planid",
                "listid",
                "eventid",
                "contactid",
            )
        ):
            if not self._record_matches_expected_kind(record, expected_kind):
                return None
            if self._is_nonempty_parameter_candidate(record.get("id")):
                return record.get("id")

        return None

    def _resolve_parameter_from_records(
        self,
        param_name: str,
        candidate_records: List[Dict[str, Any]],
        all_records: List[Dict[str, Any]],
        expected_kind: str = "generic",
    ) -> Any:
        """Resolve one parameter from matching records first, then broader result context."""
        search_spaces = [candidate_records, all_records]

        for records in search_spaces:
            if not records:
                continue

            exact_values: List[Any] = []
            seen_exact: set[str] = set()
            normalized_param = param_name.lower().replace("_", "")
            for record in records:
                if not self._record_matches_expected_kind(record, expected_kind):
                    continue
                for key, value in record.items():
                    if key.lower().replace("_", "") != normalized_param:
                        continue
                    if not self._is_nonempty_parameter_candidate(value):
                        continue
                    marker = str(value)
                    if marker in seen_exact:
                        continue
                    seen_exact.add(marker)
                    exact_values.append(value)

            if len(exact_values) == 1:
                return exact_values[0]
            if exact_values:
                return exact_values[0]

            alias_values: List[Any] = []
            seen_alias: set[str] = set()
            for record in records:
                alias_value = self._extract_alias_value_from_record(
                    param_name, record, expected_kind
                )
                if not self._is_nonempty_parameter_candidate(alias_value):
                    continue
                marker = str(alias_value)
                if marker in seen_alias:
                    continue
                seen_alias.add(marker)
                alias_values.append(alias_value)

            if alias_values:
                # With most-recent-first ordering the first alias is from the
                # latest step, which is the most specific result.
                return alias_values[0]

        return None

    def _resolve_parameters_from_context(
        self,
        required_params: List[str],
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
        action_description: str,
        user_request: str,
        my_results: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None,
        tool_name: str = "",
    ) -> Dict[str, Any]:
        """Resolve as many required parameters as possible from explicit context and prior results."""
        if not required_params:
            return {}

        runtime_context_params = {
            key: value for key, value in (runtime_context or {}).items() if key in required_params
        }
        resolved = self._merge_parameter_candidates(
            current_parameters={},
            candidate_parameters=runtime_context_params,
            param_properties=param_properties,
            full_schema=full_schema,
        )
        resolved = self._merge_parameter_candidates(
            current_parameters=resolved,
            candidate_parameters=self._extract_explicit_parameter_values_from_text(
                user_request, required_params
            ),
            param_properties=param_properties,
            full_schema=full_schema,
        )
        successful_results = self._get_successful_planning_results(my_results)
        structured_payloads = [
            self._extract_structured_planning_result_payload(result)
            for result in successful_results.values()
            if result is not None
        ]
        # Reverse so the most recent step's records are searched first —
        # later steps produce more specific results (e.g. worksheet IDs
        # from list-excel-worksheets should win over file IDs from
        # list-folder-files).
        all_records = [
            record
            for payload in reversed(structured_payloads)
            for record in self._iter_result_records(payload)
            if isinstance(record, dict)
        ]
        context_hints = self._extract_context_hints(user_request, action_description)
        candidate_records = [
            record
            for record in all_records
            if self._record_matches_context_hints(record, context_hints)
        ]

        for required_param in required_params:
            if required_param in resolved:
                continue

            param_def = self._resolve_schema_ref(
                param_properties.get(required_param, {}), full_schema
            )
            expected_kind = self._infer_parameter_record_kind(
                required_param,
                tool_name=tool_name,
                action_description=action_description,
                param_definition=param_def,
            )
            resolved_value = self._resolve_parameter_from_records(
                required_param,
                candidate_records,
                all_records,
                expected_kind=expected_kind,
            )
            if self._has_resolved_required_parameter_value(resolved_value, param_def):
                resolved[required_param] = resolved_value
                continue

            if required_param.lower().replace("_", "").endswith("driveid"):
                drive_values = self._collect_values_for_key(structured_payloads, "driveId")
                if len(drive_values) == 1 and self._has_resolved_required_parameter_value(
                    drive_values[0], param_def
                ):
                    resolved[required_param] = drive_values[0]

        return resolved

    def _get_active_skill_execution_context(self) -> Dict[str, Any]:
        """Return the active runtime-only skill context for this agent/session."""
        overlord = getattr(self, "overlord", None)
        if not overlord or not hasattr(overlord, "skill_manager"):
            return {}

        skill_manager = getattr(overlord, "skill_manager", None)
        if not skill_manager:
            return {}

        return skill_manager.get_active_execution_context(
            self.agent_id,
            getattr(self, "_current_session_id", "default"),
        )

    def _build_parameter_inference_context(
        self,
        user_request: str,
        action_description: str,
        my_results: Dict[str, Any],
        required_params: List[str],
    ) -> str:
        """Build a compact but information-dense context block for parameter inference."""
        prompt_parts = [user_request]
        if action_description:
            prompt_parts.extend(["", f"Step action: {action_description}"])

        explicit_values = self._extract_explicit_parameter_values_from_text(
            user_request, required_params
        )
        if explicit_values:
            prompt_parts.extend(
                [
                    "",
                    "Explicit parameter hints from the request/context:",
                    json.dumps(explicit_values, ensure_ascii=False),
                ]
            )

        successful_results = self._get_successful_planning_results(my_results)
        if successful_results:
            prompt_parts.append("")
            prompt_parts.append("=== PREVIOUS TOOL RESULTS ===")
            context_hint = f"{user_request}\n{action_description}"
            for placeholder, result in successful_results.items():
                prompt_parts.append(f"Previous tool result ({placeholder}):")
                prompt_parts.append(
                    self._summarize_planning_result(result, context_hint=context_hint, limit=2000)
                )

        return "\n".join(prompt_parts)

    def _resolve_parameter_from_result_payload(
        self,
        param_name: str,
        payload: Any,
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
        action_description: str,
        tool_name: str = "",
    ) -> Any:
        """Resolve one parameter value from a single successful result payload."""
        param_def = self._resolve_schema_ref(param_properties.get(param_name, {}), full_schema)
        expected_kind = self._infer_parameter_record_kind(
            param_name,
            tool_name=tool_name,
            action_description=action_description,
            param_definition=param_def,
        )
        records = [
            record for record in self._iter_result_records(payload) if isinstance(record, dict)
        ]
        resolved_value = self._resolve_parameter_from_records(
            param_name,
            records,
            records,
            expected_kind=expected_kind,
        )
        if self._has_resolved_required_parameter_value(resolved_value, param_def):
            return resolved_value

        if param_name.lower().endswith("driveid"):
            drive_values = self._collect_values_for_key([payload], "driveId")
            if len(drive_values) == 1 and self._has_resolved_required_parameter_value(
                drive_values[0], param_def
            ):
                return drive_values[0]

        # Last-resort fallback: return the whole payload only when the
        # parameter schema is known AND the payload is a scalar-like value
        # (not a dict or a list).  Without this guard, hallucinated params
        # that are not in the tool schema (empty param_def) would swallow the
        # entire result object and send it to MCP, producing pydantic errors
        # like the v0.20260416.2 BUG-4 report.
        if param_def and not isinstance(payload, (dict, list)):
            if self._has_resolved_required_parameter_value(payload, param_def):
                return payload

        return None

    @staticmethod
    def _parse_placeholder_reference(
        placeholder_key: str,
    ) -> tuple[str, Optional[str], Optional[Dict[str, Any]]]:
        """Split a placeholder reference into (base_key, field_hint, predicate).

        Supported shapes:
            ``{{FOO}}``                      → (``{{FOO}}``, None, None)
            ``{{FOO.bar}}``                  → (``{{FOO}}``, ``bar``, None)
            ``{{FOO[name='Book.xlsx']}}``    → (``{{FOO}}``, None, {"name": "Book.xlsx"})
            ``{{FOO[name='x'].id}}``         → (``{{FOO}}``, ``id``, {"name": "x"})

        The LLM often emits dotted references like ``{{SPARK_EVENT.event_id}}``
        to indicate "use the event_id field from the SPARK_EVENT step output".
        my_results is keyed on the bare placeholder (`{{SPARK_EVENT}}`), so we
        must strip the `.field` suffix before lookup and pass the suffix down
        as a field hint.

        The optional ``[key=value]`` predicate disambiguates extraction when the
        referenced step returned a list of records (e.g. ``list-folder-files``
        returning every file and folder at a OneDrive root).  Without a
        predicate, ``{{FILE_LIST.id}}`` resolves to the first record's id,
        which is rarely what the planner intended; ``{{FILE_LIST[name='Book.xlsx'].id}}``
        filters to the record whose ``name`` field matches before extraction.

        Invalid predicate syntax degrades gracefully: we return the original
        string with no field/predicate so the caller falls back to the legacy
        lookup path (which may still succeed via fuzzy matching).
        """
        match = re.match(
            r"^(\{\{\s*[A-Za-z0-9_\-]+)"  # base
            r"(\[[^\]]+\])?"  # optional predicate
            r"(?:\.([A-Za-z0-9_\-]+))?"  # optional field
            r"(\s*\}\})$",  # close
            placeholder_key,
        )
        if not match:
            return placeholder_key, None, None

        base_key = match.group(1) + match.group(4)
        predicate_raw = match.group(2)
        field_hint = match.group(3)

        predicate: Optional[Dict[str, Any]] = None
        if predicate_raw:
            predicate = Agent._parse_placeholder_predicate(predicate_raw)
            if predicate is None:
                # Predicate present but malformed — preserve original so
                # callers fall back to best-effort lookup rather than
                # silently trusting a broken filter.
                return placeholder_key, None, None

        return base_key, field_hint, predicate

    # Reserved key used internally to represent positional `[N]` selection
    # inside the predicate dict. Callers must NOT use this as a real record
    # field name; the parser guarantees it cannot appear via user syntax.
    PLACEHOLDER_INDEX_KEY = "__index__"

    @staticmethod
    def _parse_placeholder_predicate(raw: str) -> Optional[Dict[str, Any]]:
        """Parse ``[key=value]`` into ``{key: value}``, or ``[N]`` into
        ``{__index__: N}`` for positional selection.

        Value types recognized in priority order for ``[key=value]``:
            1. Single- or double-quoted string: ``'Book.xlsx'``, ``"Book.xlsx"``
            2. Boolean: ``true``/``false`` (case-insensitive)
            3. Null: ``null``/``none`` (case-insensitive)
            4. Integer: ``42``, ``-3``
            5. Float: ``1.5``, ``-0.25``
            6. Bare word (unquoted): ``file``, ``active-user`` — treated as string

        Integer index ``[N]`` (and ``[-N]``) selects the Nth indexable record
        from the payload, walking the most-relevant list-of-dicts found via
        :meth:`_iter_indexable_records` (top-level list, common wrapper keys
        like ``value``/``items``/``data``, then depth-first walk). Allows
        the LLM to write ``{{WORKSHEET_LIST[0].id}}`` for "the first
        worksheet's id" without inventing a name predicate.

        Single-pair for v1; comma-separated AND predicates are reserved for
        future extension.  Returns None on syntactic error so the caller can
        refuse substitution rather than guess intent.
        """
        if not raw or not raw.startswith("[") or not raw.endswith("]"):
            return None
        inner = raw[1:-1].strip()
        if not inner:
            return None

        # Positional index: [N], [-N]
        if re.match(r"^-?\d+$", inner):
            try:
                return {Agent.PLACEHOLDER_INDEX_KEY: int(inner)}
            except ValueError:
                return None

        eq_idx = inner.find("=")
        if eq_idx <= 0 or eq_idx >= len(inner) - 1:
            return None

        key = inner[:eq_idx].strip()
        value_str = inner[eq_idx + 1 :].strip()

        if not re.match(r"^[A-Za-z0-9_\-]+$", key):
            return None

        # Quoted string
        if len(value_str) >= 2 and value_str[0] == value_str[-1] and value_str[0] in ("'", '"'):
            return {key: value_str[1:-1]}

        lowered = value_str.lower()
        if lowered == "true":
            return {key: True}
        if lowered == "false":
            return {key: False}
        if lowered in ("null", "none"):
            return {key: None}

        try:
            if "." in value_str:
                return {key: float(value_str)}
            return {key: int(value_str)}
        except ValueError:
            pass

        # Bare word (unquoted string) — allow alphanumerics plus a few safe
        # separators seen in identifiers.  Reject anything with whitespace or
        # symbols that suggest the LLM emitted malformed syntax.
        if re.match(r"^[A-Za-z0-9._\-@]+$", value_str):
            return {key: value_str}

        return None

    @staticmethod
    def _record_matches_predicate(
        record: Any,
        predicate: Dict[str, Any],
    ) -> bool:
        """Return True if ``record`` satisfies every key=value pair in ``predicate``.

        Field names are normalized (lowercase, underscores/dashes stripped) so a
        predicate key of ``name`` matches record keys ``Name``, ``display_name``,
        and ``DisplayName``.  String values compare case-insensitively; numeric
        values tolerate string representations (e.g. record value ``"42"`` vs
        predicate value ``42``); booleans require strict type match.  An
        explicit ``None`` predicate value matches missing or null record fields.
        """
        if not isinstance(record, dict):
            return False
        if not predicate:
            return True

        # Defensive: positional index selectors are dispatched by
        # _filter_records_by_predicate, never per-record matching. Strip the
        # reserved key so downstream comparison stays sound if someone calls
        # this directly with a mixed dict.
        if Agent.PLACEHOLDER_INDEX_KEY in predicate:
            predicate = {k: v for k, v in predicate.items() if k != Agent.PLACEHOLDER_INDEX_KEY}
            if not predicate:
                return True

        normalized_record: Dict[str, Any] = {}
        for key, value in record.items():
            if not isinstance(key, str):
                continue
            normalized_record[key.lower().replace("_", "").replace("-", "")] = value

        for raw_key, expected in predicate.items():
            normalized_key = raw_key.lower().replace("_", "").replace("-", "")
            present = normalized_key in normalized_record
            actual = normalized_record.get(normalized_key)

            if expected is None:
                if not present or actual is None:
                    continue
                return False

            if actual is None:
                return False

            if isinstance(expected, bool):
                if not isinstance(actual, bool) or actual is not expected:
                    return False
            elif isinstance(expected, str) and isinstance(actual, str):
                if expected.lower() != actual.lower():
                    return False
            elif isinstance(expected, (int, float)):
                try:
                    if float(actual) != float(expected):  # type: ignore[arg-type]
                        return False
                except (TypeError, ValueError):
                    return False
            else:
                if expected != actual:
                    return False

        return True

    @staticmethod
    def _iter_indexable_records(payload: Any) -> List[Dict[str, Any]]:
        """Return the most relevant ordered list of record dicts for ``[N]`` indexing.

        Unlike :meth:`_iter_result_records` (which yields EVERY nested mapping
        including wrapper dicts), this helper resolves to the single list the
        LLM most likely meant when it wrote ``[N]``. It tries, in order:

            1. ``payload`` itself if it's a list of dicts.
            2. The first wrapper key (``value``/``items``/``data``/``results``/
               ``records``/``matches``/``files``/``messages``/``events``)
               whose value is a non-empty list of dicts.
            3. The first list of dicts encountered via depth-first walk.

        Returns an empty list when no indexable record sequence exists, so
        callers can treat "out of range" and "no list" identically (no match).
        """
        if isinstance(payload, list):
            records = [item for item in payload if isinstance(item, dict)]
            if records:
                return records

        if not isinstance(payload, dict):
            return []

        wrapper_keys = (
            "value",
            "items",
            "data",
            "results",
            "records",
            "matches",
            "files",
            "messages",
            "events",
        )
        for key in wrapper_keys:
            candidate = payload.get(key)
            if isinstance(candidate, list):
                records = [item for item in candidate if isinstance(item, dict)]
                if records:
                    return records

        # Depth-first walk for nested list-of-dicts.
        stack: List[Any] = list(payload.values())
        while stack:
            current = stack.pop(0)
            if isinstance(current, list):
                records = [item for item in current if isinstance(item, dict)]
                if records:
                    return records
                stack.extend(current)
            elif isinstance(current, dict):
                stack.extend(current.values())

        return []

    @staticmethod
    def _filter_records_by_predicate(
        payload: Any,
        predicate: Dict[str, Any],
        *,
        collect_all: bool = False,
    ) -> Any:
        """Walk every nested mapping in ``payload`` and return matching records.

        Two predicate shapes are dispatched:

        - ``{__index__: N}``: positional selection from
          :meth:`_iter_indexable_records`. Returns the Nth record (or empty
          when out of range). ``collect_all=True`` returns a one-element list
          for parity with the value-predicate path.
        - ``{key: value, ...}``: value matching against every nested record
          via :meth:`_record_matches_predicate`. Ordering is depth-first
          (outer dict first, then nested lists/dicts), matching the
          traversal used elsewhere for field extraction.

        With ``collect_all=False`` returns the first matching record or
        ``None``; with ``collect_all=True`` returns a list of every matching
        record. Empty inputs return ``None`` / ``[]``.
        """
        if predicate and Agent.PLACEHOLDER_INDEX_KEY in predicate:
            # Index path is exclusive — we deliberately reject mixing index
            # with value predicates at parse time, but defensively bail out
            # if other keys somehow leaked in.
            if len(predicate) != 1:
                return [] if collect_all else None
            idx = predicate[Agent.PLACEHOLDER_INDEX_KEY]
            if not isinstance(idx, int):
                return [] if collect_all else None
            indexable = Agent._iter_indexable_records(payload)
            if not indexable:
                return [] if collect_all else None
            try:
                record = indexable[idx]
            except IndexError:
                return [] if collect_all else None
            if collect_all:
                return [record]
            return record

        matches: List[Dict[str, Any]] = []
        for record in Agent._iter_result_records(payload):
            if not isinstance(record, dict):
                continue
            if not Agent._record_matches_predicate(record, predicate):
                continue
            matches.append(record)
            if not collect_all:
                break

        # Text-payload fallback: when structured-record matching finds
        # nothing, some MCP servers (Google Calendar/Gmail in particular)
        # serialize list results as human-readable text blocks rather than
        # JSON arrays. Parse those text blocks into synthetic dict records
        # so predicates like ``{{EVENT_SEARCH[summary='Spark Test 2'].id}}``
        # still resolve against the free-text payload.
        if not matches:
            for record in Agent._parse_text_blocks_into_records(payload):
                if not Agent._record_matches_predicate(record, predicate):
                    continue
                matches.append(record)
                if not collect_all:
                    break

        if collect_all:
            return matches
        return matches[0] if matches else None

    # Pattern for a text block boundary inside a free-text MCP payload:
    # a line starting with ``- `` (bulleted item) OR a blank line followed
    # by a line matching ``Key: value``/``Key: "value"`` or an inline
    # ``Key: ... ID: <id>`` record. Used only by
    # :meth:`_parse_text_blocks_into_records` as a conservative heuristic
    # to recover predicate-matchable records from free-text payloads.
    _TEXT_BLOCK_BULLET_PREFIX = re.compile(r"^\s*[-*]\s+", re.MULTILINE)

    # Keys we recognize inside a text block as the "title"/"name" of the
    # record. Order matters: the first matching key wins when populating
    # the synthetic record (so a block with both ``Subject:`` and
    # ``Title:`` labels uses ``Subject`` as the primary title). Lowercase.
    _TEXT_BLOCK_TITLE_ALIASES = (
        "summary",
        "title",
        "name",
        "subject",
        "displayname",
    )

    @staticmethod
    def _parse_text_blocks_into_records(payload: Any) -> List[Dict[str, Any]]:
        """Parse free-text MCP payloads into synthetic dict records.

        Google's MCP servers frequently serialize list results as
        human-readable text blocks, e.g.::

            - "Spark Test 2" (Starts: 2026-04-21T10:00, Ends: 2026-04-21T10:30)
              Description: No Description
              ID: rnnbrh9v8lh853dkvit1d8a234
            - "Ruby Daily Sync" (Starts: ...)
              ID: 09jdumm...

        This helper splits each text chunk on bullet boundaries, pulls the
        quoted title (mapping it to ``summary``/``title``/``name``/
        ``subject`` so predicate filters work), and harvests ``Key: value``
        pairs inside each block into the synthetic record. Returns an empty
        list whenever the payload does not look bulleted — callers use this
        as an optional fallback and tolerate empty results.

        Conservative by design: we only emit records when a bulleted shape
        is detected (first non-empty line starts with ``-`` or ``*``) AND
        the block yields at least one ``Key: value`` pair. This avoids
        false positives on arbitrary narrative text.
        """
        records: List[Dict[str, Any]] = []
        if payload in (None, "", [], {}):
            return records

        text_chunks = Agent._collect_text_chunks_from_payload(payload)
        for chunk in text_chunks:
            if not isinstance(chunk, str) or not chunk.strip():
                continue
            if not Agent._TEXT_BLOCK_BULLET_PREFIX.search(chunk):
                continue
            for block in Agent._split_text_into_bulleted_blocks(chunk):
                record = Agent._text_block_to_record(block)
                if record:
                    records.append(record)
        return records

    @staticmethod
    def _split_text_into_bulleted_blocks(text: str) -> List[str]:
        """Split ``text`` at ``^[-*] `` boundaries into block segments.

        Continuation lines (indented or unindented non-bullet lines) belong
        to the preceding bullet block. Non-bullet prose before the first
        bullet is ignored.
        """
        blocks: List[str] = []
        current: List[str] = []
        for raw_line in text.splitlines():
            if Agent._TEXT_BLOCK_BULLET_PREFIX.match(raw_line):
                if current:
                    blocks.append("\n".join(current))
                    current = []
                current.append(raw_line)
            elif current:
                current.append(raw_line)
        if current:
            blocks.append("\n".join(current))
        return blocks

    @staticmethod
    def _text_block_to_record(block: str) -> Optional[Dict[str, Any]]:
        """Convert a single bulleted text block into a synthetic record.

        Extracts:
        - The first quoted string on the opening bullet line as the title
          (exposed under every alias in :data:`_TEXT_BLOCK_TITLE_ALIASES`
          so predicates matching any of them succeed).
        - Every ``Key: value`` pair on subsequent lines (value trimmed of
          surrounding whitespace / trailing ``|`` separator fragments).
        - Inline ``Key: value`` pairs appearing on the opening bullet line
          itself after the title, so ``ID: xyz`` on the same line as the
          title is still captured.

        Returns ``None`` when no key-value pairs can be extracted.
        """
        if not block or not isinstance(block, str):
            return None

        record: Dict[str, Any] = {}

        # 1. Title from opening bullet line's first quoted substring.
        first_line = block.splitlines()[0] if block.splitlines() else block
        title_match = re.search(r'"([^"\n]{1,256})"|\'([^\'\n]{1,256})\'', first_line)
        if title_match:
            title = (title_match.group(1) or title_match.group(2) or "").strip()
            if title:
                for alias in Agent._TEXT_BLOCK_TITLE_ALIASES:
                    record[alias] = title

        # Title aliases we already populated from the quoted header — we
        # must not overwrite them with narrative labels that happen to
        # share a name (e.g. ``Subject: No subject`` prose later in the
        # block when the bullet-line title already set ``subject``).
        title_alias_keys = {
            alias.replace("_", "").replace("-", "") for alias in Agent._TEXT_BLOCK_TITLE_ALIASES
        }

        # 2. Harvest ``Key: value`` pairs from every line (including the
        #    opening bullet). The key must be an identifier-like word;
        #    value runs until the next ``|`` pipe separator or end of line
        #    (some MCPs concatenate fields with ``|`` in a single line).
        kv_pattern = re.compile(
            r"(?:^|\|)\s*([A-Za-z][A-Za-z0-9 _\-]{0,48})\s*:\s*([^\n|]+?)\s*(?=\||$)",
            re.MULTILINE,
        )
        for match in kv_pattern.finditer(block):
            key = match.group(1).strip()
            value = match.group(2).strip()
            if not key or not value:
                continue
            normalized_key = key.lower().replace(" ", "").replace("-", "").replace("_", "")
            # Skip the bullet prefix itself from being interpreted as a key.
            if not normalized_key or normalized_key == "-":
                continue
            # Do not clobber a title alias we already populated from the
            # quoted header on the opening bullet line.
            if normalized_key in title_alias_keys and any(
                alias in record for alias in Agent._TEXT_BLOCK_TITLE_ALIASES
            ):
                continue
            # Store under the normalized key (lowercase, no spaces) so
            # predicate matching can find it regardless of the surface
            # casing used in the text.
            record.setdefault(normalized_key, value)
            # Also preserve the original key for downstream callers that
            # walk the dict keys directly.
            record.setdefault(key, value)

        if not record:
            return None
        return record

    def _extract_field_from_matched_records(
        self,
        records: List[Dict[str, Any]],
        field_name: str,
        *,
        collect_all: bool = False,
    ) -> Any:
        """Extract ``field_name`` values from a pre-filtered list of records.

        Used by the predicate path to scan only the records that matched the
        predicate, skipping the broader tree walk and the text-chunk fallback
        (which cannot reliably honor predicates against free-text payloads).
        """
        target = field_name.lower().replace("_", "").replace("-", "")
        collected: List[Any] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            for key, value in record.items():
                if not isinstance(key, str):
                    continue
                if key.lower().replace("_", "").replace("-", "") != target:
                    continue
                if not self._is_nonempty_parameter_candidate(value):
                    continue
                if collect_all:
                    marker = str(value)
                    if marker not in {str(v) for v in collected}:
                        collected.append(value)
                else:
                    return value
        if collect_all:
            return collected
        return collected[0] if collected else None

    # File extensions that strongly indicate the token is a real resource
    # name rather than a bare noun in prose. Kept conservative to avoid
    # auto-applying predicates for generic words that happen to contain a
    # dot (e.g. version strings, URLs).
    _NAMED_RESOURCE_EXTENSIONS = (
        "xlsx",
        "xls",
        "xlsm",
        "docx",
        "doc",
        "pdf",
        "pptx",
        "ppt",
        "csv",
        "tsv",
        "txt",
        "md",
        "rtf",
        "json",
        "xml",
        "yaml",
        "yml",
        "html",
        "htm",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "bmp",
        "zip",
        "tar",
        "gz",
        "mp3",
        "mp4",
        "mov",
        "wav",
    )

    @staticmethod
    def _extract_named_resource_from_action(
        action_description: Optional[str],
    ) -> Optional[str]:
        """Return the first deliberately-named resource mentioned in the action.

        "Deliberate" means the LLM marked the name via quotes, backticks, or
        used a recognizable file extension. Bare capitalized words are
        intentionally excluded because they generate too many false positives
        (proper nouns in prose, tool verbs, agent names, etc.) to safely
        promote into an auto-applied predicate.

        The helper searches in priority order so an explicitly-quoted
        reference always beats an incidental filename elsewhere in the same
        description.
        """
        if not action_description or not isinstance(action_description, str):
            return None
        text = action_description

        # 1. Double-quoted string.
        match = re.search(r'"([^"\n]{1,128})"', text)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate

        # 2. Single-quoted string.
        match = re.search(r"'([^'\n]{1,128})'", text)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate

        # 3. Backtick-wrapped (markdown code span).
        match = re.search(r"`([^`\n]{1,128})`", text)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate

        # 4. Unquoted filename with a recognized extension. Filenames with
        # spaces must be quoted/backticked by the LLM — the unquoted path
        # deliberately disallows whitespace inside the candidate so we don't
        # swallow preceding prose (``... to find Book.xlsx`` must capture
        # only ``Book.xlsx``, not the whole sentence).
        extensions = "|".join(Agent._NAMED_RESOURCE_EXTENSIONS)
        filename_pattern = (
            r"(?<![A-Za-z0-9_\-/])"  # left boundary: not mid-identifier or path
            r"([A-Za-z0-9_][A-Za-z0-9_\-.]{0,63}\.(?:" + extensions + r"))"
            r"(?![A-Za-z0-9_])"  # right boundary: not mid-identifier
        )
        match = re.search(filename_pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate

        return None

    # Ordered list of record-field variants that represent "the human name of
    # this thing". Order matters — the first variant with ambiguity + a match
    # wins, so more-specific fields (``name``) take precedence over weaker
    # ones (``subject``) when multiple are present.
    _AUTO_PREDICATE_NAME_FIELDS = ("name", "displayName", "title", "subject")

    def _infer_auto_name_predicate(
        self,
        payload: Any,
        action_description: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Synthesize a name-predicate from the action description.

        Runs only when all three conditions hold:
            1. The action description explicitly names a resource (see
               :meth:`_extract_named_resource_from_action` for what counts).
            2. The payload contains AT LEAST TWO records that carry the same
               name-field variant (so ``{{FOO.id}}`` resolution is genuinely
               ambiguous). With 0-1 such records the resolution is
               unambiguous and auto-inference would be pointless.
            3. At least one of those records actually matches the extracted
               resource name. Without this check we would silently rewrite
               a placeholder against a resource the LLM referenced but the
               prior step never returned, producing a harder-to-debug
               "no matching record" failure instead of the legacy
               first-match behavior.

        The synthesized predicate uses the ACTUAL field variant present on
        the matching records (``name``, ``displayName``, ``title``, or
        ``subject``) so downstream matching — which is strict about key
        normalization — finds the right record.

        Returns ``None`` when any guard fails so callers fall back to the
        existing extraction path without surprise.
        """
        named = Agent._extract_named_resource_from_action(action_description)
        if not named:
            return None

        records = [
            record for record in Agent._iter_result_records(payload) if isinstance(record, dict)
        ]
        if not records:
            return None

        expected_lower = named.lower()
        for variant in Agent._AUTO_PREDICATE_NAME_FIELDS:
            variant_normalized = variant.lower().replace("_", "").replace("-", "")
            records_with_field = 0
            matching_records = 0
            for record in records:
                for key, value in record.items():
                    if not isinstance(key, str):
                        continue
                    if key.lower().replace("_", "").replace("-", "") != variant_normalized:
                        continue
                    records_with_field += 1
                    if isinstance(value, str) and value.strip().lower() == expected_lower:
                        matching_records += 1
                    break
            if records_with_field >= 2 and matching_records >= 1:
                return {variant: named}

        return None

    def _substitute_step_parameter_placeholders(
        self,
        parameters: Dict[str, Any],
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
        action_description: str,
        my_results: Dict[str, Any],
        tool_name: str = "",
    ) -> Dict[str, Any]:
        """Replace placeholder-valued step params with values from prior successful results.

        Two-pass design:

        1. **Top-level pass** — uses the full schema-aware machinery
           (auto-inferred predicates, kind-based fallback,
           cross-placeholder resolution) for each top-level param whose
           value is itself a placeholder string. This is the path
           v0.20260418.0 already covered.
        2. **Nested pass** — for top-level params whose value is a dict or
           list (e.g. MS Graph's ``parentReference: {id: "{{FOO.id}}"}``),
           recursively walks string leaves and substitutes any
           placeholder using explicit predicate / field-hint resolution.
           Schema-driven inference is intentionally skipped here because
           we do not have a per-leaf schema; the LLM authored the
           placeholder explicitly and we honor it literally.

        Without the second pass, v0.20260418.0 silently shipped literal
        ``"{{...}}"`` strings inside nested dict params to MCP, which
        Microsoft Graph silently ignored — the OneDrive "move to folder"
        bug from the v0.20260418.0 field report is the canonical case.
        """
        if not parameters or not my_results:
            return dict(parameters)

        successful_results = self._get_successful_planning_results(my_results)
        if not successful_results:
            return dict(parameters)

        substituted = dict(parameters)
        for param_name, param_value in substituted.items():
            if not self._is_placeholder_like_value(param_value):
                # Embedded-placeholder path: when the value is a string
                # that *contains* one or more ``{{...}}`` tokens mixed
                # with literal prose (e.g. ``"{{DRAFT.body}}\n\nHappy
                # Birthday!"``), run targeted in-place substitution so the
                # resolved fragments replace the tokens and the literal
                # text is preserved. Whole-string placeholders continue
                # through the richer schema-aware path below.
                if isinstance(param_value, str) and self._contains_embedded_placeholder(
                    param_value
                ):
                    replaced = self._substitute_embedded_placeholders(
                        text=param_value,
                        successful_results=successful_results,
                    )
                    if replaced != param_value:
                        substituted[param_name] = replaced
                continue

            placeholder_key = str(param_value).strip()
            referenced_result = successful_results.get(placeholder_key)
            field_hint: Optional[str] = None
            predicate: Optional[Dict[str, Any]] = None
            if referenced_result is None:
                # Try dot-notation and/or predicate filter: `{{FOO.bar}}`,
                # `{{FOO[k=v]}}`, `{{FOO[k=v].bar}}` all collapse to a lookup
                # of `{{FOO}}` with a field hint and/or predicate applied to
                # the payload prior to field extraction.
                base_key, field_hint, predicate = self._parse_placeholder_reference(placeholder_key)
                if base_key != placeholder_key:
                    referenced_result = successful_results.get(base_key)

            if referenced_result is None:
                # Cross-placeholder fallback: the LLM often invents a
                # placeholder name (e.g. ``{{EVENT_ID_FROM_SEARCH}}``) that
                # doesn't match any output_placeholder it actually assigned.
                # As a last resort, try to resolve this parameter from the
                # union of all successful result payloads, but only when the
                # match is unambiguous across every prior result.
                fallback_value = self._resolve_parameter_across_all_results(
                    param_name=param_name,
                    param_properties=param_properties,
                    full_schema=full_schema,
                    action_description=action_description,
                    tool_name=tool_name,
                    successful_results=successful_results,
                )
                if fallback_value is not None:
                    substituted[param_name] = fallback_value
                continue

            payload = self._extract_structured_planning_result_payload(referenced_result)
            resolved_value: Any = None
            param_def = self._resolve_schema_ref(param_properties.get(param_name, {}), full_schema)
            param_type = param_def.get("type") if isinstance(param_def, dict) else None

            # Option 2: when the LLM referenced `{{FOO.field}}` without an
            # explicit predicate, try to disambiguate multi-record payloads
            # by cross-referencing the step's action_description for a
            # deliberately-named resource. This prevents the "picks first
            # record" silent failure (e.g. `{{FILE_LIST.id}}` returning the
            # Attachments folder instead of the Book.xlsx the action said
            # it was trying to locate). The auto-predicate only fires when
            # the payload is genuinely ambiguous and the named resource
            # actually exists in it; otherwise we fall back to the legacy
            # first-match resolution.
            effective_predicate = predicate
            auto_applied = False
            if effective_predicate is None and field_hint and action_description:
                inferred = self._infer_auto_name_predicate(
                    payload=payload,
                    action_description=action_description,
                )
                if inferred is not None:
                    effective_predicate = inferred
                    auto_applied = True

            if field_hint or effective_predicate:
                if param_type == "array":
                    all_matches = self._extract_field_from_result_payload(
                        payload, field_hint, predicate=effective_predicate, collect_all=True
                    )
                    if isinstance(all_matches, list) and all_matches:
                        resolved_value = all_matches
                else:
                    resolved_value = self._extract_field_from_result_payload(
                        payload, field_hint, predicate=effective_predicate
                    )

            if auto_applied and resolved_value is not None:
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": self.agent_id,
                        "tool_name": tool_name,
                        "param_name": param_name,
                        "placeholder_key": placeholder_key,
                        "field_hint": field_hint,
                        "inferred_predicate": effective_predicate,
                        "action_description": action_description[:200],
                    },
                    description=(
                        f"Auto-applied name predicate {effective_predicate} to "
                        f"disambiguate {param_name}='{placeholder_key}' against a "
                        f"multi-record result on tool {tool_name or '(unknown)'}"
                    ),
                )

            if resolved_value is None and param_type == "array":
                # Try extracting by parameter name directly (for cases where
                # the placeholder has no dot-notation but the schema wants
                # an array).
                name_matches = self._extract_field_from_result_payload(
                    payload, param_name, collect_all=True
                )
                if isinstance(name_matches, list) and name_matches:
                    resolved_value = name_matches

            if resolved_value is None:
                resolved_value = self._resolve_parameter_from_result_payload(
                    param_name=param_name,
                    payload=payload,
                    param_properties=param_properties,
                    full_schema=full_schema,
                    action_description=action_description,
                    tool_name=tool_name,
                )
            if resolved_value is not None:
                substituted[param_name] = resolved_value

        # Nested pass: recurse into dict/list top-level params for nested
        # placeholder strings the top-level pass cannot see.
        for param_name, param_value in list(substituted.items()):
            if isinstance(param_value, (dict, list)):
                substituted[param_name] = self._substitute_nested_placeholders(
                    value=param_value,
                    successful_results=successful_results,
                    param_path=param_name,
                    tool_name=tool_name,
                    depth=0,
                )

        return substituted

    # Maximum nesting depth for the nested-placeholder substitution walk.
    # MS Graph payload shapes rarely exceed 4 levels (e.g.
    # ``parentReference.driveId.something``); 8 leaves comfortable headroom
    # for unusual MCP tool schemas while bounding worst-case recursion in
    # pathological LLM-emitted structures.
    _NESTED_SUBSTITUTION_MAX_DEPTH = 8

    def _substitute_nested_placeholders(
        self,
        value: Any,
        *,
        successful_results: Dict[str, Any],
        param_path: str,
        tool_name: str = "",
        depth: int = 0,
    ) -> Any:
        """Recursively substitute placeholder string leaves inside dict/list values.

        Designed for nested parameter shapes like
        ``parentReference: {id: "{{FOO.id}}"}`` where the placeholder is not
        a top-level string and therefore invisible to the schema-aware top
        pass. Only resolves placeholders the LLM authored explicitly:
        direct ``{{FOO}}`` lookup, ``{{FOO.field}}`` field hint, or
        ``{{FOO[predicate]}}`` predicate filter. Auto-inferred name
        predicates and kind-based fallback are deliberately omitted because
        they need per-parameter schema metadata that does not exist for
        nested leaves.

        Returns the value unchanged when:
          - depth exceeds :attr:`_NESTED_SUBSTITUTION_MAX_DEPTH`
          - the leaf is not placeholder-like
          - the referenced placeholder is not in ``successful_results``
          - extraction returns ``None``

        Unresolved leaves are left as literal placeholders so the
        leftover-strip pass can drop them and emit the
        ``placeholder.unresolved`` warning.
        """
        if depth > self._NESTED_SUBSTITUTION_MAX_DEPTH:
            return value

        if isinstance(value, dict):
            return {
                key: self._substitute_nested_placeholders(
                    value=child,
                    successful_results=successful_results,
                    param_path=f"{param_path}.{key}" if param_path else str(key),
                    tool_name=tool_name,
                    depth=depth + 1,
                )
                for key, child in value.items()
            }

        if isinstance(value, list):
            return [
                self._substitute_nested_placeholders(
                    value=child,
                    successful_results=successful_results,
                    param_path=f"{param_path}[{idx}]",
                    tool_name=tool_name,
                    depth=depth + 1,
                )
                for idx, child in enumerate(value)
            ]

        if not self._is_placeholder_like_value(value):
            # Embedded-placeholder path for nested string leaves: a nested
            # leaf like ``{"body": "{{DRAFT.body}}\n\nHappy Birthday!"}``
            # is not a whole-string placeholder but still needs the
            # ``{{...}}`` token resolved in place.
            if isinstance(value, str) and self._contains_embedded_placeholder(value):
                return self._substitute_embedded_placeholders(
                    text=value,
                    successful_results=successful_results,
                )
            return value

        placeholder_key = str(value).strip()
        referenced_result = successful_results.get(placeholder_key)
        field_hint: Optional[str] = None
        predicate: Optional[Dict[str, Any]] = None

        if referenced_result is None:
            base_key, field_hint, predicate = self._parse_placeholder_reference(placeholder_key)
            if base_key != placeholder_key:
                referenced_result = successful_results.get(base_key)

        if referenced_result is None:
            return value

        payload = self._extract_structured_planning_result_payload(referenced_result)

        if not (field_hint or predicate):
            # Bare ``{{FOO}}`` reference inside a nested leaf — return the
            # whole payload only when it is a scalar; structured payloads
            # are almost certainly not what the leaf wanted.
            if isinstance(payload, (str, int, float, bool)):
                return payload
            return value

        resolved = self._extract_field_from_result_payload(payload, field_hint, predicate=predicate)
        if resolved is None:
            return value
        return resolved

    def _strip_leftover_placeholder_parameters(
        self,
        parameters: Dict[str, Any],
        required_params: List[str],
        tool_name: str = "",
    ) -> Dict[str, Any]:
        """Drop non-required parameters still holding literal placeholder strings.

        After substitution, context resolution, and inference, any remaining
        ``{{...}}`` or ``<<...>>`` value is an unresolved reference the LLM
        emitted but we could not bind to a real value.  Passing such literals
        to MCP produces 404s and pydantic errors (see v0.20260416.2 Calendar
        BUG-1 report).  Required params with literal placeholders are already
        routed through the repair-plan flow; this pass catches the
        non-required case where the unresolved-required check never fires
        because the parameter isn't declared required on the tool schema.

        The walk is recursive: an unresolved placeholder nested inside a
        dict or list (e.g. ``parentReference: {id: "{{FOO.id}}"}``)
        triggers the same drop-or-warn behavior the top-level case has.
        Without this recursion v0.20260418.0 silently passed literal
        placeholder strings inside nested dict params to MCP — Microsoft
        Graph silently ignored the bogus parentReference and the OneDrive
        move never executed.

        Emits a ``placeholder.unresolved`` warning event whenever any
        unresolved leaf is detected (regardless of whether it was dropped
        or kept), enumerating the dotted/indexed param paths so devs can
        trace silent failures back to the originating placeholder.
        """
        if not parameters:
            return dict(parameters) if isinstance(parameters, dict) else {}

        required_set = set(required_params or [])
        cleaned = dict(parameters)
        dropped: List[str] = []
        unresolved_leaves: List[Dict[str, str]] = []

        for param_name in list(cleaned.keys()):
            value = cleaned[param_name]
            leaves = self._find_unresolved_placeholder_leaves(value, base_path=param_name)
            if not leaves:
                continue
            unresolved_leaves.extend(leaves)
            if param_name not in required_set:
                dropped.append(param_name)
                del cleaned[param_name]

        if unresolved_leaves:
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "phase": "placeholder.unresolved",
                    "dropped_params": dropped,
                    "unresolved": unresolved_leaves,
                },
                description=(
                    f"{len(unresolved_leaves)} unresolved placeholder leaf(s) "
                    f"for {tool_name or '(unknown)'}: "
                    f"{', '.join(leaf['param_path'] for leaf in unresolved_leaves)}; "
                    f"dropped {len(dropped)} non-required top-level param(s): "
                    f"{', '.join(dropped) if dropped else '(none)'}"
                ),
            )

        return cleaned

    def _find_unresolved_placeholder_leaves(
        self,
        value: Any,
        *,
        base_path: str = "",
    ) -> List[Dict[str, str]]:
        """Return every placeholder-like string leaf inside ``value``.

        Each entry is ``{"param_path": "<dotted/indexed path>",
        "placeholder": "<literal placeholder string>"}``.  Used by the
        leftover-strip pass to identify nested unresolved placeholders that
        the recursive substitution walker could not bind, and by
        :meth:`_has_resolved_required_parameter_value` to decide whether a
        required dict/list param needs the repair-plan flow.
        """
        if self._is_placeholder_like_value(value):
            return [
                {
                    "param_path": base_path or "<root>",
                    "placeholder": str(value).strip(),
                }
            ]

        leaves: List[Dict[str, str]] = []

        # Embedded-placeholder detection: the top-level/nested substitution
        # passes already resolved whatever they could; anything still
        # matching ``{{...}}`` inside a larger string is an unresolved
        # reference that should be logged (and the containing non-required
        # param dropped) the same way whole-string placeholders are.
        if isinstance(value, str) and self._contains_embedded_placeholder(value):
            for match in Agent._EMBEDDED_PLACEHOLDER_SCAN.finditer(value):
                leaves.append(
                    {
                        "param_path": base_path or "<root>",
                        "placeholder": match.group(0).strip(),
                    }
                )
            return leaves

        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{base_path}.{key}" if base_path else str(key)
                leaves.extend(self._find_unresolved_placeholder_leaves(child, base_path=child_path))
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                child_path = f"{base_path}[{idx}]" if base_path else f"[{idx}]"
                leaves.extend(self._find_unresolved_placeholder_leaves(child, base_path=child_path))
        return leaves

    def _get_unresolved_nonrequired_placeholder_parameters(
        self,
        *,
        parameters: Dict[str, Any],
        required_params: List[str],
    ) -> tuple[List[str], List[Dict[str, str]]]:
        """Return non-required top-level params that still contain placeholders.

        These are planner-authored dependencies that the runtime could not
        bind to a concrete value. Even when the tool schema marks them
        optional, the current plan still depends on them, so execution must
        block and re-plan instead of silently dropping them.
        """
        required_set = set(required_params or [])
        blocked_params: List[str] = []
        unresolved_leaves: List[Dict[str, str]] = []

        for param_name, param_value in (parameters or {}).items():
            leaves = self._find_unresolved_placeholder_leaves(param_value, base_path=param_name)
            if not leaves:
                continue
            unresolved_leaves.extend(leaves)
            if param_name not in required_set:
                blocked_params.append(param_name)

        return blocked_params, unresolved_leaves

    def _resolve_parameter_across_all_results(
        self,
        param_name: str,
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
        action_description: str,
        tool_name: str,
        successful_results: Dict[str, Any],
    ) -> Any:
        """Resolve one parameter from the union of successful result payloads.

        Used when the LLM references a placeholder name that doesn't exist
        in ``my_results`` (e.g. ``{{EVENT_ID_FROM_SEARCH}}`` when only
        ``{{EVENT_DETAILS}}`` was produced).  Only returns a value when
        there is exactly one candidate across every prior result, to avoid
        silently picking the wrong one from a multi-record set.
        """
        if not successful_results:
            return None

        found_values: List[Any] = []
        seen_markers: set[str] = set()
        for result in successful_results.values():
            payload = self._extract_structured_planning_result_payload(result)
            candidate = self._resolve_parameter_from_result_payload(
                param_name=param_name,
                payload=payload,
                param_properties=param_properties,
                full_schema=full_schema,
                action_description=action_description,
                tool_name=tool_name,
            )
            if candidate is None or not self._is_nonempty_parameter_candidate(candidate):
                # Try text-based fallback on this payload's text chunks.
                text_candidates: List[str] = []
                for chunk in self._collect_text_chunks_from_payload(payload):
                    text_candidates.extend(self._extract_field_values_from_text(chunk, param_name))
                if not text_candidates:
                    # Also try the bare "id" suffix (e.g. param_name="event_id"
                    # often appears as "ID: abc" in result text).
                    lowered = param_name.lower().replace("_", "").replace("-", "")
                    if lowered.endswith("id") and lowered != "id":
                        for chunk in self._collect_text_chunks_from_payload(payload):
                            text_candidates.extend(
                                self._extract_field_values_from_text(chunk, "id")
                            )
                if len(text_candidates) == 1:
                    candidate = text_candidates[0]

            if candidate is None:
                continue
            if not self._is_nonempty_parameter_candidate(candidate):
                continue
            marker = str(candidate)
            if marker in seen_markers:
                continue
            seen_markers.add(marker)
            found_values.append(candidate)

        if len(found_values) == 1:
            return found_values[0]
        return None

    def _extract_field_from_result_payload(
        self,
        payload: Any,
        field_name: Optional[str],
        *,
        predicate: Optional[Dict[str, Any]] = None,
        collect_all: bool = False,
    ) -> Any:
        """Find occurrences of ``field_name`` in a structured or text payload.

        Walks records produced by :meth:`_iter_result_records` first, matching
        keys case-insensitively with ``_``/``-`` stripped so ``eventId``,
        ``event_id``, and ``EventID`` all resolve to the same field.  When
        the payload contains free-text content (for example, FastMCP tools
        that serialize results as ``"Message ID: abc..."`` strings), falls
        back to regex-based extraction from every text chunk inside the
        payload.

        When ``predicate`` is provided, only records matching the predicate
        are considered before field extraction; the text-chunk fallback is
        skipped in this mode because free-text payloads cannot be filtered
        reliably by field value.  With no ``field_name`` and a ``predicate``,
        returns the matched record(s) themselves.

        When ``collect_all`` is True, returns a deduplicated list of every
        match; otherwise returns the first match or ``None``.
        """
        if predicate:
            matched_records = Agent._filter_records_by_predicate(
                payload, predicate, collect_all=True
            )
            if not matched_records:
                return [] if collect_all else None
            if not field_name:
                return matched_records if collect_all else matched_records[0]
            return self._extract_field_from_matched_records(
                matched_records, field_name, collect_all=collect_all
            )

        if not field_name:
            return [] if collect_all else None

        target = field_name.lower().replace("_", "").replace("-", "")
        collected: List[Any] = []

        def _record_candidate(value: Any) -> bool:
            """Return True if we should stop (collect_all=False) after this."""
            if not self._is_nonempty_parameter_candidate(value):
                return False
            if collect_all:
                marker = str(value)
                if marker not in {str(v) for v in collected}:
                    collected.append(value)
                return False
            collected.append(value)
            return True

        for record in self._iter_result_records(payload):
            if not isinstance(record, dict):
                continue
            for key, value in record.items():
                if not isinstance(key, str):
                    continue
                normalized = key.lower().replace("_", "").replace("-", "")
                if normalized != target:
                    continue
                if _record_candidate(value):
                    return collected[0]

        # Fallback: scan every text chunk in the payload for ``Field: value``
        # or JSON-style patterns.  Required when FastMCP tools serialize
        # their structured output as human-readable text.  For array-like
        # lookups (plural names) we also probe the singular form because
        # search tools typically label each item with the singular key
        # (``Message ID: abc`` rather than ``Message IDs: abc``).
        text_chunks = self._collect_text_chunks_from_payload(payload)
        text_search_forms: List[str] = [field_name]
        singular = self._singularize_field_name(field_name)
        if singular and singular != field_name:
            text_search_forms.append(singular)

        for probe in text_search_forms:
            for chunk in text_chunks:
                for extracted in self._extract_field_values_from_text(chunk, probe):
                    if _record_candidate(extracted):
                        return collected[0]
            if collected and not collect_all:
                break

        # Secondary fallback: for entity-suffixed identifiers like
        # ``event_id`` / ``message_id`` / ``task_id``, look for the
        # unadorned ``id`` / ``ID`` label as well.  FastMCP tools often
        # serialize the primary key as just ``ID: xyz`` rather than
        # ``Event ID: xyz`` in their text output.  Only applied when the
        # first pass returned nothing, to avoid pulling unrelated IDs.
        if not collected:
            for probe in text_search_forms:
                normalized = probe.lower().replace("_", "").replace("-", "")
                if normalized.endswith("id") and normalized != "id":
                    for chunk in text_chunks:
                        for extracted in self._extract_field_values_from_text(chunk, "id"):
                            if _record_candidate(extracted):
                                return collected[0]
                    break

        if collect_all:
            return collected
        return collected[0] if collected else None

    @staticmethod
    def _singularize_field_name(field_name: str) -> Optional[str]:
        """Return a best-effort singular form for a plural identifier name.

        Supports the common patterns seen in MCP tool schemas:
            ``message_ids`` → ``message_id``
            ``messageIds``  → ``messageId``
            ``events``      → ``event``
            ``entries``     → ``entry`` (y-plural)
            ``addresses``   → ``address`` (es-plural)
        Returns ``None`` when no confident singularization is possible.
        """
        if not field_name or not isinstance(field_name, str):
            return None
        if len(field_name) < 2:
            return None
        if not field_name.endswith("s") and not field_name.endswith("S"):
            return None

        # ``ies`` → ``y`` (entries → entry)
        if field_name.endswith("ies") and len(field_name) > 3:
            return field_name[:-3] + "y"
        if field_name.endswith("IES") and len(field_name) > 3:
            return field_name[:-3] + "Y"

        # ``es`` after sibilant → drop ``es`` (addresses → address)
        if field_name.endswith(("sses", "shes", "ches", "xes", "zes")):
            return field_name[:-2]
        if field_name.endswith(("SSES", "SHES", "CHES", "XES", "ZES")):
            return field_name[:-2]

        # Simple trailing ``s``: drop it (message_ids → message_id).
        return field_name[:-1]

    @staticmethod
    def _collect_text_chunks_from_payload(payload: Any) -> List[str]:
        """Recursively collect every non-empty string embedded in a payload."""
        chunks: List[str] = []

        def _walk(value: Any) -> None:
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    chunks.append(value)
            elif isinstance(value, dict):
                for nested in value.values():
                    _walk(nested)
            elif isinstance(value, list):
                for item in value:
                    _walk(item)

        _walk(payload)
        return chunks

    @staticmethod
    def _field_name_variants(field_name: str) -> List[str]:
        """Generate plausible surface forms of a field name for text matching.

        Examples:
            ``message_id`` → ``message_id``, ``messageId``, ``message id``,
            ``Message Id``, ``Message ID``
            ``eventId`` → ``eventId``, ``event_id``, ``event id``,
            ``Event Id``, ``Event ID``
        """
        if not field_name:
            return []

        cleaned = field_name.strip()
        if not cleaned:
            return []

        variants: List[str] = [cleaned]
        # camelCase → snake_case
        snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", cleaned).lower()
        if snake and snake not in variants:
            variants.append(snake)
        # snake_case → camelCase
        camel = re.sub(r"_([a-zA-Z])", lambda m: m.group(1).upper(), cleaned)
        if camel and camel not in variants:
            variants.append(camel)
        # space-separated (lower + title)
        words = re.sub(r"[_\-]+", " ", snake).strip()
        if words and words not in variants:
            variants.append(words)
        titled = words.title() if words else ""
        if titled and titled not in variants:
            variants.append(titled)
        # ALL-CAPS suffix for common identifier words (ID, URL, URI, GUID)
        uppercase_suffixes = ("id", "url", "uri", "guid", "uuid")
        for suffix in uppercase_suffixes:
            if words.endswith(f" {suffix}"):
                upper_variant = f"{words[: -len(suffix)].rstrip().title()} {suffix.upper()}"
                if upper_variant not in variants:
                    variants.append(upper_variant)
                break
            if words == suffix:
                variants.append(suffix.upper())
                break
        return variants

    @staticmethod
    def _extract_field_values_from_text(text: str, field_name: str) -> List[str]:
        """Extract values for ``field_name`` from free-form text.

        Recognizes four patterns:

        1. ``Field: value`` or ``**Field:** value`` (markdown-style labels)
        2. ``"field": "value"`` (embedded JSON)
        3. ``field = value`` (assignment-style)
        4. ``--- FIELD ---\\n<captured value>`` (section separator;
           Gmail MCP's ``get_gmail_message_content`` uses this shape for
           the message body). The captured value runs until the next
           ``--- ... ---`` line or end of text.

        Returns a deduplicated list in discovery order.
        """
        if not isinstance(text, str) or not text.strip() or not field_name:
            return []

        values: List[str] = []
        seen: set[str] = set()

        def _accept(raw: str) -> None:
            # Strip markdown/code wrappers but keep internal punctuation so we
            # do not corrupt IDs with dashes or underscores.
            candidate = raw.strip().strip("`*_")
            candidate = candidate.strip(" \t\r\n.,;:()[]{}<>'\"")
            if not candidate:
                return
            if candidate in seen:
                return
            seen.add(candidate)
            values.append(candidate)

        for form in Agent._field_name_variants(field_name):
            escaped = re.escape(form)

            # Pattern 4 runs FIRST (before the looser label/JSON patterns)
            # because the ``--- FIELD ---`` section separator is the most
            # specific shape and must win over accidental label matches
            # inside the section body. The Gmail MCP's body section is
            # the driving case: without precedence, Pattern 1 matches
            # ``Body paragraph`` (label=``Body``, value=``paragraph``)
            # and drowns the real section capture in noise.
            section_pattern = (
                rf"(?:^|\n)\s*-{{3,}}\s*{escaped}\s*-{{3,}}\s*\n"
                r"([\s\S]*?)"
                r"(?=\n\s*-{3,}\s*[A-Za-z0-9][^\n]*-{3,}\s*(?:\n|$)|\Z)"
            )
            section_matched = False
            for match in re.finditer(section_pattern, text, flags=re.IGNORECASE):
                raw_section = match.group(1)
                if raw_section is None:
                    continue
                section_value = raw_section.strip()
                if section_value:
                    # Section contents are free-form text (can contain
                    # punctuation, newlines, etc.) and typically constitute
                    # a whole field value rather than a bare token — bypass
                    # the aggressive character stripping ``_accept`` applies
                    # so we preserve the full captured block.
                    if section_value not in seen:
                        seen.add(section_value)
                        values.append(section_value)
                    section_matched = True

            # When the section separator already produced a value for this
            # surface form, skip the looser patterns so they don't re-extract
            # fragments of the section body as spurious matches.
            if section_matched:
                continue

            # Pattern 1: label-style with optional surrounding markdown.
            # Accepts any combination of ``*``, whitespace, ``:`` or ``=`` as
            # the separator so ``**Message ID:**`` (colon inside bold) and
            # ``Message ID: `` (plain) both work.  At least one separator
            # char is required to distinguish labels from inline prose.
            label_pattern = (
                rf"(?:^|[\s\*`\(>]|\|)\*{{0,2}}{escaped}[\*\s:=]+"
                r"`?([A-Za-z0-9][A-Za-z0-9_\-./:+@]{1,256})`?"
                r"(?=$|[\s,;\n\)\]\*`\|])"
            )
            for match in re.finditer(label_pattern, text, flags=re.IGNORECASE | re.MULTILINE):
                _accept(match.group(1))

            # Pattern 2: JSON-style quoted key → quoted string value
            json_string_pattern = rf'"{escaped}"\s*:\s*"([^"]+)"'
            for match in re.finditer(json_string_pattern, text, flags=re.IGNORECASE):
                _accept(match.group(1))

            # Pattern 3: JSON-style quoted key → bare scalar value
            json_bare_pattern = (
                rf'"{escaped}"\s*:\s*([A-Za-z0-9][A-Za-z0-9_\-./:+@]{{1,256}})(?=[\s,}}\]])'
            )
            for match in re.finditer(json_bare_pattern, text, flags=re.IGNORECASE):
                _accept(match.group(1))

        return values

    def _validate_inferred_parameters_against_results(
        self,
        inferred_parameters: Dict[str, Any],
        my_results: Dict[str, Any],
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
        tool_name: str = "",
        action_description: str = "",
    ) -> Dict[str, Any]:
        """Drop inferred ID-typed params whose value doesn't appear in a
        successful result record of the expected kind.

        This prevents the LLM from hallucinating file/workbook IDs from
        folder or root records when the actual target was never discovered.
        """
        if not inferred_parameters or not my_results:
            return dict(inferred_parameters)

        successful_results = self._get_successful_planning_results(my_results)

        if successful_results:
            structured_payloads = [
                self._extract_structured_planning_result_payload(result)
                for result in successful_results.values()
            ]
            all_records = [
                record
                for payload in structured_payloads
                for record in self._iter_result_records(payload)
                if isinstance(record, dict)
            ]
            # Join every text chunk from every prior result so we can look
            # up inferred values as substrings in free-form MCP responses
            # (FastMCP tools routinely serialize results as text blobs).
            all_result_text_chunks: List[str] = []
            for payload in structured_payloads:
                all_result_text_chunks.extend(self._collect_text_chunks_from_payload(payload))
            combined_result_text = "\n".join(all_result_text_chunks)
        else:
            all_records = []
            combined_result_text = ""

        def _value_appears_in_prior_results(value: Any) -> bool:
            """Return True when ``value`` literally appears in a prior record
            or in the joined text of any prior result payload."""
            value_str = str(value)
            if not value_str:
                return False
            for record in all_records:
                for v in record.values():
                    if isinstance(v, (str, int, float)) and str(v) == value_str:
                        return True
            return value_str in combined_result_text

        validated = dict(inferred_parameters)
        for param_name, param_value in list(validated.items()):
            # --- Array values: drop fabricated items, keep only those found
            # in a prior successful result.  If every item is fabricated,
            # remove the parameter entirely so the repair flow can fire.
            if isinstance(param_value, list):
                # Empty or all-empty lists aren't actionable.
                nonempty_items = [
                    item for item in param_value if self._is_nonempty_parameter_candidate(item)
                ]
                if not nonempty_items:
                    del validated[param_name]
                    continue

                surviving: List[Any] = []
                dropped_items: List[str] = []
                for item in nonempty_items:
                    if _value_appears_in_prior_results(item):
                        surviving.append(item)
                    else:
                        dropped_items.append(str(item)[:80])

                if dropped_items:
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_PLANNING,
                        level=observability.EventLevel.WARNING,
                        data={
                            "param_name": param_name,
                            "dropped_items": dropped_items[:10],
                            "dropped_count": len(dropped_items),
                            "kept_count": len(surviving),
                            "tool_name": tool_name,
                        },
                        description=(
                            f"Dropped {len(dropped_items)} fabricated item(s) from "
                            f"inferred '{param_name}' array for {tool_name}; "
                            f"{len(surviving)} verified against prior results"
                        ),
                    )

                if not surviving:
                    del validated[param_name]
                else:
                    validated[param_name] = surviving
                continue

            if not self._is_nonempty_parameter_candidate(param_value):
                continue

            param_def = self._resolve_schema_ref(param_properties.get(param_name, {}), full_schema)
            expected_kind = self._infer_parameter_record_kind(
                param_name,
                tool_name=tool_name,
                action_description=action_description,
                param_definition=param_def,
            )
            if expected_kind == "generic":
                continue

            value_str = str(param_value)
            found_in_matching_record = False
            for record in all_records:
                if not self._record_matches_expected_kind(record, expected_kind):
                    continue
                record_id = record.get("id")
                if record_id is not None and str(record_id) == value_str:
                    found_in_matching_record = True
                    break

            if not found_in_matching_record:
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "param_name": param_name,
                        "inferred_value": value_str[:120],
                        "expected_kind": expected_kind,
                        "tool_name": tool_name,
                    },
                    description=(
                        f"Dropping inferred '{param_name}' — value not found in any "
                        f"'{expected_kind}' record from successful results"
                    ),
                )
                del validated[param_name]

        return validated

    def _merge_parameter_candidates(
        self,
        current_parameters: Dict[str, Any],
        candidate_parameters: Dict[str, Any],
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge candidate params without letting unresolved values override resolved ones."""
        if not candidate_parameters:
            return dict(current_parameters)

        merged = dict(current_parameters)
        for param_name, candidate_value in candidate_parameters.items():
            param_def = self._resolve_schema_ref(param_properties.get(param_name, {}), full_schema)
            current_value = merged.get(param_name)
            if self._has_resolved_required_parameter_value(current_value, param_def):
                continue
            if self._has_resolved_required_parameter_value(candidate_value, param_def):
                merged[param_name] = candidate_value

        return merged

    @staticmethod
    def _get_unknown_tool_parameters(
        parameters: Dict[str, Any],
        tool_schema: Dict[str, Any],
    ) -> List[str]:
        """Return provided params that are not declared in the tool schema."""
        param_schema = tool_schema.get("parameters", {})
        if not isinstance(param_schema, dict):
            return []

        param_properties = param_schema.get("properties", {})
        if not isinstance(param_properties, dict):
            return []

        return [param_name for param_name in parameters if param_name not in param_properties]

    def _validate_tool_parameters(
        self,
        parameters: Dict[str, Any],
        tool_schema: Dict[str, Any],
        tool_name: str,
        server_default_param_names: Optional[set[str]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate inferred or provided parameters against the tool schema.

        Args:
            parameters: Parameters to validate
            tool_schema: Tool schema containing parameter definitions
            tool_name: Name of the tool for error reporting

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            param_schema = tool_schema.get("parameters", {})
            required_params = param_schema.get("required", [])
            param_properties = param_schema.get("properties", {})
            server_default_param_names = server_default_param_names or set()
            unknown_params: List[str] = []

            # Check all required parameters are present
            for req_param in required_params:
                if req_param not in parameters and req_param not in server_default_param_names:
                    return False, f"Missing required parameter: {req_param}"

            # Validate each provided parameter
            for param_name, param_value in parameters.items():
                if param_name not in param_properties:
                    # Unknown planner-authored parameters are a hard block:
                    # executing them fail-open forwards invalid args to MCP.
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_PLANNING,
                        level=observability.EventLevel.WARNING,
                        data={
                            "agent_id": self.agent_id,
                            "tool_name": tool_name,
                            "parameter": param_name,
                            "value": param_value,
                        },
                        description=f"Parameter '{param_name}' not in tool schema for {tool_name}",
                    )
                    unknown_params.append(param_name)
                    continue

                param_def = param_properties[param_name]
                param_type = param_def.get("type")

                # Type validation
                if param_type:
                    if param_type == "string" and not isinstance(param_value, str):
                        return (
                            False,
                            f"Parameter '{param_name}' should be string, got {type(param_value).__name__}",
                        )
                    elif param_type == "number" and not isinstance(param_value, (int, float)):
                        return (
                            False,
                            f"Parameter '{param_name}' should be number, got {type(param_value).__name__}",
                        )
                    elif param_type == "integer" and not isinstance(param_value, int):
                        return (
                            False,
                            f"Parameter '{param_name}' should be integer, got {type(param_value).__name__}",
                        )
                    elif param_type == "boolean" and not isinstance(param_value, bool):
                        return (
                            False,
                            f"Parameter '{param_name}' should be boolean, got {type(param_value).__name__}",
                        )
                    elif param_type == "array" and not isinstance(param_value, list):
                        return (
                            False,
                            f"Parameter '{param_name}' should be array, got {type(param_value).__name__}",
                        )
                    elif param_type == "object" and not isinstance(param_value, dict):
                        return (
                            False,
                            f"Parameter '{param_name}' should be object, got {type(param_value).__name__}",
                        )

                # Enum validation
                param_enum = param_def.get("enum")
                if param_enum and param_value not in param_enum:
                    return (
                        False,
                        f"Parameter '{param_name}' value '{param_value}' not in allowed values: {param_enum}",
                    )

                # Min/Max validation for numbers
                if param_type in ["number", "integer"]:
                    min_val = param_def.get("minimum")
                    max_val = param_def.get("maximum")
                    if min_val is not None and param_value < min_val:
                        return (
                            False,
                            f"Parameter '{param_name}' value {param_value} is below minimum {min_val}",
                        )
                    if max_val is not None and param_value > max_val:
                        return (
                            False,
                            f"Parameter '{param_name}' value {param_value} is above maximum {max_val}",
                        )

            if unknown_params:
                return (
                    False,
                    "Unexpected parameters not in tool schema: "
                    + ", ".join(sorted(unknown_params)),
                )

            return True, None

        except Exception as e:
            # Validation errors themselves should fail closed so the step can
            # re-plan instead of executing with unchecked parameters.
            observability.observe(
                event_type=observability.ErrorEvents.PARAMETER_VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "error": str(e),
                    "parameters": parameters,
                },
                description=f"Error validating parameters for {tool_name}: {e}",
            )
            return False, str(e)

    def _has_resolved_required_parameter_value(
        self, param_value: Any, param_def: Dict[str, Any]
    ) -> bool:
        """Return True when a required parameter value looks meaningfully resolved.

        For dict/list-typed required params we also recursively check every
        string leaf for unresolved placeholder literals — without this, the
        repair-plan flow never fires when the LLM nests an unresolved
        ``{{...}}`` inside ``parentReference: {id: ...}`` (the v0.20260418.0
        OneDrive failure).
        """
        if param_value is None:
            return False

        param_type = param_def.get("type")
        if param_type == "string" or isinstance(param_value, str):
            return self._is_nonempty_parameter_candidate(param_value)

        if isinstance(param_value, (dict, list)):
            if self._find_unresolved_placeholder_leaves(param_value):
                return False

        return True

    def _get_unresolved_required_parameters(
        self,
        parameters: Dict[str, Any],
        required_params: List[str],
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
    ) -> List[str]:
        """Identify required parameters that are missing or still unresolved."""
        unresolved: List[str] = []

        for req_param in required_params:
            if req_param not in parameters:
                unresolved.append(req_param)
                continue

            param_def = self._resolve_schema_ref(param_properties.get(req_param, {}), full_schema)
            if not self._has_resolved_required_parameter_value(
                parameters.get(req_param), param_def
            ):
                unresolved.append(req_param)

        return unresolved

    def _get_mcp_default_param_names(self, server_id: Optional[str]) -> set[str]:
        """Return parameter names supplied by MCP server defaults."""
        if not server_id or not getattr(self, "_mcp_service", None):
            return set()

        server_configs = getattr(self._mcp_service, "server_configs", {})
        if not isinstance(server_configs, dict):
            return set()

        server_config = server_configs.get(server_id, {})
        if not isinstance(server_config, dict):
            return set()

        default_params = server_config.get("parameters", {})
        if not isinstance(default_params, dict):
            return set()

        return {str(key) for key, value in default_params.items() if value not in (None, "")}

    @staticmethod
    def _filter_unresolved_params_backed_by_server_defaults(
        unresolved_params: List[str], server_default_param_names: set[str]
    ) -> List[str]:
        """Remove unresolved params that will be injected by the MCP server."""
        if not unresolved_params or not server_default_param_names:
            return list(unresolved_params)
        return [
            param_name
            for param_name in unresolved_params
            if param_name not in server_default_param_names
        ]

    @staticmethod
    def _is_tool_execution_error(result: Any) -> bool:
        """Return True when a tool result represents a handled error response."""
        if not isinstance(result, dict):
            return False

        if result.get("status") == "error" or result.get("isError") is True or "error" in result:
            return True

        nested_result = result.get("result")
        if isinstance(nested_result, dict):
            if nested_result.get("status") == "error" or nested_result.get("isError") is True:
                return True

        return False

    def _resolve_schema_ref(
        self, param_def: Dict[str, Any], full_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Resolve $ref references in JSON Schema to their actual definitions.

        Args:
            param_def: Parameter definition that may contain $ref
            full_schema: Full schema containing $defs

        Returns:
            Resolved parameter definition
        """
        if "$ref" not in param_def:
            return param_def

        ref_path = param_def["$ref"]
        # Handle #/$defs/name format
        if ref_path.startswith("#/$defs/"):
            def_name = ref_path.split("/")[-1]
            defs = full_schema.get("$defs", {})
            if def_name in defs:
                resolved = defs[def_name].copy()
                # Recursively resolve nested refs
                if "$ref" in resolved:
                    return self._resolve_schema_ref(resolved, full_schema)
                # Handle oneOf by taking the first option as example
                if "oneOf" in resolved:
                    first_option = resolved["oneOf"][0]
                    if "$ref" in first_option:
                        return self._resolve_schema_ref(first_option, full_schema)
                    return first_option
                return resolved
        return param_def

    async def _infer_tool_parameters(
        self,
        tool_name: str,
        required_params: List[str],
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
        action_description: str,
        user_request: str,
    ) -> Dict[str, Any]:
        """
        Use LLM to intelligently infer tool parameters based on context and schema.
        No hardcoded tool-specific logic.

        Args:
            tool_name: Name of the tool
            required_params: List of required parameter names
            param_properties: Parameter definitions from schema
            full_schema: Full parameter schema including $defs for resolving references
            action_description: Description of what the step is trying to do
            user_request: Original user request

        Returns:
            Dict of inferred parameters, or empty dict if inference failed
        """
        if not required_params:
            return {}

        try:
            # Build a prompt for the LLM to infer parameters
            # Build parameters section
            parameters_section = ""
            for param in required_params:
                param_def = param_properties.get(param, {})
                # Resolve $ref if present
                param_def = self._resolve_schema_ref(param_def, full_schema)
                param_type = param_def.get("type", "object")
                param_desc = param_def.get("description", "No description available")
                param_enum = param_def.get("enum", [])
                # Check for nested object structure
                nested_props = param_def.get("properties", {})
                nested_required = param_def.get("required", [])

                parameters_section += f"\n- {param}:"
                parameters_section += f"\n  Type: {param_type}"
                parameters_section += f"\n  Description: {param_desc}"
                if param_enum:
                    parameters_section += f"\n  Allowed values: {param_enum}"
                if param_def.get("minimum") is not None:
                    parameters_section += f"\n  Minimum: {param_def['minimum']}"
                if param_def.get("maximum") is not None:
                    parameters_section += f"\n  Maximum: {param_def['maximum']}"
                # Show nested object structure for complex parameters
                if nested_props and param_type == "object":
                    parameters_section += f"\n  Required fields: {nested_required}"
                    parameters_section += "\n  Structure: {"
                    for prop_name, prop_def in nested_props.items():
                        prop_type = prop_def.get("type", "string")
                        parameters_section += f'\n    "{prop_name}": <{prop_type}>'
                    parameters_section += "\n  }"

            # Include tool-specific constraints (critical for generate_file code generation)
            tool_constraints = ""
            if tool_name == "generate_file":
                tool_constraints = (
                    "\nIMPORTANT CONSTRAINTS for generate_file:\n"
                    "- ONLY use these libraries: matplotlib, seaborn, plotly, reportlab, fpdf2, "
                    "python-docx (docx), openpyxl, xlsxwriter, python-pptx (pptx), "
                    "Pillow (PIL), pandas, numpy, scipy, qrcode, python-barcode, "
                    "lxml, markdown, csv, json, datetime, math, random, re, io, base64.\n"
                    "- You may use requests/urllib to fetch data if needed.\n"
                    "- Use matplotlib.use('Agg') before any plotting.\n"
                    "- Save output files to the current directory.\n"
                    "- For PDFs, prefer reportlab over fpdf. If using fpdf2, "
                    "strip or replace non-ASCII characters to avoid encoding errors.\n"
                    "\n"
                    "EXECUTABLE-CODE CONTRACT (critical — failures here are silent):\n"
                    "- The `code` parameter MUST be COMPLETE, EXECUTABLE Python that produces "
                    "the output file when run as-is. There is NO second pass that fills in "
                    "the body for you. Comment-only code, docstring-only code, or pseudo-code "
                    "stubs like `# Content will be injected later` will execute, produce no "
                    "file, and fail with `No file was generated`.\n"
                    "- `{{PLACEHOLDER}}` references are NOT substituted inside the multi-line "
                    "`code` string. Placeholder substitution applies to scalar parameter values "
                    "in OTHER tools (e.g. URLs, IDs), not to Python source you author here. If "
                    "you write `text = '{{MUXI_DOCS}}'` inside `code`, that literal string is "
                    "what your Python will see — not the scraped content.\n"
                    "- If your file's content depends on data you don't have at planning time, "
                    "you have TWO choices and only two:\n"
                    "  (a) Write the content verbatim from what you already know about the "
                    "      subject (recommended — your training data is usually sufficient for "
                    "      one-pagers, briefs, summaries, charts).\n"
                    "  (b) Have the Python ITSELF fetch the data using `requests`/`urllib` and "
                    "      then build the file from the response. The fetch happens INSIDE the "
                    "      sandboxed subprocess, not as a prior planning step.\n"
                    "- Do NOT emit a `code` value that is only comments, only a docstring, only "
                    "imports, or otherwise has no statement that writes a file to the current "
                    "directory. The artifact sandbox will reject it before execution and the "
                    "step will fail.\n"
                )

            # System prompt for parameter inference
            system_prompt = f"""Based on the user's request and tool requirements, determine the appropriate parameter values.

Tool Name: {tool_name}
Action Description: {action_description}
{tool_constraints}
Required Parameters:
{parameters_section}

Analyze the user's request and provide appropriate parameter values.
Respond with ONLY a valid JSON object containing the parameter values.
Example: {{"param1": "value1", "param2": 123}}

Documented sentinel values are valid concrete values, not guesses. When a parameter's own Description text explicitly documents a sentinel (for example, "use 'me' for the current user", "pass 'root' for the default site", "use 'primary' for the default calendar"), emit that sentinel when BOTH of the following hold:
  (1) the user's request did not identify a specific resource for this parameter, AND
  (2) no prior step output supplies the real identifier.
If the user named a specific resource, or a prior step already produced the real ID, do NOT apply the sentinel.

If you cannot determine a value from context:
- Do NOT invent placeholder/default values
- Do NOT use empty strings, 0, false, or empty objects/lists to satisfy required parameters
- Omit unresolved parameters from the JSON object entirely
- If a required identifier must come from a prior tool call, leave it unresolved rather than guessing"""

            # Use LLM to infer parameters
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request},
            ]
            response = await self.model.chat(
                messages=messages,
                temperature=0.1,  # Low temperature for deterministic parameter generation
                max_tokens=16000,  # Must be large enough for code generation (e.g. generate_file)
            )

            response_text = response.strip()

            parameters = self._extract_json_from_response(response_text, required_params)

            if parameters is None:
                # First attempt failed -- retry with a stronger prompt
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "tool_name": tool_name,
                        "first_response": response_text[:500],
                    },
                    description=(
                        f"Parameter inference returned non-JSON for {tool_name}, retrying"
                    ),
                )
                retry_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_request},
                    {"role": "assistant", "content": response_text},
                    {
                        "role": "user",
                        "content": (
                            "Your response was not valid JSON. "
                            "Respond with ONLY a JSON object, no explanation, no XML, "
                            "no function calls, no markdown. "
                            'Example: {"param": "value"}'
                        ),
                    },
                ]
                retry_response = await self.model.chat(
                    messages=retry_messages,
                    temperature=0.0,
                    max_tokens=4000,
                )
                parameters = self._extract_json_from_response(
                    retry_response.strip(), required_params
                )

            if parameters is None:
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.ERROR,
                    data={
                        "tool_name": tool_name,
                        "response": response_text[:500],
                    },
                    description="Failed to parse LLM parameter inference as JSON after retry",
                )
                return {}

            unresolved_required_params = self._get_unresolved_required_parameters(
                parameters,
                required_params,
                param_properties,
                full_schema,
            )

            if unresolved_required_params:
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "tool_name": tool_name,
                        "unresolved_params": unresolved_required_params,
                        "inferred": parameters,
                    },
                    description=(
                        f"LLM inference left required params unresolved: "
                        f"{unresolved_required_params}"
                    ),
                )
                return {}

            # Validate we have all required parameters
            if all(param in parameters for param in required_params):
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "agent_id": self.agent_id,
                        "tool_name": tool_name,
                        "inferred_params": parameters,
                    },
                    description=f"LLM inferred parameters for {tool_name}",
                )
                return parameters
            else:
                missing = [p for p in required_params if p not in parameters]
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "tool_name": tool_name,
                        "missing_params": missing,
                        "inferred": parameters,
                    },
                    description=f"LLM inference missing required params: {missing}",
                )
                return {}
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.ERROR,
                data={"tool_name": tool_name, "error": str(e)},
                description="Exception in LLM parameter inference",
            )
            return {}

    @staticmethod
    def _extract_json_from_response(
        text: str, required_params: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Extract JSON parameters from an LLM response that may contain
        markdown code blocks, XML function-call wrappers, or embedded JSON
        objects mixed with prose. Returns None if extraction fails."""
        import json
        import re

        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Extract from XML function-call wrappers (e.g. Anthropic tool-call format)
        arg_match = re.search(
            r'<parameter\s+name="arguments">\s*(\{[^<]+\})\s*</parameter>',
            text,
            re.DOTALL,
        )
        if arg_match:
            try:
                result = json.loads(arg_match.group(1))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        # Extract individual <parameter name="key">value</parameter> tags
        param_pairs = re.findall(
            r'<parameter\s+name="([^"]+)">([^<]*)</parameter>',
            text,
        )
        if param_pairs:
            result = {}
            for key, val in param_pairs:
                if key in ("arguments",):
                    continue
                val = val.strip()
                # Try parsing as JSON value (for nested objects / arrays)
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    pass
                result[key] = val
            if result:
                return result

        # Find any JSON object containing at least one required param
        brace_starts = [i for i, c in enumerate(text) if c == "{"]
        for start in brace_starts:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            result = json.loads(candidate)
                            if isinstance(result, dict) and any(
                                p in result for p in required_params
                            ):
                                return result
                        except json.JSONDecodeError:
                            pass
                        break

        return None
