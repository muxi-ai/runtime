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

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete as sql_delete,
    desc,
    func,
    select,
    type_coerce,
)

from ...datatypes.json_type import JSONType
from ...utils.datetime_utils import utc_now_naive

# Note: No longer importing global config - values passed as parameters
from ...utils.id_generator import get_default_nanoid
from .. import observability
from ..db import AsyncModelMixin, Base, DatabaseManager

# Memory scopes (memory namespaces Phase 1). A memory row is written to
# exactly one scope; Phase 1 is pure substrate, so every write is user
# scope and reads do not fan out yet. ``scope_id`` semantics per scope:
#   user      -> the owning row's internal user id (stringified)
#   group     -> the group id (YAML filename stem)         [Phase 3]
#   formation -> the formation id                          [Phase 2]
# Existing rows are read as user scope: ``scope_type`` backfills through
# the server-side column default, and a NULL ``scope_id`` means "the
# row's owning user_id" (no backfill UPDATE is issued — same additive
# migration posture as the meta_data / derived_from_event_ids columns).
# Re-exported from base for existing importers; base.py is canonical
from .base import SCOPE_TYPE_FORMATION, SCOPE_TYPE_GROUP, SCOPE_TYPE_USER  # noqa: F401
from .embedding import DEFAULT_EMBEDDING_MODEL, embed, probe_dimension
from .scopes import (
    SCOPE_WEIGHTS,
    normalize_read_scopes,
    resolve_read_group_ids,
    validate_scope,
)

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
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identifier = Column(String(255), nullable=False)
    identifier_type = Column(String(50))  # Optional: 'email', 'slack', 'telegram', etc.
    formation_id = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive)

    # Composite unique constraint to ensure identifier uniqueness per formation
    __table_args__ = (
        UniqueConstraint("identifier", "formation_id", name="uq_identifier_formation"),
    )


class Group(Base, AsyncModelMixin):
    """
    Group table for group-based access control.

    Groups are policy data: group_id matches the group YAML filename stem
    (permission resolution is loaded from the formation's groups/
    directory at runtime). Membership is NOT stored in MUXI -- group ids
    reach the runtime per request via the formation middleware (request-
    middleware PRD); the former user_groups table was removed (existing
    deployed tables are left orphaned, nothing destructive).
    """

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False)
    name = Column(String(255))
    description = Column(Text)
    formation_id = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    # Composite unique constraint to ensure group_id uniqueness per formation
    __table_args__ = (UniqueConstraint("group_id", "formation_id", name="uq_group_formation"),)


# Dynamic Memory model factory — one ORM class per embedding dimension.
# Table name: memories_{dimension} (e.g. memories_384, memories_768, memories_1536).
_memory_models: Dict[int, Any] = {}


def get_memory_model(dimension: int):
    """Return (or create) the SQLAlchemy ORM model for the given embedding dimension.

    Each dimension gets its own table (``memories_384``, ``memories_1536``, etc.)
    so formations with different embedding models can coexist on the same database.
    """
    if dimension in _memory_models:
        return _memory_models[dimension]

    tablename = f"memories_{dimension}"

    model = type(
        f"Memory_{dimension}",
        (Base, AsyncModelMixin),
        {
            "__tablename__": tablename,
            "__table_args__": {"extend_existing": True},
            "id": Column(String(21), primary_key=True, default=get_default_nanoid),
            "user_id": Column(Integer, ForeignKey("users.id"), nullable=False, index=True),
            "embedding": Column(Vector(dimension)),
            "text": Column(Text, nullable=False),
            "meta_data": Column(JSONType, nullable=False, default={}),
            "created_at": Column(DateTime, default=utc_now_naive),
            "updated_at": Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive),
            "collection": Column(String(255), nullable=False, index=True),
            # Memory namespaces Phase 1: scope columns. The server-side
            # default backfills pre-existing rows as user scope on the
            # additive ALTER migration; scope_id stays nullable so old
            # rows read NULL-as-"the owning user_id" without a backfill
            # UPDATE. New writes always stamp both columns explicitly.
            "scope_type": Column(
                String(20), nullable=False, default=SCOPE_TYPE_USER, server_default=SCOPE_TYPE_USER
            ),
            "scope_id": Column(String(255), nullable=True),
        },
    )

    _memory_models[dimension] = model
    return model


