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


class KnowledgeGraphService:
    """Owns knowledge graph storage, extraction, and query surface."""

    def __init__(self, db_manager, formation_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the knowledge graph service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all graph rows.
            config: The ``memory.graph`` formation config section.
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
    ) -> None:
        """
        Run the real-time graph extraction pass for one conversation turn.

        Never raises: extraction or storage failures are logged and the
        chat turn continues unaffected.
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
            stored = await self._store_extraction(user_id, result)
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

    async def _store_extraction(
        self, user_id: Any, result: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, int]:
        """Persist one extraction result; returns stored counts."""
        user_id = str(user_id)
        entity_ids: Dict[Tuple[str, str], int] = {}
        stored_entities = 0
        stored_relationships = 0

        for item in result.get("entities", []):
            entity = await self.storage.upsert_entity(
                user_id=user_id,
                entity_type=item["type"],
                name=item["name"],
                attributes=item.get("attributes"),
                confidence=item["confidence"],
            )
            entity_ids[(entity["type"], _name_key(entity["name"]))] = entity["id"]
            stored_entities += 1

        for item in result.get("relationships", []):
            from_id = await self._resolve_endpoint(
                user_id, item["from"], item.get("from_type"), item["confidence"], entity_ids
            )
            to_id = await self._resolve_endpoint(
                user_id, item["to"], item.get("to_type"), item["confidence"], entity_ids
            )
            if from_id is None or to_id is None or from_id == to_id:
                continue
            await self.storage.upsert_relationship(
                user_id=user_id,
                from_entity_id=from_id,
                to_entity_id=to_id,
                rel_type=item["type"],
                attributes=item.get("attributes"),
                confidence=item["confidence"],
            )
            stored_relationships += 1

        if stored_entities or stored_relationships:
            self.algorithms.invalidate(user_id)

        return {"entities": stored_entities, "relationships": stored_relationships}

    async def _resolve_endpoint(
        self,
        user_id: str,
        name: str,
        entity_type: Optional[str],
        confidence: float,
        entity_ids: Dict[Tuple[str, str], int],
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
                stored = await self._store_extraction(user_id, result)
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

        Always includes the strongest 1-hop facts (direct SQL). When the
        query mentions a known entity, multi-hop exploration via the
        GraphAlgorithms backend appends the entities most strongly
        connected to it. Returns "" when the graph is empty or on error.
        """
        if not self.enabled:
            return ""
        try:
            user_id = str(user_id)
            relationships = await self.storage.list_relationships(user_id, limit=limit)
            if not relationships:
                return ""

            names = await self._entity_names(
                {r["from_entity_id"] for r in relationships}
                | {r["to_entity_id"] for r in relationships}
            )
            lines = [
                f"{names.get(r['from_entity_id'], '?')} -[{r['type']}]-> "
                f"{names.get(r['to_entity_id'], '?')}"
                for r in relationships
            ]

            if query_text:
                topic = await self._match_topic_entity(user_id, query_text)
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

    async def _entity_names(self, entity_ids: set) -> Dict[int, str]:
        """Map entity ids to display names (single batched query)."""
        entities = await self.storage.get_entities_by_ids(entity_ids)
        return {entity["id"]: entity["name"] for entity in entities}

    async def _match_topic_entity(self, user_id: str, query_text: str) -> Optional[Dict[str, Any]]:
        """Find the first known entity whose name appears in the query.

        Whole-word matching only: a substring check would let short entity
        names match inside longer words (e.g. "go" inside "category").
        """
        query_lower = query_text.lower()
        for entity in await self.storage.list_entities(user_id, limit=200):
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
