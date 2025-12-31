from typing import Dict, Any, List
import json
from .base import BaseFormatter

try:
    from google.protobuf.struct_pb2 import Struct

    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False


class ProtobufFormatter(BaseFormatter):
    """Protocol Buffers formatter for binary serialization."""

    @property
    def content_type(self) -> str:
        return "application/x-protobuf"

    def format_event(self, event: Dict[str, Any]) -> bytes:
        """Convert event dict to protobuf binary format."""
        enriched = self._add_metadata(event)

        if not PROTOBUF_AVAILABLE:
            # Fallback to JSON if protobuf not available
            return json.dumps(enriched).encode("utf-8")

        # Use protobuf Struct for arbitrary dict serialization (like msgpack)
        struct = Struct()
        struct.update(enriched)
        return struct.SerializeToString()

    def format_batch(self, events: List[Dict[str, Any]]) -> bytes:
        """Format multiple events as protobuf batch."""
        enriched_events = [self._add_metadata(event) for event in events]

        if not PROTOBUF_AVAILABLE:
            return json.dumps(enriched_events).encode("utf-8")

        # Serialize list of events as protobuf
        struct = Struct()
        struct.update({"events": enriched_events})
        return struct.SerializeToString()
