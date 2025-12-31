import json
import hashlib
from typing import Dict, Any, List, Optional


class AgentCardHasher:
    """Generate consistent hashes for agent cards and tasks for cache keys."""

    @staticmethod
    def hash_agent_card(agent_card: Dict[str, Any]) -> str:
        """Hash relevant fields of an agent card for cache invalidation."""
        relevant_fields = {
            "id": agent_card.get("id", ""),
            "capabilities": sorted(agent_card.get("capabilities", [])),
            "tools": sorted([t.get("name", "") for t in agent_card.get("tools", [])])
        }
        normalized = json.dumps(relevant_fields, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    @staticmethod
    def hash_agent_collection(agent_cards: List[Dict[str, Any]]) -> str:
        """Hash a collection of agent cards to detect changes."""
        sorted_cards = sorted(agent_cards, key=lambda x: x.get("id", ""))
        card_hashes = [AgentCardHasher.hash_agent_card(card) for card in sorted_cards]
        combined = "".join(card_hashes)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    @staticmethod
    def hash_task(task: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Hash task for consistent cache keys."""
        task_data = {
            "task": task.strip().lower(),
            "context": context or {}
        }
        normalized = json.dumps(task_data, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
