#!/usr/bin/env python3
"""
Test Group 2O: Preference System
Testing the ultra-simple preference detection and storage system.
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
    # Also try legacy table if it exists
    try:
        cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    except Exception:
        conn.rollback()
    cur.execute(
        "DELETE FROM user_identifiers WHERE identifier = %s", (test_user,)
    )
    # Now safe to delete orphaned users
    cur.execute("""
        DELETE FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM user_identifiers ui WHERE ui.user_id = u.id)
          AND NOT EXISTS (SELECT 1 FROM memories_1536 m WHERE m.user_id = u.id)
    """)
    conn.commit()


async def test_2o1_preference_detection_and_storage():
    """Test that user preferences are detected and stored in the preferences collection."""
    print("\n=== Test 2O1: Preference Detection and Storage ===\n")

    conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
    cur = conn.cursor()

    test_user = "test_pref_user_123"
    _cleanup_test_user(cur, conn, test_user)

    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml"))
    overlord = await formation.start_overlord()

    try:
        preference_message = "I prefer using FastAPI over Flask for all my API development work"
        print(f"1. Storing preference: {preference_message}")
        response1 = await overlord.chat(preference_message, user_id=test_user, use_async=False, stream=False)

        await asyncio.sleep(8)

        api_question = "What framework should I use to build a REST API?"
        print(f"\n2. Asking: {api_question}")
        response2 = await overlord.chat(api_question, user_id=test_user, use_async=False, stream=False)

        search_results = await overlord.persistent_memory_manager.search_long_term_memory(
            query="FastAPI Flask API development",
            k=5,
            user_id=test_user,
            collections=["preferences"]
        )

        preference_found = False
        if search_results:
            for result in search_results:
                if "FastAPI" in result.get("text", "") and "Flask" in result.get("text", ""):
                    preference_found = True
                    break

        response1_text = response1.content if hasattr(response1, 'content') else str(response1)
        response2_text = response2.content if hasattr(response2, 'content') else str(response2)

        print("\n=== Test 2O1 Results ===")
        print(f"Response to preference: {response1_text[:200] if len(response1_text) > 200 else response1_text}")
        print(f"Response mentions FastAPI: {'FastAPI' in response2_text or 'fastapi' in response2_text.lower()}")
        print(f"Preference stored in collection: {preference_found}")

        if not preference_found:
            print(f"  Warning: Preference not found in search results. Results count: {len(search_results)}")
            return False

        print("Pass: Test 2O1 PASSED")
        return True

    finally:
        await safe_formation_shutdown(formation)

        current_task = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        cur.close()
        conn.close()

async def test_2o2_preference_context_inclusion():
    """Test that stored preferences are included in context for relevant queries."""
    print("\n=== Test 2O2: Preference Context Inclusion ===\n")

    conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
    cur = conn.cursor()

    test_user = "test_pref_user_456"
    _cleanup_test_user(cur, conn, test_user)

    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml"))
    overlord = await formation.start_overlord()

    try:
        preferences = [
            "I always use pytest for testing, never unittest",
            "For UI components, I prefer using Shadcn/UI with Tailwind CSS",
            "I like to use TypeScript instead of JavaScript for all my projects"
        ]

        print("1. Storing preferences...")
        for pref in preferences:
            print(f"   - {pref}")
            await overlord.chat(pref, user_id=test_user, use_async=False, stream=False)
            await asyncio.sleep(10)

        await asyncio.sleep(10)

        print("\n2. Testing context inclusion...")
        test_response = await overlord.chat(
            "What testing framework should I use for my Python project?",
            user_id=test_user, use_async=False, stream=False
        )
        ui_response = await overlord.chat(
            "I need to build a dashboard with some components. What should I use?",
            user_id=test_user, use_async=False, stream=False
        )
        js_response = await overlord.chat(
            "Should I use JavaScript or TypeScript for a new web app?",
            user_id=test_user, use_async=False, stream=False
        )

        test_text = test_response.content if hasattr(test_response, 'content') else str(test_response)
        ui_text = ui_response.content if hasattr(ui_response, 'content') else str(ui_response)
        js_text = js_response.content if hasattr(js_response, 'content') else str(js_response)

        pytest_mentioned = "pytest" in test_text.lower()
        shadcn_mentioned = "shadcn" in ui_text.lower() or "tailwind" in ui_text.lower()
        typescript_mentioned = "typescript" in js_text.lower()

        print("\n=== Test 2O2 Results ===")
        print(f"  Testing question -> pytest mentioned: {pytest_mentioned}")
        print(f"  UI question -> Shadcn/Tailwind mentioned: {shadcn_mentioned}")
        print(f"  JS/TS question -> TypeScript mentioned: {typescript_mentioned}")

        preferences_reflected = sum([pytest_mentioned, shadcn_mentioned, typescript_mentioned])
        print(f"\nPreferences reflected: {preferences_reflected}/3")

        pref_search = await overlord.persistent_memory_manager.search_long_term_memory(
            query="preferences testing UI TypeScript",
            k=10,
            user_id=test_user,
            collections=["preferences"]
        )

        print(f"Preferences in collection: {len(pref_search)} entries found")

        if preferences_reflected >= 2 and len(pref_search) > 0:
            print("Pass: Test 2O2 PASSED")
            return True
        else:
            print(f"  Warning: Expected at least 2/3 preferences reflected, got {preferences_reflected}/3")
            print(f"  Warning: Expected preferences in collection, got {len(pref_search)}")
            return False

    finally:
        await safe_formation_shutdown(formation)

        current_task = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        cur.close()
        conn.close()


async def run_all_tests():
    """Run all preference system tests."""
    print("\n" + "=" * 60)
    print("Test Group 2O: Preference System")
    print("=" * 60)

    results = []

    try:
        result1 = await test_2o1_preference_detection_and_storage()
        results.append(("2O1: Preference Detection", result1))
    except Exception as e:
        print(f"\nFailed: Test 2O1 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("2O1: Preference Detection", False))

    try:
        result2 = await test_2o2_preference_context_inclusion()
        results.append(("2O2: Preference Context", result2))
    except Exception as e:
        print(f"\nFailed: Test 2O2 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("2O2: Preference Context", False))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")

    all_passed = all(result for _, result in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return all_passed


if __name__ == "__main__":
    result = asyncio.run(run_all_tests())
    if result:
        print("SUCCESS", flush=True)
    import os; os._exit(0 if result else 1)
