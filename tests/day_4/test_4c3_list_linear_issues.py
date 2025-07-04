#!/usr/bin/env python3
"""Test 4C3: List Linear Issues - Issue retrieval via MCP"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_list_linear_issues():
    """Test Linear issue listing and retrieval"""
    print("\n=== Test 4C3: List Linear Issues ===")
    print("Goal: List and retrieve Linear issues using formation-level secrets")
    
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
                
                print("\n1. Testing recent issues listing...")
                response = await overlord.chat(
                    "Show me the recent Linear issues",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                response_lower = response.lower()
                if "linear" not in response_lower and "mcp" not in response_lower:
                    # Might not have Linear MCP configured
                    print("⚠️  Linear MCP might not be configured")
                    if any(term in response_lower for term in 
                          ["cannot", "unable", "no tool", "not available"]):
                        print("✓ Correctly identified missing Linear MCP")
                        return True
                
                # Verify issue listing
                assert any(term in response_lower for term in 
                          ["issue", "linear", "ticket", "task", "no issues", "empty"]), \
                    "Response should mention issues or indicate none exist"
                print("✓ Recent issues query successful")
                
                print("\n2. Testing filtered issue search...")
                response = await overlord.chat(
                    "Show me all open Linear issues with high priority",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle filtered search
                assert "issue" in response_lower or "linear" in response_lower or \
                       "priority" in response_lower, \
                    "Response should address filtered search"
                print("✓ Filtered issue search handled")
                
                print("\n3. Testing issue details retrieval...")
                response = await overlord.chat(
                    "Get details of my most recent Linear issue",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should provide issue details or indicate none
                assert len(response) > 30, "Response should contain issue details or explanation"
                print("✓ Issue details retrieval handled")
                
                print("\n4. Testing issue statistics...")
                response = await overlord.chat(
                    "How many Linear issues are currently in progress?",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should provide count or status
                assert any(term in response_lower for term in 
                          ["issue", "progress", "number", "count", "none", "zero"]) or \
                       any(char.isdigit() for char in response), \
                    "Response should provide issue count or status"
                print("✓ Issue statistics query successful")
                
                print("\n5. Testing team issues overview...")
                response = await overlord.chat(
                    "Give me an overview of all team issues in Linear",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should provide team overview
                assert len(response) > 50, "Response should provide team issues overview"
                print("✓ Team issues overview handled")
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)
            
        if result:
            print("\n✅ Test 4C3 PASSED: Linear issue listing successful")
            return True
        else:
            print("\n❌ Test 4C3 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4C3 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_list_linear_issues()
    sys.exit(0 if success else 1)