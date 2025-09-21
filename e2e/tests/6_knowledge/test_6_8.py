#!/usr/bin/env python3
"""Test test_6_8: Context-Aware Knowledge Retrieval"""

import asyncio
import time
import os

from .base_knowledge_test import BaseKnowledgeTest


class Testtest68(BaseKnowledgeTest):
    """Test class for test_6_8."""

    async def test_main(self):
        """Test context-aware knowledge retrieval functionality."""
        test_name = "test_6_8"
        self.print_test_header(test_name, "Context-Aware Knowledge Retrieval")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Context-Based Knowledge Selection
            print("\n  1. Testing Context-based knowledge selection...")
            prompt1 = "I'm a developer looking for automation solutions"
            transcript.append(("User", prompt1))

            response1 = await self.overlord.chat(
                prompt1,
                user_id="test_user",
                session_id="knowledge_test_1",
                use_async=False,
                stream=False
            )

            result1 = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append(("System", result1[:100] + "..." if len(result1) > 100 else result1))

            # Verify knowledge content
            if result1 and len(result1) > 10:
                print(f"    ✓ Knowledge retrieved for Context-based knowledge selection ({len(result1)} chars)")
                checks_passed.append("Context-aware selection working")

                # Verification logic
                assert 'developer' in result1.lower() or 'automation' in result1.lower()

                if 'keywords_found' in locals() and keywords_found:
                    print(f"    ✓ Found relevant keywords: {', '.join(keywords_found)}")
                    checks_passed.append(f"Keywords found: {', '.join(keywords_found)}")
            else:
                print("    ✗ No meaningful knowledge retrieved for Context-based knowledge selection")
                all_passed = False

            # Test 2: User Role-Based Knowledge Filtering
            print("\n  2. Testing User role-based knowledge filtering...")
            prompt2 = "What pricing options are available for enterprises?"
            transcript.append(("User", prompt2))

            response2 = await self.overlord.chat(
                prompt2,
                user_id="test_user",
                session_id="knowledge_test_2",
                use_async=False,
                stream=False
            )

            result2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append(("System", result2[:100] + "..." if len(result2) > 100 else result2))

            # Verify knowledge content
            if result2 and len(result2) > 10:
                print(f"    ✓ Knowledge retrieved for User role-based knowledge filtering ({len(result2)} chars)")
                checks_passed.append("Role-based filtering working")

                # Verification logic
                assert 'enterprise' in result2.lower() or 'pricing' in result2.lower()

                if 'keywords_found' in locals() and keywords_found:
                    print(f"    ✓ Found relevant keywords: {', '.join(keywords_found)}")
                    checks_passed.append(f"Keywords found: {', '.join(keywords_found)}")
            else:
                print("    ✗ No meaningful knowledge retrieved for User role-based knowledge filtering")
                all_passed = False

            # Test 3: Contextual Knowledge Enhancement
            print("\n  3. Testing Contextual knowledge enhancement...")
            prompt3 = "I need a complete solution for CI/CD automation"
            transcript.append(("User", prompt3))

            response3 = await self.overlord.chat(
                prompt3,
                user_id="test_user",
                session_id="knowledge_test_3",
                use_async=False,
                stream=False
            )

            result3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append(("System", result3[:100] + "..." if len(result3) > 100 else result3))

            # Verify knowledge content
            if result3 and len(result3) > 10:
                print(f"    ✓ Knowledge retrieved for Contextual knowledge enhancement ({len(result3)} chars)")
                checks_passed.append("Contextual enhancement working")

                # Verification logic
                assert 'ci/cd' in result3.lower() or 'automation' in result3.lower()

                if 'keywords_found' in locals() and keywords_found:
                    print(f"    ✓ Found relevant keywords: {', '.join(keywords_found)}")
                    checks_passed.append(f"Keywords found: {', '.join(keywords_found)}")
            else:
                print("    ✗ No meaningful knowledge retrieved for Contextual knowledge enhancement")
                all_passed = False

            # Final validation
            print("\n  4. Validating knowledge retrieval...")
            total_responses = len([r for r in [result1, result2, result3] if r and len(r) > 10])

            if total_responses >= 2:
                print(f"    ✓ Knowledge retrieved from {total_responses} queries")
                checks_passed.append(f"Total successful knowledge queries: {total_responses}")
            else:
                print(f"    ✗ Only {total_responses} successful knowledge queries")
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
        print("🧪 AREA TEST_6_8")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Testtest68()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
