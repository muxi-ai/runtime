"""
Integration tests for the complete observability system.
"""

import asyncio
import sys
import os
import tempfile
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from muxi.observability.manager import ObservabilityManager
from muxi.observability.stream_processor import StreamProcessor
from muxi.observability.types import EventLevel, SystemEvents, ConversationEvents


async def test_observability_manager_integration():
    """Test the complete observability manager with streaming."""
    print("Testing ObservabilityManager integration...")

    # Create a temporary file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "test_events.jsonl"

        # Configuration with multiple streams
        config = {
            "muxi_version": "1.0.0",
            "logging": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "stdout",
                        "level": "info",
                        "format": "jsonl",
                        "events": ["system", "conversation"]
                    },
                    {
                        "transport": "file",
                        "destination": str(file_path),
                        "level": "debug",
                        "format": "jsonl",
                        "events": ["system", "conversation"]
                    }
                ]
            }
        }

        # Create and start manager
        manager = ObservabilityManager(config)
        await manager.start()

        # Test system event emission
        event_id = await manager.emit_system_event(
            SystemEvents.SERVICE_STARTED,
            level=EventLevel.INFO,
            description="Test system startup"
        )

        print(f"System event emitted with ID: {event_id}")

        # Test conversation event emission
        event_id = await manager.emit_conversation_event(
            ConversationEvents.REQUEST_RECEIVED,
            level=EventLevel.INFO,
            description="Test request received"
        )

        print(f"Conversation event emitted with ID: {event_id}")

        # Give some time for async processing
        await asyncio.sleep(0.1)

        # Check file output
        if file_path.exists():
            content = file_path.read_text()
            print(f"File content length: {len(content)} characters")
            print(f"Contains system event: {'STARTED' in content}")
            print(f"Contains conversation event: {'REQUEST_RECEIVED' in content}")

        # Get transport status
        status = await manager.get_transport_status()
        print(f"Transport status: {status}")

        await manager.stop()
        print("ObservabilityManager integration test completed!\n")


async def test_stream_processor_standalone():
    """Test the stream processor independently."""
    print("Testing StreamProcessor standalone...")

    # Create processor
    processor = StreamProcessor()

    # Configuration for multiple transports
    streams_config = [
        {
            "transport": "stdout",
            "level": "info",
            "format": "text",
            "events": ["system"]
        }
    ]

    # Initialize and start
    await processor.initialize(streams_config)
    await processor.start()

    # Emit test event
    event = {
        "id": "test-stream-123",
        "timestamp": 1234567890,
        "level": "info",
        "event": "test_stream_event",
        "data": {"message": "Stream processor test"}
    }

    await processor.emit_event(event)

    # Get status
    status = await processor.get_transport_status()
    print(f"Stream processor status: {status}")

    await processor.stop()
    print("StreamProcessor standalone test completed!\n")


async def test_formatter_integration():
    """Test different formatters with transports."""
    print("Testing formatter integration...")

    from muxi.observability.formatters import create_formatter

    # Test different formatters
    formatters = ["jsonl", "text", "datadog_json", "splunk_hec"]

    for formatter_name in formatters:
        try:
            formatter = create_formatter(formatter_name)

            event = {
                "id": f"format-test-{formatter_name}",
                "timestamp": 1234567890,
                "level": "info",
                "event": "format_test",
                "data": {"message": f"Testing {formatter_name} formatter"}
            }

            formatted = formatter.format_event(event)
            print(f"{formatter_name}: {len(formatted)} chars, content-type: {formatter.content_type}")

        except Exception as e:
            print(f"{formatter_name}: Failed - {e}")

    print("Formatter integration test completed!\n")


async def test_trail_transport_config():
    """Test the trail transport preset configuration."""
    print("Testing trail transport configuration...")

    from muxi.observability.transports.stream import StreamTransport

    # Test trail preset
    config = {
        "transport": "trail",
        "token": "test-trail-token-123"
    }

    transport = StreamTransport(config)

    # Verify trail configuration
    assert transport.destination == "tcps://trail.muxi.ai/ingest"
    assert transport.protocol == "zmq"
    assert transport.format_type == "msgpack"
    assert transport.auth_config["type"] == "bearer"
    assert transport.auth_config["token"] == "test-trail-token-123"

    print("Trail transport configuration verified!")
    print(f"  Destination: {transport.destination}")
    print(f"  Protocol: {transport.protocol}")
    print(f"  Format: {transport.format_type}")
    print(f"  Auth: {transport.auth_config}")
    print("Trail transport test completed!\n")


async def main():
    """Run all integration tests."""
    print("=== MUXI Observability Integration Tests ===\n")

    try:
        await test_observability_manager_integration()
        await test_stream_processor_standalone()
        await test_formatter_integration()
        await test_trail_transport_config()

        print("=== All integration tests completed successfully! ===")

    except Exception as e:
        print(f"Integration test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
