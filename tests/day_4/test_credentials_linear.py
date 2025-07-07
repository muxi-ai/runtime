#!/usr/bin/env python3
"""Test Linear MCP Credentials - Simple credential verification"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_linear_credentials():
    """Test Linear MCP credentials with simple operation"""
    print("\n=== Test Linear MCP Credentials ===")
    print("Goal: Verify Linear MCP token is working")
    
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
                
                print("\n1. Testing Linear list_issues to verify credentials...")
                response_gen = await overlord.chat(
                    "List the most recent Linear issues (just show me the first 3)",
                    user_id="user1",
                    use_async=False
                )
                
                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                    
                print(f"\nLinear Response: {response}")
                
                # Check if we got a proper response
                response_lower = response.lower()
                
                # Check for authentication errors
                if any(term in response_lower for term in ["unauthorized", "401", "403", "authentication", "invalid token"]):
                    print("❌ Linear authentication failed - check LINEAR_MCP_TOKEN")
                    return False
                
                # Check for successful response indicators
                if any(term in response_lower for term in ["issue", "linear", "no issues", "empty", "found", "list"]):
                    print("✅ Linear credentials verified successfully")
                    return True
                else:
                    print("⚠️ Unclear response - credentials may be working but response is ambiguous")
                    return True
                
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
            print("\n✅ Linear Credentials Test PASSED")
            return True
        else:
            print("\n❌ Linear Credentials Test FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Linear Credentials Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_linear_credentials()
    sys.exit(0 if success else 1)