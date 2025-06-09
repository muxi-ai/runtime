"""
Enhanced Overlord - Unified Orchestration System

This module provides the enhanced overlord with intelligent workflow orchestration
capabilities integrated directly into the main Overlord class.

Features:
- Automatic request complexity analysis
- Intelligent task decomposition
- Multi-agent workflow coordination
- Plan preview and approval capabilities
- Advanced response synthesis
- Graceful fallback to traditional agent routing
"""

from .overlord import Overlord
from .workflow import (
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

    # Workflow components
    RequestAnalyzer,
    TaskDecomposer,
    ApprovalManager,
    WorkflowExecutor,
    ProgressTracker,

    # Utility functions
    generate_workflow_id,
    generate_task_id,
    validate_workflow_dag,
    build_execution_phases
)


__all__ = [
    # Main overlord class with enhanced capabilities
    "Overlord",

    # Workflow data types
    "Workflow",
    "SubTask",
    "TaskStatus",
    "WorkflowStatus",
    "ApprovalStatus",
    "RequestAnalysis",
    "TaskResult",
    "TaskInput",
    "TaskOutput",

    # Workflow components
    "RequestAnalyzer",
    "TaskDecomposer",
    "ApprovalManager",
    "WorkflowExecutor",
    "ProgressTracker",



    # Utility functions
    "generate_workflow_id",
    "generate_task_id",
    "validate_workflow_dag",
    "build_execution_phases"
]