def ensure_memory_table_indexes(db_manager: DatabaseManager, dimension: int) -> None:
    """Create best-effort indexes for a dimension-specific memories table."""
    if db_manager.database_type != "postgresql":
        return

    from sqlalchemy import text

    table_name = f"memories_{dimension}"
    user_collection_index = f"idx_{table_name}_user_collection"
    scope_index = f"idx_{table_name}_scope"
    embedding_index = f"idx_{table_name}_embedding_ivfflat"

    try:
        with db_manager.engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {user_collection_index} "
                    f"ON {table_name} (user_id, collection)"
                )
            )
            conn.commit()
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "table": table_name,
                "index": user_collection_index,
                "error": str(e),
                "database_type": db_manager.database_type,
            },
            description=f"Failed to create memory lookup index on {table_name}: {e}",
        )

    # Memory namespaces Phase 1: index for the scope fan-out queries
    # arriving in Phase 2 (formation isolation is via the users join,
    # so formation_id is not part of this index).
    try:
        with db_manager.engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {scope_index} "
                    f"ON {table_name} (scope_type, scope_id, collection)"
                )
            )
            conn.commit()
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "table": table_name,
                "index": scope_index,
                "error": str(e),
                "database_type": db_manager.database_type,
            },
            description=f"Failed to create memory scope index on {table_name}: {e}",
        )

    try:
        with db_manager.engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {embedding_index} "
                    f"ON {table_name} USING ivfflat (embedding vector_l2_ops) "
                    f"WITH (lists = 100)"
                )
            )
            conn.commit()
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "table": table_name,
                "index": embedding_index,
                "error": str(e),
                "database_type": db_manager.database_type,
            },
            description=f"Failed to create pgvector ANN index on {table_name}: {e}",
        )


# Backwards-compat alias used by initialization.py for table registration.
# Defaults to 1536 (OpenAI) — callers should prefer get_memory_model(dim).
Memory = get_memory_model(1536)


