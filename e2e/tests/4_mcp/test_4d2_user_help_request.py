#!/usr/bin/env python3
"""Test 4D2 Variant: User asks for help getting a token"""

import asyncio
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the test for user asking for help with credentials."""

    print("\n" + "="*80)
    print("I am testing: User Credential Help Request")
    print("This test verifies the complete help flow when user doesn't know how to get a token:")
    print("1. User2 (no GitHub credentials) requests to list GitHub repositories")
    print("2. System detects missing credentials and asks for GitHub token")
    print("3. User responds: 'I don't know how to get a token'")
    print("4. System provides helpful instructions on how to obtain a GitHub token")
    print("5. User provides token after receiving help")
    print("6. System uses token to list repositories")
    print("="*80 + "\n")

    try:
        # Use the test formation
        formation_path = Path(str(Path(__file__).parent / "formations" / "formation-mcp"))

        # Load formation
        print("Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))

        # Start overlord first (this initializes all services)
        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Give MCP servers time to initialize
        print("\nWaiting for MCP servers to initialize...")
        await asyncio.sleep(3)

        # Clean up any existing credentials for user2 to ensure test starts fresh
        print("\n=== CLEANING UP EXISTING CREDENTIALS ===")
        if formation._db_manager:
            try:
                from sqlalchemy import text
                async with formation._db_manager.get_async_session() as session:
                    # Delete existing GitHub credentials for user_id=5 (user2)
                    delete_result = await session.execute(
                        text("""
                        DELETE FROM credentials
                        WHERE service = 'github'
                        AND user_id = 5
                        """)
                    )
                    await session.commit()
                    print(f"✅ Deleted {delete_result.rowcount} GitHub credential(s) for user_id=5")
            except Exception as e:
                print(f"Warning: Could not clear credentials: {e}")

        # Also clear the credential cache if it exists
        if overlord.credential_resolver:
            print("Clearing credential cache...")
            overlord.credential_resolver._cache.clear()
            print("✅ Cleared credential cache")

        # Initial request
        initial_prompt = "List my GitHub repositories. Do not include forks"

        print("\n" + "="*80)
        print("STEP 1: Initial request from user2 (no credentials)")
        print("Prompt:", initial_prompt)
        print("="*80 + "\n")

        # Create a session ID for this conversation
        session_id = "test_session_4d2_help"

        # Make the initial request
        response1 = await overlord.chat(
            user_id="user2",
            message=initial_prompt,
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
        print("Initial Response:")
        print(json.dumps({"response": str(response1)}, indent=2))
        print("="*80 + "\n")

        # Check if we got a clarification request
        response1_str = str(response1).lower()
        asked_for_credentials = any(phrase in response1_str for phrase in [
            "please provide", "need your", "don't have", "missing credential",
            "github token", "github credentials", "authentication", "personal access token",
            "i need", "provide me", "enter your", "what is your", "what's your",
            "cannot access", "provide the necessary"
        ])

        if not asked_for_credentials:
            print("❌ FAILED: System did not ask for credentials")
            return False

        print("✅ System correctly asked for credentials!")

        # STEP 2: User asks for help
        print("\n" + "="*80)
        print("STEP 2: User asks for help getting a token")
        help_request = "I don't know how to get a token. Can you help me?"
        print("User response:", help_request)
        print("="*80 + "\n")

        # Send the help request
        response2 = await overlord.chat(
            user_id="user2",
            message=help_request,
            session_id=session_id,  # Use same session ID
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
        print("Help Response:")
        print("="*80)
        print(str(response2))
        print("="*80 + "\n")

        # Analyze the help response
        response2_str = str(response2).lower()

        # Check if the response contains helpful instructions
        helpful_keywords = [
            "github.com", "settings", "developer settings", "personal access",
            "generate", "create", "token", "permission", "scope",
            "sign in", "profile", "configure", "expiration", "copy"
        ]

        keywords_found = [kw for kw in helpful_keywords if kw in response2_str]
        is_helpful = len(keywords_found) >= 3  # At least 3 helpful keywords

        # Check if it still asks for the token
        still_asks = any(phrase in response2_str for phrase in [
            "once you have", "after you", "when you get", "provide it",
            "paste it", "enter it", "share it"
        ])

        print("\n" + "="*80)
        print("Analysis of help response:")
        print(f"- Contains helpful instructions: {is_helpful}")
        print(f"- Keywords found: {keywords_found[:5]}...")  # Show first 5
        print(f"- Still expects token afterward: {still_asks}")
        print("="*80 + "\n")

        # Always proceed to Step 3 after getting help
        if is_helpful:
            print("\n" + "="*80)
            print("STEP 3: User provides token after getting help")
            token_response = "Thanks for the help! Here's my token: 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"
            print("User response:", token_response)
            print("="*80 + "\n")

            response3 = await overlord.chat(
                user_id="user2",
                message=token_response,
                session_id=session_id,  # Use same session ID
                use_async=False,
                stream=False,
            )

            if hasattr(response3, '__aiter__'):
                full_response = ""
                async for chunk in response3:
                    full_response += chunk
                response3 = full_response

            print("\n" + "="*80)
            print("Final Response:")
            print("="*80)
            print(str(response3))
            print("="*80 + "\n")

            # Check if repositories were listed
            response3_str = str(response3).lower()
            found_repos = any(word in response3_str for word in ["repository", "repositories", "repo", "repos"])
            has_error = "error" in response3_str or "failed" in response3_str

            # Extract and display repositories if found
            if found_repos and not has_error:
                print("\n" + "="*80)
                print("REPOSITORIES FOUND:")
                print("="*80)
                # Extract repository names from the response
                import re
                # Look for repository names in various formats
                repo_pattern = r'\*\*\[?([^\*\[\]]+)\]?\*\*|\- ([^\n]+)|\d+\. ([^\n]+)'
                matches = re.findall(repo_pattern, str(response3))
                repos = [match[0] or match[1] or match[2] for match in matches if any(match)]
                if repos:
                    for i, repo in enumerate(repos[:10], 1):  # Show first 10
                        print(f"{i}. {repo.strip()}")
                else:
                    # Fallback: show part of response
                    print(str(response3)[:300] + "..." if len(str(response3)) > 300 else str(response3))
                print("="*80 + "\n")

                print("✅ Token was accepted and repositories were listed!")
                summary = "SUCCESS: Complete flow worked - help provided, token accepted, repositories listed!"
            else:
                print("❌ Failed to list repositories after providing token")
                summary = "PARTIAL SUCCESS: Help was provided but token was not processed correctly"
        else:
            summary = "FAILED: System did not provide adequate help for obtaining a token"

        # Final success determination
        success = is_helpful and found_repos if is_helpful else False

        print("\n" + "="*80)
        print("Summary:")
        print(summary)
        print("\nFull Flow Results:")
        print("1. Asked for repositories: ✓")
        print(f"2. System requested credentials: {'✓' if asked_for_credentials else '✗'}")
        print("3. User asked for help: ✓")
        print(f"4. System provided instructions: {'✓' if is_helpful else '✗'}")
        if is_helpful:
            print("5. User provided token: ✓")
            print(f"6. System listed repositories: {'✓' if found_repos and not has_error else '✗'}")
        print("="*80 + "\n")

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
    print("Starting Test 4D2 Variant: User Credential Help Request")

    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D2 Help Request PASSED")
        else:
            print("\n❌ Test 4D2 Help Request FAILED")

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
