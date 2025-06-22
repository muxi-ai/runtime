from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional
from ....utils.datetime_utils import utc_now_iso


class BaseFormatter(ABC):
    """Abstract base class for event formatters."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.formation_id = self.config.get("formation_id", "unknown")
        self.service_name = self.config.get("service_name", "muxi-runtime")
        self.version = self.config.get("version", "1.0.0")

    @abstractmethod
    def format_event(self, event: Dict[str, Any]) -> Union[str, bytes]:
        """Format a single event."""
        pass

    @abstractmethod
    def format_batch(self, events: List[Dict[str, Any]]) -> Union[str, bytes]:
        """Format a batch of events."""
        pass

    @property
    @abstractmethod
    def content_type(self) -> str:
        """Return the content type for HTTP headers."""
        pass

    def _add_metadata(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Add common metadata to events."""
        enriched = event.copy()
        enriched.update(
            {
                "formation_id": self.formation_id,
                "service": self.service_name,
                "version": self.version,
                "_timestamp": utc_now_iso(),
            }
        )
        return enriched

    def _extract_message(self, event: Dict[str, Any]) -> str:
        """Extract message from event data."""
        data = event.get("data", {})
        return data.get("message", str(data))
