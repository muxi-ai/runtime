"""
Data types and structures for the MUXI runtime.

This module provides the core data types and structures used throughout
the MUXI framework.

Submodules are not imported by default to avoid heavy dependencies.
Import specific submodules as needed:

    from muxi.runtime.datatypes.observability import EventLevel, SystemEvents
    from muxi.runtime.datatypes.exceptions import FormationError
    # etc.

Available submodules:
- async_operations: Async operation types and utilities
- caching: Cache-related types
- clarification: Clarification system types
- exceptions: Runtime exceptions
- intelligence: AI intelligence types
- mcp: Model Context Protocol types
- memory: Memory configuration types
- observability: Observability event types
- response: Response types
- retry: Retry configuration and errors
- schema: Service schema types
- task_status: Task status types
- validation: Validation types
- workflow: Workflow types
"""

# Do not import submodules by default to avoid heavy dependencies
# This prevents loading ML libraries (spacy, nltk, torch) unnecessarily

__all__ = [
    # List submodule names for documentation
    "async_operations",
    "caching",
    "clarification",
    "exceptions",
    "intelligence",
    "mcp",
    "memory",
    "observability",
    "response",
    "retry",
    "schema",
    "task_status",
    "validation",
    "workflow",
]
