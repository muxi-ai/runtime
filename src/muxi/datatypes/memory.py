# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Datatypes - Configuration Models for Memory Systems
# Description:  Pydantic models for memory configuration validation
# Role:         Provides type-safe configuration models for memory services
# Usage:        Imported by memory services and formation configurations
# Author:       Muxi Framework Team
#
# This module defines the configuration models for the memory system, including
# buffer memory configuration, remote buffer configuration, and related settings.
# =============================================================================

from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator


class RemoteBufferConfig(BaseModel):
    """Configuration for remote buffer memory servers (e.g., FAISSx)."""

    url: str = Field(description="URL of the remote buffer server (e.g., tcp://localhost:65432)")
    api_key: Optional[str] = Field(
        None, description="API key for authenticating with the remote server"
    )
    tenant: Optional[str] = Field(None, description="Tenant ID for multi-tenant remote servers")
    timeout_seconds: int = Field(30, description="Timeout for remote operations in seconds")
    retry_attempts: int = Field(3, description="Number of retry attempts for failed operations")

    @field_validator("url")
    def validate_url(cls, v):
        """Validate the remote URL format."""
        if not v.startswith(("tcp://", "http://", "https://", "ws://", "wss://")):
            raise ValueError(
                "Remote URL must start with tcp://, http://, https://, ws://, or wss://"
            )
        return v


class BufferMemoryConfig(BaseModel):
    """Configuration for buffer memory (working memory) system."""

    enabled: bool = Field(True, description="Whether buffer memory is enabled")
    size: int = Field(10, description="Number of messages to keep in the buffer")
    multiplier: int = Field(10, description="Multiplier for vector search results")
    vector_search: bool = Field(True, description="Whether to enable vector similarity search")
    vector_dimension: int = Field(1536, description="Dimension of embedding vectors")
    mode: Literal["local", "remote"] = Field(
        "local", description="Buffer mode: local (in-memory) or remote (FAISSx)"
    )
    remote: Optional[RemoteBufferConfig] = Field(
        None, description="Configuration for remote buffer server (required when mode='remote')"
    )

    @field_validator("size")
    def validate_size(cls, v):
        """Validate buffer size is positive."""
        if v <= 0:
            raise ValueError("Buffer size must be positive")
        return v

    @field_validator("multiplier")
    def validate_multiplier(cls, v):
        """Validate multiplier is positive."""
        if v <= 0:
            raise ValueError("Buffer multiplier must be positive")
        return v

    @field_validator("vector_dimension")
    def validate_dimension(cls, v):
        """Validate vector dimension is positive."""
        if v <= 0:
            raise ValueError("Vector dimension must be positive")
        return v

    @field_validator("remote")
    @classmethod
    def validate_remote_config(cls, v, info):
        """Validate remote config is provided when mode is remote."""
        if info.data.get("mode") == "remote" and not v:
            raise ValueError("Remote configuration is required when mode='remote'")
        return v


class WorkingMemoryConfig(BaseModel):
    """Configuration for working memory system."""

    max_memory_mb: str | int = Field(
        "auto", description="Maximum memory in MB or 'auto' for automatic sizing"
    )
    fifo_interval_min: int = Field(5, description="FIFO cleanup interval in minutes")
    vector_dimension: int = Field(1536, description="Dimension of embedding vectors")
    mode: Literal["local", "remote"] = Field(
        "local", description="Working memory mode: local or remote"
    )
    remote: Optional[Dict[str, Any]] = Field(None, description="Remote server configuration")

    @field_validator("max_memory_mb")
    @classmethod
    def validate_max_memory(cls, v, info):
        """Validate max memory configuration."""
        mode = info.data.get("mode", "local")
        if mode == "remote" and v == "auto":
            raise ValueError(
                "Working memory max_memory_mb cannot be 'auto' with remote mode. "
                "Remote servers require explicit memory limits."
            )
        if isinstance(v, int) and v <= 0:
            raise ValueError("max_memory_mb must be positive when specified as integer")
        return v


class PersistentMemoryConfig(BaseModel):
    """Configuration for persistent (long-term) memory system."""

    connection_string: str = Field(description="Database connection string (PostgreSQL or SQLite)")
    embedding_model: Optional[str] = Field(
        None, description="Model to use for generating embeddings"
    )
    collection_name: str = Field("default", description="Default collection name for memories")

    @field_validator("connection_string")
    def validate_connection_string(cls, v):
        """Validate connection string format."""
        # Allow secret placeholders
        if "${{" in v and "}}" in v:
            return v

        # Validate actual connection strings
        valid_prefixes = ["postgresql://", "postgres://", "sqlite://"]
        valid_suffix = v.endswith(".db")

        if not any(v.startswith(prefix) for prefix in valid_prefixes) and not valid_suffix:
            raise ValueError(
                "Connection string must start with postgresql://, postgres://, "
                "sqlite:// or end with .db"
            )
        return v


class MemorySystemConfig(BaseModel):
    """Complete memory system configuration."""

    working: WorkingMemoryConfig = Field(
        default_factory=WorkingMemoryConfig, description="Working memory configuration"
    )
    buffer: BufferMemoryConfig = Field(
        default_factory=BufferMemoryConfig, description="Buffer memory configuration"
    )
    persistent: Optional[PersistentMemoryConfig] = Field(
        None, description="Persistent memory configuration (optional)"
    )
