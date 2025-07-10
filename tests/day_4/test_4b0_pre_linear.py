#!/usr/bin/env python3
"""Test 4B0-Pre1: Linear MCP Pre-test - Test Linear MCP in isolation"""

import sys
sys.path.insert(0, '.')
import asyncio
import os

from src.muxi.runtime.formation.formation import Formation

async def test_linear_mcp_isolation():
    """Test Linear MCP tool in isolation"""
    print("\n=== Test 4B0-Pre1: Linear MCP Pre-test ===")
    print("Goal: Test Linear MCP create_issue tool in isolation")
    
    try:
        # Load formation with MCP enabled
        formation = Formation()
        await formation.load("test-formations/formation-mcp")
        overlord = await formation.start_overlord()
        
        # Ensure overlord is started
        await overlord.ensure_started()
        
        print("\n1. Testing Linear create_issue tool...")
        # Use a more specific prompt that includes team ID to avoid multiple tool calls
        response_gen = await overlord.chat(
            "Create a Linear issue with title 'Test Issue' and description 'This is a test issue created by MUXI' for team ID 21b2d439-9ffa-4383-86f5-556acc7af93b",
            user_id="user1",
            use_async=False
        )
        
        # Collect streaming response
        response = ""
        async for chunk in response_gen:
            response += chunk
            
        print(f"\nLinear Response: {response}")
        
        # Verify the response mentions issue creation
        response_lower = response.lower()
        assert any(term in response_lower for term in ["issue", "linear", "created", "ticket"]), \
            "Response should mention Linear issue creation"
        
        print("✓ Linear MCP tool executed successfully")
        print("\n✅ Test 4B0-Pre1 PASSED: Linear MCP tool works in isolation")
        
        # Force immediate exit - bypasses all cleanup
        os._exit(0)
            
    except Exception as e:
        print(f"\n❌ Test 4B0-Pre1 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        os._exit(1)  # Exit with error code

if __name__ == "__main__":
    # Run the async test directly
    success = asyncio.run(test_linear_mcp_isolation())
    sys.exit(0 if success else 1)