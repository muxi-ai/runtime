"""
Document Context Preserver Implementation

This module implements context preservation mechanisms to maintain document context
across conversations and interactions, ensuring consistent understanding.

Features:
- Context preservation across conversations
- Document-specific context tracking
- Conversation history with document awareness
- Context relevance scoring
"""

import time
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

from ....datatypes import observability


@dataclass
class DocumentContext:
    """Represents document context information"""

    document_id: str
    title: str
    summary: str
    key_concepts: List[str]
    last_accessed: float
    access_count: int
    relevance_score: float
    conversation_references: List[str]
    metadata: Dict[str, Any]


@dataclass
class ConversationContext:
    """Represents conversation context with document awareness"""

    conversation_id: str
    user_id: str
    documents_referenced: List[str]
    context_summary: str
    key_topics: List[str]
    start_time: float
    last_update: float
    message_count: int
    active_document_context: Optional[str]


@dataclass
class ContextSnapshot:
    """Represents a preserved context snapshot"""

    snapshot_id: str
    conversation_id: str
    document_contexts: List[DocumentContext]
    conversation_state: str
    preserved_at: float
    expires_at: Optional[float]
    metadata: Dict[str, Any]


class DocumentContextPreserver:
    """
    Document context preservation system.

    Maintains context across conversations and document interactions,
    ensuring consistent understanding and relevant document awareness.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        llm_model=None,
        context_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the document context preserver.

        Args:
            storage_path: Path for storing context data
            llm_model: Language model for context analysis
            context_config: Context preservation configuration
        """
        self.storage_path = Path(storage_path) if storage_path else Path(".muxi/context")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.llm_model = llm_model
        self.context_config = context_config or {}

        # Context storage
        self._document_contexts: Dict[str, DocumentContext] = {}
        self._conversation_contexts: Dict[str, ConversationContext] = {}
        self._context_snapshots: Dict[str, ContextSnapshot] = {}

        # Access tracking
        self._document_access_history: Dict[str, List[float]] = defaultdict(list)
        self._conversation_document_map: Dict[str, List[str]] = defaultdict(list)

        # Configuration
        self.max_context_age = self.context_config.get("max_context_age", 3600 * 24)  # 24 hours
        self.max_snapshots = self.context_config.get("max_snapshots", 100)
        self.relevance_threshold = self.context_config.get("relevance_threshold", 0.5)

        # Load existing data
        self._load_contexts()

        #     f"Initialized DocumentContextPreserver with storage at {self.storage_path}"
        # )

    async def preserve_document_context(
        self,
        document_id: str,
        document_title: str,
        document_summary: str,
        conversation_id: str,
        user_id: str,
        key_concepts: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Preserve context for a document.

        Args:
            document_id: Unique document identifier
            document_title: Document title
            document_summary: Document summary or excerpt
            conversation_id: Current conversation ID
            user_id: User ID
            key_concepts: Key concepts from the document
            metadata: Additional metadata

        Returns:
            Context ID
        """
        current_time = time.time()

        # Update or create document context
        if document_id in self._document_contexts:
            doc_context = self._document_contexts[document_id]
            doc_context.last_accessed = current_time
            doc_context.access_count += 1
            doc_context.conversation_references.append(conversation_id)
        else:
            doc_context = DocumentContext(
                document_id=document_id,
                title=document_title,
                summary=document_summary,
                key_concepts=key_concepts or [],
                last_accessed=current_time,
                access_count=1,
                relevance_score=1.0,
                conversation_references=[conversation_id],
                metadata=metadata or {},
            )
            self._document_contexts[document_id] = doc_context

        # Track access history
        self._document_access_history[document_id].append(current_time)
        self._conversation_document_map[conversation_id].append(document_id)

        # Update conversation context
        await self._update_conversation_context(conversation_id, user_id, document_id)

        # Calculate relevance score
        doc_context.relevance_score = self._calculate_relevance_score(document_id)

        # Save contexts
        await self._save_contexts()

        #     f"Preserved context for document {document_id} in conversation {conversation_id}"
        # )
        return document_id

    async def get_relevant_context(
        self, conversation_id: str, query: Optional[str] = None, limit: int = 5
    ) -> List[DocumentContext]:
        """
        Get relevant document context for a conversation.

        Args:
            conversation_id: Conversation ID
            query: Optional query to filter contexts
            limit: Maximum number of contexts to return

        Returns:
            List of relevant DocumentContext objects
        """
        # Get documents referenced in this conversation
        conversation_documents = self._conversation_document_map.get(conversation_id, [])

        if not conversation_documents:
            # Return most recently accessed relevant documents
            recent_contexts = sorted(
                self._document_contexts.values(),
                key=lambda x: (x.relevance_score, x.last_accessed),
                reverse=True,
            )
            return recent_contexts[:limit]

        # Get contexts for conversation documents
        contexts = []
        for doc_id in conversation_documents:
            if doc_id in self._document_contexts:
                contexts.append(self._document_contexts[doc_id])

        # Filter by query if provided
        if query and self.llm_model:
            contexts = await self._filter_contexts_by_query(contexts, query)

        # Sort by relevance and recency
        contexts.sort(key=lambda x: (x.relevance_score, x.last_accessed), reverse=True)

        return contexts[:limit]

    async def create_context_snapshot(
        self,
        conversation_id: str,
        snapshot_metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[float] = None,
    ) -> str:
        """
        Create a snapshot of current context.

        Args:
            conversation_id: Conversation to snapshot
            snapshot_metadata: Additional snapshot metadata
            expires_at: Optional expiration timestamp

        Returns:
            Snapshot ID
        """
        current_time = time.time()
        snapshot_id = f"snapshot_{conversation_id}_{int(current_time)}"

        # Get conversation documents
        conversation_docs = self._conversation_document_map.get(conversation_id, [])
        doc_contexts = [
            self._document_contexts[doc_id]
            for doc_id in conversation_docs
            if doc_id in self._document_contexts
        ]

        # Get conversation state
        conversation_state = ""
        if conversation_id in self._conversation_contexts:
            conv_context = self._conversation_contexts[conversation_id]
            conversation_state = (
                f"Topics: {', '.join(conv_context.key_topics)}\n"
                f"Summary: {conv_context.context_summary}"
            )

        # Create snapshot
        snapshot = ContextSnapshot(
            snapshot_id=snapshot_id,
            conversation_id=conversation_id,
            document_contexts=doc_contexts,
            conversation_state=conversation_state,
            preserved_at=current_time,
            expires_at=expires_at,
            metadata=snapshot_metadata or {},
        )

        self._context_snapshots[snapshot_id] = snapshot

        # Cleanup old snapshots
        await self._cleanup_snapshots()

        # Save snapshots
        await self._save_snapshots()

        return snapshot_id

    async def restore_context_snapshot(self, snapshot_id: str) -> Optional[ContextSnapshot]:
        """
        Restore a context snapshot.

        Args:
            snapshot_id: Snapshot ID to restore

        Returns:
            ContextSnapshot object if found and valid
        """
        if snapshot_id not in self._context_snapshots:
            return None

        snapshot = self._context_snapshots[snapshot_id]

        # Check if snapshot has expired
        if snapshot.expires_at and time.time() > snapshot.expires_at:
            del self._context_snapshots[snapshot_id]
            await self._save_snapshots()
            return None

        # Restore document contexts
        for doc_context in snapshot.document_contexts:
            self._document_contexts[doc_context.document_id] = doc_context

        return snapshot

    def get_context_statistics(self) -> Dict[str, Any]:
        """Get statistics about preserved contexts"""
        current_time = time.time()

        # Document statistics
        total_documents = len(self._document_contexts)
        active_documents = sum(
            1
            for ctx in self._document_contexts.values()
            if current_time - ctx.last_accessed < self.max_context_age
        )

        # Conversation statistics
        total_conversations = len(self._conversation_contexts)
        active_conversations = sum(
            1
            for ctx in self._conversation_contexts.values()
            if current_time - ctx.last_update < self.max_context_age
        )

        # Access statistics
        total_accesses = sum(ctx.access_count for ctx in self._document_contexts.values())
        avg_accesses = total_accesses / max(total_documents, 1)

        # Relevance statistics
        if self._document_contexts:
            total_relevance = sum(ctx.relevance_score for ctx in self._document_contexts.values())
            avg_relevance = total_relevance / total_documents
            high_relevance_docs = sum(
                1
                for ctx in self._document_contexts.values()
                if ctx.relevance_score > self.relevance_threshold
            )
        else:
            avg_relevance = 0.0
            high_relevance_docs = 0

        return {
            "total_documents": total_documents,
            "active_documents": active_documents,
            "total_conversations": total_conversations,
            "active_conversations": active_conversations,
            "total_snapshots": len(self._context_snapshots),
            "total_accesses": total_accesses,
            "avg_accesses_per_document": avg_accesses,
            "avg_relevance_score": avg_relevance,
            "high_relevance_documents": high_relevance_docs,
            "context_age_hours": self.max_context_age / 3600,
        }

    async def _update_conversation_context(
        self, conversation_id: str, user_id: str, document_id: str
    ):
        """Update conversation context with document information"""
        current_time = time.time()

        if conversation_id in self._conversation_contexts:
            conv_context = self._conversation_contexts[conversation_id]
            conv_context.last_update = current_time
            conv_context.message_count += 1
            if document_id not in conv_context.documents_referenced:
                conv_context.documents_referenced.append(document_id)
            conv_context.active_document_context = document_id
        else:
            # Get document info for context summary
            doc_context = self._document_contexts.get(document_id)
            context_summary = f"Discussing document: {doc_context.title}" if doc_context else ""
            key_topics = doc_context.key_concepts if doc_context else []

            conv_context = ConversationContext(
                conversation_id=conversation_id,
                user_id=user_id,
                documents_referenced=[document_id],
                context_summary=context_summary,
                key_topics=key_topics,
                start_time=current_time,
                last_update=current_time,
                message_count=1,
                active_document_context=document_id,
            )
            self._conversation_contexts[conversation_id] = conv_context

    def _calculate_relevance_score(self, document_id: str) -> float:
        """Calculate relevance score for a document"""
        if document_id not in self._document_contexts:
            return 0.0

        doc_context = self._document_contexts[document_id]
        current_time = time.time()

        # Base score from access count
        access_score = min(doc_context.access_count / 10.0, 1.0)

        # Recency score (more recent = higher score)
        time_diff = current_time - doc_context.last_accessed
        recency_score = max(0.0, 1.0 - (time_diff / self.max_context_age))

        # Conversation reference score
        reference_score = min(len(doc_context.conversation_references) / 5.0, 1.0)

        # Combined score (weighted average)
        relevance_score = access_score * 0.3 + recency_score * 0.4 + reference_score * 0.3

        return min(relevance_score, 1.0)

    async def _filter_contexts_by_query(
        self, contexts: List[DocumentContext], query: str
    ) -> List[DocumentContext]:
        """Filter contexts based on query relevance"""
        if not self.llm_model:
            return contexts

        try:
            # Create analysis prompt
            context_summaries = []
            for i, ctx in enumerate(contexts):
                context_summaries.append(f"{i}: {ctx.title} - {ctx.summary}")

            filter_prompt = f"""
            Query: {query}

            Document contexts:
            {chr(10).join(context_summaries)}

            Return the indices (comma-separated) of documents most relevant to the query.
            Only include documents with high relevance.
            """

            response = await self.llm_model.generate_response(filter_prompt)

            # Parse response to get relevant indices
            relevant_indices = []
            for part in response.split(","):
                try:
                    idx = int(part.strip())
                    if 0 <= idx < len(contexts):
                        relevant_indices.append(idx)
                except ValueError:
                    continue

            return [contexts[i] for i in relevant_indices]

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "select_relevant_contexts",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "contexts_count": len(contexts),
                },
                description="Failed to select relevant contexts using LLM",
            )
            return contexts

    async def _cleanup_snapshots(self):
        """Clean up expired and excess snapshots"""
        current_time = time.time()

        # Remove expired snapshots
        expired_snapshots = [
            snapshot_id
            for snapshot_id, snapshot in self._context_snapshots.items()
            if snapshot.expires_at and current_time > snapshot.expires_at
        ]

        for snapshot_id in expired_snapshots:
            del self._context_snapshots[snapshot_id]

        # Remove oldest snapshots if over limit
        if len(self._context_snapshots) > self.max_snapshots:
            sorted_snapshots = sorted(
                self._context_snapshots.items(), key=lambda x: x[1].preserved_at
            )

            excess_count = len(self._context_snapshots) - self.max_snapshots
            for i in range(excess_count):
                snapshot_id = sorted_snapshots[i][0]
                del self._context_snapshots[snapshot_id]

    async def _save_contexts(self):
        """Save document and conversation contexts to storage"""
        try:
            # Save document contexts
            doc_contexts_file = self.storage_path / "document_contexts.json"
            doc_contexts_data = {
                doc_id: {
                    "document_id": ctx.document_id,
                    "title": ctx.title,
                    "summary": ctx.summary,
                    "key_concepts": ctx.key_concepts,
                    "last_accessed": ctx.last_accessed,
                    "access_count": ctx.access_count,
                    "relevance_score": ctx.relevance_score,
                    "conversation_references": ctx.conversation_references,
                    "metadata": ctx.metadata,
                }
                for doc_id, ctx in self._document_contexts.items()
            }

            with open(doc_contexts_file, "w") as f:
                json.dump(doc_contexts_data, f, indent=2)

            # Save conversation contexts
            conv_contexts_file = self.storage_path / "conversation_contexts.json"
            conv_contexts_data = {
                conv_id: {
                    "conversation_id": ctx.conversation_id,
                    "user_id": ctx.user_id,
                    "documents_referenced": ctx.documents_referenced,
                    "context_summary": ctx.context_summary,
                    "key_topics": ctx.key_topics,
                    "start_time": ctx.start_time,
                    "last_update": ctx.last_update,
                    "message_count": ctx.message_count,
                    "active_document_context": ctx.active_document_context,
                }
                for conv_id, ctx in self._conversation_contexts.items()
            }

            with open(conv_contexts_file, "w") as f:
                json.dump(conv_contexts_data, f, indent=2)

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "save_conversation_contexts",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "contexts_count": len(self._conversation_contexts),
                },
                description="Failed to save conversation contexts to storage",
            )

    async def _save_snapshots(self):
        """Save context snapshots to storage"""
        try:
            snapshots_file = self.storage_path / "context_snapshots.json"
            snapshots_data = {
                snap_id: {
                    "snapshot_id": snap.snapshot_id,
                    "conversation_id": snap.conversation_id,
                    "document_contexts": [
                        {
                            "document_id": ctx.document_id,
                            "title": ctx.title,
                            "summary": ctx.summary,
                            "key_concepts": ctx.key_concepts,
                            "last_accessed": ctx.last_accessed,
                            "access_count": ctx.access_count,
                            "relevance_score": ctx.relevance_score,
                            "conversation_references": ctx.conversation_references,
                            "metadata": ctx.metadata,
                        }
                        for ctx in snap.document_contexts
                    ],
                    "conversation_state": snap.conversation_state,
                    "preserved_at": snap.preserved_at,
                    "expires_at": snap.expires_at,
                    "metadata": snap.metadata,
                }
                for snap_id, snap in self._context_snapshots.items()
            }

            with open(snapshots_file, "w") as f:
                json.dump(snapshots_data, f, indent=2)

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "save_context_snapshots",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "snapshots_count": len(self._context_snapshots),
                },
                description="Failed to save context snapshots to storage",
            )

    def _load_contexts(self):
        """Load contexts from storage"""
        try:
            # Load document contexts
            doc_contexts_file = self.storage_path / "document_contexts.json"
            if doc_contexts_file.exists():
                with open(doc_contexts_file, "r") as f:
                    doc_contexts_data = json.load(f)

                for doc_id, ctx_data in doc_contexts_data.items():
                    self._document_contexts[doc_id] = DocumentContext(**ctx_data)

            # Load conversation contexts
            conv_contexts_file = self.storage_path / "conversation_contexts.json"
            if conv_contexts_file.exists():
                with open(conv_contexts_file, "r") as f:
                    conv_contexts_data = json.load(f)

                for conv_id, ctx_data in conv_contexts_data.items():
                    self._conversation_contexts[conv_id] = ConversationContext(**ctx_data)

            # Load snapshots
            snapshots_file = self.storage_path / "context_snapshots.json"
            if snapshots_file.exists():
                with open(snapshots_file, "r") as f:
                    snapshots_data = json.load(f)

                for snap_id, snap_data in snapshots_data.items():
                    # Reconstruct document contexts
                    doc_contexts = [
                        DocumentContext(**ctx_data) for ctx_data in snap_data["document_contexts"]
                    ]
                    snap_data["document_contexts"] = doc_contexts

                    self._context_snapshots[snap_id] = ContextSnapshot(**snap_data)

            # Rebuild access maps
            for conv_id, ctx in self._conversation_contexts.items():
                self._conversation_document_map[conv_id] = ctx.documents_referenced

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "load_contexts",
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to load context data from storage",
            )
