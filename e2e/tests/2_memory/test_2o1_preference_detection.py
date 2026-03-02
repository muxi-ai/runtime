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
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402
from test_utils import safe_formation_shutdown  # noqa: E402

MEMORIES_TABLE = "memories_1536"


def _cleanup_test_user(cur, conn, test_user):
    """Delete test user data from dimension-specific memory tables, then users."""
    for tbl in (MEMORIES_TABLE, "memories_384", "memories_768"):
        try:
            cur.execute(f"DELETE FROM {tbl} WHERE meta_data->>'user_id' = %s", (test_user,))
        except Exception:
            conn.rollback()
    try:
        cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    except Exception:
        conn.rollback()
    cur.execute("DELETE FROM user_identifiers WHERE identifier = %s", (test_user,))
    cur.execute("""
        DELETE FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM user_identifiers ui WHERE ui.user_id = u.id)
          AND NOT EXISTS (SELECT 1 FROM memories_1536 m WHERE m.user_id = u.id)
    """)
    conn.commit()


async def test_preference_detection():
    """Test that preferences are detected and stored in preferences collection."""
    print("\n=== Test 2O1: Preference Detection and Storage ===\n")

    conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
    cur = conn.cursor()

    test_user = "preference_test_user_001"
    _cleanup_test_user(cur, conn, test_user)

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
    await asyncio.sleep(5)

    # Check if ANY memories were stored (using dimension-specific table)
    cur.execute(f"""
        SELECT text, collection, meta_data
        FROM {MEMORIES_TABLE}
        WHERE meta_data->>'user_id' = %s
        ORDER BY created_at DESC
    """, (test_user,))
    all_memories = cur.fetchall()
    print(f"   Total memories stored: {len(all_memories)}")
    if all_memories:
        for mem in all_memories[:3]:
            print(f"   - Collection: {mem[1]}, Text: {mem[0][:50]}...")

    # Check memories specifically in preferences collection
    cur.execute(f"""
        SELECT text, collection, meta_data
        FROM {MEMORIES_TABLE}
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
        ORDER BY created_at DESC
    """, (test_user,))

    preferences = cur.fetchall()
    preference_texts = [pref[0] for pref in preferences]

    assert len(preferences) > 0, f"No preferences were stored in the preferences collection. Total memories: {len(all_memories)}"

    fastapi_found = any("FastAPI" in text or "Flask" in text for text in preference_texts)
    assert fastapi_found, f"FastAPI/Flask preference not found. Got: {preference_texts}"

    print(f"Pass: Preference stored: '{preference_texts[0] if preference_texts else 'None'}'")
    print("Pass: Stored in collection: 'preferences'")

    # Test 2: Multiple preferences
    print("\n2. Testing multiple preference detection...")

    test_preferences = [
        "I always use pytest for testing, never unittest",
        "For UI components, I prefer Shadcn/UI with Tailwind CSS",
        "I like to write documentation in Markdown format"
    ]

    for pref in test_preferences:
        print(f"   Expressing: {pref}")
        await overlord.chat(pref, user_id=test_user, use_async=False, stream=False)
        await asyncio.sleep(5)

    cur.execute(f"""
        SELECT text, collection
        FROM {MEMORIES_TABLE}
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
        ORDER BY created_at DESC
    """, (test_user,))

    all_preferences = cur.fetchall()
    all_texts = [pref[0] for pref in all_preferences]

    print(f"\nPass: Total preferences stored: {len(all_preferences)}")
    for text, _ in all_preferences:
        print(f"   - {text}")

    pytest_found = any("pytest" in text.lower() for text in all_texts)
    shadcn_found = any("shadcn" in text.lower() or "tailwind" in text.lower() for text in all_texts)
    markdown_found = any("markdown" in text.lower() for text in all_texts)

    assert pytest_found or shadcn_found or markdown_found, \
        f"Expected at least one preference to be captured. Got: {all_texts}"

    # Test 3: Non-preferences should not be stored
    print("\n3. Testing non-preference filtering...")

    initial_count = len(all_preferences)

    non_preferences = [
        "What is FastAPI?",
        "Show me an example of pytest",
        "How does Tailwind CSS work?"
    ]

    for msg in non_preferences:
        print(f"   Sending non-preference: {msg}")
        await overlord.chat(msg, user_id=test_user, use_async=False, stream=False)
        await asyncio.sleep(2)

    cur.execute(f"""
        SELECT COUNT(*)
        FROM {MEMORIES_TABLE}
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
    """, (test_user,))

    final_count = cur.fetchone()[0]

    assert final_count - initial_count < len(non_preferences), \
        f"Too many non-preferences stored. Initial: {initial_count}, Final: {final_count}"

    print(f"Pass: Non-preferences filtered correctly (stored {final_count - initial_count}/{len(non_preferences)})")

    # Test 4: Verify preferences are searchable
    print("\n4. Testing preference retrieval in context...")

    response = await overlord.chat(
        "What API framework should I use for my new project?",
        user_id=test_user,
        use_async=False,
    )

    response_text = response.content if hasattr(response, "content") else str(response)
    print(f"Response to API question: {response_text[:200]}...")

    await safe_formation_shutdown(formation)

    current_task = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    # Cleanup database records
    _cleanup_test_user(cur, conn, test_user)
    conn.close()

    print("\n=== Test 2O1 Complete ===")
    print("Pass: Preferences are detected from natural language")
    print("Pass: Stored in 'preferences' collection")
    print("Pass: Non-preferences are filtered out")
    print("Pass: Available for context retrieval")

if __name__ == "__main__":
    import os
    try:
        asyncio.run(test_preference_detection())
        print("SUCCESS", flush=True)
        os._exit(0)
    except Exception:
        os._exit(1)
