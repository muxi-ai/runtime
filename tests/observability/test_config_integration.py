"""
Test configuration integration for observability system.
"""

import asyncio
import sys
import os
import tempfile

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from muxi.runtime.observability.manager import ObservabilityManager
from muxi.runtime.observability.types import EventLevel, SystemEvents


async def test_config_integration():
    """Test that configuration integration works end-to-end."""
    print("Testing configuration integration...")

    # Create a temporary file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, "test.log")

        # Simulate formation config streams
        streams_config = [
            {
                "id": "test_stdout",
                "type": "stdout",
                "format": "jsonl",
                "enabled": True
            },
            {
                "id": "test_file",
                "type": "file",
                "format": "text",
                "path": file_path,
                "enabled": True
            }
        ]

        # Create manager
        manager = ObservabilityManager()
        await manager.start()

        # Reconfigure with streams (simulating formation config loading)
        await manager.reconfigure_streams(streams_config)

        # Test event emission
        event_id = await manager.emit_system_event(
            SystemEvents.SERVICE_STARTED,
            level=EventLevel.INFO,
            description="Test configuration integration"
        )

        print(f"✅ Event emitted: {event_id}")

        # Check if file was created
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                print(f"✅ File content: {content[:100]}...")
        else:
            print("❌ File was not created")

        # Clean up
        await manager.close()

        print("✅ Configuration integration test completed!")


if __name__ == "__main__":
    asyncio.run(test_config_integration())
