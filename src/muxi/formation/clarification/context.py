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

    # Maximum depth for nested clarifications (prevents infinite loops)
    MAX_DEPTH = 2

    def __init__(self, original_intent: str, session_id: str):
        self.original_intent = original_intent
        self.collected_params: Dict[str, Any] = {}
        self.clarification_chain: List[Dict[str, Any]] = []  # History of Q&A pairs
        self.conversation_history: List[Dict[str, Any]] = []  # Already exists!
        self.depth = 0  # Track clarification nesting level (clamped at MAX_DEPTH)
        self.session_id = session_id
        self.timestamp = datetime.now()

    def can_fulfill(self) -> bool:
        """Check if we have minimum required info."""
        # TODO: This is a temporary heuristic that's too permissive and may cause false positives.
        # Replace with a more precise validator that:
        # 1. Checks for required parameters based on the original intent
        # 2. Validates parameter completeness and compatibility
        # 3. Uses LLM or rule-based logic to assess actual fulfillment capability
        # Current implementation: any collected param = can fulfill (not accurate!)
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
        """
        Add a question-answer pair to the chain.

        Note: This method records the Q&A at the current depth level.
        To increment depth (for nested clarifications), use increment_depth() first.

        Args:
            question: The clarification question asked
            answer: The user's response
            intent_type: The type of intent (ANSWER, REJECT, etc.)
        """
        qa_entry = {
            "timestamp": datetime.now(),
            "question": question,
            "answer": answer,
            "intent_type": intent_type,
            "depth": self.depth
        }

        # Update both clarification_chain and conversation_history
        self.clarification_chain.append(qa_entry)

        # Add to conversation history in a format suitable for context
        self.conversation_history.append({
            "role": "assistant",
            "content": question,
            "timestamp": qa_entry["timestamp"]
        })
        self.conversation_history.append({
            "role": "user",
            "content": answer,
            "timestamp": datetime.now()
        })

    def increment_depth(self) -> bool:
        """
        Increment the clarification depth, clamping at MAX_DEPTH.

        Returns:
            bool: True if depth was incremented, False if already at max
        """
        if self.depth < self.MAX_DEPTH:
            self.depth += 1
            return True
        return False

    def decrement_depth(self) -> bool:
        """
        Decrement the clarification depth, stopping at 0.

        Returns:
            bool: True if depth was decremented, False if already at 0
        """
        if self.depth > 0:
            self.depth -= 1
            return True
        return False

    def is_at_max_depth(self) -> bool:
        """Check if we've reached the maximum clarification depth."""
        return self.depth >= self.MAX_DEPTH

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "original_message": self.original_intent,
            "session_id": self.session_id,
            "collected_params": self.collected_params,
            "clarification_chain": self.clarification_chain,
            "conversation_history": self.conversation_history,
            "depth": self.depth,
            "timestamp": self.timestamp.timestamp() if self.timestamp else None,
            "type": "multi_turn"  # To distinguish from old format
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional['ClarificationContext']:
        """
        Create from dictionary for backward compatibility.

        The session_id is read directly from the data dictionary to ensure
        consistency and avoid potential mismatches between separate arguments.

        Args:
            data: Dictionary containing the serialized ClarificationContext

        Returns:
            ClarificationContext instance or None if data is invalid
        """
        if not data or data.get("type") != "multi_turn":
            return None

        # Extract session_id from data to ensure consistency
        session_id = data.get("session_id")
        if not session_id:
            # If session_id is missing, we can't reconstruct the context properly
            return None

        context = cls(
            original_intent=data.get("original_message", ""),
            session_id=session_id
        )
        context.collected_params = data.get("collected_params", {})
        context.clarification_chain = data.get("clarification_chain", [])
        context.conversation_history = data.get("conversation_history", [])
        context.depth = data.get("depth", 0)

        # Restore timestamp if present
        timestamp_value = data.get("timestamp")
        if timestamp_value:
            context.timestamp = datetime.fromtimestamp(timestamp_value)

        return context
