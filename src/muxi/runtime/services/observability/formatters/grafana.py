import json
import time
from typing import Dict, Any, List
from datetime import datetime
from .base import BaseFormatter


class GrafanaLokiFormatter(BaseFormatter):
    """Grafana Loki log format."""

    @property
    def content_type(self) -> str:
        return "application/json"

    def format_event(self, event: Dict[str, Any]) -> str:
        # Single log entry for Loki
        timestamp_ns = self._to_nanoseconds(event.get("timestamp"))
        line = self._create_log_line(event)

        loki_stream = {
            "stream": {
                "formation_id": self.formation_id,
                "service": self.service_name,
                "level": event.get("level", "info"),
                "event_type": event.get("event", "unknown"),
            },
            "values": [[str(timestamp_ns), line]],
        }

        return json.dumps({"streams": [loki_stream]})

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        # Group events by stream labels
        streams = {}

        for event in events:
            labels = (
                self.formation_id,
                self.service_name,
                event.get("level", "info"),
                event.get("event", "unknown"),
            )

            if labels not in streams:
                streams[labels] = {
                    "stream": {
                        "formation_id": labels[0],
                        "service": labels[1],
                        "level": labels[2],
                        "event_type": labels[3],
                    },
                    "values": [],
                }

            timestamp_ns = self._to_nanoseconds(event.get("timestamp"))
            line = self._create_log_line(event)
            streams[labels]["values"].append([str(timestamp_ns), line])

        return json.dumps({"streams": list(streams.values())})

    def _to_nanoseconds(self, timestamp_str: str) -> int:
        """Convert ISO timestamp to nanoseconds."""
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1_000_000_000)
            except Exception:
                pass
        return int(time.time() * 1_000_000_000)

    def _create_log_line(self, event: Dict[str, Any]) -> str:
        """Create readable log line for Loki."""
        data = event.get("data", {})
        message = data.get("message", json.dumps(data))

        request_id = event.get("request", {}).get("id", "")
        if request_id:
            return f"[{request_id}] {message}"
        return message
