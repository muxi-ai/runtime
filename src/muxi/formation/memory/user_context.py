"""
User context management for the Overlord.

This module handles user context memory operations including getting, adding,
and clearing user-specific context information.
"""

from typing import Any, Dict, List, Optional

from ...services.memory.memobase import Memobase


class UserContextManager:
    """
    Manages user context operations for the Overlord.

    This class encapsulates all user context functionality that was previously
    embedded in the main Overlord class, providing a cleaner separation of concerns.
    """

    def __init__(self, overlord):
        """
        Initialize the user context manager.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord

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
        if not self.overlord.is_multi_user or not isinstance(
            self.overlord.long_term_memory, Memobase
        ):
            return {}

        # Use external_user_id directly - no conversion needed
        context = await self.overlord.long_term_memory.get_user_context(external_user_id=user_id)

        #  Info - TODO: add observability
        # ConversationEvents.MEMORY_LONG_TERM_RETRIEVED
        # Retrieved user context memory for user: '{user_id}'

        return context

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
        if not self.overlord.is_multi_user or not isinstance(
            self.overlord.long_term_memory, Memobase
        ):
            return []

        # Use external_user_id directly - no conversion needed
        context = await self.overlord.long_term_memory.add_user_context(
            external_user_id=user_id, knowledge=knowledge, source=source, importance=importance
        )

        # Invalidate BOTH synopsis caches (identity and context)
        # Skip if synopsis is disabled
        persistent_config = self.overlord.formation_config.get("memory", {}).get("persistent", {})
        synopsis_config = persistent_config.get("user_synopsis", {})

        if synopsis_config.get("enabled", True) and self.overlord.buffer_memory:
            try:
                public_id = await self.overlord.long_term_memory.get_user_public_id(user_id)
                if public_id:
                    # Invalidate both caches to be safe
                    await self.overlord.buffer_memory.kv_delete(
                        public_id, namespace="user_synopsis_identity"
                    )
                    await self.overlord.buffer_memory.kv_delete(
                        public_id, namespace="user_synopsis_context"
                    )
            except Exception:
                pass  # Cache invalidation failure is non-critical

        #  Info - TODO: add observability
        # ConversationEvents.MEMORY_LONG_TERM_ENHANCED

        return context

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
        if not self.overlord.is_multi_user or not isinstance(
            self.overlord.long_term_memory, Memobase
        ):
            return False

        # Use external_user_id directly - no conversion needed
        context = await self.overlord.long_term_memory.clear_user_context(
            external_user_id=user_id, keys=keys
        )

        # Invalidate BOTH synopsis caches
        # Skip if synopsis is disabled
        persistent_config = self.overlord.formation_config.get("memory", {}).get("persistent", {})
        synopsis_config = persistent_config.get("user_synopsis", {})

        if synopsis_config.get("enabled", True) and self.overlord.buffer_memory:
            try:
                public_id = await self.overlord.long_term_memory.get_user_public_id(user_id)
                if public_id:
                    await self.overlord.buffer_memory.kv_delete(
                        public_id, namespace="user_synopsis_identity"
                    )
                    await self.overlord.buffer_memory.kv_delete(
                        public_id, namespace="user_synopsis_context"
                    )
            except Exception:
                pass

        #  Info - TODO: add observability
        # ConversationEvents.MEMORY_WORKING_UPDATED

        return context

    async def invalidate_identity_synopsis_cache(self, user_id: Any) -> None:
        """
        Invalidate identity synopsis cache for a user.

        Called when identity collections (user_identity, relationships, work_projects)
        are updated by extraction or other means.

        Args:
            user_id: External user ID
        """
        # Check if synopsis is enabled
        persistent_config = self.overlord.formation_config.get("memory", {}).get("persistent", {})
        synopsis_config = persistent_config.get("user_synopsis", {})

        if not synopsis_config.get("enabled", True):
            return  # Skip if disabled

        if not self.overlord.buffer_memory:
            return

        try:
            internal_user_id = await self.overlord.long_term_memory.get_user_id(user_id)
            if internal_user_id:
                await self.overlord.buffer_memory.kv_delete(
                    internal_user_id, namespace="user_synopsis_identity"
                )
        except Exception:
            pass  # Cache invalidation failure is non-critical

    async def get_user_synopsis(self, external_user_id: str) -> str:
        """
        Get two-tier LLM-synthesized user synopsis for enhanced messages.

        Combines two synopsis tiers with different caching strategies:
        - Identity Synopsis: Stable info (identity, relationships, projects) with
          permanent cache + explicit invalidation
        - Context Synopsis: Dynamic info (preferences, activities) with configurable TTL

        Args:
            external_user_id: The external user identifier

        Returns:
            Combined synopsis string, or empty string if no context exists

        Example output:
            "Ran Aroussi is the Founder of MUXI AI, working with the engineering team.
            He prefers concise, technical communication and is currently focused on
            implementing the user synopsis feature."
        """
        # Check if synopsis is enabled in formation config
        persistent_config = self.overlord.formation_config.get("memory", {}).get("persistent", {})
        synopsis_config = persistent_config.get("user_synopsis", {})

        if not synopsis_config.get("enabled", True):  # Default: enabled
            return ""

        # Get both synopsis tiers
        identity_synopsis = await self._get_identity_synopsis(external_user_id)
        context_synopsis = await self._get_context_synopsis(external_user_id)

        # Combine results
        parts = []
        if identity_synopsis:
            parts.append(identity_synopsis)
        if context_synopsis:
            parts.append(context_synopsis)

        return " ".join(parts) if parts else ""

    async def _get_identity_synopsis(self, external_user_id: str) -> str:
        """
        Get identity synopsis (permanent cache + explicit invalidation).

        Queries: user_identity, relationships, work_projects
        Cache: Permanent (ttl=None), invalidated when these collections update

        Returns:
            Identity synopsis or empty string
        """
        # Get TTL from formation config (for empty cache only)
        persistent_config = self.overlord.formation_config.get("memory", {}).get("persistent", {})
        synopsis_config = persistent_config.get("user_synopsis", {})
        cache_ttl = synopsis_config.get("cache_ttl", 3600)  # Default: 1 hour

        # Get user_id for cache key
        try:
            user_id = await self.overlord.long_term_memory.get_user_id(external_user_id)
            if not user_id:
                return ""
        except Exception:
            return ""

        # Check cache
        if self.overlord.buffer_memory:
            try:
                cached = await self.overlord.buffer_memory.kv_get(
                    user_id, namespace="user_synopsis_identity"
                )
                if cached is not None:
                    return cached
            except Exception:
                pass

        # Prerequisites check
        if (
            not self.overlord.is_multi_user
            or not self.overlord.persistent_memory_manager
            or external_user_id == "0"
        ):
            return ""

        try:
            # Query identity collections
            identity_collections = ["user_identity", "relationships", "work_projects"]
            identity_memories = []

            for collection in identity_collections:
                try:
                    results = await self.overlord.persistent_memory_manager.search_long_term_memory(
                        query="",
                        k=3,
                        user_id=external_user_id,
                        collections=[collection],
                    )
                    if results:
                        identity_memories.extend(results)
                except Exception:
                    continue

            if not identity_memories:
                # Cache empty result with configured TTL (may get identity data soon)
                if self.overlord.buffer_memory:
                    try:
                        await self.overlord.buffer_memory.kv_set(
                            user_id, "", ttl=cache_ttl, namespace="user_synopsis_identity"
                        )
                    except Exception:
                        pass
                return ""

            # Format for LLM
            memory_texts = []
            for mem in identity_memories[:10]:
                content = mem.get("text", "")
                if content:
                    memory_texts.append(f"- {content}")

            if not memory_texts:
                return ""

            # Synthesize with LLM
            synopsis = await self._synthesize_synopsis_with_llm(
                memory_texts, synopsis_type="identity"
            )

            if synopsis:
                # Cache permanently (invalidate explicitly)
                if self.overlord.buffer_memory:
                    try:
                        await self.overlord.buffer_memory.kv_set(
                            user_id, synopsis, ttl=None, namespace="user_synopsis_identity"
                        )
                    except Exception:
                        pass
                return synopsis

            return ""

        except Exception:
            return ""

    async def _get_context_synopsis(self, external_user_id: str) -> str:
        """
        Get context synopsis (configurable TTL for auto-refresh).

        Queries: preferences, activities
        Cache: Configurable TTL (default 1 hour, auto-invalidates)

        Returns:
            Context synopsis or empty string
        """
        # Get TTL from formation config
        persistent_config = self.overlord.formation_config.get("memory", {}).get("persistent", {})
        synopsis_config = persistent_config.get("user_synopsis", {})
        cache_ttl = synopsis_config.get("cache_ttl", 3600)  # Default: 1 hour

        # Get user_id for cache key
        try:
            user_id = await self.overlord.long_term_memory.get_user_id(external_user_id)
            if not user_id:
                return ""
        except Exception:
            return ""

        # Check cache
        if self.overlord.buffer_memory:
            try:
                cached = await self.overlord.buffer_memory.kv_get(
                    user_id, namespace="user_synopsis_context"
                )
                if cached is not None:
                    return cached
            except Exception:
                pass

        # Prerequisites check
        if (
            not self.overlord.is_multi_user
            or not self.overlord.persistent_memory_manager
            or external_user_id == "0"
        ):
            return ""

        try:
            # Query context collections
            context_collections = ["preferences", "activities"]
            context_memories = []

            for collection in context_collections:
                try:
                    results = await self.overlord.persistent_memory_manager.search_long_term_memory(
                        query="",
                        k=3,
                        user_id=external_user_id,
                        collections=[collection],
                    )
                    if results:
                        context_memories.extend(results)
                except Exception:
                    continue

            if not context_memories:
                # Cache empty result with configured TTL
                if self.overlord.buffer_memory:
                    try:
                        await self.overlord.buffer_memory.kv_set(
                            user_id, "", ttl=cache_ttl, namespace="user_synopsis_context"
                        )
                    except Exception:
                        pass
                return ""

            # Format for LLM
            memory_texts = []
            for mem in context_memories[:10]:
                content = mem.get("text", "")
                if content:
                    memory_texts.append(f"- {content}")

            if not memory_texts:
                return ""

            # Synthesize with LLM
            synopsis = await self._synthesize_synopsis_with_llm(
                memory_texts, synopsis_type="context"
            )

            if synopsis:
                # Cache with configured TTL
                if self.overlord.buffer_memory:
                    try:
                        await self.overlord.buffer_memory.kv_set(
                            user_id, synopsis, ttl=cache_ttl, namespace="user_synopsis_context"
                        )
                    except Exception:
                        pass
                return synopsis

            return ""

        except Exception:
            return ""

    async def _synthesize_synopsis_with_llm(
        self, memory_texts: list, synopsis_type: str = "combined"
    ) -> str:
        """
        Use LLM to synthesize user memories into coherent synopsis.

        Args:
            memory_texts: List of formatted memory strings
            synopsis_type: Type of synopsis ("identity", "context", or "combined")

        Returns:
            LLM-synthesized synopsis or empty string on failure
        """
        if not memory_texts or not self.overlord.extraction_model:
            return ""

        # Build synthesis prompt based on type
        memories_str = "\n".join(memory_texts)

        if synopsis_type == "identity":
            prompt = f"""You are analyzing user identity information. Below are facts about a user:

