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
from .sops import SOPSystem

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
