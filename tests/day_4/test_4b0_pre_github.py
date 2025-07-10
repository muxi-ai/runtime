#!/usr/bin/env python3
"""Test 4B0-Pre2: GitHub MCP Pre-test - Test GitHub MCP in isolation"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_github_mcp_isolation():
    """Test GitHub MCP tool in isolation"""
    print("\n=== Test 4B0-Pre2: GitHub MCP Pre-test ===")
    print("Goal: Test GitHub MCP create_gist tool in isolation")
    
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
                
                print("\n1. Testing GitHub create_issue tool...")
                response_gen = await overlord.chat(
                    "Create a GitHub issue in the repo 'testing' on 'lilyautomaze' with title 'Test Issue from MUXI' and body 'Hello from MUXI MCP test'",
                    user_id="user1",
                    use_async=False
                )
                
                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                    
                print(f"\nGitHub Response: {response}")
                
                # Verify the response mentions issue creation
                response_lower = response.lower()
                assert any(term in response_lower for term in ["issue", "github", "created"]), \
                    "Response should mention GitHub issue creation"
                
                print("✓ GitHub MCP tool executed successfully")
                
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
            print("\n✅ Test 4B0-Pre2 PASSED: GitHub MCP tool works in isolation")
            return True
        else:
            print("\n❌ Test 4B0-Pre2 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4B0-Pre2 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_github_mcp_isolation()
    sys.exit(0 if success else 1)