import json
from typing import Dict, Any, List
from .base import BaseFormatter


class JSONLFormatter(BaseFormatter):
    """JSON Lines formatter - one JSON object per line."""

    @property
    def content_type(self) -> str:
        return "application/jsonl"

    def format_event(self, event: Dict[str, Any]) -> str:
        enriched = self._add_metadata(event)
        return json.dumps(enriched, separators=(",", ":"))

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        lines = []
        for event in events:
            lines.append(self.format_event(event))
        return "\n".join(lines)
