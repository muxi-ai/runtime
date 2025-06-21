"""
Protobuf Service Integration for MUXI Observability
Extends existing observability service to use protobuf for storage and transmission.
"""

import asyncio
import logging
import threading
from typing import Any, Dict, List

from .event_converter import ObservabilityEventConverter, ConversionError
from .build_protobuf import generate_protobuf_code


class ProtobufObservabilityService:
    """
    Enhanced observability service with protobuf support.

    Provides backwards compatibility while enabling efficient protobuf serialization.
    """

    def __init__(self,
                 fallback_to_json: bool = True,
                 auto_generate_protobuf: bool = True,
                 legacy_service=None):
        """
        Initialize protobuf observability service.

        Args:
            fallback_to_json: Fall back to JSON if protobuf conversion fails
            auto_generate_protobuf: Automatically generate protobuf code if needed
            legacy_service: Existing observability service for backwards compatibility
        """
        self.fallback_to_json = fallback_to_json
        self.auto_generate_protobuf = auto_generate_protobuf
        self.legacy_service = legacy_service
        self.logger = logging.getLogger(__name__)

        # Initialize converter
        self.converter = None
        self._init_converter()

        # Service state
        self.enabled = True
        self.stats = {
            'protobuf_events': 0,
            'json_fallback_events': 0,
            'conversion_errors': 0,
            'generation_attempts': 0
        }

    def _init_converter(self):
        """Initialize the event converter with error handling"""
        try:
            self.converter = ObservabilityEventConverter()
            self.logger.info("Protobuf event converter initialized successfully")
        except ConversionError as e:
            self.logger.warning(f"Protobuf converter initialization failed: {e}")

            if self.auto_generate_protobuf:
                self.logger.info("Attempting to auto-generate protobuf code...")
                self.stats['generation_attempts'] += 1

                if self._attempt_protobuf_generation():
                    try:
                        self.converter = ObservabilityEventConverter()
                        self.logger.info("Protobuf converter initialized after code generation")
                    except Exception as retry_e:
                        self.logger.error(f"Failed to initialize converter after generation: {retry_e}")
                        self.converter = None
                else:
                    self.logger.error("Failed to generate protobuf code")
                    self.converter = None
            else:
                self.converter = None

    def _attempt_protobuf_generation(self) -> bool:
        """Attempt to generate protobuf code automatically"""
        try:
            success = generate_protobuf_code()
            if success:
                self.logger.info("Protobuf code generation successful")
                return True
            else:
                self.logger.error("Protobuf code generation failed")
                return False
        except Exception as e:
            self.logger.error(f"Exception during protobuf generation: {e}")
            return False

    async def log_event(self, event_data: Dict[str, Any],
                        format_preference: str = "protobuf") -> bool:
        """
        Log observability event with format preference.

        Args:
            event_data: Event data in JSON format
            format_preference: Preferred format ("protobuf" or "json")

        Returns:
            True if event was logged successfully
        """
        if not self.enabled:
            return False

        # Try protobuf format first if preferred and converter available
        if format_preference == "protobuf" and self.converter:
            try:
                pb_event = self.converter.json_to_protobuf(event_data)
                success = await self._store_protobuf_event(pb_event)
                if success:
                    self.stats['protobuf_events'] += 1
                    self.logger.debug(f"Event {event_data.get('id', 'unknown')} logged as protobuf")
                    return True
            except ConversionError as e:
                self.logger.warning(f"Protobuf conversion failed for event {event_data.get('id', 'unknown')}: {e}")
                self.stats['conversion_errors'] += 1

        # Fall back to JSON format
        if self.fallback_to_json:
            success = await self._store_json_event(event_data)
            if success:
                self.stats['json_fallback_events'] += 1
                self.logger.debug(f"Event {event_data.get('id', 'unknown')} logged as JSON")
                return True

        self.logger.error(f"Failed to log event {event_data.get('id', 'unknown')} in any format")
        return False

    async def _store_protobuf_event(self, pb_event) -> bool:
        """Store protobuf event (placeholder for actual storage implementation)"""
        try:
            # Serialize to binary format
            binary_data = pb_event.SerializeToString()

            # Here you would integrate with your actual storage backend
            # For now, we'll simulate successful storage
            await asyncio.sleep(0.001)  # Simulate async I/O

            self.logger.debug(f"Stored protobuf event {pb_event.id} ({len(binary_data)} bytes)")
            return True

        except Exception as e:
            self.logger.error(f"Failed to store protobuf event: {e}")
            return False

    async def _store_json_event(self, event_data: Dict[str, Any]) -> bool:
        """Store JSON event using legacy service or direct storage"""
        try:
            # Use legacy service if available
            if self.legacy_service and hasattr(self.legacy_service, 'log_event'):
                if asyncio.iscoroutinefunction(self.legacy_service.log_event):
                    return await self.legacy_service.log_event(event_data)
                else:
                    return self.legacy_service.log_event(event_data)

            # Direct JSON storage fallback
            await asyncio.sleep(0.001)  # Simulate async I/O
            self.logger.debug(f"Stored JSON event {event_data.get('id', 'unknown')}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to store JSON event: {e}")
            return False

    def get_service_info(self) -> Dict[str, Any]:
        """Get information about service capabilities and status"""
        return {
            "service_name": "ProtobufObservabilityService",
            "protobuf_enabled": self.converter is not None,
            "fallback_enabled": self.fallback_to_json,
            "legacy_service_available": self.legacy_service is not None,
            "auto_generation": self.auto_generate_protobuf,
            "enabled": self.enabled,
            "stats": self.stats.copy(),
            "converter_available": self.converter is not None
        }

    def enable_service(self):
        """Enable the observability service"""
        self.enabled = True
        self.logger.info("Protobuf observability service enabled")

    def disable_service(self):
        """Disable the observability service"""
        self.enabled = False
        self.logger.info("Protobuf observability service disabled")

    def reset_stats(self):
        """Reset service statistics"""
        self.stats = {
            'protobuf_events': 0,
            'json_fallback_events': 0,
            'conversion_errors': 0,
            'generation_attempts': 0
        }
        self.logger.info("Service statistics reset")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the service"""
        health = {
            "status": "healthy" if self.enabled else "disabled",
            "protobuf_converter": "available" if self.converter else "unavailable",
            "legacy_service": "available" if self.legacy_service else "unavailable",
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        }

        # Test protobuf conversion if available
        if self.converter:
            try:
                test_event = {
                    "id": "health_check",
                    "timestamp": health["timestamp"],
                    "level": "INFO",
                    "muxi_version": "1.0.0",
                    "server": "health-check",
                    "event": "SYSTEM_HEALTH_CHECK"
                }
                pb_event = self.converter.json_to_protobuf(test_event)
                # Test round-trip conversion without storing unused result
                self.converter.protobuf_to_json(pb_event)
                health["conversion_test"] = "passed"
            except Exception as e:
                health["conversion_test"] = f"failed: {e}"
                health["status"] = "degraded"

        return health


class ServiceRegistry:
    """
    Registry for managing observability service instances and migration.

    Thread-safe registry that protects shared state with a lock.
    """

    def __init__(self):
        self.services = {}
        self.active_service_name = None
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()  # Thread safety lock

    def register_service(self, name: str, service, make_active: bool = False):
        """Register an observability service (thread-safe)"""
        with self._lock:
            self.services[name] = service
            self.logger.info(f"Registered observability service: {name}")

            if make_active or self.active_service_name is None:
                self.active_service_name = name
                self.logger.info(f"Set active observability service: {name}")

    def get_active_service(self):
        """Get the currently active observability service (thread-safe)"""
        with self._lock:
            if self.active_service_name and self.active_service_name in self.services:
                return self.services[self.active_service_name]
            return None

    def get_service(self, name: str):
        """Get a specific observability service by name (thread-safe)"""
        with self._lock:
            return self.services.get(name)

    def switch_service(self, name: str) -> bool:
        """Switch to a different observability service (thread-safe)"""
        with self._lock:
            if name not in self.services:
                self.logger.error(f"Service {name} not found in registry")
                return False

            old_service = self.active_service_name
            self.active_service_name = name
            self.logger.info(f"Switched observability service from {old_service} to {name}")
            return True

    def list_services(self) -> List[str]:
        """List all registered services (thread-safe)"""
        with self._lock:
            return list(self.services.keys())


# Global service registry instance
service_registry = ServiceRegistry()
