"""
Type definitions for enhanced type safety in MUXI Runtime.

This module provides specific TypedDict and type definitions to replace
generic Dict[str, Any] usage throughout the codebase, improving type
safety, IDE support, and code documentation.
"""

from typing import Optional, Dict, List, Any, Literal, Union
from typing_extensions import TypedDict


# ===== Common Metadata Types =====


class OperationMetadata(TypedDict, total=False):
    """Metadata for async operations."""

    operation_id: str
    start_time: str  # ISO format timestamp
    end_time: Optional[str]
    duration_ms: Optional[float]
    user_id: Optional[str]
    session_id: Optional[str]
    trace_id: Optional[str]
    tags: List[str]


class TaskMetadata(TypedDict, total=False):
    """Metadata for task execution."""

    task_id: str
    task_type: str
    priority: int
    retry_count: int
    max_retries: int
    created_at: str  # ISO format
    updated_at: str  # ISO format
    assigned_agent: Optional[str]


# ===== Parameter Types =====


class ToolParameters(TypedDict, total=False):
    """Generic tool parameters with common fields."""

    # Common fields for most tools
    input: Optional[str]
    target: Optional[str]
    options: Optional[Dict[str, Any]]  # Tool-specific options
    timeout: Optional[float]
    async_mode: Optional[bool]


class MCPToolParameters(TypedDict, total=False):
    """Parameters for MCP tool calls."""

    # File operations
    path: Optional[str]
    content: Optional[str]
    encoding: Optional[str]

    # Search operations
    query: Optional[str]
    pattern: Optional[str]
    max_results: Optional[int]

    # API operations
    url: Optional[str]
    method: Optional[str]
    headers: Optional[Dict[str, str]]
    body: Optional[Union[str, dict]]

    # Database operations
    sql: Optional[str]
    table: Optional[str]
    filters: Optional[Dict[str, Any]]
    limit: Optional[int]
    offset: Optional[int]


# ===== Task Output Types =====


class TaskOutput(TypedDict, total=False):
    """Standard task output structure."""

    result: Any  # Actual result data
    status: Literal["success", "failure", "partial"]
    error: Optional[str]
    warnings: List[str]
    metrics: Dict[str, Union[int, float]]  # Performance metrics
    artifacts: List[str]  # Generated file paths or IDs


# Type alias for workflow outputs mapping task IDs to their outputs
WorkflowOutputs = Dict[str, TaskOutput]
"""Collection of workflow task outputs. Maps task IDs to TaskOutput objects."""


# ===== Context Types =====


class ConversationContext(TypedDict, total=False):
    """Context for conversation state."""

    user_id: str
    session_id: str
    conversation_id: str
    message_count: int
    start_time: str  # ISO format
    last_activity: str  # ISO format
    active_agents: List[str]
    topics: List[str]
    language: str
    timezone: str


class UserContext(TypedDict, total=False):
    """User-specific context information."""

    user_id: str
    preferences: Dict[str, Any]  # Will be refined to UserPreferences
    permissions: List[str]
    rate_limits: Dict[str, int]
    subscription_tier: str
    created_at: str
    last_seen: str


class ExecutionContext(TypedDict, total=False):
    """Execution environment context."""

    environment: Literal["development", "staging", "production"]
    region: str
    version: str
    feature_flags: Dict[str, bool]
    resource_limits: Dict[str, Union[int, float]]
    timeout_seconds: float


# ===== Cache Types =====


class CacheMetadata(TypedDict):
    """Metadata for cached items."""

    key: str
    created_at: str  # ISO format
    expires_at: Optional[str]  # ISO format
    hit_count: int
    size_bytes: int
    tags: List[str]


class CacheEntry(TypedDict):
    """Complete cache entry with data and metadata."""

    data: Any  # Actual cached data
    metadata: CacheMetadata
    compression: Optional[Literal["gzip", "lz4", "none"]]


# ===== Intelligence Types =====


class ModelContext(TypedDict, total=False):
    """Context provided to AI models."""

    system_prompt: str
    conversation_history: List[Dict[str, str]]  # Will be refined to Message type
    relevant_memories: List[Dict[str, Any]]  # Will be refined to Memory type
    active_tools: List[str]
    constraints: List[str]
    examples: List[Dict[str, str]]


