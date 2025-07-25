"""
Tests for observability transport implementations.
"""

import asyncio
import json
import tempfile
import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

import pytest

from muxi.observability.transports.base import TransportStatus
from muxi.observability.transports.stdout import StdoutTransport
from muxi.observability.transports.file import FileTransport
from muxi.observability.transports.stream import StreamTransport


class TestStdoutTransport:
    """Test stdout transport implementation."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test stdout transport initialization."""
        config = {"enabled": True}
        transport = StdoutTransport(config)

        assert await transport.initialize()
        assert transport.status == TransportStatus.HEALTHY

        await transport.close()

    @pytest.mark.asyncio
    async def test_send_event(self, capsys):
        """Test sending single event to stdout."""
        config = {"enabled": True}
        transport = StdoutTransport(config)
        await transport.initialize()

        event = {
            "id": "test-123",
            "timestamp": 1234567890,
            "level": "info",
            "event": "test_event",
            "data": {"message": "test message"}
        }

        result = await transport.send_event(event)
        assert result is True

        captured = capsys.readouterr()
        assert "test-123" in captured.out
        assert "test_event" in captured.out

        await transport.close()

    @pytest.mark.asyncio
    async def test_send_batch(self, capsys):
        """Test sending batch of events to stdout."""
        config = {"enabled": True}
        transport = StdoutTransport(config)
        await transport.initialize()

        events = [
            {"id": "test-1", "event": "event1"},
            {"id": "test-2", "event": "event2"}
        ]

        result = await transport.send_batch(events)
        assert result is True

        captured = capsys.readouterr()
        assert "test-1" in captured.out
        assert "test-2" in captured.out

        await transport.close()


class TestFileTransport:
    """Test file transport implementation."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test file transport initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_events.jsonl"
            config = {
                "enabled": True,
                "destination": str(file_path)
            }

            transport = FileTransport(config)
            assert await transport.initialize()
            assert transport.status == TransportStatus.HEALTHY
            assert file_path.exists()

            await transport.close()

    @pytest.mark.asyncio
    async def test_send_event(self):
        """Test sending single event to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_events.jsonl"
            config = {
                "enabled": True,
                "destination": str(file_path)
            }

            transport = FileTransport(config)
            await transport.initialize()

            event = {
                "id": "test-123",
                "timestamp": 1234567890,
                "level": "info",
                "event": "test_event",
                "data": {"message": "test message"}
            }

            result = await transport.send_event(event)
            assert result is True

            # Verify file content
            content = file_path.read_text()
            assert "test-123" in content
            assert "test_event" in content

            # Verify it's valid JSON
            lines = content.strip().split('\n')
            parsed_event = json.loads(lines[0])
            assert parsed_event["id"] == "test-123"

            await transport.close()

    @pytest.mark.asyncio
    async def test_rotation_config(self):
        """Test file rotation configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_events.jsonl"
            config = {
                "enabled": True,
                "destination": str(file_path),
                "rotation": {
                    "max_size_mb": 1,
                    "max_files": 5
                }
            }

            transport = FileTransport(config)
            assert transport.max_size_mb == 1
            assert transport.max_files == 5

            await transport.initialize()
            await transport.close()


class TestStreamTransport:
    """Test stream transport implementation."""

    @pytest.mark.asyncio
    async def test_protocol_detection(self):
        """Test automatic protocol detection."""
        # HTTP detection
        config = {"destination": "https://api.example.com/events"}
        transport = StreamTransport(config)
        assert transport.protocol == "http"

        # Kafka detection
        config = {"destination": "kafka://broker1:9092,broker2:9092"}
        transport = StreamTransport(config)
        assert transport.protocol == "kafka"

        # ZMQ detection
        config = {"destination": "tcp://localhost:5555"}
        transport = StreamTransport(config)
        assert transport.protocol == "zmq"

    @pytest.mark.asyncio
    async def test_trail_preset(self):
        """Test trail transport preset configuration."""
        config = {
            "transport": "trail",
            "token": "test-token-123"
        }

        transport = StreamTransport(config)
        assert transport.destination == "tcps://trail.muxi.ai/ingest"
        assert transport.protocol == "zmq"
        assert transport.format_type == "msgpack"
        assert transport.auth_config["type"] == "bearer"
        assert transport.auth_config["token"] == "test-token-123"

    @pytest.mark.asyncio
    async def test_format_configuration(self):
        """Test format configuration."""
        config = {
            "destination": "https://api.example.com/events",
            "format": "datadog_json"
        }

        transport = StreamTransport(config)
        assert transport.format_type == "datadog_json"

    @pytest.mark.asyncio
    async def test_initialization_without_dependencies(self):
        """Test initialization when optional dependencies are not available."""
        config = {
            "destination": "https://api.example.com/events",
            "protocol": "http"
        }

        transport = StreamTransport(config)

        # This should work even if aiohttp is not available
        # (it will fail gracefully and set status to FAILED)
        result = await transport.initialize()

        # Result depends on whether aiohttp is actually available
        # Just verify it doesn't crash
        assert isinstance(result, bool)
        assert transport.status in [TransportStatus.HEALTHY, TransportStatus.FAILED]

        await transport.close()


class TestTransportIntegration:
    """Test transport integration scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_transports(self):
        """Test using multiple transports simultaneously."""
        # Create multiple transports
        transports = []

        # Stdout transport
        stdout_transport = StdoutTransport({"enabled": True})
        await stdout_transport.initialize()
        transports.append(stdout_transport)

        # File transport
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_events.jsonl"
            file_transport = FileTransport({
                "enabled": True,
                "destination": str(file_path)
            })
            await file_transport.initialize()
            transports.append(file_transport)

            # Send same event to all transports
            event = {
                "id": "multi-test-123",
                "timestamp": 1234567890,
                "level": "info",
                "event": "multi_transport_test",
                "data": {"message": "testing multiple transports"}
            }

            results = []
            for transport in transports:
                result = await transport.send_event(event)
                results.append(result)

            # All should succeed
            assert all(results)

            # Verify file content
            content = file_path.read_text()
            assert "multi-test-123" in content

            # Clean up
            for transport in transports:
                await transport.close()

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test transport error handling."""
        # Create a file transport with invalid path
        config = {
            "enabled": True,
            "destination": "/invalid/path/that/does/not/exist/events.jsonl"
        }

        transport = FileTransport(config)
        result = await transport.initialize()

        # Should fail gracefully
        assert result is False
        assert transport.status == TransportStatus.FAILED
        assert transport.last_error is not None

        await transport.close()


if __name__ == "__main__":
    # Run basic smoke test
    async def smoke_test():
        print("Running observability transport smoke test...")

        # Test stdout transport
        transport = StdoutTransport({"enabled": True})
        await transport.initialize()

        event = {
            "id": "smoke-test",
            "timestamp": 1234567890,
            "level": "info",
            "event": "smoke_test",
            "data": {"message": "Smoke test successful!"}
        }

        result = await transport.send_event(event)
        print(f"Stdout transport result: {result}")

        await transport.close()
        print("Smoke test completed!")

    asyncio.run(smoke_test())
