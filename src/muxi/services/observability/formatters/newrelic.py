import json
import time
from typing import Dict, Any, List
from datetime import datetime
from .base import BaseFormatter


class NewRelicFormatter(BaseFormatter):
    """New Relic Logs JSON formatter."""

    @property
    def content_type(self) -> str:
        return "application/json"

    def format_event(self, event: Dict[str, Any]) -> str:
        # New Relic log format
        nr_event = {
            "timestamp": int(self._to_milliseconds(event.get("timestamp"))),
            "level": event.get("level", "INFO").upper(),
            "message": self._extract_message(event),
            "service.name": self.service_name,
            "service.version": self.version,
            "formation.id": self.formation_id,
            "event.type": event.get("event"),
            "log.source": "muxi-runtime",
        }

        # Add custom attributes
        data = event.get("data", {})
        for key, value in data.items():
            nr_event[f"custom.{key}"] = value

        return json.dumps(nr_event)

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        # New Relic expects array of log objects
        formatted_events = [json.loads(self.format_event(event)) for event in events]
        return json.dumps({"logs": formatted_events})

    def _to_milliseconds(self, timestamp_str: str) -> int:
        """Convert ISO timestamp to milliseconds."""
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1000)
            except Exception:
                pass
        return int(time.time() * 1000)
