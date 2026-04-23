# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        SQLite Memory - Local Vector Database
# Description:  Lightweight vector database using SQLite for memory storage
# Role:         Provides local-first vector storage with minimal dependencies
# Usage:        Used when PostgreSQL is unavailable or for edge deployments
# Author:       Muxi Framework Team
#
# The SQLite Memory module provides a lightweight implementation of vector-based
# memory storage using SQLite with the sqlite-vec extension. Key features include:
#
# 1. Local-First Vector Storage
#    - No external database requirements
#    - Efficient storage in a single SQLite file
#    - Vector operations via the sqlite-vec extension
#
# 2. Compatibility with Core Memory APIs
#    - Implements the BaseMemory interface
#    - Similar API to LongTermMemory
#    - Collection-based organization
#
# 3. Lightweight Deployment
#    - Minimal dependencies
#    - Suitable for edge devices
#    - Self-contained database file
#
# This implementation provides a balance between the features of a full vector
# database and the simplicity of local file storage, making it ideal for
# smaller deployments or environments where PostgreSQL is not available.
# =============================================================================

import asyncio
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from ...extensions import SQLiteVecExtension
from ...utils.fastjson import json
from .. import observability
from .base import BaseMemory
from .embedding import DEFAULT_EMBEDDING_MODEL, embed, probe_dimension


