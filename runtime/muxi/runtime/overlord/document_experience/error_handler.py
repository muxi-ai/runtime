"""
Document Error Handler Implementation

This module implements specialized error handling for document processing
with recovery suggestions and user-friendly error reporting.

Features:
- Document-specific error classification
- Recovery suggestion generation
- Error pattern analysis
- User-friendly error reporting
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class DocumentError:
    """Represents a document processing error"""
    error_id: str
    error_type: str
    error_message: str
    document_id: str
    stage: str
    severity: str  # "low", "medium", "high", "critical"
    recovery_suggestions: List[str]
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class ErrorPattern:
    """Represents a recurring error pattern"""
    pattern_id: str
    error_type: str
    occurrence_count: int
    common_causes: List[str]
    success_rate: float
    last_seen: float


class DocumentErrorHandler:
    """
    Specialized error handling for document processing operations.

    Provides comprehensive error analysis, recovery suggestions,
    and user-friendly error reporting with pattern recognition.
    """

    def __init__(self, persona_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the document error handler.

        Args:
            persona_config: Overlord persona configuration for error messaging
        """
        self.persona_config = persona_config or {}

        # Error tracking
        self._error_history: List[DocumentError] = []
        self._error_patterns: Dict[str, ErrorPattern] = {}

        # Error classification mapping
        self._error_classifications = self._initialize_error_classifications()

        # Recovery suggestion templates
        self._recovery_templates = self._initialize_recovery_templates()

        logger.info("Initialized DocumentErrorHandler")

    def _initialize_error_classifications(self) -> Dict[str, Dict[str, Any]]:
        """Initialize error type classifications"""
        return {
            "file_format": {
                "severity": "medium",
                "stage": "parsing",
                "keywords": ["format", "encoding", "corrupt", "invalid"],
                "recovery_difficulty": "easy"
            },
            "size_limit": {
                "severity": "low",
                "stage": "upload",
                "keywords": ["size", "large", "limit", "exceeded"],
                "recovery_difficulty": "easy"
            },
            "content_extraction": {
                "severity": "medium",
                "stage": "processing",
                "keywords": ["extract", "parse", "read", "decode"],
                "recovery_difficulty": "medium"
            },
            "memory_limit": {
                "severity": "high",
                "stage": "processing",
                "keywords": ["memory", "ram", "allocation", "out of"],
                "recovery_difficulty": "hard"
            },
            "network_timeout": {
                "severity": "medium",
                "stage": "upload",
                "keywords": ["timeout", "network", "connection", "failed"],
                "recovery_difficulty": "easy"
            },
            "permission_denied": {
                "severity": "high",
                "stage": "access",
                "keywords": ["permission", "denied", "access", "forbidden"],
                "recovery_difficulty": "hard"
            },
            "vectorization_failure": {
                "severity": "high",
                "stage": "indexing",
                "keywords": ["vector", "embedding", "model", "api"],
                "recovery_difficulty": "medium"
            }
        }

    def _initialize_recovery_templates(self) -> Dict[str, List[str]]:
        """Initialize recovery suggestion templates"""
        return {
            "file_format": [
                "Try converting the file to a supported format (PDF, DOCX, TXT)",
                "Check if the file is corrupted and try re-uploading",
                "Ensure the file encoding is UTF-8 or a standard format"
            ],
            "size_limit": [
                "Try splitting the document into smaller sections",
                "Compress the file size by reducing image quality",
                "Contact support to increase your file size limit"
            ],
            "content_extraction": [
                "Verify the document contains readable text",
                "Try saving the file in a different format",
                "Check if the document is password-protected"
            ],
            "memory_limit": [
                "Try processing the document in smaller chunks",
                "Wait a moment and try again when system load is lower",
                "Consider upgrading to a plan with more processing capacity"
            ],
            "network_timeout": [
                "Check your internet connection and try again",
                "Try uploading the file again",
                "If the problem persists, try a smaller file first"
            ],
            "permission_denied": [
                "Check that you have permission to access this file",
                "Verify your account has the necessary privileges",
                "Contact your administrator for access rights"
            ],
            "vectorization_failure": [
                "The document content may be too complex for automatic processing",
                "Try simplifying the document structure",
                "Contact support if this error persists"
            ]
        }

    async def handle_error(
        self,
        error: Exception,
        document_id: str,
        stage: str,
        context: Optional[Dict[str, Any]] = None
    ) -> DocumentError:
        """
        Handle a document processing error and generate recovery suggestions.

        Args:
            error: The exception that occurred
            document_id: ID of the document being processed
            stage: Processing stage where error occurred
            context: Optional context information

        Returns:
            DocumentError object with analysis and suggestions
        """
        error_type = self._classify_error(error, stage)
        severity = self._determine_severity(error_type, context)

        # Generate recovery suggestions
        recovery_suggestions = self._generate_recovery_suggestions(
            error_type, error, context
        )

        # Create error object
        doc_error = DocumentError(
            error_id=f"{document_id}_{stage}_{int(time.time())}",
            error_type=error_type,
            error_message=str(error),
            document_id=document_id,
            stage=stage,
            severity=severity,
            recovery_suggestions=recovery_suggestions,
            timestamp=time.time(),
            metadata=context or {}
        )

        # Track error for pattern analysis
        self._track_error(doc_error)

        logger.error(
            f"Document error handled: {error_type} in {stage} "
            f"for document {document_id}"
        )

        return doc_error

    async def generate_user_friendly_message(
        self, doc_error: DocumentError
    ) -> str:
        """
        Generate a user-friendly error message.

        Args:
            doc_error: DocumentError object

        Returns:
            User-friendly error message string
        """
        # Get persona-appropriate messaging style
        message_style = self._get_message_style()

        # Base message based on error type
        base_message = self._get_base_error_message(doc_error.error_type, message_style)

        # Add context about the specific document
        context_message = self._add_document_context(doc_error)

        # Add recovery suggestions
        suggestions_message = self._format_recovery_suggestions(
            doc_error.recovery_suggestions, message_style
        )

        # Combine all parts
        full_message = f"{base_message} {context_message}"
        if suggestions_message:
            full_message += f" {suggestions_message}"

        return full_message

    def _classify_error(self, error: Exception, stage: str) -> str:
        """Classify the error type based on error and stage"""
        error_message = str(error).lower()

        # Check each classification for keyword matches
        for error_type, classification in self._error_classifications.items():
            if any(keyword in error_message for keyword in classification["keywords"]):
                return error_type

        # Default classification based on stage
        stage_defaults = {
            "upload": "network_timeout",
            "parsing": "file_format",
            "processing": "content_extraction",
            "indexing": "vectorization_failure"
        }

        return stage_defaults.get(stage, "content_extraction")

    def _determine_severity(
        self, error_type: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Determine error severity"""
        base_severity = self._error_classifications.get(error_type, {}).get(
            "severity", "medium"
        )

        # Adjust severity based on context
        if context:
            if context.get("retry_count", 0) > 2:
                # Increase severity for repeated failures
                if base_severity == "low":
                    return "medium"
                elif base_severity == "medium":
                    return "high"

            if context.get("file_size", 0) > 50 * 1024 * 1024:  # > 50MB
                # Large files are more likely to cause issues
                if base_severity == "low":
                    return "medium"

        return base_severity

    def _generate_recovery_suggestions(
        self,
        error_type: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Generate specific recovery suggestions"""
        # Get base suggestions for error type
        base_suggestions = self._recovery_templates.get(error_type, [])

        # Add context-specific suggestions
        suggestions = base_suggestions.copy()

        if context:
            # Add file-specific suggestions
            filename = context.get("filename", "")
            if filename:
                if filename.lower().endswith('.pdf'):
                    suggestions.append("For PDF files, ensure they're not password-protected")
                elif filename.lower().endswith(('.doc', '.docx')):
                    suggestions.append("For Word documents, try saving as PDF first")

            # Add retry suggestions for transient errors
            if error_type in ["network_timeout", "memory_limit"]:
                retry_count = context.get("retry_count", 0)
                if retry_count < 3:
                    suggestions.insert(0, "This appears to be a temporary issue - please try again")

        return suggestions[:5]  # Limit to 5 suggestions

    def _track_error(self, doc_error: DocumentError) -> None:
        """Track error for pattern analysis"""
        self._error_history.append(doc_error)

        # Update error patterns
        pattern_key = f"{doc_error.error_type}_{doc_error.stage}"

        if pattern_key in self._error_patterns:
            pattern = self._error_patterns[pattern_key]
            pattern.occurrence_count += 1
            pattern.last_seen = doc_error.timestamp
        else:
            self._error_patterns[pattern_key] = ErrorPattern(
                pattern_id=pattern_key,
                error_type=doc_error.error_type,
                occurrence_count=1,
                common_causes=[],
                success_rate=0.0,
                last_seen=doc_error.timestamp
            )

        # Keep error history manageable
        if len(self._error_history) > 1000:
            self._error_history = self._error_history[-500:]

    def _get_message_style(self) -> str:
        """Determine message style from persona configuration"""
        communication_style = self.persona_config.get("style", "professional")
        personality_traits = self.persona_config.get("traits", [])

        if "friendly" in personality_traits or communication_style == "casual":
            return "friendly"
        elif "technical" in personality_traits or communication_style == "technical":
            return "technical"
        else:
            return "professional"

    def _get_base_error_message(self, error_type: str, style: str) -> str:
        """Get base error message for the error type and style"""
        messages = {
            "professional": {
                "file_format": "The document format is not supported or may be corrupted.",
                "size_limit": "The document exceeds the maximum file size limit.",
                "content_extraction": "Unable to extract content from the document.",
                "memory_limit": "Insufficient system resources to process this document.",
                "network_timeout": "The upload request timed out.",
                "permission_denied": "Access to the document is restricted.",
                "vectorization_failure": "Unable to process document for search indexing."
            },
            "friendly": {
                "file_format": "Hmm, I'm having trouble reading this file format.",
                "size_limit": "This file is a bit too large for me to handle right now.",
                "content_extraction": "I'm having difficulty extracting the content from this document.",
                "memory_limit": "This document is quite complex and needs more processing power.",
                "network_timeout": "The upload seems to have timed out.",
                "permission_denied": "It looks like I don't have permission to access this file.",
                "vectorization_failure": "I'm having trouble processing this document for search."
            },
            "technical": {
                "file_format": "Document parsing failed due to format incompatibility.",
                "size_limit": "File size exceeds configured processing limits.",
                "content_extraction": "Content extraction pipeline encountered an error.",
                "memory_limit": "Memory allocation exceeded available system resources.",
                "network_timeout": "Network operation exceeded timeout threshold.",
                "permission_denied": "Access control validation failed.",
                "vectorization_failure": "Vector embedding generation process failed."
            }
        }

        return messages.get(style, {}).get(error_type, "An error occurred while processing the document.")

    def _add_document_context(self, doc_error: DocumentError) -> str:
        """Add document-specific context to error message"""
        filename = doc_error.metadata.get("filename", "your document")
        return f"Document '{filename}' could not be processed."

    def _format_recovery_suggestions(
        self, suggestions: List[str], style: str
    ) -> str:
        """Format recovery suggestions based on message style"""
        if not suggestions:
            return ""

        if style == "friendly":
            intro = "Here's what you can try:"
        elif style == "technical":
            intro = "Recommended recovery actions:"
        else:
            intro = "Suggestions:"

        if len(suggestions) == 1:
            return f"{intro} {suggestions[0]}"
        else:
            suggestion_list = "\n".join([f"• {suggestion}" for suggestion in suggestions[:3]])
            return f"{intro}\n{suggestion_list}"

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics and patterns"""
        if not self._error_history:
            return {"total_errors": 0}

        # Count errors by type
        error_counts = {}
        severity_counts = {}
        stage_counts = {}

        for error in self._error_history:
            error_counts[error.error_type] = error_counts.get(error.error_type, 0) + 1
            severity_counts[error.severity] = severity_counts.get(error.severity, 0) + 1
            stage_counts[error.stage] = stage_counts.get(error.stage, 0) + 1

        # Get recent error rate
        recent_errors = [
            error for error in self._error_history
            if time.time() - error.timestamp < 3600  # Last hour
        ]

        return {
            "total_errors": len(self._error_history),
            "error_types": error_counts,
            "severity_distribution": severity_counts,
            "stage_distribution": stage_counts,
            "recent_errors_count": len(recent_errors),
            "most_common_error": max(error_counts.items(), key=lambda x: x[1])[0] if error_counts else None,
            "error_patterns_count": len(self._error_patterns)
        }

    def clear_error_history(self, older_than_hours: Optional[float] = None) -> int:
        """Clear error history, optionally only entries older than specified hours"""
        if older_than_hours is None:
            count = len(self._error_history)
            self._error_history.clear()
            self._error_patterns.clear()
            return count

        current_time = time.time()
        cutoff_time = current_time - (older_than_hours * 3600)

        # Filter error history
        initial_count = len(self._error_history)
        self._error_history = [
            error for error in self._error_history
            if error.timestamp >= cutoff_time
        ]

        # Update patterns
        for pattern in self._error_patterns.values():
            if pattern.last_seen < cutoff_time:
                del self._error_patterns[pattern.pattern_id]

        return initial_count - len(self._error_history)
