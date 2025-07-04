#!/usr/bin/env python3
"""Test basic formation without MCP"""

import asyncio
import sys

sys.path.append(".")
from src.muxi.runtime import Formation

async def test():
    try:
        print("=== Testing Basic Formation ===")
        
        formation = Formation()
        formation.load("test-formations/formation-basic")
        
        print("Starting overlord...")
        overlord = formation.start_overlord()
        
        print("Overlord started successfully!")
        
        # Simple test
        response = await overlord.chat(
            "Hello, how are you?",
            user_id="user1",
            use_async=False
        )
        
        print(f"Response: {response}")
        
        formation.stop_overlord()
        print("Test completed!")
        
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())