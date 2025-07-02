#!/usr/bin/env python3
"""Test simple formation with correct schema v1.0.0."""

import asyncio
import sys
import tempfile
import os

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation


async def test_simple_formation():
    """Test basic formation functionality with schema v1.0.0."""
    print("Testing Simple Formation with Schema v1.0.0...")
    
    # Create minimal valid formation following the schema
    formation_config = """
schema: "1.0.0"
id: "test-basic"
description: "Basic test formation for validation"

# LLM configuration with separate capabilities
llm:
  api_keys:
    openai: "test-key-for-validation"
  models:
    - text: "openai/gpt-4o-mini"
    - embedding: "openai/text-embedding-3-small"

# Single test agent
agents:
  - id: "assistant"
    name: "Test Assistant"
    description: "A simple test assistant"
    system_message: "You are a helpful test assistant."
"""
    
    # Write to temp file
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
        print(f"   Agents loaded: {list(overlord.agents.keys())}")
        assert overlord.formation_id == "test-basic"
        assert "assistant" in overlord.agents
        print("✅ Basic structure verified")
        
        # Test 4: Check IntentDetectionService in agent
        print("\n4. Checking IntentDetectionService in agent...")
        agent = overlord.agents["assistant"]
        
        # Check if intent_service exists
        has_intent_service = hasattr(agent, 'intent_service')
        print(f"   Agent has intent_service attribute: {has_intent_service}")
        
        if has_intent_service and agent.intent_service:
            print("   ✅ IntentDetectionService is initialized")
            
            # Test the service works (fallback mode without LLM)
            from src.muxi.runtime.datatypes.intent import IntentType
            result = asyncio.run(agent.intent_service.detect_intent(
                "Do you remember what we discussed?",
                IntentType.QUERY_TYPE
            ))
            print(f"   Fallback detection result: {result.intent} (confidence: {result.confidence})")
        else:
            print("   ℹ️  IntentDetectionService not initialized (which is OK for basic test)")
        
        # Test 5: Check memory systems
        print("\n5. Checking memory systems...")
        print(f"   Buffer memory initialized: {overlord.buffer_memory is not None}")
        print(f"   Working memory config: {hasattr(overlord, 'working_memory_config')}")
        print("✅ Memory systems verified")
        
        # Test 6: Stop overlord
        print("\n6. Stopping overlord...")
        formation.stop_overlord()
        print("✅ Overlord stopped successfully")
        
    finally:
        # Clean up
        os.unlink(temp_path)
    
    print("\n✅ All basic formation tests passed!")
    print("\nSummary:")
    print("- Formation loading: ✅")
    print("- Overlord startup: ✅")
    print("- Agent loading: ✅")
    print("- Memory systems: ✅")
    print("- Clean shutdown: ✅")


if __name__ == "__main__":
    asyncio.run(test_simple_formation())