#!/usr/bin/env python3
"""
Test 2J1: Collection Field Usage
Test that memories are properly tagged with collection values (no collections table)
"""
import sys
from pathlib import Path
import os
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import asyncio
import psycopg2
from muxi.formation.formation import Formation


async def test_collection_field_usage():
    """Test collection field is used correctly without collections table."""
    print("\n=== Test 2J1: Collection Field Usage ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()

    # Verify collections table doesn't exist
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name='collections'
    """)
    assert cur.fetchone() is None, "Collections table should not exist!"
    print("✓ Confirmed: No collections table in database")

    # Clear test data
    test_user = "collection_test_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()

    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml")
    overlord = await formation.start_overlord()

    # Test different types of information
    print("\n1. Sending messages that should use different collections...")

    test_messages = [
        ("My name is Alex and I work at Google", "user_identity"),
        ("I enjoy playing tennis on weekends", "activities"),
        ("I prefer dark mode in my IDE", "preferences"),
        ("I have a sister who lives in Boston", "relationships"),
        ("I'm learning Spanish", "activities"),
        ("My favorite color is blue", "preferences")
    ]

    for message, expected_collection in test_messages:
        await overlord.chat(message, user_id=test_user, use_async=False)
        await asyncio.sleep(3)
        print(f"  Sent: {message}")

    # Check memories and their collections
    print("\n2. Verifying collection assignments...")
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

    print("\nMemories organized by collection:")
    for collection, texts in collections_found.items():
        print(f"\n  {collection}:")
        for text in texts:
            print(f"    - {text}")

    # Verify expected collections are used
    expected_collections = {"user_identity", "activities", "preferences", "relationships"}
    actual_collections = set(collections_found.keys())

    assert "user_identity" in actual_collections, f"Missing user_identity in: {actual_collections}"
    assert "activities" in actual_collections, f"Missing activities in: {actual_collections}"
    assert "preferences" in actual_collections, f"Missing preferences in: {actual_collections}"

    print(f"\n✓ Found {len(actual_collections)} different collection types")
    print(f"✓ Collections used: {actual_collections}")

    # Test 3: Verify collection is indexed
    print("\n3. Checking collection column is indexed...")
    cur.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'memories'
        AND indexdef LIKE '%collection%'
    """)

    collection_indexes = [row[0] for row in cur.fetchall()]
    assert len(collection_indexes) > 0, "No indexes found on collection column"
    print(f"✓ Collection column is indexed: {collection_indexes}")

    # Test 4: Collection-based retrieval via chat
    print("\n4. Testing memory retrieval by context...")
    response = await overlord.chat("What activities do I enjoy?", user_id=test_user, use_async=False)

    # Handle async generator response
    if hasattr(response, '__aiter__'):
        # It's a streaming response, collect it
        response_text = ""
        async for chunk in response:
            response_text += chunk
        response = response_text
    elif hasattr(response, 'content'):
        response = response.content

    # Should mention tennis and Spanish learning
    assert "tennis" in response.lower() or "spanish" in response.lower(), \
        f"Failed to retrieve activity memories: {response}"

    print("✓ Successfully retrieved activity-related memories")

    cur.close()
    conn.close()

    await formation.shutdown()

    print("\n✅ Collection field usage test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_collection_field_usage())
    os._exit(0)
