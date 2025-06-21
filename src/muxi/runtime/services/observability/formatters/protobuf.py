from typing import Dict, Any, List
import json
from .base import BaseFormatter

try:
    from ..proto import observability_pb2
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False


class ProtobufFormatter(BaseFormatter):
    """Protocol Buffers formatter for binary serialization."""

    @property
    def content_type(self) -> str:
        return "application/x-protobuf"

    def format_event(self, event: Dict[str, Any]) -> bytes:
        """Convert event dict to protobuf and serialize."""
        if not PROTOBUF_AVAILABLE:
            # Fallback to JSON if protobuf not available
            enriched = self._add_metadata(event)
            return json.dumps(enriched).encode('utf-8')

        # Create protobuf message
        pb_event = observability_pb2.ObservabilityEvent()

        # Set basic fields
        pb_event.id = event.get("id", "")
        pb_event.muxi_version = event.get("muxi_version", "")
        pb_event.server = event.get("server", "")
        pb_event.level = self._convert_level(event.get("level", "INFO"))
        pb_event.event_type = self._convert_event_type(event.get("event_type", ""))

        # Set timestamp
        if "timestamp" in event:
            pb_event.timestamp.FromSeconds(int(event["timestamp"]))

        # Set data using the EventData message structure
        if "data" in event:
            event_data = observability_pb2.EventData()
            if "description" in event["data"]:
                event_data.description = event["data"]["description"]
            pb_event.data.CopyFrom(event_data)

        return pb_event.SerializeToString()

    def format_batch(self, events: List[Dict[str, Any]]) -> bytes:
        """Format multiple events as protobuf batch."""
        if not PROTOBUF_AVAILABLE:
            enriched_events = [self._add_metadata(event) for event in events]
            return json.dumps(enriched_events).encode('utf-8')

        # Simple approach: serialize each event and concatenate
        # In practice, you might want a proper batch message type
        batch_data = b""
        for event in events:
            event_data = self.format_event(event)
            # Add length prefix for parsing
            batch_data += len(event_data).to_bytes(4, 'big') + event_data

        return batch_data

    def _convert_level(self, level: str) -> int:
        """Convert string level to protobuf enum."""
        level_map = {
            "DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3
        }
        return level_map.get(level.upper(), 1)  # Default to INFO

    def _convert_event_type(self, event_type: str) -> int:
        """Convert string event type to protobuf enum."""
        # Simple mapping - in practice you'd want this from your schema
        type_map = {
            "SYSTEM_STARTUP": 0, "SYSTEM_SHUTDOWN": 1,
            "CONVERSATION_MESSAGE": 10, "MCP_TOOL_CALL": 20,
        }
        return type_map.get(event_type, 0)  # Default to first type
