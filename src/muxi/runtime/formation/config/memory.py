# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Configuration - Memory System Settings
# Description:  Configuration for buffer memory, long-term memory, and vector operations
# Role:         Provides centralized memory system configuration
# Usage:        Imported by components that need memory configuration
# Author:       Muxi Framework Team
#
# The Memory Configuration module provides centralized settings for memory
# systems including buffer memory, long-term memory, vector operations,
# and similarity search parameters.
#
# Key features include:
#
# 1. Buffer Memory Configuration
#    - Buffer size limits
#    - Vector dimensions for embeddings
#    - Maximum size constraints
#
# 2. Long-Term Memory Settings
#    - Enable/disable toggle
#    - Storage location configuration
#    - Search parameters
#
# 3. Vector Storage Settings
#    - FAISS index configuration
#    - Default collection management
#    - Similarity thresholds
#
# Example usage:
#
#   from .config import memory_config
#
#   # Access memory configuration
#   vector_dim = memory_config.vector_dimension
#   similarity = memory_config.similarity_threshold
# =============================================================================


from typing import Any, Dict, Optional


class MemoryConfig:
    """Memory configuration manager for the new schema structure."""

    def __init__(self, memory_config: Dict[str, Any]):
        """Initialize memory configuration."""
        self.memory_config = memory_config
        self._validate_and_migrate()

    def _validate_and_migrate(self) -> None:
        """Validate and migrate legacy memory configuration."""
        # Handle legacy memory.short_term configuration
        if "short_term" in self.memory_config:
            #  Warning - TODO: add observability
            #     "Legacy memory.short_term configuration detected. "
            #     "Please migrate to memory.working and memory.buffer structure."
            # )
            # Migrate short_term to working
            short_term_config = self.memory_config.pop("short_term")
            if "working" not in self.memory_config:
                self.memory_config["working"] = {}

            # Extract buffer config from short_term.buffer to top-level
            if isinstance(short_term_config, dict) and "buffer" in short_term_config:
                buffer_config = short_term_config.pop("buffer")
                if "buffer" not in self.memory_config:
                    self.memory_config["buffer"] = buffer_config

            # Move remaining short_term config to working
            if isinstance(short_term_config, dict):
                self.memory_config["working"].update(short_term_config)

        # Handle legacy memory.long_term configuration
        if "long_term" in self.memory_config:
            #  Warning - TODO: add observability
            #     "Legacy memory.long_term configuration detected. "
            #     "Please migrate to memory.persistent structure."
            # )
            # Migrate long_term to persistent
            long_term_config = self.memory_config.pop("long_term")
            if "persistent" not in self.memory_config:
                self.memory_config["persistent"] = long_term_config

    def get_working_config(self) -> Dict[str, Any]:
        """Get working memory configuration."""
        return self.memory_config.get("working", {
            "max_memory_mb": "auto",
            "fifo_interval_min": 5,
            "vector_dimension": 1536,
            "mode": "local",
            "remote": {}
        })

    def get_buffer_config(self) -> Dict[str, Any]:
        """Get buffer memory configuration."""
        return self.memory_config.get("buffer", {
            "size": 10,
            "multiplier": 10,
            "vector_search": True
        })

    def get_persistent_config(self) -> Optional[Dict[str, Any]]:
        """Get persistent memory configuration."""
        return self.memory_config.get("persistent")

    def is_persistent_enabled(self) -> bool:
        """Check if persistent memory is enabled."""
        persistent_config = self.get_persistent_config()
        return (
            persistent_config is not None
            and persistent_config.get("connection_string") is not None
        )
