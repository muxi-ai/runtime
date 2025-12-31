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

import datetime
import traceback
import json
import re
import time
from typing import Any, Dict, List, Optional, Union

from ..artifacts.extractor import extract_artifacts_from_tool_results
from ..background.cancellation import RequestCancelledException
from ..credentials import MissingCredentialError
from ...utils.id_generator import generate_nanoid
from ...datatypes.response import MuxiResponse
from ...datatypes.intent import IntentType, IntentDetectionContext
from ...services.mcp.service import MCPService
from ...services.llm import LLM
from ...services.intent import IntentDetectionService
from ...services import observability, streaming
from ...utils.security import sanitize_message_preview


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
        self.role = None  # Will be set from config during agent creation
        self.specialties = []  # Will be set from config during agent creation

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
        self._messages = []

        # Initialize A2A history for loop detection and attempt limiting
        # Using collections.deque for efficient bounded history
        from collections import deque

        self._max_a2a_history_size = 20  # Keep last 20 delegation attempts
        self._a2a_history = deque(maxlen=self._max_a2a_history_size)
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
            # Import KnowledgeHandler here to avoid circular imports
            from .knowledge.handler import KnowledgeHandler

            # Get embedding function from model for semantic search
            # Knowledge handler needs a function that handles multiple texts
            embedding_fn = None
            if hasattr(self.model, "generate_embeddings"):
                # Prefer batch embedding function for efficiency
                embedding_fn = self.model.generate_embeddings
            elif hasattr(self.model, "get_embeddings"):
                embedding_fn = self.model.get_embeddings
            elif hasattr(self.model, "embed"):
                # Fallback: wrap single embed in a batch handler with error handling
                async def batch_embed(texts):
                    embeddings = []
                    for i, text in enumerate(texts):
                        try:
                            embedding = await self.model.embed(text)
                            embeddings.append(embedding)
                        except Exception as e:
                            # Log error but continue processing other texts
                            observability.observe(
                                event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                                level=observability.EventLevel.WARNING,
                                description="Failed to generate embedding for text in batch",
                                data={
                                    "text_index": i,
                                    "text_preview": text[:100] if text else "",
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                },
                            )
                            # Append None to maintain index alignment
                            embeddings.append(None)
                    return embeddings

                embedding_fn = batch_embed

            # Get formation config from overlord if available
            formation_config = None
            if hasattr(self.overlord, "formation_config") and self.overlord.formation_config:
                formation_config = self.overlord.formation_config

            # Get formation_id from overlord
            formation_id = getattr(self.overlord, "formation_id", "default-formation")

            # Create knowledge handler using the factory method with formation config
            self.knowledge_handler = await KnowledgeHandler.from_agent_config(
                agent_id=self.agent_id,
                knowledge_config=knowledge_config,
                generate_embeddings_fn=embedding_fn,
                formation_config=formation_config,
                working_memory=getattr(self.overlord, "buffer_memory", None),
                auto_inject_knowledge=True,
                formation_id=formation_id,  # Pass formation_id explicitly
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
            context = IntentDetectionContext(
                recent_messages=(
                    [
                        {"role": msg.role, "content": msg.content[:200]}
                        for msg in self._messages[-5:]  # Last 5 messages
                    ]
                    if hasattr(self, "_messages") and self._messages
                    else None
                )
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

    async def process_message(
        self,
        message: Union[str, MuxiResponse],
        user_id: Any = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        is_a2a_task: bool = False,
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

        Returns:
            The agent's response as an MuxiResponse, possibly including tool call results
            or clarification requests in metadata.
        """
        # Convert string message to MuxiResponse if needed
        if isinstance(message, str):
            content = message
            message_obj = MuxiResponse(role="user", content=content)
        else:
            content = message.content
            message_obj = message

        # Store message metadata for use in other methods (like A2A routing)
        self._current_message_metadata = (
            message_obj.metadata if hasattr(message_obj, "metadata") else None
        )

        # Reset A2A attempt counter for each new request to prevent cascading failures
        self._a2a_attempt_count = 0

        # Emit agent message processing event with enhanced metadata
        tool_count = len(self.tools) if hasattr(self, 'tools') and self.tools else 0
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "message_length": len(content),
                "has_tools": tool_count > 0,
                "tool_count": tool_count,
                "model_used": self.model if hasattr(self, 'model') and self.model else None,
            },
            description=f"Agent {self.agent_id} ({self.name}) starting message processing",
        )

        # Memory storage is handled by chat orchestrator - agent should not store messages
        # This prevents duplicate storage of enhanced messages

        # Add message to conversation context
        self._messages.append({"role": "user", "content": message_obj.content})

        # Store current user message for credential selection context
        self._current_user_message = message_obj.content

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
                search_results = await self.search_knowledge(
                    query=content, limit=5, include_memory=True, unified=True, session_id=session_id
                )

                # Build enhanced context from unified results
                knowledge_results = search_results.get("knowledge", [])
                memory_results = search_results.get("memory", [])

                if knowledge_results or memory_results or recent_docs:
                    # Add enhanced context to the conversation
                    enhanced_message = self._enhance_message_with_context(
                        content, recent_docs, knowledge_results, memory_results
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
                            "query": content[:100],
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
                enhanced_message = self._enhance_message_with_context(content, recent_docs)
                self._messages[-1]["content"] = enhanced_message

        # Check if we should include MCP tools
        tools = None
        if self.overlord and hasattr(self.overlord, "mcp_service"):
            try:
                mcp_service = self.overlord.mcp_service
                # Use agent-specific tool registry to get only tools this agent has access to
                available_tools = mcp_service.get_tool_registry(self.agent_id)

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

                # Always add the built-in generate_file tool if artifact service is available
                if self.overlord and hasattr(self.overlord, "artifact_service"):
                    generate_file_tool = {
                        "type": "function",
                        "function": {
                            "name": "generate_file",
                            "description": "Generate files (charts, documents, spreadsheets, images, presentations) by executing Python code with curated libraries.",  # noqa: E501
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "Python code to execute for file generation. The code should save the output file in the current directory.",  # noqa: E501
                                    },
                                    "filename": {
                                        "type": "string",
                                        "description": "Optional filename hint for the generated file",  # noqa: E501
                                    },
                                },
                                "required": ["code"],
                            },
                        },
                    }
                    tools.append(generate_file_tool)
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
            user_message = (
                message_obj.content if hasattr(message_obj, "content") else str(message_obj)
            )
            is_workflow_task = (
                # Check for workflow context indicators
                ("## Task:" in user_message)  # Workflow task prompt format
                or ("Task Details:" in user_message)  # Another workflow indicator
                or ("Required Capabilities:" in user_message)  # Workflow metadata
                or ("THIS SPECIFIC TASK ONLY" in user_message)  # Workflow instruction
            )

        # Extract actual user request from enhanced message for planning
        # The enhanced message contains conversation context which confuses the planning LLM
        actual_user_request = user_message
        if "=== CURRENT REQUEST ===" in user_message and "User:" in user_message:
            # Extract just the current request from the enhanced message
            lines = user_message.split("\n")
            for i, line in enumerate(lines):
                if line.strip() == "=== CURRENT REQUEST ===" and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line.startswith("User:"):
                        actual_user_request = next_line[5:].strip()  # Remove "User: " prefix
                        break

        # Skip planning for workflow tasks or A2A tasks (to prevent loops)
        if is_workflow_task or is_a2a_task:
            # Log that we're bypassing planning
            reason = "a2a_task_detected" if is_a2a_task else "workflow_task_detected"
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "phase": "planning_bypassed",
                    "reason": reason,
                    "message_preview": (
                        user_message[:100] + "..." if len(user_message) > 100 else user_message
                    ),
                },
                description=f"Agent {self.agent_id} bypassing planning phase: {reason}",
            )

        # Variables to store planning results
        execution_plan = None
        my_results = {}
        planning_response_parts = []  # Collect response parts during planning

        # Only plan for user messages that might need multiple steps (skip for workflow tasks and A2A tasks)
        if (
            self._messages
            and self._messages[-1]["role"] == "user"
            and tools
            and not is_workflow_task
            and not is_a2a_task
        ):
            try:
                # Use the extracted actual request for planning, not the full enhanced message
                execution_plan = await self._plan_before_execution(actual_user_request, tools)

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
                    for step in execution_plan.get("my_steps", []):
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
                                tool_def = next(
                                    (
                                        t
                                        for t in tools
                                        if t.get("function", {}).get("name") == tool_name
                                    ),
                                    None,
                                )

                                if tool_def:
                                    # Extract server_id and actual tool name if present
                                    if "__" in tool_name:
                                        server_id, actual_tool_name = tool_name.split("__", 1)
                                    else:
                                        server_id = None
                                        actual_tool_name = tool_name

                                    # Extract parameters from step configuration or use LLM to generate them
                                    parameters = step.get("parameters", {})

                                    # If no parameters provided, try to infer them from context
                                    if not parameters:
                                        # Get tool schema to understand required parameters
                                        tool_schema = tool_def.get("function", {})
                                        required_params = tool_schema.get("parameters", {}).get(
                                            "required", []
                                        )
                                        param_properties = tool_schema.get("parameters", {}).get(
                                            "properties", {}
                                        )

                                        if required_params:
                                            # Try to infer parameters based on tool name, request context, and schema
                                            parameters = await self._infer_tool_parameters(
                                                tool_name=actual_tool_name,
                                                required_params=required_params,
                                                param_properties=param_properties,
                                                action_description=step.get("action", ""),
                                                user_request=user_message,
                                            )

                                            if parameters:
                                                observability.observe(
                                                    event_type=observability.ConversationEvents.AGENT_PLANNING,
                                                    level=observability.EventLevel.DEBUG,
                                                    data={
                                                        "agent_id": self.agent_id,
                                                        "tool_name": tool_name,
                                                        "inferred_params": parameters,
                                                    },
                                                    description=f"Inferred parameters for {tool_name}",
                                                )

                                        # If still no parameters and required params exist, skip
                                        if not parameters and required_params:
                                            observability.observe(
                                                event_type=observability.ConversationEvents.AGENT_PLANNING,
                                                level=observability.EventLevel.DEBUG,
                                                data={
                                                    "agent_id": self.agent_id,
                                                    "tool_name": tool_name,
                                                    "required_params": required_params,
                                                    "reason": "cannot_infer_parameters",
                                                },
                                                description=(
                                                    f"Skipping planned step {tool_name} - "
                                                    "cannot infer required parameters"
                                                ),
                                            )
                                            continue

                                    # Validate parameters against tool schema before execution
                                    is_valid, validation_error = self._validate_tool_parameters(
                                        parameters=parameters,
                                        tool_schema=tool_schema,
                                        tool_name=tool_name,
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

                                        # Store error result instead of executing
                                        placeholder = step.get(
                                            "output_placeholder", f"{{{tool_name.upper()}_OUTPUT}}"
                                        )
                                        my_results[placeholder] = {
                                            "status": "error",
                                            "error": f"Parameter validation failed: {validation_error}",
                                            "tool_name": tool_name,
                                            "step_action": step.get("action", ""),
                                        }
                                        continue

                                    # Check for cancellation before tool execution
                                    await self._check_cancellation(request_id)

                                    # Execute the tool with validated parameters
                                    tool_result = await self.invoke_tool(
                                        tool_name=actual_tool_name,
                                        parameters=parameters,
                                        server_id=server_id,
                                        user_id=user_id,
                                    )

                                    # Store result with placeholder key
                                    placeholder = step.get(
                                        "output_placeholder", f"{{{tool_name.upper()}_OUTPUT}}"
                                    )
                                    my_results[placeholder] = tool_result

                                    # Log successful execution
                                    observability.observe(
                                        event_type=observability.ConversationEvents.MCP_TOOL_CALL_COMPLETED,
                                        level=observability.EventLevel.INFO,
                                        data={
                                            "agent_id": self.agent_id,
                                            "tool_name": tool_name,
                                            "step_action": step.get("action"),
                                            "phase": "planning_execution",
                                        },
                                        description=f"Executed planned step: {step.get('action')}",
                                    )
                        except Exception as e:
                            # Re-raise credential errors to trigger clarification flow
                            from ..credentials import AmbiguousCredentialError, MissingCredentialError
                            from ...services.mcp.service import CredentialSelectionNeededError

                            if isinstance(e, (
                                AmbiguousCredentialError,
                                MissingCredentialError,
                                CredentialSelectionNeededError,
                            )):
                                # These need to bubble up to overlord for clarification
                                raise

                            # Store error result for placeholder replacement
                            placeholder = step.get(
                                "output_placeholder", f"{{{tool_name.upper()}_OUTPUT}}"
                            )
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

                # DELEGATION PHASE: Handle delegate_steps
                if execution_plan and execution_plan.get("delegate_steps"):
                    # We have steps to delegate - process them after my_steps
                    for delegate_step in execution_plan.get("delegate_steps", []):
                        # Get delegation prompt with placeholders replaced
                        delegation_prompt = delegate_step.get("delegation_prompt", user_message)

                        # Replace placeholders with actual results from my_steps
                        for placeholder, result in my_results.items():
                            if placeholder in delegation_prompt:
                                # Extract useful information from result
                                result_text = str(result)
                                if isinstance(result, dict):
                                    # Try to extract the most relevant info
                                    result_text = result.get(
                                        "result", result.get("output", str(result))
                                    )
                                    # Ensure result_text is a string
                                    if not isinstance(result_text, str):
                                        result_text = str(result_text)
                                delegation_prompt = delegation_prompt.replace(
                                    placeholder, result_text
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
                            # A2A request failed (likely timeout)
                            # If this was the only delegation, we should indicate the failure
                            if (
                                not my_results
                                and len(execution_plan.get("delegate_steps", [])) == 1
                            ):
                                planning_response_parts.append(
                                    "I've delegated the task to an external agent, "
                                    "but there was a delay in receiving the response. "
                                    "The task may still be processing. "
                                    "Please check back in a moment."
                                )

                # Check if this is a simple direct response (no steps needed)
                if execution_plan and not execution_plan.get("my_steps") and not execution_plan.get("delegate_steps"):
                    # Empty plan - handle simple requests directly
                    data_flow = execution_plan.get("data_flow", "")
                    if "direct response" in data_flow.lower() or "no tools needed" in data_flow.lower():
                        # Generate a direct response for simple conversational requests
                        simple_messages = [
                            {"role": "system", "content": "You are a helpful assistant. Provide direct, natural responses without using any tools or files."},  # noqa: E501
                            {"role": "user", "content": message}
                        ]

                        response_obj = await self.model.chat(simple_messages)
                        response_text = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)

                        response = MuxiResponse(
                            role="assistant",
                            content=response_text.strip()
                        )

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

                        self._messages.append({"role": "assistant", "content": response.content})
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
                    if has_successful_delegation:
                        # Show the delegation responses as the primary result
                        response_content = "\n\n".join(planning_response_parts)

                        # Include local tool execution results only if we have any successful local executions
                        # my_results contains tool outputs from local (non-delegated) tool executions
                        if my_results:
                            response_content += "\n\n---\n\nAdditional information gathered:\n"
                            for placeholder, result in my_results.items():
                                if isinstance(result, dict):
                                    result_text = result.get(
                                        "result", result.get("output", str(result))
                                    )
                                else:
                                    result_text = str(result)
                                response_content += f"{result_text}\n\n"
                    else:
                        # No successful delegations, show local results first
                        if my_results:
                            for placeholder, result in my_results.items():
                                if isinstance(result, dict):
                                    result_text = result.get(
                                        "result", result.get("output", str(result))
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
                                artifacts = await extract_artifacts_from_tool_results(tool_execution_results)
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
                    self._messages.append({"role": "assistant", "content": response.content})

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
                from ..credentials import AmbiguousCredentialError, MissingCredentialError
                from ...services.mcp.service import CredentialSelectionNeededError

                if isinstance(e, (AmbiguousCredentialError, MissingCredentialError, CredentialSelectionNeededError)):
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

                raw_response = await self.model.chat_with_tools(self._messages, tools=tools)
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
                raw_response = await self.model.chat(self._messages)
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
                    raw_response = await self.model.chat(self._messages)
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
                raw_response = await self.model.chat(self._messages)

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
        clarification_request = await self._check_agent_clarification_needs(
            content, message_obj.content
        )

        # Create response message
        response = MuxiResponse(role="assistant", content=content)

        # Note: clarification_request is tracked in observability but not stored in response

        # Add response to conversation context
        self._messages.append({"role": "assistant", "content": response.content})

        # Emit agent response generated event
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "response_length": len(response.content),
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
        error_history = []
        current_raw_response = raw_response
        current_content = content
        all_tool_execution_results = []  # Store all tool results for artifact extraction

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
                message = current_raw_response["choices"][0]["message"]
                if "tool_calls" in message and message["tool_calls"]:
                    tool_calls = message["tool_calls"]

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
                    display_name = server_id.replace("-", " ").replace("_", " ").title() if server_id else actual_tool_name
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
                next_response = await self.model.chat_with_tools(
                    self._messages, tools=tools if tools else None
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
                    reconsider_response = await self.model.chat_with_tools(
                        self._messages, tools=tools if tools else None
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
        recent_docs: List[Dict[str, Any]] = None,
        knowledge_results: List[Dict[str, Any]] = None,
        memory_results: List[Dict[str, Any]] = None,
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
        error_counts = {}
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
                recent_messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": agent_response},
                ]
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
        return response.content

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
            # Special handling for generate_file tool - use artifact service directly
            if (
                tool_name == "generate_file"
                and self.overlord
                and hasattr(self.overlord, "artifact_service")
            ):
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": self.agent_id,
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "using_artifact_service": True,
                    },
                    description=f"Agent {self.agent_id} using artifact service for file generation",
                )

                # Call artifact service directly
                code = parameters.get("code", "")
                filename = parameters.get("filename")

                try:
                    artifact = await self.overlord.artifact_service.generate_file(code, filename)

                    # Convert MuxiArtifact to a simplified tool response
                    # Don't include full artifact details in the tool response to avoid
                    # the agent mentioning file paths or download links
                    result = {
                        "success": True,
                        "message": (
                            f"Successfully created {artifact.filename}. "
                            "The file has been automatically attached to this response."
                        ),
                        "filename": artifact.filename,
                        "type": artifact.type,
                        "format": artifact.format,
                        "size_bytes": artifact.metadata.size_bytes if artifact.metadata else None,
                        # Store the actual artifact for the extractor
                        "_artifact": artifact,
                    }

                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
                        level=observability.EventLevel.INFO,
                        data={
                            "agent_id": self.agent_id,
                            "tool_name": tool_name,
                            "success": True,
                            "artifact_type": artifact.type,
                            "artifact_format": artifact.format,
                        },
                        description=f"Agent {self.agent_id} successfully generated file using artifact service",
                    )

                    return result

                except Exception as e:
                    # Return error in expected format
                    return {"error": str(e), "status": "error"}

            # Regular MCP tool invocation
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

            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "success": True,
                },
                description=f"Agent {self.agent_id} completed tool call {tool_name}",
            )

            return result

        except Exception as e:
            # Check if this is a credential error
            from ..credentials import AmbiguousCredentialError
            from ...services.mcp.service import CredentialSelectionNeededError

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

    async def _plan_before_execution(
        self, user_message: str, available_tools: List[Dict] = None
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
            tool_count=len(available_tools) if available_tools else 0
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

        # Build context for planning (user message + available resources)
        # NOTE: Instructions go in system message, user content stays here
        planning_prompt = f"Request: {user_message}"

        # Section 1: Available tools (agent's own MCP tools)
        planning_prompt += "\n\n## Available tools:\n"
        planning_prompt += (
            f"{', '.join([t.get('function', {}).get('name', '') for t in (available_tools or [])])}"
        )

        # Get all available agents (internal and external)
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

        # Section 2: Built-in agents (internal agents in same formation)
        internal_agents = []
        external_agents = []

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

        from ..prompts.loader import PromptLoader
        try:
            planning_prompt += PromptLoader.get('agent_planning.md')
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
                        "Always respond with valid JSON only."
                    ),
                },
                {"role": "user", "content": planning_prompt},
            ]

            # Get plan from LLM
            plan_response = await self.model.chat(
                planning_messages,
                temperature=0.1,  # Low temperature for structured output
                max_tokens=1000,
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

            # Remove markdown code blocks if present
            if plan_content.strip().startswith("```"):
                plan_content = plan_content.strip().split("```")[1]
                if plan_content.startswith("json"):
                    plan_content = plan_content[4:]
            plan = json.loads(plan_content.strip())

            # Validate and fix the plan - ensure agents don't claim tools they don't have
            available_tool_names = set(
                t.get("function", {}).get("name", "") for t in (available_tools or [])
            )

            # Fix any incorrect tool claims
            for step in plan.get("steps", []):
                tool_name = step.get("tool_name", "")
                if tool_name and tool_name not in available_tool_names:
                    # Tool not available - must delegate
                    step["can_i_do_this"] = False

            # Rebuild my_steps based on corrected can_i_do_this values
            plan["my_steps"] = [
                {
                    "action": step["action"],
                    "tool_name": step["tool_name"],
                    "output_placeholder": step.get(
                        "output_placeholder", f"{{{step['tool_name'].upper()}_OUTPUT}}"
                    ),
                }
                for step in plan.get("steps", [])
                if step.get("can_i_do_this") and step.get("tool_name") in available_tool_names
            ]

            # Rebuild delegate_steps
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
                response_content = response
                if isinstance(response, dict):
                    response_content = response.get(
                        "content", response.get("response", str(response))
                    )

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
                        message_content = message.get("task", message.get("content", str(message)))
                else:
                    # Simple message without parts structure
                    message_content = message.get("task", message.get("content", str(message)))
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
            if isinstance(model_response, str):
                response_content = model_response
            elif hasattr(model_response, "choices") and model_response.choices:
                response_content = model_response.choices[0].message.content
            else:
                response_content = str(model_response)

            # Return response for request-type messages
            if message_type in ["request", "query", "consultation"]:
                return {
                    "status": "success",
                    "response": response_content,
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

    def _validate_tool_parameters(
        self, parameters: Dict[str, Any], tool_schema: Dict[str, Any], tool_name: str
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

            # Check all required parameters are present
            for req_param in required_params:
                if req_param not in parameters:
                    return False, f"Missing required parameter: {req_param}"

            # Validate each provided parameter
            for param_name, param_value in parameters.items():
                if param_name not in param_properties:
                    # Parameter not in schema - could be extra, log warning but allow
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

            return True, None

        except Exception as e:
            # Log validation error but don't crash
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
            # Return true to allow execution to proceed despite validation error
            # This prevents blocking legitimate use cases with incomplete schemas
            return True, None

    async def _infer_tool_parameters(
        self,
        tool_name: str,
        required_params: List[str],
        param_properties: Dict[str, Any],
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
                param_type = param_def.get("type", "string")
                param_desc = param_def.get("description", "No description available")
                param_enum = param_def.get("enum", [])

                parameters_section += f"\n- {param}:"
                parameters_section += f"\n  Type: {param_type}"
                parameters_section += f"\n  Description: {param_desc}"
                if param_enum:
                    parameters_section += f"\n  Allowed values: {param_enum}"
                if param_def.get("minimum") is not None:
                    parameters_section += f"\n  Minimum: {param_def['minimum']}"
                if param_def.get("maximum") is not None:
                    parameters_section += f"\n  Maximum: {param_def['maximum']}"

            # System prompt for parameter inference
            system_prompt = f"""Based on the user's request and tool requirements, determine the appropriate parameter values.

Tool Name: {tool_name}
Action Description: {action_description}

Required Parameters:
{parameters_section}

Analyze the user's request and provide appropriate parameter values.
Respond with ONLY a valid JSON object containing the parameter values.
Example: {{"param1": "value1", "param2": 123}}

If you cannot determine a value from context:
- For enums: use the first available option
- For booleans: use false (safer default)
- For strings: use an empty string
- For numbers: use 0"""

            # Use LLM to infer parameters
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request},
            ]
            response = await self.model.chat(
                messages=messages,
                temperature=0.1,  # Low temperature for deterministic parameter generation
                max_tokens=500,
            )

            # Parse the JSON response
            import json

            response_text = response.strip()
            # Clean up response if it has markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            parameters = json.loads(response_text)

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

        except json.JSONDecodeError as e:
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PLANNING,
                level=observability.EventLevel.ERROR,
                data={
                    "tool_name": tool_name,
                    "error": str(e),
                    "response": response_text if "response_text" in locals() else None,
                },
                description="Failed to parse LLM parameter inference as JSON",
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
