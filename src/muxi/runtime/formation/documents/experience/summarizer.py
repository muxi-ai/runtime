"""
Document Summarizer Implementation

This module implements advanced document summarization with multiple
summarization types and cross-document insight generation.

Features:
- Multiple summarization types (overview, key_points, actionable)
- Cross-document insight generation
- Persona-consistent summary formatting
- Progressive summarization for large documents
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ....services import observability


@dataclass
class SummaryConfig:
    """Configuration for document summarization"""

    summary_type: str = "overview"  # "overview", "key_points", "actionable", "technical"
    max_length: int = 500
    include_citations: bool = True
    persona_style: str = "professional"  # "professional", "casual", "technical"
    cross_document: bool = False


@dataclass
class DocumentSummary:
    """Represents a generated document summary"""

    summary_id: str
    document_id: str
    summary_type: str
    content: str
    key_points: List[str]
    citations: List[str]
    confidence_score: float
    processing_time: float
    timestamp: float
    metadata: Dict[str, Any]


class DocumentSummarizer:
    """
    Advanced document summarization with multiple output formats.

    Provides comprehensive summarization capabilities with persona-consistent
    formatting and cross-document insight generation.
    """

    def __init__(self, llm_model, persona_config: Optional[Dict[str, Any]] = None):
        """Initialize the document summarizer."""
        self.llm_model = llm_model
        self.persona_config = persona_config or {}
        self._summary_cache: Dict[str, DocumentSummary] = {}

    async def summarize_document(
        self, document_id: str, document_content: str, config: Optional[SummaryConfig] = None
    ) -> DocumentSummary:
        """Generate a summary for a document."""
        config = config or SummaryConfig()

        prompt = f"""
        Please provide a {config.summary_type} summary of this document:

        {document_content}

        Keep it under {config.max_length} words and focus on the key information.
        """

        try:
            response = await self.llm_model.generate_response(prompt)

            summary = DocumentSummary(
                summary_id=f"{document_id}_{config.summary_type}_{int(time.time())}",
                document_id=document_id,
                summary_type=config.summary_type,
                content=response.strip(),
                key_points=self._extract_key_points(response),
                confidence_score=0.8,  # Default confidence
                processing_time=0.0,  # Default processing time
                timestamp=time.time(),
            )

            self._summary_cache[summary.summary_id] = summary
            return summary

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "document_id": document_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "summarize_document",
                },
                description="Failed to summarize document",
            )
            raise

    def _extract_key_points(self, content: str) -> List[str]:
        """Extract key points from content"""
        lines = content.strip().split("\n")
        key_points = []

        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                key_points.append(line[2:])

        return key_points

    async def summarize_multiple_documents(
        self, documents: List[Dict[str, Any]], cross_document_insights: bool = True
    ) -> Dict[str, Any]:
        """
        Generate summaries for multiple documents with cross-document insights.

        Args:
            documents: List of document dictionaries with id, content, metadata
            cross_document_insights: Whether to generate cross-document insights

        Returns:
            Dictionary with individual summaries and cross-document insights
        """

        # Generate individual summaries
        summaries = {}
        for doc in documents:
            try:
                summary = await self.summarize_document(
                    document_id=doc["id"],
                    document_content=doc["content"],
                    config=SummaryConfig(summary_type=doc["summary_type"]),
                )
                summaries[doc["id"]] = summary
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "document_id": doc.get("id", "unknown"),
                        "error_type": type(e).__name__,
                        "error": str(e),
                        "operation": "summarize_multiple_documents",
                    },
                    description="Failed to summarize individual document in batch",
                )
                continue

        result = {"individual_summaries": summaries}

        # Generate cross-document insights if requested
        if cross_document_insights and len(summaries) > 1:
            insights = await self._generate_cross_document_insights(summaries)
            result["cross_document_insights"] = insights

        return result

    async def generate_progressive_summary(
        self, document_chunks: List[Dict[str, Any]], final_summary_type: str = "overview"
    ) -> DocumentSummary:
        """
        Generate progressive summary for large documents by chunk.

        Args:
            document_chunks: List of document chunks with content and metadata
            final_summary_type: Type of final summary to generate

        Returns:
            DocumentSummary object with progressive summary
        """

        # Summarize chunks in batches
        chunk_summaries = []
        batch_size = 5  # Process 5 chunks at a time

        for i in range(0, len(document_chunks), batch_size):
            batch = document_chunks[i:i + batch_size]
            batch_content = "\n\n".join([chunk["content"] for chunk in batch])

            # Generate summary for this batch
            batch_summary = await self._summarize_content_batch(
                batch_content, f"batch_{i // batch_size + 1}"
            )
            chunk_summaries.append(batch_summary)

        # Combine batch summaries into final summary
        combined_content = "\n\n".join(chunk_summaries)

        # Generate final summary
        final_summary = await self.summarize_document(
            document_id=f"progressive_{int(time.time())}",
            document_content=combined_content,
            config=SummaryConfig(summary_type=final_summary_type),
        )

        return final_summary

    def _build_summarization_prompt(
        self, content: str, config: SummaryConfig, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build the summarization prompt based on configuration"""
        # Get base prompt for summary type
        base_prompt = self._summary_prompts.get(
            config.summary_type, self._summary_prompts["overview"]
        )

        # Add persona styling
        persona_instruction = self._get_persona_instruction(config.persona_style)

        # Add length constraint
        length_instruction = (
            f"\n\nPlease limit the summary to approximately {config.max_length} words."
        )

        # Add citation instruction if needed
        citation_instruction = ""
        if config.include_citations:
            citation_instruction = "\n\nInclude relevant citations or references where appropriate."

        # Add document metadata context if available
        metadata_context = ""
        if metadata:
            metadata_context = f"\n\nDocument context: {metadata.get('filename', 'N/A')}"
            if metadata.get("document_type"):
                metadata_context += f", Type: {metadata['document_type']}"

        # Combine all components
        full_prompt = (
            base_prompt
            + persona_instruction
            + length_instruction
            + citation_instruction
            + metadata_context
            + f"\n\nDocument content:\n{content}"
        )

        return full_prompt

    def _get_persona_instruction(self, persona_style: str) -> str:
        """Get persona-specific instruction for summary formatting"""
        persona_instructions = {
            "professional": "\n\nUse a professional, formal tone appropriate for business documentation.",  # noqa: E501
            "casual": "\n\nUse a conversational, accessible tone that's easy to understand.",  # noqa: E501
            "technical": "\n\nUse precise technical language appropriate for technical documentation.",  # noqa: E501
        }
        return persona_instructions.get(persona_style, "")

    def _parse_summary_response(self, response: str, summary_type: str) -> Dict[str, Any]:
        """Parse and structure the LLM response"""
        # Basic parsing - in production, this would be more sophisticated
        lines = response.strip().split("\n")

        content = response.strip()
        key_points = []
        citations = []

        # Extract key points if bullet format is used
        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                key_points.append(line[2:])
            elif line.startswith("* "):
                key_points.append(line[2:])

        # Extract citations (basic pattern matching)
        import re

        citation_pattern = r"\[(.*?)\]|\((.*?)\)"
        citations = re.findall(citation_pattern, response)
        citations = [cite[0] or cite[1] for cite in citations if cite[0] or cite[1]]

        return {"content": content, "key_points": key_points, "citations": citations}

    def _calculate_confidence_score(self, structured_summary: Dict[str, Any]) -> float:
        """Calculate confidence score for the generated summary"""
        # Basic confidence calculation based on content quality indicators
        content = structured_summary["content"]

        confidence = 0.5  # Base confidence

        # Increase confidence based on content characteristics
        if len(content) > 100:  # Reasonable length
            confidence += 0.2

        if structured_summary["key_points"]:  # Has extracted key points
            confidence += 0.2

        if structured_summary["citations"]:  # Has citations
            confidence += 0.1

        # Simple quality indicators
        sentences = content.split(".")
        if len(sentences) >= 3:  # Multiple sentences
            confidence += 0.1

        return min(confidence, 1.0)

    async def _generate_cross_document_insights(
        self, summaries: Dict[str, DocumentSummary]
    ) -> Dict[str, Any]:
        """Generate insights across multiple document summaries"""

        # Combine all summary content
        combined_content = "\n\n".join(
            [f"Document {doc_id}: {summary.content}" for doc_id, summary in summaries.items()]
        )

        # Identify common themes
        themes_prompt = f"""
        Analyze these document summaries and identify:
        1. Common themes across documents
        2. Contradictions or conflicting information
        3. Complementary information that builds a bigger picture
        4. Gaps in coverage

        Summaries:
        {combined_content}
        """

        try:
            insights_response = await self.llm_model.generate_response(themes_prompt)

            return {
                "common_themes": self._extract_themes(insights_response),
                "contradictions": self._extract_contradictions(insights_response),
                "complementary_info": self._extract_complementary_info(insights_response),
                "gaps": self._extract_gaps(insights_response),
                "synthesis": insights_response,
                "document_count": len(summaries),
                "generated_at": time.time(),
            }

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "generate_cross_document_insights",
                },
                description="Failed to generate cross-document insights",
            )
            return {"error": str(e)}

    async def _summarize_content_batch(self, content: str, batch_id: str) -> str:
        """Summarize a batch of content for progressive summarization"""
        prompt = f"""
        Provide a concise summary of this content batch:

        {content}

        Focus on the main points and key information that should be preserved
        for a higher-level summary.
        """

        try:
            response = await self.llm_model.generate_response(prompt)
            return response.strip()
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "batch_id": batch_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "summarize_content_batch",
                },
                description=f"Failed to summarize content batch {batch_id}",
            )
            return f"[Error summarizing batch {batch_id}]"

    def _extract_themes(self, insights_text: str) -> List[str]:
        """Extract common themes from insights text"""
        # Basic extraction - look for numbered or bulleted lists
        lines = insights_text.split("\n")
        themes = []

        for line in lines:
            line = line.strip()
            if (
                line.startswith("1.")
                or line.startswith("2.")
                or line.startswith("- ")
                or line.startswith("• ")
            ):
                themes.append(line[2:].strip())

        return themes[:5]  # Limit to top 5 themes

    def _extract_contradictions(self, insights_text: str) -> List[str]:
        """Extract contradictions from insights text"""
        # Look for contradiction keywords
        contradiction_keywords = ["contradict", "conflict", "disagree", "opposite"]
        lines = insights_text.split("\n")
        contradictions = []

        for line in lines:
            if any(keyword in line.lower() for keyword in contradiction_keywords):
                contradictions.append(line.strip())

        return contradictions

    def _extract_complementary_info(self, insights_text: str) -> List[str]:
        """Extract complementary information from insights text"""
        # Look for complementary keywords
        complementary_keywords = ["complement", "build", "support", "enhance"]
        lines = insights_text.split("\n")
        complementary = []

        for line in lines:
            if any(keyword in line.lower() for keyword in complementary_keywords):
                complementary.append(line.strip())

        return complementary

    def _extract_gaps(self, insights_text: str) -> List[str]:
        """Extract information gaps from insights text"""
        # Look for gap keywords
        gap_keywords = ["missing", "gap", "lack", "absent", "not covered"]
        lines = insights_text.split("\n")
        gaps = []

        for line in lines:
            if any(keyword in line.lower() for keyword in gap_keywords):
                gaps.append(line.strip())

        return gaps

    def get_summary_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the summary cache"""
        if not self._summary_cache:
            return {"total_summaries": 0}

        summary_types = {}
        total_processing_time = 0

        for summary in self._summary_cache.values():
            summary_types[summary.summary_type] = summary_types.get(summary.summary_type, 0) + 1
            total_processing_time += summary.processing_time

        return {
            "total_summaries": len(self._summary_cache),
            "summary_types": summary_types,
            "avg_processing_time": total_processing_time / len(self._summary_cache),
            "cache_size_mb": self._estimate_cache_size(),
        }

    def _estimate_cache_size(self) -> float:
        """Estimate cache size in MB"""
        total_size = 0
        for summary in self._summary_cache.values():
            total_size += len(summary.content)
            total_size += sum(len(point) for point in summary.key_points)
            total_size += sum(len(citation) for citation in summary.citations)

        return total_size / (1024 * 1024)  # Convert to MB

    def clear_summary_cache(self, older_than_hours: Optional[float] = None) -> int:
        """Clear summary cache, optionally only entries older than specified hours"""
        if older_than_hours is None:
            count = len(self._summary_cache)
            self._summary_cache.clear()
            return count

        current_time = time.time()
        cutoff_time = current_time - (older_than_hours * 3600)

        to_remove = [
            summary_id
            for summary_id, summary in self._summary_cache.items()
            if summary.timestamp < cutoff_time
        ]

        for summary_id in to_remove:
            del self._summary_cache[summary_id]

        return len(to_remove)
