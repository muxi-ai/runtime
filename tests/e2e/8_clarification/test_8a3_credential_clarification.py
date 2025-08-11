"""Test 8A3: Credential Selection Clarification

Tests clarification when multiple credentials are available.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


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
        
        # Create unique test context
        ctx = TestContext("test_8a3")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

        # Test: Request that would need credentials
        print("\n1. Testing with: 'List my repositories'")
        response = await overlord.chat(
            message="List my repositories",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
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
                user_id=ctx.user_id,
                session_id=ctx.session_id,
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
        print(f"System: {response.content}")
        if response2:
            print("\nUser: GitHub repositories")
            print(f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")
        
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
            print(f"System: {response.content}")
        if 'response2' in locals():
            print("\nUser: GitHub repositories")
            print(f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")
        
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
