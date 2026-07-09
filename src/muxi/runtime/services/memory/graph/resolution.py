# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Entity Resolution - Probabilistic Identity Matching
# Description:  Detects and merges duplicate identities in the knowledge graph
# Role:         Scores entity pairs; auto-merges or flags via entity.resolved
# Usage:        Driven by the ingestion pipeline (extraction time) and the
#               synthesis cadences (hot/cold passes)
# Author:       Muxi Framework Team
#
# Memory Ingestion maturation (PRD "Entity resolution"): "Ryan from this
# email" = "Ryan Leveille" from LinkedIn = the same person. Matching is
# probabilistic over name / email / handle / role / relationship context,
# but the SCORING IS PURE STRING AND SET LOGIC -- deterministic given the
# same two entities, so the same content always resolves the same way.
#
# Decisions ride the event substrate:
# - score >= auto_merge_threshold  -> decision "merged"
# - flag_threshold <= score < auto -> decision "flagged" (event + stored
#   attributes.possible_duplicates marker; a later pass with stronger
#   evidence can still merge the pair -- merged and flagged use distinct
#   idempotency keys)
#
# Determinism and idempotency contract:
# - Every decision is appended as an entity.resolved event BEFORE it is
#   applied, keyed by a deterministic per-pair source_id
#   (entity_resolution/<type>/<nameA>|<nameB>/<decision>, names sorted).
#   Re-ingestion re-derives the same pair, hits the substrate's
#   (source, source_id) unique index, and is skipped -- it can neither
#   duplicate the merge nor re-merge differently.
# - The apply is a pure function of the event payload (names, decision):
#   rebuild replays the recorded decisions in append order and converges
#   to the same merged graph, even if thresholds changed since.
# - Merged names stay sticky: the graph upsert path redirects them to the
#   canonical entity, so later mentions of the duplicate cannot revive it.
# =============================================================================

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from ... import observability
from ..events.models import EVENT_ENTITY_RESOLVED, SOURCE_SYNTHESIS
from .extractor import USER_ENTITY_NAME
from .models import STATUS_ACTIVE

if TYPE_CHECKING:  # imported lazily at runtime (the ingest package pulls
    # in the request tracker; keep graph modules import-light)
    from ..ingest.config import ResolutionSettings

DECISION_MERGED = "merged"
DECISION_FLAGGED = "flagged"

# Signal weights (PRD matching dimensions). The exact values are a
# mechanism dial baked into the scorer; the THRESHOLDS are the formation
# author's policy surface (memory.ingestion.entity_resolution).
WEIGHT_EMAIL = 0.6
WEIGHT_HANDLE = 0.4
WEIGHT_NAME_MATCH = 0.5
WEIGHT_NAME_SUBSET = 0.35
WEIGHT_FIRST_NAME = 0.15
WEIGHT_ROLE = 0.15
WEIGHT_SHARED_CONTEXT = 0.2

# Attribute keys mined for identity signals (values may be str or list).
EMAIL_KEYS = ("email", "emails", "email_address", "contact_email")
HANDLE_KEYS = ("handle", "handles", "username", "github", "twitter", "x", "linkedin", "slack")
ROLE_KEYS = ("role", "title", "job_title", "user_role", "position")

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _attribute_values(attributes: Dict[str, Any], keys: Tuple[str, ...]) -> Set[str]:
    """Normalized string values under the given attribute keys."""
    values: Set[str] = set()
    for key in keys:
        raw = attributes.get(key)
        if raw is None:
            continue
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            if isinstance(item, str) and item.strip():
                values.add(item.strip().lower().lstrip("@"))
    return values


def _emails(entity: Dict[str, Any]) -> Set[str]:
    """Emails from the email attribute keys plus any attribute string value."""
    attributes = entity.get("attributes") or {}
    found = _attribute_values(attributes, EMAIL_KEYS)
    for value in attributes.values():
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, str):
                found.update(match.lower() for match in _EMAIL_RE.findall(item))
    return {value for value in found if "@" in value}


def _name_tokens(name: str) -> Tuple[str, ...]:
    """Lowercased alphanumeric name tokens in order."""
    return tuple(_TOKEN_RE.findall(name.lower()))


