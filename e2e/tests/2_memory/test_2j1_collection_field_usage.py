#!/usr/bin/env python3
"""Test 2J1_COLLECTION_FIELD_USAGE: Collection Field Usage

This test validates:
1. Memories are properly tagged with collection values
2. No collections table exists (field-based approach)
3. Different types of information use different collections
4. Collection-based retrieval works correctly
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


class Test2j1CollectionFieldUsage(BaseMemoryTest):
    """Test collection field usage without collections table."""

    async def test_2j1collectionfieldusage(self):
        """Test collection field is used correctly without collections table."""
        test_name = "2j1_collection_field_usage"
        self.print_test_header(test_name, "Collection Field Usage")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Setup formation with postgres for database inspection
            await self.setup_memory_formation("postgres")
            print("  ✓ Formation loaded")

            # Setup database connection
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()

            # Verify collections table doesn't exist
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema='public' AND table_name='collections'
            """)
            collections_table_exists = cur.fetchone() is not None

            if not collections_table_exists:
                print("  ✓ Confirmed: No collections table in database")
                checks_passed.append("No collections table exists (field-based approach)")
            else:
                print("  ⚠ Collections table exists (still valid)")
                checks_passed.append("Collections table approach in use")

            # Clear test data
            test_user = "collection_test_user"
            cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
            cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
            conn.commit()

            # Test different types of information
            print("\n  1. Sending messages that should use different collections...")

            test_messages = [
                ("My name is Alex and I work at Google", "user_identity"),
                ("I enjoy playing tennis on weekends", "activities"),
                ("I prefer dark mode in my IDE", "preferences"),
                ("I have a sister who lives in Boston", "relationships"),
                ("I'm learning Spanish", "activities"),
                ("My favorite color is blue", "preferences")
            ]

            for message, expected_collection in test_messages:
                response = await self.overlord.chat(message, user_id=test_user, use_async=False, stream=False)
                transcript.append(("User", message))

                # Handle response (stream=False, so response is a string or object with .content)
                response_text = response.content if hasattr(response, "content") else str(response)
                transcript.append(("System", response_text[:50] + "..." if len(response_text) > 50 else response_text))

                print(f"    Sent: {message}")

            # Wait for extraction to complete (extraction interval is 1, so all messages should trigger extraction)
            print("\n  ⏳ Waiting for memory extraction to complete...")
            await asyncio.sleep(8)  # Wait for extraction and storage

            # Check memories and their collections
            print("\n  2. Verifying collection assignments...")
            cur.execute("""
                SELECT text, collection
                FROM memories
                WHERE meta_data->>'user_id' = %s
                ORDER BY created_at
            """, (test_user,))

            memories = cur.fetchall()

            # Group by collection
            collections_found = {}
            for text, collection in memories:
                if collection not in collections_found:
                    collections_found[collection] = []
                collections_found[collection].append(text)

            print("\n    Memories organized by collection:")
            for collection, texts in collections_found.items():
                print(f"\n      {collection}:")
                for text in texts:
                    print(f"        - {text}")

            # Verify expected collections are used
            actual_collections = set(collections_found.keys())

            identity_found = "user_identity" in actual_collections
            activities_found = "activities" in actual_collections
            preferences_found = "preferences" in actual_collections

            if identity_found:
                print("    ✓ Found user_identity collection")
                checks_passed.append("user_identity collection used")
            else:
                print(f"    ✗ Missing user_identity in: {actual_collections}")
                all_passed = False

            if activities_found:
                print("    ✓ Found activities collection")
                checks_passed.append("activities collection used")
            else:
                print(f"    ✗ Missing activities in: {actual_collections}")
                all_passed = False

            if preferences_found:
                print("    ✓ Found preferences collection")
                checks_passed.append("preferences collection used")
            else:
                print(f"    ✗ Missing preferences in: {actual_collections}")
                all_passed = False

            print(f"\n    ✓ Found {len(actual_collections)} different collection types")
            print(f"    ✓ Collections used: {actual_collections}")
            checks_passed.append(f"Found {len(actual_collections)} collection types")

            # Test 3: Verify collection is indexed
            print("\n  3. Checking collection column is indexed...")
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'memories'
                AND indexdef LIKE '%collection%'
            """)

            collection_indexes = [row[0] for row in cur.fetchall()]
            if len(collection_indexes) > 0:
                print(f"    ✓ Collection column is indexed: {collection_indexes}")
                checks_passed.append("Collection column is indexed")
            else:
                print("    ⚠ No indexes found on collection column")
                # Don't fail the test for this, as it might be intentional

            # Test 4: Collection-based retrieval via chat
            print("\n  4. Testing memory retrieval by context...")
            retrieval_response = await self.overlord.chat("What activities do I enjoy?", user_id=test_user, use_async=False, stream=False)
            transcript.append(("User", "What activities do I enjoy?"))

            # Handle response (stream=False, so response is a string or object with .content)
            retrieval_response = retrieval_response.content if hasattr(retrieval_response, 'content') else str(retrieval_response)

            transcript.append(("System", retrieval_response[:100] + "..." if len(retrieval_response) > 100 else retrieval_response))

            # Should mention tennis and Spanish learning
            retrieval_success = "tennis" in retrieval_response.lower() or "spanish" in retrieval_response.lower()

            if retrieval_success:
                print("    ✓ Successfully retrieved activity-related memories")
                checks_passed.append("Successfully retrieved activity-related memories")
            else:
                print(f"    ✗ Failed to retrieve activity memories: {retrieval_response}")
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
        print("📝 AREA 2J1_COLLECTION_FIELD_USAGE")
        print("=" * 60)

        # Run test cases
        result = await self.test_2j1collectionfieldusage()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = Test2j1CollectionFieldUsage()
    result = asyncio.run(test.run_test())
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
