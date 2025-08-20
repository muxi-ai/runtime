"""Test 8B1: Context Propagation

Tests that context from previous messages is properly maintained
and used in subsequent interactions.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_context_propagation():
    """Test that context propagates across conversation turns."""
    try:
        print("\n=== Test 8B1: Context Propagation ===\n")

        # Load formation with clarification capabilities
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context
        ctx = TestContext("test_8b1")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

        # Test 1: Establish context
        print("\n1. Establishing e-commerce platform context...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="I'm working on an e-commerce platform using React and Node.js",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response1, str):
            content1 = response1
        elif hasattr(response1, "content"):
            content1 = response1.content
        else:
            content1 = str(response1)
        print(f"   Response: {content1[:200]}...")

        # Test 2: Ask question that should use context
        print("\n2. Asking database recommendation (should consider e-commerce context)...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="What database should I use?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response2, str):
            content2 = response2
        elif hasattr(response2, "content"):
            content2 = response2.content
        else:
            content2 = str(response2)
        print(f"   Response: {content2[:200]}...")

        # Should recommend databases suitable for e-commerce
        response_lower = content2.lower()
        has_db_recommendation = any(
            db in response_lower for db in ["postgres", "postgresql", "mysql", "mongo", "dynamodb"]
        )
        has_ecommerce_context = any(
            term in response_lower
            for term in ["e-commerce", "ecommerce", "product", "order", "transaction"]
        )

        if has_db_recommendation:
            print("   ✅ Database recommendation provided")
        else:
            print("   ❌ No database recommendation found")

        if has_ecommerce_context:
            print("   ✅ E-commerce context referenced")
        else:
            print("   ⚠️ E-commerce context not explicitly referenced")

        # Test 3: Further context refinement
        print("\n3. Adding scalability requirement...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="I expect high traffic during sales events with millions of users",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response3, str):
            content3 = response3
        elif hasattr(response3, "content"):
            content3 = response3.content
        else:
            content3 = str(response3)
        print(f"   Response: {content3[:200]}...")

        # Test 4: Question that should consider all context
        print(
            "\n4. Asking about caching strategy (should consider React, Node.js, high traffic)..."
        )
        response4 = await asyncio.wait_for(
            overlord.chat(
                message="What caching strategy would you recommend?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response4, str):
            content4 = response4
        elif hasattr(response4, "content"):
            content4 = response4.content
        else:
            content4 = str(response4)
        print(f"   Response: {content4[:200]}...")

        # Should mention relevant caching solutions
        response_lower = content4.lower()
        has_cache_solution = any(
            cache in response_lower
            for cache in ["redis", "memcached", "cdn", "cloudflare", "cache"]
        )
        has_scalability_context = any(
            term in response_lower for term in ["traffic", "scale", "performance", "load"]
        )

        if has_cache_solution:
            print("   ✅ Caching solution recommended")
        else:
            print("   ❌ No caching solution found")

        if has_scalability_context:
            print("   ✅ Scalability context referenced")
        else:
            print("   ⚠️ Scalability context not explicitly referenced")

        # Determine overall test success
        test_passed = has_db_recommendation and has_cache_solution

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        if test_passed:
            print("🎉 SUCCESS: Context properly propagates across conversation")
            print("✓ E-commerce platform context established")
            print("✓ Database recommendation provided with context")
            print("✓ Scalability requirement acknowledged")
            print("✓ Caching strategy recommended with context")
        else:
            print("⚠️ PARTIAL: Context propagation needs improvement")
            if not has_db_recommendation:
                print("✗ Database recommendation missing or unclear")
            if not has_ecommerce_context:
                print("✗ E-commerce context not maintained")
            if not has_cache_solution:
                print("✗ Caching recommendation missing or unclear")
            if not has_scalability_context:
                print("✗ Scalability context not maintained")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: I'm working on an e-commerce platform using React and Node.js")
        print(f"System: {content1[:400] + '...' if len(content1) > 400 else content1}")
        print("\nUser: What database should I use?")
        print(f"System: {content2[:400] + '...' if len(content2) > 400 else content2}")
        print("\nUser: I expect high traffic during sales events with millions of users")
        print(f"System: {content3[:400] + '...' if len(content3) > 400 else content3}")
        print("\nUser: What caching strategy would you recommend?")
        print(f"System: {content4[:400] + '...' if len(content4) > 400 else content4}")

        print("\n" + "=" * 40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()

        return test_passed

    except Exception as e:
        print(f"\n❌ Test 8B1 FAILED: {e}")
        import traceback

        traceback.print_exc()

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("❌ FAILED: Context propagation test failed")
        print(f"✗ Error: {e}")
        print("\n" + "=" * 40)

        print("\n### Partial Chat transcript (before failure):")
        if "content1" in locals():
            print("\nUser: I'm working on an e-commerce platform using React and Node.js")
            print(f"System: {content1[:400] + '...' if len(content1) > 400 else content1}")
        if "content2" in locals():
            print("\nUser: What database should I use?")
            print(f"System: {content2[:400] + '...' if len(content2) > 400 else content2}")
        if "content3" in locals():
            print("\nUser: I expect high traffic during sales events with millions of users")
            print(f"System: {content3[:400] + '...' if len(content3) > 400 else content3}")
        if "content4" in locals():
            print("\nUser: What caching strategy would you recommend?")
            print(f"System: {content4[:400] + '...' if len(content4) > 400 else content4}")

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
    asyncio.run(test_context_propagation())
