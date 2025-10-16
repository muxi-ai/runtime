"""
Document Cross Reference Manager Implementation

This module implements cross-document reference tracking and citation management,
enabling traceable references and connection discovery between documents.

Features:
- Cross-document reference tracking
- Citation generation and management
- Reference lineage tracking
- Connection discovery between documents
"""

import time
import hashlib
import json
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from pathlib import Path

from ....datatypes import observability


@dataclass
class DocumentReference:
    """Represents a reference between documents"""

    reference_id: str
    source_document_id: str
    target_document_id: str
    reference_type: str  # "citation", "mention", "related", "dependency"
    context: str  # Text context around the reference
    confidence: float  # 0.0 to 1.0
    page_number: Optional[int]
    section: Optional[str]
    created_at: float
    metadata: Dict[str, Any]


@dataclass
class DocumentConnection:
    """Represents a discovered connection between documents"""

    connection_id: str
    document_ids: List[str]
    connection_type: str  # "thematic", "temporal", "authorial", "procedural"
    strength: float  # 0.0 to 1.0
    description: str
    evidence: List[str]
    discovered_at: float


@dataclass
class CitationStyle:
    """Represents a citation formatting style"""

    style_name: str
    author_format: str
    title_format: str
    date_format: str
    url_format: str
    full_format: str


