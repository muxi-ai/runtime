# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Graph Service - Structured Memory Coordination
# Description:  Real-time and periodic graph extraction plus graph queries
# Role:         Formation-level service owning the knowledge graph lifecycle
# Usage:        Created in formation initialization, driven by the Overlord
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 1 (Knowledge Graph Foundation). Coordinates:
#
# 1. Real-time extraction: rides the existing extraction coordinator, one
#    high-confidence (0.9) pass per conversation turn, upserted immediately.
# 2. Periodic extraction: a background loop that re-processes the recent
#    turns accumulated since the last run with full multi-turn context at a
#    lower confidence threshold (0.7).
# 3. Graph queries: 1-hop context blocks, multi-hop exploration via the
#    backend-specific GraphAlgorithms layer, and path explanation rendering
#    ("A -[rel]-> B -[rel]-> C").
#
# Every public entry point is failure-isolated: extraction errors are logged
# and swallowed so the chat turn is never affected.
# =============================================================================

import asyncio
import re
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from sqlalchemy import text

from ... import observability
from ..events.models import EVENT_GRAPH_EXTRACTED, SOURCE_INTERACTION, SOURCE_PERIODIC
from .algorithms import NetworkXAlgorithms, PgRoutingAlgorithms
from .extractor import USER_ENTITY_NAME, USER_ENTITY_TYPE, KnowledgeGraphExtractor
from .storage import KnowledgeGraphStorage, normalize_type

# PRD defaults (Configuration Reference -> memory.graph).
DEFAULT_REALTIME_CONFIDENCE = 0.9
DEFAULT_PERIODIC_CONFIDENCE = 0.7
DEFAULT_PERIODIC_SCHEDULE = "hourly"

# Bound on turns buffered per user between periodic runs.
MAX_PENDING_TURNS_PER_USER = 50

_SCHEDULE_SECONDS = {"hourly": 3600, "daily": 86400}

# Context rendering: how many entities the attribute scan may consider
# (matches the topic-match scan window) and the hard per-line clip that
# keeps one verbose attribute from eating the context block.
ENTITY_SCAN_LIMIT = 200
MAX_ATTRIBUTE_LINE_CHARS = 200

# Attribute keys written by internal graph machinery (entity-resolution
# review flags), never user facts -- excluded from context rendering.
INTERNAL_ATTRIBUTE_KEYS = frozenset({"possible_duplicates"})


