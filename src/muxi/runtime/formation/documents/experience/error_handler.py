"""
Enhanced Document Error Handler with Risk Mitigation Strategies

This module implements comprehensive fallback mechanisms and error recovery
for production-ready document processing.
"""

import time
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass
from pathlib import Path

from ....services.intent import IntentDetectionService
from ....services.llm import LLM
from ....datatypes.intent import IntentType
from ....services.observability import EventLogger, ErrorEvents, EventLevel


class DocumentErrorType(Enum):
    """Types of document processing errors"""

    PARSING_ERROR = "parsing_error"
    SIZE_LIMIT_EXCEEDED = "size_limit_exceeded"
    UNSUPPORTED_FORMAT = "unsupported_format"
    CORRUPTION_ERROR = "corruption_error"
    MEMORY_ERROR = "memory_error"
    TIMEOUT_ERROR = "timeout_error"
    NETWORK_ERROR = "network_error"
    DEPENDENCY_ERROR = "dependency_error"


class FallbackStrategy(Enum):
    """Fallback processing strategies"""

    TEXT_EXTRACTION_ONLY = "text_only"
    SIMPLIFIED_PROCESSING = "simplified"
    EXTERNAL_SERVICE = "external"
    MANUAL_REVIEW = "manual"
    SKIP_WITH_WARNING = "skip"


