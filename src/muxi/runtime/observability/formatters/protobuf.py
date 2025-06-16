import json
from typing import Dict, Any, List
from .base import BaseFormatter

try:
    import google.protobuf  # noqa: F401
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False


class ProtobufFormatter(BaseFormatter):
    """Protocol Buffers formatter for schema-based serialization."""

    @property
    def content_type(self) -> str:
        return "application/x-protobuf"

    def format_event(self, event: Dict[str, Any]) -> bytes:
        if not PROTOBUF_AVAILABLE:
            raise ImportError("protobuf library not available")

        # For now, serialize as JSON bytes until protobuf schema is defined
        # TODO: Implement proper protobuf schema and message generation
        enriched = self._add_metadata(event)
        return json.dumps(enriched).encode('utf-8')

    def format_batch(self, events: List[Dict[str, Any]]) -> bytes:
        if not PROTOBUF_AVAILABLE:
            raise ImportError("protobuf library not available")

        # For now, serialize as JSON bytes until protobuf schema is defined
        # TODO: Implement proper protobuf schema and message generation
        enriched_events = [self._add_metadata(event) for event in events]
        return json.dumps(enriched_events).encode('utf-8')
