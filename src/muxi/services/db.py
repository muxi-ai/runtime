"""
Unified Database Manager for MUXI Services

Provides centralized database connection management for all MUXI services
including long-term memory and scheduler. Supports both PostgreSQL and SQLite
with automatic detection and shared connection pooling.

Key Features:
- Auto-detection of database type from connection string
- Shared SQLAlchemy engine and session management
- Connection pooling for optimal resource usage
- Support for both PostgreSQL and SQLite backends
- Unified table creation utilities
- Consistent error handling and observability
"""

import os
from typing import Optional, Any, Dict
from urllib.parse import urlparse

from contextlib import asynccontextmanager
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from . import observability
from ..utils.user_dirs import get_memory_dir

# Create a shared base for all MUXI models
Base = declarative_base()


class AsyncModelMixin:
    """
    Mixin class to add common async query helpers to SQLAlchemy models.

    Usage:
        class MyModel(Base, AsyncModelMixin):
            __tablename__ = 'my_table'
            ...
    """

    @classmethod
    async def get(cls, session: AsyncSession, **kwargs):
        """
        Asynchronously retrieves a single model instance matching the given filter criteria.

        Parameters:
            session (AsyncSession): The asynchronous database session.
            **kwargs: Field-based filters to apply to the query.

        Returns:
            The model instance if found, or None if no match exists.
        """
        from sqlalchemy import select
        stmt = select(cls).filter_by(**kwargs)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_all(cls, session: AsyncSession, **kwargs):
        """
        Asynchronously retrieve all instances of the model matching the given filter criteria.

        Parameters:
            session (AsyncSession): The asynchronous database session.
            **kwargs: Attribute-based filters to apply to the query.

        Returns:
            List: All model instances matching the specified criteria.
        """
        from sqlalchemy import select
        stmt = select(cls).filter_by(**kwargs)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs):
        """
        Asynchronously creates and adds a new model instance to the database session.

        Parameters:
            session (AsyncSession): The asynchronous database session.
            **kwargs: Attribute values for the new model instance.

        Returns:
            The newly created model instance with any database-assigned fields populated after flush.
        """
        instance = cls(**kwargs)
        session.add(instance)
        await session.flush()  # Flush to get ID without committing
        return instance

    async def update(self, session: AsyncSession, **kwargs):
        """
        Asynchronously updates the instance's attributes with the provided values and flushes changes to the database.

        Parameters:
            session (AsyncSession): The asynchronous database session used for the update.
            **kwargs: Attribute-value pairs to update on the instance.
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        await session.flush()

    async def delete(self, session: AsyncSession):
        """
        Asynchronously deletes this model instance from the database and flushes the session.

        Parameters:
            session (AsyncSession): The asynchronous database session used for the operation.
        """
        await session.delete(self)
        await session.flush()


class DatabaseManager:
    """
    Unified database manager for all MUXI services.

    Provides centralized connection management, automatic database type detection,
    and shared connection pooling for optimal resource usage across services.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        statement_timeout_seconds: int = 30,
        pool_size: int = 20,
        max_overflow: int = 40,
        idle_transaction_timeout_seconds: int = 60,
    ):
        """
        Initializes the database manager with synchronous engine and session support,
        resolving the connection string and database type.

        If no connection string is provided, attempts to load from environment variables
        or defaults to SQLite. Prepares for lazy initialization of asynchronous engine
        and session factory. Emits an observability event upon successful initialization.

        Args:
            connection_string: Database connection string (None for environment/default)
            statement_timeout_seconds: Maximum time for individual SQL queries.
                                      Must be a positive integer, range: 1-3600 seconds (default: 30)
            pool_size: Number of connections to maintain in the pool (default: 20)
            max_overflow: Max connections above pool_size (default: 40)
            idle_transaction_timeout_seconds: Timeout for idle transactions in seconds (default: 60)

        Raises:
            ValueError: If statement_timeout_seconds is invalid (not int, <= 0, or > 3600)
            ValueError: If pool_size or max_overflow are negative integers
        """
        self.connection_string = self._resolve_connection_string(connection_string)
        self.database_type = self._detect_database_type(self.connection_string)

        # Validate statement_timeout_seconds
        if not isinstance(statement_timeout_seconds, int):
            raise ValueError(
                f"statement_timeout_seconds must be an integer, got {type(statement_timeout_seconds).__name__}"
            )
        if statement_timeout_seconds <= 0:
            raise ValueError(
                f"statement_timeout_seconds must be positive, got {statement_timeout_seconds}"
            )
        if statement_timeout_seconds > 3600:
            raise ValueError(
                f"statement_timeout_seconds must be <= 3600 seconds (1 hour), got {statement_timeout_seconds}"
            )
        self.statement_timeout_seconds = statement_timeout_seconds

        # Validate pool_size and max_overflow
        if not isinstance(pool_size, int) or pool_size < 0:
            raise ValueError(f"pool_size must be a non-negative integer, got {pool_size}")
        if not isinstance(max_overflow, int) or max_overflow < 0:
            raise ValueError(f"max_overflow must be a non-negative integer, got {max_overflow}")
        self.pool_size = pool_size
        self.max_overflow = max_overflow

        # Validate idle_transaction_timeout_seconds
        if not isinstance(idle_transaction_timeout_seconds, int) or idle_transaction_timeout_seconds < 0:
            raise ValueError(
                "idle_transaction_timeout_seconds must be a non-negative integer, "
                f"got {idle_transaction_timeout_seconds}"
            )
        self.idle_transaction_timeout_seconds = idle_transaction_timeout_seconds

        # Create sync engine first
        self.engine = self._create_engine()
        self.Session = sessionmaker(bind=self.engine)

        # Lazy initialization for async engine to avoid import errors
        self._async_engine = None
        self._async_session_factory = None
        self._async_pgvector_initialized = False

        # Keep track of cleanup tasks to avoid warnings about unawaited tasks
        self._cleanup_tasks = []

        # Note: pgvector extension for async engine will be initialized on first use

        pass  # REMOVED: init-phase observe() call

        # Don't print here - persistent memory init message already shows database type
        # (Database only initializes when persistent memory is configured, so this message is redundant)

    def _resolve_connection_string(self, connection_string: Optional[str]) -> str:
        """
        Determines the database connection string using the provided argument,
        environment variables, or a default SQLite path.

        If no connection string is given, checks for PostgreSQL and SQLite environment
        variables before defaulting to a SQLite database file in the memory directory.

        Returns:
            str: The resolved database connection string.
        """
        if connection_string:
            return connection_string

        # Try environment variables
        postgres_url = os.getenv("POSTGRES_DATABASE_URL")
        if postgres_url:
            return postgres_url

        # Try SQLite environment variable
        sqlite_path = os.getenv("SQLITE_DATABASE_PATH")
        if sqlite_path:
            return f"sqlite:///{sqlite_path}"

        # Default to SQLite in memory directory
        memory_dir = get_memory_dir()
        default_path = f"{memory_dir}/muxi.db"
        return f"sqlite:///{default_path}"

    def _detect_database_type(self, connection_string: str) -> str:
        """
        Detect database type from connection string.

        Args:
            connection_string: Database connection string

        Returns:
            Database type ('postgresql' or 'sqlite')
        """
        parsed = urlparse(connection_string)
        scheme = parsed.scheme.lower()

        if scheme in ("postgresql", "postgres"):
            return "postgresql"
        elif scheme == "sqlite" or connection_string.endswith(".db"):
            return "sqlite"
        else:
            # Default to SQLite for unknown schemes
            observability.observe(
                event_type=observability.SystemEvents.DATABASE_TYPE_FALLBACK,
                level=observability.EventLevel.WARNING,
                data={
                    "connection_string": connection_string,
                    "detected_scheme": scheme,
                    "fallback_to": "sqlite",
                },
                description=f"Unknown database scheme '{scheme}', falling back to SQLite",
            )
            return "sqlite"

    def _create_engine(self):
        """
        Create and configure a synchronous SQLAlchemy engine for the detected database type.

        Returns:
            Engine: A configured SQLAlchemy engine instance for PostgreSQL or SQLite.
        """
        if self.database_type == "postgresql":
            # PostgreSQL configuration with connection pooling
            engine = create_engine(
                self.connection_string,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=30,
                pool_recycle=1800,
                echo=False,  # Set to True for SQL debugging
                connect_args={
                    # Set statement timeout to prevent hung queries
                    "options": f"-c statement_timeout={self.statement_timeout_seconds * 1000}"
                },
            )

            # Enable pgvector extension for PostgreSQL
            try:
                with engine.connect() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    conn.commit()
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.DATABASE_EXTENSION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e)},
                    description="Failed to create pgvector extension (may not be needed)",
                )

        else:  # SQLite
            # SQLite configuration
            engine = create_engine(
                self.connection_string,
                echo=False,  # Set to True for SQL debugging
                connect_args={"check_same_thread": False},  # Allow multi-threading
            )

        return engine

    def _create_async_engine(self):
        """
        Create and return an asynchronous SQLAlchemy engine configured for either
        PostgreSQL or SQLite, using the appropriate async driver and pooling options.

        Returns:
            AsyncEngine: An async SQLAlchemy engine instance configured for the detected database type.
        """
        # Convert connection string to async driver format
        async_connection_string = self._convert_to_async_connection_string()

        if self.database_type == "postgresql":
            # PostgreSQL async configuration with connection pooling
            # Higher limits than sync due to async concurrency patterns
            engine = create_async_engine(
                async_connection_string,
                pool_size=50,  # Increased for high async concurrency
                max_overflow=100,  # Total max connections: 150
                pool_timeout=30,
                pool_recycle=1800,
                pool_pre_ping=True,  # Verify connections before use
                echo=False,  # Set to True for SQL debugging
                connect_args={
                    "server_settings": {
                        # Statement timeout prevents hung queries (milliseconds)
                        "statement_timeout": str(self.statement_timeout_seconds * 1000),
                        # Idle transaction timeout for cleanup (milliseconds)
                        "idle_in_transaction_session_timeout": str(self.idle_transaction_timeout_seconds * 1000),
                    }
                },
            )
        else:  # SQLite
            # SQLite async configuration
            engine = create_async_engine(
                async_connection_string,
                echo=False,  # Set to True for SQL debugging
            )

        return engine

    def _convert_to_async_connection_string(self) -> str:
        """
        Convert the synchronous database connection string to an async-compatible
        format for SQLAlchemy.

        Returns:
            str: The connection string modified for use with async drivers
            (`asyncpg` for PostgreSQL, `aiosqlite` for SQLite).
        """
        if self.database_type == "postgresql":
            # Replace postgresql:// with postgresql+asyncpg://
            if self.connection_string.startswith("postgresql://"):
                return self.connection_string.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif self.connection_string.startswith("postgres://"):
                return self.connection_string.replace("postgres://", "postgresql+asyncpg://", 1)
        else:  # SQLite
            # Replace sqlite:// with sqlite+aiosqlite://
            if self.connection_string.startswith("sqlite://"):
                return self.connection_string.replace("sqlite://", "sqlite+aiosqlite://", 1)

        return self.connection_string

    @property
    def async_engine(self):
        """
        Returns the asynchronous SQLAlchemy engine, initializing it if it has not been created yet.
        """
        if self._async_engine is None:
            self._async_engine = self._create_async_engine()
        return self._async_engine

    @property
    def AsyncSession(self):
        """
        Returns the async session factory for creating SQLAlchemy AsyncSession instances, initializing it if necessary.
        """
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                bind=self.async_engine, expire_on_commit=False
            )
        return self._async_session_factory

    async def _init_async_pgvector(self):
        """
        Attempts to enable the pgvector extension on the asynchronous PostgreSQL engine.

        If the extension cannot be created, emits a warning observability event.
        This operation is a no-op for non-PostgreSQL databases.
        """
        try:
            async with self.async_engine.connect() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.commit()
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_EXTENSION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "async": True},
                description="Failed to create pgvector extension for async engine (may not be needed)",
            )

    def get_session(self) -> Session:
        """
        Return a new synchronous SQLAlchemy session for database operations.

        Returns:
            Session: A new SQLAlchemy session instance.
        """
        return self.Session()

    @asynccontextmanager
    async def get_async_session(self):
        """
        Asynchronous context manager that yields a new database session with automatic commit, rollback, and cleanup.

        Yields:
            AsyncSession: An active asynchronous SQLAlchemy session.
        """
        # Initialize pgvector extension on first use for PostgreSQL
        if self.database_type == "postgresql" and not self._async_pgvector_initialized:
            await self._init_async_pgvector()
            self._async_pgvector_initialized = True

        async with self.AsyncSession() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    def create_tables(self, metadata: MetaData) -> None:
        """
        Create all tables defined in the provided SQLAlchemy metadata using the synchronous engine.

        Parameters:
            metadata (MetaData): SQLAlchemy metadata object containing table definitions.
        """
        try:
            metadata.create_all(self.engine)
            pass  # REMOVED: init-phase observe() call
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_TABLE_CREATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "database_type": self.database_type},
                description=f"Failed to create database tables: {e}",
            )
            raise

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Return details about the current database connection, including type,
        connection string, and engine pool statistics.

        Returns:
            dict: Contains the database type, connection string, engine pool size,
            and number of checked-out connections if available.
        """
        return {
            "database_type": self.database_type,
            "connection_string": self.connection_string,
            "engine_pool_size": (
                getattr(self.engine.pool, "size", None) if hasattr(self.engine, "pool") else None
            ),
            "engine_pool_checked_out": (
                getattr(self.engine.pool, "checkedout", None)
                if hasattr(self.engine, "pool")
                else None
            ),
        }

    async def create_tables_async(self, metadata: MetaData) -> None:
        """
        Asynchronously creates all tables defined in the provided SQLAlchemy metadata using the async engine.

        Parameters:
            metadata (MetaData): SQLAlchemy metadata object containing table definitions.

        Raises:
            Exception: Propagates any exception encountered during table creation.
        """
        try:
            async with self.async_engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
            pass  # REMOVED: init-phase observe() call
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_TABLE_CREATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "database_type": self.database_type, "async": True},
                description=f"Failed to create database tables (async): {e}",
            )
            raise

    async def close_async(self) -> None:
        """
        Asynchronously disposes of the async database engine and releases associated resources.
        """
        if self._async_engine is not None:
            await self._async_engine.dispose()

    def close(self) -> None:
        """
        Closes both synchronous and asynchronous database engines and cleans up associated resources.

        If an asynchronous engine exists, attempts to dispose of it appropriately
        based on the event loop state. In production, prefer using `close_async()`
        for asynchronous cleanup.
        """
        if hasattr(self, "engine"):
            self.engine.dispose()
        if self._async_engine is not None:
            # Note: This is synchronous disposal of async engine
            # In production, prefer using close_async() when possible
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule async disposal if event loop is running
                    task = asyncio.create_task(self._async_engine.dispose())
                    # Keep reference to avoid warnings about unawaited tasks
                    self._cleanup_tasks.append(task)
                    # Remove task from list when completed
                    task.add_done_callback(lambda t: self._cleanup_tasks.remove(t))
                else:
                    # Run disposal synchronously if no event loop
                    loop.run_until_complete(self._async_engine.dispose())
            except Exception:
                # Fallback to sync disposal
                pass


# Global database manager instance (initialized on first use)
_db_manager: Optional[DatabaseManager] = None


def get_database_manager(
    connection_string: Optional[str] = None, statement_timeout_seconds: int = 30
) -> DatabaseManager:
    """
    Get the global database manager instance (SINGLETON).

    **Important**: This function uses a module-level singleton. The FIRST call's parameters
    are authoritative and will be used to initialize the DatabaseManager. Subsequent calls
    with different parameters will be IGNORED and will return the existing instance.
    A warning will be logged if parameters differ from the existing instance.

    Args:
        connection_string: Optional connection string for initialization (only used on first call)
        statement_timeout_seconds: Maximum time for individual SQL queries (default: 30, only used on first call)

    Returns:
        DatabaseManager instance (singleton)

    Note:
        If you need multiple DatabaseManager instances with different configurations,
        create them directly using DatabaseManager() instead of this singleton function.
    """
    global _db_manager

    if _db_manager is None:
        _db_manager = DatabaseManager(connection_string, statement_timeout_seconds)
    else:
        # Check if parameters differ from existing instance and log warning
        params_differ = False
        differences = []

        if connection_string is not None and connection_string != _db_manager.connection_string:
            params_differ = True
            differences.append(
                f"connection_string (provided: {connection_string!r}, existing: {_db_manager.connection_string!r})"
            )

        if statement_timeout_seconds != _db_manager.statement_timeout_seconds:
            params_differ = True
            differences.append(
                f"statement_timeout_seconds (provided: {statement_timeout_seconds}, "
                f"existing: {_db_manager.statement_timeout_seconds})"
            )

        if params_differ:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "get_database_manager called with different parameters than existing instance. "
                "Using existing instance and IGNORING new parameters. "
                "Differences: %s",
                ", ".join(differences)
            )

    return _db_manager


def set_database_manager(db_manager: DatabaseManager) -> None:
    """
    Set the global database manager instance.

    Args:
        db_manager: DatabaseManager instance to set as global
    """
    global _db_manager
    _db_manager = db_manager