class LongTermMemory:
    """
    Long-term memory implementation using PostgreSQL with pgvector.

    This class provides a persistent vector database for storing and retrieving
    information based on semantic similarity. It offers a comprehensive solution
    for durable, scalable memory storage with rich filtering capabilities and
    collection-based organization.

    When no embedding model is configured, automatically falls back to
    ``local/nomic-ai/nomic-embed-text-v1.5`` (768 dimensions, Apache-2.0).
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        formation_id: str,
        dimension: int = 1536,  # Provisional dim hint; real dim is probed lazily.
        default_collection: str = "default",
        embedding_model: Optional[str] = None,
    ):
        """
        Initialize a LongTermMemory instance for persistent semantic memory storage.

        Sets up database connections, determines multi-user mode, and
        ensures the default user exists in single-user mode. The embedding
        dimension is **probed lazily** on the first embed operation via
        :func:`services.memory.embedding.probe_dimension`; construction
        does NOT invoke OneLLM.

        Parameters
        ----------
        db_manager:
            Database manager wrapping the SQLAlchemy engine / sessionmaker.
        formation_id:
            Formation identifier used for user isolation.
        dimension:
            Provisional dimension hint used to register an initial ORM
            model for the ``memories_{dim}`` table. Replaced on first
            embed op once the real dim is probed. Defaults to ``1536``
            (OpenAI) for backwards compatibility; the value becomes
            irrelevant once :meth:`_ensure_dim` resolves the real dim.
        default_collection:
            Default collection name for memory operations.
        embedding_model:
            Provider-prefixed embedding model slug (e.g.
            ``"local/nomic-ai/nomic-embed-text-v1.5"``,
            ``"openai/text-embedding-3-small"``). When ``None``, defaults
            to :data:`~services.memory.embedding.DEFAULT_EMBEDDING_MODEL`.
        """
        self.default_collection = default_collection
        self.formation_id = formation_id

        # Store the slug (string only). The old dispatch that accepted an
        # LLM instance is gone — every caller passes a slug, and embedding
        # generation flows through the shared ``embedding.embed`` helper.
        if embedding_model is None:
            embedding_model = DEFAULT_EMBEDDING_MODEL
        if not isinstance(embedding_model, str):
            raise TypeError(
                "LongTermMemory(embedding_model=...) must be a provider-prefixed "
                f"slug string, got {type(embedding_model).__name__}"
            )
        self._embedding_model_name: str = embedding_model

        # Lazy-dim: populated on first ``_ensure_dim()`` call, never in ctor.
        self._dimension: Optional[int] = None
        self._dim_lock = asyncio.Lock()

        # Provisional ORM model for the ``memories_{dim}`` table. The
        # ``get_memory_model`` factory is a pure Python class builder (no
        # DB or network access), so constructing it here does NOT violate
        # the "no OneLLM calls in ctor" contract. When ``_ensure_dim``
        # resolves the real dim, ``self.MemoryModel`` is replaced.
        self.dimension = dimension
        self.MemoryModel = get_memory_model(dimension)

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
    def embedding_model_name(self) -> str:
        """Public accessor for the configured embedding model slug.

        Exposes the provider-prefixed slug string (e.g.
        ``"local/nomic-ai/nomic-embed-text-v1.5"``,
        ``"openai/text-embedding-3-small"``) used by this memory
        instance for embedding generation. External consumers
        (``persistent_manager.py``, etc.) should read this public
        property instead of reaching into the private
        ``_embedding_model_name`` attribute.
        """
        return self._embedding_model_name

    async def _ensure_dim(self) -> int:
        """Probe the embedding dimension exactly once and memoize it.

        On first invocation this calls
        :func:`services.memory.embedding.probe_dimension` for the
        configured model slug, stores the result on ``self._dimension``,
        and refreshes ``self.MemoryModel`` / ``self.dimension`` so the
        correct ``memories_{dim}`` ORM binding is used for subsequent
        operations.

        Concurrent callers are serialized by ``self._dim_lock`` so only
        a single underlying ``probe_dimension`` call is issued even when
        multiple coroutines hit this method simultaneously on a fresh
        instance.
        """
        if self._dimension is not None:
            return self._dimension

        async with self._dim_lock:
            # Re-check under the lock — another coroutine may have probed
            # while we were queued on ``acquire``.
            if self._dimension is not None:
                return self._dimension

            probed = await probe_dimension(self._embedding_model_name)
            self._dimension = probed
            self.dimension = probed
            self.MemoryModel = get_memory_model(probed)
            return probed

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
                result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
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
            if "already exists" in error_str or 'extension "vector" already exists' in error_str:
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
        Falls back to resolving external_user_id for direct API calls and tests,
        with an in-process cache to avoid repeated database lookups within the
        same formation lifetime (the identifier-to-ID mapping is immutable).

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
            # Determine the identifier to resolve
            if not self.is_multi_user:
                identifier = "0"
            elif external_user_id:
                identifier = external_user_id
            else:
                raise ValueError(
                    "RequestContext not available and no external_user_id provided. "
                    "This should not happen in normal operation."
                )

            # Check in-process cache (formation-lifetime, identifier is immutable)
            cache = getattr(self, "_user_id_cache", None)
            if cache is None:
                self._user_id_cache: dict = {}
                cache = self._user_id_cache

            cache_key = f"{self.formation_id}:{identifier}"
            if cache_key in cache:
                return cache[cache_key]

            from ...utils.user_resolution import resolve_user_identifier

            resolved_user = await resolve_user_identifier(
                identifier=identifier,
                formation_id=self.formation_id,
                db_manager=self.db_manager,
                kv_cache=None,
            )
            if resolved_user is None:
                raise ValueError(f"Failed to resolve user identifier: {identifier}")
            internal_user_id, _ = resolved_user
            cache[cache_key] = internal_user_id
            return internal_user_id

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
                    select(User.id).where(User.formation_id == self.formation_id).limit(1)
                    if not self.is_multi_user
                    else select(User.id)
                    .join(UserIdentifier)
                    .where(
                        UserIdentifier.identifier == external_user_id,
                        UserIdentifier.formation_id == self.formation_id,
                    )
                )
                user_id = result.scalar_one_or_none()

                if user_id:
                    return int(user_id)

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

                return int(new_user.id)

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
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[Union[List[float], np.ndarray]] = None,
        user_id: Optional[str] = None,
        collection: Optional[str] = None,
        external_user_id: Optional[str] = None,  # Alias for user_id (for Memobase compatibility)
        scope: Optional[Tuple[str, str]] = None,
    ) -> str:
        """
        Asynchronously adds new content to long-term memory, generating an embedding if not provided.

        Parameters:
            content (str): The text content to store.
            metadata (dict, optional): Additional metadata to associate with the content.
            embedding (list[float] or np.ndarray, optional): Pre-computed embedding vector.
            If not provided, an embedding is generated.
            user_id (str, optional): The user identifier (will be resolved to internal_user_id).
            external_user_id (str, optional): Alias for user_id (for Memobase compatibility).
            collection (str, optional): The collection to store the memory in.
            If not provided, uses the default collection.
            scope (tuple, optional): ``(scope_type, scope_id)`` -- the memory
                namespace this row is written to. ``None`` (the default)
                keeps today's behavior: user scope, scope_id mirroring the
                owning internal user id. Shared scopes
                (``('formation', formation_id)`` / ``('group', group_id)``)
                are AUTHORIZED BY THE CALLER via a ``memory.write`` grant
                (services/memory/scopes.py) -- this storage layer only
                stamps what it is told, so event replay can reproduce
                shared rows without permission machinery.

        Returns:
            str: The unique ID of the newly created memory entry.
        """
        # Handle external_user_id as alias for user_id
        if external_user_id is not None and user_id is None:
            user_id = external_user_id
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

        # Generate embedding if not provided.
        # Write paths use ``task="search_document"`` — the Nomic-style
        # prefix marks these inputs as corpus documents; the helper strips
        # the kwarg for cloud providers that don't honor it.
        if embedding is None:
            await self._ensure_dim()
            vectors = await embed(
                self._embedding_model_name,
                content,
                task="search_document",
            )
            embedding = vectors[0]

        # Insert into database using async method
        memory_id = await self._add_internal_async(
            content, embedding, metadata, collection, user_id, scope=scope
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
        metadata: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
        user_id: Optional[str] = None,
        scope: Optional[Tuple[str, str]] = None,
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
            scope (tuple, optional): ``(scope_type, scope_id)``; None = user scope.

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

        # Default (Phase 1 behavior): user scope, scope_id mirroring the
        # owning internal user id. Shared scopes stamp the caller-provided
        # (already authorized) target; user_id still records the writer.
        scope_type, scope_id = self._resolve_write_scope(scope, internal_user_id)

        async with self.db_manager.get_async_session() as session:
            # Convert numpy array to list if necessary
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            # Create memory using async model helper with internal user ID.
            memory = await self.MemoryModel.create(
                session,
                user_id=internal_user_id,  # Use resolved internal ID
                text=text,
                embedding=embedding,
                meta_data=metadata,
                collection=collection,
                scope_type=scope_type,
                scope_id=scope_id,
            )

            # Return ID
            return memory.id

    def _resolve_write_scope(
        self, scope: Optional[Tuple[str, str]], internal_user_id: int
    ) -> Tuple[str, str]:
        """Resolve a write's ``(scope_type, scope_id)`` stamp.

        ``None`` -> user scope with scope_id mirroring the owning internal
        user id (byte-identical to Phase 1). A ``('formation', ...)`` scope
        forces scope_id to this memory's formation id so a caller can never
        cross-stamp another formation's namespace.
        """
        if scope is None:
            return SCOPE_TYPE_USER, str(internal_user_id)
        scope_type, scope_id = scope
        validate_scope(scope_type, scope_id)
        if scope_type == SCOPE_TYPE_USER:
            return SCOPE_TYPE_USER, str(internal_user_id)
        if scope_type == SCOPE_TYPE_FORMATION:
            return SCOPE_TYPE_FORMATION, self.formation_id
        return scope_type, scope_id

    def _add_internal(
        self,
        text: str,
        embedding: Union[List[float], np.ndarray],
        metadata: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
        external_user_id: Optional[str] = None,
        scope: Optional[Tuple[str, str]] = None,
    ) -> str:
        """
        Synchronously adds a new memory entry to the database with associated text, embedding, metadata, and collection.

        Parameters:
            text (str): The text content to store.
            embedding (Union[List[float], np.ndarray]): The vector embedding representing the text.
            metadata (Dict[str, Any], optional): Additional metadata to associate with the memory.
            collection (str, optional): The collection name to store the memory in.
            external_user_id (str, optional): The external user identifier for multi-user environments.
            scope (tuple, optional): ``(scope_type, scope_id)``; None = user scope.

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

        # None = user scope with scope_id mirroring the owning internal
        # user id; shared scopes stamp the caller-authorized target.
        scope_type, scope_id = self._resolve_write_scope(scope, internal_user_id)

        with self.Session() as session:
            # Convert numpy array to list if necessary
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            memory = self.MemoryModel(
                user_id=internal_user_id,
                text=text,
                embedding=embedding,
                meta_data=metadata,
                collection=collection,
                scope_type=scope_type,
                scope_id=scope_id,
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
        collections: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Asynchronously performs a semantic similarity search for memories matching a text query.

        If a query embedding is not provided, it is generated using the embedding model.
        Supports filtering by collection and metadata, and returns a list of the most relevant
        memories with similarity scores.

        Memory namespaces (Phases 2+3): by default the search fans out over
        the requesting user's scope chain -- user rows, each group the user
        belongs to, and the formation scope -- and merges by score with
        specificity-wins weighting. Results carry ``scope_type`` /
        ``scope_id`` so callers can attribute provenance.

        Parameters:
            query (str): The text query to search for.
            limit (int): Maximum number of results to return.
            query_embedding (Optional[Union[List[float], np.ndarray]]): Opt. pre-computed embedding vector for query.
            collection (Optional[str]): The collection to search in. Defaults to the default collection.
            collections (Optional[List[str]]): Optional list of collections to search in one query.
            filter_metadata (Optional[Dict[str, Any]]): Optional metadata filters to apply.
            external_user_id (Optional[str]): The external user ID for multi-user environments.
            scopes (Optional[List[str]]): Per-query narrowing for
                privacy-sensitive callers -- e.g. ``["user"]`` restores the
                exact Phase 1 user-only query. None = full cascade.
            group_ids (Optional[List[str]]): Explicit group ids for the
                group-scope branch. Default: the per-request
                ResolvedPermissions (GBAC ContextVar) set by the request
                pipeline, or no group scopes.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing memory IDs, text, metadata, and similarity scores,
                                  ordered by relevance.
        """
        normalized_collections = list(
            dict.fromkeys(
                collection_name
                for collection_name in (collections or [collection or self.default_collection])
                if collection_name
            )
        )

        # Emit memory search started event
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "query_length": len(query),
                "limit": limit,
                "has_query_embedding": query_embedding is not None,
                "collection": (
                    normalized_collections[0]
                    if len(normalized_collections) == 1
                    else "__multiple__"
                ),
                "collections": normalized_collections,
                "collections_count": len(normalized_collections),
                "has_metadata_filter": filter_metadata is not None,
            },
            description="Long-term memory search started",
        )

        # Generate embedding if not provided.
        # Search paths use ``task="search_query"`` — the Nomic-style
        # prefix marks these inputs as retrieval queries; the helper
        # strips the kwarg for cloud providers that don't honor it.
        if query_embedding is None:
            await self._ensure_dim()
            vectors = await embed(
                self._embedding_model_name,
                query,
                task="search_query",
            )
            query_embedding = vectors[0]

        # Search in database using async method
        results = await self._search_internal_async(
            query_embedding,
            limit,
            normalized_collections,
            filter_metadata,
            external_user_id,
            scopes=scopes,
            group_ids=group_ids,
        )

        # Format results
        formatted_results = []
        for score, memory in results:
            formatted_results.append(
                {
                    "id": memory["id"],
                    "text": memory["text"],
                    "metadata": memory["meta_data"],
                    "collection": memory.get("collection"),
                    "score": score,
                    "scope_type": memory.get("scope_type", SCOPE_TYPE_USER),
                    "scope_id": memory.get("scope_id"),
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
                "collection": (
                    normalized_collections[0]
                    if len(normalized_collections) == 1
                    else "__multiple__"
                ),
                "collections": normalized_collections,
                "collections_count": len(normalized_collections),
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
        collections: Optional[List[str]] = None,
        query_embedding: Optional[Union[List[float], np.ndarray]] = None,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Build search parameters for the LongTermMemory search method.

        Args:
            query: The search query text
            k: Number of results to return
            user_id: Optional user ID for filtering
            full_filter: Optional metadata filter
            collection: Optional collection name
            collections: Optional collection names
            query_embedding: Optional precomputed query embedding
            scopes: Optional per-query scope narrowing (e.g. ["user"])

        Returns:
            Dictionary of parameters for the search method
        """
        search_params = {
            "query": query,
            "limit": k,
            "filter_metadata": full_filter,
        }

        if query_embedding is not None:
            search_params["query_embedding"] = query_embedding

        if user_id is not None:
            search_params["external_user_id"] = user_id

        if scopes is not None:
            search_params["scopes"] = scopes

        if collections:
            search_params["collections"] = collections
        elif collection:
            search_params["collection"] = collection

        return search_params

    def _search_internal(
        self,
        query_embedding: Union[List[float], np.ndarray],
        k: int = 5,
        collections: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Internal method to search for similar embeddings in the database.

        This is a synchronous implementation that directly interacts with
        the database to perform vector similarity search with optional
        metadata filtering.

        NOTE (memory namespaces): this legacy sync path stays user-scope
        only -- the shared-scope read fan-out lives on the async path
        (``_search_internal_async``), which every runtime retrieval
        surface uses.

        Args:
            query_embedding: The vector embedding to search for.
            k: Maximum number of results to return.
            collections: The collections to search in. If None, uses the default collection.
            filter_metadata: Optional metadata filters to apply.

        Returns:
            A list of tuples containing (similarity_score, memory_dict).
        """
        # Convert numpy array to list if necessary
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()

        normalized_collections = list(
            dict.fromkeys(
                collection_name
                for collection_name in (collections or [self.default_collection])
                if collection_name
            )
        )

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = self._resolve_user_id_sync(external_user_id)

        with self.Session() as session:
            # For PostgreSQL with pgvector, we need to cast the query embedding
            if self.db_manager.database_type == "postgresql":
                distance_expr = self.MemoryModel.embedding.l2_distance(query_embedding).label(
                    "distance"
                )
            else:
                distance_expr = func.l2_distance(self.MemoryModel.embedding, query_embedding).label(
                    "distance"
                )

            # Build query
            query = (
                select(self.MemoryModel, distance_expr)
                .filter(
                    self.MemoryModel.user_id == internal_user_id,
                )
                .order_by("distance")
                .limit(k)
            )

            if len(normalized_collections) == 1:
                query = query.filter(self.MemoryModel.collection == normalized_collections[0])
            else:
                query = query.filter(self.MemoryModel.collection.in_(normalized_collections))

            # Add metadata filters if provided
            if filter_metadata:
                for key, value in filter_metadata.items():
                    query = query.filter(self.MemoryModel.meta_data[key].astext == str(value))

            # Execute query
            results = session.execute(query).all()

            # Format results — use index [0] for the model instance since
            # the dynamic class name varies (Memory_384, Memory_1536, etc.)
            return [
                (
                    1.0 / (1.0 + float(result.distance)),  # Convert distance to similarity score
                    {
                        "id": result[0].id,
                        "text": result[0].text,
                        "meta_data": result[0].meta_data,
                        "collection": result[0].collection,
                        "created_at": (
                            result[0].created_at.isoformat() if result[0].created_at else None
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
                session.query(self.MemoryModel)
                .join(User, self.MemoryModel.user_id == User.id)
                .filter(
                    self.MemoryModel.id == memory_id,
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
                session.query(self.MemoryModel)
                .join(User, self.MemoryModel.user_id == User.id)
                .filter(
                    self.MemoryModel.id == memory_id,
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

    def delete(
        self,
        memory_id: str,
        external_user_id: Optional[str] = None,  # For Memobase API compatibility (not used here)
    ) -> bool:
        """
        Delete a memory by ID.

        This method permanently removes a memory entry from the database.

        Args:
            memory_id: The ID of the memory to delete.
            external_user_id: Not used in LongTermMemory (for Memobase API compatibility).

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
                session.query(self.MemoryModel)
                .join(User, self.MemoryModel.user_id == User.id)
                .filter(
                    self.MemoryModel.id == memory_id,
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

            collections: List[Any] = (
                session.query(distinct(self.MemoryModel.collection))
                .filter(
                    self.MemoryModel.user_id == internal_user_id,
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
                session.query(self.MemoryModel)
                .filter(
                    self.MemoryModel.collection == name,
                    self.MemoryModel.user_id == internal_user_id,
                )
                .count()
            )

            if memories_count == 0:
                return False

            if delete_memories:
                # Delete all memories in the collection for this user
                session.query(self.MemoryModel).filter(
                    self.MemoryModel.collection == name,
                    self.MemoryModel.user_id == internal_user_id,
                ).delete()
            else:
                # Move memories to default collection for this user
                session.query(self.MemoryModel).filter(
                    self.MemoryModel.collection == name,
                    self.MemoryModel.user_id == internal_user_id,
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
                session.query(self.MemoryModel)
                .join(User, self.MemoryModel.user_id == User.id)
                .filter(
                    self.MemoryModel.collection == collection_name,
                    User.formation_id == self.formation_id,
                )
                .order_by(desc(self.MemoryModel.created_at))
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

    async def list_memories(
        self,
        limit: int = 10,
        offset: int = 0,
        collection: Optional[str] = None,
        external_user_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List memories for a specific user without vector search (no embeddings required).

        The user branch is USER-SPECIFIC exactly as before (owned rows in
        the requested collection). By default the listing also fans out to
        the shared scopes the user can read -- group rows for the user's
        memberships and formation rows -- in one query so pagination stays
        correct. ``scopes=["user"]`` restores the Phase 1 user-only listing.

        Parameters:
            limit: Maximum number of memories to return.
            offset: Number of memories to skip (for pagination).
            collection: Optional collection name to filter by (user branch
                only -- shared rows are addressed by scope, not collection).
            external_user_id: The external user identifier (required in multi-user mode).
            scopes: Per-query scope narrowing (None = full cascade).
            group_ids: Explicit group memberships (None = ContextVar / resolver).

        Returns:
            List of memory dictionaries with id, text, metadata, timestamps, scope.
        """
        # Resolve internal user ID (handles single-user vs multi-user)
        internal_user_id = await self._resolve_user_id_async(external_user_id)

        collection_name = collection or self.default_collection

        read_scopes = normalize_read_scopes(scopes)
        read_group_ids: Tuple[str, ...] = ()
        if SCOPE_TYPE_GROUP in read_scopes:
            read_group_ids = await resolve_read_group_ids(group_ids)

        from sqlalchemy import and_, or_

        conditions = []
        if SCOPE_TYPE_USER in read_scopes:
            conditions.append(
                and_(
                    self.MemoryModel.user_id == internal_user_id,
                    self.MemoryModel.collection == collection_name,
                    self.MemoryModel.scope_type == SCOPE_TYPE_USER,
                )
            )
        if SCOPE_TYPE_GROUP in read_scopes and read_group_ids:
            conditions.append(
                and_(
                    self.MemoryModel.scope_type == SCOPE_TYPE_GROUP,
                    self.MemoryModel.scope_id.in_(list(read_group_ids)),
                )
            )
        if SCOPE_TYPE_FORMATION in read_scopes:
            conditions.append(
                and_(
                    self.MemoryModel.scope_type == SCOPE_TYPE_FORMATION,
                    self.MemoryModel.scope_id == self.formation_id,
                )
            )
        if not conditions:
            return []

        async with self.AsyncSession() as session:
            query = select(self.MemoryModel).where(or_(*conditions))
            if read_group_ids:
                # Group ids are only unique per formation; isolate through
                # the writers' users rows (same posture as the search
                # fan-out). The join is a no-op filter for the other
                # branches -- every memory row has an owning user here.
                query = query.join(User, self.MemoryModel.user_id == User.id).where(
                    User.formation_id == self.formation_id
                )
            query = query.order_by(desc(self.MemoryModel.created_at)).offset(offset).limit(limit)

            result = await session.execute(query)
            memories = result.scalars().all()

            return [
                {
                    "id": m.id,
                    "text": m.text,
                    "content": m.text,  # Alias for API compatibility
                    "meta_data": m.meta_data,
                    "metadata": m.meta_data,  # Alias for API compatibility
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                    "collection": m.collection,
                    "scope_type": m.scope_type or SCOPE_TYPE_USER,
                    "scope_id": m.scope_id,
                }
                for m in memories
            ]

    async def list_extracted_orphan_memories(
        self, external_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extraction rows without event provenance (legacy backfill support).

        Rows whose metadata says ``source == 'extraction'`` but carries no
        ``derived_from_event_id`` predate the memory event substrate; the
        backfill synthesizes fact.extracted events for exactly these so a
        rebuild can recreate them. Non-extraction rows are never listed.
        """
        internal_user_id = await self._resolve_user_id_async(external_user_id)
        source_marker = type_coerce(self.MemoryModel.meta_data, JSON)["source"].as_string()
        event_marker = type_coerce(self.MemoryModel.meta_data, JSON)[
            "derived_from_event_id"
        ].as_string()
        async with self.AsyncSession() as session:
            query = (
                select(self.MemoryModel)
                .where(self.MemoryModel.user_id == internal_user_id)
                .where(source_marker == "extraction")
                .where(event_marker.is_(None))
                .order_by(self.MemoryModel.created_at, self.MemoryModel.id)
            )
            rows = (await session.execute(query)).scalars().all()
            return [
                {
                    "id": row.id,
                    "text": row.text,
                    "collection": row.collection,
                    "metadata": row.meta_data or {},
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    async def delete_extracted_memories(self, external_user_id: Optional[str] = None) -> int:
        """
        Delete every event-sourced memory for a user (all collections).

        Rebuild support for the memory event substrate: only rows a replay
        recreates are removed -- extractor rows (metadata ``source ==
        'extraction'``) and any row carrying a ``derived_from_event_id``
        provenance link (e.g. shared-scope writes recorded through the
        event substrate). Conversations, knowledge uploads, and manually
        created user memories are not event-sourced and survive a rebuild.
        On pre-shared-scope data the two criteria coincide (every
        extraction row carries the provenance link), so this stays a
        zero-behavior change for Phase 1 databases.

        Returns:
            The number of memories deleted.
        """
        internal_user_id = await self._resolve_user_id_async(external_user_id)
        from sqlalchemy import or_

        # type_coerce gives the JSONType column a JSON-typed expression so
        # the path operator compiles per dialect (``meta_data ->> 'source'``
        # on PostgreSQL, ``JSON_EXTRACT`` elsewhere) instead of failing on
        # the decorator's TEXT impl.
        source_marker = type_coerce(self.MemoryModel.meta_data, JSON)["source"].as_string()
        event_marker = type_coerce(self.MemoryModel.meta_data, JSON)[
            "derived_from_event_id"
        ].as_string()
        stmt = (
            sql_delete(self.MemoryModel)
            .where(self.MemoryModel.user_id == internal_user_id)
            .where(or_(source_marker == "extraction", event_marker.is_not(None)))
        )
        async with self.AsyncSession() as session:
            result = await session.execute(stmt)
            await session.commit()
            return int(result.rowcount or 0)

    # Async collection methods removed - using simple column-based collections

    async def _search_internal_async(
        self,
        query_embedding: Union[List[float], np.ndarray],
        k: int = 5,
        collections: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Asynchronously searches for memories with embeddings most similar to the given query embedding.

        Memory namespaces read fan-out (write-one-read-up): one branch query
        per scope in the cascade, merged by specificity-weighted score:

        * user branch -- exactly the Phase 1 query (user_id + collection +
          metadata filters) plus ``scope_type='user'``, which is a no-op
          filter for all pre-fan-out data.
        * group branch -- ``scope_type='group' AND scope_id IN <the user's
          groups>``. Formation isolation comes from the users join (group
          ids are only unique per formation). No collection filter:
          collections are a user-space organization scheme; shared rows are
          addressed by scope.
        * formation branch -- ``scope_type='formation' AND scope_id =
          <formation id>`` (the scope id IS the formation id, so no join is
          needed for isolation).

        Branches are disjoint on scope_type, so the merge cannot duplicate
        rows. Sorting uses similarity * SCOPE_WEIGHTS[scope_type]
        (specificity wins on conflicts); the reported score stays the raw
        similarity so user-scope scores are unchanged from Phase 1.

        Parameters:
            query_embedding: The embedding vector to search against.
            k: Maximum number of results to return.
            collections: Collections to search in; defaults to the default collection if not specified.
            filter_metadata: Optional dictionary of metadata key-value pairs to filter results.
            external_user_id: External user identifier to scope the search.
            scopes: Per-query narrowing (None = full user+group+formation cascade).
            group_ids: Explicit group memberships (None = ContextVar / resolver).

        Returns:
            A list of tuples, each containing a similarity score (float) and a dictionary with memory details.
        """
        # Convert numpy array to list if necessary
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()

        normalized_collections = list(
            dict.fromkeys(
                collection_name
                for collection_name in (collections or [self.default_collection])
                if collection_name
            )
        )

        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = await self._resolve_user_id_async(external_user_id)

        read_scopes = normalize_read_scopes(scopes)
        read_group_ids: Tuple[str, ...] = ()
        if SCOPE_TYPE_GROUP in read_scopes:
            read_group_ids = await resolve_read_group_ids(group_ids)

        async with self.db_manager.get_async_session() as session:
            # For PostgreSQL with pgvector, we need to cast the query embedding
            if self.db_manager.database_type == "postgresql":
                distance_expr = self.MemoryModel.embedding.l2_distance(query_embedding).label(
                    "distance"
                )
            else:
                distance_expr = func.l2_distance(self.MemoryModel.embedding, query_embedding).label(
                    "distance"
                )

            def _apply_metadata_filters(query):
                if filter_metadata:
                    for key, value in filter_metadata.items():
                        query = query.filter(self.MemoryModel.meta_data[key].astext == str(value))
                return query

            branch_queries = []

            if SCOPE_TYPE_USER in read_scopes:
                user_query = (
                    select(self.MemoryModel, distance_expr)
                    .filter(
                        self.MemoryModel.user_id == internal_user_id,
                        self.MemoryModel.scope_type == SCOPE_TYPE_USER,
                    )
                    .order_by("distance")
                    .limit(k)
                )
                if len(normalized_collections) == 1:
                    user_query = user_query.filter(
                        self.MemoryModel.collection == normalized_collections[0]
                    )
                else:
                    user_query = user_query.filter(
                        self.MemoryModel.collection.in_(normalized_collections)
                    )
                branch_queries.append(_apply_metadata_filters(user_query))

            if SCOPE_TYPE_GROUP in read_scopes and read_group_ids:
                group_query = (
                    select(self.MemoryModel, distance_expr)
                    .join(User, self.MemoryModel.user_id == User.id)
                    .filter(
                        User.formation_id == self.formation_id,
                        self.MemoryModel.scope_type == SCOPE_TYPE_GROUP,
                        self.MemoryModel.scope_id.in_(list(read_group_ids)),
                    )
                    .order_by("distance")
                    .limit(k)
                )
                branch_queries.append(_apply_metadata_filters(group_query))

            if SCOPE_TYPE_FORMATION in read_scopes:
                formation_query = (
                    select(self.MemoryModel, distance_expr)
                    .filter(
                        self.MemoryModel.scope_type == SCOPE_TYPE_FORMATION,
                        self.MemoryModel.scope_id == self.formation_id,
                    )
                    .order_by("distance")
                    .limit(k)
                )
                branch_queries.append(_apply_metadata_filters(formation_query))

            merged: List[Tuple[float, float, Dict[str, Any]]] = []
            for branch_query in branch_queries:
                result = await session.execute(branch_query)
                # Use index [0] for the model instance since the dynamic
                # class name varies (Memory_384, Memory_1536, etc.)
                for row in result.all():
                    similarity = 1.0 / (1.0 + float(row.distance))
                    scope_type = row[0].scope_type or SCOPE_TYPE_USER
                    weighted = similarity * SCOPE_WEIGHTS.get(scope_type, 1.0)
                    merged.append(
                        (
                            weighted,
                            similarity,
                            {
                                "id": row[0].id,
                                "text": row[0].text,
                                "meta_data": row[0].meta_data,
                                "collection": row[0].collection,
                                "scope_type": scope_type,
                                "scope_id": row[0].scope_id,
                                "created_at": (
                                    row[0].created_at.isoformat() if row[0].created_at else None
                                ),
                            },
                        )
                    )

            # Specificity-weighted merge; the exposed score stays the raw
            # similarity (user-branch scores identical to Phase 1).
            merged.sort(key=lambda item: item[0], reverse=True)
            return [(similarity, memory) for _, similarity, memory in merged[:k]]

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
                table_name = self.MemoryModel.__tablename__
                sql = sql_text(f"""
                    SELECT
                        m.id,
                        m.text,
                        m.meta_data,
                        m.created_at,
                        ts_rank(to_tsvector('simple', m.text), plainto_tsquery('simple', :query)) as rank
                    FROM {table_name} m
                    JOIN users u ON m.user_id = u.id
                    WHERE u.id = :user_id
                        AND u.formation_id = :formation_id
                        AND m.collection = :collection
                        AND to_tsvector('simple', m.text) @@ plainto_tsquery('simple', :query)
                    ORDER BY rank DESC
                    LIMIT :limit
                """)

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
                    select(self.MemoryModel)
                    .filter(
                        self.MemoryModel.user_id == internal_user_id,
                        self.MemoryModel.collection == collection,
                        self.MemoryModel.text.ilike(f"%{query}%"),
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
