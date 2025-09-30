#!/usr/bin/env python3
"""Test 2I1: Natural Language Memory Extraction

This test validates:
1. Natural language memory extraction vs key-value pairs
2. Age to birth year conversion
3. Complex sentence extraction
4. Memory collection assignments
"""

import sys
import asyncio
import time
import os
import psycopg2
from pathlib import Path
from datetime import datetime

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest  # noqa: E402


class TestNaturalLanguageExtraction(BaseMemoryTest):
    """Test natural language memory extraction."""

    async def test_name_age_extraction(self):
        """Test basic name and age extraction in natural language format."""
        print("\n  👤 Testing Name and Age Extraction")

        test_user = "natural_lang_test_user"
        current_year = datetime.now().year

        # Clear test data first
        try:
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()
            cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
            cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
            conn.commit()
        except Exception as e:
            print(f"    Warning: Could not clear test data: {e}")
            return False, {"error": "Database connection failed"}

        try:
            print("    1. Testing name and age extraction...")
            await self.overlord.chat(
                "My name is Sarah and I'm 28 years old", user_id=test_user, use_async=False
            )
            await asyncio.sleep(5)  # Wait for extraction

            # Check memories in database
            cur.execute(
                """
                SELECT text, collection
                FROM memories
                WHERE meta_data->>'user_id' = %s
                ORDER BY created_at DESC
            """,
                (test_user,),
            )

            memories = cur.fetchall()
            memory_texts = [mem[0] for mem in memories]

            print(f"    Found {len(memory_texts)} memories:")
            for text in memory_texts[:3]:  # Show first 3
                print(f"      - {text[:80]}...")

            # Verify natural language format
            name_found = any("The user's name is Sarah" in text for text in memory_texts)
            if not name_found:
                # Alternative checks for name extraction
                name_found = any(
                    "Sarah" in text and ("name" in text or "called" in text)
                    for text in memory_texts
                )

            # Verify age converted to birth year
            expected_birth_year = current_year - 28
            birth_year_found = any(
                f"Was born in {expected_birth_year}" in text for text in memory_texts
            )
            if not birth_year_found:
                # Alternative checks for birth year
                birth_year_found = any(str(expected_birth_year) in text for text in memory_texts)

            print(f"    ✓ Name extraction: {'SUCCESS' if name_found else 'FAILED'}")
            print(f"    ✓ Birth year extraction: {'SUCCESS' if birth_year_found else 'FAILED'}")

            return name_found and birth_year_found, {
                "memories_extracted": len(memory_texts),
                "name_found": name_found,
                "birth_year_found": birth_year_found,
                "expected_birth_year": expected_birth_year,
            }

        except Exception as e:
            print(f"    ❌ Name and age extraction failed: {e}")
            return False, {"error": str(e)}
        finally:
            if "conn" in locals():
                cur.close()
                conn.close()

    async def test_complex_extraction(self):
        """Test complex information extraction."""
        print("\n  🏢 Testing Complex Information Extraction")

        test_user = "natural_lang_test_user"

        try:
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()

            print("    2. Testing complex information extraction...")
            await self.overlord.chat(
                "I work at DataCorp as a senior data scientist and I love hiking",
                user_id=test_user,
                use_async=False,
            )
            await asyncio.sleep(7)  # Wait for extraction

            # Get all memories for this user
            cur.execute(
                """
                SELECT text, collection
                FROM memories
                WHERE meta_data->>'user_id' = %s
                ORDER BY created_at DESC
            """,
                (test_user,),
            )

            all_memories = cur.fetchall()
            all_texts = [mem[0] for mem in all_memories]

            print(f"    Found {len(all_texts)} total memories:")
            for i, text in enumerate(all_texts[:5]):  # Show first 5
                print(f"      {i+1}. {text[:80]}...")

            # Should have extracted facts from both messages
            datacorp_found = any("DataCorp" in text for text in all_texts)
            job_found = any("data scientist" in text for text in all_texts)
            hobby_found = any("hiking" in text for text in all_texts)

            print(f"    ✓ Company extraction: {'SUCCESS' if datacorp_found else 'FAILED'}")
            print(f"    ✓ Job title extraction: {'SUCCESS' if job_found else 'FAILED'}")
            print(f"    ✓ Hobby extraction: {'SUCCESS' if hobby_found else 'FAILED'}")

            return datacorp_found and job_found and hobby_found, {
                "total_memories": len(all_texts),
                "company_found": datacorp_found,
                "job_found": job_found,
                "hobby_found": hobby_found,
            }

        except Exception as e:
            print(f"    ❌ Complex extraction failed: {e}")
            return False, {"error": str(e)}
        finally:
            if "conn" in locals():
                cur.close()
                conn.close()

    async def test_natural_language_format(self):
        """Verify memories are stored as natural sentences, not key-value pairs."""
        print("\n  📝 Testing Natural Language Format")

        test_user = "natural_lang_test_user"

        try:
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()

            # Get all memories for this user
            cur.execute(
                """
                SELECT text, collection
                FROM memories
                WHERE meta_data->>'user_id' = %s
                ORDER BY created_at DESC
            """,
                (test_user,),
            )

            all_memories = cur.fetchall()

            print("    3. Verifying no key-value pairs...")
            key_value_found = False
            natural_language_count = 0

            for text, _ in all_memories:
                # Check for key-value format indicators
                if text.startswith("name:") or text.startswith("age:") or text.startswith("job:"):
                    key_value_found = True
                    print(f"      ❌ Found key-value format: {text}")
                elif text.count(":") > 1 and "The user" not in text:
                    # Multiple colons might indicate structured data
                    key_value_found = True
                    print(f"      ❌ Potential key-value format: {text}")
                else:
                    natural_language_count += 1

            print(f"    ✓ Natural language memories: {natural_language_count}/{len(all_memories)}")
            print(
                f"    ✓ Key-value format avoided: {'SUCCESS' if not key_value_found else 'FAILED'}"
            )

            return not key_value_found, {
                "total_memories": len(all_memories),
                "natural_language_count": natural_language_count,
                "key_value_found": key_value_found,
            }

        except Exception as e:
            print(f"    ❌ Natural language format check failed: {e}")
            return False, {"error": str(e)}
        finally:
            if "conn" in locals():
                cur.close()
                conn.close()

    async def test_collection_assignments(self):
        """Verify memory collection assignments."""
        print("\n  📂 Testing Collection Assignments")

        test_user = "natural_lang_test_user"

        try:
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()

            # Get all memories for this user
            cur.execute(
                """
                SELECT text, collection
                FROM memories
                WHERE meta_data->>'user_id' = %s
                ORDER BY created_at DESC
            """,
                (test_user,),
            )

            all_memories = cur.fetchall()
            collections = {mem[1] for mem in all_memories if mem[1]}

            print("    4. Checking collection assignments...")
            print(f"    Found collections: {collections}")

            user_identity_found = "user_identity" in collections
            multiple_collections = len(collections) > 1

            print(
                f"    ✓ User identity collection: {'FOUND' if user_identity_found else 'MISSING'}"
            )
            print(f"    ✓ Multiple collections: {'YES' if multiple_collections else 'NO'}")

            return user_identity_found and len(collections) >= 1, {
                "collections": list(collections),
                "user_identity_found": user_identity_found,
                "collection_count": len(collections),
            }

        except Exception as e:
            print(f"    ❌ Collection assignment check failed: {e}")
            return False, {"error": str(e)}
        finally:
            if "conn" in locals():
                cur.close()
                conn.close()

    async def test_natural_extraction(self):
        """Main test method."""
        test_name = "2i1_natural_language_extraction"
        self.print_test_header(test_name, "Test automatic extraction from natural language")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Setup formation
            await self.setup_memory_formation("postgres")  # Use postgres for memory extraction
            print("  ✓ Formation loaded")

            print("  Testing Natural Language Memory Extraction...")

            # Test 1: Name and age extraction
            name_age_success, name_age_result = await self.test_name_age_extraction()
            if name_age_success:
                checks_passed.append("Name and age extraction working")
                transcript.append(("System", f"Name/age extraction test passed: {name_age_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Name/age extraction test failed: {name_age_result}"))

            # Test 2: Complex information extraction
            complex_success, complex_result = await self.test_complex_extraction()
            if complex_success:
                checks_passed.append("Complex information extraction working")
                transcript.append(("System", f"Complex extraction test passed: {complex_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Complex extraction test failed: {complex_result}"))

            # Test 3: Natural language format verification
            format_success, format_result = await self.test_natural_language_format()
            if format_success:
                checks_passed.append("Natural language format verified")
                transcript.append(("System", f"Format verification test passed: {format_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Format verification test failed: {format_result}"))

            # Test 4: Collection assignments
            collection_success, collection_result = await self.test_collection_assignments()
            if collection_success:
                checks_passed.append("Memory collections working")
                transcript.append(("System", f"Collection test passed: {collection_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Collection test failed: {collection_result}"))

            # Summary
            if name_age_success and complex_success and format_success and collection_success:
                print("  ✅ ALL NATURAL LANGUAGE EXTRACTION TESTS PASSED!")
                print("    ✅ Memories extracted as natural sentences (not key-value)")
                print("    ✅ Ages converted to birth years")
                print("    ✅ Complex information properly extracted")
                print("    ✅ Memories organized into appropriate collections")
                checks_passed.append("Complete natural language extraction verified")
            else:
                print("  ⚠️ PARTIAL SUCCESS")
                if name_age_success:
                    print("    ✅ Name and age extraction working")
                else:
                    print("    ❌ Name and age extraction failed")
                if complex_success:
                    print("    ✅ Complex information extraction working")
                else:
                    print("    ❌ Complex information extraction failed")
                if format_success:
                    print("    ✅ Natural language format verified")
                else:
                    print("    ❌ Natural language format issues")
                if collection_success:
                    print("    ✅ Memory collections working")
                else:
                    print("    ❌ Memory collection issues")

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False
            transcript.append(("System", f"Test failed with error: {str(e)}"))

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🗣️ AREA 2I1: NATURAL LANGUAGE EXTRACTION")
        print("=" * 60)

        # Run test cases
        result = await self.test_natural_extraction()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = TestNaturalLanguageExtraction()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
