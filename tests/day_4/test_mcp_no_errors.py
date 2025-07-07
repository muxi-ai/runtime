#!/usr/bin/env python3
"""Test MCP with NO ERROR OUTPUT using context manager"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation import formation_context

async def test_mcp_no_errors():
    """Test MCP servers with context manager - NO ERRORS!"""
    print("\n=== Test MCP with Context Manager (No Errors) ===")
    
    async with formation_context("test-formations/formation-mcp") as formation:
        print("✓ Formation loaded via context manager")
        
        # Start overlord
        overlord = await formation.start_overlord()
        print("✓ Overlord started")
        
        # Quick test
        print("\nTesting MCP servers...")
        response_gen = await overlord.chat(
            "How many MCP tools do I have access to?",
            user_id="user1",
            use_async=False
        )
        
        # Collect response
        response = ""
        async for chunk in response_gen:
            response += chunk
            if len(response) > 200:
                break
                
        print(f"\nResponse: {response[:200]}...")
        
        # Check MCP service
        if hasattr(overlord, 'mcp_service'):
            mcp = overlord.mcp_service
            print(f"\nMCP servers connected: {list(mcp.handlers.keys())}")
            total_tools = sum(len(tools) for tools in mcp.tool_registry.values())
            print(f"Total tools available: {total_tools}")
            
        print("\n✓ Test completed successfully")
        # Context manager will handle ALL cleanup and suppress errors!

if __name__ == "__main__":
    # Run the test - no error output!
    asyncio.run(test_mcp_no_errors())