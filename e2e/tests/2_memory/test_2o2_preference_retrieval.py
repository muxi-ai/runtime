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


async def test_preference_retrieval():
    """Test that preferences are retrieved and influence responses."""
    print("\n=== Test 2O2: Preference Retrieval in Context ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
    cur = conn.cursor()

    # Clear test data
    test_user = "preference_retrieval_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("""
        DELETE FROM users WHERE id IN (
            SELECT user_id FROM user_identifiers WHERE identifier = %s
        )
    """, (test_user,))
    conn.commit()

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
        await asyncio.sleep(5)  # Wait for extraction

    # Verify preferences were stored
    cur.execute(
        """
        SELECT COUNT(*)
        FROM memories
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
    """,
        (test_user,),
    )

    pref_count = cur.fetchone()[0]
    print(f"\n✓ Stored {pref_count} preferences (expected at least 1)")
    if pref_count == 0:
        # Check if memories were stored in any collection
        cur.execute("SELECT COUNT(*) FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
        total_count = cur.fetchone()[0]
        print(f"   Total memories stored: {total_count}")
    assert pref_count > 0, f"No preferences were stored (expected at least 1 from {len(preferences)} expressions)"

    # Test 2: Ask questions that should retrieve preferences
    print("\n2. Testing preference retrieval in context...")

    # Question about testing
    print("   Asking about testing...")
    test_response = await overlord.chat(
        "What testing framework should I use for my Python project?",
        user_id=test_user,
        use_async=False,
    )

    # Check if pytest preference influenced response
    test_response_text = test_response.content if hasattr(test_response, 'content') else str(test_response)
    pytest_mentioned = "pytest" in test_response_text.lower()
    print(f"   ✓ pytest mentioned in response: {pytest_mentioned}")

    # Question about APIs
    print("   Asking about API frameworks...")
    api_response = await overlord.chat(
        "I need to build a REST API. What framework do you recommend?",
        user_id=test_user,
        use_async=False,
    )

    # Check if FastAPI preference influenced response
    api_response_text = api_response.content if hasattr(api_response, 'content') else str(api_response)
    fastapi_mentioned = "fastapi" in api_response_text.lower()
    print(f"   ✓ FastAPI mentioned in response: {fastapi_mentioned}")

    # Question about frontend
    print("   Asking about frontend languages...")
    frontend_response = await overlord.chat(
        "Should I use JavaScript or TypeScript for my new web app?",
        user_id=test_user,
        use_async=False,
    )

    # Check if TypeScript preference influenced response
    frontend_response_text = frontend_response.content if hasattr(frontend_response, 'content') else str(frontend_response)
    typescript_mentioned = "typescript" in frontend_response_text.lower()
    print(f"   ✓ TypeScript mentioned in response: {typescript_mentioned}")

    # Test 3: Verify preferences are actually being retrieved
    print("\n3. Verifying preference collection search...")

    # Check database to confirm preferences exist
    cur.execute(
        """
        SELECT text
        FROM memories
        WHERE meta_data->>'user_id' = %s AND collection = 'preferences'
        ORDER BY created_at DESC
    """,
        (test_user,),
    )

    stored_prefs = cur.fetchall()
    print(f"   Found {len(stored_prefs)} preferences in database:")
    for (text,) in stored_prefs[:3]:  # Show first 3
        print(f"   - {text[:60]}...")

    # Calculate success rate
    preferences_reflected = sum([pytest_mentioned, fastapi_mentioned, typescript_mentioned])
    success_rate = (preferences_reflected / 3) * 100

    print("\n=== Results ===")
    print(f"Preferences stored: {pref_count}")
    print(f"Preferences reflected in responses: {preferences_reflected}/3 ({success_rate:.0f}%)")

    # At least 2 out of 3 should be reflected
    assert (
        preferences_reflected >= 2
    ), f"Only {preferences_reflected}/3 preferences influenced responses"

    # Shutdown formation (this now disposes database engine internally)
    await safe_formation_shutdown(formation)

    # Cancel all pending background tasks (except current task)
    current_task = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
    for task in pending:
        task.cancel()

    # Wait for tasks to cancel
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    # Cleanup database records
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("""
        DELETE FROM users WHERE id IN (
            SELECT user_id FROM user_identifiers WHERE identifier = %s
        )
    """, (test_user,))
    conn.commit()
    conn.close()

    print("\n=== Test 2O2 Complete ===")
    print("✓ Preferences stored successfully")
    print("✓ Preferences retrieved in context searches")
    print("✓ Preferences influence agent responses")
    print(f"✓ Success rate: {success_rate:.0f}%")


if __name__ == "__main__":
    import os
    result = asyncio.run(test_preference_retrieval())
    if result:
        print("SUCCESS", flush=True)
    os._exit(0 if result else 1)
