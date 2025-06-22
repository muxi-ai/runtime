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

from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

from . import observability
from ..utils.user_dirs import get_memory_dir

# Create a shared base for all MUXI models
Base = declarative_base()


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

        # Create engine with appropriate configuration
        self.engine = self._create_engine()

        # Create session factory
        self.Session = sessionmaker(bind=self.engine)

        observability.observe(
            event_type=observability.SystemEvents.DATABASE_MANAGER_INITIALIZED,
            level=observability.EventLevel.INFO,
            data={
                "database_type": self.database_type,
                "connection_configured": bool(self.connection_string)
            },
            description=f"Database manager initialized with {self.database_type}"
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
        postgres_url = os.getenv('POSTGRES_DATABASE_URL')
        if postgres_url:
            return postgres_url

        # Try SQLite environment variable
        sqlite_path = os.getenv('SQLITE_DATABASE_PATH')
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

        if scheme in ('postgresql', 'postgres'):
            return 'postgresql'
        elif scheme == 'sqlite' or connection_string.endswith('.db'):
            return 'sqlite'
        else:
            # Default to SQLite for unknown schemes
            observability.observe(
                event_type=observability.SystemEvents.DATABASE_TYPE_FALLBACK,
                level=observability.EventLevel.WARNING,
                data={
                    "connection_string": connection_string,
                    "detected_scheme": scheme,
                    "fallback_to": "sqlite"
                },
                description=f"Unknown database scheme '{scheme}', falling back to SQLite"
            )
            return 'sqlite'

    def _create_engine(self):
        """
        Create SQLAlchemy engine with appropriate configuration.

        Returns:
            Configured SQLAlchemy engine
        """
        if self.database_type == 'postgresql':
            # PostgreSQL configuration with connection pooling
            engine = create_engine(
                self.connection_string,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,
                echo=False  # Set to True for SQL debugging
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
                    description="Failed to create pgvector extension (may not be needed)"
                )

        else:  # SQLite
            # SQLite configuration
            engine = create_engine(
                self.connection_string,
                echo=False,  # Set to True for SQL debugging
                connect_args={"check_same_thread": False}  # Allow multi-threading
            )

        return engine

    def get_session(self) -> Session:
        """
        Get a new database session.

        Returns:
            SQLAlchemy session instance
        """
        return self.Session()

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
                description="Database tables created successfully"
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_TABLE_CREATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "database_type": self.database_type
                },
                description=f"Failed to create database tables: {e}"
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
            "engine_pool_size": getattr(self.engine.pool, 'size', None) if hasattr(self.engine, 'pool') else None,
            "engine_pool_checked_out": getattr(self.engine.pool, 'checkedout', None) if hasattr(self.engine, 'pool') else None,
        }

    def close(self) -> None:
        """Close the database connection and cleanup resources."""
        if hasattr(self, 'engine'):
            self.engine.dispose()
            observability.observe(
                event_type=observability.SystemEvents.DATABASE_MANAGER_CLOSED,
                level=observability.EventLevel.INFO,
                description="Database manager closed and resources cleaned up"
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
