"""
Document Reference System Implementation

This module implements cross-document reference tracking and management,
enabling traceability between document chunks and generated outputs.

Features:
- Document cross-reference tracking
- Citation generation and management
- Reference lineage tracking
- Source attribution
"""

import datetime
import hashlib
import json
import time
from ....utils.id_generator import generate_nanoid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from ....services import observability


@dataclass
class DocumentReference:
    """Represents a reference to a document chunk"""

    reference_id: str
    source_document_id: str
    source_chunk_id: str
    referenced_content: str
    context: str
    confidence: float
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class ReferenceLineage:
    """Tracks the lineage of references through processing steps"""

    lineage_id: str
    root_references: List[str]  # Original document reference IDs
    derived_references: List[str]  # References created from processing
    processing_steps: List[Dict[str, Any]]
    final_output: Optional[str]
    timestamp: float


class DocumentReferenceSystem:
    """
    Cross-document reference tracking and management system.

    Provides comprehensive reference tracking with lineage management,
    citation generation, and source attribution for document processing.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the document reference system.

        Args:
            storage_path: Optional path for reference persistence
        """
        self.storage_path = storage_path or ".muxi/document_references.json"

        # Reference storage
        self._references: Dict[str, DocumentReference] = {}
        self._lineages: Dict[str, ReferenceLineage] = {}

        # Indexing for fast lookups
        self._document_to_references: Dict[str, Set[str]] = {}  # doc_id -> ref_ids
        self._chunk_to_references: Dict[str, Set[str]] = {}  # chunk_id -> ref_ids
        self._output_to_lineage: Dict[str, str] = {}  # output_hash -> lineage_id

        # Ensure storage directory exists
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)

        # Load existing references
        self._load_references()

    async def create_reference(
        self,
        source_document_id: str,
        source_chunk_id: str,
        referenced_content: str,
        context: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new document reference.

        Args:
            source_document_id: ID of the source document
            source_chunk_id: ID of the specific chunk referenced
            referenced_content: The actual content being referenced
            context: Context in which the reference was made
            confidence: Confidence score for the reference (0.0-1.0)
            metadata: Optional additional metadata

        Returns:
            Reference ID
        """
        reference_id = f"ref_{generate_nanoid()}"
        current_time = time.time()

        reference = DocumentReference(
            reference_id=reference_id,
            source_document_id=source_document_id,
            source_chunk_id=source_chunk_id,
            referenced_content=referenced_content,
            context=context,
            confidence=confidence,
            timestamp=current_time,
            metadata=metadata or {},
        )

        # Store reference
        self._references[reference_id] = reference

        # Update indexes
        self._update_reference_indexes(reference)

        # Persist changes
        await self._persist_references()

        return reference_id

    async def create_lineage(
        self,
        root_reference_ids: List[str],
        processing_steps: List[Dict[str, Any]],
        final_output: Optional[str] = None,
    ) -> str:
        """
        Create a new reference lineage tracking processing steps.

        Args:
            root_reference_ids: List of original reference IDs
            processing_steps: List of processing step descriptions
            final_output: Optional final output content

        Returns:
            Lineage ID
        """
        lineage_id = f"lin_{generate_nanoid()}"
        current_time = time.time()

        lineage = ReferenceLineage(
            lineage_id=lineage_id,
            root_references=root_reference_ids,
            derived_references=[],
            processing_steps=processing_steps,
            final_output=final_output,
            timestamp=current_time,
        )

        # Store lineage
        self._lineages[lineage_id] = lineage

        # Index by output if provided
        if final_output:
            output_hash = self._hash_content(final_output)
            self._output_to_lineage[output_hash] = lineage_id

        # Persist changes
        await self._persist_references()

        return lineage_id

    async def add_derived_reference(self, lineage_id: str, derived_reference_id: str) -> bool:
        """
        Add a derived reference to an existing lineage.

        Args:
            lineage_id: ID of the lineage
            derived_reference_id: ID of the derived reference

        Returns:
            True if successful, False if lineage not found
        """
        lineage = self._lineages.get(lineage_id)
        if not lineage:
            return False

        lineage.derived_references.append(derived_reference_id)
        await self._persist_references()

        return True

    async def get_references_for_document(self, document_id: str) -> List[DocumentReference]:
        """
        Get all references for a specific document.

        Args:
            document_id: Document identifier

        Returns:
            List of DocumentReference objects
        """
        reference_ids = self._document_to_references.get(document_id, set())
        return [self._references[ref_id] for ref_id in reference_ids if ref_id in self._references]

    async def get_references_for_chunk(self, chunk_id: str) -> List[DocumentReference]:
        """
        Get all references for a specific chunk.

        Args:
            chunk_id: Chunk identifier

        Returns:
            List of DocumentReference objects
        """
        reference_ids = self._chunk_to_references.get(chunk_id, set())
        return [self._references[ref_id] for ref_id in reference_ids if ref_id in self._references]

    async def get_lineage_for_output(self, output_content: str) -> Optional[ReferenceLineage]:
        """
        Get the lineage for a specific output.

        Args:
            output_content: The output content to find lineage for

        Returns:
            ReferenceLineage object or None if not found
        """
        output_hash = self._hash_content(output_content)
        lineage_id = self._output_to_lineage.get(output_hash)

        if lineage_id:
            return self._lineages.get(lineage_id)
        return None

    async def generate_citation(self, reference_id: str, style: str = "academic") -> Optional[str]:
        """
        Generate a citation for a reference.

        Args:
            reference_id: Reference identifier
            style: Citation style ("academic", "brief", "full")

        Returns:
            Citation string or None if reference not found
        """
        reference = self._references.get(reference_id)
        if not reference:
            return None

        if style == "academic":
            return self._generate_academic_citation(reference)
        elif style == "brief":
            return self._generate_brief_citation(reference)
        elif style == "full":
            return self._generate_full_citation(reference)
        else:
            return self._generate_brief_citation(reference)

    def _generate_academic_citation(self, reference: DocumentReference) -> str:
        """Generate academic-style citation"""
        metadata = reference.metadata
        filename = metadata.get("filename", "Unknown Document")
        chunk_index = metadata.get("chunk_index", "")

        citation = f"({filename}"
        if chunk_index:
            citation += f", Section {chunk_index + 1}"
        citation += f", accessed {self._format_timestamp(reference.timestamp)})"

        return citation

    def _generate_brief_citation(self, reference: DocumentReference) -> str:
        """Generate brief citation"""
        metadata = reference.metadata
        filename = metadata.get("filename", "Unknown")
        return f"[{filename}]"

    def _generate_full_citation(self, reference: DocumentReference) -> str:
        """Generate full citation with all details"""
        metadata = reference.metadata
        filename = metadata.get("filename", "Unknown Document")
        chunk_index = metadata.get("chunk_index", "")
        document_id = reference.source_document_id[:8]  # Short version

        citation = f"Reference: {filename}"
        if chunk_index:
            citation += f" (Section {chunk_index + 1})"
        citation += f"\nDocument ID: {document_id}"
        citation += f"\nConfidence: {reference.confidence:.2f}"
        citation += f"\nReferenced: {self._format_timestamp(reference.timestamp)}"

        if reference.context:
            citation += f"\nContext: {reference.context[:100]}..."

        return citation

    async def trace_lineage(self, reference_id: str) -> List[Dict[str, Any]]:
        """
        Trace the complete lineage of a reference.

        Args:
            reference_id: Reference identifier

        Returns:
            List of lineage steps
        """
        lineage_trace = []

        # Find lineages containing this reference
        for lineage in self._lineages.values():
            if (
                reference_id in lineage.root_references
                or reference_id in lineage.derived_references
            ):

                lineage_trace.append(
                    {
                        "lineage_id": lineage.lineage_id,
                        "type": "root" if reference_id in lineage.root_references else "derived",
                        "processing_steps": lineage.processing_steps,
                        "final_output": lineage.final_output,
                        "timestamp": lineage.timestamp,
                    }
                )

        return sorted(lineage_trace, key=lambda x: x["timestamp"])

    async def get_source_attribution(self, output_content: str) -> Dict[str, Any]:
        """
        Get source attribution for output content.

        Args:
            output_content: Content to attribute

        Returns:
            Attribution information dictionary
        """
        lineage = await self.get_lineage_for_output(output_content)
        if not lineage:
            return {"sources": [], "confidence": 0.0}

        # Collect all source references
        all_references = lineage.root_references + lineage.derived_references
        sources = []
        total_confidence = 0.0

        for ref_id in all_references:
            reference = self._references.get(ref_id)
            if reference:
                sources.append(
                    {
                        "reference_id": ref_id,
                        "document_id": reference.source_document_id,
                        "chunk_id": reference.source_chunk_id,
                        "filename": reference.metadata.get("filename", "Unknown"),
                        "confidence": reference.confidence,
                        "content_preview": reference.referenced_content[:200] + "...",
                    }
                )
                total_confidence += reference.confidence

        avg_confidence = total_confidence / len(sources) if sources else 0.0

        return {
            "sources": sources,
            "lineage_id": lineage.lineage_id,
            "processing_steps": len(lineage.processing_steps),
            "confidence": avg_confidence,
            "timestamp": lineage.timestamp,
        }

    def get_reference_stats(self) -> Dict[str, Any]:
        """Get statistics about the reference system"""
        if not self._references:
            return {"total_references": 0, "total_lineages": 0, "total_documents": 0}

        # Count unique documents
        unique_documents = set()
        confidence_scores = []

        for reference in self._references.values():
            unique_documents.add(reference.source_document_id)
            confidence_scores.append(reference.confidence)

        avg_confidence = sum(confidence_scores) / len(confidence_scores)

        return {
            "total_references": len(self._references),
            "total_lineages": len(self._lineages),
            "total_documents": len(unique_documents),
            "avg_confidence": avg_confidence,
            "min_confidence": min(confidence_scores),
            "max_confidence": max(confidence_scores),
            "references_per_document": len(self._references) / max(len(unique_documents), 1),
        }

    def _update_reference_indexes(self, reference: DocumentReference) -> None:
        """Update reference indexes"""
        # Document index
        if reference.source_document_id not in self._document_to_references:
            self._document_to_references[reference.source_document_id] = set()
        self._document_to_references[reference.source_document_id].add(reference.reference_id)

        # Chunk index
        if reference.source_chunk_id not in self._chunk_to_references:
            self._chunk_to_references[reference.source_chunk_id] = set()
        self._chunk_to_references[reference.source_chunk_id].add(reference.reference_id)

    def _hash_content(self, content: str) -> str:
        """Generate hash for content"""
        return hashlib.md5(content.encode()).hexdigest()

    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp for display"""
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")

    def _load_references(self) -> None:
        """Load references from storage"""
        try:
            if Path(self.storage_path).exists():
                with open(self.storage_path, "r") as f:
                    data = json.load(f)

                # Load references
                for ref_id, ref_data in data.get("references", {}).items():
                    reference = DocumentReference(
                        reference_id=ref_data["reference_id"],
                        source_document_id=ref_data["source_document_id"],
                        source_chunk_id=ref_data["source_chunk_id"],
                        referenced_content=ref_data["referenced_content"],
                        context=ref_data["context"],
                        confidence=ref_data["confidence"],
                        timestamp=ref_data["timestamp"],
                        metadata=ref_data["metadata"],
                    )
                    self._references[ref_id] = reference
                    self._update_reference_indexes(reference)

                # Load lineages
                for lineage_id, lineage_data in data.get("lineages", {}).items():
                    lineage = ReferenceLineage(
                        lineage_id=lineage_data["lineage_id"],
                        root_references=lineage_data["root_references"],
                        derived_references=lineage_data["derived_references"],
                        processing_steps=lineage_data["processing_steps"],
                        final_output=lineage_data.get("final_output"),
                        timestamp=lineage_data["timestamp"],
                    )
                    self._lineages[lineage_id] = lineage

                    # Update output index
                    if lineage.final_output:
                        output_hash = self._hash_content(lineage.final_output)
                        self._output_to_lineage[output_hash] = lineage_id

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "persist_reference_cache",
                },
                description="Failed to persist reference cache",
            )

    async def _persist_references(self) -> None:
        """Persist references to storage"""
        try:
            # Convert to serializable format
            data = {
                "references": {
                    ref_id: {
                        "reference_id": ref.reference_id,
                        "source_document_id": ref.source_document_id,
                        "source_chunk_id": ref.source_chunk_id,
                        "referenced_content": ref.referenced_content,
                        "context": ref.context,
                        "confidence": ref.confidence,
                        "timestamp": ref.timestamp,
                        "metadata": ref.metadata,
                    }
                    for ref_id, ref in self._references.items()
                },
                "lineages": {
                    lineage_id: {
                        "lineage_id": lineage.lineage_id,
                        "root_references": lineage.root_references,
                        "derived_references": lineage.derived_references,
                        "processing_steps": lineage.processing_steps,
                        "final_output": lineage.final_output,
                        "timestamp": lineage.timestamp,
                    }
                    for lineage_id, lineage in self._lineages.items()
                },
            }

            # Write to temporary file first, then rename for atomic operation
            temp_path = f"{self.storage_path}.tmp"
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            Path(temp_path).rename(self.storage_path)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.REFERENCE_PERSISTENCE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "persist_references",
                },
                description="Failed to persist references to storage",
            )
            raise
