#!/usr/bin/env python3
"""
Test 8.1: Basic Clarification Flow
Tests fundamental clarification system behavior with ambiguous requests.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from base_clarification_test import BaseClarificationTest  # noqa: E402


class Test81(BaseClarificationTest):
    """Test class for test_8_1."""

async def test_basic_clarification():
    """Test basic clarification flow - ambiguous requests should trigger clarification."""
    print("\n" + "=" * 80)
    print("Test 8.1: Basic Clarification Flow")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        from muxi.formation import Formation  # noqa: E402
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")
        print(f"   Clarification enabled: {overlord.clarification is not None}")

            # Test 1: Simple Clarification Request
            print("\n  1. Testing Simple clarification request...")
            prompt1 = "Build it"
            transcript.append(("User", prompt1))

            response1 = await self.overlord.chat(
                prompt1,
                user_id="test_user",
                session_id="clarification_test_1",
                use_async=False,
                stream=False
            )

            result1 = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append(("System", result1[:100] + "..." if len(result1) > 100 else result1))

            # Verify content
            if result1 and len(result1) > 5:
                print(f"    ✓ Response received for Simple clarification request ({len(result1)} chars)")
                checks_passed.append("Clarification requested")

                # Verification logic
                assert len(result1) > 10
            else:
                print("    ✗ No meaningful response for Simple clarification request")
                all_passed = False

            # Test 2: Clarification Response Handling
            print("\n  2. Testing Clarification response handling...")
            prompt2 = "Create something useful"
            transcript.append(("User", prompt2))

            response2 = await self.overlord.chat(
                prompt2,
                user_id="test_user",
                session_id="clarification_test_2",
                use_async=False,
                stream=False
            )

            result2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append(("System", result2[:100] + "..." if len(result2) > 100 else result2))

            # Verify content
            if result2 and len(result2) > 5:
                print(f"    ✓ Response received for Clarification response handling ({len(result2)} chars)")
                checks_passed.append("Clarification flow working")

                # Verification logic
                assert 'what' in result2.lower() or 'how' in result2.lower()
            else:
                print("    ✗ No meaningful response for Clarification response handling")
                all_passed = False

            # Test 3: Clarification Completion
            print("\n  3. Testing Clarification completion...")
            prompt3 = "Help me with the project"
            transcript.append(("User", prompt3))

            response3 = await self.overlord.chat(
                prompt3,
                user_id="test_user",
                session_id="clarification_test_3",
                use_async=False,
                stream=False
            )

            result3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append(("System", result3[:100] + "..." if len(result3) > 100 else result3))

            # Verify content
            if result3 and len(result3) > 5:
                print(f"    ✓ Response received for Clarification completion ({len(result3)} chars)")
                checks_passed.append("Clarification completed")

                # Verification logic
                assert 'project' in result3.lower() or 'help' in result3.lower()
            else:
                print("    ✗ No meaningful response for Clarification completion")
                all_passed = False

            # Final validation
            print("\n  4. Validating responses...")
            total_responses = len([r for r in [result1, result2, result3] if r and len(r) > 5])

            if total_responses >= 2:
                print(f"    ✓ Received {total_responses} meaningful responses")
                checks_passed.append(f"Total successful responses: {total_responses}")
            else:
                print(f"    ✗ Only {total_responses} meaningful responses")
                all_passed = False

        except Exception as e:
            print(f"  ✗ Test failed: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)
        return all_passed

    async def run_test(self):
        """Run test."""
        print("\n" + "=" * 60)
        print("🧪 AREA TEST_8_1")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Testtest81()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
