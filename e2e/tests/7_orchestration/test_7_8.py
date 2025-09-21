#!/usr/bin/env python3
"""Test test_7_8: Integration with External Systems"""

import asyncio
import time
import os

from .base_orchestration_test import Baseorchestrationtest


class Testtest78(Baseorchestrationtest):
    """Test class for test_7_8."""

    async def test_main(self):
        """Test integration with external systems functionality."""
        test_name = "test_7_8"
        self.print_test_header(test_name, "Integration with External Systems")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: External Api Integration
            print("\n  1. Testing External API integration...")
            prompt1 = "Integrate workflow with external APIs and services"
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
                print(f"    ✓ Response received for External API integration ({len(result1)} chars)")
                checks_passed.append("External integration working")

                # Verification logic
                assert 'integrate' in result1.lower() or 'api' in result1.lower()
            else:
                print("    ✗ No meaningful response for External API integration")
                all_passed = False

            # Test 2: Third-Party Service Coordination
            print("\n  2. Testing Third-party service coordination...")
            prompt2 = "Coordinate with third-party services in workflow"
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
                print(f"    ✓ Response received for Third-party service coordination ({len(result2)} chars)")
                checks_passed.append("Service coordination active")

                # Verification logic
                assert 'coordinate' in result2.lower() or 'service' in result2.lower()
            else:
                print("    ✗ No meaningful response for Third-party service coordination")
                all_passed = False

            # Test 3: Cross-System Data Flow
            print("\n  3. Testing Cross-system data flow...")
            prompt3 = "Manage data flow across different systems"
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
                print(f"    ✓ Response received for Cross-system data flow ({len(result3)} chars)")
                checks_passed.append("Cross-system flow working")

                # Verification logic
                assert 'data' in result3.lower() or 'flow' in result3.lower()
            else:
                print("    ✗ No meaningful response for Cross-system data flow")
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
        print("🧪 AREA TEST_7_8")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Testtest78()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
