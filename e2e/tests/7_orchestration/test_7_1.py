#!/usr/bin/env python3
"""Test test_7_1: Basic Task Decomposition"""

import asyncio
import time
import os

from .base_orchestration_test import Baseorchestrationtest


class Testtest71(Baseorchestrationtest):
    """Test class for test_7_1."""

    async def test_main(self):
        """Test basic task decomposition functionality."""
        test_name = "test_7_1"
        self.print_test_header(test_name, "Basic Task Decomposition")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Simple Task Decomposition
            print("\n  1. Testing Simple task decomposition...")
            prompt1 = "Research the topic of AI automation and write a summary"
            transcript.append(("User", prompt1))

            response1 = await self.overlord.chat(
                prompt1,
                user_id="test_user",
                session_id="orchestration_test_1",
                use_async=False,
                stream=False
            )

            result1 = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append(("System", result1[:100] + "..." if len(result1) > 100 else result1))

            # Verify content
            if result1 and len(result1) > 5:
                print(f"    ✓ Response received for Simple task decomposition ({len(result1)} chars)")
                checks_passed.append("Task decomposition working")

                # Verification logic
                assert len(result1) > 50
            else:
                print("    ✗ No meaningful response for Simple task decomposition")
                all_passed = False

            # Test 2: Multi-Step Workflow Creation
            print("\n  2. Testing Multi-step workflow creation...")
            prompt2 = "Analyze sales data, create charts, and generate a report with recommendations"
            transcript.append(("User", prompt2))

            response2 = await self.overlord.chat(
                prompt2,
                user_id="test_user",
                session_id="orchestration_test_2",
                use_async=False,
                stream=False
            )

            result2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append(("System", result2[:100] + "..." if len(result2) > 100 else result2))

            # Verify content
            if result2 and len(result2) > 5:
                print(f"    ✓ Response received for Multi-step workflow creation ({len(result2)} chars)")
                checks_passed.append("Multi-step workflow created")

                # Verification logic
                assert 'analyze' in result2.lower() or 'chart' in result2.lower()
            else:
                print("    ✗ No meaningful response for Multi-step workflow creation")
                all_passed = False

            # Test 3: Workflow Dependency Handling
            print("\n  3. Testing Workflow dependency handling...")
            prompt3 = "Search for information, process it, and create deliverables"
            transcript.append(("User", prompt3))

            response3 = await self.overlord.chat(
                prompt3,
                user_id="test_user",
                session_id="orchestration_test_3",
                use_async=False,
                stream=False
            )

            result3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append(("System", result3[:100] + "..." if len(result3) > 100 else result3))

            # Verify content
            if result3 and len(result3) > 5:
                print(f"    ✓ Response received for Workflow dependency handling ({len(result3)} chars)")
                checks_passed.append("Workflow dependencies handled")

                # Verification logic
                assert len(result3) > 30
            else:
                print("    ✗ No meaningful response for Workflow dependency handling")
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
        print("🧪 AREA TEST_7_1")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Testtest71()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
