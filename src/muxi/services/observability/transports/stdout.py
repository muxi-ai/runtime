import json
from typing import Dict, Any, List
from .base import BaseTransport, TransportStatus


class StdoutTransport(BaseTransport):
    """Console output transport for development and debugging."""

    async def initialize(self) -> bool:
        """Initialize stdout transport."""
        try:
            self.status = TransportStatus.HEALTHY
            return True
        except Exception as e:
            self.last_error = str(e)
            self.status = TransportStatus.FAILED
            return False

    async def send_event(self, event: Dict[str, Any]) -> bool:
        """Send single event to stdout."""
        return await self._write_events([event])

    async def send_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Send batch of events to stdout."""
        return await self._write_events(events)

    async def _write_events(self, events: List[Dict[str, Any]]) -> bool:
        """Write events to stdout in JSON-L format."""
        try:
            for event in events:
                event_line = json.dumps(event, separators=(",", ":"))
                print(event_line, flush=True)
            return True
        except Exception as e:
            self.last_error = str(e)
            self.error_count += 1
            if self.error_count > 3:
                self.status = TransportStatus.FAILED
            return False

    async def close(self) -> None:
        """Clean up stdout transport (no-op)."""
        pass
