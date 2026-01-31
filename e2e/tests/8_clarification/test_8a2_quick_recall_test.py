#!/usr/bin/env python3
"""
Quick Test: Does the improved memory usage protocol fix recall questions?

This test runs the recall scenario 5 times to check consistency.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_recall_consistency():
    """Test recall question 5 times to check consistency."""
    print("\n" + "=" * 80)
    print("Quick Recall Test: 'My name is Alice' → 'What is my name?'")
    print("Testing 5 times to check consistency with improved prompt")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"

    results = []

    for run in range(1, 6):
        print(f"\n{'=' * 80}")
        print(f"RUN {run}/5")
        print("=" * 80)

        try:
            formation = Formation()
            await formation.load(str(formation_path))
            overlord = await formation.start_overlord()

            # Turn 1: Store name
            print("\n✓ Turn 1: Storing 'My name is Alice'...")
            _ = await overlord.chat(
                message="My name is Alice",
                user_id=f"test_run_{run}",
                session_id=f"quick_test_{run}",
                stream=False
            )

            # Wait for extraction
            await asyncio.sleep(6)

            # Turn 2: Recall name
            print("✓ Turn 2: Asking 'What is my name?'...")
            response2 = await overlord.chat(
                message="What is my name?",
                user_id=f"test_run_{run}",
                session_id=f"quick_test_{run}",
                stream=False
            )

            content = response2.content if hasattr(response2, "content") else str(response2)

            # Check result
            has_alice = "alice" in content.lower()
            has_clarification = any(ind in content.lower() for ind in [
                "could you specify",
                "could you clarify",
                "what do you mean",
                "need more information",
                "which name"
            ])

            if has_alice and not has_clarification:
                result = "✅ SUCCESS"
                print(f"\n✅ Run {run}: Alice mentioned, no clarification")
            elif has_alice and has_clarification:
                result = "⚠️  PARTIAL"
                print(f"\n⚠️  Run {run}: Alice mentioned but also clarification")
            elif not has_alice and has_clarification:
                result = "❌ FAILED"
                print(f"\n❌ Run {run}: Clarification triggered, no Alice")
            else:
                result = "❓ UNCLEAR"
                print(f"\n❓ Run {run}: Unexpected response")

            print(f"   Response: {content[:200]}...")
            results.append(result)

            # Cleanup
            await formation.stop_overlord()
            formation.stop()

        except Exception as e:
            print(f"\n✗ Run {run} error: {str(e)}")
            results.append("❌ ERROR")

    # Final tally
    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)

    success_count = results.count("✅ SUCCESS")
    partial_count = results.count("⚠️  PARTIAL")
    failed_count = results.count("❌ FAILED")
    unclear_count = results.count("❓ UNCLEAR")
    error_count = results.count("❌ ERROR")

    print(f"\n✅ SUCCESS: {success_count}/5 ({success_count * 20}%)")
    print(f"⚠️  PARTIAL: {partial_count}/5 ({partial_count * 20}%)")
    print(f"❌ FAILED:  {failed_count}/5 ({failed_count * 20}%)")
    print(f"❓ UNCLEAR: {unclear_count}/5 ({unclear_count * 20}%)")
    print(f"❌ ERROR:   {error_count}/5 ({error_count * 20}%)")

    print("\nDetailed results:")
    for i, r in enumerate(results, 1):
        print(f"  Run {i}: {r}")

    if success_count >= 4:
        print("\n🎉 EXCELLENT: Improved prompt is working consistently!")
    elif success_count + partial_count >= 4:
        print("\n✅ GOOD: Improved prompt is mostly working")
    elif success_count >= 2:
        print("\n⚠️  MIXED: Some improvement but still inconsistent")
    else:
        print("\n❌ NO IMPROVEMENT: Prompt changes didn't help significantly")

    print("=" * 80)

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_recall_consistency())
    import os; os._exit(exit_code)
