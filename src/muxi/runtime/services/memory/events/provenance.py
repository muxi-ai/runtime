# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Provenance - "Why Do You Think X?" Query Assembly
# Description:  Resolves projection rows to their event causation chains
# Role:         Read-side provenance surface (Memory Substrate Phase 2c)
# Usage:        Called by the client memory routes and e2e tests
# Author:       Muxi Framework Team
#
# Provenance is the substrate's read-side promise: any knowledge graph
# fact can be traced, in one query surface, back through the events that
# produced it -- typically fact/graph extraction events whose ``caused_by``
# links reach the originating interaction.turn (or raw ingestion event).
#
# The assembly is intentionally projection-first: the caller names an
# entity (the thing the agent "thinks" something about); we collect the
# entity row, every relationship touching it, and each row's
# ``derived_from_event_ids``, then expand every event into its causation
# chain via ``MemoryEventService.provenance_chain``. Decay is applied at
# query time so the answer carries today's effective confidence, not the
# confidence at write time.
# =============================================================================

from typing import Any, Dict, List, Optional

from .decay import DecaySettings, effective_event_confidence, effective_fact_confidence

# Ancestor chains longer than this are cut (defensive; real chains are
# interaction.turn -> extraction -> contradiction, depth 2-3).
MAX_CHAIN_DEPTH = 10


def render_event(event: Dict[str, Any], decay: Optional[DecaySettings] = None) -> Dict[str, Any]:
    """One provenance-facing view of a memory event.

    Exposes the public id (the integer id stays internal), the source
    coordinates, and the query-time effective confidence.
    """
    return {
        "event_id": event["public_id"],
        "event_type": event["event_type"],
        "source": event["source"],
        "source_id": event["source_id"],
        "source_confidence": event["source_confidence"],
        "effective_confidence": round(effective_event_confidence(event, decay), 4),
        "decay_rate": event["decay_rate"],
        "occurred_at": event["occurred_at"],
        "agent_id": event["agent_id"],
        "conversation_id": event["conversation_id"],
        "request_id": event["request_id"],
        "payload": event["payload"],
        "deleted_at": event["deleted_at"],
    }


async def event_chains(
    memory_events,
    user_id: str,
    event_ids: List[int],
    decay: Optional[DecaySettings] = None,
) -> List[List[Dict[str, Any]]]:
    """Causation chains (root-first) for a row's derived event ids."""
    chains = []
    for event_id in event_ids:
        chain = await memory_events.provenance_chain(user_id, event_id, max_depth=MAX_CHAIN_DEPTH)
        if chain:
            chains.append([render_event(event, decay) for event in chain])
    return chains


async def entity_provenance(
    memory_events,
    knowledge_graph,
    user_id: str,
    entity_name: str,
    decay: Optional[DecaySettings] = None,
    limit: int = 25,
) -> Optional[Dict[str, Any]]:
    """
    Full provenance for one knowledge graph entity.

    Returns None when the entity is unknown. Otherwise: the entity (with
    its own event chains) plus every relationship touching it -- any
    status, so contradicted and superseded facts stay explainable --
    each rendered as a statement with stored + effective confidence and
    its event chains.
    """
    user_id = str(user_id)
    entity = await knowledge_graph._find_entity_by_name(user_id, entity_name)
    if entity is None:
        return None

    facts: List[Dict[str, Any]] = []
    seen_ids = set()
    outgoing = await knowledge_graph.storage.list_relationships(
        user_id, from_entity_id=entity["id"], status=None, limit=limit
    )
    incoming = await knowledge_graph.storage.list_relationships(
        user_id, to_entity_id=entity["id"], status=None, limit=limit
    )
    for rel in list(outgoing) + list(incoming):
        if rel["id"] in seen_ids:
            continue
        seen_ids.add(rel["id"])
        from_entity = await knowledge_graph.storage.get_entity_by_id(rel["from_entity_id"])
        to_entity = await knowledge_graph.storage.get_entity_by_id(rel["to_entity_id"])
        facts.append(
            {
                "statement": (
                    f"{from_entity['name'] if from_entity else '?'} "
                    f"-[{rel['type']}]-> "
                    f"{to_entity['name'] if to_entity else '?'}"
                ),
                "relationship_type": rel["type"],
                "status": rel["status"],
                "confidence": rel["confidence"],
                "effective_confidence": round(effective_fact_confidence(rel, decay), 4),
                "updated_at": rel["updated_at"],
                "events": await event_chains(
                    memory_events, user_id, rel["derived_from_event_ids"], decay
                ),
            }
        )

    return {
        "entity": {
            "name": entity["name"],
            "type": entity["type"],
            "status": entity["status"],
            "confidence": entity["confidence"],
            "attributes": entity["attributes"],
            "events": await event_chains(
                memory_events, user_id, entity["derived_from_event_ids"], decay
            ),
        },
        "facts": facts,
        "count": len(facts),
    }


async def event_provenance(
    memory_events,
    user_id: str,
    public_event_id: str,
    decay: Optional[DecaySettings] = None,
) -> Optional[Dict[str, Any]]:
    """Causation chain for one event addressed by its public id."""
    user_id = str(user_id)
    event = await memory_events.storage.get_event_by_public_id(user_id, public_event_id)
    if event is None:
        return None
    chain = await memory_events.provenance_chain(user_id, event["id"], max_depth=MAX_CHAIN_DEPTH)
    return {
        "event": render_event(event, decay),
        "chain": [render_event(item, decay) for item in chain],
    }
