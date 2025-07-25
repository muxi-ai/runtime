#!/usr/bin/env python3
"""
Test 2I1: Natural Language Memory Extraction
Verify memories are stored as sentences, not key-value pairs
"""
import sys
import os
sys.path.insert(0, '.')
import asyncio
import psycopg2
from datetime import datetime
from src.muxi.formation.formation import Formation


async def test_natural_language_extraction():
    """Test that memories are extracted and stored in natural language format."""
    print("\n=== Test 2I1: Natural Language Memory Extraction ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()

    # Clear test data
    test_user = "natural_lang_test_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()

    formation = Formation()
    await formation.load("test-formations/formation-memory/formation-postgres.yaml")
    overlord = await formation.start_overlord()

    current_year = datetime.now().year

    # Test 1: Basic name and age extraction
    print("1. Testing name and age extraction...")
    await overlord.chat("My name is Sarah and I'm 28 years old", user_id=test_user, use_async=False)
    await asyncio.sleep(5)  # Wait for extraction

    # Check memories in database
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at DESC
    """, (test_user,))

    memories = cur.fetchall()
    memory_texts = [mem[0] for mem in memories]

    # Verify natural language format
    assert any("The user's name is Sarah" in text for text in memory_texts), \
        f"Expected natural language name format, got: {memory_texts}"

    # Verify age converted to birth year
    expected_birth_year = current_year - 28
    assert any(f"Was born in {expected_birth_year}" in text for text in memory_texts), \
        f"Expected birth year {expected_birth_year}, got: {memory_texts}"

    print("✓ Name stored as: 'The user's name is Sarah'")
    print(f"✓ Age converted to: 'Was born in {expected_birth_year}'")

    # Test 2: Complex sentence extraction
    print("\n2. Testing complex information extraction...")
    await overlord.chat("I work at DataCorp as a senior data scientist and I love hiking", user_id=test_user
    , use_async=False)
    await asyncio.sleep(5)

    # Wait a bit more for extraction to complete
    await asyncio.sleep(2)

    # Get all memories for this user
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at DESC
    """, (test_user,))

    new_memories = cur.fetchall()
    all_memories = memories + new_memories
    all_texts = [mem[0] for mem in all_memories]

    # Should have extracted facts from both messages
    assert any("DataCorp" in text for text in all_texts), \
        f"Expected company name extraction, got: {all_texts}"
    assert any("data scientist" in text for text in all_texts), \
        f"Expected job title extraction, got: {all_texts}"
    assert any("hiking" in text for text in all_texts), \
        f"Expected hobby extraction, got: {all_texts}"

    print("✓ Extracted company, job title, and hobby as natural sentences")

    # Test 3: Verify no key-value format
    print("\n3. Verifying no key-value pairs...")
    for text, _ in all_memories:
        assert ":" not in text or "The user" in text, \
            f"Found key-value format instead of natural language: {text}"
        assert not text.startswith("name:") and not text.startswith("age:"), \
            f"Found key-value format: {text}"

    print("✓ All memories stored as natural sentences (no key:value format)")

    # Test 4: Verify collection assignments
    print("\n4. Checking collection assignments...")
    collections = {mem[1] for mem in all_memories}
    assert "user_identity" in collections, f"Missing user_identity collection: {collections}"
    assert len(collections) > 1, f"Expected multiple collections, got: {collections}"

    print(f"✓ Memories organized into collections: {collections}")

    cur.close()
    conn.close()

    await formation.shutdown()

    print("\n✅ Natural language extraction test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_natural_language_extraction())
    os._exit(0)
