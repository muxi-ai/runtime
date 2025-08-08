"""
Clarification context management for multi-turn clarification sequences.

This module provides the ClarificationContext class which tracks the state
of a clarification sequence, including the original intent, collected parameters,
and the chain of questions and answers.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class ClarificationContext:
    """Simple dataclass for clarification context with multi-turn support."""

    def __init__(self, original_intent: str, session_id: str):
        self.original_intent = original_intent
        self.collected_params: Dict[str, Any] = {}
        self.clarification_chain: List[Dict[str, Any]] = []  # History of Q&A pairs
        self.conversation_history: List[Dict[str, Any]] = []  # Already exists!
        self.depth = 0  # Track nesting (max 2)
        self.session_id = session_id
        self.timestamp = datetime.now()

    def can_fulfill(self) -> bool:
        """Check if we have minimum required info."""
        # Simple heuristic: if we have any collected params, we might be able to fulfill
        # This will be enhanced with LLM checking
        return len(self.collected_params) > 0

    def add_param(self, key: str, value: Any):
        """Add collected parameter."""
        self.collected_params[key] = value
        self.clarification_chain.append({
            "timestamp": datetime.now(),
            "param": key,
            "value": value
        })

    def add_qa_pair(self, question: str, answer: str, intent_type: str = "ANSWER"):
        """Add a question-answer pair to the chain."""
        self.clarification_chain.append({
            "timestamp": datetime.now(),
            "question": question,
            "answer": answer,
            "intent_type": intent_type,
            "depth": self.depth
        })

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "original_message": self.original_intent,
            "session_id": self.session_id,
            "collected_params": self.collected_params,
            "clarification_chain": self.clarification_chain,
            "depth": self.depth,
            "timestamp": self.timestamp.timestamp() if self.timestamp else None,
            "type": "multi_turn"  # To distinguish from old format
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], session_id: str) -> Optional['ClarificationContext']:
        """Create from dictionary for backward compatibility."""
        if not data or data.get("type") != "multi_turn":
            return None

        context = cls(
            original_intent=data.get("original_message", ""),
            session_id=session_id
        )
        context.collected_params = data.get("collected_params", {})
        context.clarification_chain = data.get("clarification_chain", [])
        context.depth = data.get("depth", 0)
        return context
