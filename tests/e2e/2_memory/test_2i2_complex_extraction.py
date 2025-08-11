#!/usr/bin/env python3
"""
Test 2I2: Complex Multi-Fact Extraction
Test extraction of multiple facts from a single complex message
"""
import sys
from pathlib import Path
import os
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import asyncio
import psycopg2
from muxi.formation.formation import Formation


async def test_complex_extraction():
    """Test extraction of multiple facts from complex messages."""
    print("\n=== Test 2I2: Complex Multi-Fact Extraction ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()

    # Clear test data
    test_user = "complex_extraction_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()

    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml")
    overlord = await formation.start_overlord()

    # Test 1: CEO and company information
    print("1. Testing complex sentence with multiple facts...")
    await overlord.chat(
        "I'm the CEO of TechStart, a company that builds AI tools for healthcare",
        user_id=test_user
    , use_async=False)
    await asyncio.sleep(5)  # Wait for extraction

    # Check extracted memories
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at ASC
    """, (test_user,))

    memories = cur.fetchall()
    memory_texts = [mem[0] for mem in memories]
    all_text = " ".join(memory_texts)

    # Verify all facts were extracted
    facts_to_verify = [
        ("CEO", "job title"),
        ("TechStart", "company name"),
        ("AI tools", "product/service"),
        ("healthcare", "industry")
    ]

    for fact, description in facts_to_verify:
        assert fact in all_text, f"Missing {description} '{fact}' in: {memory_texts}"
        print(f"✓ Extracted {description}: {fact}")

    # Test 2: Multiple facts in different domains
    print("\n2. Testing multiple domain extraction...")
    await overlord.chat(
        "I live in San Francisco, have two kids, and enjoy playing chess in my free time",
        user_id=test_user
    , use_async=False)
    await asyncio.sleep(5)

    # Get all memories for this user to see what was extracted
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at ASC
    """, (test_user,))

    all_memories_now = cur.fetchall()
    new_memories = all_memories_now[len(memories):]  # Get only the new ones
    new_texts = [mem[0] for mem in new_memories]
    all_new_text = " ".join(new_texts)

    print(f"\nAll memories after second message ({len(all_memories_now)} total):")
    for i, (text, coll) in enumerate(all_memories_now):
        print(f"  {i+1}. [{coll}] {text}")

    # Verify location, family, and hobby extraction
    assert "San Francisco" in all_new_text, f"Missing location in: {new_texts}"
    assert "two kids" in all_new_text or "2 kids" in all_new_text, f"Missing family info in: {new_texts}"
    assert "chess" in all_new_text, f"Missing hobby in: {new_texts}"

    print("✓ Extracted location: San Francisco")
    print("✓ Extracted family: two kids")
    print("✓ Extracted hobby: chess")

    # Test 3: Verify appropriate collections
    print("\n3. Checking collection diversity...")
    collections_used = {mem[1] for mem in all_memories_now}

    expected_collections = {"user_identity", "relationships", "activities", "preferences"}
    found_collections = collections_used.intersection(expected_collections)

    assert len(found_collections) >= 2, \
        f"Expected multiple collection types, found: {collections_used}"

    print(f"✓ Facts distributed across collections: {collections_used}")

    # Test 4: Natural language format preserved
    print("\n4. Verifying natural language format...")
    for text, _ in all_memories_now:
        # Should be complete sentences, not fragments
        assert len(text.split()) >= 3, f"Memory too short/fragmented: {text}"
        # Should not be raw extraction without context
        assert not text.startswith("CEO of"), f"Missing sentence structure: {text}"

    print("✓ All memories stored as complete natural sentences")

    cur.close()
    conn.close()

    await formation.shutdown()

    print("\n✅ Complex extraction test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_complex_extraction())
    os._exit(0)
