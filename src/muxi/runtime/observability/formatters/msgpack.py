from typing import Dict, Any, List
from .base import BaseFormatter

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False


class MsgPackFormatter(BaseFormatter):
    """MsgPack binary formatter for efficient transmission."""

    @property
    def content_type(self) -> str:
        return "application/msgpack"

    def format_event(self, event: Dict[str, Any]) -> bytes:
        if not MSGPACK_AVAILABLE:
            raise ImportError("msgpack library not available")

        enriched = self._add_metadata(event)
        return msgpack.packb(enriched)

    def format_batch(self, events: List[Dict[str, Any]]) -> bytes:
        if not MSGPACK_AVAILABLE:
            raise ImportError("msgpack library not available")

        enriched_events = [self._add_metadata(event) for event in events]
        return msgpack.packb(enriched_events)
