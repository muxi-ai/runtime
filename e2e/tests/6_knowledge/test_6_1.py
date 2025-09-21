#!/usr/bin/env python3
"""Test test_6_1: Basic Knowledge Routing and Search"""

import asyncio
import time
import os

from .base_knowledge_test import BaseKnowledgeTest


class Testtest61(BaseKnowledgeTest):
    """Test class for test_6_1."""

    async def test_main(self):
        """Test basic knowledge routing and search functionality."""
        test_name = "test_6_1"
        self.print_test_header(test_name, "Basic Knowledge Routing and Search")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            await self.setup_formation()
            print("  ✓ Formation loaded")

            # Test 1: Faq Knowledge Routing
            print("\n  1. Testing FAQ knowledge routing...")
            prompt1 = "What services does Automaze offer?"
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
                print(f"    ✓ Knowledge retrieved for FAQ knowledge routing ({len(result1)} chars)")
                checks_passed.append("FAQ knowledge retrieved")

                # Verification logic
                automaze_keywords = ['automaze', 'service', 'solution', 'automation']
keywords_found = [kw for kw in automaze_keywords if kw.lower() in result1.lower()]

                if 'keywords_found' in locals() and keywords_found:
                    print(f"    ✓ Found relevant keywords: {', '.join(keywords_found)}")
                    checks_passed.append(f"Keywords found: {', '.join(keywords_found)}")
            else:
                print("    ✗ No meaningful knowledge retrieved for FAQ knowledge routing")
                all_passed = False

            # Test 2: Business Plan Knowledge
            print("\n  2. Testing Business plan knowledge...")
            prompt2 = "What are MUXI's pricing plans?"
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
                print(f"    ✓ Knowledge retrieved for Business plan knowledge ({len(result2)} chars)")
                checks_passed.append("Business plan knowledge retrieved")

                # Verification logic
                muxi_keywords = ['muxi', 'price', 'plan', 'tier']
keywords_found = [kw for kw in muxi_keywords if kw.lower() in result2.lower()]

                if 'keywords_found' in locals() and keywords_found:
                    print(f"    ✓ Found relevant keywords: {', '.join(keywords_found)}")
                    checks_passed.append(f"Keywords found: {', '.join(keywords_found)}")
            else:
                print("    ✗ No meaningful knowledge retrieved for Business plan knowledge")
                all_passed = False

            # Test 3: Documentation Search
            print("\n  3. Testing Documentation search...")
            prompt3 = "How do I configure MUXI runtime?"
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
                print(f"    ✓ Knowledge retrieved for Documentation search ({len(result3)} chars)")
                checks_passed.append("Documentation knowledge accessed")

                # Verification logic
                doc_keywords = ['configure', 'runtime', 'setup']
keywords_found = [kw for kw in doc_keywords if kw.lower() in result3.lower()]

                if 'keywords_found' in locals() and keywords_found:
                    print(f"    ✓ Found relevant keywords: {', '.join(keywords_found)}")
                    checks_passed.append(f"Keywords found: {', '.join(keywords_found)}")
            else:
                print("    ✗ No meaningful knowledge retrieved for Documentation search")
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
        print("🧪 AREA TEST_6_1")
        print("=" * 60)

        result = await self.test_main()

        print("\n" + "=" * 60)
        print(f"🎯 RESULT: {'✅ PASSED' if result else '❌ FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Testtest61()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
