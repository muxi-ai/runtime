"""
Integration test for health monitoring system.

Tests the complete health monitoring pipeline including:
- HealthManager file operations
- HealthMonitor proactive checks
- Circuit breaker integration in StreamProcessor
- Health API endpoints
- ObservabilityManager integration
"""

import asyncio
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from muxi.observability.health import HealthManager, HealthMonitor, HealthStatusAPI
from muxi.observability.manager import ObservabilityManager


class TestHealthMonitoringIntegration:
    """Integration tests for the complete health monitoring system."""

    @pytest.fixture
    async def temp_health_file(self):
        """Create a temporary health file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.health', delete=False) as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        try:
            Path(temp_path).unlink()
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def health_manager(self, temp_health_file):
        """Create a HealthManager instance with temporary file."""
        return HealthManager(temp_health_file)

    @pytest.fixture
    async def health_monitor(self, health_manager):
        """Create a HealthMonitor instance."""
        return HealthMonitor(check_interval=1, health_manager=health_manager)

    @pytest.fixture
    async def health_api(self, health_manager):
        """Create a HealthStatusAPI instance."""
        return HealthStatusAPI(health_manager)

    @pytest.fixture
    async def observability_manager(self):
        """Create an ObservabilityManager instance for testing."""
        config = {
            "health_check_interval": 1,
            "logging": {
                "streams": [
                    {
                        "type": "http",
                        "destination": "https://api.example.com/events",
                        "formatter": "jsonl"
                    },
                    {
                        "type": "file",
                        "destination": "/tmp/test_events.log",
                        "formatter": "text"
                    }
                ]
            }
        }
        return ObservabilityManager(config)

    async def test_health_manager_basic_operations(self, health_manager):
        """Test basic HealthManager file operations."""
        # Test initial state
        status = await health_manager.get_all_destinations_status()
        assert status["destinations"] == {}

        # Test updating destination health
        await health_manager.update_destination_health(
            "https://api.example.com/events", False, "Connection timeout"
        )

        # Verify update
        dest_status = await health_manager.get_destination_status("https://api.example.com/events")
        assert dest_status["healthy"] is False
        assert dest_status["last_error"] == "Connection timeout"
        assert "since" in dest_status

        # Test getting healthy destinations
        healthy = await health_manager.get_healthy_destinations([
            "https://api.example.com/events",
            "https://healthy.example.com/events"
        ])
        assert "https://api.example.com/events" not in healthy
        assert "https://healthy.example.com/events" in healthy  # Default healthy

    async def test_health_monitor_lifecycle(self, health_monitor):
        """Test HealthMonitor start/stop lifecycle."""
        destinations = [
            "https://api.example.com/events",
            "kafka://broker1:9092,broker2:9092",
            "/tmp/test_file.log"
        ]

        # Start monitoring
        await health_monitor.start(destinations)
        assert health_monitor.is_running()

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Stop monitoring
        await health_monitor.stop()
        assert not health_monitor.is_running()

    @patch('aiohttp.ClientSession.get')
    async def test_health_monitor_http_checks(self, mock_get, health_monitor):
        """Test HTTP health checks with mocked responses."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_get.return_value.__aenter__.return_value = mock_response

        destinations = ["https://api.example.com/events"]
        await health_monitor.start(destinations)

        # Wait for health check
        await asyncio.sleep(1.5)

        # Verify healthy status
        status = await health_monitor.health_manager.get_destination_status(
            "https://api.example.com/events"
        )
        assert status.get("healthy", True) is True

        await health_monitor.stop()

    @patch('aiohttp.ClientSession.get')
    async def test_health_monitor_http_failure(self, mock_get, health_monitor):
        """Test HTTP health check failure handling."""
        # Mock failed response
        mock_get.side_effect = Exception("Connection timeout")

        destinations = ["https://api.example.com/events"]
        await health_monitor.start(destinations)

        # Wait for health check
        await asyncio.sleep(1.5)

        # Verify unhealthy status
        status = await health_monitor.health_manager.get_destination_status(
            "https://api.example.com/events"
        )
        assert status.get("healthy", True) is False
        assert "Connection timeout" in status.get("last_error", "")

        await health_monitor.stop()

    async def test_health_api_endpoints(self, health_api, health_manager):
        """Test Health API endpoint functionality."""
        # Set up test data
        await health_manager.update_destination_health(
            "https://api.example.com/events", False, "Service unavailable"
        )
        await health_manager.update_destination_health(
            "https://healthy.example.com/events", True, None
        )

        # Test health summary
        summary = await health_api.get_health_summary()
        assert summary["status"] == "degraded"
        assert summary["summary"]["total_destinations"] == 2
        assert summary["summary"]["healthy"] == 1
        assert summary["summary"]["unhealthy"] == 1
        assert summary["summary"]["health_percentage"] == 50.0

        # Test destination-specific health
        dest_health = await health_api.get_destination_health("https://api.example.com/events")
        assert dest_health["healthy"] is False
        assert dest_health["last_error"] == "Service unavailable"
        assert "downtime_seconds" in dest_health

        # Test unhealthy destinations
        unhealthy = await health_api.get_unhealthy_destinations()
        assert unhealthy["count"] == 1
        assert "https://api.example.com/events" in unhealthy["destinations"]

        # Test reset health
        reset_result = await health_api.reset_destination_health("https://api.example.com/events")
        assert reset_result["action"] == "reset_health"
        assert reset_result["status"] == "healthy"

        # Verify reset worked
        dest_health = await health_api.get_destination_health("https://api.example.com/events")
        assert dest_health["healthy"] is True

        # Test metrics
        metrics = await health_api.get_health_metrics()
        assert "metrics" in metrics
        assert metrics["metrics"]["muxi_observability_destinations_total"] == 2

    async def test_observability_manager_integration(self, observability_manager):
        """Test health monitoring integration with ObservabilityManager."""
        # Start the observability system
        await observability_manager.start()

        # Verify health monitoring components are initialized
        assert observability_manager.health_monitor is not None
        assert observability_manager.health_api is not None

        # Test health API methods through manager
        summary = await observability_manager.get_health_summary()
        assert "status" in summary
        assert "summary" in summary

        # Test metrics
        metrics = await observability_manager.get_health_metrics()
        assert "metrics" in metrics

        # Stop the system
        await observability_manager.stop()

    async def test_circuit_breaker_integration(self, observability_manager):
        """Test circuit breaker integration with health monitoring."""
        # Configure with a mock destination that will fail
        streams_config = [
            {
                "type": "http",
                "destination": "https://failing.example.com/events",
                "formatter": "jsonl"
            }
        ]

        await observability_manager.start()
        await observability_manager.reconfigure_streams(streams_config)

        # Simulate multiple failures to trigger circuit breaker
        stream_processor = observability_manager.stream_processor

        # Get the transport
        transport_id = list(stream_processor.transports.keys())[0]
        transport = stream_processor.transports[transport_id]

        # Simulate failures
        for _ in range(4):  # Exceed circuit breaker threshold
            await stream_processor._handle_transport_failure(
                transport, transport_id, "https://failing.example.com/events", "Connection failed"
            )

        # Verify destination is marked unhealthy
        unhealthy = await observability_manager.get_unhealthy_destinations()
        assert unhealthy["count"] > 0
        assert "https://failing.example.com/events" in unhealthy["destinations"]

        await observability_manager.stop()

    async def test_health_file_persistence(self, temp_health_file):
        """Test health status persistence across manager instances."""
        # Create first manager and set some health status
        manager1 = HealthManager(temp_health_file)
        await manager1.update_destination_health(
            "https://api.example.com/events", False, "Initial failure"
        )

        # Create second manager with same file
        manager2 = HealthManager(temp_health_file)
        status = await manager2.get_destination_status("https://api.example.com/events")

        # Verify persistence
        assert status["healthy"] is False
        assert status["last_error"] == "Initial failure"

    async def test_concurrent_health_operations(self, health_manager):
        """Test concurrent health status operations."""
        destinations = [f"https://api{i}.example.com/events" for i in range(10)]

        # Concurrent updates
        tasks = []
        for i, dest in enumerate(destinations):
            task = health_manager.update_destination_health(
                dest, i % 2 == 0, f"Error {i}" if i % 2 != 0 else None
            )
            tasks.append(task)

        await asyncio.gather(*tasks)

        # Verify all updates
        status = await health_manager.get_all_destinations_status()
        assert len(status["destinations"]) == 10

                 # Check healthy/unhealthy split
        healthy_count = sum(
            1 for dest in status["destinations"].values() if dest.get("healthy", True)
        )
        assert healthy_count == 5  # Even indices should be healthy

    async def test_health_monitoring_with_multitasking_fallback(self, health_monitor):
        """Test health monitoring works even without multitasking library."""
        # This test verifies the fallback behavior when multitasking is not available
        with patch('muxi.observability.health_monitor.MULTITASKING_AVAILABLE', False):
            destinations = ["https://api.example.com/events"]

            await health_monitor.start(destinations)
            assert health_monitor.is_running()

            # Let it run briefly
            await asyncio.sleep(0.1)

            await health_monitor.stop()
            assert not health_monitor.is_running()