class KnowledgeGraphService:
    """Owns knowledge graph storage, extraction, and query surface."""

    def __init__(
        self,
        db_manager,
        formation_id: str,
        config: Optional[Dict[str, Any]] = None,
        event_log=None,
        decay=None,
    ):
        """
        Initialize the knowledge graph service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all graph rows.
            config: The ``memory.graph`` formation config section.
            event_log: MemoryEventService (or None). When present, every
                extraction batch is appended to the memory event log before
                the projection write (dual-write; append failures are
                isolated inside the event service and never block the
                graph write). With ``memory.events.event_first`` enabled
                the direct write is skipped and the substrate's applier
                projects the event instead.
            decay: DecaySettings (or None). When present, context-block
                ranking weights fact confidence by age at query time for
                relationship types with a configured half-life
                (memory.decay.half_lives).
        """
        config = config or {}
        extraction_config = config.get("extraction") or {}

        self.formation_id = formation_id
        self.enabled = config.get("enabled", True)
        self.realtime_enabled = extraction_config.get("realtime", True)
        self.realtime_confidence = float(
            extraction_config.get("realtime_confidence", DEFAULT_REALTIME_CONFIDENCE)
        )
        self.periodic_enabled = extraction_config.get("periodic", True)
        self.periodic_confidence = float(
            extraction_config.get("periodic_confidence", DEFAULT_PERIODIC_CONFIDENCE)
        )
        self.periodic_interval_seconds = _schedule_to_seconds(
            extraction_config.get("periodic_schedule", DEFAULT_PERIODIC_SCHEDULE)
        )

        self.db_manager = db_manager
        self.storage = KnowledgeGraphStorage(db_manager, formation_id)
        self.extractor = KnowledgeGraphExtractor(confidence_threshold=self.realtime_confidence)
        self.event_log = event_log
        self.decay = decay

        # Backend selection: pgRouting on PostgreSQL when the extension is
        # installable, NetworkX on SQLite and as the safe fallback when the
        # extension is unavailable on a managed instance.
        self.pgrouting_available = False
        if db_manager.database_type == "postgresql":
            self.pgrouting_available = self._ensure_pgrouting_extension()
        if self.pgrouting_available:
            self.algorithms = PgRoutingAlgorithms(db_manager, formation_id)
        else:
            self.algorithms = NetworkXAlgorithms(self.storage)

        # Turns accumulated per user since the last periodic run.
        self._pending_turns: Dict[str, Deque[str]] = {}
        self._periodic_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _ensure_pgrouting_extension(self) -> bool:
        """Best-effort ``CREATE EXTENSION pgrouting`` on the Postgres backend."""
        try:
            with self.db_manager.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting CASCADE"))
                conn.commit()
            return True
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_EXTENSION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "extension": "pgrouting"},
                description=(
                    "pgrouting extension unavailable - knowledge graph algorithms "
                    "fall back to NetworkX"
                ),
            )
            return False

    # ------------------------------------------------------------------
    # Real-time extraction
    # ------------------------------------------------------------------

    async def process_conversation_turn(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        model,
        caused_by_event_id: Optional[int] = None,
        event_source: Optional[str] = None,
    ) -> None:
        """
        Run the real-time graph extraction pass for one conversation turn.

        Never raises: extraction or storage failures are logged and the
        chat turn continues unaffected. ``caused_by_event_id`` links the
        recorded graph.extracted event to its interaction.turn event.
        ``event_source`` overrides the source stamped on that event
        (default: interaction; the ingestion pipeline passes the
        developer's source so graph provenance carries the true origin).
        """
        if not self.enabled or model is None:
            return

        conversation = _format_turn(user_message, agent_response)
        if self.periodic_enabled:
            self._queue_turn(user_id, conversation)

        if not self.realtime_enabled:
            return

        try:
            result = await self.extractor.extract(
                conversation, model, confidence_threshold=self.realtime_confidence
            )
            stored = await self.store_extraction(
                user_id,
                result,
                source=event_source or SOURCE_INTERACTION,
                caused_by=caused_by_event_id,
            )
            if stored["entities"] or stored["relationships"]:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_AUTO_EXTRACTED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "user_id": str(user_id),
                        "pass": "realtime",
                        "entities": stored["entities"],
                        "relationships": stored["relationships"],
                    },
                    description=(
                        f"Knowledge graph extraction stored {stored['entities']} entities "
                        f"and {stored['relationships']} relationships"
                    ),
                )
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_AUTO_EXTRACTION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "user_id": str(user_id),
                    "pass": "realtime",
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Knowledge graph real-time extraction failed: {e}",
            )

    async def store_extraction(
        self,
        user_id: Any,
        result: Dict[str, List[Dict[str, Any]]],
        source: str = SOURCE_INTERACTION,
        caused_by: Optional[int] = None,
    ) -> Dict[str, int]:
        """Record and persist an extraction result (dual-write path).

        Public entry point for the built-in extraction passes and the
        Captain's Log digest integration. Appends a ``graph.extracted``
        event to the memory event log first (failure-isolated inside the
        event service), then applies the same result through the upsert
        path the replay rebuild uses. With ``memory.events.event_first``
        enabled and the event durably appended, the direct apply is
        skipped -- the substrate's applier projects the event (Phase C
        cutover semantics, flag-gated, default off).

        Contradictions detected during the apply are recorded as
        ``fact.contradicted`` audit events linked to the extraction event.
        """
        event = None
        if self.event_log is not None and (result.get("entities") or result.get("relationships")):
            event = await self.event_log.record(
                user_id=str(user_id),
                event_type=EVENT_GRAPH_EXTRACTED,
                payload={
                    "entities": result.get("entities", []),
                    "relationships": result.get("relationships", []),
                },
                source=source,
                caused_by=caused_by,
            )
            if event is not None and self.event_log.event_first:
                # Event-first cutover: the append is the write; the
                # incremental applier derives the projection (and records
                # the contradiction audit events) from the event.
                await self.event_log.apply_event(event)
                return {
                    "entities": len(result.get("entities", [])),
                    "relationships": len(result.get("relationships", [])),
                }
        stored = await self.apply_extraction(
            user_id, result, event_id=event["id"] if event else None
        )
        if event is not None and stored.get("contradictions"):
            await self.event_log.record_contradictions(event, stored)
        return stored

    async def apply_extraction(
        self,
        user_id: Any,
        result: Dict[str, List[Dict[str, Any]]],
        event_id: Optional[int] = None,
    ) -> Dict[str, int]:
        """Persist one extraction result; returns stored counts.

        Deterministic projection write shared by the live dual-write path
        and the event-replay rebuild: given the same result batches in the
        same order it converges to the same graph state. Contradictions
        detected by the storage layer are returned under the
        ``contradictions`` key (only when any occurred) so the LIVE caller
        can record fact.contradicted audit events -- this method itself
        never writes to the event log, keeping replay pure.
        """
        user_id = str(user_id)
        entity_ids: Dict[Tuple[str, str], int] = {}
        stored_entities = 0
        stored_relationships = 0
        contradictions: List[Dict[str, Any]] = []

        for item in result.get("entities", []):
            entity = await self.storage.upsert_entity(
                user_id=user_id,
                entity_type=item["type"],
                name=item["name"],
                attributes=item.get("attributes"),
                confidence=item["confidence"],
                event_id=event_id,
            )
            entity_ids[(entity["type"], _name_key(entity["name"]))] = entity["id"]
            stored_entities += 1

        for item in result.get("relationships", []):
            from_id = await self._resolve_endpoint(
                user_id,
                item["from"],
                item.get("from_type"),
                item["confidence"],
                entity_ids,
                event_id,
            )
            to_id = await self._resolve_endpoint(
                user_id, item["to"], item.get("to_type"), item["confidence"], entity_ids, event_id
            )
            if from_id is None or to_id is None or from_id == to_id:
                continue
            stored = await self.storage.upsert_relationship(
                user_id=user_id,
                from_entity_id=from_id,
                to_entity_id=to_id,
                rel_type=item["type"],
                attributes=item.get("attributes"),
                confidence=item["confidence"],
                event_id=event_id,
            )
            contradictions.extend(stored.get("contradictions") or [])
            stored_relationships += 1

        if stored_entities or stored_relationships:
            self.algorithms.invalidate(user_id)

        result_counts: Dict[str, Any] = {
            "entities": stored_entities,
            "relationships": stored_relationships,
        }
        if contradictions:
            result_counts["contradictions"] = contradictions
        return result_counts

    async def apply_entity_resolution(
        self,
        user_id: Any,
        payload: Dict[str, Any],
        event_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply one entity.resolved decision (live path and replay).

        A pure function of the payload (Memory Ingestion maturation):
        entities are addressed by their (type, name) natural key, so
        replaying the recorded decision on a rebuilt graph converges to
        the same merged state. Missing entities (e.g. their source events
        were forgotten) make the apply a no-op rather than an error.
        """
        user_id = str(user_id)
        from .resolution import DECISION_MERGED

        entity_type = normalize_type(payload["entity_type"])
        canonical = await self.storage.get_entity(user_id, entity_type, payload["canonical_name"])
        duplicate = await self.storage.get_entity(user_id, entity_type, payload["duplicate_name"])
        if canonical is None or duplicate is None or canonical["id"] == duplicate["id"]:
            return {"applied": False}

        if payload["decision"] == DECISION_MERGED:
            result = await self.storage.merge_entities(
                user_id, canonical["id"], duplicate["id"], event_id=event_id
            )
            self.algorithms.invalidate(user_id)
            return {"applied": True, "decision": payload["decision"], **result}

        flagged_canonical = await self.storage.mark_possible_duplicate(
            canonical["id"], duplicate["name"], event_id=event_id
        )
        flagged_duplicate = await self.storage.mark_possible_duplicate(
            duplicate["id"], canonical["name"], event_id=event_id
        )
        return {
            "applied": flagged_canonical or flagged_duplicate,
            "decision": payload["decision"],
        }

    async def _resolve_endpoint(
        self,
        user_id: str,
        name: str,
        entity_type: Optional[str],
        confidence: float,
        entity_ids: Dict[Tuple[str, str], int],
        event_id: Optional[int] = None,
    ) -> Optional[int]:
        """Resolve a relationship endpoint to an entity id, creating it if typed."""
        key_name = _name_key(name)

        if entity_type:
            normalized = normalize_type(entity_type)
            existing = entity_ids.get((normalized, key_name))
            if existing is not None:
                return existing
            entity = await self.storage.upsert_entity(
                user_id=user_id,
                entity_type=normalized,
                name=name,
                confidence=confidence,
                event_id=event_id,
            )
            entity_ids[(entity["type"], key_name)] = entity["id"]
            return entity["id"]

        # Untyped endpoint: only resolvable against entities from this batch.
        for (_, existing_name), entity_id in entity_ids.items():
            if existing_name == key_name:
                return entity_id
        return None

    # ------------------------------------------------------------------
    # Periodic extraction
    # ------------------------------------------------------------------

    def _queue_turn(self, user_id: Any, conversation: str) -> None:
        """Buffer a turn for the next periodic deep-extraction pass."""
        queue = self._pending_turns.setdefault(
            str(user_id), deque(maxlen=MAX_PENDING_TURNS_PER_USER)
        )
        queue.append(conversation)

    def start_periodic_extraction(self, model_getter) -> None:
        """
        Start the periodic deep-extraction background loop.

        Args:
            model_getter: Zero-argument callable returning the extraction
                LLM (or None while unavailable). Resolved per run so the
                loop always uses the formation's current capability model.
        """
        if not self.enabled or not self.periodic_enabled:
            return
        if self._periodic_task is not None and not self._periodic_task.done():
            return
        self._periodic_task = asyncio.create_task(self._periodic_loop(model_getter))

    async def stop(self) -> None:
        """Cancel the periodic loop, if running."""
        if self._periodic_task is not None:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None

    async def _periodic_loop(self, model_getter) -> None:
        """Sleep-run loop for the periodic extraction pass."""
        while True:
            await asyncio.sleep(self.periodic_interval_seconds)
            try:
                await self.run_periodic_extraction(model_getter())
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_AUTO_EXTRACTION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"pass": "periodic", "error": str(e), "error_type": type(e).__name__},
                    description=f"Knowledge graph periodic extraction failed: {e}",
                )

    async def run_periodic_extraction(self, model) -> Dict[str, int]:
        """
        Deep-extract the turns accumulated since the last run.

        Processes each user's pending turns as one batch with full context
        at the periodic (lower) confidence threshold. Returns aggregate
        stored counts.
        """
        totals = {"entities": 0, "relationships": 0}
        if not self.enabled or not self.periodic_enabled or model is None:
            return totals

        pending = {user: list(turns) for user, turns in self._pending_turns.items() if turns}
        self._pending_turns.clear()

        for user_id, turns in pending.items():
            conversation = "\n\n".join(turns)
            try:
                result = await self.extractor.extract(
                    conversation, model, confidence_threshold=self.periodic_confidence
                )
                stored = await self.store_extraction(user_id, result, source=SOURCE_PERIODIC)
                totals["entities"] += stored["entities"]
                totals["relationships"] += stored["relationships"]
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_AUTO_EXTRACTION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "user_id": user_id,
                        "pass": "periodic",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Knowledge graph periodic extraction failed: {e}",
                )

        if totals["entities"] or totals["relationships"]:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_AUTO_EXTRACTED,
                level=observability.EventLevel.DEBUG,
                data={"pass": "periodic", **totals},
                description=(
                    f"Knowledge graph periodic extraction stored {totals['entities']} "
                    f"entities and {totals['relationships']} relationships"
                ),
            )
        return totals

    # ------------------------------------------------------------------
    # Query surface (context injection + path explanation)
    # ------------------------------------------------------------------

    async def get_context_block(
        self,
        user_id: Any,
        query_text: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """
        Render the user's graph context for prompt injection.

        Always includes the strongest 1-hop facts (direct SQL) followed by
        compact attribute cards ("Name (type): key: value; ...") for the
        entities carrying attribute facts -- emails, roles, tracking codes
        live on the entity itself, so a relationship-only rendering would
        never surface them to the LLM. Relationships and cards SHARE the
        single ``limit`` budget -- relationship lines consume first, cards
        fill the remainder -- so the block never grows past the ceiling
        callers sized their context for. Cards render most relevant
        entities first: entities touching the ranked relationships lead,
        then the newest attribute-bearing entities. Entities without
        attributes add
        nothing -- graphs with no attribute facts render exactly as
        before. When the query mentions a known entity, multi-hop
        exploration via the GraphAlgorithms backend appends the entities
        most strongly connected to it. Returns "" when the graph is empty
        or on error.

        Decay (Memory Substrate Phase 2c): when the formation configures
        half-lives (memory.decay.half_lives), facts are re-ranked by their
        query-time effective confidence -- stale decaying facts sink below
        fresh ones without any stored value changing.
        """
        if not self.enabled:
            return ""
        try:
            user_id = str(user_id)
            relationships = await self.storage.list_relationships(user_id, limit=limit)
            entities = await self.storage.list_entities(user_id, limit=ENTITY_SCAN_LIMIT)
            if not relationships and not entities:
                return ""
            relationships = self._rank_with_decay(relationships)

            entities_by_id = {entity["id"]: entity for entity in entities}
            # Relationship endpoints in rank order (strongest facts first);
            # also the relevance order for the attribute cards below.
            connected_ids: List[int] = []
            for rel in relationships:
                for entity_id in (rel["from_entity_id"], rel["to_entity_id"]):
                    if entity_id not in connected_ids:
                        connected_ids.append(entity_id)
            # Endpoints outside the active-entity scan window (e.g. merged
            # or superseded rows) still need names: one batched backfill.
            missing = [eid for eid in connected_ids if eid not in entities_by_id]
            if missing:
                for entity in await self.storage.get_entities_by_ids(missing):
                    entities_by_id[entity["id"]] = entity

            names = {eid: entity["name"] for eid, entity in entities_by_id.items()}
            lines = [
                f"{names.get(r['from_entity_id'], '?')} -[{r['type']}]-> "
                f"{names.get(r['to_entity_id'], '?')}"
                for r in relationships
            ]
            # Shared budget: relationship lines consume first (they lead
            # the relevance order), attribute cards fill the remainder --
            # the block never exceeds the single ``limit`` ceiling callers
            # sized their context for.
            remaining = limit - len(lines)
            if remaining > 0:
                lines.extend(_attribute_lines(connected_ids, entities, entities_by_id, remaining))
            if not lines:
                return ""

            if query_text:
                topic = await self._match_topic_entity(user_id, query_text, entities=entities)
                if topic is not None:
                    neighbors = await self.algorithms.weighted_neighbors(
                        topic["id"], user_id=user_id, limit=limit
                    )
                    neighbor_names = await self._entity_names(
                        {entity_id for entity_id, _ in neighbors}
                    )
                    related = ", ".join(
                        neighbor_names[entity_id]
                        for entity_id, _ in neighbors
                        if entity_id in neighbor_names
                    )
                    if related:
                        lines.append(f"Related to {topic['name']}: {related}")

            return "\n".join(lines)
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVAL_FAILED,
                level=observability.EventLevel.WARNING,
                data={"user_id": str(user_id), "error": str(e), "component": "knowledge_graph"},
                description=f"Knowledge graph context lookup failed: {e}",
            )
            return ""

    async def explain_path(self, user_id: Any, from_name: str, to_name: str) -> str:
        """
        Explain why two entities are related, as a rendered edge chain.

        Returns "" when either entity is unknown or no path exists.
        """
        if not self.enabled:
            return ""
        user_id = str(user_id)
        start = await self._find_entity_by_name(user_id, from_name)
        end = await self._find_entity_by_name(user_id, to_name)
        if start is None or end is None:
            return ""

        steps = await self.algorithms.path_explain(start["id"], end["id"], user_id=user_id)
        if not steps:
            return ""

        names = await self._entity_names({node_id for node_id, _ in steps})
        parts: List[str] = []
        for node_id, edge_id in steps:
            parts.append(names.get(node_id, "?"))
            if edge_id is not None:
                relationship = await self.storage.get_relationship_by_id(edge_id)
                parts.append(f"-[{relationship['type'] if relationship else '?'}]->")
        return " ".join(parts)

    def _rank_with_decay(self, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Re-rank facts by query-time effective confidence.

        A no-op (stable order) when decay is disabled or no relationship
        type has a configured half-life -- the default posture, so the
        hot read path pays nothing unless the formation opts in.
        """
        if self.decay is None or not self.decay.enabled or not self.decay.half_lives:
            return relationships
        from ..events.decay import effective_fact_confidence

        return sorted(
            relationships,
            key=lambda rel: effective_fact_confidence(rel, self.decay),
            reverse=True,
        )

    async def _entity_names(self, entity_ids: set) -> Dict[int, str]:
        """Map entity ids to display names (single batched query)."""
        entities = await self.storage.get_entities_by_ids(entity_ids)
        return {entity["id"]: entity["name"] for entity in entities}

    async def _match_topic_entity(
        self,
        user_id: str,
        query_text: str,
        entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find the first known entity whose name appears in the query.

        Whole-word matching only: a substring check would let short entity
        names match inside longer words (e.g. "go" inside "category").
        ``entities`` lets callers that already fetched the scan window
        (get_context_block) skip the second storage round-trip.
        """
        if entities is None:
            entities = await self.storage.list_entities(user_id, limit=ENTITY_SCAN_LIMIT)
        query_lower = query_text.lower()
        for entity in entities:
            name = entity["name"].lower()
            if name == _name_key(USER_ENTITY_NAME):
                continue
            if re.search(r"\b" + re.escape(name) + r"\b", query_lower):
                return entity
        return None

    async def _find_entity_by_name(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Find an active entity by case-insensitive name match."""
        key = _name_key(name)
        for entity in await self.storage.list_entities(user_id, limit=200):
            if _name_key(entity["name"]) == key:
                return entity
        return None


def _format_turn(user_message: str, agent_response: str) -> str:
    """Format a conversation turn for extraction, mirroring the flat extractor."""
    if agent_response and agent_response.strip():
        return f"User: {user_message}\nAssistant: {agent_response}"
    return f"User: {user_message}"


def _name_key(name: str) -> str:
    """Case-insensitive comparison key for entity names."""
    return name.strip().lower()


def _attribute_lines(
    connected_ids: List[int],
    scanned_entities: List[Dict[str, Any]],
    entities_by_id: Dict[int, Dict[str, Any]],
    limit: int,
) -> List[str]:
    """Compact attribute cards for the entities carrying attribute facts.

    Most relevant first: entities touching the ranked relationships (in
    rank order) lead, then the remaining attribute-bearing entities from
    the scan window (newest first). At most ``limit`` cards -- the caller
    passes the budget left after the relationship lines, so the whole
    block stays under one shared ceiling. Entities without renderable
    attributes are skipped entirely, so attribute-free graphs render
    unchanged.
    """
    ordered_ids = list(connected_ids)
    seen = set(connected_ids)
    for entity in scanned_entities:
        if entity["id"] not in seen:
            seen.add(entity["id"])
            ordered_ids.append(entity["id"])

    lines: List[str] = []
    for entity_id in ordered_ids:
        entity = entities_by_id.get(entity_id)
        if entity is None:
            continue
        attributes = _renderable_attributes(entity)
        if not attributes:
            continue
        lines.append(_entity_attribute_line(entity, attributes))
        if len(lines) >= limit:
            break
    return lines


def _renderable_attributes(entity: Dict[str, Any]) -> Dict[str, Any]:
    """The entity's attribute facts worth rendering (internal keys and
    empty values excluded)."""
    attributes = entity.get("attributes") or {}
    return {
        key: value
        for key, value in attributes.items()
        if key not in INTERNAL_ATTRIBUTE_KEYS and value not in (None, "", [], {})
    }


def _entity_attribute_line(entity: Dict[str, Any], attributes: Dict[str, Any]) -> str:
    """Render one entity's attribute card: ``Name (type): key: value; ...``.

    Keys are sorted for deterministic output; the line is hard-clipped to
    MAX_ATTRIBUTE_LINE_CHARS so a verbose value cannot blow the budget.
    """
    pairs = "; ".join(
        f"{key}: {_format_attribute_value(attributes[key])}" for key in sorted(attributes)
    )
    line = f"{entity['name']} ({entity['type']}): {pairs}"
    if len(line) > MAX_ATTRIBUTE_LINE_CHARS:
        line = line[: MAX_ATTRIBUTE_LINE_CHARS - 3] + "..."
    return line


def _format_attribute_value(value: Any) -> str:
    """Render one attribute value compactly (lists join, scalars stringify).

    Sets are sorted first -- their iteration order is arbitrary, and the
    card must render deterministically for the same stored value.
    """
    if isinstance(value, (set, frozenset)):
        return ", ".join(sorted(str(item) for item in value))
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _schedule_to_seconds(schedule: Any) -> float:
    """Convert a periodic_schedule config value to seconds."""
    if isinstance(schedule, (int, float)) and not isinstance(schedule, bool) and schedule > 0:
        return float(schedule)
    if isinstance(schedule, str):
        seconds = _SCHEDULE_SECONDS.get(schedule.strip().lower())
        if seconds is not None:
            return float(seconds)
    return float(_SCHEDULE_SECONDS[DEFAULT_PERIODIC_SCHEDULE])


# Re-exported for callers that render the user node specially.
__all__ = [
    "KnowledgeGraphService",
    "USER_ENTITY_NAME",
    "USER_ENTITY_TYPE",
]
