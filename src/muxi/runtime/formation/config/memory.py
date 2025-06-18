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
