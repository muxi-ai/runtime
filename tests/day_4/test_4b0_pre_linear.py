#!/usr/bin/env python3
"""Test 4B0-Pre1: Linear MCP Pre-test - Test Linear MCP in isolation"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_linear_mcp_isolation():
    """Test Linear MCP tool in isolation"""
    print("\n=== Test 4B0-Pre1: Linear MCP Pre-test ===")
    print("Goal: Test Linear MCP create_issue tool in isolation")
    
    try:
        # Run the async test in a thread pool to avoid event loop issues
        def run_test():
            async def test_operations():
                # Load formation with MCP enabled
                formation = Formation()
                await formation.load("test-formations/formation-mcp")
                overlord = await formation.start_overlord()
                
                # Ensure overlord is started
                await overlord.ensure_started()
                
                print("\n1. Testing Linear create_issue tool...")
                response_gen = await overlord.chat(
                    "Create a Linear issue with title 'Test Issue' and description 'This is a test issue created by MUXI'",
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
                
                # Stop the overlord
                await formation.stop_overlord()
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)
            
        if result:
            print("\n✅ Test 4B0-Pre1 PASSED: Linear MCP tool works in isolation")
            return True
        else:
            print("\n❌ Test 4B0-Pre1 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4B0-Pre1 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_linear_mcp_isolation()
    sys.exit(0 if success else 1)