"""
Caching layer for scheduler operations to reduce redundant computations.

This module provides intelligent caching for expensive operations like
LLM calls, cron expression parsing, and job type detection.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from functools import lru_cache
import time
import hashlib
from croniter import croniter

from ...services import observability


class SchedulerCache:
    """
    Intelligent caching system for scheduler operations.

    Provides caching for:
    - LLM job type detection results
    - Parsed cron expressions
    - Job execution history
    - Schedule text parsing results
    """

    def __init__(self, cache_ttl: int = 300, max_cache_size: int = 1000):
        """
        Initialize the scheduler cache.

        Args:
            cache_ttl: Time-to-live for cache entries in seconds (default: 5 minutes)
            max_cache_size: Maximum number of entries per cache (default: 1000)
        """
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size

        # Different caches for different types of data
        self._job_type_cache: Dict[str, Dict[str, Any]] = {}
        self._parse_result_cache: Dict[str, Dict[str, Any]] = {}
        self._execution_cache: Dict[str, Dict[str, Any]] = {}

        # Cache statistics
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _generate_cache_key(self, *args) -> str:
        """
        Generate a cache key from arguments.

        Args:
            *args: Arguments to hash

        Returns:
            Cache key string
        """
        key_data = "|".join(str(arg) for arg in args)
        return hashlib.md5(key_data.encode()).hexdigest()

    def _is_cache_valid(self, entry: Dict[str, Any]) -> bool:
        """
        Check if a cache entry is still valid.

        Args:
            entry: Cache entry to check

        Returns:
            True if entry is valid, False otherwise
        """
        if not entry:
            return False

        age = time.time() - entry.get("timestamp", 0)
        return age < self.cache_ttl

    def _evict_oldest_entries(self, cache: Dict[str, Dict[str, Any]]) -> None:
        """
        Evict oldest entries when cache is full.

        Args:
            cache: Cache dictionary to evict from
        """
        if len(cache) < self.max_cache_size:
            return

        # Sort by timestamp and remove oldest 10%
        sorted_entries = sorted(cache.items(), key=lambda x: x[1].get("timestamp", 0))

        evict_count = max(1, len(cache) // 10)
        for key, _ in sorted_entries[:evict_count]:
            del cache[key]
            self._stats["evictions"] += 1

    # Job type detection caching
    def get_cached_job_type(self, schedule_text: str) -> Optional[str]:
        """
        Get cached job type detection result.

        Args:
            schedule_text: The schedule text to look up

        Returns:
            Cached job type if available and valid, None otherwise
        """
        cache_key = self._generate_cache_key("job_type", schedule_text)
        entry = self._job_type_cache.get(cache_key)

        if self._is_cache_valid(entry):
            self._stats["hits"] += 1
            return entry["result"]

        self._stats["misses"] += 1
        return None

    def cache_job_type(self, schedule_text: str, job_type: str) -> None:
        """
        Cache a job type detection result.

        Args:
            schedule_text: The schedule text
            job_type: The detected job type
        """
        self._evict_oldest_entries(self._job_type_cache)

        cache_key = self._generate_cache_key("job_type", schedule_text)
        self._job_type_cache[cache_key] = {"result": job_type, "timestamp": time.time()}

    # Parse result caching
    def get_cached_parse_result(self, schedule_text: str) -> Optional[Dict[str, Any]]:
        """
        Get cached schedule parsing result.

        Args:
            schedule_text: The schedule text to look up

        Returns:
            Cached parse result if available and valid, None otherwise
        """
        cache_key = self._generate_cache_key("parse", schedule_text)
        entry = self._parse_result_cache.get(cache_key)

        if self._is_cache_valid(entry):
            self._stats["hits"] += 1
            return entry["result"]

        self._stats["misses"] += 1
        return None

    def cache_parse_result(self, schedule_text: str, parse_result: Dict[str, Any]) -> None:
        """
        Cache a schedule parsing result.

        Args:
            schedule_text: The schedule text
            parse_result: The parsing result
        """
        self._evict_oldest_entries(self._parse_result_cache)

        cache_key = self._generate_cache_key("parse", schedule_text)
        self._parse_result_cache[cache_key] = {"result": parse_result, "timestamp": time.time()}

    # Execution history caching
    def get_last_execution(self, job_id: str) -> Optional[datetime]:
        """
        Get cached last execution time for a job.

        Args:
            job_id: The job ID to look up

        Returns:
            Last execution time if cached, None otherwise
        """
        entry = self._execution_cache.get(job_id)

        if self._is_cache_valid(entry):
            return entry["last_execution"]

        return None

    def update_execution_time(self, job_id: str, execution_time: datetime) -> None:
        """
        Update cached execution time for a job.

        Args:
            job_id: The job ID
            execution_time: The execution time
        """
        self._evict_oldest_entries(self._execution_cache)

        self._execution_cache[job_id] = {"last_execution": execution_time, "timestamp": time.time()}

    # Cron expression parsing cache
    @lru_cache(maxsize=500)
    def parse_cron_expression(self, expr: str) -> Optional[croniter]:
        """
        Parse and cache cron expressions.

        Uses functools.lru_cache for efficient caching of parsed expressions.

        Args:
            expr: Cron expression to parse

        Returns:
            Parsed croniter object or None if invalid
        """
        try:
            return croniter(expr)
        except (ValueError, TypeError) as e:
            # Log the specific error for debugging
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.DEBUG,
                data={
                    "expression": expr,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                },
                description=f"Failed to parse cron expression: {expr}"
            )
            return None

    # Cache management
    def clear_cache(self, cache_type: Optional[str] = None) -> None:
        """
        Clear cache entries.

        Args:
            cache_type: Specific cache to clear, or None to clear all
        """
        if cache_type == "job_type" or cache_type is None:
            self._job_type_cache.clear()

        if cache_type == "parse" or cache_type is None:
            self._parse_result_cache.clear()

        if cache_type == "execution" or cache_type is None:
            self._execution_cache.clear()

        if cache_type == "cron" or cache_type is None:
            self.parse_cron_expression.cache_clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_entries = (
            len(self._job_type_cache) + len(self._parse_result_cache) + len(self._execution_cache)
        )

        hit_rate = 0.0
        total_requests = self._stats["hits"] + self._stats["misses"]
        if total_requests > 0:
            hit_rate = self._stats["hits"] / total_requests

        return {
            "total_entries": total_entries,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "hit_rate": hit_rate,
            "cache_sizes": {
                "job_type": len(self._job_type_cache),
                "parse": len(self._parse_result_cache),
                "execution": len(self._execution_cache),
                "cron": self.parse_cron_expression.cache_info().currsize,
            },
        }

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        removed = 0
        current_time = time.time()

        # Clean up each cache
        for cache in [self._job_type_cache, self._parse_result_cache, self._execution_cache]:
            expired_keys = [
                key
                for key, entry in cache.items()
                if current_time - entry.get("timestamp", 0) > self.cache_ttl
            ]

            for key in expired_keys:
                del cache[key]
                removed += 1

        if removed > 0:
            observability.observe(
                event_type=observability.SystemEvents.SCHEDULER_CACHE_CLEANUP,
                level=observability.EventLevel.DEBUG,
                data={"removed_entries": removed},
                description=f"Cleaned up {removed} expired cache entries",
            )

        return removed