def score_identity_match(
    a: Dict[str, Any],
    b: Dict[str, Any],
    shared_neighbors: int = 0,
) -> Tuple[float, List[str]]:
    """
    Score two entities as the same identity (0.0 - 1.0, deterministic).

    Args:
        a, b: Entity dicts (graph storage shape: name + attributes).
        shared_neighbors: Count of graph entities both are related to
            (relationship context, e.g. both ``works_at`` the same
            company).

    Returns:
        (score, signals) -- signals is the sorted list of contributing
        signal names, recorded on the entity.resolved event.
    """
    score = 0.0
    signals: List[str] = []

    if _emails(a) & _emails(b):
        score += WEIGHT_EMAIL
        signals.append("email_match")

    handles_a = _attribute_values(a.get("attributes") or {}, HANDLE_KEYS)
    handles_b = _attribute_values(b.get("attributes") or {}, HANDLE_KEYS)
    if handles_a & handles_b:
        score += WEIGHT_HANDLE
        signals.append("handle_match")

    tokens_a = set(_name_tokens(a.get("name") or ""))
    tokens_b = set(_name_tokens(b.get("name") or ""))
    if tokens_a and tokens_b:
        if tokens_a == tokens_b:
            score += WEIGHT_NAME_MATCH
            signals.append("name_match")
        elif tokens_a < tokens_b or tokens_b < tokens_a:
            score += WEIGHT_NAME_SUBSET
            signals.append("name_subset")
        else:
            first_a = _name_tokens(a.get("name") or "")[0]
            first_b = _name_tokens(b.get("name") or "")[0]
            if first_a == first_b:
                score += WEIGHT_FIRST_NAME
                signals.append("first_name_match")

    roles_a = _attribute_values(a.get("attributes") or {}, ROLE_KEYS)
    roles_b = _attribute_values(b.get("attributes") or {}, ROLE_KEYS)
    if roles_a & roles_b:
        score += WEIGHT_ROLE
        signals.append("role_match")

    if shared_neighbors > 0:
        score += WEIGHT_SHARED_CONTEXT
        signals.append("shared_context")

    return min(score, 1.0), sorted(signals)


