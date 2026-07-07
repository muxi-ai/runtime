# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Ingestion Service - Tiered Processing Pipeline
# Description:  Async pipeline behind POST /v1/memories (classify->filter->
#               extract->embed->link->store), riding the event substrate
# Role:         Owns ingestion validation, idempotent accept, and processing
# Usage:        Constructed by the Overlord; driven by the memories API routes
# Author:       Muxi Framework Team
#
# Memory Ingestion Phase 3a. The endpoint is the developer product (PRD:
# "treat the endpoint with the care of a payments API"), so the semantics
# here are exact:
#
# - Accept is event-first and idempotent: every item becomes a
#   memory.ingested event carrying the developer's (source, source_id)
#   idempotency key BEFORE any pipeline stage runs. The substrate's partial
#   unique index guarantees a replayed POST can never create duplicates --
#   it returns the original event (duplicate: true), not an error.
# - Processing is async by default: accept returns fast with a
#   processing_id; a background job (tracked in the shared RequestTracker,
#   pollable via GET /v1/memories/ingestion/{processing_id}) runs the
#   pipeline per item and reports per-stage outcomes plus token usage.
# - The pipeline stages ride existing machinery, never rebuild it:
#   classify = LocalClassifier prototype similarity (no frontier LLM),
#   filter = per-source noise gate (events record filtered dispositions),
#   extract/embed/link/store = the shipped MemoryExtractor + knowledge
#   graph + substrate record/apply paths, exactly as chat extraction uses
#   them. Synthesis (captain's log digests, lessons) picks the results up
#   from the same substrate -- nothing here schedules it.
# - Scope policy mirrors memory namespaces (#215): user scope by default;
#   shared scopes only after the route's memory.write grant check, written
#   event-first like every shared write.
# =============================================================================

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ....formation.background.request_tracker import RequestState, RequestStatus
from ....utils.datetime_utils import utc_now_iso
from ....utils.id_generator import get_default_nanoid
from ... import observability
from ..events.models import (
    EVENT_FACT_EXTRACTED,
    EVENT_GRAPH_EXTRACTED,
    EVENT_INGESTION_FILTERED,
    EVENT_MEMORY_INGESTED,
)
from ..events.projectors import apply_fact_event
from .classification import (
    CATEGORY_UNKNOWN,
    DEFAULT_FILTER_LEVEL,
    FILTER_LEVELS,
    classify_content,
    is_filtered,
)

# Fallback ceiling on concurrently processing ingestion jobs per user.
# One job may carry a whole batch, so this caps background work, not
# item throughput. Overridable via memory.ingestion.max_in_flight_per_user.
DEFAULT_MAX_IN_FLIGHT_PER_USER = 4

# Collection ingested items are stored under when they bypass the
# extractor (shared scopes, or extractor unavailable). Mirrors the
# memories route's shared-scope bookkeeping collection.
INGEST_COLLECTION = "context"

# Length ceilings from the memory_events columns; enforced here so the
# developer gets a precise 422 instead of a database error.
MAX_SOURCE_LENGTH = 50
MAX_SOURCE_ID_LENGTH = 255
MAX_SUBJECT_LENGTH = 255

# Item status vocabulary shared by single, batch, and status responses.
STATUS_ACCEPTED = "accepted"
STATUS_DUPLICATE = "duplicate"
STATUS_INVALID = "invalid"

# Per-item pipeline dispositions reported by the status endpoint.
DISPOSITION_STORED = "stored"
DISPOSITION_FILTERED = "filtered"
DISPOSITION_FAILED = "failed"


class IngestionUnavailableError(Exception):
    """Ingestion requires persistent memory + the memory event substrate."""


class IngestionBusyError(Exception):
    """The per-user in-flight ingestion job cap was reached."""

    def __init__(self, max_in_flight: int):
        super().__init__(
            f"Too many ingestion jobs in flight for this user "
            f"(max {max_in_flight}). Poll GET /v1/memories/ingestion/{{processing_id}} "
            f"until a job completes, then retry; idempotent (source, source_id) "
            f"retries are always safe."
        )
        self.max_in_flight = max_in_flight


