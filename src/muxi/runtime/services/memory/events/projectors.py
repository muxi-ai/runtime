# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Projectors - Event-to-Projection Builders
# Description:  Projector registry contract and the four built-in projectors
# Role:         Rebuild derived memory state (KG, log, facts, artifacts)
# Usage:        Registered with MemoryEventService during formation init
# Author:       Muxi Framework Team
#
# Memory Event Substrate. A projector owns one projection: it knows which
# event types feed it, how to apply one event, and how to wipe its derived
# state for a user. ``MemoryEventService.rebuild`` drives the contract:
# reset -> replay events in append order -> checkpoint. The incremental
# path (``project_pending`` / ``apply_event``) drives the same ``apply``
# with a per-(projection, user) cursor instead of a reset.
#
# Determinism contract: ``apply`` must be a pure function of the event (no
# LLM calls, no clock reads beyond what storage layers stamp identically on
# the incremental path). Every projector routes through the exact same
# storage upserts the live dual-write path uses, so a full replay converges
# to the same state as incremental writes. ``apply`` may RETURN information
# (e.g. detected contradictions) -- recording derived events from that
# information is the caller's job on the live path only, never on replay.
#
# Legacy backfill (Phase B): projectors that can synthesize events for
# pre-event-log rows expose ``backfill(user_id, event_service)``. Synthetic
# events carry source='legacy' with a per-row source_id, so the backfill is
# idempotent through the substrate's own (source, source_id) key.
#
# Extensibility: adding a projection (e.g. the deferred Knowledge Index) is
# a new class with these members plus a service.register_projector call --
# no schema changes to the event log.
# =============================================================================

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..base import SCOPE_TYPE_USER
from .models import (
    EVENT_ARTIFACT_SAVED,
    EVENT_ENTITY_RESOLVED,
    EVENT_FACT_EXTRACTED,
    EVENT_GRAPH_EXTRACTED,
    EVENT_LESSON_RECORDED,
    EVENT_LOG_ENTRY,
    SOURCE_ARTIFACT_MEMORY,
    SOURCE_LEGACY,
)

# Metadata key linking a flat-fact memory row back to its originating event
# (the provenance bridge for the vector projection, which has no dedicated
# derived_from column -- metadata is its extension point).
FACT_EVENT_METADATA_KEY = "derived_from_event_id"


