from typing import Dict, Any, List
import json
from .base import BaseFormatter


class ProtobufFormatter(BaseFormatter):
    """Protocol Buffers formatter for structured data serialization."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.message_type = config.get("message_type")

    @property
    def content_type(self) -> str:
        return "application/x-protobuf"

    def format_event(self, event: Dict[str, Any]) -> bytes:
        # For now, serialize as JSON bytes until protobuf schema is defined
        # TODO: Implement proper protobuf schema and message generation
        enriched = self._add_metadata(event)
        return json.dumps(enriched).encode('utf-8')

    def format_batch(self, events: List[Dict[str, Any]]) -> bytes:
        # For batches, serialize as JSON array
        enriched_events = [self._add_metadata(event) for event in events]
        return json.dumps(enriched_events).encode('utf-8')