@dataclass
class IngestItem:
    """One validated ingestion item, normalized for the pipeline."""

    content: Any  # raw content as submitted (string or structured)
    content_text: str  # string form fed to classify/extract
    source: str
    source_id: Optional[str] = None
    occurred_at: Optional[datetime] = None  # parsed `timestamp` (naive UTC)
    subject: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    scope: Optional[Tuple[str, str]] = None  # None = user scope (default)


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO 8601 timestamp into the substrate's naive-UTC shape.

    Raises ValueError with the original string preserved for the 422.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def validate_item(
    payload: Dict[str, Any], input_validator=None
) -> Tuple[Optional[IngestItem], Optional[str]]:
    """Validate one ingestion item against the contract.

    Args:
        payload: Dict with the contract keys (content, source, source_id,
            timestamp, subject, metadata). Scope authorization happens at
            the route (it needs the formation's permission resolver); the
            resolved scope is attached to the returned item by the caller.
        input_validator: Optional overlord InputValidator enforcing
            max_memory_entry_size.

    Returns:
        (item, None) on success, (None, precise error message) on failure.
    """
    from ....utils.fastjson import json

    source = payload.get("source")
    if not isinstance(source, str) or not source.strip():
        return None, "'source' is required and must be a non-empty string (e.g. \"gmail\")"
    source = source.strip()
    if len(source) > MAX_SOURCE_LENGTH:
        return None, f"'source' must be at most {MAX_SOURCE_LENGTH} characters, got {len(source)}"

    source_id = payload.get("source_id")
    if source_id is not None:
        if not isinstance(source_id, str) or not source_id.strip():
            return None, "'source_id' must be a non-empty string when provided"
        source_id = source_id.strip()
        if len(source_id) > MAX_SOURCE_ID_LENGTH:
            return None, (
                f"'source_id' must be at most {MAX_SOURCE_ID_LENGTH} characters, "
                f"got {len(source_id)}"
            )

    content = payload.get("content")
    if content is None:
        return None, "'content' is required (a string or a structured object)"
    if isinstance(content, str):
        if not content.strip():
            return None, "'content' must not be empty"
        content_text = content
    elif isinstance(content, (dict, list)):
        if not content:
            return None, "'content' must not be empty"
        content_text = json.dumps(content)
    else:
        return None, (
            f"'content' must be a string or a structured object, " f"got {type(content).__name__}"
        )
    if input_validator is not None:
        try:
            input_validator.validate_memory_entry(content_text)
        except ValueError as exc:
            return None, str(exc)

    occurred_at = None
    timestamp = payload.get("timestamp")
    if timestamp is not None:
        if not isinstance(timestamp, str):
            return None, "'timestamp' must be an ISO 8601 string when provided"
        try:
            occurred_at = _parse_timestamp(timestamp)
        except ValueError:
            return None, (
                f"'timestamp' is not valid ISO 8601: {timestamp!r} "
                f'(expected e.g. "2026-07-01T12:00:00Z")'
            )

    subject = payload.get("subject")
    if subject is not None:
        if not isinstance(subject, str) or not subject.strip():
            return None, "'subject' must be a non-empty string when provided"
        subject = subject.strip()
        if len(subject) > MAX_SUBJECT_LENGTH:
            return None, (
                f"'subject' must be at most {MAX_SUBJECT_LENGTH} characters, " f"got {len(subject)}"
            )

    metadata = payload.get("metadata")
    if metadata is None:
        metadata = {}
    elif not isinstance(metadata, dict):
        return None, f"'metadata' must be an object, got {type(metadata).__name__}"

    return (
        IngestItem(
            content=content,
            content_text=content_text,
            source=source,
            source_id=source_id,
            occurred_at=occurred_at,
            subject=subject,
            metadata=dict(metadata),
        ),
        None,
    )


