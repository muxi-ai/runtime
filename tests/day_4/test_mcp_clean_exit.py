#!/usr/bin/env python3
"""Test MCP with clean exit utilities"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation import Formation, aclean_exit, suppress_async_generator_errors

async def test_mcp_clean_exit():
    """Test MCP servers with clean exit"""
    print("\n=== Test MCP with Clean Exit ===")
    
    # Suppress the warnings
    suppress_async_generator_errors()
    
    # Create formation
    formation = Formation()
    
    # Load formation
    await formation.load("test-formations/formation-mcp")
    print("✓ Formation loaded")
    
    # Start overlord
    overlord = await formation.start_overlord()
    print("✓ Overlord started")
    
    # Quick test
    print("\nTesting a simple query...")
    response_gen = await overlord.chat(
        "List the MCP servers",
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        if len(response) > 100:
            break
            
    print(f"Response: {response[:100]}...")
    
    # Check MCP service
    if hasattr(overlord, 'mcp_service'):
        mcp = overlord.mcp_service
        print(f"\nMCP servers connected: {list(mcp.handlers.keys())}")
        
    # Use clean exit
    print("\nUsing clean exit...")
    await aclean_exit(formation)

if __name__ == "__main__":
    asyncio.run(test_mcp_clean_exit())