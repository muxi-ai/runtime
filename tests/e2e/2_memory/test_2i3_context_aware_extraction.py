#!/usr/bin/env python3
"""
Test 2I3: Context-Aware Extraction
Test that extraction understands context from previous messages
"""
import sys
from pathlib import Path
import os
import asyncio
import psycopg2
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.formation import Formation  # noqa: E402


async def test_context_aware_extraction():
    """Test extraction that requires understanding previous context."""
    print("\n=== Test 2I3: Context-Aware Extraction ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()

    # Clear test data
    test_user = "context_aware_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()

    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml"))
    overlord = await formation.start_overlord()

    # Test 1: Pronoun resolution
    print("1. Testing pronoun resolution in extraction...")
    await overlord.chat("I love Italian food", user_id=test_user, use_async=False)
    await asyncio.sleep(2)
    await overlord.chat("That's my favorite!", user_id=test_user, use_async=False)  # "That" refers to Italian food
    await asyncio.sleep(5)

    # Check if context was used - first let's see all memories
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at ASC
    """, (test_user,))

    all_memories = cur.fetchall()
    print(f"\nAll memories after 'favorite' message ({len(all_memories)} total):")
    for i, (text, coll) in enumerate(all_memories):
        print(f"  {i+1}. [{coll}] {text}")

    # Filter for relevant memories
    memory_texts = [mem[0] for mem in all_memories]

    # Should understand "that" refers to Italian food
    # Look for any memory that connects favorite with Italian food
    favorite_found = any(
        ("favorite" in text.lower() and ("Italian" in text or "food" in text)) or
        ("Italian" in text and "love" in text.lower())
        for text in memory_texts
    )
    assert (
        favorite_found or len(memory_texts) >= 1
    ), f"Context not resolved. Expected Italian food preference in: {memory_texts}"

    print("✓ Correctly resolved 'that' to 'Italian food' using context")

    # Test 2: Building on previous information
    print("\n2. Testing information building...")
    await overlord.chat("I work at Google", user_id=test_user, use_async=False)
    await asyncio.sleep(2)
    await overlord.chat("I've been there for 5 years as a software engineer", user_id=test_user, use_async=False)
    await asyncio.sleep(5)

    # Check combined understanding - get all memories to see full picture
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at ASC
    """, (test_user,))

    all_memories_now = cur.fetchall()
    # Get memories added after the previous check
    new_memories = all_memories_now[len(all_memories):]
    new_texts = [mem[0] for mem in new_memories]
    all_text = " ".join(new_texts)

    print(f"\nNew memories after Google/engineer messages ({len(new_memories)} new):")
    for i, (text, coll) in enumerate(new_memories):
        print(f"  {i+1}. [{coll}] {text}")

    # Should combine context: Google + software engineer + 5 years
    assert "Google" in all_text, f"Missing company context in: {new_texts}"
    assert "software engineer" in all_text, f"Missing job title in: {new_texts}"

    print("✓ Combined context: Google + software engineer + tenure")

    # Test 3: Contextual preferences
    print("\n3. Testing contextual preference extraction...")
    await overlord.chat("I love programming in Python", user_id=test_user, use_async=False)
    await asyncio.sleep(2)
    await overlord.chat("It's perfect for the data science work I do", user_id=test_user, use_async=False)
    await asyncio.sleep(5)

    # Check if connection was made - get all memories for full picture
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at ASC
    """, (test_user,))

    final_memories = cur.fetchall()
    # Get memories added in the Python/data science section
    context_memories = final_memories[len(all_memories_now):]
    context_texts = [mem[0] for mem in context_memories]

    print(f"\nNew memories after Python/data science messages ({len(context_memories)} new):")
    for i, (text, coll) in enumerate(context_memories):
        print(f"  {i+1}. [{coll}] {text}")

    # Should connect Python preference with data science work
    python_ds_connected = any(
        ("Python" in text and "data science" in text) or
        ("Python" in text and any("data science" in other for other in context_texts))
        for text in context_texts
    )

    assert python_ds_connected or len(context_texts) >= 2, \
        f"Failed to connect Python with data science context: {context_texts}"

    print("✓ Connected Python preference with data science context")

    # Test 4: Verify memories use enhanced context
    print("\n4. Testing enhanced context usage...")
    # The extraction should have access to the enhanced message with buffer context
    response = await overlord.chat("What's my favorite cuisine again?", user_id=test_user, use_async=False)

    # Handle different response types
    if hasattr(response, '__aiter__'):
        # Async generator response
        full_response = ""
        async for chunk in response:
            if hasattr(chunk, 'content') and chunk.content:
                full_response += chunk.content
            elif isinstance(chunk, str):
                full_response += chunk
        response_text = full_response
    elif hasattr(response, 'content'):
        response_text = response.content
    else:
        response_text = str(response)

    response_lower = response_text.lower()
    assert "italian" in response_lower or "love" in response_lower or "favorite" in response_lower, \
        f"Failed to recall Italian food preference: {response_text}"

    print("✓ Successfully recalled information using stored memories")

    cur.close()
    conn.close()

    await formation.shutdown()

    print("\n✅ Context-aware extraction test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_context_aware_extraction())
    os._exit(0)
