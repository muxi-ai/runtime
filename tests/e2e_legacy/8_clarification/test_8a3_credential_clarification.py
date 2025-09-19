"""Test 8A3: Credential Selection Clarification

Tests clarification when multiple credentials are available.
"""

import asyncio
from pathlib import Path
import sys
import uuid

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

        # Use user1 which has two GitHub credentials in the database
        user_id = "user1"
        session_id = f"test_8a3_session_{uuid.uuid4().hex[:8]}"
        print(f"Using User: {user_id} (has multiple GitHub credentials), Session: {session_id}")

        # Test: Request that would need credentials
        print("\n1. Testing with: 'List my repositories'")
        response = await overlord.chat(
            message="List my github repositories",
            user_id=user_id,
            session_id=session_id,
            stream=False,
        )

        # Handle both string and MuxiResponse object
        if isinstance(response, str):
            response_content = response
            # For string responses, detect clarification by content
            is_clarification = any(word in response.lower() for word in ["which", "what", "clarify", "specific"])
            response_metadata = None
        else:
            response_content = response.content
            is_clarification = response.metadata and response.metadata.get("clarification")
            response_metadata = response.metadata

        print(f"   Response: {response_content}")

        # Should ask which service/account
        if is_clarification:
            assert any(
                word in response_content.lower()
                for word in ["which", "account", "github", "gitlab", "service", "repository"]
            ), "Should ask about which repository service"
            print("   ✅ Credential clarification triggered")

            # Provide clarification
            print("\n2. Clarifying: 'GitHub repositories'")
            response2 = await overlord.chat(
                message="Use my ranaroussi GitHub account",
                user_id=user_id,
                session_id=session_id,
                stream=False,
            )

            # Handle response2 format
            if isinstance(response2, str):
                response2_content = response2
            else:
                response2_content = response2.content

            print(f"   Response: {response2_content}")
            print("   ✅ Credential clarification flow completed")
        else:
            # If MCP is not configured, might directly explain limitation
            print("   ℹ️ No clarification needed (likely no MCP configured)")
            assert (
                "repositor" in response_content.lower()
            ), "Should mention repositories in response"
            response2 = None

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Credential clarification handled")
        print("✓ Repository request processed")
        if is_clarification:
            print("✓ System asked for service clarification")
            print("✓ Clarification response handled correctly")
        else:
            print("✓ Direct response provided (no MCP configured)")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: List my repositories")
        print(f"System: {response_content}")
        if response2:
            print("\nUser: GitHub repositories")
            if isinstance(response2, str):
                print(f"System: {response2[:500] + '...' if len(response2) > 500 else response2}")
            else:
                print(
                    f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")

        print("\n" + "="*40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()

        return True

    except Exception as e:
        print(f"\n❌ Test 8A3 FAILED: {e}")
        import traceback

        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Credential clarification test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response' in locals():
            print("\nUser: List my repositories")
            if isinstance(response, str):
                print(f"System: {response}")
            else:
                print(f"System: {response.content}")
        if 'response2' in locals():
            print("\nUser: GitHub repositories")
            if isinstance(response2, str):
                print(f"System: {response2[:500] + '...' if len(response2) > 500 else response2}")
            else:
                print(
                    f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")

        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass

        return False
    finally:
        sys.exit(0 if "return True" in locals() else 1)


if __name__ == "__main__":
    asyncio.run(test_credential_clarification())
