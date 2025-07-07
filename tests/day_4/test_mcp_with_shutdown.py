#!/usr/bin/env python3
"""Test MCP with formation.shutdown() - should have no errors!"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation import Formation

async def test_mcp_with_shutdown():
    """Test MCP servers with proper shutdown"""
    print("\n=== Test MCP with formation.shutdown() ===")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    print("✓ Formation loaded")
    
    overlord = await formation.start_overlord()
    print("✓ Overlord started")
    
    # Quick test
    print("\nTesting MCP servers...")
    response_gen = await overlord.chat(
        "How many filesystem tools are available?",
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        if len(response) > 100:
            break
            
    print(f"\nResponse: {response[:100]}...")
    
    # Check MCP service
    if hasattr(overlord, 'mcp_service'):
        mcp = overlord.mcp_service
        print(f"\nMCP servers connected: {list(mcp.handlers.keys())}")
        
    print("\n✓ Test completed successfully")
    print("Calling formation.shutdown()...")
    
    # This should exit immediately with NO ERRORS!
    formation.shutdown(0)

if __name__ == "__main__":
    asyncio.run(test_mcp_with_shutdown())