if __name__ == "__main__":
    # Run a simple integration test
    async def main():
        print("Running health monitoring integration test...")

        # Create temporary health file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.health', delete=False) as f:
            temp_path = f.name

        try:
            # Test basic health manager operations
            health_manager = HealthManager(temp_path)

            print("✓ Testing health manager basic operations...")
            await health_manager.update_destination_health(
                "https://api.example.com/events", False, "Test failure"
            )

            status = await health_manager.get_destination_status("https://api.example.com/events")
            assert status["healthy"] is False
            print("✓ Health status update and retrieval working")

            # Test health API
            print("✓ Testing health API...")
            health_api = HealthStatusAPI(health_manager)
            summary = await health_api.get_health_summary()
            assert summary["status"] == "degraded"
            print("✓ Health API working")

            # Test observability manager integration
            print("✓ Testing observability manager integration...")
            config = {"health_check_interval": 1}
            obs_manager = ObservabilityManager(config)
            await obs_manager.start()

            health_summary = await obs_manager.get_health_summary()
            assert "status" in health_summary
            print("✓ ObservabilityManager health integration working")

            await obs_manager.stop()

            print("🎉 All health monitoring integration tests passed!")

        finally:
            # Cleanup
            try:
                Path(temp_path).unlink()
            except FileNotFoundError:
                pass

    asyncio.run(main())
