#!/usr/bin/env python3
"""Test 4B0-Pre3: System MCP Pre-test - Test System MCP in isolation"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_system_mcp_isolation():
    """Test System MCP tool in isolation"""
    print("\n=== Test 4B0-Pre3: System MCP Pre-test ===")
    print("Goal: Test System MCP get_cpu_usage tool in isolation")
    
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
                
                print("\n1. Testing System get_cpu_usage tool...")
                response_gen = await overlord.chat(
                    "Get the current CPU usage statistics from the system",
                    user_id="user1",
                    use_async=False
                )
                
                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                    
                print(f"\nSystem Response: {response}")
                
                # Verify the response mentions CPU stats
                response_lower = response.lower()
                assert any(term in response_lower for term in ["cpu", "usage", "percent", "core"]), \
                    "Response should mention CPU statistics"
                
                print("✓ System MCP tool executed successfully")
                
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
            print("\n✅ Test 4B0-Pre3 PASSED: System MCP tool works in isolation")
            return True
        else:
            print("\n❌ Test 4B0-Pre3 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4B0-Pre3 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_system_mcp_isolation()
    sys.exit(0 if success else 1)