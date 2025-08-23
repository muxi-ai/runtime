#!/usr/bin/env python3
"""
Area 8 - Test Group 8D: Clarification Stack Management
Test 8D1: Stack Depth Handling

Tests handling of deep clarification stacks (3+ levels).
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_8d1_three_level_clarification():
    """Test 3-level deep clarification stack."""
    print("\n=== Test 8D1: Three-Level Deep Clarification Stack ===")

    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    # Create unique test context
    ctx = TestContext("test_8d1")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

    try:
        # Level 1: Initial ambiguous request
        print("\n1. Initial request (Level 0)...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Process the data",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response1.content}")

        # Should ask what data
        assert any(word in response1.content.lower() for word in ["what", "which", "data", "type", "kind"]), \
            "Should ask for clarification about data type"

        # Level 2: Provide partial info
        print("\n2. First clarification (Level 1)...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "The sales data",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response2.content}")

        # Should ask for more specifics about sales data
        response_lower = response2.content.lower()
        assert any(word in response_lower for word in ["format", "period", "source", "location", "which", "what"]), \
            "Should ask for more details about sales data"

        # Level 3: Still ambiguous
        print("\n3. Second clarification (Level 2)...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "Q4 sales",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response3.content}")

        # Should ask about format or year
        response_lower = response3.content.lower()
        assert any(word in response_lower for word in [
            "format", "year", "2024", "2025", "csv", "excel", "process", "analyze"]), \
            "Should ask about format, year, or processing type"

        # Level 4: Final clarification
        print("\n4. Third clarification (Level 3)...")
        response4 = await asyncio.wait_for(
            overlord.chat(
                "2024 CSV files for analysis",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response4.content}")

        # Should now have enough context to provide guidance
        response_lower = response4.content.lower()
        assert any(term in response_lower for term in ["csv", "q4", "2024", "sales", "analysis", "data"]), \
            "Should provide guidance with all collected context"

        # Verify context preservation
        print("\n5. Verify full context is preserved...")
        response5 = await asyncio.wait_for(
            overlord.chat(
                "What am I trying to process?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response5.content}")

        # Should remember all the details
        response_lower = response5.content.lower()
        context_preserved = (
            ("q4" in response_lower or "fourth quarter" in response_lower) and
            ("2024" in response_lower) and
            ("csv" in response_lower) and
            ("sales" in response_lower)
        )

        assert context_preserved, "Should remember all clarification details"

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: 3-level deep clarification stack handled correctly")
        print("✓ Level 1: Clarified data type (sales data)")
        print("✓ Level 2: Clarified time period (Q4)")
        print("✓ Level 3: Clarified year and format (2024 CSV)")
        print("✓ Full context preserved through all levels")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Process the data")
        print(f"System: {response1.content[:300] + '...' if len(response1.content) > 300 else response1.content}")
        print("\nUser: The sales data")
        print(f"System: {response2.content[:300] + '...' if len(response2.content) > 300 else response2.content}")
        print("\nUser: Q4 sales")
        print(f"System: {response3.content[:300] + '...' if len(response3.content) > 300 else response3.content}")
        print("\nUser: 2024 CSV files for analysis")
        print(f"System: {response4.content[:300] + '...' if len(response4.content) > 300 else response4.content}")
        print("\nUser: What am I trying to process?")
        print(f"System: {response5.content[:300] + '...' if len(response5.content) > 300 else response5.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8D1 FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_8d1_depth_limit_enforcement():
    """Test that clarification depth limits are enforced."""
    print("\n=== Test 8D1b: Clarification Depth Limit Enforcement ===")

    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    # Create unique test context
    ctx = TestContext("test_8d1b")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

    try:
        # Start with very ambiguous request
        print("\n1. Starting very ambiguous request...")
        response = await asyncio.wait_for(
            overlord.chat(
                "Do the thing",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )

        # Keep giving ambiguous responses to test depth limit
        depth_count = 1
        max_attempts = 10  # Try up to 10 levels

        for i in range(max_attempts):
            print(f"\n{i+2}. Ambiguous response level {i+1}...")

            # Give increasingly vague responses
            vague_responses = [
                "The usual thing",
                "What we discussed",
                "The standard process",
                "The regular task",
                "The normal procedure",
                "The typical operation",
                "The common workflow",
                "The routine activity",
                "The everyday task",
                "The ordinary process"
            ]

            response = await asyncio.wait_for(
                overlord.chat(
                    vague_responses[i % len(vague_responses)],
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    stream=False
                ),
                timeout=120.0
            )
            print(f"Response: {response.content[:200]}...")

            # Check if system stopped asking for clarification
            response_lower = response.content.lower()
            is_clarifying = any(word in response_lower for word in [
                "what", "which", "clarify", "specify", "elaborate",
                "more information", "details", "could you", "can you"
            ])

            if is_clarifying:
                depth_count += 1
            else:
                # System stopped clarifying - either hit limit or made assumption
                print(f"\nSystem stopped clarifying at depth {depth_count}")
                break

        # Verify depth limit was enforced (typically 5-7 levels)
        assert depth_count <= 7, f"Clarification went too deep: {depth_count} levels"
        assert depth_count >= 2, f"Should have at least some clarification depth: {depth_count}"

        print("\n" + "="*40)
        print("\n### Test Result:")
        print(f"🎉 SUCCESS: Depth limit enforced at {depth_count} levels")
        print("✓ System asked for clarification multiple times")
        print("✓ Eventually stopped to prevent infinite loop")
        print("✓ Depth limit working as expected")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8D1b FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":
    async def run_tests():
        """Run all stack depth tests."""
        results = []

        # Run three-level clarification test
        result = await test_8d1_three_level_clarification()
        results.append(("8D1: Three-Level Stack", result))

        # Run depth limit test
        result = await test_8d1_depth_limit_enforcement()
        results.append(("8D1b: Depth Limit Enforcement", result))

        # Print summary
        print("\n" + "="*50)
        print("TEST SUMMARY")
        print("="*50)
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{test_name}: {status}")

        all_passed = all(result for _, result in results)
        if all_passed:
            print(f"\n🎉 All {len(results)} tests PASSED!")
        else:
            failed = sum(1 for _, result in results if not result)
            print(f"\n⚠️ {failed}/{len(results)} tests FAILED")

        return all_passed

    try:
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    finally:
        pass
