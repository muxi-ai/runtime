"""
Workflow management subsystem for Enhanced Overlord.

This module provides intelligent task decomposition and multi-agent workflow
orchestration capabilities.
"""

# Import all workflow types first
from ...datatypes.workflow import (
    # Core workflow data structures
    Workflow,
    SubTask,
    TaskStatus,
    WorkflowStatus,
    ApprovalStatus,
    RequestAnalysis,
    TaskResult,
    TaskInput,
    TaskOutput,

    # Utility functions
    generate_workflow_id,
    generate_task_id,
    validate_workflow_dag,
    build_execution_phases
)

# Import workflow components
from .analyzer import RequestAnalyzer
from .decomposer import TaskDecomposer, ApprovalManager
from .executor import WorkflowExecutor, ProgressTracker
from .workflow_manager import WorkflowManager
from .workflow_metrics import WorkflowMetrics
# SOPSystem is lazy-loaded via __getattr__ to avoid disk I/O on import

__all__ = [
    # Data types
    "ApprovalStatus",
    "RequestAnalysis",
    "SubTask",
    "TaskInput",
    "TaskOutput",
    "TaskResult",
    "TaskStatus",
    "Workflow",
    "WorkflowStatus",

    # Utility functions
    "build_execution_phases",
    "generate_task_id",
    "generate_workflow_id",
    "validate_workflow_dag",

    # Core classes
    "ApprovalManager",
    "ProgressTracker",
    "RequestAnalyzer",
    "TaskDecomposer",
    "WorkflowExecutor",
    "WorkflowManager",
    "WorkflowMetrics",
    "SOPSystem"
]


# Lazy loading implementation for SOPSystem
_lazy_imports = {
    'SOPSystem': None
}


def __getattr__(name):
    """
    Lazy import for SOPSystem to defer disk I/O until actually needed.

    SOPSystem performs directory scanning and file I/O during initialization,
    which can impact startup time. This lazy loading ensures it's only
    imported when actually accessed.
    """
    if name == 'SOPSystem':
        # Check if already imported
        if _lazy_imports['SOPSystem'] is None:
            from .sops import SOPSystem
            _lazy_imports['SOPSystem'] = SOPSystem
        return _lazy_imports['SOPSystem']

    # If not a lazy import, raise AttributeError
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
