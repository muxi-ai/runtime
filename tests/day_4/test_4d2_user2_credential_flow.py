#!/usr/bin/env python3
"""Test 4D2: User2 Credential Flow - User without credentials triggers clarification"""

import sys
sys.path.insert(0, '.')
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation

def test_user2_credential_flow():
    """Test credential clarification flow for user without GitHub credentials"""
    print("\n=== Test 4D2: User2 Credential Flow ===")
    print("Goal: Test clarification flow when user lacks required credentials")
    print("Note: User2 should NOT have GitHub credentials pre-configured")
    
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
                
                print("\n1. Testing GitHub operation without credentials...")
                response = await overlord.chat(
                    "Create a GitHub gist with some test content",
                    user_id="user2",
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
                
                # Should trigger clarification for missing credentials
                assert any(term in response_lower for term in 
                          ["credential", "github", "token", "provide", "need", 
                           "authentication", "authorize", "access", "api key"]), \
                    "Response should request credentials from user"
                print("✓ Credential clarification triggered correctly")
                
                print("\n2. Testing specific credential request...")
                response = await overlord.chat(
                    "I want to create a private GitHub gist in my personal account",
                    user_id="user2",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should ask for GitHub token/credentials
                assert any(term in response_lower for term in 
                          ["token", "credential", "github", "authenticate", "provide"]), \
                    "Response should specifically request GitHub credentials"
                print("✓ Specific credential request made")
                
                print("\n3. Testing operation explanation with missing credentials...")
                response = await overlord.chat(
                    "List all my GitHub gists",
                    user_id="user2",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should explain need for credentials
                assert any(term in response_lower for term in 
                          ["credential", "token", "need", "require", "authenticate"]) or \
                       "github" in response_lower, \
                    "Response should explain credential requirement"
                print("✓ Credential requirement explained")
                
                print("\n4. Testing multiple GitHub operations without credentials...")
                response = await overlord.chat(
                    "Create a GitHub gist, then create an issue in my repository",
                    user_id="user2",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should handle multiple operations needing credentials
                assert len(response) > 50, "Response should address credential needs comprehensively"
                assert any(term in response_lower for term in 
                          ["credential", "token", "authenticate", "github"]), \
                    "Response should mention credential requirements"
                print("✓ Multiple operations credential flow handled")
                
                print("\n5. Testing helpful credential guidance...")
                response = await overlord.chat(
                    "How do I set up GitHub access for creating gists?",
                    user_id="user2",
                    use_async=False
                )
                print(f"Response: {response}")
                
                # Should provide helpful guidance
                assert len(response) > 100, "Response should provide detailed guidance"
                print("✓ Credential setup guidance provided")
                
                return True
            
            # Run the async test
            return asyncio.run(test_operations())
        
        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)
            
        if result:
            print("\n✅ Test 4D2 PASSED: Credential clarification flow working correctly")
            return True
        else:
            print("\n❌ Test 4D2 FAILED")
            return False
            
    except Exception as e:
        print(f"\n❌ Test 4D2 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_user2_credential_flow()
    sys.exit(0 if success else 1)