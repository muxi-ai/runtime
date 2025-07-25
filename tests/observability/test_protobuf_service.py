"""
Tests for Protobuf Service Integration
"""

import pytest
from datetime import datetime
from typing import Any, Dict
from unittest.mock import Mock, AsyncMock

from src.muxi.services.observability.protobuf_service import (
    ProtobufObservabilityService,
    ServiceRegistry
)


class TestProtobufObservabilityService:
    """Test the ProtobufObservabilityService class"""

    @pytest.fixture
    def sample_event(self) -> Dict[str, Any]:
        """Sample event for testing"""
        return {
            "id": "evt_test_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "data": {
                "description": "Test event",
                "user_message": "Hello",
                "agent_response": "Hi there!"
            }
        }

    @pytest.fixture
    def mock_legacy_service(self):
        """Mock legacy observability service"""
        service = Mock()
        service.log_event = AsyncMock(return_value=True)
        service.retrieve_events = AsyncMock(return_value=[])
        return service

    def test_service_initialization_with_converter(self):
        """Test service initializes successfully when protobuf converter is available"""
        service = ProtobufObservabilityService()

        assert service.fallback_to_json is True
        assert service.auto_generate_protobuf is True
        assert service.enabled is True
        assert service.converter is not None  # Should initialize successfully
        assert service.stats['protobuf_events'] == 0
        assert service.stats['json_fallback_events'] == 0
        assert service.stats['conversion_errors'] == 0

    def test_service_initialization_with_legacy_service(self, mock_legacy_service):
        """Test service initializes with legacy service for fallback"""
        service = ProtobufObservabilityService(legacy_service=mock_legacy_service)

        assert service.legacy_service == mock_legacy_service
        assert service.fallback_to_json is True

    @pytest.mark.asyncio
    async def test_log_event_protobuf_format(self, sample_event):
        """Test logging event in protobuf format"""
        service = ProtobufObservabilityService()

        # Mock the storage method
        service._store_protobuf_event = AsyncMock(return_value=True)

        result = await service.log_event(sample_event, format_preference="protobuf")

        assert result is True
        assert service.stats['protobuf_events'] == 1
        assert service.stats['json_fallback_events'] == 0
        service._store_protobuf_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_json_fallback(self, sample_event, mock_legacy_service):
        """Test logging event falls back to JSON when protobuf fails"""
        service = ProtobufObservabilityService(legacy_service=mock_legacy_service)

        # Mock protobuf failure
        service._store_protobuf_event = AsyncMock(return_value=False)

        result = await service.log_event(sample_event, format_preference="protobuf")

        assert result is True
        assert service.stats['json_fallback_events'] == 1
        mock_legacy_service.log_event.assert_called_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_log_event_json_preference(self, sample_event, mock_legacy_service):
        """Test logging event with JSON format preference"""
        service = ProtobufObservabilityService(legacy_service=mock_legacy_service)

        result = await service.log_event(sample_event, format_preference="json")

        assert result is True
        assert service.stats['protobuf_events'] == 0
        assert service.stats['json_fallback_events'] == 1
        mock_legacy_service.log_event.assert_called_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_log_event_disabled_service(self, sample_event):
        """Test that disabled service doesn't log events"""
        service = ProtobufObservabilityService()
        service.disable_service()

        result = await service.log_event(sample_event)

        assert result is False
        assert service.stats['protobuf_events'] == 0
        assert service.stats['json_fallback_events'] == 0

    @pytest.mark.asyncio
    async def test_log_event_conversion_error(self, mock_legacy_service):
        """Test handling of conversion errors"""
        service = ProtobufObservabilityService(legacy_service=mock_legacy_service)

        # Invalid event that will cause conversion error
        invalid_event = {
            "id": "evt_invalid",
            "timestamp": "invalid_timestamp",  # Should be int
            "level": "INVALID_LEVEL",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "INVALID_EVENT_TYPE"
        }

        result = await service.log_event(invalid_event, format_preference="protobuf")

        # Should fall back to JSON
        assert result is True
        assert service.stats['conversion_errors'] >= 1
        assert service.stats['json_fallback_events'] == 1
        mock_legacy_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_protobuf_event(self, sample_event):
        """Test storing protobuf event"""
        service = ProtobufObservabilityService()

        # Convert to protobuf first
        pb_event = service.converter.json_to_protobuf(sample_event)

        result = await service._store_protobuf_event(pb_event)

        assert result is True

    @pytest.mark.asyncio
    async def test_store_json_event_with_legacy(self, sample_event, mock_legacy_service):
        """Test storing JSON event using legacy service"""
        service = ProtobufObservabilityService(legacy_service=mock_legacy_service)

        result = await service._store_json_event(sample_event)

        assert result is True
        mock_legacy_service.log_event.assert_called_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_store_json_event_without_legacy(self, sample_event):
        """Test storing JSON event without legacy service"""
        service = ProtobufObservabilityService(legacy_service=None)

        result = await service._store_json_event(sample_event)

        assert result is True  # Should succeed with direct storage

    def test_get_service_info(self, mock_legacy_service):
        """Test getting service information"""
        service = ProtobufObservabilityService(legacy_service=mock_legacy_service)

        info = service.get_service_info()

        assert info["service_name"] == "ProtobufObservabilityService"
        assert info["protobuf_enabled"] is True
        assert info["fallback_enabled"] is True
        assert info["legacy_service_available"] is True
        assert info["enabled"] is True
        assert "stats" in info
        assert info["converter_available"] is True

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check when service is healthy"""
        service = ProtobufObservabilityService()

        health = await service.health_check()

        assert health["status"] == "healthy"
        assert health["protobuf_converter"] == "available"
        assert health["conversion_test"] == "passed"
        assert "timestamp" in health

    @pytest.mark.asyncio
    async def test_health_check_disabled(self):
        """Test health check when service is disabled"""
        service = ProtobufObservabilityService()
        service.disable_service()

        health = await service.health_check()

        assert health["status"] == "disabled"

    def test_enable_disable_service(self):
        """Test enabling and disabling service"""
        service = ProtobufObservabilityService()

        assert service.enabled is True

        service.disable_service()
        assert service.enabled is False

        service.enable_service()
        assert service.enabled is True

    def test_reset_stats(self):
        """Test resetting service statistics"""
        service = ProtobufObservabilityService()

        # Modify stats
        service.stats['protobuf_events'] = 10
        service.stats['json_fallback_events'] = 5
        service.stats['conversion_errors'] = 2

        service.reset_stats()

        assert service.stats['protobuf_events'] == 0
        assert service.stats['json_fallback_events'] == 0
        assert service.stats['conversion_errors'] == 0
        assert service.stats['generation_attempts'] == 0


class TestServiceRegistry:
    """Test the ServiceRegistry class"""

    @pytest.fixture
    def registry(self):
        """Create fresh service registry for testing"""
        return ServiceRegistry()

    @pytest.fixture
    def mock_service(self):
        """Mock observability service"""
        service = Mock()
        service.log_event = AsyncMock(return_value=True)
        return service

    @pytest.fixture
    def mock_protobuf_service(self):
        """Mock protobuf observability service"""
        service = Mock()
        service.log_event = AsyncMock(return_value=True)
        service.health_check = AsyncMock(return_value={"status": "healthy"})
        return service

    def test_register_service(self, registry, mock_service):
        """Test registering a service"""
        registry.register_service("test_service", mock_service, make_active=True)

        assert "test_service" in registry.services
        assert registry.services["test_service"] == mock_service
        assert registry.active_service_name == "test_service"

    def test_register_multiple_services(self, registry, mock_service):
        """Test registering multiple services"""
        service1 = Mock()
        service2 = Mock()

        registry.register_service("service1", service1, make_active=True)
        registry.register_service("service2", service2, make_active=False)

        assert len(registry.services) == 2
        assert registry.active_service_name == "service1"

    def test_get_active_service(self, registry, mock_service):
        """Test getting active service"""
        registry.register_service("active_service", mock_service, make_active=True)

        active = registry.get_active_service()
        assert active == mock_service

    def test_get_active_service_none(self, registry):
        """Test getting active service when none registered"""
        active = registry.get_active_service()
        assert active is None

    def test_get_service_by_name(self, registry, mock_service):
        """Test getting service by name"""
        registry.register_service("named_service", mock_service)

        service = registry.get_service("named_service")
        assert service == mock_service

        # Test non-existent service
        none_service = registry.get_service("nonexistent")
        assert none_service is None

    def test_switch_service(self, registry):
        """Test switching between services"""
        service1 = Mock()
        service2 = Mock()

        registry.register_service("service1", service1, make_active=True)
        registry.register_service("service2", service2, make_active=False)

        assert registry.active_service_name == "service1"

        # Switch to service2
        result = registry.switch_service("service2")
        assert result is True
        assert registry.active_service_name == "service2"

        # Try to switch to non-existent service
        result = registry.switch_service("nonexistent")
        assert result is False
        assert registry.active_service_name == "service2"  # Should remain unchanged

    def test_list_services(self, registry):
        """Test listing registered services"""
        service1 = Mock()
        service2 = Mock()
        service3 = Mock()

        registry.register_service("service1", service1)
        registry.register_service("service2", service2)
        registry.register_service("service3", service3)

        services = registry.list_services()
        assert len(services) == 3
        assert "service1" in services
        assert "service2" in services
        assert "service3" in services


class TestServiceIntegration:
    """Integration tests for protobuf service with real components"""

    @pytest.mark.asyncio
    async def test_end_to_end_event_flow(self):
        """Test complete event flow from JSON to protobuf and back"""
        # Create sample event
        event = {
            "id": "evt_e2e_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "integration-test",
            "event": "SYSTEM_HEALTH_CHECK",
            "data": {
                "description": "End-to-end test",
                "component": "protobuf_service",
                "status": "testing"
            }
        }

        # Create service
        service = ProtobufObservabilityService()

        # Mock storage to capture what gets stored
        stored_events = []

        async def mock_store_protobuf(pb_event):
            stored_events.append(pb_event)
            return True

        service._store_protobuf_event = mock_store_protobuf

        # Log event
        result = await service.log_event(event, format_preference="protobuf")

        assert result is True
        assert len(stored_events) == 1
        assert service.stats['protobuf_events'] == 1

        # Verify stored event can be converted back to JSON
        stored_pb_event = stored_events[0]
        converted_json = service.converter.protobuf_to_json(stored_pb_event)

        # Verify key fields preserved
        assert converted_json["id"] == event["id"]
        assert converted_json["level"] == event["level"]
        assert converted_json["event"] == event["event"]
        assert converted_json["data"]["description"] == event["data"]["description"]

    @pytest.mark.asyncio
    async def test_service_registry_integration(self):
        """Test service registry with actual services"""
        registry = ServiceRegistry()

        # Create mock legacy service
        legacy_service = Mock()
        legacy_service.log_event = AsyncMock(return_value=True)

        # Create protobuf service
        protobuf_service = ProtobufObservabilityService(legacy_service=legacy_service)

        # Register services
        registry.register_service("legacy", legacy_service, make_active=True)
        registry.register_service("protobuf", protobuf_service, make_active=False)

        # Test switching services
        assert registry.active_service_name == "legacy"

        result = registry.switch_service("protobuf")
        assert result is True
        assert registry.active_service_name == "protobuf"

        # Test using active service
        active_service = registry.get_active_service()
        assert active_service == protobuf_service

        # Test service capabilities
        info = active_service.get_service_info()
        assert info["service_name"] == "ProtobufObservabilityService"
        assert info["protobuf_enabled"] is True

    @pytest.mark.asyncio
    async def test_backwards_compatibility(self):
        """Test that protobuf service maintains backwards compatibility"""
        # Create mock legacy service that uses old interface
        class MockLegacyService:
            def __init__(self):
                self.logged_events = []

            async def log_event(self, event_data):
                self.logged_events.append(event_data)
                return True

        legacy_service = MockLegacyService()

        # Create protobuf service with legacy fallback
        protobuf_service = ProtobufObservabilityService(
            fallback_to_json=True,
            legacy_service=legacy_service
        )

        # Test event that should fall back to legacy
        event = {
            "id": "evt_compat_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "compat-test",
            "event": "CONVERSATION_MESSAGE"
        }

        # Force JSON fallback
        result = await protobuf_service.log_event(event, format_preference="json")

        assert result is True
        assert len(legacy_service.logged_events) == 1
        assert legacy_service.logged_events[0] == event
        assert protobuf_service.stats['json_fallback_events'] == 1
