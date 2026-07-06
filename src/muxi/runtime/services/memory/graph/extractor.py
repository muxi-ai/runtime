# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Graph Extractor - Entity/Relationship Extraction
# Description:  LLM-based extraction of structured graph facts
# Role:         Turns conversation turns into typed entities and relationships
# Usage:        Used by KnowledgeGraphService for real-time and periodic passes
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 1. Runs alongside (never instead of) the existing
# flat-fact MemoryExtractor: the flat pipeline keeps feeding the rich
# collections, this one adds graph structure. Two passes share the module:
#
# - Real-time: single conversation turn, high confidence threshold (0.9).
# - Periodic: batch of recent turns with full context, lower threshold (0.7).
#
# The extraction model is resolved by the caller the same way the flat
# extractor resolves it (formation capability model / overlord default), and
# every failure is parsed down to an empty result -- extraction must never
# break a chat turn.
# =============================================================================

from typing import Any, Dict, List, Optional

from ....utils.fastjson import json
from .models import ENTITY_TYPES, RELATIONSHIP_TYPES

# Canonical name the prompt uses for the user themselves, so self-referential
# facts ("I live in London") produce a stable graph node per user.
USER_ENTITY_NAME = "User"
USER_ENTITY_TYPE = "person"


class KnowledgeGraphExtractor:
    """Extracts typed entities and relationships from conversation text."""

    def __init__(self, confidence_threshold: float = 0.9):
        """
        Args:
            confidence_threshold: Minimum confidence (0.0-1.0) for extracted
                items to be kept. PRD defaults: 0.9 real-time, 0.7 periodic.
        """
        self.confidence_threshold = confidence_threshold

    async def extract(
        self,
        conversation: str,
        model,
        confidence_threshold: Optional[float] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run one extraction pass over conversation text.

        Args:
            conversation: Conversation text (one turn or a batch of turns).
            model: LLM instance exposing ``generate_text`` (resolved by the
                caller via the formation's capability model resolution).
            confidence_threshold: Optional per-call override of the
                instance threshold.

        Returns:
            Dict with ``entities`` and ``relationships`` lists. Empty lists
            on any model or parse failure.
        """
        threshold = (
            self.confidence_threshold if confidence_threshold is None else confidence_threshold
        )
        prompt = self.build_prompt(conversation)

        # Caching disabled for the same reason as the flat extractor: similar
        # prompts for different messages must not return stale extractions.
        response = await model.generate_text(prompt, caching=False)
        return self.parse_response(response, threshold)

    def build_prompt(self, conversation: str) -> str:
        """Build the graph extraction prompt for the LLM."""
        entity_lines = "\n".join(f"- {name}: {desc}" for name, desc in ENTITY_TYPES.items())
        rel_lines = "\n".join(f"- {name}: {desc}" for name, desc in RELATIONSHIP_TYPES.items())

        return (
            "Extract a knowledge graph from the following conversation: entities and the "
            "relationships between them, as stated by the user about themselves and their "
            "world.\n\n"
            "ENTITY TYPES:\n"
            f"{entity_lines}\n\n"
            "RELATIONSHIP TYPES:\n"
            f"{rel_lines}\n\n"
            "RULES:\n"
            f'- Refer to the user themselves as the entity named "{USER_ENTITY_NAME}" '
            f'(type "{USER_ENTITY_TYPE}").\n'
            "- ONLY extract facts the user explicitly states. Questions, hypotheticals, and "
            "general topic discussion are NOT facts about the user.\n"
            "- DO NOT extract sensitive information (passwords, credit cards, government IDs, "
            "financial or medical details).\n"
            "- Every relationship endpoint must appear in the entities list.\n"
            "- Assign each item a confidence score between 0.0 and 1.0.\n"
            "- If there is nothing to extract, return empty arrays.\n\n"
            "Respond with a JSON object in exactly this structure:\n"
            "{\n"
            '  "entities": [\n'
            '    {"name": "Automaze", "type": "company", "attributes": {"user_role": '
            '"founder"}, "confidence": 0.95}\n'
            "  ],\n"
            '  "relationships": [\n'
            '    {"from": "User", "from_type": "person", "to": "Automaze", '
            '"to_type": "company", "type": "founded", "confidence": 0.95}\n'
            "  ]\n"
            "}\n\n"
            f"Conversation:\n{conversation}\n"
        )

    def parse_response(self, response: str, threshold: float) -> Dict[str, List[Dict[str, Any]]]:
        """
        Parse the LLM response into validated entities and relationships.

        Tolerates fenced code blocks and drops malformed or low-confidence
        items instead of raising.
        """
        empty: Dict[str, List[Dict[str, Any]]] = {"entities": [], "relationships": []}
        if not response or not isinstance(response, str):
            return empty

        clean = response.strip()
        if clean.startswith("```"):
            first_newline = clean.find("\n")
            if first_newline > 0:
                clean = clean[first_newline + 1 :]
            if clean.endswith("```"):
                clean = clean[:-3].strip()

        try:
            payload = json.loads(clean)
        except json.JSONDecodeError:
            return empty
        if not isinstance(payload, dict):
            return empty

        entities: List[Dict[str, Any]] = []
        for item in payload.get("entities") or []:
            entity = self._validate_entity(item, threshold)
            if entity:
                entities.append(entity)

        relationships: List[Dict[str, Any]] = []
        for item in payload.get("relationships") or []:
            relationship = self._validate_relationship(item, threshold)
            if relationship:
                relationships.append(relationship)

        return {"entities": entities, "relationships": relationships}

    @staticmethod
    def _validate_entity(item: Any, threshold: float) -> Optional[Dict[str, Any]]:
        """Validate one raw entity item; return normalized dict or None."""
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        entity_type = item.get("type")
        if not isinstance(name, str) or not name.strip():
            return None
        if not isinstance(entity_type, str) or not entity_type.strip():
            return None
        confidence = _as_confidence(item.get("confidence"))
        if confidence is None or confidence < threshold:
            return None
        attributes = item.get("attributes")
        return {
            "name": name.strip()[:255],
            "type": entity_type,
            "attributes": attributes if isinstance(attributes, dict) else {},
            "confidence": confidence,
        }

    @staticmethod
    def _validate_relationship(item: Any, threshold: float) -> Optional[Dict[str, Any]]:
        """Validate one raw relationship item; return normalized dict or None."""
        if not isinstance(item, dict):
            return None
        from_name = item.get("from")
        to_name = item.get("to")
        rel_type = item.get("type")
        if not isinstance(from_name, str) or not from_name.strip():
            return None
        if not isinstance(to_name, str) or not to_name.strip():
            return None
        if not isinstance(rel_type, str) or not rel_type.strip():
            return None
        confidence = _as_confidence(item.get("confidence"))
        if confidence is None or confidence < threshold:
            return None
        attributes = item.get("attributes")
        from_type = item.get("from_type")
        to_type = item.get("to_type")
        return {
            "from": from_name.strip()[:255],
            "from_type": from_type if isinstance(from_type, str) and from_type.strip() else None,
            "to": to_name.strip()[:255],
            "to_type": to_type if isinstance(to_type, str) and to_type.strip() else None,
            "type": rel_type,
            "attributes": attributes if isinstance(attributes, dict) else {},
            "confidence": confidence,
        }


def _as_confidence(value: Any) -> Optional[float]:
    """Coerce a confidence value to a float in [0.0, 1.0], or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence < 0.0 or confidence > 1.0:
        return None
    return confidence
