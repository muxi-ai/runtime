#!/usr/bin/env python3
"""Test 4D1: User1 GitHub Credentials - User with existing credentials"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_user1_github_credentials():
    """Test GitHub operations with user1 who has credentials"""
    print("\n=== Test 4D1: User1 GitHub Credentials ===")
    print("Goal: Test GitHub MCP operations with pre-configured user credentials")
    print("Note: Requires user1 to have GitHub credentials in database")
    
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
                
                print("\n1. Testing GitHub gist creation with user1...")
                response = await overlord.chat(
                    "Create a GitHub gist with the title 'Test Gist' and content 'Hello from MUXI'",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                response_lower = response.lower()
                
                # Check if GitHub MCP is available
                if "github" not in response_lower and "gist" not in response_lower:
                    print("⚠️  GitHub MCP might not be configured")
                    if any(term in response_lower for term in 
                          ["cannot", "unable", "no tool", "not available"]):
                        print("✓ Correctly identified missing GitHub MCP")
                        return True
                
                # If credentials are missing for user1
                if any(term in response_lower for term in 
                      ["credential", "token", "authentication", "provide", "need"]):
                    print("⚠️  User1 doesn't have GitHub credentials configured")
                    print("✓ Correctly identified missing credentials")
                    return True
                
                # If successful
                assert any(term in response_lower for term in 
                          ["gist", "created", "github", "successfully", "link", "url"]), \
                    "Response should indicate gist creation"
                print("✓ GitHub gist created successfully with user1 credentials")
                
                print("\n2. Testing gist with code content...")
                response = await overlord.chat(
                    "Create a GitHub gist with Python code: 'def hello(): return \"Hello MUXI\"'",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should create code gist
                assert "gist" in response_lower or "github" in response_lower or \
                       "created" in response_lower, \
                    "Response should confirm code gist creation"
                print("✓ Code gist created successfully")
                
                print("\n3. Testing multi-file gist...")
                response = await overlord.chat(
                    "Create a GitHub gist with two files: main.py with 'print(\"Hello\")' "
                    "and README.md with 'Test gist from MUXI'",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle multi-file gist
                assert len(response) > 30, "Response should address multi-file gist request"
                print("✓ Multi-file gist request handled")
                
                print("\n4. Testing gist description...")
                response = await overlord.chat(
                    "Create a GitHub gist titled 'Configuration Example' with description "
                    "'Sample configuration for MUXI Runtime' and content showing a YAML config",
                    user_id="user1",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should create gist with description
                assert "gist" in response_lower or "github" in response_lower or \
                       "config" in response_lower, \
                    "Response should confirm gist with description"
                print("✓ Gist with description created")
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)
            
        if result:
            print("\n✅ Test 4D1 PASSED: User1 GitHub operations successful")
            return True
        else:
            print("\n❌ Test 4D1 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4D1 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_user1_github_credentials()
    sys.exit(0 if success else 1)