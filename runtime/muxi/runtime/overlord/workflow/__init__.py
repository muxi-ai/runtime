"""
Workflow management subsystem for Enhanced Overlord.

This module provides intelligent task decomposition and multi-agent workflow
orchestration capabilities.
"""

# Import all workflow types first
from .types import (
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

__all__ = [
    # Data types
    "Workflow",
    "SubTask",
    "TaskStatus",
    "WorkflowStatus",
    "ApprovalStatus",
    "RequestAnalysis",
    "TaskResult",
    "TaskInput",
    "TaskOutput",

    # Utility functions
    "generate_workflow_id",
    "generate_task_id",
    "validate_workflow_dag",
    "build_execution_phases",

    # Core classes
    "RequestAnalyzer",
    "TaskDecomposer",
    "ApprovalManager",
    "WorkflowExecutor",
    "ProgressTracker"
]
