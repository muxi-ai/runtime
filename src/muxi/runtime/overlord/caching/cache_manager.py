"""
Intelligent Cache Manager for the MUXI Overlord system.

This module provides the main cache manager that orchestrates multi-layer caching
with intelligent eviction policies, semantic similarity matching, and automatic
memory optimization.
"""

import hashlib
import json

import time
from typing import Any, Dict, List, Optional

from .cache_types import CacheKey, CachedResponse, CacheType, CacheStatistics
from .implementations import LRUCache, SizeBasedCache, PersistentCache, SemanticCache
from .analytics import CacheHitAnalyzer
from .memory_optimizer import MemoryOptimizer


class IntelligentCacheManager:
    """
    Multi-layer intelligent cache manager with semantic similarity and automatic optimization.

    Provides L1 exact match caching, L2 semantic similarity caching, and L3 partial
    workflow caching with intelligent eviction policies and memory optimization.
    """

    def __init__(
        self,
        l1_max_size: int = 1000,
        l2_max_size: int = 500,
        l3_max_memory_mb: int = 100,
        persistent_db_path: str = "cache/persistent.db",
        similarity_threshold: float = 0.85,
        default_ttl_seconds: int = 3600,
        enable_analytics: bool = True,
        enable_memory_optimization: bool = True,
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize intelligent cache manager.

        Args:
            l1_max_size: Maximum number of items in L1 cache
            l2_max_size: Maximum number of items in L2 semantic cache
            l3_max_memory_mb: Maximum memory usage for L3 cache in MB
            persistent_db_path: Path to persistent cache database
            similarity_threshold: Minimum similarity score for L2 matches
            default_ttl_seconds: Default TTL for cached items
            enable_analytics: Whether to enable cache analytics
            enable_memory_optimization: Whether to enable memory optimization
            embedding_service: Service for generating embeddings
        """
        self.similarity_threshold = similarity_threshold
        self.default_ttl_seconds = default_ttl_seconds
        self.embedding_service = embedding_service

        # Initialize cache layers
        self.l1_cache = LRUCache(max_size=l1_max_size)  # Exact match cache
        self.l2_cache = SemanticCache(
            max_size=l2_max_size, similarity_threshold=similarity_threshold
        )  # Semantic similarity
        self.l3_cache = SizeBasedCache(max_memory_mb=l3_max_memory_mb)  # Partial workflow cache
        self.persistent_cache = PersistentCache(db_path=persistent_db_path)  # Long-term storage

        # Cache layer names for analytics
        self.cache_layers = {
            "L1": self.l1_cache,
            "L2": self.l2_cache,
            "L3": self.l3_cache,
            "persistent": self.persistent_cache,
        }

        # Analytics and optimization
        self.analytics = None
        self.memory_optimizer = None

        if enable_analytics:
            self.analytics = CacheHitAnalyzer()
            for name, cache in self.cache_layers.items():
                self.analytics.register_cache_component(name, cache)

        if enable_memory_optimization:
            self.memory_optimizer = MemoryOptimizer()
            for name, cache in self.cache_layers.items():
                self.memory_optimizer.register_cache_component(name, cache)

        # Performance tracking
        self.statistics = CacheStatistics()
        self.request_count = 0

        #  Cache manager info - add observability event

    async def start(self) -> None:
        """Start analytics and memory optimization services."""
        if self.analytics:
            await self.analytics.start_collection()

        if self.memory_optimizer:
            await self.memory_optimizer.start()

        #  Cache manager info - add observability event

    async def stop(self) -> None:
        """Stop analytics and memory optimization services."""
        if self.analytics:
            await self.analytics.stop_collection()

        if self.memory_optimizer:
            await self.memory_optimizer.stop()

        #  Cache manager info - add observability event

    async def get_cached_response(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> Optional[CachedResponse]:
        """
        Intelligent cache retrieval with multi-layer checking.

        Args:
            user_message: User's message/request
            context: Request context
            user_id: User identifier
            agent_id: Agent identifier

        Returns:
            Cached response if found, None otherwise
        """
        start_time = time.time()
        self.request_count += 1

        # Generate cache key
        cache_key = self._generate_cache_key(user_message, context, user_id, agent_id)
        cache_key_str = str(cache_key)

        # L1: Exact match cache
        l1_response = await self.l1_cache.get(cache_key_str)
        if l1_response and l1_response.is_valid():
            response_time_ms = (time.time() - start_time) * 1000
            self._record_cache_hit("L1", CacheType.EXACT, response_time_ms, cache_key_str)
            #  Cache manager debug - add observability event
            return l1_response

        # L2: Semantic similarity cache
        if self.embedding_service:
            try:
                query_embedding = await self._get_embedding(user_message)
                if query_embedding:
                    similar_responses = await self.l2_cache.find_similar(query_embedding, top_k=3)
                    if similar_responses:
                        best_match = similar_responses[0]  # (key, response, similarity)
                        if best_match[2] >= self.similarity_threshold:
                            response_time_ms = (time.time() - start_time) * 1000
                            self._record_cache_hit(
                                "L2", CacheType.SIMILAR, response_time_ms, cache_key_str
                            )
                            #  Cache manager debug - add observability event
                            return best_match[1]
            except Exception as e:
                #  Cache manager error - add observability event
                _ = e  # remove this after implementing observability

        # L3: Partial workflow cache (for workflow-based requests)
        l3_response = await self.l3_cache.get(cache_key_str)
        if l3_response and l3_response.is_valid():
            response_time_ms = (time.time() - start_time) * 1000
            self._record_cache_hit("L3", CacheType.PARTIAL, response_time_ms, cache_key_str)
            #  Cache manager debug - add observability event
            return l3_response

        # Persistent cache (last resort)
        persistent_response = await self.persistent_cache.get(cache_key_str)
        if persistent_response and persistent_response.is_valid():
            # Promote to L1 cache for faster future access
            await self.l1_cache.put(cache_key_str, persistent_response)
            response_time_ms = (time.time() - start_time) * 1000
            self._record_cache_hit("persistent", CacheType.EXACT, response_time_ms, cache_key_str)
            #  Cache manager debug - add observability event
            return persistent_response

        # Cache miss
        response_time_ms = (time.time() - start_time) * 1000
        self._record_cache_miss("overall", response_time_ms, cache_key_str)
        #  Cache manager debug - add observability event
        return None

    async def cache_response(
        self,
        user_message: str,
        response_content: str,
        response_type: str = "text",
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        interactive_elements: Optional[List[Dict]] = None,
        media_content: Optional[List[Dict]] = None,
        workflow_id: Optional[str] = None,
        task_results: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        quality_score: float = 1.0,
    ) -> bool:
        """
        Cache a response with intelligent layer placement.

        Args:
            user_message: Original user message
            response_content: Response content to cache
            response_type: Type of response
            context: Request context
            user_id: User identifier
            agent_id: Agent identifier
            interactive_elements: UI elements in response
            media_content: Media attachments
            workflow_id: Associated workflow ID
            task_results: Task execution results
            ttl_seconds: Time to live override
            quality_score: Response quality score

        Returns:
            True if successfully cached
        """
        start_time = time.time()

        # Generate cache key
        cache_key = self._generate_cache_key(user_message, context, user_id, agent_id)
        cache_key_str = str(cache_key)

        # Create cached response
        cached_response = CachedResponse(
            content=response_content,
            response_type=response_type,
            interactive_elements=interactive_elements or [],
            media_content=media_content or [],
            ttl_seconds=ttl_seconds or self.default_ttl_seconds,
            quality_score=quality_score,
            workflow_id=workflow_id,
            task_results=task_results or {},
        )

        # Generate embedding for semantic caching
        if self.embedding_service:
            try:
                embedding = await self._get_embedding(user_message)
                if embedding:
                    cached_response.embedding = embedding
            except Exception as e:
                #  Cache manager error - add observability event
                _ = e  # remove this after implementing observability

        # Cache in multiple layers
        success_count = 0

        # L1: Always cache for exact matches
        if await self.l1_cache.put(cache_key_str, cached_response):
            success_count += 1

        # L2: Cache with embedding if available
        if cached_response.embedding:
            if await self.l2_cache.put(cache_key_str, cached_response, cached_response.embedding):
                success_count += 1

        # L3: Cache if it's a workflow response
        if workflow_id or task_results:
            if await self.l3_cache.put(cache_key_str, cached_response):
                success_count += 1

        # Persistent: Cache high-quality responses
        if quality_score >= 0.8:
            if await self.persistent_cache.put(cache_key_str, cached_response):
                success_count += 1

        duration_ms = (time.time() - start_time) * 1000

        # Record analytics
        if self.analytics:
            self.analytics.record_cache_operation(
                operation="put",
                cache_component="intelligent_manager",
                duration_ms=duration_ms,
                success=success_count > 0,
                memory_usage_bytes=self._get_total_memory_usage(),
            )

        #  Cache manager debug - add observability event
        return success_count > 0

    async def invalidate_cache(
        self,
        user_message: Optional[str] = None,
        user_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        pattern: Optional[str] = None,
    ) -> int:
        """
        Invalidate cached entries based on criteria.

        Args:
            user_message: Specific message to invalidate
            user_id: User ID to invalidate all entries for
            agent_id: Agent ID to invalidate all entries for
            pattern: Pattern to match against cache keys

        Returns:
            Number of entries invalidated
        """
        invalidated_count = 0

        if user_message:
            # Invalidate specific entry
            cache_key = self._generate_cache_key(user_message, user_id=user_id, agent_id=agent_id)
            cache_key_str = str(cache_key)

            for cache in self.cache_layers.values():
                if await cache.remove(cache_key_str):
                    invalidated_count += 1

        # TODO: Implement pattern-based and user/agent-based invalidation
        # This would require iterating through cache entries and matching criteria

        #  Cache manager info - add observability event
        return invalidated_count

    async def cleanup_expired(self) -> Dict[str, int]:
        """
        Clean up expired entries from all cache layers.

        Returns:
            Dictionary with cleanup counts per layer
        """
        cleanup_results = {}

        for name, cache in self.cache_layers.items():
            if hasattr(cache, "cleanup_expired"):
                try:
                    cleaned = await cache.cleanup_expired()
                    cleanup_results[name] = cleaned
                    if cleaned > 0:
                        #  Cache manager info - add observability event
                        _ = None  # remove this after implementing observability
                except Exception as e:
                    #  Cache manager error - add observability event
                    _ = e  # remove this after implementing observability
                    cleanup_results[name] = 0
            else:
                cleanup_results[name] = 0

        return cleanup_results

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        stats = {
            "overall": {
                "total_requests": self.request_count,
                "total_memory_usage_bytes": self._get_total_memory_usage(),
                "cache_layers": len(self.cache_layers),
            },
            "layers": {},
        }

        # Get statistics for each layer
        for name, cache in self.cache_layers.items():
            layer_stats = {
                "size": cache.size() if hasattr(cache, "size") else 0,
                "memory_usage_bytes": (
                    cache.get_memory_usage() if hasattr(cache, "get_memory_usage") else 0
                ),
                "type": type(cache).__name__,
            }
            stats["layers"][name] = layer_stats

        # Add analytics data if available
        if self.analytics:
            stats["hit_rate_summary"] = self.analytics.get_hit_rate_summary(24)
            stats["performance_summary"] = self.analytics.get_performance_summary(24)
            stats["recommendations"] = self.analytics.get_optimization_recommendations()

        # Add memory optimizer data if available
        if self.memory_optimizer:
            stats["memory_optimization"] = self.memory_optimizer.get_performance_summary()

        return stats

    async def force_memory_cleanup(self) -> Dict[str, Any]:
        """Force immediate memory cleanup across all cache layers."""
        if self.memory_optimizer:
            result_stats = await self.memory_optimizer.force_cleanup()
            #  Cache manager info - add observability event
            return result_stats.get_summary()
        else:
            #  Cache manager warning - add observability event
            return {}

    def _generate_cache_key(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> CacheKey:
        """
        Generate a composite cache key for the request.

        Args:
            user_message: User's message
            context: Request context
            user_id: User identifier
            agent_id: Agent identifier

        Returns:
            Composite cache key
        """
        # Normalize user message for consistent hashing
        normalized_message = user_message.lower().strip()
        request_fingerprint = hashlib.sha256(normalized_message.encode()).hexdigest()[:16]

        # Generate context hash
        context_data = context or {}
        # Remove volatile context elements that shouldn't affect caching
        stable_context = {
            k: v
            for k, v in context_data.items()
            if k not in ["timestamp", "request_id", "session_id"]
        }
        context_str = json.dumps(stable_context, sort_keys=True)
        context_hash = hashlib.sha256(context_str.encode()).hexdigest()[:16]

        return CacheKey(
            request_fingerprint=request_fingerprint,
            context_hash=context_hash,
            user_id=user_id,
            agent_id=agent_id,
        )

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding for text using the embedding service.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if service unavailable
        """
        if not self.embedding_service:
            return None

        try:
            if hasattr(self.embedding_service, "embed"):
                return await self.embedding_service.embed(text)
            elif hasattr(self.embedding_service, "get_embedding"):
                return await self.embedding_service.get_embedding(text)
            else:
                #  Cache manager warning - add observability event
                return None
        except Exception as e:
            #  Cache manager error - add observability event
            _ = e  # remove this after implementing observability
            return None

    def _get_total_memory_usage(self) -> int:
        """Get total memory usage across all cache layers."""
        total = 0
        for cache in self.cache_layers.values():
            if hasattr(cache, "get_memory_usage"):
                total += cache.get_memory_usage()
        return total

    def _record_cache_hit(
        self, layer: str, cache_type: CacheType, response_time_ms: float, cache_key: str
    ) -> None:
        """Record a cache hit for analytics."""
        self.statistics.record_hit(cache_type, response_time_ms)

        if self.analytics:
            self.analytics.record_cache_hit(
                cache_layer=layer,
                cache_type=cache_type,
                response_time_ms=response_time_ms,
                cache_key=cache_key,
            )

    def _record_cache_miss(self, layer: str, response_time_ms: float, cache_key: str) -> None:
        """Record a cache miss for analytics."""
        self.statistics.record_miss()

        if self.analytics:
            self.analytics.record_cache_miss(
                cache_layer=layer, response_time_ms=response_time_ms, cache_key=cache_key
            )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
