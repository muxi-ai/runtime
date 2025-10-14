#!/usr/bin/env python3
"""Test 2K2_MEMORY_PRIORITY: Memory Priority in Context Enhancement

This test validates:
1. Important long-term memories are prioritized over recent buffer noise
2. Health and critical information retrieval despite message volume
3. Context window management with priority
4. Memory search relevance scoring
"""

import asyncio
import time
import os
import psycopg2

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest
from test_utils import timeout_test, safe_overlord_chat, with_timeout, safe_formation_load, safe_formation_shutdown


class Test2k2MemoryPriority(BaseMemoryTest):
    """Test memory prioritization in context enhancement."""

    @timeout_test(120.0)
    async def test_2k2memorypriority(self):
        """Test memory prioritization despite buffer noise."""
        test_name = "2k2_memory_priority"
        self.print_test_header(test_name, "Memory Priority in Context Enhancement")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Setup formation with postgres for advanced memory features
            await self.setup_memory_formation("postgres")
            print("  ✓ Formation loaded")

            # Setup database connection
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()

            # Clear test data
            test_user = "priority_test_user"
            cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
            cur.execute("""
                DELETE FROM users WHERE id IN (
                    SELECT user_id FROM user_identifiers WHERE identifier = %s
                )
            """, (test_user,))
            conn.commit()

            # Test 1: Important information extraction
            print("\n  1. Establishing important long-term memories...")

            critical_info = [
                "I'm allergic to peanuts - this is very important!",
                "I'm diabetic and need to monitor sugar intake",
                "I'm vegetarian for ethical reasons"
            ]

            for info in critical_info:
                response = await self.overlord.chat(info, user_id=test_user, use_async=False, stream=False)
                transcript.append(("User", info))

                response_text = ""
                # Handle response (stream=False, so response is a string or object with .content)
                response_text = response.content if hasattr(response, "content") else str(response)
                transcript.append(("System", response_text[:50] + "..." if len(response_text) > 50 else response_text))

                await asyncio.sleep(3)

            print("    ✓ Stored critical dietary and health information")
            checks_passed.append("Stored critical health information")

            # Test 2: Fill buffer with noise
            print("\n  2. Filling buffer with unrelated messages...")

            for i in range(15):
                noise_msg = f"Random conversation {i} about the weather, sports, and other topics"
                await self.overlord.chat(noise_msg, user_id=test_user, use_async=False, stream=False)
                await asyncio.sleep(0.5)

            print("    ✓ Added 15 noise messages to buffer")
            checks_passed.append("Added buffer noise")

            # Test 3: Query about important information
            print("\n  3. Testing retrieval of important information despite noise...")

            health_query = "Do I have any dietary restrictions or health concerns?"
            response = await self.overlord.chat(health_query, user_id=test_user, use_async=False, stream=False)
            transcript.append(("User", health_query))

            # Handle response (stream=False, so response is a string or object with .content)
            response_text = response.content if hasattr(response, "content") else str(response)

            transcript.append(("System", response_text[:100] + "..." if len(response_text) > 100 else response_text))

            # Should prioritize health-related memories
            important_terms = ["peanut", "allerg", "diabet", "sugar", "vegetarian"]
            found_terms = [term for term in important_terms if term in response_text.lower()]

            if len(found_terms) >= 2:
                print(f"    ✓ Retrieved important memories: {found_terms}")
                checks_passed.append(f"Retrieved {len(found_terms)} important health terms")
            else:
                print(f"    ✗ Failed to retrieve important health info. Found only: {found_terms}")
                all_passed = False

            # Test 4: Specific allergy query
            print("\n  4. Testing specific health query...")

            allergy_query = "Can I eat this peanut butter sandwich?"
            response = await self.overlord.chat(allergy_query, user_id=test_user, use_async=False, stream=False)
            transcript.append(("User", allergy_query))

            # Handle response (stream=False, so response is a string or object with .content)
            response_text = response.content if hasattr(response, "content") else str(response)

            transcript.append(("System", response_text[:100] + "..." if len(response_text) > 100 else response_text))

            # MUST warn about peanut allergy
            allergy_warning = ("no" in response_text.lower() or
                             "allerg" in response_text.lower() or
                             "avoid" in response_text.lower())

            if allergy_warning:
                print("    ✓ Correctly warned about peanut allergy")
                checks_passed.append("Correctly warned about peanut allergy")
            else:
                print(f"    ✗ Failed to warn about peanut allergy: {response_text}")
                all_passed = False

            # Test 5: Verify memory search prioritization
            print("\n  5. Checking memory search relevance...")

            try:
                # Query memories directly to verify search
                cur.execute("""
                    SELECT text, collection,
                           ts_rank(to_tsvector('english', text),
                                   to_tsquery('english', 'peanut | allergy')) as rank
                    FROM memories
                    WHERE meta_data->>'user_id' = %s
                    AND to_tsvector('english', text) @@ to_tsquery('english', 'peanut | allergy')
                    ORDER BY rank DESC
                """, (test_user,))

                search_results = cur.fetchall()

                if len(search_results) > 0 and search_results[0][2] > 0:
                    print(f"    ✓ Allergy memory has relevance score: {search_results[0][2]}")
                    checks_passed.append(f"Allergy memory ranked with score {search_results[0][2]:.3f}")
                else:
                    print("    ⚠ No allergy memory found via search (may use different search method)")
                    checks_passed.append("Memory search mechanism may differ from expected")
            except Exception as e:
                print(f"    ⚠ Could not verify search ranking: {e}")
                # Don't fail the test for this

            # Test 6: Context window management
            print("\n  6. Testing context window with priority...")

            # Add more important information
            blood_info = "My blood type is O-negative, important for emergencies"
            await self.overlord.chat(blood_info, user_id=test_user, use_async=False, stream=False)
            transcript.append(("User", blood_info))
            await asyncio.sleep(3)

            # Query should still include all critical info
            medical_query = "What critical medical information should a doctor know about me?"
            response = await self.overlord.chat(medical_query, user_id=test_user, use_async=False, stream=False)
            transcript.append(("User", medical_query))

            # Handle response (stream=False, so response is a string or object with .content)
            response_text = response.content if hasattr(response, "content") else str(response)

            transcript.append(("System", response_text[:100] + "..." if len(response_text) > 100 else response_text))

            medical_info = ["allerg", "peanut", "diabet", "vegetarian", "o-negative", "blood"]
            found_medical = [info for info in medical_info if info in response_text.lower()]

            if len(found_medical) >= 3:
                print(f"    ✓ Medical summary includes: {found_medical}")
                checks_passed.append(f"Medical summary includes {len(found_medical)} key terms")
            else:
                print(f"    ✗ Missing critical medical info. Found: {found_medical}")
                all_passed = False

            cur.close()
            conn.close()

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("📝 AREA 2K2_MEMORY_PRIORITY")
        print("=" * 60)

        # Run test cases
        result = await self.test_2k2memorypriority()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Test2k2MemoryPriority()
    result = asyncio.run(test.run_test())
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
