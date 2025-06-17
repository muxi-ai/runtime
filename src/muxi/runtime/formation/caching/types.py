"""
Cache data types and structures for the intelligent caching system.

This module defines the core data structures used throughout the caching system,
including cache types, cached responses, cache keys, and statistics.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CacheType(Enum):
    """Types of cache hits for analytics tracking."""

    EXACT = "exact"  # L1: Exact match cache hit
    SIMILAR = "similar"  # L2: Semantic similarity cache hit
    PARTIAL = "partial"  # L3: Partial workflow cache hit
    MISS = "miss"  # Cache miss, full execution required


@dataclass
class CacheKey:
    """
    Composite cache key with request fingerprinting and context hashing.

    The cache key combines multiple factors to ensure accurate cache matching
    while accounting for context variations that might affect the response.
    """

    request_fingerprint: str  # Hash of normalized request content
    context_hash: str  # Hash of relevant context variables
    user_id: Optional[int] = None  # User identifier for personalized caching
    agent_id: Optional[str] = None  # Agent identifier for agent-specific caching

    def __str__(self) -> str:
        """Generate string representation for cache storage."""
        parts = [self.request_fingerprint, self.context_hash]
        if self.user_id is not None:
            parts.append(f"user:{self.user_id}")
        if self.agent_id:
            parts.append(f"agent:{self.agent_id}")
        return ":".join(parts)

    def __hash__(self) -> int:
        """Enable use as dictionary key."""
        return hash(str(self))


@dataclass
class CachedResponse:
    """
    Cached response with metadata for intelligent retrieval and validation.

    Contains the cached response data along with metadata needed for cache
    validation, similarity matching, and performance optimization.
    """

    content: str  # The cached response content
    response_type: str  # Type of response (text, workflow, etc.)
    interactive_elements: List[Dict] = field(default_factory=list)  # UI elements
    media_content: List[Dict] = field(default_factory=list)  # Media attachments

    # Cache metadata
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: Optional[int] = None  # Time to live in seconds
    access_count: int = 0  # Number of times accessed
    last_accessed: float = field(default_factory=time.time)

    # Similarity matching metadata
    embedding: Optional[List[float]] = None  # Semantic embedding for similarity
    context_fingerprint: str = ""  # Context signature for matching

    # Quality metrics
    quality_score: float = 1.0  # Response quality (0.0-1.0)
    user_feedback: Optional[str] = None  # User feedback on response

    # Workflow metadata (for partial workflow caching)
    workflow_id: Optional[str] = None  # Original workflow identifier
    task_results: Dict[str, Any] = field(default_factory=dict)  # Task outputs

    def is_valid(self) -> bool:
        """Check if cached response is still valid."""
        if self.ttl_seconds is None:
            return True  # No expiration

        age_seconds = time.time() - self.timestamp
        return age_seconds < self.ttl_seconds

    def age_seconds(self) -> float:
        """Get age of cached response in seconds."""
        return time.time() - self.timestamp

    def increment_access(self) -> None:
        """Record cache access for analytics."""
        self.access_count += 1
        self.last_accessed = time.time()


@dataclass
class CacheStatistics:
    """
    Cache performance statistics for monitoring and optimization.

    Tracks hit rates, miss rates, performance metrics, and other analytics
    data for cache performance monitoring and optimization.
    """

    # Hit/miss counters
    exact_hits: int = 0
    similar_hits: int = 0
    partial_hits: int = 0
    misses: int = 0

    # Performance metrics
    total_requests: int = 0
    total_response_time_saved: float = 0.0  # Milliseconds saved by caching
    average_similarity_score: float = 0.0  # Average similarity for L2 hits

    # Cache efficiency
    cache_size_bytes: int = 0  # Total cache size in bytes
    eviction_count: int = 0  # Number of cache evictions
    cleanup_count: int = 0  # Number of memory cleanups

    # Time tracking
    start_time: float = field(default_factory=time.time)
    last_reset: float = field(default_factory=time.time)

    @property
    def total_hits(self) -> int:
        """Total cache hits across all levels."""
        return self.exact_hits + self.similar_hits + self.partial_hits

    @property
    def hit_rate(self) -> float:
        """Overall cache hit rate (0.0-1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.total_hits / self.total_requests

    @property
    def miss_rate(self) -> float:
        """Overall cache miss rate (0.0-1.0)."""
        return 1.0 - self.hit_rate

    @property
    def exact_hit_rate(self) -> float:
        """L1 exact match hit rate (0.0-1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.exact_hits / self.total_requests

    @property
    def similar_hit_rate(self) -> float:
        """L2 semantic similarity hit rate (0.0-1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.similar_hits / self.total_requests

    @property
    def partial_hit_rate(self) -> float:
        """L3 partial workflow hit rate (0.0-1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.partial_hits / self.total_requests

    def record_hit(self, cache_type: CacheType, response_time_saved: float = 0.0) -> None:
        """Record a cache hit of the specified type."""
        self.total_requests += 1
        self.total_response_time_saved += response_time_saved

        if cache_type == CacheType.EXACT:
            self.exact_hits += 1
        elif cache_type == CacheType.SIMILAR:
            self.similar_hits += 1
        elif cache_type == CacheType.PARTIAL:
            self.partial_hits += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.total_requests += 1
        self.misses += 1

    def record_eviction(self) -> None:
        """Record a cache eviction event."""
        self.eviction_count += 1

    def record_cleanup(self, bytes_freed: int) -> None:
        """Record a memory cleanup event."""
        self.cleanup_count += 1
        self.cache_size_bytes = max(0, self.cache_size_bytes - bytes_freed)

    def reset_statistics(self) -> None:
        """Reset all statistics counters."""
        self.exact_hits = 0
        self.similar_hits = 0
        self.partial_hits = 0
        self.misses = 0
        self.total_requests = 0
        self.total_response_time_saved = 0.0
        self.eviction_count = 0
        self.cleanup_count = 0
        self.last_reset = time.time()

    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive statistics summary."""
        uptime_hours = (time.time() - self.start_time) / 3600

        return {
            "hit_rate": round(self.hit_rate * 100, 2),
            "miss_rate": round(self.miss_rate * 100, 2),
            "exact_hit_rate": round(self.exact_hit_rate * 100, 2),
            "similar_hit_rate": round(self.similar_hit_rate * 100, 2),
            "partial_hit_rate": round(self.partial_hit_rate * 100, 2),
            "total_requests": self.total_requests,
            "total_hits": self.total_hits,
            "total_misses": self.misses,
            "response_time_saved_ms": round(self.total_response_time_saved, 2),
            "cache_size_mb": round(self.cache_size_bytes / (1024 * 1024), 2),
            "evictions": self.eviction_count,
            "cleanups": self.cleanup_count,
            "uptime_hours": round(uptime_hours, 2),
            "requests_per_hour": round(self.total_requests / max(uptime_hours, 0.001), 2),
        }


@dataclass
class MemoryStats:
    """
    Memory usage statistics for the caching system.

    Tracks memory consumption across different cache levels and provides
    insights for memory optimization decisions.
    """

    # Memory usage by cache level
    l1_memory_bytes: int = 0  # L1 exact match cache memory
    l2_memory_bytes: int = 0  # L2 semantic similarity cache memory
    l3_memory_bytes: int = 0  # L3 partial workflow cache memory
    embeddings_memory_bytes: int = 0  # Embedding storage memory

    # Overall memory metrics
    total_memory_bytes: int = 0  # Total cache memory usage
    peak_memory_bytes: int = 0  # Peak memory usage observed
    memory_limit_bytes: int = 0  # Configured memory limit

    # Memory events
    cleanup_events: int = 0  # Number of memory cleanup events
    oom_warnings: int = 0  # Out of memory warnings
    eviction_events: int = 0  # Cache evictions due to memory pressure

    # Timing
    last_cleanup: float = 0.0  # Timestamp of last memory cleanup
    last_update: float = field(default_factory=time.time)

    @property
    def total_memory_mb(self) -> float:
        """Total memory usage in megabytes."""
        return self.total_memory_bytes / (1024 * 1024)

    @property
    def memory_utilization(self) -> float:
        """Memory utilization percentage (0.0-1.0)."""
        if self.memory_limit_bytes == 0:
            return 0.0
        return self.total_memory_bytes / self.memory_limit_bytes

    @property
    def is_memory_pressure(self) -> bool:
        """Check if system is under memory pressure (>80% utilization)."""
        return self.memory_utilization > 0.8

    def update_memory_usage(
        self, l1_bytes: int = 0, l2_bytes: int = 0, l3_bytes: int = 0, embeddings_bytes: int = 0
    ) -> None:
        """Update memory usage statistics."""
        self.l1_memory_bytes = l1_bytes
        self.l2_memory_bytes = l2_bytes
        self.l3_memory_bytes = l3_bytes
        self.embeddings_memory_bytes = embeddings_bytes

        self.total_memory_bytes = l1_bytes + l2_bytes + l3_bytes + embeddings_bytes
        self.peak_memory_bytes = max(self.peak_memory_bytes, self.total_memory_bytes)
        self.last_update = time.time()

    def record_cleanup(self, bytes_freed: int) -> None:
        """Record a memory cleanup event."""
        self.cleanup_events += 1
        self.last_cleanup = time.time()

    def record_oom_warning(self) -> None:
        """Record an out-of-memory warning."""
        self.oom_warnings += 1

    def record_eviction(self) -> None:
        """Record a cache eviction due to memory pressure."""
        self.eviction_events += 1

    def get_summary(self) -> Dict[str, Any]:
        """Get memory statistics summary."""
        return {
            "total_memory_mb": round(self.total_memory_mb, 2),
            "peak_memory_mb": round(self.peak_memory_bytes / (1024 * 1024), 2),
            "memory_limit_mb": round(self.memory_limit_bytes / (1024 * 1024), 2),
            "utilization_percent": round(self.memory_utilization * 100, 2),
            "l1_memory_mb": round(self.l1_memory_bytes / (1024 * 1024), 2),
            "l2_memory_mb": round(self.l2_memory_bytes / (1024 * 1024), 2),
            "l3_memory_mb": round(self.l3_memory_bytes / (1024 * 1024), 2),
            "embeddings_memory_mb": round(self.embeddings_memory_bytes / (1024 * 1024), 2),
            "cleanup_events": self.cleanup_events,
            "oom_warnings": self.oom_warnings,
            "eviction_events": self.eviction_events,
            "is_memory_pressure": self.is_memory_pressure,
        }
