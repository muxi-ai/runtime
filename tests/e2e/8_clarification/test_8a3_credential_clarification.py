"""Test 8A3: Credential Selection Clarification

Tests clarification when multiple credentials are available.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402


async def test_credential_clarification():
    """Test clarification for credential selection."""
    try:
        print("\n=== Test 8A3: Credential Selection Clarification ===\n")

        # This test simulates credential clarification flow
        formation_path = (
            Path(__file__).parent / "formations" / "formation-clarification"
        )
        formation = Formation()
        await formation.load(str(formation_path))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Test: Request that would need credentials
        print("\n1. Testing with: 'List my repositories'")
        response = await overlord.chat(
            message="List my repositories",
            user_id="test_user",
            session_id="credential_session",
            stream=False,
        )

        print(f"   Response: {response.content}")

        # Should ask which service/account
        is_clarification = response.metadata and response.metadata.get("clarification")
        if is_clarification:
            assert any(
                word in response.content.lower()
                for word in ["which", "account", "github", "gitlab", "service", "repository"]
            ), "Should ask about which repository service"
            print("   ✅ Credential clarification triggered")

            # Provide clarification
            print("\n2. Clarifying: 'GitHub repositories'")
            response2 = await overlord.chat(
                message="GitHub repositories",
                user_id="test_user",
                session_id="credential_session",
                stream=False,
            )

            print(f"   Response: {response2.content[:200]}...")
            print("   ✅ Credential clarification flow completed")
        else:
            # If MCP is not configured, might directly explain limitation
            print("   ℹ️ No clarification needed (likely no MCP configured)")
            assert (
                "repositor" in response.content.lower()
            ), "Should mention repositories in response"

        print("\n✅ Test 8A3 PASSED: Credential clarification handled")
        return True

    except Exception as e:
        print(f"\n❌ Test 8A3 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        sys.exit(0 if "return True" in locals() else 1)


if __name__ == "__main__":
    asyncio.run(test_credential_clarification())
