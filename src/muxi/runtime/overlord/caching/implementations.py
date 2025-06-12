"""
Cache implementation classes for the intelligent caching system.

This module provides various cache implementations with different eviction policies
and optimization strategies for the multi-layer caching system.
"""

import asyncio
import hashlib
import json
import pickle
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy.spatial.distance import cosine

from .cache_types import CachedResponse, CacheKey


class LRUCache:
    """
    Least Recently Used (LRU) cache implementation.

    Automatically evicts the least recently used items when capacity is reached.
    Ideal for L1 exact match caching where access patterns matter more than age.
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of items to store
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, CachedResponse] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CachedResponse]:
        """Get item from cache and mark as recently used."""
        async with self._lock:
            if key in self.cache:
                # Move to end (most recent)
                response = self.cache.pop(key)
                self.cache[key] = response
                response.increment_access()
                return response
            return None

    async def put(self, key: str, response: CachedResponse) -> bool:
        """Put item in cache, evicting LRU item if necessary."""
        async with self._lock:
            if key in self.cache:
                # Update existing item
                self.cache.pop(key)
            elif len(self.cache) >= self.max_size:
                # Remove least recently used item
                self.cache.popitem(last=False)

            self.cache[key] = response
            return True

    async def remove(self, key: str) -> bool:
        """Remove item from cache."""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all items from cache."""
        async with self._lock:
            self.cache.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)

    def get_memory_usage(self) -> int:
        """Estimate memory usage in bytes."""
        total_bytes = 0
        for key, response in self.cache.items():
            # Estimate key size
            total_bytes += len(key.encode('utf-8'))
            # Estimate response size
            total_bytes += len(response.content.encode('utf-8'))
            total_bytes += len(json.dumps(response.interactive_elements).encode('utf-8'))
            total_bytes += len(json.dumps(response.media_content).encode('utf-8'))
            # Add metadata overhead
            total_bytes += 200  # Rough estimate for metadata
        return total_bytes


class TTLCache:
    """
    Time-To-Live (TTL) cache implementation.

    Automatically expires items after a specified time period.
    Ideal for workflow and response caching where freshness is important.
    """

    def __init__(self, max_size: int = 500, default_ttl: int = 3600):
        """
        Initialize TTL cache.

        Args:
            max_size: Maximum number of items to store
            default_ttl: Default TTL in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: Dict[str, CachedResponse] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CachedResponse]:
        """Get item from cache if not expired."""
        async with self._lock:
            if key in self.cache:
                response = self.cache[key]
                if response.is_valid():
                    response.increment_access()
                    return response
                else:
                    # Remove expired item
                    del self.cache[key]
            return None

    async def put(
        self,
        key: str,
        response: CachedResponse,
        ttl: Optional[int] = None
    ) -> bool:
        """Put item in cache with TTL."""
        async with self._lock:
            # Set TTL if not already set
            if response.ttl_seconds is None:
                response.ttl_seconds = ttl or self.default_ttl

            # Remove expired items if at capacity
            if len(self.cache) >= self.max_size:
                await self._cleanup_expired()

                # If still at capacity, remove oldest items
                if len(self.cache) >= self.max_size:
                    oldest_keys = sorted(
                        self.cache.keys(),
                        key=lambda k: self.cache[k].timestamp
                    )
                    for old_key in oldest_keys[:len(self.cache) - self.max_size + 1]:
                        del self.cache[old_key]

            self.cache[key] = response
            return True

    async def remove(self, key: str) -> bool:
        """Remove item from cache."""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all items from cache."""
        async with self._lock:
            self.cache.clear()

    async def cleanup_expired(self) -> int:
        """Remove expired items and return count removed."""
        async with self._lock:
            return await self._cleanup_expired()

    async def _cleanup_expired(self) -> int:
        """Internal method to clean up expired items."""
        expired_keys = [
            key for key, response in self.cache.items()
            if not response.is_valid()
        ]
        for key in expired_keys:
            del self.cache[key]
        return len(expired_keys)

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)

    def get_memory_usage(self) -> int:
        """Estimate memory usage in bytes."""
        total_bytes = 0
        for key, response in self.cache.items():
            total_bytes += len(key.encode('utf-8'))
            total_bytes += len(response.content.encode('utf-8'))
            total_bytes += len(json.dumps(response.interactive_elements).encode('utf-8'))
            total_bytes += len(json.dumps(response.media_content).encode('utf-8'))
            total_bytes += 200  # Metadata overhead
        return total_bytes


