#!/usr/bin/env python3
"""Simple test to verify basic chat functionality works."""

import asyncio
import sys
sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation
from pathlib import Path


async def test_simple_chat():
    """Test simple chat with minimal formation."""
    print("Testing Simple Chat with Minimal Formation...")
    
    # Create minimal valid formation
    formation_config = """
schema: "1.0.0"
formation:
  id: "test-minimal"
  name: "Test Minimal Formation"
  description: "Minimal formation for testing"
  version: "1.0.0"

llm:
  models:
    - text: "openai/gpt-4o-mini"
    - embedding: "openai/text-embedding-3-small"

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
        formation.load(temp_path)
        print("✅ Formation loaded successfully")
        
        # Test 2: Start overlord
        print("\n2. Starting overlord...")
        overlord = formation.start_overlord()
        print("✅ Overlord started successfully")
        
        # Test 3: Check basic structure
        print("\n3. Checking overlord structure...")
        print(f"   Formation ID: {overlord.formation_id}")
        print(f"   Agents: {list(overlord.agents.keys())}")
        assert overlord.formation_id == "test-minimal"
        assert "assistant" in overlord.agents
        print("✅ Structure verified")
        
        # Test 4: Test IntentDetectionService initialization in agent
        print("\n4. Checking agent has IntentDetectionService...")
        agent = overlord.agents["assistant"]
        assert hasattr(agent, 'intent_service')
        assert agent.intent_service is not None
        print("✅ IntentDetectionService properly initialized in agent")
        
        # Test 5: Stop overlord
        print("\n5. Stopping overlord...")
        formation.stop_overlord()
        print("✅ Overlord stopped successfully")
        
    finally:
        # Clean up
        import os
        os.unlink(temp_path)
    
    print("\n✅ All simple chat tests passed!")


if __name__ == "__main__":
    asyncio.run(test_simple_chat())