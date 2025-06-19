"""
MUXI Runtime Type Definitions

Centralized type definitions for all MUXI runtime components.
This module provides a single source of truth for all type definitions
across services, formation, and other runtime components.
"""

# Core response and error types
from .response import (
    MuxiFileContent,
    MuxiContentItem,
    MuxiErrorDetails,
    MuxiUnifiedResponse,
    MuxiMessageContent,
    MuxiResponse,
)
from .errors import (
    ErrorCodeInfo,
    ERROR_CODE_REGISTRY,
    get_error_info,
    get_error_message,
    get_http_status,
    create_error_details,
)

from .exceptions import (
    FormationError,
    ConfigurationNotFoundError,
    ConfigurationValidationError,
    ConfigurationLoadError,
    ServiceConfigurationError,
    ServiceStartupError,
    ServiceDependencyError,
    OverlordImportError,
    OverlordStartupError,
    OverlordStateError,
    AgentConfigurationError,
    AgentValidationError,
    SecretsManagementError,
    ResourceCleanupError,
    DependencyValidationError,
    add_error_context,
)

# Workflow types
from .workflow import (
    Workflow,
    SubTask,
    TaskStatus,
    WorkflowStatus,
    ApprovalStatus,
    TaskResult,
    TaskInput,
    TaskOutput,
    RequestAnalysis,
    generate_workflow_id,
    generate_task_id,
    validate_workflow_dag,
    build_execution_phases,
    calculate_workflow_progress,
    get_ready_tasks
)

# Observability types
from .observability import (
    ConversationEvents,
    SystemEvents,
    ServerEvents,
    ErrorEvents,
    EventLevel,
    RequestContext,
    TokenUsage
)

# Resilience types
from .resilience import (
    ErrorType,
    ErrorSeverity,
    RecoveryStrategy,
    RecoveryResult,
    CircuitState,
    ResilienceConfig,
    ResilientWorkflowResult,
    WorkflowException,
    RecoveryException,
    CircuitBreakerException,
    ErrorContext,
    CircuitBreakerConfig,
    CircuitBreakerState,
    FallbackFunction
)

# Intelligence types
from .intelligence import (
    UserPreferences,
    ConversationContext,
    AdaptedResponse,
    FeedbackEvent,
    PreferenceType,
    AdaptationType,
    ConfidenceScore,
    Message,
    ExplicitPreference,
    ImplicitPreference,
    ContextualPreference,
    PreferenceExtractionResult,
    BehaviorAnalysisResult,
    ContextPredictionResult,
    AdaptationDetails
)

# Caching types
from .caching import (
    CacheType,
    CachedResponse,
    CacheKey,
    CacheStatistics,
    MemoryStats
)

# Clarification types
from .clarification import (
    ClarificationRequest,
    ClarificationResult,
    ClarificationResultStatus,
    ClarificationQuestion,
    ClarificationConfig,
    ClarificationStatus,
    RequestType,
    QuestionStyle,
    ClarificationMode,
    ProactiveRequestType,
    ProactiveRequest,
    MultiStepPlan,
    PlanStepAnalysis,
    PlanAnalysis,
    GoalContext,
    ClarificationSession,
    PlanningWorkflowType,
    WorkflowState,
    PlanningWorkflowRequest,
    ToolExecutionResult,
    WorkflowSynthesis,
    PlanningWorkflowSession,
    PlanningOption,
    ParameterMapping,
    InformationAnalysis,
    ToolInformationAnalysis,
    ReasoningInformationAnalysis,
    ContextAnalysis,
    ToolCall,
    ToolCallResult,
    InformationAnalysisError,
    ClarificationError,
    QuestionGenerationError,
    ParameterExtractionError,
    ContextEnrichmentError,
    ClarificationContext
)

# Parallel types
from .parallel import (
    ParallelGroup,
    ResourceAllocation,
    BottleneckInfo,
    OptimizedWorkflow,
    ExecutionPlan,
    ParallelExecutionResult,
    TaskNode,
    AgentCapability,
    BottleneckType
)

# Validation data types
from .validation import (
    ServiceDependency,
    ValidationResult,
)

# Async operation data types
from .async_operations import (
    OperationStatus,
    OperationContext,
    CancellationToken,
    TimeoutConfig,
    AsyncOperationResult,
    CancellationError,
    TimeoutError,
)

# Retry logic data types
from .retry import (
    RetryConfig,
    RetryResult,
    RetryAttempt,
    RetryStrategy,
    TransientError,
    NetworkTransientError,
    ServiceTransientError,
    RateLimitTransientError,
    TransientErrorType,
    calculate_delay,
    is_retryable_error,
)

