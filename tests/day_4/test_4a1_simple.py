#!/usr/bin/env python3
"""Test 4A1: Filesystem MCP Operations - Simple Version"""

import asyncio
from pathlib import Path
import sys

sys.path.append(".")
from src.muxi.runtime import Formation

async def test():
    try:
        print("=== Test 4A1: Filesystem MCP Operations (Simple) ===")
        print("Loading formation...")
        
        formation = Formation()
        formation.load("test-formations/formation-mcp")
        
        print("Starting overlord...")
        overlord = formation.start_overlord()
        
        print("Overlord started successfully!")
        
        # Simple test
        print("\nTesting file creation...")
        response = await overlord.chat(
            "Create a file called 'test.txt' with content 'Hello World' in /Users/ran/Desktop/tests",
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