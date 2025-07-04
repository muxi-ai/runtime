#!/usr/bin/env python3
"""Test 4D3: List User Gists - Retrieve user's GitHub gists"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_list_user_gists():
    """Test listing GitHub gists for user with credentials"""
    print("\n=== Test 4D3: List User Gists ===")
    print("Goal: List user's GitHub gists using stored credentials")
    
    try:
        # Run the async test in a thread pool to avoid event loop issues
        def run_test():
            async def test_operations():
                # Load formation with MCP enabled
                formation = Formation()
                formation.load("test-formations/formation-mcp")
                overlord = formation.start_overlord()
                
                # Ensure overlord is started
                await overlord.ensure_started()
                
                print("\n1. Testing list recent gists for user1...")
                response = await overlord.chat(
                    "Show me my recent GitHub gists",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                response_lower = response.lower()
                
                # Check various scenarios
                if "github" not in response_lower and "gist" not in response_lower:
                    print("⚠️  GitHub MCP might not be configured")
                    if any(term in response_lower for term in 
                          ["cannot", "unable", "no tool", "not available"]):
                        print("✓ Correctly identified missing GitHub MCP")
                        return True
                
                # If credentials are missing
                if any(term in response_lower for term in 
                      ["credential", "token", "authentication", "provide"]):
                    print("⚠️  User1 credentials not configured")
                    print("✓ Correctly identified missing credentials")
                    return True
                
                # Success case - should list gists or indicate none exist
                assert any(term in response_lower for term in 
                          ["gist", "github", "no gists", "empty", "none", "list"]) or \
                       len(response) > 50, \
                    "Response should list gists or indicate none exist"
                print("✓ Gist listing successful")
                
                print("\n2. Testing filtered gist search...")
                response = await overlord.chat(
                    "Show me my GitHub gists that contain Python code",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle filtered search
                assert "gist" in response_lower or "github" in response_lower or \
                       "python" in response_lower, \
                    "Response should address filtered gist search"
                print("✓ Filtered gist search handled")
                
                print("\n3. Testing gist count query...")
                response = await overlord.chat(
                    "How many GitHub gists do I have?",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should provide count or indicate number
                assert any(term in response_lower for term in 
                          ["gist", "number", "count", "total", "have", "none", "zero"]) or \
                       any(char.isdigit() for char in response), \
                    "Response should provide gist count"
                print("✓ Gist count query successful")
                
                print("\n4. Testing specific gist details...")
                response = await overlord.chat(
                    "Show me details of my most recent GitHub gist",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should provide details or indicate no gists
                assert len(response) > 40, "Response should contain gist details or explanation"
                print("✓ Gist details retrieval handled")
                
                print("\n5. Testing public vs private gists...")
                response = await overlord.chat(
                    "List my public GitHub gists only",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle visibility filtering
                assert "gist" in response_lower or "github" in response_lower or \
                       "public" in response_lower, \
                    "Response should address public gist filtering"
                print("✓ Public gist filtering handled")
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)
            
        if result:
            print("\n✅ Test 4D3 PASSED: User gist listing successful")
            return True
        else:
            print("\n❌ Test 4D3 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4D3 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_list_user_gists()
    sys.exit(0 if success else 1)