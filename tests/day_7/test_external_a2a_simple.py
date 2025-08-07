#!/usr/bin/env python3
"""
Simple test for external A2A communication between two formations.
Tests basic message passing without complex scenarios.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.muxi.formation.formation import Formation


async def test_simple_a2a():
    """Test simple A2A message between formations."""
    print("\nSimple External A2A Test")
    print("=" * 60)
    print("This test assumes Formation 2 is already running on port 8181")
    print("=" * 60)
    
    formation = Formation()
    
    try:
        # Load Formation 1
        await formation.load("test-formations/formation-a2a/formation1/formation.yaml")
        overlord = await formation.start_overlord()
        
        # Simple test message
        print("\nSending simple A2A request...")
        response = await overlord.chat(
            "Ask the agent at localhost:8181 to say hello",
            user_id="test_user"
        )
        
        print(f"\nResponse: {response}")
        
        assert response is not None
        assert len(response) > 0
        
        print("\n✅ Simple A2A test passed!")
        
    finally:
        await formation.stop_overlord()


if __name__ == "__main__":
    asyncio.run(test_simple_a2a())