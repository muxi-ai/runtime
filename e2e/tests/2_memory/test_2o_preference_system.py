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

async def test_2o1_preference_detection_and_storage():
    """Test that user preferences are detected and stored in the preferences collection."""
    print("\n=== Test 2O1: Preference Detection and Storage ===\n")

    # Setup database connection
    conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
    cur = conn.cursor()

    test_user = "test_pref_user_123"

    # Clear test data
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("""
        DELETE FROM users WHERE id IN (
            SELECT user_id FROM user_identifiers WHERE identifier = %s
        )
    """, (test_user,))
    conn.commit()

    # Load formation
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml"))
    overlord = await formation.start_overlord()

    try:
        # Express a preference
        preference_message = "I prefer using FastAPI over Flask for all my API development work"
        print(f"1. Storing preference: {preference_message}")
        response1 = await overlord.chat(preference_message, user_id=test_user, use_async=False, stream=False)

        # Give time for async preference storage
        await asyncio.sleep(8)

        # Ask a related question to see if preference is retrieved
        api_question = "What framework should I use to build a REST API?"
        print(f"\n2. Asking: {api_question}")
        response2 = await overlord.chat(api_question, user_id=test_user, use_async=False, stream=False)

        # Search memory to verify preference was stored
        search_results = await overlord.persistent_memory_manager.search_long_term_memory(
            query="FastAPI Flask API development",
            k=5,
            user_id=test_user,
            collections=["preferences"]
        )

        # Check if preference was stored
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
            print(f"  ⚠️  Preference not found in search results. Results count: {len(search_results)}")
            return False

        print("✓ Test 2O1 PASSED")
        return True

    finally:
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

        cur.close()
        conn.close()

async def test_2o2_preference_context_inclusion():
    """Test that stored preferences are included in context for relevant queries."""
    print("\n=== Test 2O2: Preference Context Inclusion ===\n")

    # Setup database connection
    conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
    cur = conn.cursor()

    test_user = "test_pref_user_456"

    # Clear test data
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("""
        DELETE FROM users WHERE id IN (
            SELECT user_id FROM user_identifiers WHERE identifier = %s
        )
    """, (test_user,))
    conn.commit()

    # Load formation
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml"))
    overlord = await formation.start_overlord()

    try:
        # Store multiple preferences
        preferences = [
            "I always use pytest for testing, never unittest",
            "For UI components, I prefer using Shadcn/UI with Tailwind CSS",
            "I like to use TypeScript instead of JavaScript for all my projects"
        ]

        print("1. Storing preferences...")
        for pref in preferences:
            print(f"   - {pref}")
            await overlord.chat(pref, user_id=test_user, use_async=False, stream=False)
            await asyncio.sleep(10)  # Give time for extraction (takes 8-10s per item)

        # Final wait to ensure all extractions complete
        await asyncio.sleep(10)

        # Test 1: Ask about testing - should retrieve pytest preference
        print("\n2. Testing context inclusion...")
        test_response = await overlord.chat(
            "What testing framework should I use for my Python project?",
            user_id=test_user,
            use_async=False,
            stream=False
        )

        # Test 2: Ask about UI - should retrieve Shadcn/UI preference
        ui_response = await overlord.chat(
            "I need to build a dashboard with some components. What should I use?",
            user_id=test_user,
            use_async=False,
            stream=False
        )

        # Test 3: Ask about JavaScript - should retrieve TypeScript preference
        js_response = await overlord.chat(
            "Should I use JavaScript or TypeScript for a new web app?",
            user_id=test_user,
            use_async=False,
            stream=False
        )

        # Extract text from responses
        test_text = test_response.content if hasattr(test_response, 'content') else str(test_response)
        ui_text = ui_response.content if hasattr(ui_response, 'content') else str(ui_response)
        js_text = js_response.content if hasattr(js_response, 'content') else str(js_response)

        # Verify preferences are reflected in responses
        pytest_mentioned = "pytest" in test_text.lower()
        shadcn_mentioned = "shadcn" in ui_text.lower() or "tailwind" in ui_text.lower()
        typescript_mentioned = "typescript" in js_text.lower()

        print("\n=== Test 2O2 Results ===")
        print("Context inclusion results:")
        print(f"  Testing question -> pytest mentioned: {pytest_mentioned}")
        print(f"  UI question -> Shadcn/Tailwind mentioned: {shadcn_mentioned}")
        print(f"  JS/TS question -> TypeScript mentioned: {typescript_mentioned}")

        # At least 2 out of 3 preferences should be reflected
        preferences_reflected = sum([pytest_mentioned, shadcn_mentioned, typescript_mentioned])
        print(f"\nPreferences reflected: {preferences_reflected}/3")

        # Verify preferences are in the preferences collection
        pref_search = await overlord.persistent_memory_manager.search_long_term_memory(
            query="preferences testing UI TypeScript",
            k=10,
            user_id=test_user,
            collections=["preferences"]
        )

        print(f"Preferences in collection: {len(pref_search)} entries found")

        if preferences_reflected >= 2 and len(pref_search) > 0:
            print("✓ Test 2O2 PASSED")
            return True
        else:
            print(f"  ⚠️  Expected at least 2/3 preferences reflected, got {preferences_reflected}/3")
            print(f"  ⚠️  Expected preferences in collection, got {len(pref_search)}")
            return False

    finally:
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

        cur.close()
        conn.close()


async def run_all_tests():
    """Run all preference system tests."""
    print("\n" + "=" * 60)
    print("Test Group 2O: Preference System")
    print("=" * 60)

    results = []

    # Test 2O1
    try:
        result1 = await test_2o1_preference_detection_and_storage()
        results.append(("2O1: Preference Detection", result1))
    except Exception as e:
        print(f"\n❌ Test 2O1 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("2O1: Preference Detection", False))

    # Test 2O2
    try:
        result2 = await test_2o2_preference_context_inclusion()
        results.append(("2O2: Preference Context", result2))
    except Exception as e:
        print(f"\n❌ Test 2O2 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("2O2: Preference Context", False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")

    all_passed = all(result for _, result in results)
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")

    return all_passed


if __name__ == "__main__":
    result = asyncio.run(run_all_tests())
    exit(0 if result else 1)
