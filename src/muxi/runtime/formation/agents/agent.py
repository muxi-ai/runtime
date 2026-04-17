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
            # Import KnowledgeHandler here to avoid circular imports
            from .knowledge.handler import KnowledgeHandler

            # Get embedding function from model for semantic search
            # Knowledge handler needs a function that handles multiple texts
            embedding_fn: Optional[Callable[..., Any]] = None
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
        """Synthesize a final response from planning execution results."""
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "phase": "planning_response_synthesis_start",
                "tool_result_count": len(my_results),
                "delegated_response_count": len(planning_response_parts),
            },
            description=f"Agent {self.agent_id} starting planning response synthesis",
        )

        synthesis_messages = [
            {
                "role": "system",
                "content": self._get_planning_response_synthesis_system_prompt(),
            },
            {
                "role": "user",
                "content": self._build_planning_response_synthesis_prompt(
                    user_request, my_results, planning_response_parts
                ),
            },
        ]

        response_obj = await self.model.chat(synthesis_messages)
        response_text = (
            response_obj.content if hasattr(response_obj, "content") else str(response_obj)
        )
        response_text = response_text.strip()

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "phase": "planning_response_synthesis_completed",
                "response_length": len(response_text),
            },
            description=f"Agent {self.agent_id} completed planning response synthesis",
        )

        return response_text or None

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
            user_message = message
            message_obj = MuxiResponse(role="user", content=user_message)
        else:
            message_obj = message
            user_message = self._content_to_text(message.content)

        content = user_message

        # Store message metadata for use in other methods (like A2A routing)
        self._current_message_metadata = (
            message_obj.metadata if hasattr(message_obj, "metadata") else None
        )

        # Store session_id for skill activation scoping
        self._current_session_id = session_id or "default"

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
                "model_used": self.model if hasattr(self, "model") and self.model else None,
            },
            description=f"Agent {self.agent_id} ({self.name}) starting message processing",
        )

        # Memory storage is handled by chat orchestrator - agent should not store messages
        # This prevents duplicate storage of enhanced messages

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

        # Add message to conversation context
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
                    skill_tool = self.overlord.skill_manager.build_activate_skill_tool(
                        self.agent_id
                    )
                    if skill_tool:
                        tools.append(skill_tool)

                    # Add run_skill tool if RCE client is available and skills have scripts
                    if hasattr(self.overlord, "rce_client") and self.overlord.rce_client:
                        run_tool = self.overlord.skill_manager.build_run_skill_tool(self.agent_id)
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

                                        # Store error result instead of executing
                                        my_results[placeholder] = {
                                            "status": "error",
                                            "error": f"Parameter validation failed: {validation_error}",
                                            "tool_name": tool_name,
                                            "step_action": step.get("action", ""),
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
                    ):
                        # Generate a direct response for simple conversational requests
                        # Use the agent's system_message if available, otherwise use default
                        system_content = (
                            self.system_message
                            if self.system_message
                            else (
                                "You are a helpful assistant. Provide direct, natural responses without using any tools or files."
                            )
                        )
                        simple_messages = [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": actual_user_request},
                        ]

                        response_obj = await self.model.chat(simple_messages)
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
                        try:
                            synthesized_planning_response = (
                                await self._synthesize_planning_execution_response(
                                    actual_user_request, my_results, planning_response_parts
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
                                    "Planning response synthesis failed; using raw planning results"
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

                raw_response = await self.model.chat_with_tools(
                    cast(List[Dict[str, str]], llm_messages), tools=tools
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
                    raw_response = await self.model.chat(cast(List[Dict[str, str]], self._messages))
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
                raw_response = await self.model.chat(cast(List[Dict[str, str]], self._messages))

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
                next_response = await self.model.chat_with_tools(
                    cast(List[Dict[str, str]], self._messages), tools=tools if tools else None
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
                        cast(List[Dict[str, str]], self._messages), tools=tools if tools else None
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
                        "to execute the script (e.g., command: 'python3 scripts/run.py').\n"
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

        rebuilt_my_steps: List[Dict[str, Any]] = []
        for step in plan.get("steps", []):
            if not step.get("can_i_do_this"):
                continue
            tool_name = step.get("tool_name", "")
            if tool_name not in available_tool_names:
                continue
            # Prefer parameters already present on the unified step (rare), then
            # fall back to the LLM's my_steps entry for this tool.
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
    ) -> tuple[str, Optional[str]]:
        """Split `{{FOO.bar}}` into (`{{FOO}}`, `bar`).

        The LLM often emits dotted references like ``{{SPARK_EVENT.event_id}}``
        to indicate "use the event_id field from the SPARK_EVENT step output".
        my_results is keyed on the bare placeholder (`{{SPARK_EVENT}}`), so we
        must strip the `.field` suffix before lookup and pass the suffix down
        as a field hint.
        """
        match = re.match(
            r"^(\{\{\s*[A-Za-z0-9_\-]+)\.([A-Za-z0-9_\-]+)(\s*\}\})$",
            placeholder_key,
        )
        if match:
            base_key = match.group(1) + match.group(3)
            field_hint = match.group(2)
            return base_key, field_hint
        return placeholder_key, None

    def _substitute_step_parameter_placeholders(
        self,
        parameters: Dict[str, Any],
        param_properties: Dict[str, Any],
        full_schema: Dict[str, Any],
        action_description: str,
        my_results: Dict[str, Any],
        tool_name: str = "",
    ) -> Dict[str, Any]:
        """Replace placeholder-valued step params with values from prior successful results."""
        if not parameters or not my_results:
            return dict(parameters)

        successful_results = self._get_successful_planning_results(my_results)
        if not successful_results:
            return dict(parameters)

        substituted = dict(parameters)
        for param_name, param_value in substituted.items():
            if not self._is_placeholder_like_value(param_value):
                continue

            placeholder_key = str(param_value).strip()
            referenced_result = successful_results.get(placeholder_key)
            field_hint: Optional[str] = None
            if referenced_result is None:
                # Try dot-notation: `{{FOO.bar}}` -> look up `{{FOO}}` and
                # remember `bar` as the field to prefer inside the payload.
                base_key, field_hint = self._parse_placeholder_reference(placeholder_key)
                if base_key != placeholder_key:
                    referenced_result = successful_results.get(base_key)
            if referenced_result is None:
                continue

            payload = self._extract_structured_planning_result_payload(referenced_result)
            resolved_value: Any = None
            if field_hint:
                resolved_value = self._extract_field_from_result_payload(payload, field_hint)
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

        return substituted

    def _extract_field_from_result_payload(self, payload: Any, field_name: str) -> Any:
        """Find the first occurrence of `field_name` in a structured payload.

        Walks records produced by `_iter_result_records`.  Matches are tried
        exact, case-insensitive, and with underscores stripped so that
        `eventId`, `event_id`, and `EventID` all resolve to the same field."""
        if not field_name:
            return None
        target = field_name.lower().replace("_", "").replace("-", "")
        for record in self._iter_result_records(payload):
            if not isinstance(record, dict):
                continue
            for key, value in record.items():
                if not isinstance(key, str):
                    continue
                normalized = key.lower().replace("_", "").replace("-", "")
                if normalized == target and self._is_nonempty_parameter_candidate(value):
                    return value
        return None

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
        else:
            all_records = []

        validated = dict(inferred_parameters)
        for param_name, param_value in list(validated.items()):
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

            # Check all required parameters are present
            for req_param in required_params:
                if req_param not in parameters and req_param not in server_default_param_names:
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

    def _has_resolved_required_parameter_value(
        self, param_value: Any, param_def: Dict[str, Any]
    ) -> bool:
        """Return True when a required parameter value looks meaningfully resolved."""
        if param_value is None:
            return False

        param_type = param_def.get("type")
        if param_type == "string" or isinstance(param_value, str):
            return self._is_nonempty_parameter_candidate(param_value)

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
