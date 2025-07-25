"""
Document Workflow Components

This module provides document-centric workflow components that are primarily
used for document processing workflows, not for agent knowledge systems.

Components:
- DocumentWorkflowIntegrator: Document-based task generation and workflow enrichment
- DocumentCrossReferenceManager: Traceable cross-document reference management
- DocumentContextPreserver: Context preservation across conversations

Note: These components are deprecated for agent knowledge use cases.
Agent knowledge systems should use the hybrid architecture with DocumentChunkManager
and WorkingMemory from the formation module instead.
"""

import warnings

# Import the actual classes
from .workflow_integrator import DocumentWorkflowIntegrator
from .cross_reference_manager import DocumentCrossReferenceManager
from .context_preserver import DocumentContextPreserver


def _deprecated_warning(component_name: str) -> None:
    """Issue deprecation warning for document workflow components."""
    warnings.warn(
        f"{component_name} is deprecated for agent knowledge use cases. "
        f"Use DocumentChunkManager and WorkingMemory from the formation module instead.",
        DeprecationWarning,
        stacklevel=3
    )


# Deprecated exports with warnings
__all__ = [
    "DocumentWorkflowIntegrator",
    "DocumentCrossReferenceManager",
    "DocumentContextPreserver"
]


# Issue warnings when these are imported for agent knowledge use
def __getattr__(name: str):
    """Issue deprecation warnings when workflow components are accessed."""
    if name in __all__:
        _deprecated_warning(name)

    if name == "DocumentWorkflowIntegrator":
        return DocumentWorkflowIntegrator
    elif name == "DocumentCrossReferenceManager":
        return DocumentCrossReferenceManager
    elif name == "DocumentContextPreserver":
        return DocumentContextPreserver
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
