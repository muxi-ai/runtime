"""Integration tests for telemetry service with mock endpoint."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.services.telemetry import TelemetryService, get_telemetry, set_telemetry


class TestTelemetryIntegration:
    """Integration tests for telemetry service."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_mock_endpoint(self):
        """Test complete telemetry lifecycle: start, record, flush, shutdown."""
        # Create service
        service = TelemetryService(version="1.0.0-test")
        service.set_formation_info(
            agents=2,
            tools=5,
            mcp_servers=1,
            memory_backend="sqlite",
            features=["clarification", "workflow"],
        )

        # Mock the HTTP client to capture sent payloads
        sent_payloads = []

        async def mock_post(url, json, headers):
            sent_payloads.append(json)
            mock_response = AsyncMock()
            mock_response.status_code = 200
            return mock_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = mock_post
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Start service
            await service.start()

            # Record various metrics
            service.record_request(success=True, latency_ms=100.0, route="server", sdk="python")
            service.record_request(success=True, latency_ms=150.0, route="direct")
            service.record_request(success=False, latency_ms=50.0, route="framework")

            service.record_llm_request("openai", "gpt-4o", cache_hit=False)
            service.record_llm_request("openai", "gpt-4o", cache_hit=True)
            service.record_llm_request("anthropic", "claude-3-sonnet", cache_hit=False)

            service.record_feature("clarification")
            service.record_feature("workflow")
            service.record_feature("clarification")

            service.record_error("timeout")
            service.record_error("rate_limit")

            # Manually trigger flush (normally happens hourly)
            await service._flush()

            # Verify payload was sent
            assert len(sent_payloads) == 1
            payload = sent_payloads[0]

            # Verify top-level structure
            assert payload["module"] == "runtime"
            assert payload["schema_version"] == 1
            assert "machine_id" in payload
            assert "ts" in payload

            # Verify payload content
            inner = payload["payload"]
            assert inner["version"] == "1.0.0-test"
            assert "uptime_hours" in inner

            # Verify formation info
            assert inner["formation"]["agents_count"] == 2
            assert inner["formation"]["tools_count"] == 5
            assert inner["formation"]["mcp_servers"] == 1
            assert inner["formation"]["memory_backend"] == "sqlite"

            # Verify request tracking
            assert inner["requests"]["total"] == 3
            assert inner["requests"]["success"] == 2
            assert inner["requests"]["failed"] == 1
            assert inner["requests"]["sources"]["framework"] == 1
            assert inner["requests"]["sources"]["api"]["direct"] == 1
            assert inner["requests"]["sources"]["api"]["server"] == 1
            assert inner["requests"]["sources"]["sdk"]["python"] == 1

            # Verify failures tracking
            assert inner["requests"]["failures"]["framework"] == 1

            # Verify LLM tracking
            assert inner["llm"]["requests_total"] == 3
            assert inner["llm"]["cache_hits"] == 1
            assert inner["llm"]["openai"]["gpt-4o"]["requests"] == 2
            assert inner["llm"]["openai"]["gpt-4o"]["cache_hits"] == 1
            assert inner["llm"]["anthropic"]["claude-3-sonnet"]["requests"] == 1

            # Verify feature tracking
            assert inner["features"]["clarification"] == 2
            assert inner["features"]["workflow"] == 1

            # Verify error tracking
            assert inner["errors"]["timeout"] == 1
            assert inner["errors"]["rate_limit"] == 1

            # Shutdown
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_backup_on_send_failure(self):
        """Test that payload is saved to backup file when send fails."""
        import tempfile
        from pathlib import Path

        # Create a temporary backup path
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "telemetry_backup.json"

            # Patch the backup path
            with patch("muxi.runtime.services.telemetry.service.BACKUP_PATH", backup_path):
                service = TelemetryService(version="1.0.0-test")

                # Mock HTTP client to fail
                async def mock_post_fail(url, json, headers):
                    mock_response = AsyncMock()
                    mock_response.status_code = 500
                    return mock_response

                with patch("httpx.AsyncClient") as mock_client:
                    mock_instance = AsyncMock()
                    mock_instance.post = mock_post_fail
                    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                    mock_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_client.return_value = mock_instance

                    await service.start()

                    # Record some metrics
                    service.record_request(success=True, latency_ms=100.0, route="server")

                    # Trigger flush (will fail and save backup)
                    await service._flush()

                    # Verify backup file was created
                    assert backup_path.exists()

                    # Verify backup content
                    with open(backup_path) as f:
                        backup_data = json.load(f)
                    assert backup_data["module"] == "runtime"
                    assert backup_data["payload"]["requests"]["total"] == 1

                    await service.shutdown()

    @pytest.mark.asyncio
    async def test_backup_cleared_on_successful_send(self):
        """Test that backup file is cleared after successful send."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "telemetry_backup.json"

            # Create a pre-existing backup file
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            with open(backup_path, "w") as f:
                json.dump({"old": "backup"}, f)

            with patch("muxi.runtime.services.telemetry.service.BACKUP_PATH", backup_path):
                service = TelemetryService(version="1.0.0-test")

                # Mock HTTP client to succeed
                async def mock_post_success(url, json, headers):
                    mock_response = AsyncMock()
                    mock_response.status_code = 200
                    return mock_response

                with patch("httpx.AsyncClient") as mock_client:
                    mock_instance = AsyncMock()
                    mock_instance.post = mock_post_success
                    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                    mock_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_client.return_value = mock_instance

                    await service.start()

                    # Record some metrics
                    service.record_request(success=True, latency_ms=100.0, route="server")

                    # Trigger flush (will succeed and clear backup)
                    await service._flush()

                    # Verify backup file was cleared
                    assert not backup_path.exists()

                    await service.shutdown()

    @pytest.mark.asyncio
    async def test_global_telemetry_accessor(self):
        """Test global get/set telemetry functions."""
        # Initially no global telemetry
        assert get_telemetry() is None

        # Set global telemetry
        service = TelemetryService(version="1.0.0")
        set_telemetry(service)

        # Verify it's accessible
        assert get_telemetry() is service

        # Clear it
        set_telemetry(None)
        assert get_telemetry() is None

    @pytest.mark.asyncio
    async def test_opt_out_prevents_sending(self):
        """Test that MUXI_TELEMETRY=0 prevents sending but still collects."""
        import os

        # Set opt-out environment variable
        with patch.dict(os.environ, {"MUXI_TELEMETRY": "0"}):
            service = TelemetryService(version="1.0.0-test")

            assert service.enabled is False

            sent_payloads = []

            async def mock_post(url, json, headers):
                sent_payloads.append(json)
                mock_response = AsyncMock()
                mock_response.status_code = 200
                return mock_response

            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_instance.post = mock_post
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client.return_value = mock_instance

                await service.start()

                # Record metrics (should still work)
                service.record_request(success=True, latency_ms=100.0, route="server")

                # Flush should NOT send
                await service._flush()

                # Verify nothing was sent
                assert len(sent_payloads) == 0

                # But counters should still have been updated (and reset by flush)
                # Record again to verify collection still works
                service.record_request(success=True, latency_ms=100.0, route="server")
                assert service._counters.requests_total == 1

                await service.shutdown()

    @pytest.mark.asyncio
    async def test_latency_percentiles_calculation(self):
        """Test that latency percentiles are calculated correctly."""
        service = TelemetryService(version="1.0.0")

        # Add latencies with known distribution
        latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]  # 10 values
        for lat in latencies:
            service.record_request(success=True, latency_ms=float(lat), route="server")

        # Get snapshot
        snapshot = service._counters.snapshot_and_reset()

        # Verify percentiles (with small margin for calculation method)
        assert 50 <= snapshot["latency_ms"]["p50"] <= 60
        assert 90 <= snapshot["latency_ms"]["p95"] <= 100
        assert 90 <= snapshot["latency_ms"]["p99"] <= 100
