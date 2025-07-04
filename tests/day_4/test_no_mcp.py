#!/usr/bin/env python3
"""Test formation without MCP"""

import asyncio
import sys

sys.path.append(".")
from src.muxi.runtime import Formation

async def test():
    try:
        print("=== Testing Formation Without MCP ===")
        
        formation = Formation()
        formation.load("test-formations/formation-mcp-disabled")
        
        print("Starting overlord...")
        overlord = formation.start_overlord()
        
        print("✓ Overlord started successfully!")
        
        # Simple test
        response = await overlord.chat(
            "Hello, how are you?",
            user_id="user1",
            use_async=False
        )
        
        print(f"\nResponse: {response}")
        
        formation.stop_overlord()
        print("\n✓ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())