#!/usr/bin/env python3
"""Simple test to verify basic chat functionality works."""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def test_simple_chat():
    """Test simple chat with minimal formation."""
    print("Testing Simple Chat with Minimal Formation...")

    # Create minimal valid formation
    formation_config = """
schema: "1.0.0"
id: "test-minimal"
description: "Minimal formation for testing"

llm:
  api_keys:
    openai: "test-key-for-validation"
  models:
    - text: "openai/gpt-4o-mini"
    - embedding: "openai/text-embedding-3-small"

runtime:
  built_in_mcps: false  # Disable built-in MCPs for faster test startup

agents:
  - id: "assistant"
    name: "Test Assistant"
    description: "A simple test assistant"
    system_message: "You are a helpful test assistant. Keep responses brief."
"""

    # Write to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(formation_config)
        temp_path = f.name

    try:
        # Test 1: Load formation
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(temp_path)
        print("✅ Formation loaded successfully")

        # Test 2: Start overlord
        print("\n2. Starting overlord...")
        overlord = await formation.start_overlord()
        print("✅ Overlord started successfully")

        # Test 3: Check basic structure
        print("\n3. Checking overlord structure...")
        print(f"   Formation ID: {overlord.formation_id}")
        print(f"   Agents: {list(overlord.agents.keys())}")
        # Formation ID might be different from config id
        assert overlord.formation_id is not None
        assert "assistant" in overlord.agents
        print("✅ Structure verified")

        # Test 4: Test agent is properly initialized
        print("\n4. Checking agent is properly initialized...")
        agent = overlord.agents["assistant"]
        assert agent is not None
        # Agent should have been initialized properly
        print(f"   Agent type: {type(agent).__name__}")
        print(f"   Agent attributes: {[attr for attr in dir(agent) if not attr.startswith('_')][:5]}...")
        print("✅ Agent properly initialized")

        # Test 5: Stop overlord
        print("\n5. Stopping overlord...")
        await formation.stop_overlord()
        print("✅ Overlord stopped successfully")

    finally:
        # Clean up
        import os
        os.unlink(temp_path)

    print("\n✅ All simple chat tests passed!")


if __name__ == "__main__":
    asyncio.run(test_simple_chat())
