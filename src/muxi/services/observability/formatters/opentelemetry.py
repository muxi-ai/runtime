import json
import time
from typing import Dict, Any, List
from datetime import datetime
from .base import BaseFormatter


class OpenTelemetryFormatter(BaseFormatter):
    """OpenTelemetry logs format (OTLP)."""

    @property
    def content_type(self) -> str:
        return "application/json"

    def format_event(self, event: Dict[str, Any]) -> str:
        # OpenTelemetry log record format
        log_record = {
            "timeUnixNano": str(self._to_nanoseconds(event.get("timestamp"))),
            "severityNumber": self._severity_to_number(event.get("level")),
            "severityText": event.get("level", "INFO").upper(),
            "body": {"stringValue": self._extract_message(event)},
            "attributes": self._convert_attributes(event),
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": self.service_name}},
                    {"key": "service.version", "value": {"stringValue": self.version}},
                    {"key": "formation.id", "value": {"stringValue": self.formation_id}},
                ]
            },
        }

        return json.dumps(
            {
                "resourceLogs": [
                    {
                        "resource": log_record["resource"],
                        "scopeLogs": [
                            {
                                "scope": {"name": "muxi.observability"},
                                "logRecords": [log_record],
                            }
                        ],
                    }
                ]
            }
        )

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        log_records = []

        for event in events:
            log_record = {
                "timeUnixNano": str(self._to_nanoseconds(event.get("timestamp"))),
                "severityNumber": self._severity_to_number(event.get("level")),
                "severityText": event.get("level", "INFO").upper(),
                "body": {"stringValue": self._extract_message(event)},
                "attributes": self._convert_attributes(event),
            }
            log_records.append(log_record)

        return json.dumps(
            {
                "resourceLogs": [
                    {
                        "resource": {
                            "attributes": [
                                {
                                    "key": "service.name",
                                    "value": {"stringValue": self.service_name},
                                },
                                {"key": "service.version", "value": {"stringValue": self.version}},
                                {
                                    "key": "formation.id",
                                    "value": {"stringValue": self.formation_id},
                                },
                            ]
                        },
                        "scopeLogs": [
                            {
                                "scope": {"name": "muxi.observability"},
                                "logRecords": log_records,
                            }
                        ],
                    }
                ]
            }
        )

    def _severity_to_number(self, level: str) -> int:
        """Convert log level to OpenTelemetry severity number."""
        mapping = {"TRACE": 1, "DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17, "FATAL": 21}
        return mapping.get(level.upper() if level else "INFO", 9)

    def _to_nanoseconds(self, timestamp_str: str) -> int:
        """Convert ISO timestamp to nanoseconds."""
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1_000_000_000)
            except Exception:
                pass
        return int(time.time() * 1_000_000_000)

    def _convert_attributes(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert event data to OpenTelemetry attributes."""
        attributes = []

        # Add event type
        if event.get("event"):
            attributes.append({"key": "event.type", "value": {"stringValue": event["event"]}})

        # Add request ID
        request_id = event.get("request", {}).get("id")
        if request_id:
            attributes.append({"key": "request.id", "value": {"stringValue": request_id}})

        # Add custom data attributes
        data = event.get("data", {})
        for key, value in data.items():
            if isinstance(value, str):
                attributes.append({"key": f"custom.{key}", "value": {"stringValue": value}})
            elif isinstance(value, (int, float)):
                attributes.append({"key": f"custom.{key}", "value": {"doubleValue": float(value)}})
            elif isinstance(value, bool):
                attributes.append({"key": f"custom.{key}", "value": {"boolValue": value}})

        return attributes
