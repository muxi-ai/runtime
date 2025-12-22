"""
User context management for the Overlord.

This module handles user context memory operations including getting, adding,
and clearing user-specific context information.
"""

from typing import Any


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
                    # Get ALL recent memories from collection (no semantic search/embeddings needed)
                    results = self.overlord.long_term_memory.get_recent_memories(
                        limit=10,
                        collection=collection,
                        external_user_id=external_user_id
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
                    # Get ALL recent memories from collection (no semantic search/embeddings needed)
                    results = self.overlord.long_term_memory.get_recent_memories(
                        limit=10,
                        collection=collection,
                        external_user_id=external_user_id
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

        # Build synthesis prompt based on type - separate system and user content
        memories_str = "\n".join(memory_texts)

        if synopsis_type == "identity":
            system_prompt = """You are analyzing user identity information.
Synthesize the facts into 1-2 natural sentences about who they are. Focus ONLY on:
- Name, role, occupation
- Team/relationships
- Work projects

Write in third person. Be concise and factual."""
        elif synopsis_type == "context":
            system_prompt = """You are analyzing user preferences and activities.
Synthesize the facts into 1-2 natural sentences about their current context. Focus ONLY on:
- Communication preferences and style
- Current activities and interests
- Recent focus areas

Write in third person. Be concise and factual. Use present tense."""
        else:
            # Combined fallback (shouldn't be used with two-tier system)
            system_prompt = """You are analyzing user profile information.
Synthesize the facts into a coherent, natural 2-3 sentence user profile summary. Focus on:
- Who they are (name, role, identity)
- Key preferences and communication style
- Current activities or projects

Write in third person. Be concise and factual. If contradictory, use recent facts."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Facts about the user:\n{memories_str}"},
            ]
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