class RoutingContext(TypedDict, total=False):
    """Context for agent routing decisions."""

    message_intent: str
    required_capabilities: List[str]
    preferred_agents: List[str]
    excluded_agents: List[str]
    urgency: Literal["low", "medium", "high", "critical"]
    domain: Optional[str]


# ===== Error Context Types =====


class ErrorContext(TypedDict, total=False):
    """Context information for errors."""

    error_id: str
    timestamp: str
    service: str
    operation: str
    user_id: Optional[str]
    session_id: Optional[str]
    trace_id: Optional[str]
    request_data: Optional[Dict[str, Any]]  # Sanitized request
    stack_trace: Optional[str]
    related_errors: List[str]  # Related error IDs


# ===== Performance Types =====


class PerformanceMetrics(TypedDict):
    """Performance measurement data."""

    operation: str
    start_time: float
    end_time: float
    duration_ms: float
    cpu_usage: Optional[float]
    memory_usage_mb: Optional[float]
    success: bool
    error_type: Optional[str]


class ResourceUsage(TypedDict):
    """Resource usage information."""

    cpu_percent: float
    memory_mb: float
    disk_io_mb: float
    network_io_mb: float
    active_connections: int
    thread_count: int


# ===== Information Analysis Types =====


class AvailableInformation(TypedDict, total=False):
    """Information available from various sources."""

    from_context: Dict[str, Any]
    from_memory: Dict[str, Any]
    from_tools: Dict[str, Any]
    from_user: Dict[str, Any]
    confidence_scores: Dict[str, float]


class CollectedInformation(TypedDict, total=False):
    """Information collected during clarification."""

    parameters: Dict[str, Any]
    confirmations: Dict[str, bool]
    selections: Dict[str, str]
    free_text: Dict[str, str]
    metadata: Dict[str, Any]


# ===== Planning Types =====


class PlanningContext(TypedDict, total=False):
    """Context for planning operations."""

    goal: str
    constraints: List[str]
    available_resources: List[str]
    time_limit_seconds: Optional[float]
    priority: Literal["low", "medium", "high"]
    dependencies: List[str]


# ===== Type Aliases for Gradual Migration =====

# These aliases help with gradual migration from Dict[str, Any]
Metadata = Union[OperationMetadata, TaskMetadata, CacheMetadata, Dict[str, Any]]
Parameters = Union[ToolParameters, MCPToolParameters, Dict[str, Any]]
Context = Union[
    ConversationContext,
    UserContext,
    ExecutionContext,
    ModelContext,
    RoutingContext,
    ErrorContext,
    PlanningContext,
    Dict[str, Any],
]
Outputs = Union[TaskOutput, WorkflowOutputs, Dict[str, Any]]


# ===== Helper Functions =====


def cast_to_type(data: Dict[str, Any], target_type: type) -> Any:
    """
    Cast a dictionary to a specific TypedDict type.

    This is mainly for documentation and IDE support,
    as TypedDict doesn't enforce runtime validation.

    Args:
        data: Dictionary to cast
        target_type: Target TypedDict type

    Returns:
        The same dictionary with type annotation
    """
    return data  # TypedDict is just for static typing


# ===== Export all types =====
__all__ = [
    # Metadata types
    "OperationMetadata",
    "TaskMetadata",
    "CacheMetadata",
    # Parameter types
    "ToolParameters",
    "MCPToolParameters",
    # Output types
    "TaskOutput",
    "WorkflowOutputs",
    # Context types
    "ConversationContext",
    "UserContext",
    "ExecutionContext",
    "ModelContext",
    "RoutingContext",
    "ErrorContext",
    "PlanningContext",
    # Cache types
    "CacheEntry",
    # Intelligence types
    "AvailableInformation",
    "CollectedInformation",
    # Performance types
    "PerformanceMetrics",
    "ResourceUsage",
    # Type aliases
    "Metadata",
    "Parameters",
    "Context",
    "Outputs",
    # Helper functions
    "cast_to_type",
]
