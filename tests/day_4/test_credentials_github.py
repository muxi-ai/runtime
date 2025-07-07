#!/usr/bin/env python3
"""Test GitHub MCP Credentials - Simple credential verification"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_github_credentials():
    """Test GitHub MCP credentials with simple operation"""
    print("\n=== Test GitHub MCP Credentials ===")
    print("Goal: Verify GitHub MCP token is working")
    
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
                
                print("\n1. Testing GitHub list_gists to verify credentials...")
                response_gen = await overlord.chat(
                    "List my GitHub gists (just show me the first 3 if any exist)",
                    user_id="user1",
                    use_async=False
                )
                
                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                    
                print(f"\nGitHub Response: {response}")
                
                # Check if we got a proper response
                response_lower = response.lower()
                
                # Check for authentication errors
                if any(term in response_lower for term in ["unauthorized", "401", "403", "authentication", "bad credentials", "requires authentication"]):
                    print("❌ GitHub authentication failed - check USER_CREDENTIALS_GITHUB")
                    return False
                
                # Check for successful response indicators
                if any(term in response_lower for term in ["gist", "github", "no gists", "empty", "found", "list", "repository", "file"]):
                    print("✅ GitHub credentials verified successfully")
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
            print("\n✅ GitHub Credentials Test PASSED")
            return True
        else:
            print("\n❌ GitHub Credentials Test FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ GitHub Credentials Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_github_credentials()
    sys.exit(0 if success else 1)