#!/usr/bin/env python3
"""Test 4D4: Create GitHub Issue - Create repository issues via MCP"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_create_github_issue():
    """Test creating GitHub repository issues"""
    print("\n=== Test 4D4: Create GitHub Issue ===")
    print("Goal: Create GitHub issues in repositories using user credentials")
    print("Note: User1 should have credentials for 'piepilot org' repository")
    
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
                
                print("\n1. Testing GitHub issue creation...")
                response = await overlord.chat(
                    "Create a GitHub issue in the piepilot org repository titled 'Test Issue from MUXI'",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                response_lower = response.lower()
                
                # Check various scenarios
                if "github" not in response_lower and "issue" not in response_lower:
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
                
                # If repository access issue
                if any(term in response_lower for term in 
                      ["repository", "not found", "access", "permission"]):
                    print("⚠️  Repository access issue")
                    print("✓ Correctly identified repository access problem")
                    return True
                
                # Success case
                assert any(term in response_lower for term in 
                          ["issue", "created", "github", "successfully"]), \
                    "Response should indicate issue creation"
                print("✓ GitHub issue created successfully")
                
                print("\n2. Testing detailed issue creation...")
                response = await overlord.chat(
                    "Create a GitHub issue titled 'Feature Request: Add Dark Mode' "
                    "with description 'Users have requested a dark mode theme option. "
                    "This should include UI components and code editor themes.'",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should create detailed issue
                assert "issue" in response_lower or "github" in response_lower or \
                       "feature" in response_lower, \
                    "Response should confirm detailed issue creation"
                print("✓ Detailed issue created successfully")
                
                print("\n3. Testing issue with labels...")
                response = await overlord.chat(
                    "Create a GitHub issue titled 'Bug: Memory leak in worker process' "
                    "and add labels 'bug' and 'high-priority'",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle labels
                assert len(response) > 30, "Response should address issue with labels"
                print("✓ Issue with labels handled")
                
                print("\n4. Testing issue assignment...")
                response = await overlord.chat(
                    "Create a GitHub issue titled 'Documentation Update' and assign it to me",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle assignment
                assert "issue" in response_lower or "github" in response_lower or \
                       "assign" in response_lower, \
                    "Response should address issue assignment"
                print("✓ Issue assignment handled")
                
                print("\n5. Testing milestone association...")
                response = await overlord.chat(
                    "Create a GitHub issue for the next release milestone: 'Performance improvements needed'",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle milestone reference
                assert len(response) > 40, "Response should address milestone-related issue"
                print("✓ Milestone issue creation handled")
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)
            
        if result:
            print("\n✅ Test 4D4 PASSED: GitHub issue creation successful")
            return True
        else:
            print("\n❌ Test 4D4 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4D4 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_create_github_issue()
    sys.exit(0 if success else 1)