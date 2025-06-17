"""
Centralized cache directory management for Muxi Runtime.

This module provides consistent cache directory paths across all components,
following platform-specific conventions:
- Windows: %APPDATA%/muxi/cache
- Mac/Linux: ~/.muxi/cache

All cache files should use paths from this module to ensure consistency
and proper cleanup.
"""

from pathlib import Path
from .user_dirs import user_cache_dir


class MuxiCachePaths:
    """Centralized cache directory paths for Muxi components."""

    def __init__(self):
        """Initialize cache paths.

        Args:
            appname: Application name for cache directory (ignored, uses 'muxi')
            appauthor: Application author (ignored)
        """
        self.base_cache_dir = Path(user_cache_dir())

    @property
    def knowledge_embeddings(self) -> Path:
        """Cache directory for knowledge embeddings."""
        return self.base_cache_dir / "knowledge"

    @property
    def a2a_cards(self) -> Path:
        """Cache directory for A2A service discovery cards."""
        return self.base_cache_dir / "a2a_cards"

    @property
    def a2a_registry(self) -> Path:
        """Cache directory for A2A service discovery registry."""
        return self.base_cache_dir / "a2a_registry"

    @property
    def formation_persistent(self) -> Path:
        """Formation persistent cache database path."""
        return self.base_cache_dir / "formation" / "persistent.db"

    @property
    def memory_databases(self) -> Path:
        """Base directory for memory databases."""
        return self.base_cache_dir / "memory"

    @property
    def temp_files(self) -> Path:
        """Temporary files directory."""
        return self.base_cache_dir / "temp"

    def ensure_directories(self) -> None:
        """Create all cache directories if they don't exist."""
        directories = [
            self.knowledge_embeddings,
            self.a2a_cards,
            self.formation_persistent.parent,
            self.memory_databases,
            self.temp_files,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def get_knowledge_cache_path(self, agent_id: str, file_type: str = "embeddings") -> Path:
        """Get specific path for knowledge cache files.

        Args:
            agent_id: Agent identifier
            file_type: Type of cache file (embeddings, metadata)

        Returns:
            Full path to cache file
        """
        self.knowledge_embeddings.mkdir(parents=True, exist_ok=True)
        return self.knowledge_embeddings / f"{agent_id}_{file_type}.pickle"

    def get_memory_db_path(self, db_name: str) -> Path:
        """Get path for memory database files.

        Args:
            db_name: Database name

        Returns:
            Full path to database file
        """
        self.memory_databases.mkdir(parents=True, exist_ok=True)
        return self.memory_databases / f"{db_name}.db"


# Global instance for easy access
cache_paths = MuxiCachePaths()


def get_cache_paths() -> MuxiCachePaths:
    """Get the global cache paths instance."""
    return cache_paths


def ensure_cache_directories() -> None:
    """Ensure all cache directories exist."""
    cache_paths.ensure_directories()


# Convenience functions for common cache paths
def get_knowledge_cache_dir() -> Path:
    """Get knowledge embeddings cache directory."""
    return cache_paths.knowledge_embeddings


def get_a2a_cache_dir() -> Path:
    """Get A2A cards cache directory."""
    return cache_paths.a2a_cards


def get_formation_cache_db() -> Path:
    """Get formation persistent cache database path."""
    return cache_paths.formation_persistent


def get_memory_cache_dir() -> Path:
    """Get memory databases cache directory."""
    return cache_paths.memory_databases
