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

from pydantic import BaseModel, Field
from typing import Optional


class MemoryConfig(BaseModel):
    """
    Configuration settings for memory systems.

    This class defines the configuration structure for memory systems,
    including buffer memory, long-term memory, vector operations, and
    similarity search parameters. Settings can be customized per formation
    or environment.

    Attributes:
        use_long_term_memory: Whether to enable long-term memory
        vector_dimension: Dimension of embedding vectors
        buffer_max_size: Maximum size of buffer memory
        connection_string: Database connection string for memory storage
        default_collection: Default collection name for memory storage
        similarity_threshold: Threshold for similarity matching
        max_search_results: Maximum results to return from searches
    """

    # Core memory settings
    use_long_term_memory: bool = Field(
        default=True,
        description="Whether to enable long-term memory storage",
    )
    vector_dimension: int = Field(
        default=1536,
        description="Dimension of embedding vectors",
    )
    buffer_max_size: int = Field(
        default=1000,
        description="Maximum number of messages in buffer memory",
    )

    # Database settings
    connection_string: Optional[str] = Field(
        default="sqlite:///data/memory.db",
        description="Database connection string for memory storage",
    )
    default_collection: str = Field(
        default="default",
        description="Default collection name for memory storage",
    )

    # Search and similarity settings
    similarity_threshold: float = Field(
        default=0.7,
        description="Minimum similarity score for memory matches",
    )
    max_search_results: int = Field(
        default=10,
        description="Maximum number of results to return from memory searches",
    )
