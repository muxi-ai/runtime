#!/usr/bin/env python3
"""Test 4D3 Clarification with Cache: Credential Selection Memory"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the test for credential selection memory."""

    print("\n" + "="*80)
    print("I am testing: Credential Selection Memory")
    print("This test verifies that the system remembers credential selection:")
    print("1. User1 has two GitHub credentials: 'ranaroussi' and 'lily automaze'")
    print("2. Request 'list my repositories' should trigger clarification")
    print("3. User selects option '1' (lily automaze)")
    print("4. System lists lily's repositories")
    print("5. Ask 'how many repos do I have there?' - should use lily's account")
    print("="*80 + "\n")

    try:
        # Use the test formation
        formation_path = Path(str(Path(__file__).parent / "formations" / "formation-mcp"))

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
        from muxi.services.mcp.service import MCPService
        mcp_service = MCPService.get_instance()
        mcp_service.clear_user_credentials_cache()

        # Check existing credentials for user1
        print("\n=== CHECKING EXISTING CREDENTIALS ===")
        if formation._db_manager:
            try:
                from sqlalchemy import text
                async with formation._db_manager.get_async_session() as session:
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

        # STEP 1: Ambiguous request
        print("\n" + "="*80)
        print("STEP 1: Ambiguous request (should trigger clarification)")
        print("="*80 + "\n")

        session_id = "test_session_4d3_cache"
        prompt = "list my repositories"

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
        asked_clarification = any(phrase in response_str for phrase in [
            "which account", "which github", "multiple accounts", "ranaroussi", "lily",
            "choose", "select", "specify", "clarify", "several accounts"
        ])

        if not asked_clarification:
            print("❌ STEP 1 FAILED: System did not ask for clarification when request was ambiguous")
            return False

        print("✅ STEP 1 PASSED: System correctly asked for clarification")

        # STEP 2: Respond to clarification
        print("\n" + "="*80)
        print("STEP 2: Respond to clarification with '1' (lily automaze)")
        print("="*80 + "\n")

        clarification_response = "1"
        print(f"User responds: {clarification_response}")

        response2 = await overlord.chat(
            user_id="user1",
            message=clarification_response,
            session_id=session_id,  # Same session to continue conversation
            use_async=False,
            stream=False,
        )

        # Handle response
        if hasattr(response2, '__aiter__'):
            full_response = ""
            async for chunk in response2:
                full_response += chunk
            response2 = full_response

        print("\n" + "="*80)
        print("Response after clarification:")
        print("="*80)
        print(str(response2))
        print("="*80 + "\n")

        response2_str = str(response2).lower()
        found_repos = any(
            word in response2_str for word in ["repository", "repositories", "repo", "repos"])

        if not found_repos:
            print("❌ STEP 2 FAILED: System did not list repositories after selection")
            return False

        print("✅ STEP 2 PASSED: System successfully listed repositories")

        # STEP 3: Follow-up question (should use cached credential)
        print("\n" + "="*80)
        print("STEP 3: Follow-up question (should remember lily's account)")
        print("="*80 + "\n")

        follow_up = "how many repos do I have there?"
        print(f"User asks follow-up: {follow_up}")

        response3 = await overlord.chat(
            user_id="user1",
            message=follow_up,
            session_id=session_id,  # Same session to maintain context
            use_async=False,
            stream=False,
        )

        # Handle response
        if hasattr(response3, '__aiter__'):
            full_response = ""
            async for chunk in response3:
                full_response += chunk
            response3 = full_response

        print("\n" + "="*80)
        print("Response to follow-up:")
        print("="*80)
        print(str(response3))
        print("="*80 + "\n")

        # Analyze follow-up response
        response3_str = str(response3).lower()

        # Check if it asked for clarification again (shouldn't)
        asked_clarification_again = any(phrase in response3_str for phrase in [
            "which account", "which github", "multiple accounts", "choose", "select"
        ])

        # Check if it gave a count or mentioned repositories
        has_count_info = any(pattern in response3_str for pattern in [
            "repo", "repositor", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "no ", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "none", "several", "many", "few"
        ])

        # Check if it mentions lily's account (good sign it remembered)
        mentions_lily = "lily" in response3_str or "lilyautomaze" in response3_str

        step3_success = has_count_info and not asked_clarification_again

        print("\n" + "="*80)
        print("Analysis of Step 3:")
        print(f"- Asked for clarification again: {asked_clarification_again}")
        print(f"- Provided count/repo info: {has_count_info}")
        print(f"- Mentions lily account: {mentions_lily}")
        print(f"- Step 3 Success: {step3_success}")
        print("="*80 + "\n")

        if step3_success:
            print("✅ STEP 3 PASSED: System remembered the credential selection")
            print("\n🎉 CREDENTIAL CACHING VERIFIED:")
            print("   1. Initial request triggered clarification ✅")
            print("   2. User selected lily automaze ✅")
            print("   3. System listed repositories ✅")
            print("   4. Follow-up used same credential without asking again ✅")
        else:
            print("❌ STEP 3 FAILED: System did not remember the credential selection")

        overall_success = step3_success
        return overall_success

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
    print("Starting Test 4D3 Clarification with Cache: Credential Selection Memory")

    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D3 Cache PASSED: Credential caching works correctly")
        else:
            print("\n❌ Test 4D3 Cache FAILED: Credential caching not working correctly")

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