class DocumentCrossReferenceManager:
    """
    Cross-document reference tracking and citation management system.

    Tracks references between documents, generates citations, and
    discovers connections based on content analysis.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        llm_model=None,
        citation_styles: Optional[Dict[str, CitationStyle]] = None,
    ):
        """
        Initialize the cross reference manager.

        Args:
            storage_path: Path for storing reference data
            llm_model: Language model for connection discovery
            citation_styles: Custom citation styles
        """
        self.storage_path = Path(storage_path) if storage_path else Path(".muxi/references")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.llm_model = llm_model

        # Reference storage
        self._references: Dict[str, DocumentReference] = {}
        self._connections: Dict[str, DocumentConnection] = {}
        # Document ID -> Set of connected document IDs
        self._document_graph: Dict[str, Set[str]] = {}

        # Citation styles
        self.citation_styles = citation_styles or self._default_citation_styles()

        # Load existing data
        self._load_references()

        observability.observe(
            event_type=observability.SystemEvents.CROSS_REFERENCE_MANAGER_INITIALIZED,
            level=observability.EventLevel.DEBUG,
            description=f"Cross-reference manager initialized with storage at {self.storage_path}",
            data={
                "operation": "cross_reference_manager_init",
                "storage_path": str(self.storage_path),
            }
        )

    def _default_citation_styles(self) -> Dict[str, CitationStyle]:
        """Initialize default citation styles"""
        return {
            "apa": CitationStyle(
                style_name="APA",
                author_format="{last}, {first_initial}.",
                title_format="{title}",
                date_format="({year})",
                url_format="Retrieved from {url}",
                full_format="{author} {date}. {title}. {url}",
            ),
            "mla": CitationStyle(
                style_name="MLA",
                author_format="{last}, {first}",
                title_format='"{title}"',
                date_format="{day} {month} {year}",
                url_format="Web. {access_date}",
                full_format="{author}. {title}. {date}. {url}",
            ),
            "chicago": CitationStyle(
                style_name="Chicago",
                author_format="{last}, {first}",
                title_format='"{title}"',
                date_format="{month} {day}, {year}",
                url_format="accessed {access_date}, {url}",
                full_format="{author}. {title}. {date}. {url}",
            ),
        }

    async def add_reference(
        self,
        source_document_id: str,
        target_document_id: str,
        reference_type: str,
        context: str,
        confidence: float = 1.0,
        page_number: Optional[int] = None,
        section: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a reference between two documents.

        Args:
            source_document_id: Document making the reference
            target_document_id: Document being referenced
            reference_type: Type of reference (citation, mention, etc.)
            context: Text context around the reference
            confidence: Confidence in the reference (0.0-1.0)
            page_number: Optional page number
            section: Optional section identifier
            metadata: Optional additional metadata

        Returns:
            Reference ID
        """
        reference_id = self._generate_reference_id(source_document_id, target_document_id, context)

        reference = DocumentReference(
            reference_id=reference_id,
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            reference_type=reference_type,
            context=context,
            confidence=confidence,
            page_number=page_number,
            section=section,
            created_at=time.time(),
            metadata=metadata or {},
        )

        # Store reference
        self._references[reference_id] = reference

        # Update document graph
        if source_document_id not in self._document_graph:
            self._document_graph[source_document_id] = set()
        self._document_graph[source_document_id].add(target_document_id)

        # Save to storage
        await self._save_references()

        observability.observe(
            event_type=observability.SystemEvents.CROSS_REFERENCE_ADDED,
            level=observability.EventLevel.DEBUG,
            description=f"Added cross-reference {reference_id} from {source_document_id} to {target_document_id}",
            data={
                "operation": "add_reference",
                "reference_id": reference_id,
                "source_document_id": source_document_id,
                "target_document_id": target_document_id,
                "reference_type": reference_type,
            }
        )
        return reference_id

    def get_references_for_document(
        self, document_id: str, direction: str = "outgoing"
    ) -> List[DocumentReference]:
        """
        Get all references for a document.

        Args:
            document_id: Document ID
            direction: "outgoing" (references this doc makes) or "incoming" (references to this doc)

        Returns:
            List of DocumentReference objects
        """
        if direction == "outgoing":
            return [
                ref for ref in self._references.values() if ref.source_document_id == document_id
            ]
        elif direction == "incoming":
            return [
                ref for ref in self._references.values() if ref.target_document_id == document_id
            ]
        else:
            # Both directions
            return [
                ref
                for ref in self._references.values()
                if ref.source_document_id == document_id or ref.target_document_id == document_id
            ]

    def _generate_reference_id(self, source_doc_id: str, target_doc_id: str, context: str) -> str:
        """Generate unique reference ID"""
        content = f"{source_doc_id}_{target_doc_id}_{context}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    async def _save_references(self):
        """Save references to storage"""
        try:
            references_file = self.storage_path / "references.json"
            references_data = {
                ref_id: {
                    "reference_id": ref.reference_id,
                    "source_document_id": ref.source_document_id,
                    "target_document_id": ref.target_document_id,
                    "reference_type": ref.reference_type,
                    "context": ref.context,
                    "confidence": ref.confidence,
                    "page_number": ref.page_number,
                    "section": ref.section,
                    "created_at": ref.created_at,
                    "metadata": ref.metadata,
                }
                for ref_id, ref in self._references.items()
            }

            with open(references_file, "w") as f:
                json.dump(references_data, f, indent=2)

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "save_references",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "references_count": len(self._references),
                },
                description="Failed to save document references to storage",
            )

    def _load_references(self):
        """Load references from storage"""
        try:
            references_file = self.storage_path / "references.json"
            if references_file.exists():
                with open(references_file, "r") as f:
                    references_data = json.load(f)

                for ref_id, ref_data in references_data.items():
                    self._references[ref_id] = DocumentReference(**ref_data)

                observability.observe(
                    event_type=observability.SystemEvents.CROSS_REFERENCES_LOADED,
                    level=observability.EventLevel.DEBUG,
                    description=f"Loaded {len(self._references)} document cross-references from storage",
                    data={
                        "operation": "load_references",
                        "references_count": len(self._references),
                    }
                )

            # Rebuild document graph
            self._rebuild_document_graph()

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "load_references",
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to load document references from storage",
            )

    def _rebuild_document_graph(self):
        """Rebuild document graph from references"""
        self._document_graph.clear()

        for ref in self._references.values():
            if ref.source_document_id not in self._document_graph:
                self._document_graph[ref.source_document_id] = set()
            self._document_graph[ref.source_document_id].add(ref.target_document_id)