def pick_canonical(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Deterministically pick (canonical, duplicate) for a matched pair.

    The fuller name wins (more tokens); ties fall to higher confidence,
    then to the older row (lower id -- replay recreates rows in the same
    relative order, so this is stable across rebuilds).
    """
    key_a = (len(_name_tokens(a.get("name") or "")), a.get("confidence") or 0.0, -(a["id"]))
    key_b = (len(_name_tokens(b.get("name") or "")), b.get("confidence") or 0.0, -(b["id"]))
    return (a, b) if key_a >= key_b else (b, a)


def pair_source_id(entity_type: str, name_a: str, name_b: str, decision: str) -> str:
    """Deterministic idempotency key for one resolution decision."""
    low, high = sorted((name_a.strip().lower(), name_b.strip().lower()))
    return f"entity_resolution/{entity_type}/{low}|{high}/{decision}"


class EntityResolver:
    """Runs resolution passes over a user's graph; never raises."""

    def __init__(self, knowledge_graph, memory_events, settings: "ResolutionSettings"):
        """
        Args:
            knowledge_graph: KnowledgeGraphService (storage + apply path).
            memory_events: MemoryEventService (event-first decisions).
            settings: Validated ResolutionSettings.
        """
        self.knowledge_graph = knowledge_graph
        self.memory_events = memory_events
        self.settings = settings

    async def resolve_user(
        self,
        user_id: Any,
        caused_by: Optional[int] = None,
    ) -> Dict[str, int]:
        """
        Run one resolution pass for a user. Failure-isolated: any error is
        observed and an empty result returned -- resolution can never
        break ingestion or a synthesis cadence.

        Returns:
            {"merged": n, "flagged": n} decision counts for this pass.
        """
        try:
            return await self._resolve(str(user_id), caused_by)
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_SYNTHESIS_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "user_id": str(user_id),
                    "pass": "entity_resolution",
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Entity resolution failed (isolated): {e}",
            )
            return {"merged": 0, "flagged": 0}

    async def _resolve(self, user_id: str, caused_by: Optional[int]) -> Dict[str, int]:
        if (
            not self.settings.enabled
            or self.knowledge_graph is None
            or self.memory_events is None
            or not getattr(self.memory_events, "enabled", False)
        ):
            return {"merged": 0, "flagged": 0}

        storage = self.knowledge_graph.storage
        neighbors = await self._neighbor_map(storage, user_id)
        counts = {"merged": 0, "flagged": 0}

        for entity_type in self.settings.entity_types:
            entities = await storage.list_entities(
                user_id,
                entity_type=entity_type,
                status=STATUS_ACTIVE,
                limit=self.settings.max_entities,
            )
            # The user's canonical self node is never a merge candidate:
            # every self-referential fact hangs off it, so a false match
            # would fold a contact into the user themselves.
            entities = [
                entity
                for entity in entities
                if entity["name"].strip().lower() != USER_ENTITY_NAME.lower()
            ]
            entities.sort(key=lambda entity: entity["id"])
            resolved_away: Set[int] = set()

            for i, a in enumerate(entities):
                if a["id"] in resolved_away:
                    continue
                for b in entities[i + 1 :]:
                    if b["id"] in resolved_away or a["id"] in resolved_away:
                        continue
                    shared = len(
                        (neighbors.get(a["id"], set()) - {b["id"]})
                        & (neighbors.get(b["id"], set()) - {a["id"]})
                    )
                    score, signals = score_identity_match(a, b, shared_neighbors=shared)
                    if score >= self.settings.auto_merge_threshold:
                        decision = DECISION_MERGED
                    elif score >= self.settings.flag_threshold:
                        decision = DECISION_FLAGGED
                    else:
                        continue

                    canonical, duplicate = pick_canonical(a, b)
                    applied = await self._record_and_apply(
                        user_id,
                        entity_type,
                        canonical,
                        duplicate,
                        decision,
                        score,
                        signals,
                        caused_by,
                    )
                    if applied:
                        counts[decision] += 1
                        if decision == DECISION_MERGED:
                            resolved_away.add(duplicate["id"])
        return counts

    async def _neighbor_map(self, storage, user_id: str) -> Dict[int, Set[int]]:
        """Undirected adjacency sets over the user's active edges."""
        neighbors: Dict[int, Set[int]] = {}
        for edge in await storage.iter_edges(user_id):
            neighbors.setdefault(edge["from_entity_id"], set()).add(edge["to_entity_id"])
            neighbors.setdefault(edge["to_entity_id"], set()).add(edge["from_entity_id"])
        return neighbors

    async def _record_and_apply(
        self,
        user_id: str,
        entity_type: str,
        canonical: Dict[str, Any],
        duplicate: Dict[str, Any],
        decision: str,
        score: float,
        signals: List[str],
        caused_by: Optional[int],
    ) -> bool:
        """Append the decision event (idempotent) and apply it once.

        Returns True when a NEW decision was recorded and applied; False
        for pairs already resolved (duplicate source_id) or when the
        substrate rejected the append.
        """
        payload = {
            "decision": decision,
            "entity_type": entity_type,
            "canonical_name": canonical["name"],
            "duplicate_name": duplicate["name"],
            "score": round(score, 4),
            "signals": signals,
        }
        source_id = pair_source_id(entity_type, canonical["name"], duplicate["name"], decision)
        try:
            event, created = await self.memory_events.storage.append(
                user_id=user_id,
                event_type=EVENT_ENTITY_RESOLVED,
                payload=payload,
                source=SOURCE_SYNTHESIS,
                source_id=source_id,
                caused_by=caused_by,
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_EVENT_APPEND_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "user_id": user_id,
                    "memory_event_type": EVENT_ENTITY_RESOLVED,
                    "source": SOURCE_SYNTHESIS,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Entity resolution event append failed: {e}",
            )
            return False
        if not created:
            # Already decided (this run or a previous ingestion): the
            # substrate's idempotency key guarantees one merge per pair.
            return False

        if getattr(self.memory_events, "event_first", False):
            await self.memory_events.apply_event(event)
        else:
            await self.knowledge_graph.apply_entity_resolution(
                user_id, payload, event_id=event["id"]
            )

        observability.observe(
            event_type=(
                observability.ConversationEvents.MEMORY_ENTITY_MERGED
                if decision == DECISION_MERGED
                else observability.ConversationEvents.MEMORY_ENTITY_FLAGGED
            ),
            level=observability.EventLevel.INFO,
            data={
                "user_id": user_id,
                "entity_type": entity_type,
                "canonical_name": canonical["name"],
                "duplicate_name": duplicate["name"],
                "score": payload["score"],
                "signals": signals,
                "memory_event_id": event["id"],
            },
            description=(
                f"Entity resolution {decision}: {duplicate['name']!r} -> "
                f"{canonical['name']!r} (score {payload['score']})"
            ),
        )
        return True