class SizeBasedCache:
    """
    Size-based cache with memory limits.

    Evicts items when memory usage exceeds the limit, prioritizing older items.
    Ideal for large responses and media content caching.
    """

    def __init__(self, max_memory_mb: int = 100):
        """
        Initialize size-based cache.

        Args:
            max_memory_mb: Maximum memory usage in megabytes
        """
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: Dict[str, CachedResponse] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CachedResponse]:
        """Get item from cache."""
        async with self._lock:
            if key in self.cache:
                response = self.cache[key]
                response.increment_access()
                return response
            return None

    async def put(self, key: str, response: CachedResponse) -> bool:
        """Put item in cache, managing memory usage."""
        async with self._lock:
            # Calculate size of new item
            item_size = self._calculate_item_size(key, response)

            # If item is too large, reject it
            if item_size > self.max_memory_bytes:
                return False

            # Free up memory if needed
            current_usage = self.get_memory_usage()
            while current_usage + item_size > self.max_memory_bytes and self.cache:
                # Remove oldest item
                oldest_key = min(
                    self.cache.keys(),
                    key=lambda k: self.cache[k].timestamp
                )
                del self.cache[oldest_key]
                current_usage = self.get_memory_usage()

            self.cache[key] = response
            return True

    async def remove(self, key: str) -> bool:
        """Remove item from cache."""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all items from cache."""
        async with self._lock:
            self.cache.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)

    def get_memory_usage(self) -> int:
        """Get current memory usage in bytes."""
        total_bytes = 0
        for key, response in self.cache.items():
            total_bytes += self._calculate_item_size(key, response)
        return total_bytes

    def _calculate_item_size(self, key: str, response: CachedResponse) -> int:
        """Calculate size of cache item in bytes."""
        size = len(key.encode('utf-8'))
        size += len(response.content.encode('utf-8'))
        size += len(json.dumps(response.interactive_elements).encode('utf-8'))
        size += len(json.dumps(response.media_content).encode('utf-8'))
        if response.embedding:
            size += len(response.embedding) * 4  # 4 bytes per float
        size += 200  # Metadata overhead
        return size


class PersistentCache:
    """
    Persistent cache using SQLite for storage.

    Survives application restarts and provides durable caching.
    Ideal for embeddings and long-term workflow results.
    """

    def __init__(self, db_path: str = "cache/persistent.db"):
        """
        Initialize persistent cache.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    response_type TEXT NOT NULL,
                    interactive_elements TEXT,
                    media_content TEXT,
                    timestamp REAL NOT NULL,
                    ttl_seconds INTEGER,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL,
                    embedding BLOB,
                    context_fingerprint TEXT,
                    quality_score REAL DEFAULT 1.0,
                    workflow_id TEXT,
                    task_results TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON cache_entries(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ttl ON cache_entries(ttl_seconds)
            """)

    async def get(self, key: str) -> Optional[CachedResponse]:
        """Get item from persistent cache."""
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM cache_entries WHERE key = ?", (key,)
                )
                row = cursor.fetchone()

                if row:
                    response = self._row_to_response(row)
                    if response.is_valid():
                        response.increment_access()
                        # Update access count in database
                        conn.execute(
                            "UPDATE cache_entries SET access_count = ?, last_accessed = ? WHERE key = ?",
                            (response.access_count, response.last_accessed, key)
                        )
                        return response
                    else:
                        # Remove expired item
                        conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))

                return None

    async def put(self, key: str, response: CachedResponse) -> bool:
        """Put item in persistent cache."""
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # Serialize complex fields
                interactive_elements_json = json.dumps(response.interactive_elements)
                media_content_json = json.dumps(response.media_content)
                task_results_json = json.dumps(response.task_results)
                embedding_blob = None
                if response.embedding:
                    embedding_blob = pickle.dumps(response.embedding)

                conn.execute("""
                    INSERT OR REPLACE INTO cache_entries (
                        key, content, response_type, interactive_elements, media_content,
                        timestamp, ttl_seconds, access_count, last_accessed,
                        embedding, context_fingerprint, quality_score,
                        workflow_id, task_results
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    key, response.content, response.response_type,
                    interactive_elements_json, media_content_json,
                    response.timestamp, response.ttl_seconds,
                    response.access_count, response.last_accessed,
                    embedding_blob, response.context_fingerprint,
                    response.quality_score, response.workflow_id,
                    task_results_json
                ))
                return True

    async def remove(self, key: str) -> bool:
        """Remove item from persistent cache."""
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                return cursor.rowcount > 0

    async def clear(self) -> None:
        """Clear all items from persistent cache."""
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cache_entries")

    async def cleanup_expired(self) -> int:
        """Remove expired items from persistent cache."""
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                current_time = time.time()
                cursor = conn.execute("""
                    DELETE FROM cache_entries
                    WHERE ttl_seconds IS NOT NULL
                    AND (timestamp + ttl_seconds) < ?
                """, (current_time,))
                return cursor.rowcount

    def size(self) -> int:
        """Get current cache size."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cache_entries")
            return cursor.fetchone()[0]

    def get_memory_usage(self) -> int:
        """Get database file size as memory usage estimate."""
        return self.db_path.stat().st_size if self.db_path.exists() else 0

    def _row_to_response(self, row: sqlite3.Row) -> CachedResponse:
        """Convert database row to CachedResponse object."""
        embedding = None
        if row['embedding']:
            embedding = pickle.loads(row['embedding'])

        return CachedResponse(
            content=row['content'],
            response_type=row['response_type'],
            interactive_elements=json.loads(row['interactive_elements'] or '[]'),
            media_content=json.loads(row['media_content'] or '[]'),
            timestamp=row['timestamp'],
            ttl_seconds=row['ttl_seconds'],
            access_count=row['access_count'],
            last_accessed=row['last_accessed'],
            embedding=embedding,
            context_fingerprint=row['context_fingerprint'] or '',
            quality_score=row['quality_score'],
            workflow_id=row['workflow_id'],
            task_results=json.loads(row['task_results'] or '{}')
        )


class SemanticCache:
    """
    Semantic similarity cache using vector embeddings.

    Finds similar cached responses using cosine similarity on embeddings.
    Ideal for L2 semantic similarity matching in the cache hierarchy.
    """

    def __init__(
        self,
        max_size: int = 500,
        similarity_threshold: float = 0.85,
        embedding_dim: int = 1536
    ):
        """
        Initialize semantic cache.

        Args:
            max_size: Maximum number of cached items
            similarity_threshold: Minimum similarity score for matches (0.0-1.0)
            embedding_dim: Dimension of embeddings
        """
        self.max_size = max_size
        self.similarity_threshold = similarity_threshold
        self.embedding_dim = embedding_dim
        self.cache: Dict[str, CachedResponse] = {}
        self.embeddings: Dict[str, np.ndarray] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CachedResponse]:
        """Get exact match from cache."""
        async with self._lock:
            if key in self.cache:
                response = self.cache[key]
                response.increment_access()
                return response
            return None

    async def find_similar(
        self,
        query_embedding: List[float],
        top_k: int = 3
    ) -> List[Tuple[str, CachedResponse, float]]:
        """
        Find similar cached responses using cosine similarity.

        Args:
            query_embedding: Query embedding vector
            top_k: Maximum number of similar items to return

        Returns:
            List of (key, response, similarity_score) tuples
        """
        async with self._lock:
            if not self.embeddings:
                return []

            query_vec = np.array(query_embedding)
            similarities = []

            for key, cached_embedding in self.embeddings.items():
                if key in self.cache:
                    similarity = 1 - cosine(query_vec, cached_embedding)
                    if similarity >= self.similarity_threshold:
                        similarities.append((key, self.cache[key], similarity))

            # Sort by similarity score (descending)
            similarities.sort(key=lambda x: x[2], reverse=True)

            # Update access counts for returned items
            for key, response, _ in similarities[:top_k]:
                response.increment_access()

            return similarities[:top_k]

    async def put(
        self,
        key: str,
        response: CachedResponse,
        embedding: Optional[List[float]] = None
    ) -> bool:
        """Put item in semantic cache with embedding."""
        async with self._lock:
            # Use provided embedding or extract from response
            if embedding:
                response.embedding = embedding

            if not response.embedding:
                return False  # Cannot cache without embedding

            # Remove oldest items if at capacity
            if len(self.cache) >= self.max_size and key not in self.cache:
                oldest_key = min(
                    self.cache.keys(),
                    key=lambda k: self.cache[k].timestamp
                )
                del self.cache[oldest_key]
                del self.embeddings[oldest_key]

            self.cache[key] = response
            self.embeddings[key] = np.array(response.embedding)
            return True

    async def remove(self, key: str) -> bool:
        """Remove item from semantic cache."""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
                del self.embeddings[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all items from semantic cache."""
        async with self._lock:
            self.cache.clear()
            self.embeddings.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)

    def get_memory_usage(self) -> int:
        """Estimate memory usage in bytes."""
        total_bytes = 0

        # Cache content
        for key, response in self.cache.items():
            total_bytes += len(key.encode('utf-8'))
            total_bytes += len(response.content.encode('utf-8'))
            total_bytes += len(json.dumps(response.interactive_elements).encode('utf-8'))
            total_bytes += len(json.dumps(response.media_content).encode('utf-8'))
            total_bytes += 200  # Metadata overhead

        # Embeddings
        total_bytes += len(self.embeddings) * self.embedding_dim * 4  # 4 bytes per float

        return total_bytes
