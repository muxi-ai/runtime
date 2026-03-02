#!/usr/bin/env python3
"""
Test 2O2: Preference Retrieval in Context
Verify stored preferences are included in context for relevant queries
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


async def test_preference_retrieval():
    """Test that preferences are retrieved and influence responses."""
    print("\n=== Test 2O2: Preference Retrieval in Context ===\n")

    conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
    cur = conn.cursor()

    test_user = "preference_retrieval_user"
    _cleanup_test_user(cur, conn, test_user)

    formation = Formation()
    await formation.load(
        str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml")
    )
    overlord = await formation.start_overlord()

    # Test 1: Store multiple preferences
    print("1. Storing technology preferences...")
    preferences = [
        "I always use pytest for testing in Python projects",
        "For web APIs, I prefer FastAPI over Flask or Django",
        "I like TypeScript over JavaScript for frontend development",
    ]

    for pref in preferences:
        print(f"   Expressing: {pref[:50]}...")
        await overlord.chat(pref, user_id=test_user, use_async=False, stream=False)
        await asyncio.sleep(5)

    # Verify preferences were stored
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM {MEMORIES_TABLE}
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
    """,
        (test_user,),
    )

    pref_count = cur.fetchone()[0]
    print(f"\nPass: Stored {pref_count} preferences (expected at least 1)")
    if pref_count == 0:
        cur.execute(
            f"SELECT COUNT(*) FROM {MEMORIES_TABLE} WHERE meta_data->>'user_id' = %s",
            (test_user,),
        )
        total_count = cur.fetchone()[0]
        print(f"   Total memories stored: {total_count}")
    assert pref_count > 0, f"No preferences were stored (expected at least 1 from {len(preferences)} expressions)"

    # Test 2: Ask questions that should retrieve preferences
    print("\n2. Testing preference retrieval in context...")

    print("   Asking about testing...")
    test_response = await overlord.chat(
        "What testing framework should I use for my Python project?",
        user_id=test_user,
        use_async=False,
    )

    test_response_text = test_response.content if hasattr(test_response, 'content') else str(test_response)
    pytest_mentioned = "pytest" in test_response_text.lower()
    print(f"   Pass: pytest mentioned in response: {pytest_mentioned}")

    print("   Asking about API frameworks...")
    api_response = await overlord.chat(
        "I need to build a REST API. What framework do you recommend?",
        user_id=test_user,
        use_async=False,
    )

    api_response_text = api_response.content if hasattr(api_response, 'content') else str(api_response)
    fastapi_mentioned = "fastapi" in api_response_text.lower()
    print(f"   Pass: FastAPI mentioned in response: {fastapi_mentioned}")

    print("   Asking about frontend languages...")
    frontend_response = await overlord.chat(
        "Should I use JavaScript or TypeScript for my new web app?",
        user_id=test_user,
        use_async=False,
    )

    frontend_response_text = frontend_response.content if hasattr(frontend_response, 'content') else str(frontend_response)
    typescript_mentioned = "typescript" in frontend_response_text.lower()
    print(f"   Pass: TypeScript mentioned in response: {typescript_mentioned}")

    # Test 3: Verify preferences are actually in the DB
    print("\n3. Verifying preference collection search...")

    cur.execute(
        f"""
        SELECT text
        FROM {MEMORIES_TABLE}
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
        ORDER BY created_at DESC
    """,
        (test_user,),
    )

    stored_prefs = cur.fetchall()
    print(f"   Found {len(stored_prefs)} preferences in database:")
    for (text,) in stored_prefs[:3]:
        print(f"   - {text[:60]}...")

    preferences_reflected = sum([pytest_mentioned, fastapi_mentioned, typescript_mentioned])
    success_rate = (preferences_reflected / 3) * 100

    print("\n=== Results ===")
    print(f"Preferences stored: {pref_count}")
    print(f"Preferences reflected in responses: {preferences_reflected}/3 ({success_rate:.0f}%)")

    assert (
        preferences_reflected >= 2
    ), f"Only {preferences_reflected}/3 preferences influenced responses"

    await safe_formation_shutdown(formation)

    current_task = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    _cleanup_test_user(cur, conn, test_user)
    conn.close()

    print("\n=== Test 2O2 Complete ===")
    print("Pass: Preferences stored successfully")
    print("Pass: Preferences retrieved in context searches")
    print("Pass: Preferences influence agent responses")
    print(f"Pass: Success rate: {success_rate:.0f}%")


if __name__ == "__main__":
    import os
    try:
        asyncio.run(test_preference_retrieval())
        print("SUCCESS", flush=True)
        os._exit(0)
    except Exception:
        os._exit(1)
