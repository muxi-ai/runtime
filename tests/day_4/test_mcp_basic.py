#!/usr/bin/env python3
"""Test MCP Basic - Check if MCP servers are starting correctly"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_mcp_basic():
    """Test basic MCP server startup"""
    print("\n=== Test MCP Basic Server Startup ===")
    print("Goal: Verify MCP servers are starting")
    
    try:
        # Run the async test in a thread pool to avoid event loop issues
        def run_test():
            async def test_operations():
                # Load formation with MCP enabled
                formation = Formation()
                await formation.load("test-formations/formation-mcp")
                
                # Check loaded MCP servers
                mcp_service = formation.configured_services.get('mcp_service')
                if mcp_service:
                    print(f"\nMCP Service found: {mcp_service}")
                    print(f"Registered servers: {list(mcp_service.servers.keys())}")
                
                # Start overlord
                overlord = await formation.start_overlord()
                
                # Give MCP servers time to initialize
                await asyncio.sleep(5)
                
                # Check MCP server status
                if mcp_service:
                    print("\nMCP Server Status:")
                    for server_id, server_info in mcp_service.servers.items():
                        handler = mcp_service.handlers.get(server_id)
                        if handler:
                            print(f"  {server_id}: Connected")
                        else:
                            print(f"  {server_id}: Not connected")
                
                # Try a simple query
                print("\n\nTesting simple query...")
                response_gen = await overlord.chat(
                    "What tools do you have available?",
                    user_id="user1",
                    use_async=False
                )
                
                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                    
                print(f"\nResponse: {response[:500]}...")  # First 500 chars
                
                # Stop the overlord
                await formation.stop_overlord()
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=30)  # Short timeout
            
        if result:
            print("\n✅ MCP Basic Test PASSED")
            return True
        else:
            print("\n❌ MCP Basic Test FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ MCP Basic Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_mcp_basic()
    sys.exit(0 if success else 1)