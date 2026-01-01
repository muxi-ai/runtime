#!/usr/bin/env python3
"""Test 2I2_COMPLEX_EXTRACTION: Complex Multi-Fact Extraction

This test validates:
1. Extraction of multiple facts from a single complex message
2. Distribution across different memory collections
3. Natural language format preservation
4. Complex multi-domain information extraction
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


class Test2i2ComplexExtraction(BaseMemoryTest):
    """Test complex multi-fact memory extraction."""

    async def test_2i2complexextraction(self):
        """Test extraction of multiple facts from complex messages."""
        test_name = "2i2_complex_extraction"
        self.print_test_header(test_name, "Complex Multi-Fact Extraction")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Setup formation with postgres for memory inspection
            await self.setup_memory_formation("postgres")
            print("  ✓ Formation loaded")

            # Setup database connection for memory inspection
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()

            # Clear test data
            test_user = "complex_extraction_user"
            cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
            cur.execute("""
                DELETE FROM users WHERE id IN (
                    SELECT user_id FROM user_identifiers WHERE identifier = %s
                )
            """, (test_user,))
            conn.commit()

            # Test 1: CEO and company information
            print("\n  1. Testing complex sentence with multiple facts...")
            response1 = await self.overlord.chat(
                "I'm the CEO of TechStart, a company that builds AI tools for healthcare",
                user_id=test_user,
                use_async=False,
            )
            transcript.append(("User", "I'm the CEO of TechStart, a company that builds AI tools for healthcare"))

            response_text = ""
            if hasattr(response1, "__aiter__"):
                async for chunk in response1:
                    response_text += chunk
            else:
                response_text = response1.content if hasattr(response1, "content") else str(response1)

            transcript.append(("System", response_text[:200] + "..." if len(response_text) > 200 else response_text))

            await asyncio.sleep(5)  # Wait for extraction

            # Check extracted memories
            cur.execute(
                """
                SELECT text, collection
                FROM memories
                WHERE meta_data->>'user_id' = %s
                ORDER BY created_at ASC
            """,
                (test_user,),
            )

            memories = cur.fetchall()
            memory_texts = [mem[0] for mem in memories]
            all_text = " ".join(memory_texts)

            # Verify all facts were extracted
            facts_to_verify = [
                ("CEO", "job title"),
                ("TechStart", "company name"),
                ("AI tools", "product/service"),
                ("healthcare", "industry"),
            ]

            fact_extraction_success = True
            for fact, description in facts_to_verify:
                if fact in all_text:
                    print(f"    ✓ Extracted {description}: {fact}")
                    checks_passed.append(f"Extracted {description}: {fact}")
                else:
                    print(f"    ✗ Missing {description} '{fact}' in: {memory_texts}")
                    fact_extraction_success = False

            if not fact_extraction_success:
                all_passed = False
            else:
                checks_passed.append("All facts from complex message extracted")

            # Test 2: Multiple facts in different domains
            print("\n  2. Testing multiple domain extraction...")
            response2 = await self.overlord.chat(
                "I live in San Francisco, have two kids, and enjoy playing chess in my free time",
                user_id=test_user,
                use_async=False,
            )
            transcript.append(("User", "I live in San Francisco, have two kids, and enjoy playing chess in my free time"))

            response_text2 = ""
            if hasattr(response2, "__aiter__"):
                async for chunk in response2:
                    response_text2 += chunk
            else:
                response_text2 = response2.content if hasattr(response2, "content") else str(response2)

            transcript.append(("System", response_text2[:200] + "..." if len(response_text2) > 200 else response_text2))

            await asyncio.sleep(5)

            # Get all memories for this user to see what was extracted
            cur.execute(
                """
                SELECT text, collection
                FROM memories
                WHERE meta_data->>'user_id' = %s
                ORDER BY created_at ASC
            """,
                (test_user,),
            )

            all_memories_now = cur.fetchall()
            new_memories = all_memories_now[len(memories):]  # Get only the new ones
            new_texts = [mem[0] for mem in new_memories]
            all_new_text = " ".join(new_texts)

            print(f"\n    All memories after second message ({len(all_memories_now)} total):")
            for i, (text, coll) in enumerate(all_memories_now):
                print(f"      {i+1}. [{coll}] {text}")

            # Verify location, family, and hobby extraction
            location_success = "San Francisco" in all_new_text
            family_success = "two kids" in all_new_text or "2 kids" in all_new_text
            hobby_success = "chess" in all_new_text

            if location_success:
                print("    ✓ Extracted location: San Francisco")
                checks_passed.append("Extracted location: San Francisco")
            else:
                print(f"    ✗ Missing location in: {new_texts}")
                all_passed = False

            if family_success:
                print("    ✓ Extracted family: two kids")
                checks_passed.append("Extracted family: two kids")
            else:
                print(f"    ✗ Missing family info in: {new_texts}")
                all_passed = False

            if hobby_success:
                print("    ✓ Extracted hobby: chess")
                checks_passed.append("Extracted hobby: chess")
            else:
                print(f"    ✗ Missing hobby in: {new_texts}")
                all_passed = False

            # Test 3: Verify appropriate collections
            print("\n  3. Checking collection diversity...")
            collections_used = {mem[1] for mem in all_memories_now}

            expected_collections = {"user_identity", "relationships", "activities", "preferences"}
            found_collections = collections_used.intersection(expected_collections)

            if len(found_collections) >= 2:
                print(f"    ✓ Facts distributed across collections: {collections_used}")
                checks_passed.append(f"Facts distributed across {len(found_collections)} collection types")
            else:
                print(f"    ✗ Expected multiple collection types, found: {collections_used}")
                all_passed = False

            # Test 4: Natural language format preserved
            print("\n  4. Verifying natural language format...")
            natural_format_success = True
            for text, _ in all_memories_now:
                # Should be complete sentences, not fragments
                if len(text.split()) < 3:
                    print(f"    ✗ Memory too short/fragmented: {text}")
                    natural_format_success = False
                # Should not be raw extraction without context
                if text.startswith("CEO of"):
                    print(f"    ✗ Missing sentence structure: {text}")
                    natural_format_success = False

            if natural_format_success:
                print("    ✓ All memories stored as complete natural sentences")
                checks_passed.append("All memories stored as complete natural sentences")
            else:
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
        print("📝 AREA 2I2_COMPLEX_EXTRACTION")
        print("=" * 60)

        # Run test cases
        result = await self.test_2i2complexextraction()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Test2i2ComplexExtraction()
    result = asyncio.run(test.run_test())
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
