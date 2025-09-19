#!/usr/bin/env python3
"""Test 4D2 Full: User Credential Missing - Complete Clarification Flow"""

import asyncio
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the test for missing user credentials with full clarification flow."""

    print("\n" + "="*80)
    print("I am testing: User Credential Missing - Complete Clarification Flow")
    print("This test verifies the full credential clarification flow:")
    print("1. User2 (no GitHub credentials) requests to list GitHub repositories")
    print("2. System detects missing credentials and asks for GitHub token")
    print("3. User provides token: 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")
    print("4. System uses the token to complete the request")
    print("5. If successful: token is saved in DB for user2")
    print("6. If failed: clarification is re-triggered")
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
                async with formation._db_manager.get_session() as session:
                    # Delete existing GitHub credentials for user2 (more comprehensive)
                    delete_result = await session.execute(
                        text("""
                        DELETE FROM credentials
                        WHERE service = 'github'
                        AND user_id IN (
                            SELECT id FROM users WHERE external_user_id = 'user2'
                        )
                        """)
                    )
                    await session.commit()
                    print(f"✅ Deleted {delete_result.rowcount} GitHub credential(s) for user2")

                    # Also check if user2 exists
                    user_check = await session.execute(
                        text("SELECT id, external_user_id FROM users WHERE external_user_id = 'user2'")
                    )
                    user = user_check.fetchone()
                    if user:
                        print(f"✅ User2 exists with ID: {user.id}")
                    else:
                        print("⚠️  User2 does not exist in database")

            except Exception as e:
                print(f"Warning: Could not clear credentials: {e}")
                import traceback
                traceback.print_exc()

        # Also clear the credential cache if it exists
        if overlord.credential_resolver:
            print("Clearing credential cache...")
            overlord.credential_resolver._cache.clear()
            print("✅ Cleared credential cache")

        # Check available tools
        print("\n=== CHECKING MCP TOOLS ===")
        mcp_service = overlord.mcp_service
        if mcp_service:
            tools = mcp_service.tool_registry
            github_tools = [tool for tool in tools.keys() if 'github' in tool.lower()]
            print(f"GitHub MCP tools available: {len(github_tools)}")
            if github_tools:
                print("Sample tools:", github_tools[:3])

        # Initial request
        initial_prompt = "List my GitHub repositories. Do not include forks"

        print("\n" + "="*80)
        print("STEP 1: Initial request from user2 (no credentials)")
        print("Prompt:", initial_prompt)
        print("="*80 + "\n")

        # Create a session ID for this conversation
        session_id = "test_session_4d2"

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

        # STEP 2: Provide the GitHub token
        print("\n" + "="*80)
        print("STEP 2: User provides GitHub token")
        token_response = "Here is my GitHub token: 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 - please use it carefully!"
        print("User response:", token_response)
        print("="*80 + "\n")

        # Send the token as a response
        response2 = await overlord.chat(
            user_id="user2",
            message=token_response,
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
        print("Response after providing token:")
        print(json.dumps({"response": str(response2)}, indent=2))
        print("="*80 + "\n")

        # Analyze the response
        response2_str = str(response2).lower()

        # Check for different outcomes
        found_repos = any(word in response2_str for word in ["repository", "repositories", "repo", "repos"])
        has_error = "error" in response2_str or "failed" in response2_str
        invalid_token = any(phrase in response2_str for phrase in ["invalid", "expired", "unauthorized", "401"])
        asks_again = any(phrase in response2_str for phrase in [
            "please provide", "need your", "github token", "try again"
        ])

        # If we found repositories, extract and print them
        if found_repos and not has_error:
            print("\n" + "="*80)
            print("REPOSITORIES FOUND:")
            print("="*80)
            # Extract repository names from the response
            import re
            # Look for repository names in the format [repo_name](url) or **repo_name**
            repo_pattern = r'\*\*\[?([^\*\[\]]+)\]?\*\*'
            repos = re.findall(repo_pattern, str(response2))
            if repos:
                for i, repo in enumerate(repos, 1):
                    print(f"{i}. {repo}")
            else:
                # Fallback: just print the relevant part of the response
                print(str(response2)[:500] + "..." if len(str(response2)) > 500 else str(response2))
            print("="*80 + "\n")

        print("\n" + "="*80)
        print("Analysis of token response:")
        print(f"- Found repositories: {found_repos}")
        print(f"- Has error: {has_error}")
        print(f"- Invalid token message: {invalid_token}")
        print(f"- Asks for credentials again: {asks_again}")
        print("="*80 + "\n")

        # Wait for async credential name update to complete
        print("\n=== WAITING FOR ASYNC CREDENTIAL NAME UPDATE ===")
        print("Waiting 25 seconds for async credential name discovery to complete...")
        await asyncio.sleep(25)
        print("✅ Wait complete - checking database for updated credential name")

        # Check if credentials were saved in DB
        if formation._db_manager:
            print("\n=== CHECKING DATABASE ===")
            try:
                # Check if credential was saved and if name was updated
                from sqlalchemy import text
                async with formation._db_manager.get_session() as session:
                    result = await session.execute(
                        text("""
                        SELECT c.service, c.name, c.encrypted_data IS NOT NULL as has_data
                        FROM credentials c
                        JOIN users u ON c.user_id = u.id
                        WHERE u.external_user_id = :user_id
                        AND c.service = 'github'
                        """),
                        {"user_id": "user2"}
                    )
                    cred = result.fetchone()

                    if cred:
                        print("✅ Credential found in DB for user2/github")
                        print(f"   Service: {cred.service}")
                        print(f"   Name: {cred.name}")
                        print(f"   Has data: {cred.has_data}")
                        if cred.name != "github":
                            print(f"🎉 SUCCESS: Credential name was updated from 'github' to '{cred.name}'!")
                        else:
                            print("⚠️  Credential name is still 'github' - async update may not have completed")
                    else:
                        print("❌ No credential found in DB for user2/github")
            except Exception as e:
                print(f"Error checking DB: {e}")

        # Determine success
        success = False
        summary = ""

        if found_repos and not has_error:
            success = True
            summary = "SUCCESS: Token was accepted and repositories were listed!"
        elif invalid_token and asks_again:
            success = True
            summary = "SUCCESS: Invalid token was detected and clarification re-triggered!"
        elif has_error and not asks_again:
            success = False
            summary = "FAILED: Error occurred but clarification was not re-triggered"
        else:
            success = False
            summary = "FAILED: Unexpected response after providing token"

        print("\n" + "="*80)
        print("Summary:")
        print(summary)
        print("="*80 + "\n")

        # Optional: Test with another request to verify saved credentials
        if found_repos and not has_error:
            print("\n" + "="*80)
            print("STEP 3: Testing if credentials were saved (making another request)")
            print("="*80 + "\n")

            response3 = await overlord.chat(
                user_id="user2",
                message="Show me my GitHub profile information",
                session_id=session_id,  # Use same session ID
                use_async=False,
                stream=False,
            )

            if hasattr(response3, '__aiter__'):
                full_response = ""
                async for chunk in response3:
                    full_response += chunk
                response3 = full_response

            response3_str = str(response3).lower()
            if "error" not in response3_str and "credential" not in response3_str:
                print("✅ Subsequent request worked without asking for credentials!")
            else:
                print("❌ Subsequent request still has credential issues")

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
    print("Starting Test 4D2 Full: User Credential Missing - Complete Clarification Flow")

    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D2 Full PASSED")
        else:
            print("\n❌ Test 4D2 Full FAILED")

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
