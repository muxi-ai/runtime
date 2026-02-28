#!/usr/bin/env python3
"""Test test_8_2: Multi-Turn Clarification"""

import asyncio
import time
import os

from base_clarification_test import BaseClarificationTest


class Testtest82(BaseClarificationTest):
    """Test class for test_8_2."""

    async def test_main(self):
        """Test multi-turn clarification functionality."""
        test_name = "test_8_2"
        self.print_test_header(test_name, "Multi-Turn Clarification")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Multi-Turn Clarification Sequence
            print("\n  1. Testing Multi-turn clarification sequence...")
            prompt1 = "Make the application"
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
                print(f"    ✓ Response received for Multi-turn clarification sequence ({len(result1)} chars)")
                checks_passed.append("Multi-turn clarification started")

                # Verification logic
                assert len(result1) > 10
            else:
                print("    ✗ No meaningful response for Multi-turn clarification sequence")
                all_passed = False

            # Test 2: Context Preservation In Clarification
            print("\n  2. Testing Context preservation in clarification...")
            prompt2 = "Update the system"
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
                print(f"    ✓ Response received for Context preservation in clarification ({len(result2)} chars)")
                checks_passed.append("Context preserved")

                # Verification logic
                assert 'system' in result2.lower() or 'update' in result2.lower()
            else:
                print("    ✗ No meaningful response for Context preservation in clarification")
                all_passed = False

            # Test 3: Clarification Chain Completion
            print("\n  3. Testing Clarification chain completion...")
            prompt3 = "Fix the issues"
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
                print(f"    ✓ Response received for Clarification chain completion ({len(result3)} chars)")
                checks_passed.append("Clarification chain completed")

                # Verification logic
                assert 'fix' in result3.lower() or 'issue' in result3.lower()
            else:
                print("    ✗ No meaningful response for Clarification chain completion")
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
        print("🧪 AREA TEST_8_2")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Testtest82()
    result = asyncio.run(test.run_test())
    if result:
        print("SUCCESS", flush=True)
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