class SQLiteMemory(BaseMemory):
    """
    SQLite-based long-term memory implementation.

    This class provides a persistent vector database using SQLite with the
    sqlite-vec extension for storing and retrieving information based on
    semantic similarity. It offers a lightweight alternative to the PostgreSQL-
    based LongTermMemory with similar capabilities.
    """

    def __init__(
        self,
        db_path: str,
        formation_id: str,
        dimension: int = 1536,  # Retained for backwards compat; real dim probed lazily.
        default_collection: str = "default",
        extensions_dir: str = "extensions",
        embedding_model: Optional[str] = None,
    ):
        """
        Initialize a local SQLite-based vector memory store.

        The embedding dimension is **probed lazily** on the first embed
        operation via
        :func:`services.memory.embedding.probe_dimension`; construction
        does NOT invoke OneLLM. The dim-specific ``memories_{dim}`` table
        is created on first ``_ensure_dim()`` call — base tables
        (``users``, ``user_identifiers``, ``collections``) are still
        created in the constructor so single-user bootstrap works.

        Parameters
        ----------
        db_path:
            Path to the SQLite database file.
        formation_id:
            Identifier used to scope data within the database.
        dimension:
            Provisional dimension hint retained for backwards
            compatibility. Ignored once :meth:`_ensure_dim` resolves the
            real dim from the configured embedding model.
        default_collection:
            Name of the default collection. Defaults to ``"default"``.
        extensions_dir:
            Directory containing sqlite-vec extensions. Defaults to
            ``"extensions"``.
        embedding_model:
            Provider-prefixed embedding model slug (e.g.
            ``"local/nomic-ai/nomic-embed-text-v1.5"``,
            ``"openai/text-embedding-3-small"``). When ``None``, defaults
            to :data:`~services.memory.embedding.DEFAULT_EMBEDDING_MODEL`.
        """
        self.db_path = db_path
        self.formation_id = formation_id
        self.default_collection = default_collection
        self.extensions_dir = extensions_dir

        # Resolve the embedding model slug. The old local/cloud
        # dispatch that accepted an LLM instance is gone — every caller
        # passes a slug string, and embedding generation flows through
        # the shared ``embedding.embed`` helper.
        if embedding_model is None:
            embedding_model = DEFAULT_EMBEDDING_MODEL
        if not isinstance(embedding_model, str):
            raise TypeError(
                "SQLiteMemory(embedding_model=...) must be a provider-prefixed "
                f"slug string, got {type(embedding_model).__name__}"
            )
        self._embedding_model_name: str = embedding_model

        # Lazy-dim: populated on first ``_ensure_dim()`` call, never in
        # ctor. ``self.dimension`` keeps the provisional hint for any
        # pre-probe introspection, but the authoritative dim is
        # ``self._dimension`` (set under the lock by ``_ensure_dim``).
        self._dimension: Optional[int] = None
        self._dim_lock = asyncio.Lock()
        self.dimension = dimension
        # ``memories_table`` is set once ``_ensure_dim`` resolves the
        # real dim. Sync read paths guard against the ``None`` case.
        self.memories_table: Optional[str] = None

        # Create database directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        # Initialize base schema — users, user_identifiers, collections
        # only. The dim-specific memories table is created lazily by
        # ``_ensure_dim`` once the real embedding dim is known.
        self.conn = self._init_database()

    @property
    def embedding_model_name(self) -> str:
        """Public accessor for the configured embedding model slug.

        Exposes the provider-prefixed slug string (e.g.
        ``"local/nomic-ai/nomic-embed-text-v1.5"``,
        ``"openai/text-embedding-3-small"``) used by this memory
        instance for embedding generation. External consumers should
        read this public property instead of reaching into the private
        ``_embedding_model_name`` attribute.
        """
        return self._embedding_model_name

    async def _ensure_dim(self) -> int:
        """Probe the embedding dimension exactly once and memoize it.

        On first invocation this calls
        :func:`services.memory.embedding.probe_dimension` for the
        configured model slug, stores the result on
        ``self._dimension``, sets ``self.memories_table`` to
        ``f"memories_{dim}"``, and creates the corresponding table
        (idempotent via ``CREATE TABLE IF NOT EXISTS``).

        Concurrent callers are serialized by ``self._dim_lock`` so only
        a single underlying ``probe_dimension`` call is issued even
        when multiple coroutines hit this method simultaneously on a
        fresh instance.
        """
        if self._dimension is not None:
            return self._dimension

        async with self._dim_lock:
            # Re-check under the lock — another coroutine may have
            # probed while we were queued on ``acquire``.
            if self._dimension is not None:
                return self._dimension

            probed = await probe_dimension(self._embedding_model_name)
            self._dimension = probed
            self.dimension = probed
            self.memories_table = f"memories_{probed}"
            self._create_memories_table()
            return probed

    def _create_memories_table(self) -> None:
        """Create the dim-specific ``memories_{dim}`` table and its companions.

        Creates the memory table (BLOB-packed float32 embeddings), the
        five secondary indexes, the FTS5 virtual table, and the FTS
        sync + updated_at triggers. Mirrors the pre-created ``memories_{dim}``
        tables from ``migrations/init_schema_sqlite.sql`` so that a
        runtime-created dim (any dim outside the pre-baked
        ``{384, 768, 1024, 1536, 3072}`` set) ends up with the same
        feature set.

        All statements use ``IF NOT EXISTS`` so re-opening a DB that
        already has the table (the common case on the pre-baked dims)
        is a safe no-op.
        """
        assert self.memories_table is not None, "_ensure_dim must set memories_table first"
        table = self.memories_table
        fts = f"{table}_fts"
        # Core memories table
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                collection TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """)
        # Secondary indexes (match init_schema_sqlite.sql)
        self.conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_collection ON {table}(collection)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_created_at ON {table}(created_at)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_updated_at ON {table}(updated_at)"
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_user_created_at "
            f"ON {table}(user_id, created_at)"
        )
        # FTS5 virtual table + sync triggers (full-text search parity
        # with the PostgreSQL GIN index on the equivalent dim table).
        self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {fts} USING fts5(
                text,
                content='{table}',
                content_rowid='rowid'
            )
            """)
        self.conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_fts_insert
            AFTER INSERT ON {table} BEGIN
                INSERT INTO {fts}(rowid, text) VALUES (new.rowid, new.text);
            END
            """)
        self.conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_fts_delete
            AFTER DELETE ON {table} BEGIN
                DELETE FROM {fts} WHERE rowid = old.rowid;
            END
            """)
        self.conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_fts_update
            AFTER UPDATE ON {table} BEGIN
                DELETE FROM {fts} WHERE rowid = old.rowid;
                INSERT INTO {fts}(rowid, text) VALUES (new.rowid, new.text);
            END
            """)
        # updated_at trigger (parity with init_schema_sqlite.sql).
        self.conn.execute(f"""
            CREATE TRIGGER IF NOT EXISTS trigger_update_{table}_updated_at
            AFTER UPDATE ON {table}
            FOR EACH ROW
            BEGIN
                UPDATE {table} SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END
            """)
        self.conn.commit()

    async def get_or_create_user(self, identifier: str) -> int:
        """
        Get or create a user by identifier.

        Args:
            identifier: The user identifier (email, Slack ID, etc.)

        Returns:
            The internal database user ID
        """
        # Look up via user_identifiers table
        cursor = self.conn.execute(
            "SELECT user_id FROM user_identifiers WHERE identifier = ? AND formation_id = ?",
            (identifier, self.formation_id),
        )
        user_row = cursor.fetchone()

        if user_row:
            return user_row[0]

        # Create new user + identifier
        public_id = self._generate_id()
        self.conn.execute(
            "INSERT INTO users (public_id, formation_id) VALUES (?, ?)",
            (public_id, self.formation_id),
        )

        # Get the new user ID
        cursor = self.conn.execute("SELECT last_insert_rowid()")
        user_id = cursor.fetchone()[0]

        # Create identifier mapping
        self.conn.execute(
            "INSERT INTO user_identifiers (user_id, identifier, formation_id) VALUES (?, ?, ?)",
            (user_id, identifier, self.formation_id),
        )
        self.conn.commit()

        return user_id

    def _init_database(self) -> sqlite3.Connection:
        """
        Initialize the SQLite database with required tables.

        This method sets up the SQLite database, loads the sqlite-vec
        extension, and creates the necessary tables for storing memories
        and collections.

        Returns:
            A configured SQLite connection ready for use

        Raises:
            ImportError: If the sqlite-vec extension is not available
        """
        conn = sqlite3.connect(self.db_path)

        # Load sqlite-vec extension using the extension system
        try:
            SQLiteVecExtension.load_extension(conn)
        except ImportError:
            # If extension system not available, raise an error
            raise ImportError(
                "SQLiteVecExtension not available. Please install it with:"
                " pip install muxi-extensions-sqlite-vec"
            )

        # Create tables. Keep the schema identical to
        # migrations/init_schema_sqlite.sql so a DB seeded by the migration
        # and then opened by the runtime has the same constraints either
        # way (CREATE TABLE IF NOT EXISTS skips ALTER, so divergence here
        # silently produced weaker-or-stronger uniqueness depending on
        # which path created the table first).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL UNIQUE,
                formation_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create user_identifiers table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_identifiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                identifier TEXT NOT NULL,
                identifier_type TEXT,
                formation_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(identifier, formation_id)
            )
        """)

        # Create indexes for user_identifiers
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_identifiers_identifier "
            "ON user_identifiers(identifier, formation_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_identifiers_user_id "
            "ON user_identifiers(user_id)"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(name, user_id)
            )
        """)

        # NOTE: The dim-specific ``memories_{dim}`` table is created by
        # ``_ensure_dim()`` on the first embed operation — at ctor time
        # we have only a provisional dim hint, not the real probed dim.

        # Create default user and collection if they don't exist
        self._ensure_default_user(conn)

        conn.commit()
        return conn

    def _ensure_default_user(self, conn: sqlite3.Connection) -> None:
        """
        Ensure default user exists for single-user mode.
        """
        # Default user ID for single-user mode - use "0" to match orchestrator override
        default_user_id = "0"
        # Check if user exists
        cursor = conn.execute(
            "SELECT u.id FROM users u "
            "JOIN user_identifiers ui ON u.id = ui.user_id "
            "WHERE ui.identifier = ? AND ui.formation_id = ?",
            (default_user_id, self.formation_id),
        )
        user_row = cursor.fetchone()

        if not user_row:
            # Create default user
            public_id = self._generate_id()
            conn.execute(
                "INSERT INTO users (public_id, formation_id) VALUES (?, ?)",
                (public_id, self.formation_id),
            )
            # Also create user_identifier entry
            conn.execute(
                "INSERT INTO user_identifiers (user_id, identifier, formation_id) "
                "SELECT id, ?, ? FROM users WHERE public_id = ? AND formation_id = ?",
                (default_user_id, self.formation_id, public_id, self.formation_id),
            )
            cursor = conn.execute(
                "SELECT u.id FROM users u "
                "JOIN user_identifiers ui ON u.id = ui.user_id "
                "WHERE ui.identifier = ? AND ui.formation_id = ?",
                (default_user_id, self.formation_id),
            )
            user_row = cursor.fetchone()

        self.default_user_id = user_row[0]

        # Create default collection for this user
        cursor = conn.execute(
            "SELECT id FROM collections WHERE name = ? AND user_id = ?",
            (self.default_collection, self.default_user_id),
        )
        if not cursor.fetchone():
            conn.execute(
                "INSERT INTO collections (id, user_id, name, description) VALUES (?, ?, ?, ?)",
                (
                    self._generate_id(),
                    self.default_user_id,
                    self.default_collection,
                    "Default collection for memories",
                ),
            )

    def _generate_id(self, size: int = 21) -> str:
        """
        Generate a unique ID for memories and collections.

        This method creates a unique nanoid for database records.

        Args:
            size: The character length of the generated ID

        Returns:
            A unique string identifier
        """
        import nanoid

        return nanoid.generate(size=size)

    async def add(  # type: ignore[override]
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        collection: Optional[str] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
    ) -> str:
        """
        Add content to memory.

        Generates an embedding via the shared
        :func:`services.memory.embedding.embed` helper when one is not
        supplied, then persists the text + float32 BLOB embedding in the
        dim-specific ``memories_{dim}`` table.

        Args:
            content: The text content to store.
            metadata: Optional metadata to associate with the content.
            user_id: Optional user identifier for multi-user support.
            collection: Optional collection name.
            embedding: Optional pre-computed embedding. When provided,
                the shared helper is bypassed but ``_ensure_dim()`` is
                still invoked so the dim-specific table exists.

        Returns:
            The ID of the newly created memory entry.
        """
        if metadata is None:
            metadata = {}

        # Use provided collection or default
        if collection is None:
            collection = self.default_collection

        # Always ensure the probed-dim table exists before writing. The
        # probe is memoized, so this is cheap after the first call.
        await self._ensure_dim()

        # Generate embedding if not provided. Write paths use
        # ``task="search_document"`` — the Nomic-style prefix marks the
        # input as a corpus document. The helper strips the kwarg for
        # cloud providers that don't honor it.
        if embedding is None:
            vectors = await embed(
                self._embedding_model_name,
                content,
                task="search_document",
            )
            embedding = vectors[0]

        # Add timestamp to metadata
        metadata["timestamp"] = time.time()

        # Get or create user if provided
        if user_id:
            internal_user_id = await self.get_or_create_user(user_id)
        else:
            internal_user_id = self.default_user_id

        # Add to database and return memory ID
        memory_id = self._add_internal(content, embedding, metadata, collection, internal_user_id)
        return memory_id

    def _add_internal(
        self,
        text: str,
        embedding: Union[List[float], np.ndarray],
        metadata: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """
        Internal method to add a memory to the database.

        This synchronous method handles the actual storage of memory
        in the SQLite database with proper type handling.

        Args:
            text: The text content to store
            embedding: The vector embedding of the text
            metadata: Optional metadata to associate with the content
            collection: Optional collection name

        Returns:
            The ID of the newly created memory entry
        """
        # Convert numpy array to bytes for SQLite storage
        if isinstance(embedding, np.ndarray):
            embedding_bytes = embedding.astype(np.float32).tobytes()
        else:
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

        # Use default collection and user if none specified
        collection = collection or self.default_collection
        user_id = user_id or self.default_user_id

        # Generate memory ID
        memory_id = self._generate_id()

        # Insert memory
        self.conn.execute(
            f"""
            INSERT INTO {self.memories_table}
            (id, user_id, collection, text, embedding, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                user_id,
                collection,
                text,
                embedding_bytes,
                metadata and json.dumps(metadata),
            ),
        )
        self.conn.commit()

        return memory_id

    async def search(
        self,
        query: str,
        limit: int = 5,
        query_embedding: Optional[Union[List[float], np.ndarray]] = None,
        user_id: Optional[str] = None,
        collection: Optional[str] = None,
        collections: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar content in memory.

        This method performs a semantic similarity search for content matching
        the query, using the embedding provider to generate query embeddings.

        Args:
            query: The text query to search for
            limit: Maximum number of results to return
            query_embedding: Optional pre-computed embedding for the query
            user_id: Optional user ID for filtering
            collection: Optional collection name to filter results
            collections: Optional collection names to search in one query

        Returns:
            List of dictionaries containing the search results with content and metadata
        """
        # Always ensure the probed-dim table exists before querying;
        # probe is memoized after first invocation.
        await self._ensure_dim()

        # Generate embedding for query if not provided. Search paths use
        # ``task="search_query"`` — the Nomic-style prefix marks the
        # input as a retrieval query; the helper strips the kwarg for
        # cloud providers that don't honor it.
        if query_embedding is None:
            vectors = await embed(
                self._embedding_model_name,
                query,
                task="search_query",
            )
            query_embedding = vectors[0]

        # Get or create user if provided
        internal_user_id = None
        if user_id:
            internal_user_id = await self.get_or_create_user(user_id)

        # Search with embedding (filter by collection if specified)
        results = self._search_internal(
            query_embedding,
            limit,
            collection=collection,
            collections=collections,
            user_id=internal_user_id,
        )

        # Format results
        formatted_results = []
        for score, memory in results:
            formatted_results.append(
                {
                    "text": memory["text"],  # Use "text" key to match LongTermMemory format
                    "metadata": memory["metadata"] if "metadata" in memory else {},
                    "score": score,
                }
            )

        return formatted_results

    def build_search_parameters(
        self,
        query: str,
        k: int = 5,
        user_id: Optional[str] = None,
        full_filter: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
        collections: Optional[List[str]] = None,
        query_embedding: Optional[Union[List[float], np.ndarray]] = None,
    ) -> Dict[str, Any]:
        """
        Build search parameters for the SQLiteMemory search method.

        Args:
            query: The search query text
            k: Number of results to return
            user_id: Optional user ID for filtering
            full_filter: Optional metadata filter (not used in SQLiteMemory)
            collection: Optional collection name (not used in SQLiteMemory public API)
            collections: Optional collection names
            query_embedding: Optional precomputed query embedding

        Returns:
            Dictionary of parameters for the search method
        """
        search_params = {
            "query": query,
            "limit": k,
        }

        if query_embedding is not None:
            search_params["query_embedding"] = query_embedding

        if user_id is not None:
            search_params["user_id"] = user_id

        if collections:
            search_params["collections"] = collections
        elif collection is not None:
            search_params["collection"] = collection

        return search_params

    def _search_internal(
        self,
        query_embedding: Union[List[float], np.ndarray],
        k: int = 5,
        collection: Optional[str] = None,
        collections: Optional[List[str]] = None,
        user_id: Optional[int] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Internal method to search for similar content.

        This synchronous method performs the actual vector similarity search
        in the SQLite database using cosine distance.

        Args:
            query_embedding: The query embedding vector
            k: Maximum number of results to return
            collection: Optional collection to search in
            collections: Optional collections to search in one query

        Returns:
            List of tuples containing (similarity_score, memory_dict)
        """
        # Convert numpy array to bytes for SQLite search
        if isinstance(query_embedding, np.ndarray):
            query_embedding_bytes = query_embedding.astype(np.float32).tobytes()
        else:
            query_embedding_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

        normalized_collections = list(
            dict.fromkeys(
                collection_name
                for collection_name in (collections or ([collection] if collection else []))
                if collection_name
            )
        )

        # Build query with JOIN to ensure formation isolation
        # Search across ALL collections if collection is None
        if normalized_collections and user_id:
            placeholders = ", ".join("?" for _ in normalized_collections)
            query = f"""
                SELECT
                    m.id,
                    m.text,
                    m.metadata,
                    m.created_at,
                    vec_distance_cosine(m.embedding, ?) as score
                FROM {self.memories_table} m
                JOIN users u ON m.user_id = u.id
                WHERE m.collection IN ({placeholders})
                    AND m.user_id = ?
                    AND u.formation_id = ?
                ORDER BY score ASC
                LIMIT ?
            """
            params = (
                query_embedding_bytes,
                *normalized_collections,
                user_id,
                self.formation_id,
                k,
            )
        elif normalized_collections:
            placeholders = ", ".join("?" for _ in normalized_collections)
            # No user_id — single-user mode: search the given collection
            # across all users in this formation (only one user exists in
            # single-user deployments).
            query = f"""
                SELECT
                    m.id,
                    m.text,
                    m.metadata,
                    m.created_at,
                    vec_distance_cosine(m.embedding, ?) as score
                FROM {self.memories_table} m
                JOIN users u ON m.user_id = u.id
                WHERE m.collection IN ({placeholders})
                    AND u.formation_id = ?
                ORDER BY score ASC
                LIMIT ?
            """
            params = (query_embedding_bytes, *normalized_collections, self.formation_id, k)
        elif user_id:
            query = f"""
                SELECT
                    m.id,
                    m.text,
                    m.metadata,
                    m.created_at,
                    vec_distance_cosine(m.embedding, ?) as score
                FROM {self.memories_table} m
                JOIN users u ON m.user_id = u.id
                WHERE m.user_id = ?
                    AND u.formation_id = ?
                ORDER BY score ASC
                LIMIT ?
            """
            params = (query_embedding_bytes, user_id, self.formation_id, k)
        else:
            # No user_id and no collection — single-user mode: search all
            # memories in this formation regardless of user or collection.
            query = f"""
                SELECT
                    m.id,
                    m.text,
                    m.metadata,
                    m.created_at,
                    vec_distance_cosine(m.embedding, ?) as score
                FROM {self.memories_table} m
                JOIN users u ON m.user_id = u.id
                WHERE u.formation_id = ?
                ORDER BY score ASC
                LIMIT ?
            """
            params = (query_embedding_bytes, self.formation_id, k)

        # Execute search
        cursor = self.conn.execute(query, params)

        # Format results
        results = []
        for row in cursor.fetchall():
            metadata = json.loads(row[2]) if row[2] else {}
            # Convert distance to similarity score (1 - distance)
            similarity = 1.0 - float(row[4])
            results.append(
                (
                    similarity,  # similarity score (1 - cosine distance)
                    {
                        "id": row[0],
                        "text": row[1],
                        "metadata": metadata,
                        "created_at": row[3],
                    },
                )
            )

        return results

    def get(self, memory_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.

        This method fetches a single memory entry by its unique identifier.
        Returns ``None`` if the dim-specific ``memories_{dim}`` table has
        not yet been created (i.e. no async op has run yet and the dim
        is unresolved).

        Args:
            memory_id: The ID of the memory to retrieve

        Returns:
            The memory object if found, otherwise None
        """
        if self.memories_table is None:
            return None

        cursor = self.conn.execute(
            f"""
            SELECT m.id, m.text, m.metadata, m.created_at
            FROM {self.memories_table} m
            JOIN users u ON m.user_id = u.id
            WHERE m.id = ? AND u.formation_id = ?
            """,
            (memory_id, self.formation_id),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "text": row[1],
            "metadata": json.loads(row[2]) if row[2] else {},
            "created_at": row[3],
        }

    def get_recent_memories(
        self, limit: int = 10, collection: Optional[str] = None, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get the most recent memories.

        This method retrieves the most recently created memories from a
        specified collection, ordered by creation date.

        Args:
            limit: Maximum number of memories to return
            collection: Collection to retrieve memories from

        Returns:
            List of memories in reverse chronological order (newest first).
            Returns an empty list when the dim-specific
            ``memories_{dim}`` table has not yet been created (i.e. no
            async op has run yet and the dim is unresolved).
        """
        if self.memories_table is None:
            return []

        # Use defaults if not specified
        collection = collection or self.default_collection

        # Get internal user ID if external user ID provided
        if user_id:
            # Synchronous version of get_or_create_user
            cursor = self.conn.execute(
                "SELECT u.id FROM users u "
                "JOIN user_identifiers ui ON u.id = ui.user_id "
                "WHERE ui.identifier = ? AND ui.formation_id = ?",
                (user_id, self.formation_id),
            )
            user_row = cursor.fetchone()
            internal_user_id = user_row[0] if user_row else self.default_user_id
        else:
            internal_user_id = self.default_user_id

        # Ensure we're sorting by created_at in descending order (newest first)
        cursor = self.conn.execute(
            f"""
            SELECT m.id, m.text, m.metadata, m.created_at
            FROM {self.memories_table} m
            JOIN users u ON m.user_id = u.id
            WHERE m.collection = ?
                AND m.user_id = ?
                AND u.formation_id = ?
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (collection, internal_user_id, self.formation_id, limit),
        )

        # Parse results
        results = [
            {
                "id": row[0],
                "text": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
                "created_at": row[3],
            }
            for row in cursor.fetchall()
        ]

        # Log the result order for debugging
        if results and observability:
            orders = [m.get("metadata", {}).get("order") for m in results]
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_RETRIEVED,
                level=observability.EventLevel.DEBUG,
                data={"count": len(results), "orders": orders[:5]},
                description=f"Retrieved {len(results)} recent memories with orders: {orders[:5]}",
            )

        return results

    async def create_collection(
        self, name: str, description: Optional[str] = None, user_id: Optional[str] = None
    ) -> str:
        """
        Create a new collection.

        Args:
            name: The collection name
            description: Optional description
            user_id: Optional external user ID

        Returns:
            The collection ID
        """
        # Get internal user ID
        if user_id:
            internal_user_id = await self.get_or_create_user(user_id)
        else:
            internal_user_id = self.default_user_id

        collection_id = self._generate_id()

        try:
            self.conn.execute(
                "INSERT INTO collections (id, user_id, name, description) VALUES (?, ?, ?, ?)",
                (collection_id, internal_user_id, name, description),
            )
            self.conn.commit()
            return collection_id
        except sqlite3.IntegrityError:
            # Collection already exists for this user
            cursor = self.conn.execute(
                "SELECT id FROM collections WHERE name = ? AND user_id = ?",
                (name, internal_user_id),
            )
            return cursor.fetchone()[0]

    async def list_collections(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all collections for a user.

        Args:
            user_id: Optional external user ID

        Returns:
            List of collection dictionaries
        """
        # Get internal user ID
        if user_id:
            internal_user_id = await self.get_or_create_user(user_id)
        else:
            internal_user_id = self.default_user_id

        cursor = self.conn.execute(
            """
            SELECT c.id, c.name, c.description, c.created_at
            FROM collections c
            JOIN users u ON c.user_id = u.id
            WHERE c.user_id = ? AND u.formation_id = ?
            ORDER BY c.name
            """,
            (internal_user_id, self.formation_id),
        )

        return [
            {"id": row[0], "name": row[1], "description": row[2], "created_at": row[3]}
            for row in cursor.fetchall()
        ]

    def __del__(self):
        """
        Clean up database connection.

        This method ensures the database connection is properly closed
        when the object is garbage collected.
        """
        if hasattr(self, "conn"):
            self.conn.close()
