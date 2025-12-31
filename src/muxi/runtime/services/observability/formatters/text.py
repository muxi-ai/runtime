from typing import Dict, Any, List
from .base import BaseFormatter


class TextFormatter(BaseFormatter):
    """Human-readable text formatter."""

    @property
    def content_type(self) -> str:
        return "text/plain"

    def format_event(self, event: Dict[str, Any]) -> str:
        timestamp = event.get("timestamp", "")
        level = event.get("level", "INFO").upper()
        event_type = event.get("event", "unknown")
        request_id = event.get("request", {}).get("id", "")

        # Extract message from data
        data = event.get("data", {})
        message = data.get("message", str(data))

        parts = [timestamp, level, event_type]
        if request_id:
            parts.append(f"[{request_id}]")
        parts.append(message)

        return " | ".join(parts)

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        lines = []
        for event in events:
            lines.append(self.format_event(event))
        return "\n".join(lines)
