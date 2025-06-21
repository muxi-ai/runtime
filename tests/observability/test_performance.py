"""
Performance Tests for Protobuf Observability Implementation
Tests serialization speed, size efficiency, and throughput improvements.
"""

import time
import json
import statistics
from datetime import datetime
from typing import Dict, List, Any
import pytest

from src.muxi.runtime.services.observability.event_converter import ObservabilityEventConverter


class PerformanceTestSuite:
    """Performance test suite for protobuf vs JSON observability events"""

    def __init__(self):
        self.converter = ObservabilityEventConverter()

    def generate_test_events(self, count: int) -> List[Dict[str, Any]]:
        """Generate test events for performance testing"""
        events = []
        base_timestamp = int(datetime.now().timestamp() * 1000)

        for i in range(count):
            event = {
                "id": f"evt_perf_{i:06d}",
                "timestamp": base_timestamp + i,
                "level": ["DEBUG", "INFO", "WARNING", "ERROR"][i % 4],
                "muxi_version": "1.0.0",
                "server": f"server-{i % 5}",
                "event": [
                    "CONVERSATION_MESSAGE",
                    "SYSTEM_HEALTH_CHECK",
                    "MCP_TOOL_CALL",
                    "MEMORY_STORE",
                ][i % 4],
                "data": {
                    "description": f"Performance test event {i}",
                    "user_message": f"Test message {i} with some content",
                    "agent_response": f"Response {i} with detailed information",
                    "response_time_ms": 800 + (i % 1500),
                },
            }
            events.append(event)

        return events

    def measure_json_serialization(self, events: List[Dict[str, Any]]) -> Dict[str, float]:
        """Measure JSON serialization performance"""
        start_time = time.perf_counter()

        json_sizes = []
        for event in events:
            json_data = json.dumps(event)
            json_sizes.append(len(json_data.encode("utf-8")))

        end_time = time.perf_counter()

        return {
            "duration_seconds": end_time - start_time,
            "events_per_second": len(events) / (end_time - start_time),
            "average_size_bytes": statistics.mean(json_sizes),
            "total_size_bytes": sum(json_sizes),
        }

    def measure_protobuf_serialization(self, events: List[Dict[str, Any]]) -> Dict[str, float]:
        """Measure protobuf serialization performance"""
        start_time = time.perf_counter()

        protobuf_sizes = []
        for event in events:
            pb_event = self.converter.json_to_protobuf(event)
            binary_data = pb_event.SerializeToString()
            protobuf_sizes.append(len(binary_data))

        end_time = time.perf_counter()

        return {
            "duration_seconds": end_time - start_time,
            "events_per_second": len(events) / (end_time - start_time),
            "average_size_bytes": statistics.mean(protobuf_sizes),
            "total_size_bytes": sum(protobuf_sizes),
        }


class TestPerformanceBasics:
    """Basic performance tests"""

    @pytest.fixture
    def perf_suite(self):
        """Create performance test suite"""
        return PerformanceTestSuite()

    def test_serialization_speed(self, perf_suite):
        """Test serialization speed comparison"""
        events = perf_suite.generate_test_events(100)

        json_perf = perf_suite.measure_json_serialization(events)
        pb_perf = perf_suite.measure_protobuf_serialization(events)

        # Both should be reasonably fast
        assert json_perf["events_per_second"] > 50
        assert pb_perf["events_per_second"] > 25

        print(f"JSON: {json_perf['events_per_second']:.1f} events/sec")
        print(f"Protobuf: {pb_perf['events_per_second']:.1f} events/sec")

    def test_size_efficiency(self, perf_suite):
        """Test size efficiency comparison"""
        events = perf_suite.generate_test_events(100)

        json_perf = perf_suite.measure_json_serialization(events)
        pb_perf = perf_suite.measure_protobuf_serialization(events)

        # Protobuf should generally be more compact
        size_reduction = (
            (json_perf["total_size_bytes"] - pb_perf["total_size_bytes"])
            / json_perf["total_size_bytes"]
            * 100
        )

        print(f"JSON total: {json_perf['total_size_bytes']:,} bytes")
        print(f"Protobuf total: {pb_perf['total_size_bytes']:,} bytes")
        print(f"Size reduction: {size_reduction:.1f}%")

        # Should have some size benefit
        assert size_reduction > 0, f"Expected size reduction, got {size_reduction}%"
