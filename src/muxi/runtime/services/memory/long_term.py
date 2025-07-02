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
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession

# Note: No longer importing global config - values passed as parameters
from ...utils.id_generator import get_default_nanoid
from ...utils.datetime_utils import utc_now_naive
from ..llm import LLM
from .. import observability
from ..db import DatabaseManager, Base, AsyncModelMixin


class User(Base, AsyncModelMixin):
    """
    User table for multi-user support.

    Maps external user IDs to internal database IDs.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_user_id = Column(String(255), nullable=False, index=True)
    external_user_id_hash = Column(String(64), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False)
    formation_id_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    # Composite unique constraint to ensure uniqueness within each formation
    __table_args__ = (
        UniqueConstraint(
            "external_user_id_hash", "formation_id_hash", name="uq_user_formation_external_id"
        ),
        UniqueConstraint(
            "external_user_id", "formation_id", name="uq_user_formation_external_id_plain"
        ),
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
    formation_id = Column(String(255), nullable=False)
    formation_id_hash = Column(String(64), nullable=False, index=True)
    embedding = Column(Vector(1536))  # Default dimension for OpenAI embeddings
    text = Column(Text, nullable=False)
    meta_data = Column(JSONType, nullable=False, default={})
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    collection = Column(String(255), nullable=False, index=True)


class Collection(Base, AsyncModelMixin):
    """
    Collection table for organizing memories.

    This SQLAlchemy model defines the structure for organizing memories into
    collections, allowing logical grouping of related memories.
    """

    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False)
    formation_id_hash = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class LongTermMemory:
    """
    Long-term memory implementation using PostgreSQL with pgvector.

    This class provides a persistent vector database for storing and retrieving
    information based on semantic similarity. It offers a comprehensive solution
    for durable, scalable memory storage with rich filtering capabilities and
    collection-based organization.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        formation_id: str,
        dimension: int = 1536,  # Default dimension for OpenAI embeddings
        default_collection: str = "default",
        embedding_model: Optional[LLM] = None,
    ):
        """
        Initialize a LongTermMemory instance for persistent semantic memory storage.
        
        Sets up database connections, determines multi-user mode, creates necessary tables, and ensures default user and collection exist in single-user mode. Supports configuration of vector dimension, default collection, and optional embedding model.
        """
        self.dimension = dimension
        self.default_collection = default_collection
        self.embedding_model = embedding_model
        self.formation_id = formation_id
        self.formation_id_hash = self._hash_formation_id(formation_id)

        # Use provided database manager
        self.db_manager = db_manager
        self.engine = self.db_manager.engine
        self.Session = self.db_manager.Session
        self.AsyncSession = self.db_manager.AsyncSession

        # Determine if we're in multi-user mode
        self.is_multi_user = self.db_manager.database_type == "postgresql"

        # Create tables if they don't exist
        self._create_tables()

        # Create default user and collection for single-user mode
        if not self.is_multi_user:
            self._ensure_default_user()

    def _create_tables(self) -> None:
        """
        Create database tables if they don't exist.

        This method initializes the database schema, ensuring the pgvector
        extension is loaded and all required tables are created.
        """
        try:
            # Note: In production, you'd use proper migrations to handle schema changes

            # Use unified database manager to create tables
            self.db_manager.create_tables(Base.metadata)

            # Create pgvector extension if using PostgreSQL
            if self.db_manager.database_type == "postgresql":
                from sqlalchemy import text

                with self.engine.connect() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    conn.commit()

            observability.observe(
                event_type=observability.SystemEvents.DATABASE_TABLES_CREATED,
                level=observability.EventLevel.INFO,
                data={
                    "database_type": self.db_manager.database_type,
                    "component": "long_term_memory",
                },
                description="Long-term memory database initialized with unified manager",
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_TABLE_CREATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "database_type": self.db_manager.database_type},
                description=f"Failed to initialize long-term memory database: {e}",
            )
            raise

    def _hash_external_id(self, external_id: str) -> str:
        """Generate SHA256 hash of external user ID."""
        import hashlib

        # Convert to string if not already (handles int, None, etc.)
        if external_id is None:
            external_id = "0"
        elif not isinstance(external_id, str):
            external_id = str(external_id)
        return hashlib.sha256(external_id.encode("utf-8")).hexdigest()

    def _hash_formation_id(self, formation_id: str) -> str:
        """Generate SHA256 hash of formation ID."""
        import hashlib

        # Convert to string if not already
        if not isinstance(formation_id, str):
            formation_id = str(formation_id)
        return hashlib.sha256(formation_id.encode("utf-8")).hexdigest()

    def _get_or_create_user(self, session: Session, external_user_id: Optional[str] = None) -> User:
        """Get existing user or create new one."""
        # Handle single-user mode
        if not self.is_multi_user:
            external_user_id = "0"
        elif external_user_id is None:
            raise ValueError("external_user_id is required in multi-user mode")

        # Calculate hash
        user_hash = self._hash_external_id(external_user_id)

        # Try to find existing user with formation scope
        user = (
            session.query(User)
            .filter_by(external_user_id_hash=user_hash, formation_id_hash=self.formation_id_hash)
            .first()
        )
        if user:
            return user

        # Create new user
        user = User(
            external_user_id=external_user_id,
            external_user_id_hash=user_hash,
            formation_id=self.formation_id,
            formation_id_hash=self.formation_id_hash,
            created_at=utc_now(),
        )
        session.add(user)
        session.commit()

        return user

    def _ensure_default_user(self) -> None:
        """Ensure default user exists for single-user mode."""
        with self.Session() as session:
            user = self._get_or_create_user(session, "0")
            # Also create default collection for this user
            self._create_default_collection_for_user(session, user.id)

    def _create_default_collection_for_user(self, session: Session, user_id: int) -> None:
        """Create default collection for a specific user."""
        # Check if default collection exists for this user
        collection = (
            session.query(Collection)
            .filter_by(
                user_id=user_id,
                name=self.default_collection,
                formation_id_hash=self.formation_id_hash,
            )
            .first()
        )

        if not collection:
            # Create default collection
            collection = Collection(
                user_id=user_id,
                name=self.default_collection,
                description="Default collection for memories",
                formation_id=self.formation_id,
                formation_id_hash=self.formation_id_hash,
            )
            session.add(collection)
            session.commit()
            #  Default collection creation - TODO: add observability

    async def add(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
        external_user_id: Optional[str] = None,
    ) -> str:
        """
        Asynchronously adds new content to long-term memory, generating an embedding if not provided.
        
        Parameters:
            content (str): The text content to store.
            metadata (dict, optional): Additional metadata to associate with the content.
            embedding (list[float] or np.ndarray, optional): Pre-computed embedding vector. If not provided, an embedding is generated.
            external_user_id (str, optional): The external user identifier for multi-user environments.
        
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
                "collection": self.default_collection,
            },
            description="Long-term memory storage started",
        )

        if metadata is None:
            metadata = {}

        # Generate embedding if not provided
        if embedding is None:
            embedding = await self.embedding_model.embed(content)

        # Insert into database using async method
        memory_id = await self._add_internal_async(
            content, embedding, metadata, self.default_collection, external_user_id
        )

        # Emit memory storage completed event
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "memory_id": memory_id,
                "content_length": len(content),
                "collection": self.default_collection,
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
        external_user_id: Optional[str] = None,
    ) -> str:
        """
        Asynchronously adds a new memory entry to the database with the specified text, embedding, metadata, collection, and user context.
        
        Parameters:
            text (str): The text content to store as memory.
            embedding (Union[List[float], np.ndarray]): The vector embedding representing the content.
            metadata (Dict[str, Any], optional): Additional metadata to associate with the memory.
            collection (str, optional): The collection name to store the memory in. Defaults to the default collection if not specified.
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

        async with self.db_manager.get_async_session() as session:
            # Get or create user
            user = await self._get_or_create_user_async(session, external_user_id)

            # Ensure collection exists for this user
            await self._ensure_collection_exists_async(session, collection, user.id)

            # Convert numpy array to list if necessary
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            # Create memory using async model helper
            memory = await Memory.create(
                session,
                user_id=user.id,
                text=text,
                embedding=embedding,
                meta_data=metadata,
                collection=collection,
                formation_id=self.formation_id,
                formation_id_hash=self.formation_id_hash,
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

        with self.Session() as session:
            # Get or create user
            user = self._get_or_create_user(session, external_user_id)

            # Ensure collection exists for this user
            self._ensure_collection_exists(session, collection, user.id)

            # Convert numpy array to list if necessary
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            # Create memory
            memory = Memory(
                user_id=user.id,
                text=text,
                embedding=embedding,
                meta_data=metadata,
                collection=collection,
                formation_id=self.formation_id,
                formation_id_hash=self.formation_id_hash,
            )

            # Add to database
            session.add(memory)
            session.commit()

            # Return ID
            return memory.id

    def _ensure_collection_exists(
        self, session: Session, collection_name: str, user_id: int
    ) -> None:
        """
        Ensure that a collection exists for a user, creating it if necessary.

        This method checks if a collection exists and creates it if it
        doesn't, ensuring that memories can always be stored properly.

        Args:
            session: The database session.
            collection_name: The name of the collection.
            user_id: The internal user ID.
        """
        collection = (
            session.query(Collection)
            .filter_by(
                user_id=user_id, name=collection_name, formation_id_hash=self.formation_id_hash
            )
            .first()
        )

        if not collection:
            collection = Collection(
                user_id=user_id,
                name=collection_name,
                description=f"Collection: {collection_name}",
                formation_id=self.formation_id,
                formation_id_hash=self.formation_id_hash,
            )
            session.add(collection)
            session.flush()

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
        
        If a query embedding is not provided, it is generated using the embedding model. Supports filtering by collection and metadata, and returns a list of the most relevant memories with similarity scores.
        
        Parameters:
            query (str): The text query to search for.
            limit (int): Maximum number of results to return.
            query_embedding (Optional[Union[List[float], np.ndarray]]): Optional pre-computed embedding vector for the query.
            collection (Optional[str]): The collection to search in. Defaults to the default collection if not specified.
            filter_metadata (Optional[Dict[str, Any]]): Optional metadata filters to apply.
            external_user_id (Optional[str]): The external user ID for multi-user environments.
        
        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing memory IDs, text, metadata, and similarity scores, ordered by relevance.
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
            query_embedding = await self.embedding_model.embed(query)

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

        # Emit memory search completed event
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
            level=observability.EventLevel.INFO,
            data={
                "query_length": len(query),
                "results_count": len(formatted_results),
                "collection": collection,
                "limit": limit,
            },
            description="Long-term memory search completed",
        )

        return formatted_results

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

        with self.Session() as session:
            # Get user
            user = self._get_or_create_user(session, external_user_id)

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
                .filter(Memory.user_id == user.id)
                .filter(Memory.formation_id_hash == self.formation_id_hash)
                .filter(Memory.collection == collection)
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
                .filter_by(id=memory_id, formation_id_hash=self.formation_id_hash)
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
                .filter_by(id=memory_id, formation_id_hash=self.formation_id_hash)
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
                .filter_by(id=memory_id, formation_id_hash=self.formation_id_hash)
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

    def list_collections(self) -> List[Dict[str, Any]]:
        """
        List all collections.

        This method returns information about all available collections
        in the long-term memory system, useful for browsing available
        data organization structures.

        Returns:
            A list of dictionaries containing collection information.
        """
        with self.Session() as session:
            collections = (
                session.query(Collection).filter_by(formation_id_hash=self.formation_id_hash).all()
            )

            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat(),
                }
                for c in collections
            ]

    def create_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a new collection.

        This method creates a new organizational collection for storing
        related memories together.

        Args:
            name: The name of the collection.
            description: Optional description of the collection.

        Returns:
            The ID of the newly created collection.
        """
        with self.Session() as session:
            # Check if collection already exists
            existing = session.query(Collection).filter_by(name=name).first()

            if existing:
                return existing.id

            # Create new collection
            collection = Collection(name=name, description=description or f"Collection: {name}")

            session.add(collection)
            session.commit()

            return collection.id

    def delete_collection(self, name: str, delete_memories: bool = False) -> bool:
        """
        Delete a collection.

        This method removes a collection and either deletes its memories
        or moves them to the default collection.

        Args:
            name: The name of the collection to delete.
            delete_memories: Whether to also delete all memories in the
                collection.

        Returns:
            True if the collection was deleted, False if not found.
        """
        if name == self.default_collection:
            raise ValueError("Cannot delete the default collection")

        with self.Session() as session:
            collection = session.query(Collection).filter_by(name=name).first()

            if not collection:
                return False

            if delete_memories:
                # Delete all memories in the collection
                session.query(Memory).filter_by(collection=name).delete()
            else:
                # Move memories to default collection
                session.query(Memory).filter_by(collection=name).update(
                    {"collection": self.default_collection}
                )

            # Delete the collection
            session.delete(collection)
            session.commit()

            return True

    def get_recent_memories(
        self, limit: int = 10, collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent memories from a specified or default collection, ordered by creation date.
        
        Parameters:
            limit (int): Maximum number of memories to return.
            collection (str, optional): Name of the collection to retrieve memories from. Uses the default collection if not specified.
        
        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing memory details, including ID, text, metadata, timestamps, and collection name.
        """
        collection_name = collection or self.default_collection

        with self.Session() as session:
            memories = (
                session.query(Memory)
                .filter_by(collection=collection_name, formation_id_hash=self.formation_id_hash)
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

    async def _get_or_create_user_async(self, session: AsyncSession, external_user_id: Optional[str] = None) -> User:
        """
        Asynchronously retrieves an existing user or creates a new one based on the external user ID and formation scope.
        
        Raises:
            ValueError: If `external_user_id` is not provided in multi-user mode.
        
        Returns:
            User: The retrieved or newly created user instance.
        """
        # Handle single-user mode
        if not self.is_multi_user:
            external_user_id = "0"
        elif external_user_id is None:
            raise ValueError("external_user_id is required in multi-user mode")

        # Calculate hash
        external_user_id_hash = self._hash_external_id(external_user_id)

        # Try to get existing user
        user = await User.get(
            session,
            external_user_id_hash=external_user_id_hash,
            formation_id_hash=self.formation_id_hash,
        )

        if not user:
            # Create new user
            user = await User.create(
                session,
                external_user_id=external_user_id,
                external_user_id_hash=external_user_id_hash,
                formation_id=self.formation_id,
                formation_id_hash=self.formation_id_hash,
            )

        return user

    async def _ensure_collection_exists_async(
        self, session: AsyncSession, collection_name: str, user_id: int
    ) -> None:
        """
        Asynchronously ensures that a collection with the specified name exists for the given user and formation, creating it if it does not already exist.
        """
        collection = await Collection.get(
            session,
            user_id=user_id,
            name=collection_name,
            formation_id_hash=self.formation_id_hash,
        )

        if not collection:
            await Collection.create(
                session,
                user_id=user_id,
                name=collection_name,
                description=f"Collection: {collection_name}",
                formation_id=self.formation_id,
                formation_id_hash=self.formation_id_hash,
            )

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
        
        Performs a vector similarity search within the specified collection and user scope, optionally filtering by metadata. Returns up to `k` results as tuples of similarity score and memory data.
         
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

        async with self.db_manager.get_async_session() as session:
            # Get user
            user = await self._get_or_create_user_async(session, external_user_id)

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
                .filter(Memory.user_id == user.id)
                .filter(Memory.formation_id_hash == self.formation_id_hash)
                .filter(Memory.collection == collection)
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