{memories_str}

Synthesize these facts into 1-2 natural sentences about who they are. Focus ONLY on:
- Name, role, occupation
- Team/relationships
- Work projects

Write in third person. Be concise and factual.

Identity Synopsis:"""
        elif synopsis_type == "context":
            prompt = f"""You are analyzing user preferences and activities. Below are facts about a user:

{memories_str}

Synthesize these facts into 1-2 natural sentences about their current context. Focus ONLY on:
- Communication preferences and style
- Current activities and interests
- Recent focus areas

Write in third person. Be concise and factual. Use present tense.

Context Synopsis:"""
        else:
            # Combined fallback (shouldn't be used with two-tier system)
            prompt = f"""You are analyzing user profile information. Below are facts about a user:

{memories_str}

Synthesize these facts into a coherent, natural 2-3 sentence user profile summary. Focus on:
- Who they are (name, role, identity)
- Key preferences and communication style
- Current activities or projects

Write in third person. Be concise and factual. If contradictory, use recent facts.

User Synopsis:"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.overlord.extraction_model.chat(
                messages, temperature=0.3, max_tokens=100
            )
            content = response.content if hasattr(response, "content") else str(response)

            # Clean up the response
            synopsis = content.strip()
            if synopsis:
                return synopsis

        except Exception:
            # LLM synthesis failed - return empty string
            pass

        return ""
