"""
Base configuration framework for MUXI services.

This module provides standardized configuration patterns for all MUXI services,
ensuring consistent validation, documentation, and initialization across the framework.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List, Literal
from abc import ABC, abstractmethod


class BaseServiceSchema(BaseModel, ABC):
    """
    Base configuration for all MUXI services.

    This abstract base class provides common configuration fields and validation
    patterns that all service configurations should inherit from. It ensures
    consistent configuration handling across the entire framework.
    """

    service_name: str = Field(..., description="Unique service identifier")
    enabled: bool = Field(default=True, description="Whether service is enabled")
    timeout: Optional[float] = Field(
        default=30.0, ge=0, description="Default timeout in seconds for service operations"
    )
    observability_enabled: bool = Field(
        default=True, description="Enable observability events for this service"
    )
    retry_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Retry configuration for service operations"
    )

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v):
        """Ensure timeout is reasonable."""
        if v is not None and v > 300:  # 5 minutes
            raise ValueError("Timeout cannot exceed 300 seconds")
        return v

    @abstractmethod
    def validate_service_specific(self) -> None:
        """
        Service-specific validation logic.

        Each service must implement this method to validate its specific
        configuration requirements.
        """
        pass

    def validate(self) -> None:
        """
        Perform full configuration validation.

        This method calls both the base validation and service-specific validation.
        """
        # Pydantic handles base validation automatically
        # Call service-specific validation
        self.validate_service_specific()

    model_config = {
        "extra": "forbid",  # Prevent typos in config
        "validate_assignment": True,  # Validate on field updates
        "use_enum_values": True,
        "json_encoders": {
            # Add custom encoders if needed
        },
    }


class LLMServiceSchema(BaseServiceSchema):
    """Configuration for LLM service."""

    service_name: Literal["llm"] = Field(default="llm")
    default_model: str = Field(..., description="Default LLM model to use")
    max_tokens: int = Field(
        default=4096, ge=1, le=32768, description="Maximum tokens for generation"
    )
    temperature: float = Field(
        default=0.7, ge=0.0, le=2.0, description="Temperature for generation randomness"
    )
    cache_enabled: bool = Field(default=True, description="Enable response caching")
    cache_ttl: int = Field(default=3600, ge=0, description="Cache TTL in seconds")
    api_key: Optional[str] = Field(default=None, description="API key for LLM provider")

    @field_validator("default_model")
    @classmethod
    def validate_model(cls, v):
        """Ensure model format is valid."""
        if not v or "/" not in v:
            raise ValueError("Model must be in format 'provider/model'")
        return v

    def validate_service_specific(self) -> None:
        """Validate LLM-specific configuration."""
        if self.cache_enabled and self.cache_ttl == 0:
            raise ValueError("Cache TTL must be > 0 when cache is enabled")


class MemoryServiceSchema(BaseServiceSchema):
    """Configuration for memory services."""

    service_name: Literal["memory"] = Field(default="memory")

    # Buffer memory config
    buffer_enabled: bool = Field(default=True, description="Enable buffer memory")
    buffer_size: int = Field(default=50, ge=1, le=1000, description="Maximum messages in buffer")

    # Long-term memory config
    long_term_enabled: bool = Field(default=False, description="Enable long-term memory")
    vector_store_type: str = Field(
        default="faiss", description="Type of vector store (faiss, chroma, etc.)"
    )
    embedding_model: Optional[str] = Field(
        default=None, description="Model for generating embeddings"
    )
    index_path: Optional[str] = Field(default=None, description="Path to vector index storage")

    def validate_service_specific(self) -> None:
        """Validate memory-specific configuration."""
        if self.long_term_enabled and not self.embedding_model:
            raise ValueError("Embedding model required when long-term memory is enabled")

        if self.long_term_enabled and not self.index_path:
            raise ValueError("Index path required when long-term memory is enabled")


class MCPServiceSchema(BaseServiceSchema):
    """Configuration for MCP service."""

    service_name: Literal["mcp"] = Field(default="mcp")
    max_concurrent_servers: int = Field(
        default=10, ge=1, le=100, description="Maximum concurrent MCP servers"
    )
    default_timeout: float = Field(
        default=30.0, ge=1.0, le=300.0, description="Default timeout for MCP operations"
    )
    retry_attempts: int = Field(
        default=3, ge=0, le=10, description="Number of retry attempts for failed operations"
    )
    retry_delay: float = Field(
        default=1.0, ge=0.1, le=60.0, description="Delay between retry attempts in seconds"
    )

    def validate_service_specific(self) -> None:
        """Validate MCP-specific configuration."""
        if self.retry_attempts > 0 and self.retry_delay == 0:
            raise ValueError("Retry delay must be > 0 when retries are enabled")


class A2AServiceSchema(BaseServiceSchema):
    """Configuration for A2A (Agent-to-Agent) service."""

    service_name: Literal["a2a"] = Field(default="a2a")

    # Server configuration
    server_enabled: bool = Field(
        default=False, description="Enable A2A server for incoming requests"
    )
    server_host: str = Field(default="0.0.0.0", description="Host address for A2A server")
    server_port: int = Field(default=8080, ge=1024, le=65535, description="Port for A2A server")

    # Registry configuration
    external_registry_enabled: bool = Field(
        default=False, description="Enable external registry for agent discovery"
    )
    registry_url: Optional[str] = Field(default=None, description="URL of external A2A registry")
    registration_timeout: float = Field(
        default=30.0, ge=1.0, le=300.0, description="Timeout for registry operations"
    )

    # Security configuration
    require_auth: bool = Field(default=False, description="Require authentication for A2A requests")
    allowed_origins: Optional[List[str]] = Field(
        default=None, description="Allowed origins for CORS"
    )

    def validate_service_specific(self) -> None:
        """Validate A2A-specific configuration."""
        if self.external_registry_enabled and not self.registry_url:
            raise ValueError("Registry URL required when external registry is enabled")

        if self.server_enabled and self.server_port < 1024:
            raise ValueError("Server port must be >= 1024 for non-root operation")


class SchedulerServiceSchema(BaseServiceSchema):
    """Configuration for scheduler service."""

    service_name: Literal["scheduler"] = Field(default="scheduler")

    # Job limits
    max_jobs_per_user: int = Field(default=100, ge=1, le=10000, description="Maximum jobs per user")
    max_concurrent_jobs: int = Field(
        default=10, ge=1, le=100, description="Maximum concurrent job executions"
    )

    # Execution limits
    max_execution_time: int = Field(
        default=300, ge=1, le=3600, description="Maximum execution time per job in seconds"
    )

    # Cleanup configuration
    cleanup_interval: int = Field(
        default=3600, ge=60, description="Interval for cleaning up completed jobs in seconds"
    )
    retention_days: int = Field(
        default=7, ge=1, le=365, description="Days to retain completed job records"
    )

    # Security
    enable_input_validation: bool = Field(
        default=True, description="Enable input validation and sanitization"
    )
    max_prompt_length: int = Field(
        default=10000, ge=100, le=100000, description="Maximum length for job prompts"
    )

    def validate_service_specific(self) -> None:
        """Validate scheduler-specific configuration."""
        if self.max_concurrent_jobs > self.max_jobs_per_user:
            raise ValueError("Concurrent jobs cannot exceed max jobs per user")


class FormationSchema(BaseServiceSchema):
    """Configuration for formation orchestration."""

    service_name: Literal["formation"] = Field(default="formation")
    formation_id: str = Field(..., description="Unique formation identifier")

    # Agent configuration
    max_agents: int = Field(
        default=10, ge=1, le=100, description="Maximum number of agents in formation"
    )
    default_agent_timeout: float = Field(
        default=60.0, ge=1.0, le=600.0, description="Default timeout for agent operations"
    )

    # Overlord configuration
    enable_intelligent_routing: bool = Field(
        default=True, description="Enable intelligent agent routing"
    )
    routing_cache_ttl: int = Field(
        default=3600, ge=0, description="TTL for routing cache in seconds"
    )

    # Workflow configuration
    enable_workflows: bool = Field(default=True, description="Enable multi-agent workflows")
    max_workflow_steps: int = Field(
        default=20, ge=1, le=100, description="Maximum steps in a workflow"
    )

    def validate_service_specific(self) -> None:
        """Validate formation-specific configuration."""
        if not self.formation_id:
            raise ValueError("Formation ID is required")

        if self.enable_intelligent_routing and self.routing_cache_ttl < 0:
            raise ValueError("Routing cache TTL must be >= 0")


# Re-export commonly used configs
__all__ = [
    "BaseServiceSchema",
    "LLMServiceSchema",
    "MemoryServiceSchema",
    "MCPServiceSchema",
    "A2AServiceSchema",
    "SchedulerServiceSchema",
    "FormationSchema",
]