def event_scope(event: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Return the ``(scope_type, scope_id)`` a scoped event's projection
    write must carry, or None for the implicit user scope.

    Memory namespaces contract: events record the true scope of the write
    they describe; replay stamps the projection row with that exact scope.
    """
    scope_type = event.get("scope_type")
    if not scope_type or scope_type == SCOPE_TYPE_USER:
        return None
    return (scope_type, event.get("scope_id"))


def contradiction_payloads(result: Any) -> List[Dict[str, Any]]:
    """fact.contradicted payloads for one apply result.

    Shared by the dual-write path (graph service records after its own
    apply) and the incremental applier (records after projecting an
    event) so both stamp identical audit events. Returns [] when the
    result is not a dict or carries no contradictions.
    """
    if not isinstance(result, dict):
        return []
    return list(result.get("contradictions") or [])


async def apply_fact_event(
    long_term_memory,
    user_id: str,
    payload: Dict[str, Any],
    event_id: Optional[int] = None,
    scope: Optional[Tuple[str, str]] = None,
    embedding=None,
) -> str:
    """
    Apply one fact.extracted payload to the flat-fact (vector) projection.

    Shared by the live write paths (extractor, shared-scope API writes,
    distillery intake) and the replay path so both produce byte-identical
    rows. ``scope`` is the memory namespace stamp (None = user scope);
    replay passes the scope recorded on the event. ``embedding`` is an
    optional pre-computed vector (memory distillery ``pre_computed`` mode,
    validated against the formation's model by the caller); when None the
    storage layer embeds on write, which is also what replay does.
    Returns the stored memory id.
    """
    metadata = dict(payload.get("metadata") or {})
    if event_id is not None:
        metadata[FACT_EVENT_METADATA_KEY] = event_id
    # Forward the pre-computed vector only when one was shipped: the
    # keyword stays absent on every other path (extractor, shared-scope
    # writes, replay), which all embed on write.
    kwargs = {"embedding": embedding} if embedding is not None else {}
    return await long_term_memory.add(
        content=payload["memory"],
        metadata=metadata,
        user_id=user_id,
        collection=payload["collection"],
        scope=scope,
        **kwargs,
    )


class KnowledgeGraphProjector:
    """Rebuilds kg_entities / kg_relationships from graph.extracted and
    entity.resolved events (extraction batches + identity merges replay
    in append order, converging to the same merged graph)."""

    name = "knowledge_graph"
    event_types = (EVENT_GRAPH_EXTRACTED, EVENT_ENTITY_RESOLVED)

    def __init__(self, knowledge_graph_service):
        self.service = knowledge_graph_service

    async def apply(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Apply one extraction batch or resolution decision.

        Extraction batches go through the service's upsert path and
        return the apply result (counts + detected contradictions) so
        the live incremental path can record fact.contradicted audit
        events; resolution decisions replay the recorded merge/flag
        exactly (never re-scored). Rebuild replay ignores the return
        value either way.
        """
        if event.get("event_type") == EVENT_ENTITY_RESOLVED:
            return await self.service.apply_entity_resolution(
                event["user_id"], event["payload"], event_id=event["id"]
            )
        return await self.service.apply_extraction(
            event["user_id"], event["payload"], event_id=event["id"]
        )

    async def reset(self, user_id: str) -> None:
        """Wipe the user's graph and invalidate the algorithms cache."""
        await self.service.storage.delete_all_for_user(user_id)
        self.service.algorithms.invalidate(str(user_id))

    async def backfill(self, user_id: str, event_service) -> int:
        """Synthesize graph.extracted events for pre-event-log rows.

        One event per entity/relationship without provenance, keyed
        ``legacy/kg_entity/<public_id>`` / ``legacy/kg_rel/<public_id>``,
        dated to the row's creation. Each synthetic event is applied
        immediately: the upsert merges into the existing row (a no-op for
        content) and stamps its ``derived_from_event_ids`` bridge.
        Returns the number of events synthesized.
        """
        user_id = str(user_id)
        storage = self.service.storage
        synthesized = 0

        entities = await storage.list_entities(user_id, status=None, limit=100000)
        names = {entity["id"]: entity for entity in entities}
        for entity in entities:
            if entity["derived_from_event_ids"]:
                continue
            event = await event_service.record(
                user_id=user_id,
                event_type=EVENT_GRAPH_EXTRACTED,
                payload={
                    "entities": [
                        {
                            "type": entity["type"],
                            "name": entity["name"],
                            "attributes": entity["attributes"],
                            "confidence": entity["confidence"],
                        }
                    ],
                    "relationships": [],
                },
                source=SOURCE_LEGACY,
                source_id=f"legacy/kg_entity/{entity['public_id']}",
                occurred_at=_parse_iso(entity["created_at"]),
            )
            if event is None:
                continue
            await self.apply({"user_id": user_id, "id": event["id"], "payload": event["payload"]})
            synthesized += 1

        for rel in await storage.list_relationships(user_id, status=None, limit=100000):
            if rel["derived_from_event_ids"]:
                continue
            from_entity = names.get(rel["from_entity_id"])
            to_entity = names.get(rel["to_entity_id"])
            if from_entity is None or to_entity is None:
                continue
            event = await event_service.record(
                user_id=user_id,
                event_type=EVENT_GRAPH_EXTRACTED,
                payload={
                    "entities": [],
                    "relationships": [
                        {
                            "from": from_entity["name"],
                            "from_type": from_entity["type"],
                            "to": to_entity["name"],
                            "to_type": to_entity["type"],
                            "type": rel["type"],
                            "attributes": rel["attributes"],
                            "confidence": rel["confidence"],
                        }
                    ],
                },
                source=SOURCE_LEGACY,
                source_id=f"legacy/kg_rel/{rel['public_id']}",
                occurred_at=_parse_iso(rel["created_at"]),
            )
            if event is None:
                continue
            await self.apply({"user_id": user_id, "id": event["id"], "payload": event["payload"]})
            synthesized += 1
        return synthesized


class CaptainsLogProjector:
    """Rebuilds captains_log(+sources) and lessons from digest events."""

    name = "captains_log"
    event_types = (EVENT_LOG_ENTRY, EVENT_LESSON_RECORDED)

    def __init__(self, captains_log_service):
        self.service = captains_log_service

    async def apply(self, event: Dict[str, Any]):
        """Apply one log-entry or lesson event through the service.

        Returns the underlying apply result (entry/source counts or
        lesson/created) so event-first callers can report on the row
        they just wrote; replay ignores the return value.
        """
        if event["event_type"] == EVENT_LOG_ENTRY:
            return await self.service.apply_log_entry_event(
                event["user_id"], event["payload"], event_id=event["id"]
            )
        return await self.service.apply_lesson_event(
            event["user_id"], event["payload"], event_id=event["id"]
        )

    async def reset(self, user_id: str) -> None:
        """Wipe the user's lessons, log entries, and source lineage.

        Lessons go first: their source_log_id FK references captains_log
        rows, so the reverse order would violate the constraint on
        PostgreSQL.
        """
        await self.service.lessons.delete_all_for_user(user_id)
        await self.service.storage.delete_all_for_user(user_id)

    async def backfill(self, user_id: str, event_service) -> int:
        """Synthesize log.entry / lesson.recorded events for legacy rows.

        Entries are keyed ``legacy/captains_log/<public_id>``, lessons
        ``legacy/lesson/<public_id>``; both dated to the row's creation
        and applied immediately to stamp provenance. Returns the number
        of events synthesized.
        """
        user_id = str(user_id)
        synthesized = 0

        entries = await self.service.storage.list_entries(user_id, limit=100000)
        sources = await self.service.storage.get_sources_for_logs([e["id"] for e in entries])
        dates_by_id = {entry["id"]: entry["date"] for entry in entries}
        for entry in entries:
            if entry["derived_from_event_ids"]:
                continue
            event = await event_service.record(
                user_id=user_id,
                event_type=EVENT_LOG_ENTRY,
                payload={
                    "date": entry["date"],
                    "summary": entry["summary"],
                    "decisions": entry["decisions"],
                    "projects": entry["projects"],
                    "context": entry["context"],
                    "sources": [
                        {"source_type": s["source_type"], "source_id": s["source_id"]}
                        for s in sources.get(entry["id"], [])
                    ],
                },
                source=SOURCE_LEGACY,
                source_id=f"legacy/captains_log/{entry['public_id']}",
                occurred_at=_parse_iso(entry["created_at"]),
            )
            if event is None:
                continue
            await self.apply(
                {
                    "user_id": user_id,
                    "id": event["id"],
                    "event_type": EVENT_LOG_ENTRY,
                    "payload": event["payload"],
                }
            )
            synthesized += 1

        for lesson in await self.service.lessons.list_all_for_user(user_id):
            if lesson["derived_from_event_ids"]:
                continue
            event = await event_service.record(
                user_id=user_id,
                event_type=EVENT_LESSON_RECORDED,
                payload={
                    "agent_id": lesson["agent_id"],
                    "rule": lesson["rule"],
                    "context": lesson["context"],
                    "confidence": lesson["confidence"],
                    "source_log_date": dates_by_id.get(lesson["source_log_id"]),
                },
                source=SOURCE_LEGACY,
                source_id=f"legacy/lesson/{lesson['public_id']}",
                occurred_at=_parse_iso(lesson["created_at"]),
            )
            if event is None:
                continue
            await self.apply(
                {
                    "user_id": user_id,
                    "id": event["id"],
                    "event_type": EVENT_LESSON_RECORDED,
                    "payload": event["payload"],
                }
            )
            synthesized += 1
        return synthesized


class FlatFactProjector:
    """Rebuilds extraction-derived flat facts in the vector projection."""

    name = "flat_facts"
    event_types = (EVENT_FACT_EXTRACTED,)

    def __init__(self, long_term_memory):
        self.long_term_memory = long_term_memory

    async def apply(self, event: Dict[str, Any]) -> None:
        """Re-add one extracted fact through the shared write helper.

        The scope recorded on the event is reproduced on the projection
        row, so shared-scope facts replay as shared rows (memory
        namespaces Phases 2+3).
        """
        await apply_fact_event(
            self.long_term_memory,
            event["user_id"],
            event["payload"],
            event_id=event["id"],
            scope=event_scope(event),
        )

    async def reset(self, user_id: str) -> int:
        """
        Delete the user's event-sourced memories.

        Extractor rows (metadata source == 'extraction') and event-derived
        rows (metadata ``derived_from_event_id`` -- e.g. shared-scope API
        writes) are wiped, since replay recreates exactly those. Not
        event-sourced (conversations, knowledge uploads, manually created
        user memories) survives a rebuild.
        Returns the number of memories deleted.
        """
        return await self.long_term_memory.delete_extracted_memories(str(user_id))

    async def backfill(self, user_id: str, event_service) -> int:
        """Synthesize fact.extracted events for pre-event-log extraction rows.

        Keyed ``legacy/memory/<row id>``, dated to the row's creation. The
        rows are NOT re-applied here (the flat-fact write path inserts, it
        does not upsert, so applying would duplicate them); the provenance
        bridge lands on the next rebuild, whose reset already wipes
        extraction rows and whose replay recreates them from these events.
        Returns the number of events synthesized.
        """
        user_id = str(user_id)
        synthesized = 0
        for row in await self.long_term_memory.list_extracted_orphan_memories(user_id):
            source_id = f"legacy/memory/{row['id']}"
            # The row stays orphaned until the next rebuild stamps it, so
            # a re-run sees it again -- the per-row idempotency key keeps
            # the re-run from double-counting (or double-recording).
            existing = await event_service.storage.find_by_source_id(
                user_id, SOURCE_LEGACY, source_id
            )
            if existing is not None:
                continue
            metadata = {
                key: value
                for key, value in (row.get("metadata") or {}).items()
                if key != FACT_EVENT_METADATA_KEY
            }
            event = await event_service.record(
                user_id=user_id,
                event_type=EVENT_FACT_EXTRACTED,
                payload={
                    "memory": row["text"],
                    "collection": row["collection"],
                    "metadata": metadata,
                },
                source=SOURCE_LEGACY,
                source_id=source_id,
                occurred_at=_parse_iso(row.get("created_at")),
            )
            if event is not None:
                synthesized += 1
        return synthesized


class ArtifactMetadataProjector:
    """Rebuilds artifact metadata rows from artifact.saved events.

    The blob is NOT a projection -- it lives in artifact storage and never
    enters the event log. Only the metadata row is derived state: replay
    recreates it (version chain included, because events replay in capture
    order) pointing at the same ``storage_ref``. Rows without a
    ``derived_from_event_id`` (pre-substrate captures) are left alone by
    ``reset`` so a rebuild can never orphan a blob's metadata.
    """

    name = "artifact_metadata"
    event_types = (EVENT_ARTIFACT_SAVED,)

    def __init__(self, artifact_service):
        self.service = artifact_service

    async def apply(self, event: Dict[str, Any]) -> None:
        """Upsert one artifact metadata row from an artifact.saved event.

        Handles every historical payload version: v1 events lack summary
        and compressed size, which are reconstructed deterministically
        (the same helper the capture path used). An existing row (matched
        by public id) is only stamped with provenance -- the artifacts
        table remains authoritative for rows that already exist.
        """
        payload = event["payload"]
        user_id = str(event["user_id"])
        storage = self.service.storage

        existing = await storage.get_by_public_id(
            user_id, payload["artifact_id"], include_deleted=True
        )
        if existing is not None:
            await storage.set_derived_event(existing["id"], event["id"])
            return

        size_bytes = int(payload.get("size_bytes") or 0)
        summary = payload.get("summary") or self.service._build_summary(
            payload["name"], payload["content_type"], size_bytes, event.get("agent_id")
        )
        await storage.save_artifact(
            user_id=user_id,
            public_id=payload["artifact_id"],
            name=payload["name"],
            content_type=payload["content_type"],
            summary=summary,
            storage_ref=payload.get("storage_ref") or "",
            size_bytes=size_bytes,
            compressed_bytes=int(payload.get("compressed_bytes") or size_bytes),
            checksum_sha256=payload.get("checksum_sha256") or "",
            category=payload.get("category"),
            tags=payload.get("tags"),
            agent_id=event.get("agent_id"),
            conversation_id=event.get("conversation_id"),
            expires_at=self.service._compute_expiry(),
            created_at=_parse_iso(event.get("occurred_at")),
            derived_from_event_id=event["id"],
        )

    async def reset(self, user_id: str) -> int:
        """Delete the user's event-sourced metadata rows (blobs untouched).

        Only rows carrying a ``derived_from_event_id`` are wiped: replay
        recreates exactly those. Pre-substrate rows survive until a
        backfill stamps them. Returns the number of rows deleted.
        """
        return await self.service.storage.delete_event_sourced_for_user(str(user_id))

    async def backfill(self, user_id: str, event_service) -> int:
        """Synthesize artifact.saved events for pre-substrate metadata rows.

        Uses the live capture path's ``artifact/<public_id>`` idempotency
        key, so rows that already have an audit event reuse it instead of
        duplicating; either way the row is stamped with its provenance
        bridge. Returns the number of rows stamped.
        """
        user_id = str(user_id)
        stamped = 0
        rows = await self.service.storage.list_artifacts(
            user_id, latest_only=False, include_deleted=True
        )
        for row in rows:
            if row.get("derived_from_event_id") is not None:
                continue
            event = await event_service.record(
                user_id=user_id,
                event_type=EVENT_ARTIFACT_SAVED,
                event_version=2,
                payload={
                    "artifact_id": row["public_id"],
                    "name": row["name"],
                    "version": row["version"],
                    "content_type": row["content_type"],
                    "category": row["category"],
                    "size_bytes": row["size_bytes"],
                    "checksum_sha256": row["checksum_sha256"],
                    "storage_ref": row["storage_ref"],
                    "tags": row["tags"],
                    "summary": row["summary"],
                    "compressed_bytes": row["compressed_bytes"],
                },
                source=SOURCE_ARTIFACT_MEMORY,
                source_id=f"artifact/{row['public_id']}",
                occurred_at=_parse_iso(row["created_at"]),
                agent_id=row["agent_id"],
                conversation_id=row["conversation_id"],
            )
            if event is None:
                continue
            await self.service.storage.set_derived_event(row["id"], event["id"])
            stamped += 1
        return stamped


def _parse_iso(value):
    """Parse an ISO timestamp string to a datetime (passthrough otherwise)."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return value if isinstance(value, datetime) else None
