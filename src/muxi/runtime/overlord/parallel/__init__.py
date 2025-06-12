"""
Parallel Workflow Optimization for MUXI Overlord.

This module provides intelligent parallelization of workflow execution to reduce
response times and optimize resource utilization across multiple agents.
"""

from .types import (
    ParallelGroup,
    ResourceAllocation,
    BottleneckInfo,
    OptimizedWorkflow,
    ExecutionPlan,
    ParallelExecutionResult
)

from .dependency_analyzer import DependencyAnalyzer
from .resource_manager import ResourceManager
from .bottleneck_detector import BottleneckDetector
from .optimizer import ParallelWorkflowOptimizer
from .executor import ParallelExecutor

__all__ = [
    # Data types
    "ParallelGroup",
    "ResourceAllocation",
    "BottleneckInfo",
    "OptimizedWorkflow",
    "ExecutionPlan",
    "ParallelExecutionResult",

    # Core components
    "DependencyAnalyzer",
    "ResourceManager",
    "BottleneckDetector",
    "ParallelWorkflowOptimizer",
    "ParallelExecutor"
]
