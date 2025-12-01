# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Long-Term Memory - PostgreSQL Vector Database
# Description:  Persistent vector memory implementation using PostgreSQL
# Role:         Provides durable semantic memory storage with pgvector
# Usage:        Used for permanent storage of agent knowledge and conversations
# Author:       Muxi Framework Team
#
# The Long-Term Memory module provides a durable, scalable memory system using
# PostgreSQL with the pgvector extension. This implementation enables:
#
# 1. Vector Similarity Search
#    - Efficient storage and retrieval of embeddings
#    - Support for semantic similarity searching
#    - Integration with any embedding model
#
# 2. Structured Data Organization
#    - Collection-based storage hierarchy
#    - Rich metadata filtering capabilities
#    - Flexible query parameters
#
# 3. Enterprise-Ready Persistence
#    - Transactional storage guarantees
#    - Indexing for performance at scale
#    - Backup and recovery support
#
# This implementation is suitable for production deployments where durability,
# scalability, and performance are important requirements.
# =============================================================================

import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    desc,
    func,
    select,
    UniqueConstraint,
)
from ...datatypes.json_type import JSONType

# Note: No longer importing global config - values passed as parameters
from ...utils.id_generator import get_default_nanoid
from ...utils.datetime_utils import utc_now_naive
from ..llm import LLM
from .. import observability
from ..db import DatabaseManager, Base, AsyncModelMixin


# Memory collection definitions for organizing long-term storage
MEMORY_COLLECTIONS = {
    "conversations": "Raw chat history and full message exchanges",
    "user_identity": "Personal information like name, age, location, occupation, contact details",
    "preferences": "Likes, dislikes, favorites, preferences, opinions",
    "relationships": "Family, friends, colleagues, social connections",
    "activities": "Hobbies, interests, routines, habits, regular activities",
    "goals": "Aspirations, plans, objectives, desires, future intentions",
    "history": "Past experiences, stories, achievements, background",
    "context": "General knowledge, facts, observations, miscellaneous info",
}


