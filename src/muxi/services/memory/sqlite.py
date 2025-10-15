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

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from .base import BaseMemory
from ...extensions import SQLiteVecExtension
from .. import observability


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
        dimension: int = 1536,
        default_collection: str = "default",
        extensions_dir: str = "extensions",
        embedding_model=None,  # Accept but ignore for compatibility
    ):
        """
        Initialize a local SQLite-based vector memory store with support for persistent collections and embeddings.

        Parameters:
            db_path (str): Path to the SQLite database file.
            formation_id (str): Identifier used to scope data within the database.
            dimension (int, optional): Dimensionality of embedding vectors. Defaults to 1536.
            default_collection (str, optional): Name of the default collection. Defaults to "default".
            extensions_dir (str, optional): Directory containing sqlite-vec extensions. Defaults to "extensions".
            embedding_model (optional): Accepted for compatibility but not used.
        """
        self.db_path = db_path
        self.formation_id = formation_id
        self.dimension = dimension
        self.default_collection = default_collection
        self.extensions_dir = extensions_dir

        # Store embedding model config for lazy loading (like LongTermMemory does)
        self._embedding_provider = None
        self._embedding_model_name = None
        if embedding_model:
            if isinstance(embedding_model, str):
                # Store the model name, create LLM on first use
                self._embedding_model_name = embedding_model
            else:
                # Already an LLM instance
                self._embedding_provider = embedding_model

        # Create database directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        # Initialize database
        self.conn = self._init_database()

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

        # Create tables
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL UNIQUE,
                formation_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(public_id, formation_id)
            )
        """
        )

        # Create user_identifiers table
        conn.execute(
            """
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
        """
        )

        # Create indexes for user_identifiers
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_identifiers_identifier "
            "ON user_identifiers(identifier, formation_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_identifiers_user_id "
            "ON user_identifiers(user_id)"
        )

        conn.execute(
            """
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
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
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
        """
        )

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

    @property
    def embedding_provider(self):
        """Lazy load embedding provider on first access (like LongTermMemory)."""
        if self._embedding_provider is None and self._embedding_model_name:
            from ..llm import LLM
            self._embedding_provider = LLM(model=self._embedding_model_name)
        return self._embedding_provider

    def _extract_embedding_from_response(self, embedding_response):
        """Extract the actual embedding vector from LLM response (copied from LongTermMemory)."""
        if hasattr(embedding_response, 'data') and isinstance(embedding_response.data, list):
            if len(embedding_response.data) > 0:
                first_embedding = embedding_response.data[0]
                if hasattr(first_embedding, 'embedding'):
                    return first_embedding.embedding
                elif isinstance(first_embedding, (list, np.ndarray)):
                    return first_embedding
        elif isinstance(embedding_response, (list, np.ndarray)):
            return embedding_response
        return embedding_response

    async def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        collection: Optional[str] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
    ) -> str:
        """
        Add content to memory.

        This method stores new content in memory, generating an embedding
        if an embedding provider is available.

        Args:
            content: The text content to store
            metadata: Optional metadata to associate with the content
            user_id: Optional user identifier for multi-user support
            collection: Optional collection name
            embedding: Optional pre-computed embedding

        Returns:
            The ID of the newly created memory entry
        """
        if metadata is None:
            metadata = {}

        # Use provided collection or default
        if collection is None:
            collection = self.default_collection

        # Generate embedding if not provided and provider is set
        if embedding is None and self.embedding_provider:
            try:
                # Use embed() method like LongTermMemory does
                embedding_response = await self.embedding_provider.embed(content)
                # Extract the actual embedding vector using helper method
                embedding = self._extract_embedding_from_response(embedding_response)
            except AttributeError as e:
                # Provider doesn't have embed() method
                raise RuntimeError(
                    f"Embedding provider doesn't have 'embed()' method. "
                    f"Provider type: {type(self.embedding_provider).__name__}. "
                    f"Error: {str(e)}"
                ) from e
            except Exception as e:
                # Provide context about embedding generation failure
                content_preview = content[:100] if content else "<empty>"
                error_msg = (
                    f"Failed to generate embedding for content (length={len(content)}, "
                    f"preview='{content_preview}...'): {str(e)}"
                )
                raise RuntimeError(error_msg) from e

            # Add timestamp to metadata
            metadata["timestamp"] = time.time()

            # Get or create user if provided
            internal_user_id = None
            if user_id:
                internal_user_id = await self.get_or_create_user(user_id)
            else:
                internal_user_id = self.default_user_id

            # Add to database and return memory ID
            memory_id = self._add_internal(
                content, embedding, metadata, collection, internal_user_id
            )
            return memory_id

        # If no embedding provider and no embedding provided, raise error
        raise ValueError("No embedding provided and no embedding provider configured")

    def _add_internal(
        self,
        text: str,
        embedding: Union[List[float], np.ndarray],
        metadata: Dict[str, Any] = None,
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
            embedding = embedding.astype(np.float32).tobytes()
        elif isinstance(embedding, list):
            embedding = np.array(embedding, dtype=np.float32).tobytes()

        # Use default collection and user if none specified
        collection = collection or self.default_collection
        user_id = user_id or self.default_user_id

        # Generate memory ID
        memory_id = self._generate_id()

        # Insert memory
        self.conn.execute(
            """
            INSERT INTO memories
            (id, user_id, collection, text, embedding, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                user_id,
                collection,
                text,
                embedding,
                metadata and json.dumps(metadata),
            ),
        )
        self.conn.commit()

        return memory_id

    async def search(
        self, query: str, limit: int = 5, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar content in memory.

        This method performs a semantic similarity search for content matching
        the query, using the embedding provider to generate query embeddings.

        Args:
            query: The text query to search for
            limit: Maximum number of results to return

        Returns:
            List of dictionaries containing the search results with content and metadata
        """
        # Generate embedding for query if provider is set
        if not self.embedding_provider:
            return []

        # Generate embedding for query using embed() method
        embedding_response = await self.embedding_provider.embed(query)
        query_embedding = self._extract_embedding_from_response(embedding_response)

        # Get or create user if provided
        internal_user_id = None
        if user_id:
            internal_user_id = await self.get_or_create_user(user_id)
        else:
            internal_user_id = self.default_user_id

        # Search with embedding (search ALL collections, not just default)
        results = self._search_internal(
            query_embedding, limit, collection=None, user_id=internal_user_id
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
    ) -> Dict[str, Any]:
        """
        Build search parameters for the SQLiteMemory search method.

        Args:
            query: The search query text
            k: Number of results to return
            user_id: Optional user ID for filtering
            full_filter: Optional metadata filter (not used in SQLiteMemory)
            collection: Optional collection name (not used in SQLiteMemory public API)

        Returns:
            Dictionary of parameters for the search method
        """
        search_params = {
            "query": query,
            "limit": k,
        }

        if user_id is not None:
            search_params["user_id"] = user_id

        # Note: SQLiteMemory doesn't support collection or metadata filtering
        # in its public search API, so we don't include those parameters

        return search_params

    def _search_internal(
        self,
        query_embedding: Union[List[float], np.ndarray],
        k: int = 5,
        collection: Optional[str] = None,
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

        Returns:
            List of tuples containing (similarity_score, memory_dict)
        """
        # Convert numpy array to bytes for SQLite search
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.astype(np.float32).tobytes()
        elif isinstance(query_embedding, list):
            query_embedding = np.array(query_embedding, dtype=np.float32).tobytes()

        # Use defaults if not specified
        user_id = user_id or self.default_user_id

        # Build query with JOIN to ensure formation isolation
        # Search across ALL collections if collection is None
        if collection:
            query = """
                SELECT
                    m.id,
                    m.text,
                    m.metadata,
                    m.created_at,
                    vec_distance_cosine(m.embedding, ?) as score
                FROM memories m
                JOIN users u ON m.user_id = u.id
                WHERE m.collection = ?
                    AND m.user_id = ?
                    AND u.formation_id = ?
                ORDER BY score ASC
                LIMIT ?
            """
            params = (query_embedding, collection, user_id, self.formation_id, k)
        else:
            # Search ALL collections
            query = """
                SELECT
                    m.id,
                    m.text,
                    m.metadata,
                    m.created_at,
                    vec_distance_cosine(m.embedding, ?) as score
                FROM memories m
                JOIN users u ON m.user_id = u.id
                WHERE m.user_id = ?
                    AND u.formation_id = ?
                ORDER BY score ASC
                LIMIT ?
            """
            params = (query_embedding, user_id, self.formation_id, k)

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

        Args:
            memory_id: The ID of the memory to retrieve

        Returns:
            The memory object if found, otherwise None
        """
        cursor = self.conn.execute(
            """
            SELECT m.id, m.text, m.metadata, m.created_at
            FROM memories m
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
            List of memories in reverse chronological order (newest first)
        """
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
            """
            SELECT m.id, m.text, m.metadata, m.created_at
            FROM memories m
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
