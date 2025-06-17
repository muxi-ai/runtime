from abc import ABC, abstractmethod
from typing import Dict, Any, List
from enum import Enum


class TransportStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


class BaseTransport(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", True)
        self.status = TransportStatus.DISABLED
        self.error_count = 0
        self.last_error = None

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the transport. Return True if successful."""
        pass

    @abstractmethod
    async def send_event(self, event: Dict[str, Any]) -> bool:
        """Send a single event. Return True if successful."""
        pass

    @abstractmethod
    async def send_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Send a batch of events. Return True if successful."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass

    async def health_check(self) -> TransportStatus:
        """Check transport health."""
        return self.status
