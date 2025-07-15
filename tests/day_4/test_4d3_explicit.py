#!/usr/bin/env python3
"""Test 4D3 Explicit: Specific Account Request"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the test for explicit account request."""

    print("\n" + "="*80)
    print("I am testing: Explicit Account Request")
    print("This test verifies that specific account requests work without clarification:")
    print("1. User1 has two GitHub credentials: 'ranaroussi' and 'lily automaze'")
    print("2. Request for 'lily account' should directly use the lily credential")
    print("="*80 + "\n")

    try:
        # Use the test formation
        formation_path = Path("test-formations/formation-mcp")

        # Load formation
        print("Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))

        # Start overlord
        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Give MCP servers time to initialize
        print("\nWaiting for MCP servers to initialize...")
        await asyncio.sleep(3)

        # Clear any existing buffer/cache to ensure clean test
        print("\nClearing buffer and credential cache...")
        if hasattr(overlord, '_buffer_memory'):
            overlord._buffer_memory.clear()

        # Clear MCP credential cache
        from src.muxi.runtime.services.mcp.service import MCPService
        mcp_service = MCPService.get_instance()
        mcp_service.clear_user_credentials_cache()

        # Check existing credentials for user1
        print("\n=== CHECKING EXISTING CREDENTIALS ===")
        if formation._db_manager:
            try:
                from sqlalchemy import text
                async with formation._db_manager.get_session() as session:
                    result = await session.execute(
                        text("""
                        SELECT u.external_user_id, c.name, c.service
                        FROM credentials c
                        JOIN users u ON c.user_id = u.id
                        WHERE u.external_user_id = :user_id
                        AND c.service = 'github'
                        ORDER BY c.name
                        """),
                        {"user_id": "user1"}
                    )
                    rows = result.fetchall()
                    print(f"Found {len(rows)} GitHub credentials for user1:")
                    for row in rows:
                        print(f"  - Name: '{row.name}'")
            except Exception as e:
                print(f"Error checking credentials: {e}")

        # TEST: Request for lily account
        print("\n" + "="*80)
        print("TEST: Request for lily account (should find and use it directly)")
        print("="*80 + "\n")

        session_id = "test_session_4d3_explicit"
        prompt = "list the repositories in my lily account"

        print("User: user1")
        print(f"Prompt: {prompt}")

        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            session_id=session_id,
            use_async=False,
            stream=False,
        )

        # Handle response
        if hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response

        print("\n" + "="*80)
        print("Response:")
        print("="*80)
        print(str(response))
        print("="*80 + "\n")

        # Analyze response
        response_str = str(response).lower()

        # Check if it asked for clarification (shouldn't happen for specific request)
        asked_clarification = any(phrase in response_str for phrase in [
            "which account", "which github", "multiple accounts", "choose", "select"
        ])

        # Check if it found repositories (indicates successful use of lily credential)
        found_repos = any(word in response_str for word in ["repository", "repositories", "repo", "repos"])
        has_error = "error" in response_str or "failed" in response_str

        # Check if it mentions lily's account specifically
        mentions_lily = "lily" in response_str or "lilyautomaze" in response_str

        success = found_repos and not has_error and not asked_clarification

        print("\n" + "="*80)
        print("Analysis:")
        print(f"- Asked for clarification: {asked_clarification}")
        print(f"- Found repositories: {found_repos}")
        print(f"- Has error: {has_error}")
        print(f"- Mentions lily account: {mentions_lily}")
        print(f"- Test Success: {success}")
        print("="*80 + "\n")

        if not success:
            print("❌ TEST FAILED: System did not directly use the lily account when specifically requested")
        else:
            print("✅ TEST PASSED: System correctly used lily account without clarification")

        return success

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        try:
            await formation.stop_overlord(5.0)
        except Exception:
            formation.kill_overlord()


def main():
    """Main entry point."""
    print("Starting Test 4D3 Explicit: Specific Account Request")

    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D3 Explicit PASSED: Specific account request handled correctly")
        else:
            print("\n❌ Test 4D3 Explicit FAILED: Specific account request not handled correctly")

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
    main()
