"""
Document Acknowledgment Generator Implementation

This module implements persona-consistent document acknowledgment generation,
providing tailored responses based on overlord personality and document content.

Features:
- Persona-consistent acknowledgment generation
- Real-time processing confirmations
- Document type-specific responses
- Processing status updates
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class DocumentProcessingStatus:
    """Represents the processing status of a document"""

    document_id: str
    filename: str
    stage: str  # "received", "processing", "chunked", "indexed", "complete", "error"
    progress_percentage: float
    estimated_completion: Optional[float]
    messages: List[str]
    timestamp: float


@dataclass
class AcknowledgmentConfig:
    """Configuration for acknowledgment generation"""

    persona_name: Optional[str] = None
    enthusiasm_level: str = "balanced"  # "low", "balanced", "high"
    technical_detail: str = "moderate"  # "minimal", "moderate", "detailed"
    include_processing_status: bool = True
    include_next_steps: bool = True
    max_message_length: int = 500


class DocumentAcknowledgmentGenerator:
    """
    Generates persona-consistent acknowledgments for document processing.

    Provides tailored acknowledgment messages based on overlord personality,
    document type, and processing status with real-time updates.
    """

    def __init__(
        self,
        persona_config: Optional[Dict[str, Any]] = None,
        acknowledgment_config: Optional[AcknowledgmentConfig] = None,
    ):
        """
        Initialize the acknowledgment generator.

        Args:
            persona_config: Overlord persona configuration
            acknowledgment_config: Acknowledgment generation settings
        """
        self.persona_config = persona_config or {}
        self.config = acknowledgment_config or AcknowledgmentConfig()

        # Extract persona characteristics
        self.persona_name = self.persona_config.get("name", self.config.persona_name)
        self.personality_traits = self.persona_config.get("traits", [])
        self.communication_style = self.persona_config.get("style", "professional")

        # Processing status tracking
        self._processing_statuses: Dict[str, DocumentProcessingStatus] = {}

        # Message templates by persona type
        self._message_templates = self._initialize_templates()

    def _initialize_templates(self) -> Dict[str, Dict[str, List[str]]]:
        """Initialize message templates for different persona types and stages"""
        return {
            "professional": {
                "received": [
                    "Document '{filename}' has been received and queued for processing.",
                    "I've received '{filename}' and will begin processing immediately.",
                    "'{filename}' is now in the processing queue.",
                ],
                "processing": [
                    "Currently processing '{filename}' - analyzing content structure.",
                    "Working on '{filename}' - extracting key information.",
                    "Processing '{filename}' - {progress}% complete.",
                ],
                "complete": [
                    "Successfully processed '{filename}'. Document analysis complete.",
                    "'{filename}' has been fully processed and indexed.",
                    "Document processing for '{filename}' completed successfully.",
                ],
                "error": [
                    "Encountered an issue processing '{filename}'. Investigating resolution.",
                    "Processing error with '{filename}'. Please check document format.",
                    "Unable to complete processing for '{filename}' due to: {error_reason}",
                ],
            },
            "friendly": {
                "received": [
                    "Great! I've got '{filename}' and I'm excited to dive into it.",
                    "Perfect! '{filename}' is here - let me take a look at this.",
                    "Thanks for sharing '{filename}'! I'll get this processed right away.",
                ],
                "processing": [
                    "Making good progress on '{filename}' - this is interesting content!",
                    "Working through '{filename}' now - {progress}% done and counting!",
                    "'{filename}' is coming along nicely - almost there!",
                ],
                "complete": [
                    "All done with '{filename}'! That was a great read.",
                    "'{filename}' is fully processed - really insightful document!",
                    "Finished analyzing '{filename}' - lots of useful information here!",
                ],
                "error": [
                    "Hmm, hit a snag with '{filename}' - let me figure out what's going on.",
                    "Oops! Having trouble with '{filename}' - the format might need adjustment.",
                    "'{filename}' is giving me some trouble: {error_reason}. Let's fix this!",
                ],
            },
            "technical": {
                "received": [
                    "Document '{filename}' ingested. Initiating analysis pipeline.",
                    "'{filename}' received. Beginning content parsing and extraction.",
                    "Processing queue updated with '{filename}'. Starting workflow.",
                ],
                "processing": [
                    "'{filename}': Chunking algorithm active, vector encoding in progress.",
                    "Processing '{filename}': {progress}% - semantic analysis underway.",
                    "'{filename}' processing: Content structure mapped, indexing vectors.",
                ],
                "complete": [
                    "'{filename}' processing complete. Vector index updated with {chunk_count} chunks.",  # noqa: E501
                    "Document analysis finished for '{filename}'. Semantic search ready.",
                    "'{filename}' successfully processed and integrated into knowledge base.",
                ],
                "error": [
                    "Processing error in '{filename}': {error_reason}. Check format specifications.",  # noqa: E501
                    "'{filename}' failed processing pipeline. Error code: {error_code}",
                    "Unable to parse '{filename}': {error_reason}. Diagnostic information available.",  # noqa: E501
                ],
            },
        }

    async def generate_receipt_acknowledgment(
        self,
        filename: str,
        document_id: str,
        file_size: int,
        mime_type: Optional[str] = None,
        estimated_processing_time: Optional[float] = None,
    ) -> str:
        """
        Generate acknowledgment for document receipt.

        Args:
            filename: Name of the uploaded file
            document_id: Unique document identifier
            file_size: Size of the file in bytes
            mime_type: MIME type of the document
            estimated_processing_time: Estimated processing time in seconds

        Returns:
            Acknowledgment message string
        """
        # Create processing status
        status = DocumentProcessingStatus(
            document_id=document_id,
            filename=filename,
            stage="received",
            progress_percentage=0.0,
            estimated_completion=estimated_processing_time,
            messages=[],
            timestamp=time.time(),
        )

        self._processing_statuses[document_id] = status

        # Generate base acknowledgment
        base_message = self._get_template_message("received", filename=filename)

        # Add processing details if configured
        if self.config.include_processing_status:
            details = self._generate_processing_details(
                file_size, mime_type, estimated_processing_time
            )
            if details:
                base_message += f" {details}"

        # Add next steps if configured
        if self.config.include_next_steps:
            next_steps = self._generate_next_steps(mime_type)
            if next_steps:
                base_message += f" {next_steps}"

        # Apply persona styling
        final_message = self._apply_persona_styling(base_message)

        return final_message

    async def generate_progress_update(
        self,
        document_id: str,
        progress_percentage: float,
        current_stage: str,
        stage_details: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate progress update message.

        Args:
            document_id: Document identifier
            progress_percentage: Current progress (0.0-100.0)
            current_stage: Current processing stage
            stage_details: Optional details about current stage

        Returns:
            Progress update message or None if no update needed
        """
        status = self._processing_statuses.get(document_id)
        if not status:
            return None

        # Update status
        status.stage = current_stage
        status.progress_percentage = progress_percentage
        status.timestamp = time.time()

        # Only generate updates for significant progress or stage changes
        if not self._should_generate_progress_update(status, progress_percentage):
            return None

        # Generate progress message
        message = self._get_template_message(
            current_stage, filename=status.filename, progress=int(progress_percentage)
        )

        # Add stage details if provided
        if stage_details and self.config.technical_detail != "minimal":
            message += f" {stage_details}"

        # Apply persona styling
        final_message = self._apply_persona_styling(message)

        return final_message

    async def generate_completion_acknowledgment(
        self,
        document_id: str,
        processing_summary: Dict[str, Any],
        insights: Optional[List[str]] = None,
    ) -> str:
        """
        Generate completion acknowledgment with processing summary.

        Args:
            document_id: Document identifier
            processing_summary: Summary of processing results
            insights: Optional list of document insights

        Returns:
            Completion acknowledgment message
        """
        status = self._processing_statuses.get(document_id)
        if not status:
            return "Document processing completed."

        # Update status
        status.stage = "complete"
        status.progress_percentage = 100.0
        status.timestamp = time.time()

        # Generate base completion message
        base_message = self._get_template_message(
            "complete",
            filename=status.filename,
            chunk_count=processing_summary.get("chunk_count", 0),
        )

        # Add processing summary if configured
        if self.config.technical_detail != "minimal":
            summary = self._generate_processing_summary(processing_summary)
            if summary:
                base_message += f" {summary}"

        # Add insights if provided and appropriate
        if insights and self.config.include_next_steps:
            insight_text = self._format_insights(insights)
            if insight_text:
                base_message += f" {insight_text}"

        # Apply persona styling
        final_message = self._apply_persona_styling(base_message)

        return final_message

    async def generate_error_acknowledgment(
        self,
        document_id: str,
        error_type: str,
        error_details: str,
        recovery_suggestions: Optional[List[str]] = None,
    ) -> str:
        """
        Generate error acknowledgment with recovery suggestions.

        Args:
            document_id: Document identifier
            error_type: Type of error encountered
            error_details: Detailed error description
            recovery_suggestions: Optional recovery suggestions

        Returns:
            Error acknowledgment message
        """
        status = self._processing_statuses.get(document_id)
        filename = status.filename if status else "document"

        # Update status if available
        if status:
            status.stage = "error"
            status.timestamp = time.time()

        # Generate base error message
        base_message = self._get_template_message(
            "error", filename=filename, error_reason=error_details, error_code=error_type
        )

        # Add recovery suggestions if provided
        if recovery_suggestions and self.config.include_next_steps:
            suggestions_text = self._format_recovery_suggestions(recovery_suggestions)
            if suggestions_text:
                base_message += f" {suggestions_text}"

        # Apply persona styling
        final_message = self._apply_persona_styling(base_message)

        return final_message

    def _get_template_message(self, stage: str, **kwargs) -> str:
        """Get appropriate template message for stage and persona"""
        persona_type = self._determine_persona_type()
        templates = self._message_templates.get(persona_type, {}).get(stage, [])

        if not templates:
            # Fallback to professional templates
            templates = self._message_templates["professional"].get(stage, [])

        if not templates:
            return f"Document {stage}"

        # Select template based on enthusiasm level
        template_index = self._select_template_index(len(templates))
        template = templates[template_index]

        # Format template with provided kwargs
        try:
            return template.format(**kwargs)
        except KeyError:
            # Return template without formatting if missing keys
            return template

    def _determine_persona_type(self) -> str:
        """Determine the persona type from configuration"""
        if "technical" in self.personality_traits or self.communication_style == "technical":
            return "technical"
        elif "friendly" in self.personality_traits or self.communication_style == "casual":
            return "friendly"
        else:
            return "professional"

    def _select_template_index(self, template_count: int) -> int:
        """Select template index based on enthusiasm level"""
        if self.config.enthusiasm_level == "low":
            return 0
        elif self.config.enthusiasm_level == "high":
            return min(template_count - 1, 2)
        else:
            return min(1, template_count - 1)

    def _generate_processing_details(
        self, file_size: int, mime_type: Optional[str], estimated_time: Optional[float]
    ) -> str:
        """Generate processing details for acknowledgment"""
        details = []

        # Add file size if significant
        if file_size > 1024 * 1024:  # > 1MB
            size_mb = file_size / (1024 * 1024)
            details.append(f"Size: {size_mb:.1f}MB")

        # Add document type
        if mime_type:
            doc_type = self._mime_type_to_description(mime_type)
            if doc_type:
                details.append(f"Type: {doc_type}")

        # Add estimated time if available
        if estimated_time and estimated_time > 30:  # > 30 seconds
            time_desc = self._format_estimated_time(estimated_time)
            details.append(f"Estimated processing: {time_desc}")

        if details:
            return f"({', '.join(details)})"
        return ""

    def _generate_next_steps(self, mime_type: Optional[str]) -> str:
        """Generate next steps information"""
        if mime_type:
            if "pdf" in mime_type.lower():
                return "I'll extract text, images, and structure from this PDF."
            elif "word" in mime_type.lower() or "document" in mime_type.lower():
                return "I'll process the document content and formatting."
            elif "text" in mime_type.lower():
                return "I'll analyze and chunk this text for optimal searchability."

        return "I'll process and analyze the content for you."

    def _generate_processing_summary(self, summary: Dict[str, Any]) -> str:
        """Generate processing summary text"""
        parts = []

        if "chunk_count" in summary:
            parts.append(f"{summary['chunk_count']} content chunks created")

        if "page_count" in summary:
            parts.append(f"{summary['page_count']} pages processed")

        if "word_count" in summary:
            parts.append(f"{summary['word_count']:,} words analyzed")

        if "processing_time" in summary:
            time_str = self._format_processing_time(summary["processing_time"])
            parts.append(f"processed in {time_str}")

        if parts:
            return f"({', '.join(parts)})"
        return ""

    def _format_insights(self, insights: List[str]) -> str:
        """Format document insights for acknowledgment"""
        if not insights:
            return ""

        if len(insights) == 1:
            return f"Key insight: {insights[0]}"
        elif len(insights) <= 3:
            return f"Key insights include: {', '.join(insights[:2])}"
        else:
            return f"Identified {len(insights)} key insights from this document"

    def _format_recovery_suggestions(self, suggestions: List[str]) -> str:
        """Format recovery suggestions"""
        if not suggestions:
            return ""

        if len(suggestions) == 1:
            return f"Suggestion: {suggestions[0]}"
        else:
            return f"Suggestions: {suggestions[0]}"

    def _apply_persona_styling(self, message: str) -> str:
        """Apply persona-specific styling to message"""
        # Add persona name if configured
        if self.persona_name and self.communication_style == "friendly":
            if not message.startswith(self.persona_name):
                message = f"{self.persona_name}: {message}"

        # Ensure message length is within limits
        if len(message) > self.config.max_message_length:
            message = message[: self.config.max_message_length - 3] + "..."

        return message

    def _should_generate_progress_update(
        self, status: DocumentProcessingStatus, progress: float
    ) -> bool:
        """Determine if a progress update should be generated"""
        # Always update on stage changes
        if status.stage != status.stage:
            return True

        # Update on significant progress increments
        progress_diff = progress - status.progress_percentage
        if progress_diff >= 25:  # 25% increments
            return True

        # Update if it's been a while since last update
        time_since_update = time.time() - status.timestamp
        if time_since_update > 30:  # 30 seconds
            return True

        return False

    def _mime_type_to_description(self, mime_type: str) -> str:
        """Convert MIME type to user-friendly description"""
        mime_mapping = {
            "application/pdf": "PDF",
            "application/msword": "Word Document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",  # noqa: E501
            "text/plain": "Text File",
            "text/markdown": "Markdown",
            "application/rtf": "Rich Text Document",
        }
        return mime_mapping.get(mime_type, "Document")

    def _format_estimated_time(self, seconds: float) -> str:
        """Format estimated time for user display"""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''}"

    def _format_processing_time(self, seconds: float) -> str:
        """Format processing time for summary"""
        if seconds < 1:
            return f"{int(seconds * 1000)}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        else:
            minutes = int(seconds / 60)
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds:.0f}s"

    def get_processing_status(self, document_id: str) -> Optional[DocumentProcessingStatus]:
        """Get current processing status for a document"""
        return self._processing_statuses.get(document_id)

    def clear_processing_status(self, document_id: str) -> bool:
        """Clear processing status for a document"""
        if document_id in self._processing_statuses:
            del self._processing_statuses[document_id]
            return True
        return False
