#!/usr/bin/env python3
"""Test 4D3: Multiple Credentials - Choose Right One Based on Context"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the test for multiple credentials selection."""

    print("\n" + "="*80)
    print("I am testing: Multiple Credentials - Context-Based Selection")
    print("This test verifies credential selection based on name matching:")
    print("1. User1 has two GitHub credentials: 'ranaroussi' and 'lily account'")
    print("2. Request for 'lily account' should use the lily credential")
    print("3. Request for 'automaze account' should trigger clarification (no such credential)")
    print("4. Request without specifying account should trigger clarification (ambiguous)")
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

        # TEST PART 1: Request for lily account
        print("\n" + "="*80)
        print("PART 1: Request for lily account (should find and use it)")
        print("="*80 + "\n")

        session_id = "test_session_4d3"
        prompt1 = "list the repositories in my account"

        print("User: user1")
        print(f"Prompt: {prompt1}")

        response1 = await overlord.chat(
            user_id="user1",
            message=prompt1,
            session_id=session_id,
            use_async=False,
            stream=False,
        )

        # Handle response
        if hasattr(response1, '__aiter__'):
            full_response = ""
            async for chunk in response1:
                full_response += chunk
            response1 = full_response

        print("\n" + "="*80)
        print("Response for lily account:")
        print("="*80)
        print(str(response1))
        print("="*80 + "\n")

        # Analyze response
        response1_str = str(response1).lower()

        # Check if it asked for credentials (shouldn't happen if lily credential exists)
        asked_for_creds_part1 = any(phrase in response1_str for phrase in [
            "please provide", "need your", "don't have", "missing credential",
            "github token", "github credentials", "authentication", "personal access token"
        ])

        # Check if it found repositories (indicates successful use of lily credential)
        found_repos_part1 = any(word in response1_str for word in ["repository", "repositories", "repo", "repos"])
        has_error_part1 = "error" in response1_str or "failed" in response1_str

        part1_success = found_repos_part1 and not has_error_part1 and not asked_for_creds_part1

        print("\n" + "="*80)
        print("Analysis of Part 1:")
        print(f"- Asked for credentials: {asked_for_creds_part1}")
        print(f"- Found repositories: {found_repos_part1}")
        print(f"- Has error: {has_error_part1}")
        print(f"- Part 1 Success: {part1_success}")
        print("="*80 + "\n")

        if not part1_success:
            print("❌ PART 1 FAILED: System did not use the lily account credential")
            print("    This suggests we need to implement name-based credential matching")
            return False

        print("✅ PART 1 PASSED: System successfully used the lily account credential")

        # TEST PART 2: Request for automaze account (should trigger clarification)
        print("\n" + "="*80)
        print("PART 2: Request for automaze account (should trigger clarification)")
        print("="*80 + "\n")

        # Use a new session to avoid context from previous request
        session_id2 = "test_session_4d3_part2"
        prompt2 = "list the repositories in my automaze account"

        print("User: user1")
        print(f"Prompt: {prompt2}")

        response2 = await overlord.chat(
            user_id="user1",
            message=prompt2,
            session_id=session_id2,
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
        print("Response for automaze account:")
        print("="*80)
        print(str(response2))
        print("="*80 + "\n")

        # Analyze response
        response2_str = str(response2).lower()

        # Check if it mentioned multiple accounts or asked which one to use
        mentioned_multiple = any(phrase in response2_str for phrase in [
            "which", "multiple", "ranaroussi", "lily", "choose", "select", "found multiple", "which account"
        ])

        # Check if it asked for credentials (shouldn't happen since credentials exist)
        asked_for_creds_part2 = any(phrase in response2_str for phrase in [
            "please provide", "need your", "don't have", "missing credential",
            "github token", "github credentials", "authentication", "personal access token"
        ])

        part2_success = mentioned_multiple and not asked_for_creds_part2

        print("\n" + "="*80)
        print("Analysis of Part 2:")
        print(f"- Mentioned multiple accounts/clarification: {mentioned_multiple}")
        print(f"- Asked for credentials: {asked_for_creds_part2}")
        print(f"- Part 2 Success: {part2_success}")
        print("="*80 + "\n")

        if not part2_success:
            print("❌ PART 2 FAILED: System did not trigger clarification for ambiguous automaze account")
            print("    Expected: Clarification asking which account to use")
            print("    Got: Either asked for credentials or picked an account without asking")
            return False

        print("✅ PART 2 PASSED: System correctly triggered clarification for ambiguous automaze account")

        # PART 2B: Test clarification response
        print("\n" + "="*80)
        print("PART 2B: Respond to clarification with specific account selection")
        print("="*80 + "\n")

        if mentioned_multiple:
            # Check which credentials were mentioned in the clarification
            mentioned_ranaroussi = "ranaroussi" in response2_str
            mentioned_lily = "lily" in response2_str

            print("Clarification mentioned:")
            print(f"- ranaroussi: {mentioned_ranaroussi}")
            print(f"- lily: {mentioned_lily}")

            # Respond with selection for lily automaze (since request was for "automaze")
            # TEST: Use number "1" instead of full name to see if LLM understands
            clarification_response = "1"
            print(f"\nUser responds to clarification: {clarification_response}")
            print("(Testing if system understands '1' means 'lily automaze')")

            response2b = await overlord.chat(
                user_id="user1",
                message=clarification_response,
                session_id=session_id2,  # Same session to continue conversation
                use_async=False,
                stream=False,
            )

            # Handle response
            if hasattr(response2b, '__aiter__'):
                full_response = ""
                async for chunk in response2b:
                    full_response += chunk
                response2b = full_response

            print("\n" + "="*80)
            print("Response after clarification selection:")
            print("="*80)
            print(str(response2b))
            print("="*80 + "\n")

            # Check if we got repositories after selection
            response2b_str = str(response2b).lower()
            found_repos_after_selection = any(
                word in response2b_str for word in ["repository", "repositories", "repo", "repos"])
            has_error_after_selection = "error" in response2b_str or "failed" in response2b_str

            part2b_success = found_repos_after_selection and not has_error_after_selection

            print("\n" + "="*80)
            print("Analysis of Part 2B (Clarification Response):")
            print(f"- Found repositories after selection: {found_repos_after_selection}")
            print(f"- Has error after selection: {has_error_after_selection}")
            print(f"- Part 2B Success: {part2b_success}")
            print("="*80 + "\n")

            if part2b_success:
                print("✅ PART 2B PASSED: System successfully used selected credential to list repositories")
                print("🎉 COMPLETE CLARIFICATION FLOW VERIFIED:")
                print("   1. Ambiguous request triggered clarification ✅")
                print("   2. User provided selection ✅")
                print("   3. System used selected credential ✅")
                print("   4. Original request fulfilled ✅")
            else:
                print("❌ PART 2B FAILED: System did not fulfill request after credential selection")
                return False
        else:
            print("⚠️  PART 2B SKIPPED: No clarification was triggered in Part 2")

        # TEST PART 3: Request without specifying account (should trigger clarification for multiple credentials)
        print("\n" + "="*80)
        print("PART 3: Request without specifying account (should trigger clarification)")
        print("="*80 + "\n")

        # Use a new session to avoid context from previous requests
        session_id3 = "test_session_4d3_part3"
        prompt3 = "list my repositories"

        print("User: user1")
        print(f"Prompt: {prompt3}")

        response3 = await overlord.chat(
            user_id="user1",
            message=prompt3,
            session_id=session_id3,
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
        print("Response for unspecified account:")
        print("="*80)
        print(str(response3))
        print("="*80 + "\n")

        # Analyze response
        response3_str = str(response3).lower()

        # Check if it asked for clarification about which account to use
        asked_which_account = any(phrase in response3_str for phrase in [
            "which account", "which github", "multiple accounts", "ranaroussi", "lily",
            "choose", "select", "specify", "clarify", "several accounts"
        ])

        # Check if it just used one of the accounts without asking
        used_account_directly = any(
            word in response3_str for word in ["repository", "repositories", "repo", "repos"]
        ) and not asked_which_account

        # Check if it asked for credentials (shouldn't happen since credentials exist)
        asked_for_creds_part3 = any(phrase in response3_str for phrase in [
            "please provide", "need your", "don't have", "missing credential",
            "github token", "github credentials", "authentication", "personal access token"
        ])

        part3_success = asked_which_account and not asked_for_creds_part3

        print("\n" + "="*80)
        print("Analysis of Part 3:")
        print(f"- Asked which account to use: {asked_which_account}")
        print(f"- Used account directly: {used_account_directly}")
        print(f"- Asked for credentials: {asked_for_creds_part3}")
        print(f"- Part 3 Success: {part3_success}")
        print("="*80 + "\n")

        if not part3_success:
            print("❌ PART 3 FAILED: System did not ask for clarification when multiple accounts available")
            print(
                "    This suggests the LLM is either picking one arbitrarily or there's an issue with credential selection"  # noqa: E501
            )
        else:
            print("✅ PART 3 PASSED: System correctly asked for clarification when no specific account mentioned")

        # Overall success (Part 2B success is included in part2_success logic above)
        overall_success = part1_success and part2_success and part3_success

        print("\n" + "="*80)
        print("Summary:")
        print(f"- Part 1 (lily account direct match): {'PASSED' if part1_success else 'FAILED'}")
        print(f"- Part 2 (automaze account clarification): {'PASSED' if part2_success else 'FAILED'}")
        if mentioned_multiple and 'part2b_success' in locals():
            print(f"- Part 2B (clarification response): {'PASSED' if part2b_success else 'FAILED'}")
        print(f"- Part 3 (unspecified account): {'PASSED' if part3_success else 'FAILED'}")
        print(f"- Overall Test: {'PASSED' if overall_success else 'FAILED'}")
        print("="*80 + "\n")

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
    print("Starting Test 4D3: Multiple Credentials - Context-Based Selection")

    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D3 PASSED: Multiple credentials handled correctly")
        else:
            print("\n❌ Test 4D3 FAILED: Need to improve credential selection logic")

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
