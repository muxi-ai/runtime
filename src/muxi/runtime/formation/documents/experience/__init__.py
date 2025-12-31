"""
Document User Experience Layer for Enhanced Overlord Intelligence System

This module implements Subtask 3.8 of the Enhanced Overlord Intelligence System,
providing a comprehensive document processing user experience with persona-consistent
acknowledgments, advanced summarization, and intelligent error handling.

Core Components:
- DocumentAcknowledgmentGenerator: Persona-consistent document acknowledgments
- DocumentSummarizer: Advanced multi-format document summarization
- DocumentErrorHandler: Intelligent error handling with recovery suggestions

Integration:
- Seamless integration with existing overlord persona system
- Real-time processing feedback and status updates
- Cross-document insight generation capabilities
- User experience optimization for document workflows

Usage:
    from muxi.runtime.formation.document_experience import (
        DocumentAcknowledgmentGenerator,
        DocumentSummarizer,
        DocumentErrorHandler
    )
"""

from .acknowledgment_generator import DocumentAcknowledgmentGenerator
from .summarizer import DocumentSummarizer
from .error_handler import DocumentErrorHandler

__all__ = [
    "DocumentAcknowledgmentGenerator",
    "DocumentSummarizer",
    "DocumentErrorHandler"
]
