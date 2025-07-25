"""
Simple smoke test for observability transports.
"""

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

# Direct imports to avoid full runtime initialization
from muxi.observability.transports.stdout import StdoutTransport
from muxi.observability.transports.file import FileTransport
from muxi.observability.transports.stream import StreamTransport


async def test_stdout_transport():
    """Test stdout transport."""
    print("Testing stdout transport...")

    config = {"enabled": True}
    transport = StdoutTransport(config)

    # Initialize
    result = await transport.initialize()
    print(f"Initialization result: {result}")
    print(f"Status: {transport.status}")

    # Send test event
    event = {
        "id": "test-123",
        "timestamp": 1234567890,
        "level": "info",
        "event": "test_event",
        "data": {"message": "Hello from stdout transport!"}
    }

    result = await transport.send_event(event)
    print(f"Send event result: {result}")

    await transport.close()
    print("Stdout transport test completed!\n")


async def test_file_transport():
    """Test file transport."""
    print("Testing file transport...")

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "test_events.jsonl"
        config = {
            "enabled": True,
            "destination": str(file_path)
        }

        transport = FileTransport(config)

        # Initialize
        result = await transport.initialize()
        print(f"Initialization result: {result}")
        print(f"Status: {transport.status}")
        print(f"File exists: {file_path.exists()}")

        # Send test event
        event = {
            "id": "file-test-123",
            "timestamp": 1234567890,
            "level": "info",
            "event": "file_test_event",
            "data": {"message": "Hello from file transport!"}
        }

        result = await transport.send_event(event)
        print(f"Send event result: {result}")

        # Check file content
        if file_path.exists():
            content = file_path.read_text()
            print(f"File content length: {len(content)} characters")
            print(f"Contains test ID: {'file-test-123' in content}")

        await transport.close()
        print("File transport test completed!\n")


async def test_stream_transport():
    """Test stream transport configuration."""
    print("Testing stream transport configuration...")

    # Test HTTP detection
    config = {"destination": "https://api.example.com/events"}
    transport = StreamTransport(config)
    print(f"HTTP protocol detection: {transport.protocol}")

    # Test Kafka detection
    config = {"destination": "kafka://broker1:9092,broker2:9092"}
    transport = StreamTransport(config)
    print(f"Kafka protocol detection: {transport.protocol}")

    # Test ZMQ detection
    config = {"destination": "tcp://localhost:5555"}
    transport = StreamTransport(config)
    print(f"ZMQ protocol detection: {transport.protocol}")

    # Test trail preset
    config = {
        "transport": "trail",
        "token": "test-token-123"
    }
    transport = StreamTransport(config)
    print(f"Trail destination: {transport.destination}")
    print(f"Trail protocol: {transport.protocol}")
    print(f"Trail format: {transport.format_type}")
    print(f"Trail auth: {transport.auth_config}")

    print("Stream transport configuration test completed!\n")


async def test_formatters():
    """Test formatter creation."""
    print("Testing formatters...")

    try:
        from muxi.observability.formatters import create_formatter

        # Test JSON Lines formatter
        formatter = create_formatter("jsonl")
        print(f"JSONL formatter created: {type(formatter).__name__}")
        print(f"Content type: {formatter.content_type}")

        # Test event formatting
        event = {
            "id": "format-test",
            "timestamp": 1234567890,
            "level": "info",
            "event": "format_test",
            "data": {"message": "Test formatting"}
        }

        formatted = formatter.format_event(event)
        print(f"Formatted event length: {len(formatted)} characters")
        print(f"Contains test data: {'format-test' in formatted}")

        # Test text formatter
        text_formatter = create_formatter("text")
        text_output = text_formatter.format_event(event)
        print(f"Text formatter output: {text_output}")

        print("Formatters test completed!\n")

    except Exception as e:
        print(f"Formatters test failed: {e}\n")


async def main():
    """Run all tests."""
    print("=== MUXI Observability Transport Smoke Tests ===\n")

    try:
        await test_stdout_transport()
        await test_file_transport()
        await test_stream_transport()
        await test_formatters()

        print("=== All tests completed successfully! ===")

    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