__all__ = [
    # Core response and error types
    "MuxiFileContent",
    "MuxiContentItem",
    "MuxiErrorDetails",
    "MuxiUnifiedResponse",
    "MuxiMessageContent",
    "MuxiResponse",
    "ErrorCodeInfo",
    "ERROR_CODE_REGISTRY",
    "get_error_info",
    "get_error_message",
    "get_http_status",
    "create_error_details",

    # Workflow types
    "Workflow",
    "SubTask",
    "TaskStatus",
    "WorkflowStatus",
    "ApprovalStatus",
    "TaskResult",
    "TaskInput",
    "TaskOutput",
    "RequestAnalysis",
    "generate_workflow_id",
    "generate_task_id",
    "validate_workflow_dag",
    "build_execution_phases",
    "calculate_workflow_progress",
    "get_ready_tasks",

    # Observability types
    "ConversationEvents",
    "SystemEvents",
    "ServerEvents",
    "ErrorEvents",
    "EventLevel",
    "RequestContext",
    "TokenUsage",

    # Resilience types
    "ErrorType",
    "ErrorSeverity",
    "RecoveryStrategy",
    "RecoveryResult",
    "CircuitState",
    "ResilienceConfig",
    "ResilientWorkflowResult",
    "WorkflowException",
    "RecoveryException",
    "CircuitBreakerException",
    "ErrorContext",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "FallbackFunction",

    # Intelligence types
    "UserPreferences",
    "ConversationContext",
    "AdaptedResponse",
    "FeedbackEvent",
    "PreferenceType",
    "AdaptationType",
    "ConfidenceScore",
    "Message",
    "ExplicitPreference",
    "ImplicitPreference",
    "ContextualPreference",
    "PreferenceExtractionResult",
    "BehaviorAnalysisResult",
    "ContextPredictionResult",
    "AdaptationDetails",

    # Caching types
    "CacheType",
    "CachedResponse",
    "CacheKey",
    "CacheStatistics",
    "MemoryStats",

    # Clarification types
    "ClarificationRequest",
    "ClarificationResult",
    "ClarificationResultStatus",
    "ClarificationQuestion",
    "ClarificationConfig",
    "ClarificationStatus",
    "ContextEnrichmentError",
    "RequestType",
    "QuestionStyle",
    "ClarificationMode",
    "ProactiveRequestType",
    "ProactiveRequest",
    "MultiStepPlan",
    "PlanStepAnalysis",
    "PlanAnalysis",
    "GoalContext",
    "ClarificationSession",
    "PlanningWorkflowType",
    "WorkflowState",
    "PlanningWorkflowRequest",
    "ToolExecutionResult",
    "WorkflowSynthesis",
    "PlanningWorkflowSession",
    "PlanningOption",
    "ParameterMapping",
    "InformationAnalysis",
    "ToolInformationAnalysis",
    "ReasoningInformationAnalysis",
    "ContextAnalysis",
    "ToolCall",
    "ToolCallResult",
    "InformationAnalysisError",
    "ClarificationError",
    "QuestionGenerationError",
    "ParameterExtractionError",
    "ClarificationContext",

    # Parallel types
    "ParallelGroup",
    "ResourceAllocation",
    "BottleneckInfo",
    "OptimizedWorkflow",
    "ExecutionPlan",
    "ParallelExecutionResult",
    "TaskNode",
    "AgentCapability",
    "BottleneckType",

    # Exception classes
    "FormationError",
    "ConfigurationNotFoundError",
    "ConfigurationValidationError",
    "ConfigurationLoadError",
    "ServiceConfigurationError",
    "ServiceStartupError",
    "ServiceDependencyError",
    "OverlordImportError",
    "OverlordStartupError",
    "OverlordStateError",
    "AgentConfigurationError",
    "AgentValidationError",
    "SecretsManagementError",
    "ResourceCleanupError",
    "DependencyValidationError",
    "add_error_context",

    # Validation data types
    "ServiceDependency",
    "ValidationResult",

    # Async operation data types
    "OperationStatus",
    "OperationContext",
    "CancellationToken",
    "TimeoutConfig",
    "AsyncOperationResult",
    "CancellationError",
    "TimeoutError",

    # Retry logic data types
    "RetryConfig",
    "RetryResult",
    "RetryAttempt",
    "RetryStrategy",
    "TransientError",
    "NetworkTransientError",
    "ServiceTransientError",
    "RateLimitTransientError",
    "TransientErrorType",
    "calculate_delay",
    "is_retryable_error",
]
