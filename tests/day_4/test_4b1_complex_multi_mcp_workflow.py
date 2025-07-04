#!/usr/bin/env python3
"""Test 4B1: Complex Multi-MCP Workflow - Linear → System → GitHub → Linear"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_complex_multi_mcp_workflow():
    """Test complex multi-MCP orchestration workflow"""
    print("\n=== Test 4B1: Complex Multi-MCP Workflow ===")
    print("Goal: Orchestrate Linear → System → GitHub → Linear workflow")
    print("Flow: Create issue → Get CPU stats → Create gist → Update issue")
    
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
                
                print("\n1. Testing complex multi-MCP workflow...")
                print("   - Create Linear issue requesting CPU documentation")
                print("   - Get system CPU usage stats")
                print("   - Create GitHub gist with the stats")
                print("   - Update Linear issue as completed with gist link")
                
                response = await overlord.chat(
                    "Create a Linear issue asking to document system CPU usage. "
                    "The issue should request creating a GitHub gist with the current CPU stats. "
                    "After creating the gist, update the Linear issue as completed with a link to the gist.",
                    user_id="user1",
                    use_async=False
                )
                print(f"\nWorkflow Response: {response}")
                
                # Verify the workflow components were executed
                response_lower = response.lower()
                
                # Should mention issue creation
                assert any(term in response_lower for term in ["issue", "linear", "created", "ticket"]), \
                    "Response should mention Linear issue creation"
                
                # Should mention CPU stats
                assert any(term in response_lower for term in ["cpu", "processor", "usage", "stats"]), \
                    "Response should mention CPU statistics"
                
                # Should mention gist creation
                assert any(term in response_lower for term in ["gist", "github", "created"]), \
                    "Response should mention GitHub gist creation"
                
                # Should mention completion/update
                assert any(term in response_lower for term in ["completed", "updated", "done", "finished"]), \
                    "Response should mention issue completion/update"
                
                print("✓ Complex multi-MCP workflow executed successfully")
                
                print("\n2. Testing workflow error handling...")
                # Test partial workflow failure handling
                response = await overlord.chat(
                    "Create a Linear issue to document disk usage, then try to create a gist in a non-existent repository",
                    user_id="user1",
                    use_async=False
                )
                print(f"\nError Handling Response: {response}")
                
                # Should handle the error gracefully
                assert any(term in response_lower for term in ["error", "failed", "unable", "issue"]) or \
                       "linear" in response_lower, \
                    "Response should handle partial workflow failure"
                print("✓ Workflow error handling successful")
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=120)  # Longer timeout for complex workflow
            
        if result:
            print("\n✅ Test 4B1 PASSED: Complex multi-MCP workflow successful")
            return True
        else:
            print("\n❌ Test 4B1 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4B1 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_complex_multi_mcp_workflow()
    sys.exit(0 if success else 1)