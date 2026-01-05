"""Unit tests for the telemetry service."""

import asyncio
import threading

import pytest

from muxi.runtime.services.telemetry import TelemetryService, get_machine_id
from muxi.runtime.services.telemetry.service import Counters


class TestMachineId:
    """Tests for machine ID generation."""

    def test_machine_id_is_deterministic(self):
        """Same machine should generate the same ID."""
        id1 = get_machine_id()
        id2 = get_machine_id()
        assert id1 == id2

    def test_machine_id_is_valid_uuid(self):
        """Machine ID should be a valid UUID string."""
        machine_id = get_machine_id()
        assert len(machine_id) == 36  # UUID format: 8-4-4-4-12
        assert machine_id.count("-") == 4


class TestCounters:
    """Tests for thread-safe counters."""

    def test_increment_request_success(self):
        """Recording a successful request increments correct counters."""
        counters = Counters()
        counters.increment_request(success=True, latency_ms=100.0, route="server")

        assert counters.requests_total == 1
        assert counters.requests_success == 1
        assert counters.requests_failed == 0
        assert counters.sources_server == 1

    def test_increment_request_failure(self):
        """Recording a failed request increments failure counters."""
        counters = Counters()
        counters.increment_request(success=False, latency_ms=50.0, route="direct")

        assert counters.requests_total == 1
        assert counters.requests_success == 0
        assert counters.requests_failed == 1
        assert counters.sources_direct == 1
        assert counters.failures_direct == 1

    def test_increment_request_with_sdk(self):
        """Recording a request with SDK tracks SDK correctly."""
        counters = Counters()
        counters.increment_request(success=True, latency_ms=100.0, route="server", sdk="python")
        counters.increment_request(success=True, latency_ms=100.0, route="server", sdk="python")
        counters.increment_request(success=True, latency_ms=100.0, route="server", sdk="typescript")

        assert counters.sdk_requests["python"] == 2
        assert counters.sdk_requests["typescript"] == 1

    def test_increment_llm(self):
        """LLM tracking records provider and model correctly."""
        counters = Counters()
        counters.increment_llm("openai", "gpt-4o", cache_hit=False)
        counters.increment_llm("openai", "gpt-4o", cache_hit=True)
        counters.increment_llm("openai", "gpt-4o-mini", cache_hit=False)
        counters.increment_llm("anthropic", "claude-3-sonnet", cache_hit=True)

        assert counters.llm_stats["openai"]["gpt-4o"]["requests"] == 2
        assert counters.llm_stats["openai"]["gpt-4o"]["cache_hits"] == 1
        assert counters.llm_stats["openai"]["gpt-4o-mini"]["requests"] == 1
        assert counters.llm_stats["anthropic"]["claude-3-sonnet"]["requests"] == 1
        assert counters.llm_stats["anthropic"]["claude-3-sonnet"]["cache_hits"] == 1

    def test_increment_error(self):
        """Error tracking records by type."""
        counters = Counters()
        counters.increment_error("timeout")
        counters.increment_error("timeout")
        counters.increment_error("rate_limit")

        assert counters.errors["timeout"] == 2
        assert counters.errors["rate_limit"] == 1

    def test_increment_feature(self):
        """Feature tracking records usage."""
        counters = Counters()
        counters.increment_feature("clarification")
        counters.increment_feature("workflow")
        counters.increment_feature("clarification")

        assert counters.features["clarification"] == 2
        assert counters.features["workflow"] == 1

    def test_get_percentiles_empty(self):
        """Percentiles return zeros when no latencies."""
        counters = Counters()
        percentiles = counters.get_percentiles()

        assert percentiles["p50"] == 0
        assert percentiles["p95"] == 0
        assert percentiles["p99"] == 0

    def test_get_percentiles_with_data(self):
        """Percentiles are calculated correctly."""
        counters = Counters()
        # Add 100 latencies from 1 to 100
        for i in range(1, 101):
            counters.latencies.append(float(i))

        percentiles = counters.get_percentiles()

        # Percentiles should be approximately correct (allow for index calculation)
        assert 50 <= percentiles["p50"] <= 52
        assert 95 <= percentiles["p95"] <= 96
        assert 99 <= percentiles["p99"] <= 100

    def test_snapshot_and_reset(self):
        """Snapshot captures data and resets counters."""
        counters = Counters()
        counters.increment_request(success=True, latency_ms=100.0, route="server", sdk="python")
        counters.increment_llm("openai", "gpt-4o", cache_hit=True)
        counters.increment_feature("workflow")
        counters.increment_error("timeout")

        snapshot = counters.snapshot_and_reset()

        # Verify snapshot has data
        assert snapshot["requests"]["total"] == 1
        assert snapshot["requests"]["success"] == 1
        assert snapshot["requests"]["sources"]["api"]["server"] == 1
        assert snapshot["requests"]["sources"]["sdk"]["python"] == 1
        assert snapshot["llm"]["requests_total"] == 1
        assert snapshot["llm"]["cache_hits"] == 1
        assert snapshot["llm"]["openai"]["gpt-4o"]["requests"] == 1
        assert snapshot["features"]["workflow"] == 1
        assert snapshot["errors"]["timeout"] == 1

        # Verify counters are reset
        assert counters.requests_total == 0
        assert counters.requests_success == 0
        assert counters.sources_server == 0

    def test_thread_safety(self):
        """Counters should be thread-safe under concurrent access."""
        counters = Counters()
        num_threads = 5
        increments_per_thread = 100

        def increment_requests():
            for _ in range(increments_per_thread):
                counters.increment_request(success=True, latency_ms=10.0, route="server")

        threads = [threading.Thread(target=increment_requests) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counters.requests_total == num_threads * increments_per_thread


class TestTelemetryService:
    """Tests for the TelemetryService class."""

    def test_service_creation(self):
        """Service can be created with version."""
        service = TelemetryService(version="1.0.0")
        assert service._version == "1.0.0"

    def test_set_formation_info(self):
        """Formation info is stored correctly."""
        service = TelemetryService()
        service.set_formation_info(
            agents=3,
            tools=10,
            mcp_servers=2,
            memory_backend="postgres",
            features=["clarification", "workflow"],
        )

        assert service._formation_info["agents_count"] == 3
        assert service._formation_info["tools_count"] == 10
        assert service._formation_info["mcp_servers"] == 2
        assert service._formation_info["memory_backend"] == "postgres"
        assert "clarification" in service._formation_info["features_enabled"]

    def test_record_request(self):
        """Recording requests updates counters."""
        service = TelemetryService()
        service.record_request(success=True, latency_ms=100.0, route="server", sdk="python")

        assert service._counters.requests_total == 1

    def test_record_llm_request(self):
        """Recording LLM requests updates counters."""
        service = TelemetryService()
        service.record_llm_request(provider="openai", model="gpt-4o", cache_hit=True)

        assert service._counters.llm_stats["openai"]["gpt-4o"]["requests"] == 1
        assert service._counters.llm_stats["openai"]["gpt-4o"]["cache_hits"] == 1

    def test_record_error(self):
        """Recording errors updates counters."""
        service = TelemetryService()
        service.record_error("timeout")

        assert service._counters.errors["timeout"] == 1

    def test_record_feature(self):
        """Recording features updates counters."""
        service = TelemetryService()
        service.record_feature("workflow")

        assert service._counters.features["workflow"] == 1

    def test_build_payload(self):
        """Payload is built correctly with all required fields."""
        service = TelemetryService(version="1.0.0")
        service.set_formation_info(agents=2, tools=5)
        service.record_request(success=True, latency_ms=100.0, route="server")

        snapshot = service._counters.snapshot_and_reset()
        # Add back one request so payload isn't empty
        service.record_request(success=True, latency_ms=100.0, route="server")
        snapshot = service._counters.snapshot_and_reset()

        payload = service._build_payload(snapshot)

        assert payload["module"] == "runtime"
        assert payload["schema_version"] == 1
        assert "machine_id" in payload
        assert "ts" in payload
        assert payload["payload"]["version"] == "1.0.0"
        assert payload["payload"]["formation"]["agents_count"] == 2
        assert payload["payload"]["requests"]["total"] == 1

    @pytest.mark.asyncio
    async def test_start_and_shutdown(self):
        """Service starts and shuts down cleanly."""
        service = TelemetryService()
        await service.start()
        assert service._running is True
        assert service._flush_task is not None

        await service.shutdown()
        assert service._running is False

    def test_enabled_property(self):
        """Enabled property reflects config."""
        service = TelemetryService()
        assert service.enabled is True  # Default enabled
