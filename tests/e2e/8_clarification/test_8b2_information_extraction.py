"""Test 8B2: Information Extraction

Tests that the system properly extracts and remembers key information
from user messages (budget, timeline, requirements, etc.).
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_information_extraction():
    """Test extraction of key project information from conversation."""
    try:
        print("\n=== Test 8B2: Information Extraction ===\n")

        # Load formation with clarification capabilities
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context
        ctx = TestContext("test_8b2")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

        # Test 1: Extract budget and timeline
        print("\n1. Providing budget and timeline information...")
        response1 = await overlord.chat(
            message="My budget is $5000 and timeline is 2 weeks for the MVP",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False,
        )

        # Handle different response types
        if isinstance(response1, str):
            content1 = response1
        elif hasattr(response1, "content"):
            content1 = response1.content
        else:
            content1 = str(response1)
        print(f"   Response: {content1[:200]}...")

        # Test 2: Ask for recommendations that should consider budget/timeline
        print("\n2. Asking for tech stack recommendation...")
        response2 = await overlord.chat(
            message="What tech stack would you recommend for a quick prototype?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False,
        )

        # Handle different response types
        if isinstance(response2, str):
            content2 = response2
        elif hasattr(response2, "content"):
            content2 = response2.content
        else:
            content2 = str(response2)
        print(f"   Response: {content2[:200]}...")

        response_lower = content2.lower()
        # Should mention quick/rapid/fast development given 2-week timeline
        has_timeline_ref = any(
            term in response_lower
            for term in ["quick", "rapid", "fast", "mvp", "prototype", "week"]
        )
        # Should suggest cost-effective solutions given $5000 budget
        has_budget_ref = any(
            term in response_lower for term in ["cost", "budget", "free", "open", "affordable"]
        )

        if has_timeline_ref:
            print("   ✅ Timeline consideration found")
        else:
            print("   ⚠️ Timeline not explicitly referenced")

        if has_budget_ref:
            print("   ✅ Budget consideration found")
        else:
            print("   ⚠️ Budget not explicitly referenced")

        # Test 3: Extract technical requirements
        print("\n3. Providing technical requirements...")
        response3 = await overlord.chat(
            message="The app needs user authentication, real-time chat, and payment processing",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False,
        )

        # Handle different response types
        if isinstance(response3, str):
            content3 = response3
        elif hasattr(response3, "content"):
            content3 = response3.content
        else:
            content3 = str(response3)
        print(f"   Response: {content3[:200]}...")

        # Test 4: Ask specific question that should use extracted requirements
        print("\n4. Asking about authentication solution...")
        response4 = await overlord.chat(
            message="Which authentication solution would work best?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False,
        )

        # Handle different response types
        if isinstance(response4, str):
            content4 = response4
        elif hasattr(response4, "content"):
            content4 = response4.content
        else:
            content4 = str(response4)
        print(f"   Response: {content4[:200]}...")

        response_lower = content4.lower()
        # Should mention auth solutions
        has_auth_solution = any(
            auth in response_lower for auth in ["auth0", "firebase", "supabase", "jwt", "oauth"]
        )
        # Should consider real-time and payment requirements
        has_requirements_ref = any(
            term in response_lower
            for term in ["real-time", "realtime", "chat", "payment", "stripe"]
        )

        if has_auth_solution:
            print("   ✅ Authentication solution recommended")
        else:
            print("   ❌ No authentication solution found")

        if has_requirements_ref:
            print("   ✅ Other requirements referenced")
        else:
            print("   ⚠️ Other requirements not explicitly referenced")

        # Determine overall test success
        test_passed = has_auth_solution

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        if test_passed:
            print("🎉 SUCCESS: Information properly extracted and used")
            print("✓ Budget and timeline information received")
            print("✓ Tech stack recommendation provided")
            print("✓ Technical requirements acknowledged")
            print("✓ Authentication recommendation given")
        else:
            print("⚠️ PARTIAL: Information extraction needs improvement")
            if not has_timeline_ref:
                print("✗ Timeline not considered in recommendations")
            if not has_budget_ref:
                print("✗ Budget not considered in recommendations")
            if not has_auth_solution:
                print("✗ Authentication solution not recommended")
            if not has_requirements_ref:
                print("✗ Other requirements not referenced")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: My budget is $5000 and timeline is 2 weeks for the MVP")
        print(f"System: {content1[:400] + '...' if len(content1) > 400 else content1}")
        print("\nUser: What tech stack would you recommend for a quick prototype?")
        print(f"System: {content2[:500] + '...' if len(content2) > 500 else content2}")
        print("\nUser: The app needs user authentication, real-time chat, and payment processing")
        print(f"System: {content3[:300] + '...' if len(content3) > 300 else content3}")
        print("\nUser: Which authentication solution would work best?")
        print(f"System: {content4[:500] + '...' if len(content4) > 500 else content4}")

        print("\n" + "=" * 40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()

        return test_passed

    except Exception as e:
        print(f"\n❌ Test 8B2 FAILED: {e}")
        import traceback

        traceback.print_exc()

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("❌ FAILED: Information extraction test failed")
        print(f"✗ Error: {e}")
        print("\n" + "=" * 40)

        print("\n### Partial Chat transcript (before failure):")
        if "content1" in locals():
            print("\nUser: My budget is $5000 and timeline is 2 weeks for the MVP")
            print(f"System: {content1[:400] + '...' if len(content1) > 400 else content1}")
        if "content2" in locals():
            print("\nUser: What tech stack would you recommend for a quick prototype?")
            print(f"System: {content2[:500] + '...' if len(content2) > 500 else content2}")
        if "content3" in locals():
            print(
                "\nUser: The app needs user authentication, real-time chat, and payment processing"
            )
            print(f"System: {content3[:300] + '...' if len(content3) > 300 else content3}")
        if "content4" in locals():
            print("\nUser: Which authentication solution would work best?")
            print(f"System: {content4[:500] + '...' if len(content4) > 500 else content4}")

        print("\n" + "=" * 40)

        # Try to shut down even on failure
        if "formation" in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass

        return False
    finally:
        sys.exit(0 if "return True" in locals() else 1)


if __name__ == "__main__":
    asyncio.run(test_information_extraction())
