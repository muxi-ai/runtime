# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Projectors - Event-to-Projection Builders
# Description:  Projector registry contract and the three built-in projectors
# Role:         Rebuild derived memory state (KG, log, flat facts) from events
# Usage:        Registered with MemoryEventService during formation init
# Author:       Muxi Framework Team
#
# Memory Event Substrate. A projector owns one projection: it knows which
# event types feed it, how to apply one event, and how to wipe its derived
# state for a user. ``MemoryEventService.rebuild`` drives the contract:
# reset -> replay events in append order -> checkpoint.
#
# Determinism contract: ``apply`` must be a pure function of the event (no
# LLM calls, no clock reads beyond what storage layers stamp identically on
# the incremental path). Every projector routes through the exact same
# storage upserts the live dual-write path uses, so a full replay converges
# to the same state as incremental writes.
#
# Extensibility: adding a projection (e.g. the deferred Knowledge Index) is
# a new class with these three members plus a service.register_projector
# call -- no schema changes to the event log.
# =============================================================================

from typing import Any, Dict, Optional, Tuple

from ..base import SCOPE_TYPE_USER
from .models import (
    EVENT_FACT_EXTRACTED,
    EVENT_GRAPH_EXTRACTED,
    EVENT_LESSON_RECORDED,
    EVENT_LOG_ENTRY,
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
    """Rebuilds kg_entities / kg_relationships from graph.extracted events."""

    name = "knowledge_graph"
    event_types = (EVENT_GRAPH_EXTRACTED,)

    def __init__(self, knowledge_graph_service):
        self.service = knowledge_graph_service

    async def apply(self, event: Dict[str, Any]) -> None:
        """Apply one extraction batch through the service's upsert path."""
        await self.service.apply_extraction(
            event["user_id"], event["payload"], event_id=event["id"]
        )

    async def reset(self, user_id: str) -> None:
        """Wipe the user's graph and invalidate the algorithms cache."""
        await self.service.storage.delete_all_for_user(user_id)
        self.service.algorithms.invalidate(str(user_id))


class CaptainsLogProjector:
    """Rebuilds captains_log(+sources) and lessons from digest events."""

    name = "captains_log"
    event_types = (EVENT_LOG_ENTRY, EVENT_LESSON_RECORDED)

    def __init__(self, captains_log_service):
        self.service = captains_log_service

    async def apply(self, event: Dict[str, Any]) -> None:
        """Apply one log-entry or lesson event through the service."""
        if event["event_type"] == EVENT_LOG_ENTRY:
            await self.service.apply_log_entry_event(
                event["user_id"], event["payload"], event_id=event["id"]
            )
        else:
            await self.service.apply_lesson_event(
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