class MemoryIngestionService:
    """Owns the ingestion accept path, in-flight cap, and pipeline job."""

    def __init__(self, overlord):
        self.overlord = overlord
        formation_config = getattr(overlord, "formation_config", None) or {}
        memory_config = formation_config.get("memory") or {}
        config = memory_config.get("ingestion") or {}
        self.sources_config: Dict[str, Any] = config.get("sources") or {}
        try:
            self.max_in_flight = int(
                config.get("max_in_flight_per_user", DEFAULT_MAX_IN_FLIGHT_PER_USER)
            )
        except (TypeError, ValueError):
            self.max_in_flight = DEFAULT_MAX_IN_FLIGHT_PER_USER

        self._in_flight: Dict[str, int] = {}
        self._in_flight_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Configuration surface
    # ------------------------------------------------------------------

    def filter_level(self, source: str) -> str:
        """Per-source noise-gate level; aggressive (strict) by default.

        Config: memory.ingestion.sources.<source>.filter: strict|lenient|off.
        Unknown values fall back to strict rather than failing the item.
        """
        source_config = self.sources_config.get(source)
        if not isinstance(source_config, dict):
            return DEFAULT_FILTER_LEVEL
        level = str(source_config.get("filter", DEFAULT_FILTER_LEVEL)).strip().lower()
        return level if level in FILTER_LEVELS else DEFAULT_FILTER_LEVEL

    # ------------------------------------------------------------------
    # Accept path (validate happens at the route; this is event-first)
    # ------------------------------------------------------------------

    @property
    def memory_events(self):
        return getattr(self.overlord, "memory_events", None)

    def _require_substrate(self):
        memory_events = self.memory_events
        if memory_events is None or not getattr(memory_events, "enabled", False):
            raise IngestionUnavailableError(
                "Memory ingestion requires persistent memory with the memory "
                "event substrate enabled (memory.events.enabled)"
            )
        return memory_events

    async def submit(self, user_id: str, items: List[Tuple[int, IngestItem]]) -> Dict[str, Any]:
        """Accept validated items: append raw events, enqueue processing.

        Args:
            user_id: The authenticated user id.
            items: (original index, validated item) pairs.

        Returns:
            {"processing_id": str|None, "results": {index: per-item dict}}
            where each per-item dict has status accepted|duplicate|invalid
            (invalid only for defensive substrate rejections), the raw
            event's public id, and for duplicates the events already
            derived from the original.

        Raises:
            IngestionUnavailableError: Substrate missing or disabled.
            IngestionBusyError: Per-user in-flight job cap reached.
        """
        memory_events = self._require_substrate()
        user_id = str(user_id)

        # Reserve the job slot BEFORE appending events: if the cap
        # rejected the request after the append, the idempotency key
        # would be burned without any processing ever running.
        await self._acquire_slot(user_id)

        # Ownership-transfer pattern: this coroutine owns the slot release
        # until the processing task has been successfully created. Only
        # then does release responsibility transfer to _process_job's
        # finally -- a failure anywhere before that point (event appends,
        # tracker registration, task creation) releases the slot here, so
        # a transient error can never leak the counter and 429 the user
        # forever.
        slot_owned = True
        results: Dict[int, Dict[str, Any]] = {}
        to_process: List[Tuple[int, IngestItem, Dict[str, Any]]] = []
        try:
            for index, item in items:
                payload: Dict[str, Any] = {"content": item.content}
                if item.metadata:
                    payload["metadata"] = item.metadata
                if item.subject:
                    payload["subject"] = item.subject
                try:
                    event, created = await memory_events.storage.append(
                        user_id=user_id,
                        event_type=EVENT_MEMORY_INGESTED,
                        payload=payload,
                        source=item.source,
                        source_id=item.source_id,
                        occurred_at=item.occurred_at,
                        scope_type=item.scope[0] if item.scope else None,
                        scope_id=item.scope[1] if item.scope else None,
                    )
                except ValueError as exc:
                    # Defensive: route validation should have caught this.
                    results[index] = {"status": STATUS_INVALID, "error": str(exc)}
                    continue

                if created:
                    results[index] = {
                        "status": STATUS_ACCEPTED,
                        "event_id": event["public_id"],
                    }
                    to_process.append((index, item, event))
                else:
                    results[index] = {
                        "status": STATUS_DUPLICATE,
                        "event_id": event["public_id"],
                        "derived_events": await self._derived_events(user_id, event),
                    }

            if not to_process:
                # Nothing new to run: all duplicates/invalid. The finally
                # releases the slot; report without a processing_id.
                return {"processing_id": None, "results": results}

            processing_id = f"ing_{get_default_nanoid()}"
            tracker = self.overlord.request_tracker
            state = RequestState(
                id=processing_id,
                status=RequestStatus.PENDING,
                start_time=time.time(),
                user_id=user_id,
            )
            await tracker.track_request(processing_id, state)
            try:
                task = asyncio.create_task(self._process_job(processing_id, user_id, to_process))
            except BaseException:
                # Don't leave an orphaned queued entry that never runs.
                await tracker.remove_request(processing_id)
                raise
            state.task_ref = task
            # The task now exists: its finally releases the slot.
            slot_owned = False
        finally:
            if slot_owned:
                await self._release_slot(user_id)

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_INGESTION_ACCEPTED,
            level=observability.EventLevel.INFO,
            data={
                "user_id": user_id,
                "processing_id": processing_id,
                "accepted": len(to_process),
                "duplicates": sum(1 for r in results.values() if r["status"] == STATUS_DUPLICATE),
                "sources": sorted({item.source for _, item, _ in to_process}),
            },
            description=f"Memory ingestion accepted {len(to_process)} item(s)",
        )
        return {"processing_id": processing_id, "results": results}

    async def _derived_events(self, user_id: str, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Events the pipeline already derived from a raw ingestion event.

        This is the "original processing result" a replayed POST gets
        back: the fact/graph/disposition events whose caused_by points at
        the original memory.ingested event.
        """
        try:
            memory_events = self.memory_events
            if memory_events is None:
                return []
            events = await memory_events.storage.list_events(user_id, after_id=event["id"])
            return [
                {"event_id": e["public_id"], "event_type": e["event_type"]}
                for e in events
                if e.get("caused_by") == event["id"]
            ]
        except Exception:
            return []  # advisory field; a lookup failure must not fail the accept

    # ------------------------------------------------------------------
    # In-flight cap (simple per-user job counter)
    # ------------------------------------------------------------------

    async def _acquire_slot(self, user_id: str) -> None:
        async with self._in_flight_lock:
            current = self._in_flight.get(user_id, 0)
            if current >= self.max_in_flight:
                raise IngestionBusyError(self.max_in_flight)
            self._in_flight[user_id] = current + 1

    async def _release_slot(self, user_id: str) -> None:
        async with self._in_flight_lock:
            current = self._in_flight.get(user_id, 0)
            if current <= 1:
                self._in_flight.pop(user_id, None)
            else:
                self._in_flight[user_id] = current - 1

    def in_flight(self, user_id: str) -> int:
        """Current in-flight job count for a user (diagnostics/tests)."""
        return self._in_flight.get(str(user_id), 0)

    # ------------------------------------------------------------------
    # Background processing job
    # ------------------------------------------------------------------

    async def _process_job(
        self,
        processing_id: str,
        user_id: str,
        items: List[Tuple[int, IngestItem, Dict[str, Any]]],
    ) -> None:
        """Run the pipeline over one accepted job; never raises."""
        from ....datatypes.observability import RequestContext
        from ...observability.context import set_request_context

        tracker = self.overlord.request_tracker
        # Fresh request context so extraction/embedding token usage
        # accumulates per job -- this is the response's cost attribution.
        request_context = RequestContext(
            id=processing_id,
            user_id=user_id,
            formation_id=getattr(self.overlord, "formation_id", None),
        )
        set_request_context(request_context)

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_INGESTION_STARTED,
            level=observability.EventLevel.INFO,
            data={"user_id": user_id, "processing_id": processing_id, "items": len(items)},
            description=f"Memory ingestion processing started ({len(items)} item(s))",
        )

        try:
            await tracker.update_request(processing_id, RequestStatus.PROCESSING)
            reports: List[Dict[str, Any]] = []
            for index, item, event in items:
                report = await self._process_item(user_id, item, event)
                report["index"] = index
                report["event_id"] = event["public_id"]
                reports.append(report)

            counts = {
                DISPOSITION_STORED: sum(
                    1 for r in reports if r["disposition"] == DISPOSITION_STORED
                ),
                DISPOSITION_FILTERED: sum(
                    1 for r in reports if r["disposition"] == DISPOSITION_FILTERED
                ),
                DISPOSITION_FAILED: sum(
                    1 for r in reports if r["disposition"] == DISPOSITION_FAILED
                ),
            }
            result = {
                "items": reports,
                "counts": counts,
                "usage": request_context.tokens.to_dict(),
                "completed_at": utc_now_iso(),
            }
            await tracker.update_request(processing_id, RequestStatus.COMPLETED, result=result)
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_INGESTION_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "user_id": user_id,
                    "processing_id": processing_id,
                    "counts": counts,
                    "tokens": request_context.tokens.to_dict(),
                },
                description=f"Memory ingestion completed: {counts}",
            )
        except Exception as exc:
            await tracker.update_request(processing_id, RequestStatus.FAILED, error=str(exc))
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_INGESTION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "user_id": user_id,
                    "processing_id": processing_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                description=f"Memory ingestion failed: {exc}",
            )
        finally:
            await self._release_slot(user_id)

    async def _process_item(
        self, user_id: str, item: IngestItem, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run classify -> filter -> extract/store for one item.

        Per-item failures are contained: the job continues and the item
        reports disposition "failed" with the error.
        """
        report: Dict[str, Any] = {"source": item.source, "source_id": item.source_id}
        try:
            # Stage 1: classify (Tier 0/1 -- local prototype similarity,
            # fail-open: triage failure must never drop developer data).
            try:
                classifier = await self._get_classifier()
                category, margin = await classify_content(classifier, item.content_text)
            except Exception as exc:
                category, margin = CATEGORY_UNKNOWN, 0.0
                report["classify_error"] = str(exc)
            report["classification"] = {"category": category, "margin": round(margin, 4)}

            # Stage 2: filter (per-source noise gate).
            level = self.filter_level(item.source)
            report["filter_level"] = level
            if is_filtered(category, level):
                await self._record_filtered(user_id, item, event, category, level)
                report["disposition"] = DISPOSITION_FILTERED
                return report

            # Stages 3-6: extract -> embed -> link -> store, all riding
            # the existing extraction machinery.
            report.update(await self._store_item(user_id, item, event))
            report["disposition"] = DISPOSITION_STORED
            return report
        except Exception as exc:
            report["disposition"] = DISPOSITION_FAILED
            report["error"] = str(exc)
            return report

    async def _get_classifier(self):
        """The shared LocalClassifier (overlord-warmed when available)."""
        getter = getattr(self.overlord, "_get_local_classifier", None)
        if getter is not None:
            return await getter()
        from ...classification import get_classifier

        return await get_classifier()

    async def _record_filtered(
        self, user_id: str, item: IngestItem, event: Dict[str, Any], category: str, level: str
    ) -> None:
        """Record the filtered disposition as an event (audit + replay)."""
        memory_events = self.memory_events
        if memory_events is not None:
            # record() is failure-isolated; a disposition append failure is
            # logged by the substrate and must not fail the item.
            await memory_events.record(
                user_id=user_id,
                event_type=EVENT_INGESTION_FILTERED,
                payload={
                    "category": category,
                    "filter_level": level,
                    "reason": f"category {category!r} is noise at filter level {level!r}",
                },
                source=item.source,
                caused_by=event["id"],
            )
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_INGESTION_FILTERED,
            level=observability.EventLevel.DEBUG,
            data={
                "user_id": user_id,
                "source": item.source,
                "source_id": item.source_id,
                "category": category,
                "filter_level": level,
                "memory_event_id": event["id"],
            },
            description=f"Ingested item filtered as {category} noise",
        )

    async def _store_item(
        self, user_id: str, item: IngestItem, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract/embed/link/store one kept item through existing paths."""
        if item.scope is not None:
            return await self._store_shared(user_id, item, event)

        extractor = getattr(self.overlord, "extractor", None)
        if extractor is None:
            # No extractor configured (auto extraction disabled): store the
            # content verbatim as an event-sourced user-scope fact so the
            # item is still recallable.
            return await self._store_fact(user_id, item, event, scope=None)

        await extractor.process_conversation_turn(
            user_message=item.content_text,
            agent_response="",
            user_id=user_id,
            message_count=extractor.extraction_interval,  # always run for ingestion
            caused_by_event_id=event["id"],
            event_source=item.source,
        )

        # Link pass: the knowledge graph's real-time extraction (entity
        # resolution + relationships) with provenance back to the raw event.
        knowledge_graph = getattr(self.overlord, "knowledge_graph", None)
        if knowledge_graph is not None:
            await knowledge_graph.process_conversation_turn(
                user_message=item.content_text,
                agent_response="",
                user_id=user_id,
                model=getattr(self.overlord, "default_model", None),
                caused_by_event_id=event["id"],
                event_source=item.source,
            )

        derived = await self._derived_events(user_id, event)
        return {
            "facts_extracted": sum(1 for d in derived if d["event_type"] == EVENT_FACT_EXTRACTED),
            "graph_extractions": sum(
                1 for d in derived if d["event_type"] == EVENT_GRAPH_EXTRACTED
            ),
        }

    async def _store_shared(
        self, user_id: str, item: IngestItem, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Shared-scope store: event-first fact write, #215 semantics.

        Conversation-derived LLM extraction stays pinned to user scope
        (memory namespaces write policy), so shared-scope ingestion stores
        the content itself as one grant-checked shared fact -- exactly
        what POST /v1/memories with a scope does today -- with caused_by
        provenance back to the raw ingestion event.
        """
        return await self._store_fact(user_id, item, event, scope=item.scope)

    async def _store_fact(
        self,
        user_id: str,
        item: IngestItem,
        event: Dict[str, Any],
        scope: Optional[Tuple[str, str]],
    ) -> Dict[str, Any]:
        """Event-first verbatim fact write through the shared apply helper."""
        metadata = dict(item.metadata)
        metadata.setdefault("source", item.source)
        metadata["written_by"] = user_id
        if item.subject:
            metadata.setdefault("subject", item.subject)
        payload = {
            "memory": item.content_text,
            "collection": INGEST_COLLECTION,
            "metadata": metadata,
        }
        memory_events = self._require_substrate()
        # No source_id here: the raw memory.ingested event owns the
        # (source, source_id) idempotency key; caused_by carries lineage.
        fact_event = await memory_events.record(
            user_id=user_id,
            event_type=EVENT_FACT_EXTRACTED,
            payload=payload,
            source=item.source,
            caused_by=event["id"],
            scope_type=scope[0] if scope else None,
            scope_id=scope[1] if scope else None,
        )
        if fact_event is None:
            raise IngestionUnavailableError(
                "The memory event substrate rejected the fact append; " "the item was not stored"
            )
        memory_id = await apply_fact_event(
            self.overlord.long_term_memory,
            user_id,
            payload,
            event_id=fact_event["id"],
            scope=scope,
        )
        return {"memory_id": memory_id, "facts_extracted": 1}
