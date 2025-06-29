#!/usr/bin/env python3
"""Basic formation test to ensure system still works after our changes."""

import asyncio
import sys
sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation


async def test_basic_formation():
    """Test basic formation loading and chat."""
    print("Testing Basic Formation Loading and Chat...")
    
    # Create a minimal formation config
    formation_config = {
        "formation": {
            "id": "test-formation",
            "name": "Test Formation",
            "version": "1.0.0"
        },
        "llm": {
            "models": [
                {
                    "text": "openai/gpt-4o-mini",
                    "embedding": "openai/text-embedding-3-small"
                }
            ]
        },
        "agents": [
            {
                "id": "assistant",
                "name": "Test Assistant",
                "system_message": "You are a helpful test assistant."
            }
        ]
    }
    
    # Test 1: Load formation
    print("\n1. Loading formation...")
    import tempfile
    import yaml
    
    # Write config to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation_config, f)
        temp_path = f.name
    
    formation = Formation()
    formation.load(temp_path)
    print("✅ Formation loaded successfully")
    
    # Clean up temp file
    import os
    os.unlink(temp_path)
    
    # Test 2: Start overlord
    print("\n2. Starting overlord...")
    overlord = formation.start_overlord()
    print("✅ Overlord started successfully")
    
    # Test 3: Check agents loaded
    print("\n3. Checking agents...")
    print(f"   Agents loaded: {list(overlord.agents.keys())}")
    assert "assistant" in overlord.agents
    print("✅ Agent 'assistant' loaded correctly")
    
    # Test 4: Simple chat (without actual LLM call)
    print("\n4. Testing chat structure...")
    try:
        # This will fail due to no API key, but we're testing the structure
        response = await overlord.chat(
            message="Hello, this is a test",
            user_id="test_user"
        )
    except Exception as e:
        # We expect this to fail due to no API key
        error_str = str(e).lower()
        if "api" in error_str or "key" in error_str or "authenticate" in error_str:
            print("✅ Chat method called correctly (failed due to missing API key as expected)")
        else:
            print(f"❌ Unexpected error: {e}")
            raise
    
    # Test 5: Stop overlord
    print("\n5. Stopping overlord...")
    formation.stop_overlord()
    print("✅ Overlord stopped successfully")
    
    print("\n✅ All basic formation tests passed!")


if __name__ == "__main__":
    asyncio.run(test_basic_formation())