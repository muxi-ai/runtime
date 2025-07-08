#!/usr/bin/env python3
"""Test 4D1: GitHub MCP Tool Discovery and User Credentials"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""

    print("\nTEST 4D1: GitHub MCP Tool Discovery and User Credentials")
    print("Step 1: Testing MCP initialization and tool discovery")
    print("Step 2: Testing user credential resolution at runtime")
    print()

    try:
        # Use the actual test formation which has database configured
        formation_path = Path("test-formations/formation-mcp")

        # Load formation
        formation = Formation()

        # Use async API directly
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Give MCP servers time to fully initialize
        print("Waiting for MCP servers to initialize...")
        await asyncio.sleep(3)

        # Debug: Check available MCP tools
        print("\n=== CHECKING MCP TOOL DISCOVERY ===")
        mcp_service = overlord.mcp_service
        if mcp_service:
            # The tool registry is stored directly in the service
            tools = mcp_service.tool_registry
            print(f"Total MCP tools available: {len(tools)}")
            
            # Check specifically for GitHub tools
            github_tools = [tool for tool in tools.keys() if 'github' in tool.lower()]
            if github_tools:
                print(f"\nGitHub MCP tools discovered: {len(github_tools)}")
                print("Sample GitHub tools:")
                for tool in github_tools[:5]:  # Show first 5
                    print(f"  - {tool}")
                print("✓ GitHub MCP initialized successfully!")
            else:
                print("⚠️  No GitHub MCP tools found - might be missing credentials")
        else:
            print("⚠️  No MCP service available!")

        # Now test actual tool invocation with user credentials
        print("\n=== TESTING USER CREDENTIAL RESOLUTION ===")
        print("Testing with user1 who has GitHub credentials in the database...")
        
        # Try to create a repository (not gist, as GitHub MCP doesn't support gists)
        prompt = "Create a new GitHub repository called 'muxi-test-repo' with description 'Test repository for MUXI Runtime'"
        print(f"\nPrompt: {prompt}")

        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            use_async=False,
            stream=False,
        )

        # Handle different response types
        if isinstance(response, dict) and "request_id" in response:
            print(f"Async response received: {response}")
            await asyncio.sleep(3)
        elif hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response

        print(f"\nResponse type: {type(response)}")
        print(f"Response: {response}")
        
        # Check if it used user credentials or failed
        response_lower = str(response).lower()
        if "repository" in response_lower and "created" in response_lower:
            print("\n✓ Successfully created repository using user1's credentials!")
        elif "credential" in response_lower or "token" in response_lower or "auth" in response_lower:
            print("\n⚠️  Credential issue detected - checking clarification flow")
        else:
            print(f"\n⚠️  Unexpected response - check output above")

        # Test with user2 who doesn't have credentials
        print("\n=== TESTING MISSING CREDENTIAL FLOW ===")
        print("Testing with user2 who does NOT have GitHub credentials...")
        
        response = await overlord.chat(
            user_id="user2",
            message="Create a GitHub repository called 'muxi-test-2'",
            use_async=False,
            stream=False,
        )

        # Handle different response types
        if hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response

        print(f"\nUser2 Response: {response}")
        
        response_lower = str(response).lower()
        if any(term in response_lower for term in ["credential", "token", "auth", "provide", "need"]):
            print("\n✓ Correctly triggered clarification flow for missing credentials!")
        else:
            print("\n⚠️  Expected clarification flow but got different response")

        print("\n🔚 Stopping overlord...")
        await formation.stop_overlord(10.0)
        print("✅ Test complete!")

        # Clean shutdown to avoid async generator errors
        formation.shutdown(0)

    except Exception as e:
        print(f"\n❌ Test 4D1 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    print("Starting GitHub MCP tool discovery and credential test...")

    # Run everything in a single event loop that persists until completion
    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D1 PASSED")
        else:
            print("\n❌ Test 4D1 FAILED")

        # Force exit to avoid MCP SDK cleanup hang
        import os
        os._exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        import os
        os._exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        import os
        os._exit(1)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)