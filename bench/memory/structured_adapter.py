"""Real-formation adapter for the Tier 2 structured-recall benchmark.

Extends the Tier 1 :class:`~bench.memory.adapter.MuxiMemoryAdapter`
with a fourth retrieval mode, ``structured``, that exercises the
Knowledge Graph and Captain's Log services instead of vector search:

- **Ingestion** loads each case's ground-truth manifest through the
  real service write paths — ``KnowledgeGraphService.apply_extraction``
  (which runs the storage layer's contradiction detection on exclusive
  predicates) and ``CaptainsLogStorage.upsert_entry`` — in corpus
  chronological order. No LLM is involved: ingesting the manifest
  directly isolates *structured recall* (can the KG/log query surface
  answer the question?) from *extraction quality* (can the LLM build
  the right graph from raw text?). The extraction-quality half is the
  Tier 3 seam: once the memory-substrate rebuild lands, the same
  dataset can be replayed turn-by-turn through
  ``process_conversation_turn`` to measure the full pipeline.
- **Retrieval** matches question text against KG entities (whole-word,
  longest-first), ranks the relationships touching matched entities by
  confidence, and — for date-scoped questions — fetches Captain's-Log
  entries for the question's date window. KG facts and log entries are
  fused with the same scale-free RRF used by Tier 1's combined mode.
  Results are mapped back to evidence session/turn ids through the
  manifest's provenance, so Tier 1 R@K scoring applies unchanged.
- **Contradiction audit** reads back the KG's conflict/supersede flags
  after ingestion and compares the flagged pairs against the injected
  ground truth (precision/recall).

Vector modes (``working``/``persistent``/``combined``) are inherited
untouched so the same runner produces directly comparable baselines.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .adapter import MODES as VECTOR_MODES, MuxiMemoryAdapter, RetrievedItem
from .datasets import Question
from .scoring import reciprocal_rank_fusion
from .structured_dataset import StructuredGroundTruth
from .structured_scoring import ContradictionCaseResult

STRUCTURED_MODE = "structured"
MODES = tuple(VECTOR_MODES) + (STRUCTURED_MODE,)


def _name_key(name: str) -> str:
    return " ".join(str(name).split()).lower()


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _render_attributes(attributes: Dict[str, Any]) -> str:
    if not attributes:
        return ""
    parts = [f"{key}: {attributes[key]}" for key in sorted(attributes)]
    return " (" + ", ".join(parts) + ")"


class StructuredMemoryAdapter(MuxiMemoryAdapter):
    """Tier 2 adapter: vector modes plus KG + Captain's-Log retrieval."""

    def __init__(self, mode: str, **kwargs):
        if mode == STRUCTURED_MODE:
            # The base class validates against the vector modes; run its
            # setup under a valid mode, then switch.
            super().__init__(mode="combined", **kwargs)
            self.mode = STRUCTURED_MODE
        else:
            super().__init__(mode=mode, **kwargs)
        # Provenance for the current case, rebuilt per ingest_ground_truth:
        # (from_key, rel_type, to_key) -> ordered [(session_id, turn_id), ...]
        self._rel_provenance: Dict[Tuple[str, str, str], List[Tuple[str, str]]] = {}
        # entity name key -> ordered [(session_id, turn_id), ...]
        self._entity_provenance: Dict[str, List[Tuple[str, str]]] = {}
        # log entry date (iso) -> source session ids
        self._log_sources: Dict[str, List[str]] = {}

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        await super().start()
        if self.mode == STRUCTURED_MODE:
            if getattr(self.overlord, "knowledge_graph", None) is None:
                raise RuntimeError(
                    "Knowledge graph service is not configured on the benchmark formation"
                )
            if getattr(self.overlord, "captains_log", None) is None:
                raise RuntimeError(
                    "Captain's log service is not configured on the benchmark formation"
                )

    def clear_case(self) -> None:
        super().clear_case()
        self._rel_provenance = {}
        self._entity_provenance = {}
        self._log_sources = {}

    # -- ground-truth ingestion (structured mode) -----------------------------

    async def ingest_ground_truth(self, user_id: str, truth: StructuredGroundTruth) -> None:
        """Load one case's manifest through the real KG + log write paths."""
        graph = self.overlord.knowledge_graph
        log_storage = self.overlord.captains_log.storage

        def _order_key(item: Dict[str, Any]) -> Tuple[str, int]:
            turn_id = str(item.get("turn_id", ""))
            session_id, _, turn_index = turn_id.rpartition(":")
            return (session_id, int(turn_index) if turn_index.isdigit() else 0)

        entities = sorted(truth.entities, key=_order_key)
        relationships = sorted(truth.relationships, key=_order_key)

        # Chronological single batch: apply_extraction processes lists in
        # order, so the storage layer sees assertions in corpus order and
        # its contradiction detection fires exactly as it would live.
        extraction = {
            "entities": [
                {
                    "type": entity["type"],
                    "name": entity["name"],
                    "attributes": dict(entity.get("attributes") or {}),
                    "confidence": 0.85,
                }
                for entity in entities
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
            ],
        }
        await graph.apply_extraction(user_id, extraction)

        self._rel_provenance = {}
        for rel in relationships:
            key = (_name_key(rel["from_name"]), str(rel["type"]), _name_key(rel["to_name"]))
            self._rel_provenance.setdefault(key, []).append(
                (str(rel["session_id"]), str(rel["turn_id"]))
            )

        self._entity_provenance = {}
        for entity in entities:
            self._entity_provenance.setdefault(_name_key(entity["name"]), []).append(
                (str(entity["session_id"]), str(entity["turn_id"]))
            )

        self._log_sources = {}
        for entry in truth.log_entries:
            entry_date = _parse_date(entry["date"])
            if entry_date is None:
                continue
            await log_storage.upsert_entry(
                user_id=user_id,
                entry_date=entry_date,
                summary=entry.get("summary"),
                decisions=list(entry.get("decisions") or []),
                projects=list(entry.get("projects") or []),
            )
            self._log_sources[str(entry["date"])] = list(entry.get("source_session_ids") or [])
            self.ingested_turns += 1

    # -- retrieval -------------------------------------------------------------

    async def search_question(
        self, user_id: str, question: Question, fetch_limit: int
    ) -> List[RetrievedItem]:
        """Question-aware retrieval (structured mode needs the date window)."""
        if self.mode != STRUCTURED_MODE:
            return await self.search(user_id, question.question, fetch_limit)
        self.searches += 1
        kg_items = await self._search_graph(user_id, question.question, fetch_limit)
        log_items = await self._search_log(user_id, question, fetch_limit)

        by_key: Dict[str, RetrievedItem] = {}
        for item in log_items + kg_items:
            by_key.setdefault(item.turn_id, item)
        fused = reciprocal_rank_fusion(
            [
                [item.turn_id for item in kg_items],
                [item.turn_id for item in log_items],
            ]
        )
        return [by_key[key] for key in fused[:fetch_limit]]

    async def _search_graph(
        self, user_id: str, question_text: str, fetch_limit: int
    ) -> List[RetrievedItem]:
        """Rank KG facts by entity match + confidence, mapped to provenance."""
        graph = self.overlord.knowledge_graph
        entities = await graph.storage.list_entities(user_id, status=None, limit=500)
        names = {entity["id"]: entity["name"] for entity in entities}

        question_lower = question_text.lower()
        matched: List[Dict[str, Any]] = []
        matched_ids = set()
        for entity in sorted(entities, key=lambda e: (-len(e["name"]), e["name"])):
            name = _name_key(entity["name"])
            if name and re.search(r"\b" + re.escape(name) + r"\b", question_lower):
                matched.append(entity)
                matched_ids.add(entity["id"])

        # Entity cards for matched entities: the KG stores attribute facts
        # (emails, roles, reference kinds) on the entity itself, so a
        # relationship-only rendering would lose them (that gap showed up
        # as 0% exact-string recall on entity-attribute questions).
        items: List[RetrievedItem] = []
        seen_turns = set()
        for entity in matched:
            attributes = dict(entity.get("attributes") or {})
            if not attributes:
                continue
            text = f"{entity['name']} ({entity['type']}){_render_attributes(attributes)}"
            for session_id, turn_id in self._entity_provenance.get(_name_key(entity["name"]), [])[
                :1
            ]:
                if turn_id in seen_turns:
                    continue
                seen_turns.add(turn_id)
                items.append(
                    RetrievedItem(
                        turn_id=turn_id,
                        session_id=session_id,
                        text=text,
                        score=float(entity.get("confidence") or 0.0),
                        source="knowledge_graph",
                    )
                )

        relationships = await graph.storage.list_relationships(user_id, status=None, limit=1000)
        touching = [
            rel
            for rel in relationships
            if rel["from_entity_id"] in matched_ids or rel["to_entity_id"] in matched_ids
        ]
        # Deterministic rank: strongest first, stable id tiebreak.
        touching.sort(key=lambda rel: (-float(rel["confidence"] or 0.0), rel["id"]))

        for rel in touching:
            from_name = names.get(rel["from_entity_id"], "?")
            to_name = names.get(rel["to_entity_id"], "?")
            key = (_name_key(from_name), str(rel["type"]), _name_key(to_name))
            attributes = dict(rel.get("attributes") or {})
            status = rel.get("status")
            if status and status != "active":
                attributes["status"] = status
            text = f"{from_name} -[{rel['type']}]-> {to_name}{_render_attributes(attributes)}"
            for session_id, turn_id in self._rel_provenance.get(key, []):
                if turn_id in seen_turns:
                    continue
                seen_turns.add(turn_id)
                items.append(
                    RetrievedItem(
                        turn_id=turn_id,
                        session_id=session_id,
                        text=text,
                        score=float(rel["confidence"] or 0.0),
                        source="knowledge_graph",
                    )
                )
            if len(items) >= fetch_limit:
                break
        return items[:fetch_limit]

    async def _search_log(
        self, user_id: str, question: Question, fetch_limit: int
    ) -> List[RetrievedItem]:
        """Captain's-Log lookup for the question's date window."""
        date_from = _parse_date(question.date_from)
        date_to = _parse_date(question.date_to)
        if date_from is None and date_to is None:
            return []
        log_storage = self.overlord.captains_log.storage
        entries = await log_storage.list_entries(
            user_id, limit=fetch_limit, date_from=date_from, date_to=date_to
        )
        items: List[RetrievedItem] = []
        for entry in entries:
            entry_date = str(entry.get("date") or "")[:10]
            sections = [f"Captain's log {entry_date}: {entry.get('summary') or ''}"]
            decisions = entry.get("decisions") or []
            if decisions:
                sections.append("Decisions: " + "; ".join(decisions))
            projects = entry.get("projects") or []
            if projects:
                sections.append("Projects: " + ", ".join(projects))
            text = " | ".join(sections)
            for session_id in self._log_sources.get(entry_date, []):
                items.append(
                    RetrievedItem(
                        turn_id=f"{session_id}:log",
                        session_id=session_id,
                        text=text,
                        score=1.0,
                        source="captains_log",
                    )
                )
        return items[:fetch_limit]

    # -- contradiction audit (structured mode) ---------------------------------

    async def audit_contradictions(
        self, user_id: str, truth: StructuredGroundTruth
    ) -> ContradictionCaseResult:
        """Compare the KG's conflict/supersede flags against ground truth."""
        graph = self.overlord.knowledge_graph
        relationships = await graph.storage.list_relationships(user_id, status=None, limit=1000)
        by_id = {rel["id"]: rel for rel in relationships}
        entities = await graph.storage.list_entities(user_id, status=None, limit=500)
        names = {entity["id"]: entity["name"] for entity in entities}

        def _pair_signature(rel_a: Dict[str, Any], rel_b: Dict[str, Any]):
            subject = _name_key(names.get(rel_a["from_entity_id"], "?"))
            objects = tuple(
                sorted(
                    (
                        _name_key(names.get(rel_a["to_entity_id"], "?")),
                        _name_key(names.get(rel_b["to_entity_id"], "?")),
                    )
                )
            )
            return (subject, str(rel_a["type"]), objects[0], objects[1])

        detected_ids = set()
        for rel in relationships:
            for link in ("contradicted_by", "superseded_by"):
                other_id = rel.get(link)
                if other_id and other_id in by_id:
                    detected_ids.add(tuple(sorted((rel["id"], other_id))))

        detected_pairs = sorted(_pair_signature(by_id[a], by_id[b]) for a, b in detected_ids)
        expected_pairs = sorted(
            (
                _name_key(c["subject"]),
                str(c["predicate"]),
                *sorted((_name_key(c["old_object"]), _name_key(c["new_object"]))),
            )
            for c in truth.contradictions
        )
        true_positives = len(set(detected_pairs) & set(expected_pairs))
        return ContradictionCaseResult(
            case_id=truth.case_id,
            expected=len(expected_pairs),
            detected=len(detected_pairs),
            true_positives=true_positives,
            detected_pairs=[tuple(p) for p in detected_pairs],
            expected_pairs=[tuple(p) for p in expected_pairs],
        )

    # -- reporting -------------------------------------------------------------

    def config_snapshot(self) -> Dict[str, Any]:
        config = super().config_snapshot()
        config["mode"] = self.mode
        if self.mode == STRUCTURED_MODE:
            config["structured_backends"] = ["knowledge_graph", "captains_log"]
            config["ground_truth_ingestion"] = (
                "manifest via apply_extraction (no LLM extraction; see README Tier 3 seam)"
            )
        return config
