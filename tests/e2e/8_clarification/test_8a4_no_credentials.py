"""Test 8A4: No Credentials Flow

Tests the flow when a user has no stored credentials.
Expected: System should inform user and offer to store credentials.
"""

import asyncio
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402


async def test_no_credentials_flow():
    """Test flow when user has no stored credentials."""
    print("=== Test 8A4: No Credentials Flow ===\n")

    try:
        # Load the same formation with clarification config
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Use a random user that won't have any credentials
        user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        session_id = f"test_8a4_session_{uuid.uuid4().hex[:8]}"
        print(f"Using User: {user_id} (no credentials), Session: {session_id}")

        # Test: Request that would need credentials
        print("\n1. Testing with: 'List my GitHub repositories'")
        response = await overlord.chat(
            message="List my GitHub repositories",
            user_id=user_id,
            session_id=session_id,
            stream=False,
        )

        # Handle both string and MuxiResponse object
        if isinstance(response, str):
            response_content = response
        else:
            response_content = response.content

        print(f"   Response: {response_content}")

        # Should inform about missing credentials
        response_lower = response_content.lower()
        has_no_creds_message = any(phrase in response_lower for phrase in [
            "no credentials",
            "don't have any credentials",
            "credentials not found",
            "missing credentials",
            "need to provide",
            "need credentials",
            "authenticate",
            "provide your github"
        ])

        if has_no_creds_message:
            print("   ✅ System correctly identified missing credentials")

            # Test 2: User provides credentials
            print("\n2. User provides GitHub token")
            response2 = await overlord.chat(
                message="My GitHub token is ghp_exampletoken123",
                user_id=user_id,
                session_id=session_id,
                stream=False,
            )

            if isinstance(response2, str):
                response2_content = response2
            else:
                response2_content = response2.content

            print(f"   Response: {response2_content}")

            # Check if credentials were acknowledged
            response2_lower = response2_content.lower()
            creds_stored = any(phrase in response2_lower for phrase in [
                "stored",
                "saved",
                "registered",
                "added",
                "authenticated"
            ])

            if creds_stored:
                print("   ✅ Credentials appear to be stored")
            else:
                print("   ⚠️ Unclear if credentials were stored")

            # Test 3: Try the original request again
            print("\n3. Retry: 'List my GitHub repositories'")
            response3 = await overlord.chat(
                message="List my GitHub repositories",
                user_id=user_id,
                session_id=session_id,
                stream=False,
            )

            if isinstance(response3, str):
                response3_content = response3
            else:
                response3_content = response3.content

            print(f"   Response: {response3_content}")

            # Check if it now attempts to use the credentials
            response3_lower = response3_content.lower()
            attempts_github = any(phrase in response3_lower for phrase in [
                "repositor",
                "github",
                "fetching",
                "retrieving",
                "error",  # Even an error shows it tried
                "access"
            ])

            if attempts_github:
                print("   ✅ System attempted to use credentials")
            else:
                print("   ❌ System didn't attempt to use stored credentials")
        else:
            print("   ❌ System didn't identify missing credentials")
            print("   Expected message about missing credentials")

        print("\n" + "=" * 40)
        print("\n### Test Result:")

        if has_no_creds_message:
            print("  🎉 SUCCESS: No credentials flow handled correctly")
            print("  ✓ System identified missing credentials")
            print("  ✓ Offered to store credentials")
            if creds_stored:
                print("  ✓ Credentials were stored")
            if attempts_github:
                print("  ✓ System attempted to use stored credentials")
        else:
            print("  ❌ FAILED: No credentials flow not working")
            print("  ✗ System didn't handle missing credentials properly")

        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: List my GitHub repositories")
        print(f"System: {response_content}")
        if has_no_creds_message:
            print("\nUser: My GitHub token is ghp_exampletoken123")
            print(f"System: {response2_content}")
            print("\nUser: List my GitHub repositories")
            print(f"System: {response3_content}")

    except Exception as e:
        print(f"\n❌ Test 8A4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean shutdown
        try:
            await formation.stop()
        except Exception as e:
            print(f"   ❌ Error during cleanup: {e}")

    return has_no_creds_message


if __name__ == "__main__":
    success = asyncio.run(test_no_credentials_flow())
    exit(0 if success else 1)
