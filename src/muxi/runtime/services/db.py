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
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
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
        Get a single instance by keyword arguments.
        
        Args:
            session: Async database session
            **kwargs: Filter criteria
            
        Returns:
            Model instance or None
        """
        from sqlalchemy import select
        stmt = select(cls).filter_by(**kwargs)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @classmethod
    async def get_all(cls, session: AsyncSession, **kwargs):
        """
        Get all instances matching the criteria.
        
        Args:
            session: Async database session
            **kwargs: Filter criteria
            
        Returns:
            List of model instances
        """
        from sqlalchemy import select
        stmt = select(cls).filter_by(**kwargs)
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @classmethod
    async def create(cls, session: AsyncSession, **kwargs):
        """
        Create a new instance.
        
        Args:
            session: Async database session
            **kwargs: Model attributes
            
        Returns:
            Created model instance
        """
        instance = cls(**kwargs)
        session.add(instance)
        await session.flush()  # Flush to get ID without committing
        return instance
    
    async def update(self, session: AsyncSession, **kwargs):
        """
        Update instance attributes.
        
        Args:
            session: Async database session
            **kwargs: Attributes to update
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        await session.flush()
    
    async def delete(self, session: AsyncSession):
        """
        Delete this instance.
        
        Args:
            session: Async database session
        """
        await session.delete(self)
        await session.flush()


class DatabaseManager:
    """
    Unified database manager for all MUXI services.

    Provides centralized connection management, automatic database type detection,
    and shared connection pooling for optimal resource usage across services.
    """

    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            connection_string: Database connection string. If None, will attempt
                              to load from environment or use default SQLite.
        """
        self.connection_string = self._resolve_connection_string(connection_string)
        self.database_type = self._detect_database_type(self.connection_string)

        # Create both sync and async engines for backward compatibility
        self.engine = self._create_engine()
        self.async_engine = self._create_async_engine()

        # Create both sync and async session factories
        self.Session = sessionmaker(bind=self.engine)
        self.AsyncSession = async_sessionmaker(bind=self.async_engine, expire_on_commit=False)

        # Initialize pgvector extension for async engine if PostgreSQL
        if self.database_type == "postgresql":
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._init_async_pgvector())
                else:
                    loop.run_until_complete(self._init_async_pgvector())
            except Exception:
                # Non-critical failure, extension might already exist
                pass

        observability.observe(
            event_type=observability.SystemEvents.DATABASE_MANAGER_INITIALIZED,
            level=observability.EventLevel.INFO,
            data={
                "database_type": self.database_type,
                "connection_configured": bool(self.connection_string),
                "async_support": True,
            },
            description=f"Database manager initialized with {self.database_type} (async support enabled)",
        )

    def _resolve_connection_string(self, connection_string: Optional[str]) -> str:
        """
        Resolve the database connection string from various sources.

        Args:
            connection_string: Explicitly provided connection string

        Returns:
            Resolved connection string
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
        Create SQLAlchemy engine with appropriate configuration.

        Returns:
            Configured SQLAlchemy engine
        """
        if self.database_type == "postgresql":
            # PostgreSQL configuration with connection pooling
            engine = create_engine(
                self.connection_string,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,
                echo=False,  # Set to True for SQL debugging
            )

            # Enable pgvector extension for PostgreSQL
            try:
                with engine.connect() as conn:
                    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
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
        Create async SQLAlchemy engine with appropriate configuration.

        Returns:
            Configured async SQLAlchemy engine
        """
        # Convert connection string to async driver format
        async_connection_string = self._convert_to_async_connection_string()
        
        if self.database_type == "postgresql":
            # PostgreSQL async configuration with connection pooling
            engine = create_async_engine(
                async_connection_string,
                pool_size=20,  # Increased for async operations
                max_overflow=40,  # Increased for async operations
                pool_timeout=30,
                pool_recycle=1800,
                pool_pre_ping=True,
                echo=False,  # Set to True for SQL debugging
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
        Convert sync connection string to async format.

        Returns:
            Async-compatible connection string
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
    
    async def _init_async_pgvector(self):
        """Initialize pgvector extension for async PostgreSQL connections."""
        try:
            async with self.async_engine.connect() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
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
        Get a new database session (synchronous).

        Returns:
            SQLAlchemy session instance
        """
        return self.Session()

    @asynccontextmanager
    async def get_async_session(self):
        """
        Get a new async database session with automatic transaction management.

        Yields:
            AsyncSession instance
        """
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
        Create tables for the given metadata.

        Args:
            metadata: SQLAlchemy metadata containing table definitions
        """
        try:
            metadata.create_all(self.engine)
            observability.observe(
                event_type=observability.SystemEvents.DATABASE_TABLES_CREATED,
                level=observability.EventLevel.INFO,
                data={"database_type": self.database_type},
                description="Database tables created successfully",
            )
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
        Get information about the database connection.

        Returns:
            Dictionary with connection information
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
        Create tables for the given metadata asynchronously.

        Args:
            metadata: SQLAlchemy metadata containing table definitions
        """
        try:
            async with self.async_engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
            observability.observe(
                event_type=observability.SystemEvents.DATABASE_TABLES_CREATED,
                level=observability.EventLevel.INFO,
                data={"database_type": self.database_type, "async": True},
                description="Database tables created successfully (async)",
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_TABLE_CREATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "database_type": self.database_type, "async": True},
                description=f"Failed to create database tables (async): {e}",
            )
            raise

    async def close_async(self) -> None:
        """Close the async database connection and cleanup resources."""
        if hasattr(self, "async_engine"):
            await self.async_engine.dispose()
            observability.observe(
                event_type=observability.SystemEvents.DATABASE_MANAGER_CLOSED,
                level=observability.EventLevel.INFO,
                data={"async": True},
                description="Async database manager closed and resources cleaned up",
            )

    def close(self) -> None:
        """Close the database connection and cleanup resources."""
        if hasattr(self, "engine"):
            self.engine.dispose()
        if hasattr(self, "async_engine"):
            # Note: This is synchronous disposal of async engine
            # In production, prefer using close_async() when possible
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule async disposal if event loop is running
                    asyncio.create_task(self.async_engine.dispose())
                else:
                    # Run disposal synchronously if no event loop
                    loop.run_until_complete(self.async_engine.dispose())
            except Exception:
                # Fallback to sync disposal
                pass
        observability.observe(
            event_type=observability.SystemEvents.DATABASE_MANAGER_CLOSED,
            level=observability.EventLevel.INFO,
            description="Database manager closed and resources cleaned up",
        )


# Global database manager instance (will be initialized by formation)
_db_manager: Optional[DatabaseManager] = None


def get_database_manager(connection_string: Optional[str] = None) -> DatabaseManager:
    """
    Get the global database manager instance.

    Args:
        connection_string: Optional connection string for initialization

    Returns:
        DatabaseManager instance
    """
    global _db_manager

    if _db_manager is None:
        _db_manager = DatabaseManager(connection_string)

    return _db_manager


def set_database_manager(db_manager: DatabaseManager) -> None:
    """
    Set the global database manager instance.

    Args:
        db_manager: DatabaseManager instance to set as global
    """
    global _db_manager
    _db_manager = db_manager
