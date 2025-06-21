import json
import time
from typing import Dict, Any, List
from datetime import datetime
from .base import BaseFormatter


class SplunkFormatter(BaseFormatter):
    """Splunk HTTP Event Collector formatter."""

    @property
    def content_type(self) -> str:
        return "application/json"

    def format_event(self, event: Dict[str, Any]) -> str:
        # Splunk HEC format
        hec_event = {
            "time": self._convert_timestamp(event.get("timestamp")),
            "source": "muxi-runtime",
            "sourcetype": "muxi:observability",
            "index": self.config.get("index", "main"),
            "event": {
                "level": event.get("level"),
                "event_type": event.get("event"),
                "formation_id": self.formation_id,
                "service": self.service_name,
                **event.get("data", {}),
            },
        }
        return json.dumps(hec_event)

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        lines = []
        for event in events:
            lines.append(self.format_event(event))
        return "\n".join(lines)

    def _convert_timestamp(self, timestamp_str: str) -> float:
        """Convert ISO timestamp to Unix epoch."""
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                return dt.timestamp()
            except Exception:
                pass
        return time.time()
