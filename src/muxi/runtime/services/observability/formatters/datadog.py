import json
from typing import Dict, Any, List
from .base import BaseFormatter


class DatadogFormatter(BaseFormatter):
    """Datadog-compatible JSON formatter."""

    @property
    def content_type(self) -> str:
        return "application/json"

    def format_event(self, event: Dict[str, Any]) -> str:
        # Transform to Datadog format
        datadog_event = {
            "timestamp": event.get("timestamp"),
            "level": event.get("level", "info").lower(),
            "message": self._extract_message(event),
            "service": self.service_name,
            "ddsource": "muxi",
            "ddtags": f"formation_id:{self.formation_id},version:{self.version}",
            "attributes": {
                "event_type": event.get("event"),
                "request_id": event.get("request", {}).get("id"),
                "agent_id": event.get("data", {}).get("agent_id"),
                **event.get("data", {}),
            },
        }
        return json.dumps(datadog_event)

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        formatted_events = [json.loads(self.format_event(event)) for event in events]
        return json.dumps(formatted_events)
