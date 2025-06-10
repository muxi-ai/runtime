"""
Document Workflow Integration Layer for Enhanced Overlord Intelligence System

This module implements Subtask 3.9 of the Enhanced Overlord Intelligence System,
providing comprehensive document workflow integration with task generation,
cross-reference management, and context preservation capabilities.

Core Components:
- DocumentWorkflowIntegrator: Document-based task generation and workflow enrichment
- DocumentCrossReferenceManager: Traceable cross-document reference management
- DocumentContextPreserver: Context preservation across conversations

Integration:
- Seamless integration with existing overlord workflow system
- Document-aware task generation and enrichment
- Cross-document insight generation and reference tracking
- Context preservation for long-term document conversations

Usage:
    from muxi.runtime.overlord.document_workflow import (
        DocumentWorkflowIntegrator,
        DocumentCrossReferenceManager,
        DocumentContextPreserver
    )
"""

from .workflow_integrator import DocumentWorkflowIntegrator
from .cross_reference_manager import DocumentCrossReferenceManager
from .context_preserver import DocumentContextPreserver

__all__ = [
    "DocumentWorkflowIntegrator",
    "DocumentCrossReferenceManager",
    "DocumentContextPreserver"
]

__version__ = "1.0.0"
__author__ = "MUXI Framework Team"
__description__ = "Document Workflow Integration Layer"
