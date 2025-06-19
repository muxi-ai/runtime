"""
Intelligent Caching & Memory Optimization for MUXI Overlord

This module provides multi-layer caching capabilities with intelligent eviction
policies, semantic similarity matching, and memory optimization.

Key Components:
- IntelligentCacheManager: Multi-layer caching with L1/L2/L3 cache levels
- CacheHitAnalyzer: Cache performance analytics and monitoring
- MemoryOptimizer: Automatic memory management and cleanup
- Various cache implementations: LRUCache, TTLCache, SizeBasedCache, etc.
"""

from .cache_manager import IntelligentCacheManager
from .analytics import CacheHitAnalyzer
from .memory_optimizer import MemoryOptimizer
from ...datatypes.caching import (
    CacheType,
    CachedResponse,
    CacheKey,
    CacheStatistics,
    MemoryStats,
)
from .implementations import (
    LRUCache,
    TTLCache,
    SizeBasedCache,
    PersistentCache,
    SemanticCache,
)

__all__ = [
    "IntelligentCacheManager",
    "CacheHitAnalyzer",
    "MemoryOptimizer",
    "CacheType",
    "CachedResponse",
    "CacheKey",
    "CacheStatistics",
    "MemoryStats",
    "LRUCache",
    "TTLCache",
    "SizeBasedCache",
    "PersistentCache",
    "SemanticCache",
]
