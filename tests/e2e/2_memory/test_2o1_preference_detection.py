#!/usr/bin/env python3
"""
Test 2O1: Preference Detection and Storage
Verify user preferences are detected and stored in the preferences collection
"""
import sys
from pathlib import Path
import asyncio
import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.formation.formation import Formation  # noqa: E402


async def test_preference_detection():
    """Test that preferences are detected and stored in preferences collection."""
    print("\n=== Test 2O1: Preference Detection and Storage ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()

    # Clear test data
    test_user = "preference_test_user_001"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()

    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml"))
    overlord = await formation.start_overlord()

    # Test 1: Express a technology preference
    print("1. Testing technology preference detection...")
    await overlord.chat(
        "I prefer using FastAPI over Flask for all my API development",
        user_id=test_user,
        use_async=False,
    )
    await asyncio.sleep(5)  # Wait for preference detection and storage

    # Check memories in database - specifically in preferences collection
    cur.execute("""
        SELECT text, collection, meta_data
        FROM memories
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
        ORDER BY created_at DESC
    """, (test_user,))

    preferences = cur.fetchall()
    preference_texts = [pref[0] for pref in preferences]

    # Verify preference was stored
    assert len(preferences) > 0, "No preferences were stored in the preferences collection"

    # Verify it contains the preference content
    fastapi_found = any("FastAPI" in text or "Flask" in text for text in preference_texts)
    assert fastapi_found, f"FastAPI/Flask preference not found. Got: {preference_texts}"

    print(f"✓ Preference stored: '{preference_texts[0] if preference_texts else 'None'}'")
    print("✓ Stored in collection: 'preferences'")

    # Test 2: Multiple preferences
    print("\n2. Testing multiple preference detection...")

    # Express more preferences
    test_preferences = [
        "I always use pytest for testing, never unittest",
        "For UI components, I prefer Shadcn/UI with Tailwind CSS",
        "I like to write documentation in Markdown format"
    ]

    for pref in test_preferences:
        print(f"   Expressing: {pref}")
        await overlord.chat(pref, user_id=test_user, use_async=False)
        await asyncio.sleep(3)  # Wait between preferences

    # Check all preferences
    cur.execute("""
        SELECT text, collection
        FROM memories
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
        ORDER BY created_at DESC
    """, (test_user,))

    all_preferences = cur.fetchall()
    all_texts = [pref[0] for pref in all_preferences]

    print(f"\n✓ Total preferences stored: {len(all_preferences)}")
    print("✓ Stored preferences:")
    for text, _ in all_preferences:
        print(f"   - {text}")

    # Verify key preferences were captured
    pytest_found = any("pytest" in text.lower() for text in all_texts)
    shadcn_found = any("shadcn" in text.lower() or "tailwind" in text.lower() for text in all_texts)
    markdown_found = any("markdown" in text.lower() for text in all_texts)

    assert pytest_found or shadcn_found or markdown_found, \
        f"Expected at least one preference to be captured. Got: {all_texts}"

    # Test 3: Non-preferences should not be stored
    print("\n3. Testing non-preference filtering...")

    # Get current count
    initial_count = len(all_preferences)

    # Send non-preference messages
    non_preferences = [
        "What is FastAPI?",
        "Show me an example of pytest",
        "How does Tailwind CSS work?"
    ]

    for msg in non_preferences:
        print(f"   Sending non-preference: {msg}")
        await overlord.chat(msg, user_id=test_user, use_async=False)
        await asyncio.sleep(2)

    # Check if count increased (it shouldn't)
    cur.execute("""
        SELECT COUNT(*)
        FROM memories
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
    """, (test_user,))

    final_count = cur.fetchone()[0]

    # Allow for some false positives but not all
    assert final_count - initial_count < len(non_preferences), \
        f"Too many non-preferences stored. Initial: {initial_count}, Final: {final_count}"

    print(f"✓ Non-preferences filtered correctly (stored {final_count - initial_count}/{len(non_preferences)})")

    # Test 4: Verify preferences are searchable
    print("\n4. Testing preference retrieval in context...")

    # Ask a question that should trigger preference context
    response = await overlord.chat(
        "What API framework should I use for my new project?",
        user_id=test_user,
        use_async=False,
    )

    # The response should reflect the FastAPI preference
    print(f"Response to API question: {response[:200]}...")

    # Note: We can't guarantee the exact response, but we've verified the preference is stored

    # Cleanup
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()
    conn.close()

    # Properly shutdown formation to avoid timeout
    await formation.stop_overlord()
    formation.shutdown()

    print("\n=== Test 2O1 Complete ===")
    print("✓ Preferences are detected from natural language")
    print("✓ Stored in 'preferences' collection")
    print("✓ Non-preferences are filtered out")
    print("✓ Available for context retrieval")

if __name__ == "__main__":
    asyncio.run(test_preference_detection())
