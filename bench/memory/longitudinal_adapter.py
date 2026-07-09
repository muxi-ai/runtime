"""Real-formation adapter for the Tier 3 longitudinal benchmark.

Extends the Tier 2 :class:`~bench.memory.structured_adapter.StructuredMemoryAdapter`
with the scenario-specific instrumentation Tier 3 needs. Everything
runs against the real services — no mocks:

- **Buffer cycling (Scenario A)** — sessions are replayed into the
  real working-memory buffer under a small ``max_memory_mb`` budget,
  and the buffer's own FIFO cleanup (``check_memory_usage_and_cleanup``)
  is driven once per ingested session (benchmark time is compressed;
  in production the same pass runs on a wall-clock interval). That is
  the exact path the pre-compaction flush (memory-revamp Phase 3)
  guards: the adapter wraps the flush service's eviction listener to
  count hand-offs, and — by default — resolves the flush digest model
  to ``None`` so runs stay deterministic and $0 (the trigger and
  hand-off mechanics are still exercised end-to-end). Pass
  ``flush_digest=True`` to let the silent-turn digest make its real
  LLM calls.
- **Per-session extraction replay (Scenario D)** — the ground-truth
  manifest is applied through ``KnowledgeGraphService.store_extraction``
  one session batch at a time, in corpus order, with per-fact
  confidences. That is the live dual-write path: the storage layer's
  contradiction detection fires exactly as it would in production and
  the event substrate records ``graph.extracted`` +
  ``fact.contradicted`` events, enabling the substrate-event tally and
  the projection-rebuild consistency check.
- **Audits** — contradiction pair audit (detection kind aware),
  zero-lost-decisions (Captain's Log), zero-artifact-orphans (KG
  reachability), and the isolation leak probes (vector / graph / log
  read paths).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple

from .datasets import Session
from .longitudinal_dataset import LongitudinalGroundTruth
from .longitudinal_scoring import (
    ArtifactAuditItem,
    ContradictionPairAudit,
    DecisionAuditItem,
)
from .structured_adapter import STRUCTURED_MODE, StructuredMemoryAdapter, _name_key

# The substrate audit event type recorded by the live extraction path
# (services/memory/events/models.py::EVENT_FACT_CONTRADICTED; literal
# here so the bench package stays importable without the runtime).
FACT_CONTRADICTED_EVENT = "fact.contradicted"


def _turn_order_key(item: Dict[str, Any]) -> Tuple[str, int]:
    turn_id = str(item.get("turn_id", ""))
    session_id, _, turn_index = turn_id.rpartition(":")
    return (session_id, int(turn_index) if turn_index.isdigit() else 0)


class LongitudinalMemoryAdapter(StructuredMemoryAdapter):
    """Tier 3 adapter: Tier 2 machinery plus longitudinal instrumentation."""

    def __init__(
        self,
        mode: str = STRUCTURED_MODE,
        buffer_max_mb: Optional[float] = None,
        flush_digest: bool = False,
        **kwargs,
    ):
        super().__init__(mode=mode, **kwargs)
        self.buffer_max_mb = buffer_max_mb
        self.flush_digest = flush_digest
        self.buffer_ingested_turns = 0
        self.cleanup_passes = 0
        self.flush_hand_offs = 0
        self.flush_items_handed = 0

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        await super().start()
        buffer = self.overlord.buffer_memory
        if buffer is None:
            return

        if self.buffer_max_mb is not None:
            # The buffer's memory budget is a constructor default (not
            # formation-configurable); the benchmark shrinks it so a
            # 30-day corpus cycles the buffer in minutes.
            buffer.max_memory_mb = float(self.buffer_max_mb)

        # Interpose on the pre-compaction flush hand-off (installed by
        # the Overlord at startup) to count triggers without changing
        # the real path.
        original_listener = buffer._eviction_listener
        threshold = buffer._eviction_flush_threshold

        def _counting_listener(items: List[Dict[str, Any]]) -> None:
            self.flush_hand_offs += 1
            self.flush_items_handed += len(items)
            if original_listener is not None:
                original_listener(items)

        buffer.set_eviction_listener(_counting_listener, threshold)

        flush_service = getattr(self.overlord, "precompaction_flush", None)
        if flush_service is not None and not self.flush_digest:
            # Counting-only mode (default): the trigger and hand-off
            # mechanics run for real, but the silent-turn digest
            # resolves no model — deterministic, $0. flush_items()
            # no-ops on a None model by design.
            flush_service._model_getter = lambda: None

    # -- Scenario A: buffer ingestion under a cycling budget -------------------

    async def ingest_session_buffer(self, user_id: str, session: Session) -> None:
        """Replay one session into the working-memory buffer, then run
        the FIFO cleanup pass (threshold flush + eviction) once."""
        buffer = self.overlord.buffer_memory
        for turn in session.turns:
            text = self._render_turn_text(session, turn)
            if not text.strip():
                continue
            metadata = {
                "user_id": user_id,
                "bench_session_id": session.session_id,
                "bench_turn_id": turn.turn_id,
                "role": turn.role,
            }
            await buffer.add(text, metadata=metadata)
            self.ingested_turns += 1
            self.buffer_ingested_turns += 1

        buffer.check_memory_usage_and_cleanup()
        self.cleanup_passes += 1
        # A triggered flush is scheduled onto this loop; yield so the
        # (counting-only) coroutine can run between sessions.
        await asyncio.sleep(0)

    def buffer_resident_turn_ids(self) -> Set[str]:
        """Bench turn ids still resident in the buffer (post-eviction)."""
        buffer = self.overlord.buffer_memory
        resident: Set[str] = set()
        for item in buffer.buffer:
            turn_id = (item.get("metadata") or {}).get("bench_turn_id")
            if turn_id:
                resident.add(str(turn_id))
        return resident

    async def search_working(self, user_id: str, query: str, fetch_limit: int):
        """Working-memory-only retrieval (the Scenario A baseline)."""
        self.searches += 1
        raw = await self.overlord.buffer_memory.search(
            query,
            limit=fetch_limit,
            filter_metadata={"user_id": user_id},
            recency_bias=0.0,
            namespace="buffer",
        )
        return self._items_from_working(raw)

    def eviction_stats(self) -> Dict[str, Any]:
        resident = self.buffer_resident_turn_ids()
        return {
            "ingested_turns": self.buffer_ingested_turns,
            "resident_turns": len(resident),
            "evicted_turns": self.buffer_ingested_turns - len(resident),
            "max_memory_mb": (
                self.overlord.buffer_memory.max_memory_mb
                if self.overlord and self.overlord.buffer_memory
                else None
            ),
            "cleanup_passes": self.cleanup_passes,
        }

    def flush_stats(self) -> Dict[str, Any]:
        return {
            "hand_offs": self.flush_hand_offs,
            "items_handed": self.flush_items_handed,
            "digest_enabled": self.flush_digest,
            "attached": getattr(self.overlord, "precompaction_flush", None) is not None,
        }

    # -- Scenario A/B audits ----------------------------------------------------

    async def audit_decisions(
        self, user_id: str, truth: LongitudinalGroundTruth
    ) -> List[DecisionAuditItem]:
        """Zero-lost-decisions: every ground-truth decision must be
        findable in the Captain's Log."""
        log_storage = self.overlord.captains_log.storage
        entries = await log_storage.list_entries(user_id, limit=1000)
        logged: Set[str] = set()
        for entry in entries:
            for decision in entry.get("decisions") or []:
                logged.add(str(decision))
        return [
            DecisionAuditItem(
                decision=str(item["decision"]),
                date=str(item["date"]),
                found=str(item["decision"]) in logged,
            )
            for item in truth.decisions
        ]

    async def audit_artifacts(
        self, user_id: str, truth: LongitudinalGroundTruth
    ) -> List[ArtifactAuditItem]:
        """Zero-artifact-orphans: every artifact must be reachable from
        the KG (entity present + produced edge from its agent)."""
        graph = self.overlord.knowledge_graph
        entities = await graph.storage.list_entities(user_id, status=None, limit=1000)
        relationships = await graph.storage.list_relationships(user_id, status=None, limit=2000)
        names = {entity["id"]: _name_key(entity["name"]) for entity in entities}
        entity_keys = {(_name_key(entity["name"]), entity["type"]) for entity in entities}
        produced = {
            (names.get(rel["from_entity_id"]), names.get(rel["to_entity_id"]))
            for rel in relationships
            if rel["type"] == "produced"
        }
        items: List[ArtifactAuditItem] = []
        for artifact in truth.artifacts:
            name = _name_key(str(artifact["name"]))
            agent = _name_key(str(artifact["agent"]))
            items.append(
                ArtifactAuditItem(
                    name=str(artifact["name"]),
                    agent=str(artifact["agent"]),
                    entity_found=(name, "artifact") in entity_keys,
                    produced_link_found=(agent, name) in produced,
                )
            )
        return items

    # -- Scenario C: isolation probes -------------------------------------------

    async def isolation_vector_op(
        self, user_id: str, query: str, fetch_limit: int
    ) -> Tuple[List[str], List[str]]:
        """One vector retrieval op; returns (texts, session ids)."""
        items = await self.search(user_id, query, fetch_limit)
        return [item.text for item in items], [item.session_id for item in items]

    async def isolation_graph_op(self, user_id: str) -> Tuple[List[str], List[str]]:
        """One KG read op: every entity/relationship visible to the user."""
        graph = self.overlord.knowledge_graph
        entities = await graph.storage.list_entities(user_id, status=None, limit=1000)
        relationships = await graph.storage.list_relationships(user_id, status=None, limit=2000)
        names = {entity["id"]: entity["name"] for entity in entities}
        texts = [
            f"{entity['name']} ({entity['type']}) {entity.get('attributes') or {}}"
            for entity in entities
        ]
        texts.extend(
            f"{names.get(rel['from_entity_id'], '?')} -[{rel['type']}]-> "
            f"{names.get(rel['to_entity_id'], '?')}"
            for rel in relationships
        )
        return texts, []

    async def isolation_log_op(self, user_id: str) -> Tuple[List[str], List[str]]:
        """One Captain's-Log read op: every entry visible to the user."""
        log_storage = self.overlord.captains_log.storage
        entries = await log_storage.list_entries(user_id, limit=1000)
        texts = []
        for entry in entries:
            parts = [str(entry.get("summary") or "")]
            parts.extend(str(decision) for decision in entry.get("decisions") or [])
            texts.append(" | ".join(part for part in parts if part))
        return texts, []

    # -- Scenario D: per-session extraction replay + audits ----------------------

    async def ingest_extraction_sessions(self, user_id: str, truth: LongitudinalGroundTruth) -> int:
        """Replay the manifest through ``store_extraction`` one session
        at a time, in corpus order (the live dual-write path: storage
        contradiction detection + substrate event recording)."""
        graph = self.overlord.knowledge_graph

        entities = sorted(truth.entities, key=_turn_order_key)
        relationships = sorted(truth.relationships, key=_turn_order_key)
        session_ids = sorted({str(item["session_id"]) for item in (*entities, *relationships)})

        batches = 0
        for session_id in session_ids:
            extraction = {
                "entities": [
                    {
                        "type": entity["type"],
                        "name": entity["name"],
                        "attributes": dict(entity.get("attributes") or {}),
                        "confidence": 0.85,
                    }
                    for entity in entities
                    if str(entity["session_id"]) == session_id
                ],
                "relationships": [
                    {
                        "from": rel["from_name"],
                        "from_type": rel["from_type"],
                        "type": rel["type"],
                        "to": rel["to_name"],
                        "to_type": rel["to_type"],
                        "attributes": dict(rel.get("attributes") or {}),
                        "confidence": float(rel.get("confidence", 0.85)),
                    }
                    for rel in relationships
                    if str(rel["session_id"]) == session_id
                ],
            }
            if not extraction["entities"] and not extraction["relationships"]:
                continue
            await graph.store_extraction(user_id, extraction, source="interaction")
            batches += 1
            self.ingested_turns += 1
        return batches

    async def _kg_flag_state(
        self, user_id: str
    ) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, str]]:
        graph = self.overlord.knowledge_graph
        relationships = await graph.storage.list_relationships(user_id, status=None, limit=2000)
        entities = await graph.storage.list_entities(user_id, status=None, limit=1000)
        by_id = {rel["id"]: rel for rel in relationships}
        names = {entity["id"]: _name_key(entity["name"]) for entity in entities}
        return by_id, names

    async def audit_contradiction_pairs(
        self, user_id: str, truth: LongitudinalGroundTruth
    ) -> Tuple[List[ContradictionPairAudit], List[Tuple[str, str, str, str]]]:
        """Compare KG conflict/supersede flags against the injected
        pairs; returns (per-pair audits, false-positive signatures)."""
        by_id, names = await self._kg_flag_state(user_id)

        def _rel_lookup(subject: str, predicate: str, obj: str) -> Optional[Dict[str, Any]]:
            for rel in by_id.values():
                if (
                    names.get(rel["from_entity_id"]) == _name_key(subject)
                    and str(rel["type"]) == predicate
                    and names.get(rel["to_entity_id"]) == _name_key(obj)
                ):
                    return rel
            return None

        pairs: List[ContradictionPairAudit] = []
        for contradiction in truth.contradictions:
            audit = ContradictionPairAudit(
                subject=str(contradiction["subject"]),
                predicate=str(contradiction["predicate"]),
                old_object=str(contradiction["old_object"]),
                new_object=str(contradiction["new_object"]),
                expected_detection=str(contradiction["expected_detection"]),
            )
            old_rel = _rel_lookup(audit.subject, audit.predicate, audit.old_object)
            new_rel = _rel_lookup(audit.subject, audit.predicate, audit.new_object)
            if old_rel is not None and new_rel is not None:
                if old_rel.get("superseded_by") == new_rel["id"]:
                    audit.detected = True
                    audit.detected_kind = "superseded"
                elif old_rel.get("contradicted_by") == new_rel["id"]:
                    audit.detected = True
                    audit.detected_kind = "conflicted"
            pairs.append(audit)

        # Every flagged pair in the graph, as unordered signatures, to
        # count detections outside the injected ground truth.
        detected_signatures = set()
        for rel in by_id.values():
            for link in ("contradicted_by", "superseded_by"):
                other_id = rel.get(link)
                other = by_id.get(other_id)
                if other is None:
                    continue
                subject = names.get(rel["from_entity_id"], "?")
                objects = sorted(
                    (
                        names.get(rel["to_entity_id"], "?"),
                        names.get(other["to_entity_id"], "?"),
                    )
                )
                detected_signatures.add((subject, str(rel["type"]), objects[0], objects[1]))
        expected_signatures = {
            (
                _name_key(str(c["subject"])),
                str(c["predicate"]),
                *sorted((_name_key(str(c["old_object"])), _name_key(str(c["new_object"])))),
            )
            for c in truth.contradictions
        }
        false_positives = sorted(detected_signatures - expected_signatures)
        return pairs, false_positives

    async def contradiction_event_stats(self, user_id: str, detected_total: int) -> Dict[str, Any]:
        """Tally the substrate's fact.contradicted audit events."""
        service = getattr(self.overlord, "memory_events", None)
        if service is None or not getattr(service, "enabled", False):
            return {"available": False, "events": 0, "matches_detections": None}
        events = await service.list_events(user_id, event_types=[FACT_CONTRADICTED_EVENT])
        return {
            "available": True,
            "events": len(events),
            "matches_detections": len(events) == detected_total,
        }

    async def rebuild_knowledge_graph(self, user_id: str) -> Dict[str, Any]:
        """Rebuild the KG projection from the event log (service layer,
        same path as the /memory rebuild endpoint)."""
        service = getattr(self.overlord, "memory_events", None)
        if service is None or not getattr(service, "enabled", False):
            return {"available": False}
        report = await service.rebuild(user_id, projection="knowledge_graph")
        return {"available": True, **report.get("knowledge_graph", {})}

    # -- reporting ---------------------------------------------------------------

    def config_snapshot(self) -> Dict[str, Any]:
        config = super().config_snapshot()
        if self.buffer_max_mb is not None:
            config["buffer_max_mb"] = self.buffer_max_mb
        config["flush_digest"] = self.flush_digest
        return config
