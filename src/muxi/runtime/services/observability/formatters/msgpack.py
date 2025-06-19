from typing import Dict, Any, List
import msgpack
from .base import BaseFormatter


class MsgPackFormatter(BaseFormatter):
    """MsgPack binary formatter for efficient transmission."""

    @property
    def content_type(self) -> str:
        return "application/msgpack"

    def format_event(self, event: Dict[str, Any]) -> bytes:
        enriched = self._add_metadata(event)
        return msgpack.packb(enriched)

    def format_batch(self, events: List[Dict[str, Any]]) -> bytes:
        enriched_events = [self._add_metadata(event) for event in events]
        return msgpack.packb(enriched_events)