class User(Base, AsyncModelMixin):
    """
    User table for multi-user support.

    Core user entity that can have multiple external identifiers.
    External identifiers are stored in the user_identifiers table.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(
        String(21), nullable=False, unique=True, index=True
    )  # Nano ID for external exposure (muxi_user_id)
    formation_id = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class UserIdentifier(Base, AsyncModelMixin):
    """
    User identifier table for multi-identity support.

    Enables multiple external identifiers (email, Slack ID, Telegram handle, etc.)
    to map to a single MUXI user. This allows context and memory carryover across
    communication channels.
    """

    __tablename__ = "user_identifiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    identifier = Column(String(255), nullable=False)
    identifier_type = Column(String(50))  # Optional: 'email', 'slack', 'telegram', etc.
    formation_id = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive)

    # Composite unique constraint to ensure identifier uniqueness per formation
    __table_args__ = (
        UniqueConstraint("identifier", "formation_id", name="uq_identifier_formation"),
    )


class Memory(Base, AsyncModelMixin):
    """
    Memory table for storing vector embeddings and metadata.

    This SQLAlchemy model defines the structure for storing memories in the database,
    including vector embeddings, text content, metadata, and organizational information.
    """

    __tablename__ = "memories"

    id = Column(String(21), primary_key=True, default=get_default_nanoid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    embedding = Column(Vector(1536))  # Default dimension for OpenAI embeddings
    text = Column(Text, nullable=False)
    meta_data = Column(JSONType, nullable=False, default={})
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    collection = Column(String(255), nullable=False, index=True)


# Note: Collection table has been removed.
# Memories now use a simple 'collection' column for categorization.


class LongTermMemory:
    """
    Long-term memory implementation using PostgreSQL with pgvector.

    This class provides a persistent vector database for storing and retrieving
    information based on semantic similarity. It offers a comprehensive solution
    for durable, scalable memory storage with rich filtering capabilities and
    collection-based organization.

    When no embedding model is configured, automatically falls back to local
    sentence-transformer embeddings (all-MiniLM-L6-v2, 384 dimensions).
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        formation_id: str,
        dimension: int = 1536,  # Default dimension for OpenAI embeddings
        default_collection: str = "default",
        embedding_model: Optional[Union[LLM, str]] = None,
    ):
        """
        Initialize a LongTermMemory instance for persistent semantic memory storage.

        Sets up database connections, determines multi-user mode,
        creates necessary tables, and ensures default user and collection
        exist in single-user mode. Supports configuration of vector dimension,
        default collection, and optional embedding model.

        If no embedding model is provided, uses local sentence-transformer
        embeddings (all-MiniLM-L6-v2) as a fallback.
        """
        self.default_collection = default_collection
        self.formation_id = formation_id

        # Model can be either an LLM instance or a model name string (lazy loading)
        self._embedding_model = None
        self._embedding_model_name = None
        self._use_local_embeddings = False
        self._local_embedding_logged = False

        if embedding_model:
            if isinstance(embedding_model, str):
                # Model name provided - will create LLM instance lazily
                self._embedding_model_name = embedding_model
                self.dimension = dimension
            else:
                # Assume it's an LLM instance
                self._embedding_model = embedding_model
                self.dimension = dimension
        else:
            # No embedding model configured - use local fallback
            self._use_local_embeddings = True
            from .local_embeddings import get_local_embedding_dimension

            self.dimension = get_local_embedding_dimension()

        # Use provided database manager
        self.db_manager = db_manager
        self.engine = self.db_manager.engine
        self.Session = self.db_manager.Session
        self.AsyncSession = self.db_manager.AsyncSession

        # Determine if we're in multi-user mode
        self.is_multi_user = self.db_manager.database_type == "postgresql"

        # Tables are now created centrally in formation initialization
        # Only handle pgvector extension setup here if needed
        if self.db_manager.database_type == "postgresql":
            self._ensure_pgvector_extension()

        # Create default user and collection for single-user mode
        if not self.is_multi_user:
            self._ensure_default_user()

    @property
    def embedding_model(self):
        """Get the embedding model, creating it lazily if needed.

        If no API-based embedding model is configured, returns a LocalEmbeddingProvider
        that uses sentence-transformers for local embedding generation.
        """
        # Check if we should use local embeddings
        if self._use_local_embeddings:
            if self._embedding_model is None:
                from .local_embeddings import LocalEmbeddingProvider

                self._embedding_model = LocalEmbeddingProvider()

                # Log once about using local embeddings
                if not self._local_embedding_logged:
                    observability.observe(
                        event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                        level=observability.EventLevel.INFO,
                        data={
                            "embedding_model": "all-MiniLM-L6-v2",
                            "dimension": self.dimension,
                            "type": "local_fallback",
                        },
                        description=(
                            "Using local embedding model (all-MiniLM-L6-v2). "
                            "For better quality, configure: llm.models.embedding"
                        ),
                    )
                    self._local_embedding_logged = True
            return self._embedding_model

        # API-based embedding model
        if self._embedding_model is None and self._embedding_model_name:
            # Create LLM instance lazily
            try:
                from ..llm import LLM as LLMClass

                self._embedding_model = LLMClass(model=self._embedding_model_name)
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.LLM_INITIALIZATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "model_name": self._embedding_model_name,
                        "error": str(e),
                    },
                    description=f"Failed to create LLM instance for embeddings: {e}",
                )
                # Clear the model name to prevent repeated initialization attempts
                self._embedding_model_name = None
                raise ValueError(f"Failed to initialize embedding model: {e}")
        return self._embedding_model

    def _ensure_pgvector_extension(self) -> None:
        """
        Ensure pgvector extension is created for PostgreSQL.

        This method creates the pgvector extension if it doesn't already exist.
        It's safe to call multiple times.
        """
        try:
            from sqlalchemy import text

            # First check if extension already exists
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                )
                extension_exists = result.fetchone() is not None

            if extension_exists:
                # Extension already exists - silent success (no logging needed)
                return

            # Extension doesn't exist, try to create it
            with self.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()

            # Successfully created - log at INFO level
            # REMOVE - line 258 (DEBUG runtime trace: internal detail)
        except Exception as e:
            # Check if the error is because extension already exists (shouldn't happen, but be safe)
            error_str = str(e).lower()
            if "already exists" in error_str or "extension \"vector\" already exists" in error_str:
                # Extension exists, no need to log as error
                return

            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_EXTENSION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "extension": "pgvector"},
                description=f"Failed to create pgvector extension: {e}",
            )
            # Don't raise - pgvector might not be available but system can continue

    async def _resolve_user_id_async(self, external_user_id: Optional[str] = None) -> int:
        """
        Resolve user identifier to internal user ID.

        Prefers RequestContext.internal_user_id if available (normal path after Phase 3).
        Falls back to resolving external_user_id for direct API calls and tests.

        Returns:
            int: Internal user ID for database operations
        """
        from ..observability.context import get_current_request_context
        ctx = get_current_request_context()

        if ctx and ctx.internal_user_id is not None:
            # Normal path: Use internal user ID from context (already resolved at entry)
            return ctx.internal_user_id
        else:
            # Fallback for non-context calls (tests, direct API usage, etc.)
            if not self.is_multi_user:
                # Single-user mode: Always use identifier "0"
                from ...utils.user_resolution import resolve_user_identifier
                internal_user_id, _ = await resolve_user_identifier(
                    identifier="0",
                    formation_id=self.formation_id,
                    db_manager=self.db_manager,
                    kv_cache=None,
                )
                return internal_user_id
            elif external_user_id:
                # Multi-user mode: Resolve provided external_user_id
                from ...utils.user_resolution import resolve_user_identifier
                internal_user_id, _ = await resolve_user_identifier(
                    identifier=external_user_id,
                    formation_id=self.formation_id,
                    db_manager=self.db_manager,
                    kv_cache=None,
                )
                return internal_user_id
            else:
                raise ValueError(
                    "RequestContext not available and no external_user_id provided. "
                    "This should not happen in normal operation."
                )

    def _resolve_user_id_sync(self, external_user_id: Optional[str] = None) -> int:
        """
        Synchronous version of _resolve_user_id_async.

        Note: Sync methods are deprecated - prefer async methods where possible.
        This is provided for backward compatibility only.
        """
        from ..observability.context import get_current_request_context
        ctx = get_current_request_context()

        if ctx and ctx.internal_user_id is not None:
            return ctx.internal_user_id
        else:
            # Fallback: Need to do blocking resolution (not ideal)
            # For sync fallback, we'll use the old _get_or_create_user pattern
            # This is only hit in tests or direct sync API usage
            if not self.is_multi_user:
                external_user_id = "0"
            elif external_user_id is None:
                raise ValueError("external_user_id required in multi-user mode")

            # Find or create user synchronously
            with self.Session() as session:
                result = session.execute(
                    select(User.id).where(
                        User.formation_id == self.formation_id
                    ).limit(1) if not self.is_multi_user else
                    select(User.id).join(UserIdentifier).where(
                        UserIdentifier.identifier == external_user_id,
                        UserIdentifier.formation_id == self.formation_id
                    )
                )
                user_id = result.scalar_one_or_none()

                if user_id:
                    return user_id

                # Create new user if not found
                new_user = User(
                    public_id=get_default_nanoid(),
                    formation_id=self.formation_id,
                )
                session.add(new_user)
                session.flush()

                # Create identifier
                new_identifier = UserIdentifier(
                    user_id=new_user.id,
                    identifier=external_user_id,
                    formation_id=self.formation_id,
                )
                session.add(new_identifier)
                session.commit()

                return new_user.id

    async def get_user_id(self, external_user_id: str) -> Optional[int]:
        """
        Get our internal user ID for an external_user_id.

        This method looks up the user record based on the external identifier
        and returns the internal database ID. This ID should be used for
        all internal operations like KV cache keys.

        Args:
            external_user_id: The external user identifier provided by the developer

        Returns:
            Internal user ID (integer) or None if user doesn't exist
        """
        # Handle single-user mode
        if not self.is_multi_user:
            external_user_id = "0"

        # Query via user_identifiers table
        async with self.db_manager.get_async_session() as session:
            result = await session.execute(
                select(UserIdentifier.user_id)
                .where(UserIdentifier.identifier == external_user_id)
                .where(UserIdentifier.formation_id == self.formation_id)
            )
            user_id = result.scalar_one_or_none()

            # If user doesn't exist yet, return None
            # (will be created on first memory operation)
            return user_id

    def _ensure_default_user(self) -> None:
        """Ensure default user exists for single-user mode."""
        # Use resolution utility to ensure default user exists
        self._resolve_user_id_sync("0")

    # Collection table removed - no longer needed

    def _extract_embedding_from_response(self, embedding_response: Any) -> List[float]:
        """
        Extract embedding vector from various response formats.

        This method handles different embedding response formats from various providers:
        - OpenAI-style: response.data[0].embedding
        - Alternative: response.embeddings[0].embedding
        - Direct: response.embedding
        - List: Already a list of floats

        Args:
            embedding_response: The response from embedding model

        Returns:
            List of floats representing the embedding vector
        """
        # OpenAI-style response: EmbeddingResponse.data[0].embedding
        if hasattr(embedding_response, "data") and embedding_response.data:
            embedding_item = embedding_response.data[0]
            if hasattr(embedding_item, "embedding"):
                return embedding_item.embedding
            else:
                return embedding_item
        # Alternative format: might have embeddings list
        elif hasattr(embedding_response, "embeddings") and embedding_response.embeddings:
            embedding_item = embedding_response.embeddings[0]
            if hasattr(embedding_item, "embedding"):
                return embedding_item.embedding
            else:
                return embedding_item
        # Direct embedding attribute
        elif hasattr(embedding_response, "embedding"):
            return embedding_response.embedding
        # Already a list of floats
        elif isinstance(embedding_response, list):
            return embedding_response
        else:
            # Last resort - try to use as is
            return embedding_response

    async def add(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
        user_id: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> str:
        """
        Asynchronously adds new content to long-term memory, generating an embedding if not provided.

        Parameters:
            content (str): The text content to store.
            metadata (dict, optional): Additional metadata to associate with the content.
            embedding (list[float] or np.ndarray, optional): Pre-computed embedding vector.
            If not provided, an embedding is generated.
            user_id (str, optional): The user identifier (will be resolved to internal_user_id).
            collection (str, optional): The collection to store the memory in.
            If not provided, uses the default collection.

        Returns:
            str: The unique ID of the newly created memory entry.
        """
        # Emit memory storage started event
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCED,
            level=observability.EventLevel.INFO,
            data={
                "content_length": len(content),
                "has_metadata": metadata is not None,
                "has_embedding": embedding is not None,
                "embedding_dimensions": len(embedding) if embedding is not None else None,
                "collection": collection or self.default_collection,
            },
            description="Long-term memory storage started",
        )

        if metadata is None:
            metadata = {}

        # Generate embedding if not provided
        if embedding is None:
            if not self.embedding_model:
                raise ValueError("No embedding model available for generating embeddings")
            embedding_response = await self.embedding_model.embed(content)
            # Extract the actual embedding vector from the response
            embedding = self._extract_embedding_from_response(embedding_response)

        # Insert into database using async method
        memory_id = await self._add_internal_async(
            content, embedding, metadata, collection, user_id
        )

        # Emit memory storage completed event
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "memory_id": memory_id,
                "content_length": len(content),
                "collection": collection or self.default_collection,
            },
            description="Long-term memory storage completed",
        )
        return memory_id

    async def _add_internal_async(
        self,
        text: str,
        embedding: Union[List[float], np.ndarray],
        metadata: Dict[str, Any] = None,
        collection: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Asynchronously adds a new memory entry to the database with the
        specified text, embedding, metadata, collection, and user context.

        Parameters:
            text (str): The text content to store as memory.
            embedding (Union[List[float], np.ndarray]): The vector embedding representing the content.
            metadata (Dict[str, Any], optional): Additional metadata to associate with the memory.
            collection (str, optional): The collection name to store the memory in. Defaults to the default collection.
            user_id (str, optional): The user identifier (will be resolved to internal_user_id).

        Returns:
            str: The unique ID of the newly created memory entry.
        """
        if metadata is None:
            metadata = {}

        if collection is None:
            collection = self.default_collection

        # Add timestamp to metadata
        metadata["timestamp"] = time.time()

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = await self._resolve_user_id_async(user_id)

        async with self.db_manager.get_async_session() as session:
            # Convert numpy array to list if necessary
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            # Create memory using async model helper with internal user ID
            memory = await Memory.create(
                session,
                user_id=internal_user_id,  # Use resolved internal ID
                text=text,
                embedding=embedding,
                meta_data=metadata,
                collection=collection,
            )

            # Return ID
            return memory.id

    def _add_internal(
        self,
        text: str,
        embedding: Union[List[float], np.ndarray],
        metadata: Dict[str, Any] = None,
        collection: Optional[str] = None,
        external_user_id: Optional[str] = None,
    ) -> str:
        """
        Synchronously adds a new memory entry to the database with associated text, embedding, metadata, and collection.

        Parameters:
            text (str): The text content to store.
            embedding (Union[List[float], np.ndarray]): The vector embedding representing the text.
            metadata (Dict[str, Any], optional): Additional metadata to associate with the memory.
            collection (str, optional): The collection name to store the memory in.
            external_user_id (str, optional): The external user identifier for multi-user environments.

        Returns:
            str: The unique ID of the newly created memory entry.
        """
        if metadata is None:
            metadata = {}

        if collection is None:
            collection = self.default_collection

        # Add timestamp to metadata
        metadata["timestamp"] = time.time()

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = self._resolve_user_id_sync(external_user_id)

        with self.Session() as session:
            # Convert numpy array to list if necessary
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            # Create memory
            memory = Memory(
                user_id=internal_user_id,
                text=text,
                embedding=embedding,
                meta_data=metadata,
                collection=collection,
            )

            # Add to database
            session.add(memory)
            session.commit()

            # Return ID
            return memory.id

    # Collection methods removed - using simple column-based collections

    async def search(
        self,
        query: str,
        limit: int = 5,
        query_embedding: Optional[Union[List[float], np.ndarray]] = None,
        collection: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Asynchronously performs a semantic similarity search for memories matching a text query.

        If a query embedding is not provided, it is generated using the embedding model.
        Supports filtering by collection and metadata, and returns a list of the most relevant
        memories with similarity scores.

        Parameters:
            query (str): The text query to search for.
            limit (int): Maximum number of results to return.
            query_embedding (Optional[Union[List[float], np.ndarray]]): Opt. pre-computed embedding vector for query.
            collection (Optional[str]): The collection to search in. Defaults to the default collection.
            filter_metadata (Optional[Dict[str, Any]]): Optional metadata filters to apply.
            external_user_id (Optional[str]): The external user ID for multi-user environments.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing memory IDs, text, metadata, and similarity scores,
                                  ordered by relevance.
        """
        # Emit memory search started event
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "query_length": len(query),
                "limit": limit,
                "has_query_embedding": query_embedding is not None,
                "collection": collection or self.default_collection,
                "has_metadata_filter": filter_metadata is not None,
            },
            description="Long-term memory search started",
        )

        # Generate embedding if not provided
        if query_embedding is None:
            if not self.embedding_model:
                raise ValueError("No embedding model available for generating embeddings")
            embedding_response = await self.embedding_model.embed(query)
            # Extract the actual embedding vector from the response
            query_embedding = self._extract_embedding_from_response(embedding_response)

        # Use default collection if not specified
        if collection is None:
            collection = self.default_collection

        # Search in database using async method
        results = await self._search_internal_async(
            query_embedding, limit, collection, filter_metadata, external_user_id
        )

        # Format results
        formatted_results = []
        for score, memory in results:
            formatted_results.append(
                {
                    "id": memory["id"],
                    "text": memory["text"],
                    "metadata": memory["meta_data"],
                    "score": score,
                }
            )

        # Calculate quality metrics
        results_quality_score = (
            sum(r["score"] for r in formatted_results) / len(formatted_results)
            if formatted_results
            else 0.0
        )

        # Emit memory search completed event
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
            level=observability.EventLevel.INFO,
            data={
                "query_length": len(query),
                "results_count": len(formatted_results),
                "results_quality_score": results_quality_score,
                "collection": collection,
                "limit": limit,
            },
            description="Long-term memory search completed",
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
        Build search parameters for the LongTermMemory search method.

        Args:
            query: The search query text
            k: Number of results to return
            user_id: Optional user ID for filtering
            full_filter: Optional metadata filter
            collection: Optional collection name

        Returns:
            Dictionary of parameters for the search method
        """
        search_params = {
            "query": query,
            "limit": k,
            "filter_metadata": full_filter,
        }

        if user_id is not None:
            search_params["external_user_id"] = user_id

        if collection:
            search_params["collection"] = collection

        return search_params

    def _search_internal(
        self,
        query_embedding: Union[List[float], np.ndarray],
        k: int = 5,
        collection: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Internal method to search for similar embeddings in the database.

        This is a synchronous implementation that directly interacts with
        the database to perform vector similarity search with optional
        metadata filtering.

        Args:
            query_embedding: The vector embedding to search for.
            k: Maximum number of results to return.
            collection: The collection to search in. If None, uses the default collection.
            filter_metadata: Optional metadata filters to apply.

        Returns:
            A list of tuples containing (similarity_score, memory_dict).
        """
        # Convert numpy array to list if necessary
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()

        # Use default collection if not specified
        if collection is None:
            collection = self.default_collection

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = self._resolve_user_id_sync(external_user_id)

        with self.Session() as session:
            # For PostgreSQL with pgvector, we need to cast the query embedding
            if self.db_manager.database_type == "postgresql":
                from sqlalchemy import cast
                from pgvector.sqlalchemy import Vector

                query_embedding_vector = cast(query_embedding, Vector(self.dimension))
            else:
                query_embedding_vector = query_embedding

            # Build query
            query = (
                select(
                    Memory,
                    func.l2_distance(Memory.embedding, query_embedding_vector).label("distance"),
                )
                .filter(
                    Memory.user_id == internal_user_id,
                    Memory.collection == collection,
                )
                .order_by("distance")
                .limit(k)
            )

            # Add metadata filters if provided
            if filter_metadata:
                for key, value in filter_metadata.items():
                    query = query.filter(Memory.meta_data[key].astext == str(value))

            # Execute query
            results = session.execute(query).all()

            # Format results
            return [
                (
                    1.0 / (1.0 + float(result.distance)),  # Convert distance to similarity score
                    {
                        "id": result.Memory.id,
                        "text": result.Memory.text,
                        "meta_data": result.Memory.meta_data,
                        "created_at": (
                            result.Memory.created_at.isoformat()
                            if result.Memory.created_at
                            else None
                        ),
                    },
                )
                for result in results
            ]

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.

        This method fetches a single memory entry by its unique identifier,
        returning all associated data including content, embedding, and metadata.

        Args:
            memory_id: The ID of the memory to retrieve.

        Returns:
            The memory object if found, otherwise None.
        """
        with self.Session() as session:
            memory = (
                session.query(Memory)
                .join(User, Memory.user_id == User.id)
                .filter(
                    Memory.id == memory_id,
                    User.formation_id == self.formation_id,
                )
                .first()
            )

            if not memory:
                return None

            return {
                "id": memory.id,
                "text": memory.text,
                "embedding": memory.embedding,
                "meta_data": memory.meta_data,
                "created_at": memory.created_at.isoformat(),
                "updated_at": memory.updated_at.isoformat(),
                "collection": memory.collection,
            }

    def update(
        self,
        memory_id: str,
        text: Optional[str] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update an existing memory.

        This method allows partial updates to a memory entry, modifying
        only the fields that are provided while leaving others unchanged.

        Args:
            memory_id: The ID of the memory to update.
            text: Optional new text content.
            embedding: Optional new embedding vector.
            metadata: Optional new metadata.

        Returns:
            True if the update was successful, False otherwise.
        """
        # Emit memory update started event
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "memory_id": memory_id,
                "has_text_update": text is not None,
                "has_embedding_update": embedding is not None,
                "has_metadata_update": metadata is not None,
            },
            description="Long-term memory update started",
        )

        with self.Session() as session:
            memory = (
                session.query(Memory)
                .join(User, Memory.user_id == User.id)
                .filter(
                    Memory.id == memory_id,
                    User.formation_id == self.formation_id,
                )
                .first()
            )

            if not memory:
                # Emit memory update failed event
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_UPDATE_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "memory_id": memory_id,
                        "error": "Memory not found",
                    },
                    description="Long-term memory update failed - memory not found",
                )
                return False

            if text is not None:
                memory.text = text

            if embedding is not None:
                # Convert numpy array to list if necessary
                if isinstance(embedding, np.ndarray):
                    embedding = embedding.tolist()
                memory.embedding = embedding

            if metadata is not None:
                # Update timestamp
                metadata["timestamp"] = time.time()
                memory.meta_data = metadata

            session.commit()

            # Emit memory update completed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_UPDATED,
                level=observability.EventLevel.INFO,
                data={
                    "memory_id": memory_id,
                    "updated_text": text is not None,
                    "updated_embedding": embedding is not None,
                    "updated_metadata": metadata is not None,
                },
                description="Long-term memory update completed",
            )

            return True

    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.

        This method permanently removes a memory entry from the database.

        Args:
            memory_id: The ID of the memory to delete.

        Returns:
            True if the deletion was successful, False otherwise.
        """
        # Emit memory deletion started event
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={"memory_id": memory_id},
            description="Long-term memory deletion started",
        )

        with self.Session() as session:
            memory = (
                session.query(Memory)
                .join(User, Memory.user_id == User.id)
                .filter(
                    Memory.id == memory_id,
                    User.formation_id == self.formation_id,
                )
                .first()
            )

            if not memory:
                # Emit memory deletion failed event
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_DELETION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "memory_id": memory_id,
                        "error": "Memory not found",
                    },
                    description="Long-term memory deletion failed - memory not found",
                )
                return False

            session.delete(memory)
            session.commit()

            # Emit memory deletion completed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_UPDATED,
                level=observability.EventLevel.INFO,
                data={"memory_id": memory_id},
                description="Long-term memory item deleted",
            )

            return True

    def list_collections(self, external_user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all collections used by memories.

        This method returns information about all collections that have
        memories stored in them, based on the collection column in the
        memories table.

        Args:
            external_user_id: Optional external user ID for multi-user mode.

        Returns:
            A list of dictionaries containing collection information.
        """
        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = self._resolve_user_id_sync(external_user_id)

        with self.Session() as session:
            # Get distinct collections from memories table (no JOIN needed)
            from sqlalchemy import distinct

            collections = (
                session.query(distinct(Memory.collection))
                .filter(
                    Memory.user_id == internal_user_id,
                )
                .all()
            )

            return [
                {
                    "name": c[0],
                    "description": MEMORY_COLLECTIONS.get(c[0], f"Collection: {c[0]}"),
                }
                for c in collections
                if c[0]
            ]

    def create_collection(
        self, name: str, description: Optional[str] = None, external_user_id: Optional[str] = None
    ) -> str:
        """
        Create a new collection.

        Note: With the simplified collection system, this method now just
        validates that the collection name is valid. Collections are created
        automatically when memories are added to them.

        Args:
            name: The name of the collection.
            description: Optional description of the collection (ignored).
            external_user_id: Optional external user ID for multi-user mode (ignored).

        Returns:
            The collection name.
        """
        # Ignore unused parameters but keep them for API compatibility
        _ = description
        _ = external_user_id

        if not name or not name.strip():
            raise ValueError("Collection name cannot be empty")

        # Collections are now created automatically when memories are added
        # This method exists for API compatibility
        return name

    def delete_collection(
        self, name: str, delete_memories: bool = False, external_user_id: Optional[str] = None
    ) -> bool:
        """
        Delete a collection.

        This method removes all memories from a collection and either deletes
        them or moves them to the default collection.

        Args:
            name: The name of the collection to delete.
            delete_memories: Whether to also delete all memories in the
                collection.
            external_user_id: Optional external user ID for multi-user mode.

        Returns:
            True if the collection had memories and was processed, False if not found.
        """
        if name == self.default_collection:
            raise ValueError("Cannot delete the default collection")

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = self._resolve_user_id_sync(external_user_id)

        with self.Session() as session:
            # Check if there are memories in this collection (no JOIN needed)
            memories_count = (
                session.query(Memory)
                .filter(
                    Memory.collection == name,
                    Memory.user_id == internal_user_id,
                )
                .count()
            )

            if memories_count == 0:
                return False

            if delete_memories:
                # Delete all memories in the collection for this user
                session.query(Memory).filter(
                    Memory.collection == name, Memory.user_id == internal_user_id
                ).delete()
            else:
                # Move memories to default collection for this user
                session.query(Memory).filter(
                    Memory.collection == name, Memory.user_id == internal_user_id
                ).update({"collection": self.default_collection})

            session.commit()
            return True

    def get_recent_memories(
        self, limit: int = 10, collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent memories from a specified or default collection, ordered by creation date.

        Parameters:
            limit (int): Maximum number of memories to return.
            collection (str, optional): Name of the collection to retrieve memories from.
                                        Uses the default collection if not specified.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing memory details,
                                  including ID, text, metadata, timestamps, and collection name.
        """
        collection_name = collection or self.default_collection

        with self.Session() as session:
            memories = (
                session.query(Memory)
                .join(User, Memory.user_id == User.id)
                .filter(
                    Memory.collection == collection_name,
                    User.formation_id == self.formation_id,
                )
                .order_by(desc(Memory.created_at))
                .limit(limit)
                .all()
            )

            return [
                {
                    "id": m.id,
                    "text": m.text,
                    "meta_data": m.meta_data,
                    "created_at": m.created_at.isoformat(),
                    "updated_at": m.updated_at.isoformat(),
                    "collection": m.collection,
                }
                for m in memories
            ]

    # Async collection methods removed - using simple column-based collections

    async def _search_internal_async(
        self,
        query_embedding: Union[List[float], np.ndarray],
        k: int = 5,
        collection: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Asynchronously searches for memories with embeddings most similar to the given query embedding.

        Performs a vector similarity search within the specified collection and user scope,
        optionally filtering by metadata. Returns up to `k` results as tuples of similarity score and memory data.

        Parameters:
            query_embedding: The embedding vector to search against.
            k: Maximum number of results to return.
            collection: Name of the collection to search in; defaults to the default collection if not specified.
            filter_metadata: Optional dictionary of metadata key-value pairs to filter results.
            external_user_id: External user identifier to scope the search.

        Returns:
            A list of tuples, each containing a similarity score (float) and a dictionary with memory details.
        """
        # Convert numpy array to list if necessary
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()

        # Use default collection if not specified
        if collection is None:
            collection = self.default_collection

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = await self._resolve_user_id_async(external_user_id)

        async with self.db_manager.get_async_session() as session:
            # For PostgreSQL with pgvector, we need to cast the query embedding
            if self.db_manager.database_type == "postgresql":
                from sqlalchemy import cast
                from pgvector.sqlalchemy import Vector

                query_embedding_vector = cast(query_embedding, Vector(self.dimension))
            else:
                query_embedding_vector = query_embedding

            # Build query
            query = (
                select(
                    Memory,
                    func.l2_distance(Memory.embedding, query_embedding_vector).label("distance"),
                )
                .filter(
                    Memory.user_id == internal_user_id,
                    Memory.collection == collection,
                )
                .order_by("distance")
                .limit(k)
            )

            # Add metadata filters if provided
            if filter_metadata:
                for key, value in filter_metadata.items():
                    query = query.filter(Memory.meta_data[key].astext == str(value))

            # Execute query
            result = await session.execute(query)
            results = result.all()

            # Format results
            return [
                (
                    1.0 / (1.0 + float(result.distance)),  # Convert distance to similarity score
                    {
                        "id": result.Memory.id,
                        "text": result.Memory.text,
                        "meta_data": result.Memory.meta_data,
                        "created_at": (
                            result.Memory.created_at.isoformat()
                            if result.Memory.created_at
                            else None
                        ),
                    },
                )
                for result in results
            ]

    async def search_text(
        self,
        query: str,
        limit: int = 5,
        collection: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories using text-based search with proper user isolation.

        This method uses PostgreSQL's full-text search capabilities with the GIN index
        on the text field, ensuring results are always filtered by user.
        """
        if collection is None:
            collection = self.default_collection

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = await self._resolve_user_id_async(external_user_id)

        async with self.db_manager.get_async_session() as session:

            # Build the query with proper user isolation
            if self.db_manager.database_type == "postgresql":
                # Use PostgreSQL full-text search with 'simple' configuration for multilingual support
                from sqlalchemy import text as sql_text

                # Using parameterized query for safety
                sql = sql_text(
                    """
                    SELECT
                        m.id,
                        m.text,
                        m.meta_data,
                        m.created_at,
                        ts_rank(to_tsvector('simple', m.text), plainto_tsquery('simple', :query)) as rank
                    FROM memories m
                    JOIN users u ON m.user_id = u.id
                    WHERE u.id = :user_id
                        AND u.formation_id = :formation_id
                        AND m.collection = :collection
                        AND to_tsvector('simple', m.text) @@ plainto_tsquery('simple', :query)
                    ORDER BY rank DESC
                    LIMIT :limit
                """
                )

                result = await session.execute(
                    sql,
                    {
                        "query": query,
                        "user_id": internal_user_id,
                        "formation_id": self.formation_id,
                        "collection": collection,
                        "limit": limit,
                    },
                )
                rows = result.fetchall()

                # Format results
                return [
                    {
                        "id": row.id,
                        "text": row.text,
                        "metadata": row.meta_data,
                        "score": float(row.rank) if row.rank else 0.0,
                    }
                    for row in rows
                ]
            else:
                # Fallback for SQLite - use LIKE with proper user filtering
                query_obj = (
                    select(Memory)
                    .filter(
                        Memory.user_id == internal_user_id,
                        Memory.collection == collection,
                        Memory.text.ilike(f"%{query}%"),
                    )
                    .limit(limit)
                )

                result = await session.execute(query_obj)
                memories = result.scalars().all()

                return [
                    {
                        "id": m.id,
                        "text": m.text,
                        "metadata": m.meta_data,
                        "score": 1.0,  # No ranking for LIKE queries
                    }
                    for m in memories
                ]
