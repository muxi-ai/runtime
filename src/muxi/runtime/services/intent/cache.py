"""
Intent Detection Cache

LRU cache for intent detection results to avoid redundant LLM calls.
"""

from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict
import threading

from ...datatypes.intent import IntentResult


class IntentCache:
    """Thread-safe LRU cache for intent detection results."""

    def __init__(self, ttl: int = 3600, max_size: int = 10000):
        """
        Initialize intent cache.

        Args:
            ttl: Time to live in seconds (default: 1 hour)
            max_size: Maximum cache size (default: 10000 entries)
        """
        self.ttl = timedelta(seconds=ttl)
        self.max_size = max_size
        self._cache: OrderedDict[str, Tuple[IntentResult, datetime]] = OrderedDict()
        self._lock = threading.Lock()

        # Statistics
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[IntentResult]:
        """
        Get cached intent result.

        Args:
            key: Cache key

        Returns:
            Cached IntentResult or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                self.misses += 1
                return None

            result, timestamp = self._cache[key]

            # Check if expired
            if datetime.now() - timestamp > self.ttl:
                del self._cache[key]
                self.misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self.hits += 1
            return result

    def set(self, key: str, result: IntentResult) -> None:
        """
        Set cache entry.

        Args:
            key: Cache key
            result: Intent detection result
        """
        with self._lock:
            # Remove oldest if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._cache.popitem(last=False)

            self._cache[key] = (result, datetime.now())
            self._cache.move_to_end(key)

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    def clear_by_intent_type(self, intent_type: str) -> int:
        """
        Clear cache entries by intent type.

        Args:
            intent_type: Intent type to clear

        Returns:
            Number of entries cleared
        """
        with self._lock:
            keys_to_remove = []
            for key, (result, _) in self._cache.items():
                if result.intent_type.value == intent_type:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]

            return len(keys_to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0.0

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "ttl_seconds": self.ttl.total_seconds(),
            }

    def cleanup_expired(self) -> int:
        """
        Remove expired entries.

        Returns:
            Number of entries removed
        """
        with self._lock:
            now = datetime.now()
            keys_to_remove = []

            for key, (_, timestamp) in self._cache.items():
                if now - timestamp > self.ttl:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]

            return len(keys_to_remove)