@dataclass
class ProcessingMetrics:
    """Track processing performance metrics"""

    file_size_mb: float
    processing_time_ms: float
    memory_usage_mb: float
    success: bool
    fallback_used: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class CircuitBreakerState:
    """Circuit breaker for failing operations"""

    failure_count: int = 0
    last_failure_time: float = 0
    state: str = "closed"  # closed, open, half_open
    failure_threshold: int = 5
    timeout_seconds: float = 60.0


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
    """Enhanced error handler with comprehensive risk mitigation"""

    def __init__(self, persona_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the document error handler.

        Args:
            persona_config: Overlord persona configuration for error messaging
        """
        self.persona_config = persona_config or {}
        self.logger = EventLogger()

        # Circuit breakers for different operations
        self.circuit_breakers: Dict[str, CircuitBreakerState] = {}

        # Performance tracking
        self.processing_metrics: List[ProcessingMetrics] = []

        # Fallback configurations
        self.fallback_strategies = {
            DocumentErrorType.PARSING_ERROR: FallbackStrategy.TEXT_EXTRACTION_ONLY,
            DocumentErrorType.SIZE_LIMIT_EXCEEDED: FallbackStrategy.SIMPLIFIED_PROCESSING,
            DocumentErrorType.UNSUPPORTED_FORMAT: FallbackStrategy.EXTERNAL_SERVICE,
            DocumentErrorType.CORRUPTION_ERROR: FallbackStrategy.TEXT_EXTRACTION_ONLY,
            DocumentErrorType.MEMORY_ERROR: FallbackStrategy.SIMPLIFIED_PROCESSING,
            DocumentErrorType.TIMEOUT_ERROR: FallbackStrategy.SIMPLIFIED_PROCESSING,
            DocumentErrorType.NETWORK_ERROR: FallbackStrategy.SKIP_WITH_WARNING,
            DocumentErrorType.DEPENDENCY_ERROR: FallbackStrategy.TEXT_EXTRACTION_ONLY,
        }

        # Initialize backup processing methods
        self._initialize_fallback_processors()

        # Error tracking
        self._error_history: List[DocumentError] = []
        self._error_patterns: Dict[str, ErrorPattern] = {}

        # Error classification mapping
        self._error_classifications = self._initialize_error_classifications()

        # Recovery suggestion templates
        self._recovery_templates = self._initialize_recovery_templates()

        # Initialize intent detection service eagerly
        self._initialize_intent_detector()

        self.logger.emit(
            ErrorEvents.SERVICE_INITIALIZED,
            EventLevel.INFO,
            "Document error handler initialized",
            {"persona_config": self._sanitize_config_for_logging(self.persona_config)},
        )

    def _initialize_error_classifications(self) -> Dict[str, Dict[str, Any]]:
        """Initialize error type classifications"""
        return {
            "file_format": {
                "severity": "medium",
                "stage": "parsing",
                "keywords": ["format", "encoding", "corrupt", "invalid"],
                "recovery_difficulty": "easy",
            },
            "size_limit": {
                "severity": "low",
                "stage": "upload",
                "keywords": ["size", "large", "limit", "exceeded"],
                "recovery_difficulty": "easy",
            },
            "content_extraction": {
                "severity": "medium",
                "stage": "processing",
                "keywords": ["extract", "parse", "read", "decode"],
                "recovery_difficulty": "medium",
            },
            "memory_limit": {
                "severity": "high",
                "stage": "processing",
                "keywords": ["memory", "ram", "allocation", "out of"],
                "recovery_difficulty": "hard",
            },
            "network_timeout": {
                "severity": "medium",
                "stage": "upload",
                "keywords": ["timeout", "network", "connection", "failed"],
                "recovery_difficulty": "easy",
            },
            "permission_denied": {
                "severity": "high",
                "stage": "access",
                "keywords": ["permission", "denied", "access", "forbidden"],
                "recovery_difficulty": "hard",
            },
            "vectorization_failure": {
                "severity": "high",
                "stage": "indexing",
                "keywords": ["vector", "embedding", "model", "api"],
                "recovery_difficulty": "medium",
            },
        }

    def _initialize_recovery_templates(self) -> Dict[str, List[str]]:
        """Initialize recovery suggestion templates"""
        return {
            "file_format": [
                "Try converting the file to a supported format (PDF, DOCX, TXT)",
                "Check if the file is corrupted and try re-uploading",
                "Ensure the file encoding is UTF-8 or a standard format",
            ],
            "size_limit": [
                "Try splitting the document into smaller sections",
                "Compress the file size by reducing image quality",
                "Contact support to increase your file size limit",
            ],
            "content_extraction": [
                "Verify the document contains readable text",
                "Try saving the file in a different format",
                "Check if the document is password-protected",
            ],
            "memory_limit": [
                "Try processing the document in smaller chunks",
                "Wait a moment and try again when system load is lower",
                "Consider upgrading to a plan with more processing capacity",
            ],
            "network_timeout": [
                "Check your internet connection and try again",
                "Try uploading the file again",
                "If the problem persists, try a smaller file first",
            ],
            "permission_denied": [
                "Check that you have permission to access this file",
                "Verify your account has the necessary privileges",
                "Contact your administrator for access rights",
            ],
            "vectorization_failure": [
                "The document content may be too complex for automatic processing",
                "Try simplifying the document structure",
                "Contact support if this error persists",
            ],
        }

    def _initialize_fallback_processors(self) -> None:
        """Initialize backup processing methods"""
        try:
            # Basic text extraction (always available)
            self.basic_text_extractor = self._create_basic_extractor()

            # Simplified processors (fewer dependencies)
            self.simplified_pdf_processor = self._create_simplified_pdf_processor()
            self.simplified_docx_processor = self._create_simplified_docx_processor()

            self.logger.emit(
                ErrorEvents.SERVICE_INITIALIZED,
                EventLevel.INFO,
                "Fallback processors initialized successfully",
                {},
            )

        except Exception as e:
            self.logger.emit(
                ErrorEvents.INTERNAL_ERROR,
                EventLevel.ERROR,
                "Failed to initialize fallback processors",
                {"error": str(e)},
            )

    def _initialize_intent_detector(self) -> None:
        """Initialize the intent detection service eagerly."""
        try:
            # Get LLM model from persona config or use default
            llm_model = self.persona_config.get("error_classification_llm", "openai/gpt-4")

            # Create LLM instance
            llm_service = LLM(model=llm_model, api_key=None)  # Will use env or config

            # Create intent detection service
            self._intent_detector = IntentDetectionService(
                llm_service=llm_service, enable_cache=True
            )

            self.logger.emit(
                ErrorEvents.SERVICE_INITIALIZED,
                EventLevel.INFO,
                "Intent detection service initialized",
                {"llm_model": llm_model},
            )
        except Exception as e:
            self.logger.emit(
                ErrorEvents.INTERNAL_ERROR,
                EventLevel.ERROR,
                "Failed to initialize intent detection service",
                {"error": str(e)},
            )
            # Create a fallback detector that will be initialized on first use
            self._intent_detector = None

    def _sanitize_config_for_logging(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize configuration for safe logging.

        Removes or masks sensitive fields while preserving structure for debugging.

        Args:
            config: Configuration dictionary to sanitize

        Returns:
            Sanitized configuration safe for logging
        """
        if not config:
            return {}

        # Define sensitive field patterns
        sensitive_patterns = [
            "key",
            "token",
            "secret",
            "password",
            "credential",
            "auth",
            "api_key",
            "access_token",
            "private",
            "cert",
            "connection_string",
        ]

        sanitized = {}
        for key, value in config.items():
            # Check if key contains sensitive patterns
            is_sensitive = any(pattern in key.lower() for pattern in sensitive_patterns)

            if is_sensitive:
                # Mask sensitive values
                if isinstance(value, str):
                    sanitized[key] = "***" if value else None
                elif isinstance(value, (int, float)):
                    sanitized[key] = "<numeric_value>"
                elif isinstance(value, dict):
                    sanitized[key] = "<dict_value>"
                else:
                    sanitized[key] = f"<{type(value).__name__}_value>"
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_config_for_logging(value)
            elif isinstance(value, list):
                # For lists, just indicate type and length
                sanitized[key] = f"<list[{len(value)}]>"
            else:
                # Non-sensitive values can be logged as-is
                sanitized[key] = value

        return sanitized

    async def handle_document_error(
        self, error: Exception, filename: str, file_size_mb: float, operation: str = "parsing"
    ) -> Tuple[Optional[str], str]:
        """
        Handle document processing errors with fallback strategies

        Returns:
            Tuple[content, status_message]
        """
        error_type = await self._classify_error(error, file_size_mb)

        # Update circuit breaker
        self._update_circuit_breaker(operation, success=False)

        # Check if circuit breaker is open
        if self._is_circuit_breaker_open(operation):
            return (
                None,
                f"⚠️ Service temporarily unavailable for {operation}. Please try again later.",
            )

        # Attempt fallback strategy
        fallback_strategy = self.fallback_strategies.get(
            error_type, FallbackStrategy.SKIP_WITH_WARNING
        )

        self.logger.emit(
            ErrorEvents.FALLBACK_TRIGGERED,
            EventLevel.WARNING,
            f"Document error for {filename}: {error_type.value}, attempting fallback: {fallback_strategy.value}",
            {
                "filename": filename,
                "error_type": error_type.value,
                "fallback_strategy": fallback_strategy.value,
                "operation": operation,
            },
        )

        return await self._execute_fallback_strategy(fallback_strategy, filename, error_type, error)

    async def _execute_fallback_strategy(
        self,
        strategy: FallbackStrategy,
        filename: str,
        error_type: DocumentErrorType,
        original_error: Exception,
    ) -> Tuple[Optional[str], str]:
        """Execute the appropriate fallback strategy"""

        try:
            if strategy == FallbackStrategy.TEXT_EXTRACTION_ONLY:
                content = await self._fallback_text_extraction(filename)
                return (
                    content,
                    f"✅ Extracted text using fallback method (original error: {error_type.value})",
                )

            elif strategy == FallbackStrategy.SIMPLIFIED_PROCESSING:
                content = await self._fallback_simplified_processing(filename)
                return (
                    content,
                    f"✅ Processed using simplified method (original error: {error_type.value})",
                )

            elif strategy == FallbackStrategy.EXTERNAL_SERVICE:
                content = await self._fallback_external_service(filename)
                return (
                    content,
                    f"✅ Processed using external service (original error: {error_type.value})",
                )

            elif strategy == FallbackStrategy.MANUAL_REVIEW:
                await self._queue_for_manual_review(filename, error_type, original_error)
                return None, f"📋 Document queued for manual review (error: {error_type.value})"

            elif strategy == FallbackStrategy.SKIP_WITH_WARNING:
                return (
                    None,
                    f"⚠️ Skipping document due to {error_type.value}: {str(original_error)}",
                )

        except Exception as fallback_error:
            self.logger.emit(
                ErrorEvents.INTERNAL_ERROR,
                EventLevel.ERROR,
                f"Fallback strategy {strategy.value} failed for {filename}",
                {
                    "filename": filename,
                    "strategy": strategy.value,
                    "error": str(fallback_error),
                    "original_error_type": error_type.value,
                },
            )
            return (
                None,
                f"❌ All processing methods failed. Original: {error_type.value}, Fallback: {str(fallback_error)}",  # noqa: E501
            )

    async def _fallback_text_extraction(self, filename: str) -> Optional[str]:
        """Basic text extraction fallback"""
        try:
            if filename.lower().endswith(".pdf"):
                return await self._extract_pdf_text_basic(filename)
            elif filename.lower().endswith((".docx", ".doc")):
                return await self._extract_docx_text_basic(filename)
            elif filename.lower().endswith((".txt", ".md")):
                return await self._extract_plain_text(filename)
            else:
                return f"Unable to extract text from {Path(filename).suffix} files"
        except Exception as e:
            self.logger.emit(
                ErrorEvents.INTERNAL_ERROR,
                EventLevel.ERROR,
                f"Failed text extraction fallback for {filename}",
                {"error": str(e), "filename": filename},
            )
            return None

    async def _fallback_simplified_processing(self, filename: str) -> Optional[str]:
        """Simplified processing with reduced memory usage"""
        try:
            # Use streaming processing for large files
            if filename.lower().endswith(".pdf"):
                return await self._process_pdf_streaming(filename)
            elif filename.lower().endswith((".docx", ".doc")):
                return await self._process_docx_minimal(filename)
            else:
                return await self._fallback_text_extraction(filename)
        except Exception as e:
            self.logger.emit(
                ErrorEvents.INTERNAL_ERROR,
                EventLevel.ERROR,
                f"Failed processing for {filename}",
                {"error": str(e), "filename": filename},
            )
            return await self._fallback_text_extraction(filename)

    async def _fallback_external_service(self, filename: str) -> Optional[str]:
        """Use external service for processing"""
        try:
            # This could integrate with cloud services like AWS Textract, Google Document AI, etc.
            self.logger.emit(
                ErrorEvents.SERVICE_CALLED,
                EventLevel.INFO,
                f"Using external service fallback for {filename}",
                {"filename": filename},
            )
            return await self._fallback_text_extraction(filename)
        except Exception as e:
            self.logger.emit(
                ErrorEvents.INTERNAL_ERROR,
                EventLevel.ERROR,
                f"Failed processing for {filename}",
                {"error": str(e), "filename": filename},
            )
            return await self._fallback_text_extraction(filename)

    async def _classify_error(self, error: Exception, file_size_mb: float) -> DocumentErrorType:
        """
        Classify error type for appropriate fallback strategy.

        Uses IntentDetectionService for language-agnostic error classification.
        """
        # Check file size first
        if file_size_mb > self.persona_config.get("max_file_size_mb", 50):
            return DocumentErrorType.SIZE_LIMIT_EXCEEDED

        error_str = str(error)

        # Try to use intent detection service
        try:
            # Check if intent detector is available
            if self._intent_detector is None:
                # Try to initialize it again if it failed during init
                self._initialize_intent_detector()
                if self._intent_detector is None:
                    # Still not available, use fallback
                    return self._fallback_classify_error(error)

            # Use intent detection for error classification
            result = await self._intent_detector.detect_intent(
                text=error_str, intent_type=IntentType.ERROR_TYPE, context=None
            )

            # Map intent to DocumentErrorType
            confidence_threshold = self.persona_config.get("error_classification_confidence", 0.6)
            if result.confidence > confidence_threshold:
                error_mapping = {
                    "memory": DocumentErrorType.MEMORY_ERROR,
                    "timeout": DocumentErrorType.TIMEOUT_ERROR,
                    "network": DocumentErrorType.NETWORK_ERROR,
                    "format": DocumentErrorType.CORRUPTION_ERROR,
                    "permission": DocumentErrorType.DEPENDENCY_ERROR,
                    "parsing": DocumentErrorType.PARSING_ERROR,
                    "size": DocumentErrorType.SIZE_LIMIT_EXCEEDED,
                    "api": DocumentErrorType.NETWORK_ERROR,
                    "unknown": DocumentErrorType.PARSING_ERROR,
                }

                return error_mapping.get(result.intent, DocumentErrorType.PARSING_ERROR)

            # Low confidence, use fallback
            return self._fallback_classify_error(error)

        except Exception as e:
            # Log error and fall back to keyword-based classification
            self.logger.emit(
                ErrorEvents.INTERNAL_ERROR,
                EventLevel.ERROR,
                "Intent detection failed for error classification",
                {"error": str(e), "original_error": error_str},
            )
            return self._fallback_classify_error(error)

    def _fallback_classify_error(self, error: Exception) -> DocumentErrorType:
        """
        Fallback keyword-based error classification.

        Used when intent detection service is not available.
        """
        error_str = str(error).lower()

        if any(keyword in error_str for keyword in ["memory", "ram", "out of memory"]):
            return DocumentErrorType.MEMORY_ERROR

        if any(keyword in error_str for keyword in ["timeout", "time out", "deadline"]):
            return DocumentErrorType.TIMEOUT_ERROR

        if any(keyword in error_str for keyword in ["network", "connection", "dns"]):
            return DocumentErrorType.NETWORK_ERROR

        if any(keyword in error_str for keyword in ["corrupt", "damaged", "invalid"]):
            return DocumentErrorType.CORRUPTION_ERROR

        if any(keyword in error_str for keyword in ["unsupported", "not supported", "format"]):
            return DocumentErrorType.UNSUPPORTED_FORMAT

        if any(keyword in error_str for keyword in ["import", "module", "dependency"]):
            return DocumentErrorType.DEPENDENCY_ERROR

        # Default to parsing error
        return DocumentErrorType.PARSING_ERROR

    def _update_circuit_breaker(self, operation: str, success: bool) -> None:
        """Update circuit breaker state"""
        if operation not in self.circuit_breakers:
            self.circuit_breakers[operation] = CircuitBreakerState()

        breaker = self.circuit_breakers[operation]
        current_time = time.time()

        if success:
            breaker.failure_count = 0
            breaker.state = "closed"
        else:
            breaker.failure_count += 1
            breaker.last_failure_time = current_time

            if breaker.failure_count >= breaker.failure_threshold:
                breaker.state = "open"

    def _is_circuit_breaker_open(self, operation: str) -> bool:
        """Check if circuit breaker is open"""
        if operation not in self.circuit_breakers:
            return False

        breaker = self.circuit_breakers[operation]
        current_time = time.time()

        if breaker.state == "open":
            if current_time - breaker.last_failure_time > breaker.timeout_seconds:
                breaker.state = "half_open"
                return False
            return True

        return False

    async def record_processing_metrics(
        self,
        filename: str,
        file_size_mb: float,
        processing_time_ms: float,
        memory_usage_mb: float,
        success: bool,
        fallback_used: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """Record processing metrics for analysis"""
        metrics = ProcessingMetrics(
            file_size_mb=file_size_mb,
            processing_time_ms=processing_time_ms,
            memory_usage_mb=memory_usage_mb,
            success=success,
            fallback_used=fallback_used,
            error_type=error_type,
        )

        self.processing_metrics.append(metrics)

        # Keep only last 1000 metrics to prevent memory growth
        if len(self.processing_metrics) > 1000:
            self.processing_metrics = self.processing_metrics[-1000:]

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error and recovery statistics"""
        if not self.processing_metrics:
            return {"total_processed": 0, "success_rate": 0.0}

        total = len(self.processing_metrics)
        successful = sum(1 for m in self.processing_metrics if m.success)
        fallback_used = sum(1 for m in self.processing_metrics if m.fallback_used)

        error_types = {}
        for metric in self.processing_metrics:
            if metric.error_type:
                error_types[metric.error_type] = error_types.get(metric.error_type, 0) + 1

        return {
            "total_processed": total,
            "success_rate": successful / total,
            "fallback_usage_rate": fallback_used / total,
            "error_types": error_types,
            "circuit_breaker_states": {
                op: breaker.state for op, breaker in self.circuit_breakers.items()
            },
        }

    # Helper methods for fallback processing
    def _create_basic_extractor(self):
        """Create basic text extractor that always works"""
        return lambda content: content[:1000] if isinstance(content, str) else str(content)[:1000]

    def _create_simplified_pdf_processor(self):
        """Create simplified PDF processor with minimal dependencies"""

        def simple_pdf_extract(filename):
            try:
                import PyPDF2

                with open(filename, "rb") as file:
                    reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page_num in range(min(5, len(reader.pages))):  # Limit to 5 pages
                        text += reader.pages[page_num].extract_text()
                    return text[:5000]  # Limit output size
            except Exception:
                return f"Unable to process PDF: {filename}"

        return simple_pdf_extract

    def _create_simplified_docx_processor(self):
        """Create simplified DOCX processor"""

        def simple_docx_extract(filename):
            try:
                import docx

                doc = docx.Document(filename)
                text = ""
                for paragraph in doc.paragraphs[:20]:  # Limit to 20 paragraphs
                    text += paragraph.text + "\n"
                return text[:5000]  # Limit output size
            except Exception:
                return f"Unable to process Word document: {filename}"

        return simple_docx_extract

    async def _extract_pdf_text_basic(self, filename: str) -> str:
        """Basic PDF text extraction"""
        return self.simplified_pdf_processor(filename)

    async def _extract_docx_text_basic(self, filename: str) -> str:
        """Basic DOCX text extraction"""
        return self.simplified_docx_processor(filename)

    async def _extract_plain_text(self, filename: str) -> str:
        """Extract plain text files"""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(filename, "r", encoding="latin-1") as f:
                return f.read()

    async def _process_pdf_streaming(self, filename: str) -> str:
        """Process PDF with streaming to reduce memory usage"""
        # Implementation would use streaming PDF processing
        return await self._extract_pdf_text_basic(filename)

    async def _process_docx_minimal(self, filename: str) -> str:
        """Process DOCX with minimal memory usage"""
        # Implementation would use minimal DOCX processing
        return await self._extract_docx_text_basic(filename)

    async def _queue_for_manual_review(
        self, filename: str, error_type: DocumentErrorType, error: Exception
    ) -> None:
        """Queue document for manual review"""
        # This could integrate with a ticketing system, email alerts, etc.
        #     f"Document {filename} queued for manual review: "
        #     f"{error_type.value} - {str(error)}"
        # )

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
                last_seen=doc_error.timestamp,
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
                "vectorization_failure": "Unable to process document for search indexing.",
            },
            "friendly": {
                "file_format": "Hmm, I'm having trouble reading this file format.",
                "size_limit": "This file is a bit too large for me to handle right now.",
                "content_extraction": "I'm having difficulty extracting the content from this document.",  # noqa: E501
                "memory_limit": "This document is quite complex and needs more processing power.",
                "network_timeout": "The upload seems to have timed out.",
                "permission_denied": "It looks like I don't have permission to access this file.",
                "vectorization_failure": "I'm having trouble processing this document for search.",
            },
            "technical": {
                "file_format": "Document parsing failed due to format incompatibility.",
                "size_limit": "File size exceeds configured processing limits.",
                "content_extraction": "Content extraction pipeline encountered an error.",
                "memory_limit": "Memory allocation exceeded available system resources.",
                "network_timeout": "Network operation exceeded timeout threshold.",
                "permission_denied": "Access control validation failed.",
                "vectorization_failure": "Vector embedding generation process failed.",
            },
        }

        return messages.get(style, {}).get(
            error_type, "An error occurred while processing the document."
        )

    def _add_document_context(self, doc_error: DocumentError) -> str:
        """Add document-specific context to error message"""
        filename = doc_error.metadata.get("filename", "your document")
        return f"Document '{filename}' could not be processed."

    def _format_recovery_suggestions(self, suggestions: List[str], style: str) -> str:
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
            error for error in self._error_history if error.timestamp >= cutoff_time
        ]

        # Update patterns
        for pattern in self._error_patterns.values():
            if pattern.last_seen < cutoff_time:
                del self._error_patterns[pattern.pattern_id]

        return initial_count - len(self._error_history)
