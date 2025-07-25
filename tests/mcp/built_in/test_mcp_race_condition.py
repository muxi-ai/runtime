#!/usr/bin/env python3
"""
Test for MCP registration race condition fix.
"""

import asyncio
import tempfile
import yaml
from pathlib import Path
import sys

# Add runtime source to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi import Formation


def test_mcp_registration_synchronization():
    """Test that MCP registration completes before start_overlord returns."""
    config = {
        "schema": "1.0.0",
        "id": "test-race-condition",
        "description": "Test race condition fix",
        "llm": {
            "api_keys": {"openai": "test-key"},
            "models": [{"text": "gpt-3.5-turbo", "provider": "openai"}]
        },
        "agents": [{
            "schema": "1.0.0",
            "id": "test-agent",
            "name": "Test Agent",
            "description": "Test agent"
        }],
        "runtime": {
            "built_in_mcps": ["file-generation"]
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "formation.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        formation = Formation()
        formation.load(str(config_path))

        print("✅ Formation loaded")
        print(f"✅ MCP ready before start: {formation.is_mcp_ready()}")

        # This should complete MCP registration before returning
        overlord = formation.start_overlord()

        print(f"✅ MCP ready after start: {formation.is_mcp_ready()}")
        print("✅ Overlord started without race condition")

        formation.stop_overlord()
        formation.stop()

        print("✅ Test completed successfully")


async def test_async_mcp_readiness():
    """Test async MCP readiness checking."""
    config = {
        "schema": "1.0.0",
        "id": "test-async-readiness",
        "description": "Test async readiness",
        "llm": {
            "api_keys": {"openai": "test-key"},
            "models": [{"text": "gpt-3.5-turbo", "provider": "openai"}]
        },
        "agents": [{
            "schema": "1.0.0",
            "id": "test-agent",
            "name": "Test Agent",
            "description": "Test agent"
        }],
        "runtime": {
            "built_in_mcps": ["file-generation"]
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "formation.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        formation = Formation()
        formation.load(str(config_path))

        # Start overlord (which should wait for MCP registration)
        overlord = formation.start_overlord()

        # Test async wait method
        ready = await formation.wait_for_mcp_readiness(timeout=5.0)
        print(f"✅ Async MCP readiness: {ready}")

        formation.stop_overlord()
        formation.stop()


if __name__ == "__main__":
    print("=" * 60)
    print("Testing MCP Registration Race Condition Fix")
    print("=" * 60)

    try:
        test_mcp_registration_synchronization()
        print("\n" + "=" * 60)
        print("Testing Async MCP Readiness")
        print("=" * 60)
        asyncio.run(test_async_mcp_readiness())
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
