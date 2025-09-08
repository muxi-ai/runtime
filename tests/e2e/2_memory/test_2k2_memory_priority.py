#!/usr/bin/env python3
"""
Test 2K2: Memory Priority in Context Enhancement
Test that important long-term memories are prioritized over recent buffer noise
"""
import sys
from pathlib import Path
import os

import asyncio
import psycopg2
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.formation import Formation  # noqa: E402


async def test_memory_priority():
    """Test memory prioritization in context enhancement."""
    print("\n=== Test 2K2: Memory Priority in Context Enhancement ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()

    # Clear test data
    test_user = "priority_test_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()

    formation = Formation()
    await formation.load(
        str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml")
    )
    overlord = await formation.start_overlord()

    # Test 1: Important information extraction
    print("1. Establishing important long-term memories...")

    # Critical health information
    await overlord.chat(
        "I'm allergic to peanuts - this is very important!", user_id=test_user, use_async=False
    )
    await asyncio.sleep(3)

    # Other important facts
    await overlord.chat(
        "I'm diabetic and need to monitor sugar intake", user_id=test_user, use_async=False
    )
    await asyncio.sleep(3)

    await overlord.chat("I'm vegetarian for ethical reasons", user_id=test_user, use_async=False)
    await asyncio.sleep(3)

    print("✓ Stored critical dietary and health information")

    # Test 2: Fill buffer with noise
    print("\n2. Filling buffer with unrelated messages...")

    for i in range(15):
        await overlord.chat(
            f"Random conversation {i} about the weather, sports, and other topics",
            user_id=test_user,
            use_async=False,
        )
        await asyncio.sleep(0.5)

    print("✓ Added 15 noise messages to buffer")

    # Test 3: Query about important information
    print("\n3. Testing retrieval of important information despite noise...")

    response = await overlord.chat(
        "Do I have any dietary restrictions or health concerns?", user_id=test_user, use_async=False
    )

    # Handle different response types
    if hasattr(response, "__aiter__"):
        # Async generator response
        full_response = ""
        async for chunk in response:
            if hasattr(chunk, "content") and chunk.content:
                full_response += chunk.content
            elif isinstance(chunk, str):
                full_response += chunk
        response_text = full_response
    elif hasattr(response, "content"):
        response_text = response.content
    else:
        response_text = str(response)

    # Should prioritize health-related memories
    important_terms = ["peanut", "allerg", "diabet", "sugar", "vegetarian"]
    found_terms = [term for term in important_terms if term in response_text.lower()]

    assert (
        len(found_terms) >= 2
    ), f"Failed to retrieve important health info. Found only: {found_terms} in: {response_text}"

    print(f"✓ Retrieved important memories: {found_terms}")

    # Test 4: Specific allergy query
    print("\n4. Testing specific health query...")

    response = await overlord.chat(
        "Can I eat this peanut butter sandwich?", user_id=test_user, use_async=False
    )

    # Handle different response types
    if hasattr(response, "__aiter__"):
        # Async generator response
        full_response = ""
        async for chunk in response:
            if hasattr(chunk, "content") and chunk.content:
                full_response += chunk.content
            elif isinstance(chunk, str):
                full_response += chunk
        response_text = full_response
    elif hasattr(response, "content"):
        response_text = response.content
    else:
        response_text = str(response)

    # MUST warn about peanut allergy
    assert (
        "no" in response_text.lower()
        or "allerg" in response_text.lower()
        or "avoid" in response_text.lower()
    ), f"Failed to warn about peanut allergy: {response_text}"

    print("✓ Correctly warned about peanut allergy")

    # Test 5: Verify memory search prioritization
    print("\n5. Checking memory search relevance...")

    # Query memories directly to verify search
    cur.execute(
        """
        SELECT text, collection,
               ts_rank(to_tsvector('english', text),
                       to_tsquery('english', 'peanut | allergy')) as rank
        FROM memories
        WHERE meta_data->>'user_id' = %s
        AND to_tsvector('english', text) @@ to_tsquery('english', 'peanut | allergy')
        ORDER BY rank DESC
    """,
        (test_user,),
    )

    search_results = cur.fetchall()

    assert len(search_results) > 0, "Failed to find allergy memory via search"
    assert search_results[0][2] > 0, "Allergy memory should have high relevance score"

    print(f"✓ Allergy memory has relevance score: {search_results[0][2]}")

    # Test 6: Context window management
    print("\n6. Testing context window with priority...")

    # Add more important information
    await overlord.chat(
        "My blood type is O-negative, important for emergencies", user_id=test_user, use_async=False
    )
    await asyncio.sleep(3)

    # Query should still include all critical info
    response = await overlord.chat(
        "What critical medical information should a doctor know about me?",
        user_id=test_user,
        use_async=False,
    )

    # Handle different response types
    if hasattr(response, "__aiter__"):
        # Async generator response
        full_response = ""
        async for chunk in response:
            if hasattr(chunk, "content") and chunk.content:
                full_response += chunk.content
            elif isinstance(chunk, str):
                full_response += chunk
        response_text = full_response
    elif hasattr(response, "content"):
        response_text = response.content
    else:
        response_text = str(response)

    medical_info = ["allerg", "peanut", "diabet", "vegetarian", "o-negative", "blood"]
    found_medical = [info for info in medical_info if info in response_text.lower()]

    assert (
        len(found_medical) >= 3
    ), f"Missing critical medical info. Found: {found_medical} in: {response_text}"

    print(f"✓ Medical summary includes: {found_medical}")

    cur.close()
    conn.close()

    await formation.shutdown()

    print("\n✅ Memory priority test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_memory_priority())
    os._exit(0)
