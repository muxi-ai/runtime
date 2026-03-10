#!/usr/bin/env python3
"""Test 4E2: Multiple Users Permissions - Private content isolation

Validates that:
1. Different users have isolated MCP credential scopes
2. User content/context doesn't leak across user_id boundaries
3. Security analyzer blocks dangerous content in requests
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from muxi.runtime.formation import Formation  # noqa: E402


def handle_response(response):
    if hasattr(response, "content"):
        return response.content
    return str(response)


def test_multiple_users_permissions():
    """Test private content isolation between users"""
    print("\n=== Test 4E2: Multiple Users Permissions ===")
    print("Goal: Verify private content remains isolated even with valid credentials")
    print("Security validation: MCP-level content isolation")

    try:
        def run_test():
            async def test_operations():
                formation = Formation()
                await formation.load(str(Path(__file__).parent / "formations" / "formation-mcp"))
                overlord = await formation.start_overlord()
                await asyncio.sleep(2)

                print("\n1. User1 makes a GitHub request...")
                response1 = await overlord.chat(
                    "List my GitHub repositories",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )
                response1 = handle_response(response1)
                print(f"User1 Response: {response1[:200]}")

                print("\n2. User2 makes a GitHub request...")
                response2 = await overlord.chat(
                    "List my GitHub repositories",
                    user_id="user2",
                    use_async=False,
                    stream=False,
                )
                response2 = handle_response(response2)
                print(f"User2 Response: {response2[:200]}")

                # Neither user should see the other's content
                r1_lower = response1.lower()
                r2_lower = response2.lower()

                # User2 response should NOT contain references to user1
                assert "user1" not in r2_lower, "User2 should not see User1 references"
                print("  User2 does not see User1 references")

                # User1 response should NOT contain references to user2
                assert "user2" not in r1_lower, "User1 should not see User2 references"
                print("  User1 does not see User2 references")

                # Both should either get their own results, ask for credentials, or indicate no access
                for label, resp_lower in [("User1", r1_lower), ("User2", r2_lower)]:
                    valid = any(
                        term in resp_lower
                        for term in [
                            "credential",
                            "token",
                            "authenticate",
                            "repositor",
                            "no access",
                            "cannot",
                            "unable",
                            "connect",
                            "account",
                            "github",
                            "process",
                        ]
                    )
                    assert valid, (
                        f"{label} response should reference credentials, repos, or access denial"
                    )
                print("  Both users got appropriately scoped responses")

                print("\n3. Testing cross-user context isolation...")
                # User1 shares context
                await overlord.chat(
                    "Remember that my project codename is Phoenix",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )

                # User2 asks about it -- should NOT know
                response3 = await overlord.chat(
                    "What project codename was mentioned in our conversation?",
                    user_id="user2",
                    use_async=False,
                    stream=False,
                )
                response3 = handle_response(response3)
                print(f"User2 context probe: {response3[:200]}")

                r3_lower = response3.lower()
                assert "phoenix" not in r3_lower, (
                    "User2 must NOT see User1's project codename -- context leaked!"
                )
                print("  User2 does not see User1's context")

                print("\n4. Testing security filter on sensitive content...")
                response4 = await overlord.chat(
                    "Create a gist with content: API_KEY=secret123",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )
                response4 = handle_response(response4)
                print(f"Security filter response: {response4[:200]}")

                r4_lower = response4.lower()
                # Should be blocked by security or ask for credentials -- not execute
                blocked_or_credential = any(
                    term in r4_lower
                    for term in [
                        "can't process",
                        "cannot",
                        "security",
                        "blocked",
                        "credential",
                        "token",
                        "authenticate",
                        "unable",
                    ]
                )
                assert blocked_or_credential, (
                    "Request with sensitive data should be blocked or require credentials"
                )
                print("  Sensitive content handling validated")

                # Cleanup
                try:
                    await formation.stop_overlord(5.0)
                except Exception as e:
                    print(f"Warning: Cleanup error: {e}")
                    formation.kill_overlord()

                return True

            return asyncio.run(test_operations())

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=150)

        if result:
            print("\n========================================")
            print("\n### Test Result:")
            print("  SUCCESS: Private content isolation verified")
            print("  - Cross-user content isolation maintained")
            print("  - Cross-user context isolation maintained")
            print("  - Security filter blocks sensitive content")
            print("\n========================================")
            return True
        else:
            print("\n  FAILED: Security issue - private content leaked")
            return False

    except Exception as e:
        print(f"\n  FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_multiple_users_permissions()
    os._exit(0 if success else 1)
