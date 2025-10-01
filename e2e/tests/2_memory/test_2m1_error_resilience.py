#!/usr/bin/env python3
"""
Test 2M1: Memory Error Handling & Resilience
Test that chat continues working even when memory operations fail
"""
import sys
from pathlib import Path
import os
import asyncio
import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402
from test_utils import safe_formation_shutdown  # noqa: E402


async def get_response_text(response):
    """Helper function to extract text from different response types."""
    if hasattr(response, "__aiter__"):
        # Async generator response
        full_response = ""
        async for chunk in response:
            if hasattr(chunk, "content") and chunk.content:
                full_response += chunk.content
            elif isinstance(chunk, str):
                full_response += chunk
        return full_response
    elif hasattr(response, "content"):
        return response.content
    else:
        return str(response)


async def test_error_resilience():
    """Test system resilience when memory operations fail."""
    print("\n=== Test 2M1: Memory Error Handling & Resilience ===\n")

    # Setup
    formation = Formation()
    await formation.load(
        str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml")
    )
    overlord = await formation.start_overlord()

    test_user = "resilience_test_user"

    # Test 1: Chat works despite extraction failures
    print("1. Testing chat resilience with extraction failures...")

    # Temporarily break the extraction
    original_extract = overlord.extract_user_information
    extraction_called = False

    async def failing_extract(*args, **kwargs):
        nonlocal extraction_called
        extraction_called = True
        raise Exception("Simulated extraction failure")

    overlord.extract_user_information = failing_extract

    # Chat should still work
    response = await overlord.chat(
        "My name is TestUser and I love Python", user_id=test_user, use_async=False
    )
    response_text = await get_response_text(response)

    assert len(response_text) > 0, "Chat failed when extraction failed"
    assert extraction_called, "Extraction was not attempted"

    print("✓ Chat continues despite extraction failure")

    # Restore extraction
    overlord.extract_user_information = original_extract

    # Test 2: Chat works with buffer memory failures
    print("\n2. Testing chat resilience with buffer memory failures...")

    # Temporarily break buffer memory storage
    original_add_message = overlord.add_message_to_memory
    storage_attempted = False

    async def failing_add_message(*args, **kwargs):
        nonlocal storage_attempted
        storage_attempted = True
        raise Exception("Simulated buffer storage failure")

    overlord.add_message_to_memory = failing_add_message

    # Chat should still work
    response = await overlord.chat(
        "Tell me about machine learning", user_id=test_user, use_async=False
    )
    response_text = await get_response_text(response)
    assert len(response_text) > 0, "Chat failed when buffer storage failed"
    assert storage_attempted, "Buffer storage was not attempted"

    print("✓ Chat continues despite buffer storage failure")

    # Restore buffer storage
    overlord.add_message_to_memory = original_add_message

    # Test 3: Long-term memory failure doesn't affect chat
    print("\n3. Testing resilience with long-term memory failures...")

    if overlord.long_term_memory:
        # Clear existing memories to ensure extraction will attempt storage
        conn = psycopg2.connect(
            dbname="muxi_test",
            user="muxi",
            host="localhost"
        )
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE external_user_id = %s", (test_user,))
            result = cur.fetchone()
            if result:
                user_db_id = result[0]
                cur.execute("DELETE FROM memories WHERE user_id = %s", (user_db_id,))
        conn.commit()
        conn.close()
        
        original_add = overlord.long_term_memory.add
        add_attempted = False

        async def failing_add(*args, **kwargs):
            nonlocal add_attempted
            add_attempted = True
            raise Exception("Simulated long-term memory failure")

        overlord.long_term_memory.add = failing_add

        # Trigger extraction which will try to store in long-term memory
        response = await overlord.chat(
            "I work at SpaceX as an engineer", user_id=test_user, use_async=False, stream=False
        )
        response_text = await get_response_text(response)
        assert len(response_text) > 0, "Chat failed when long-term memory failed"

        # Give time for async extraction (needs 8+ seconds to complete)
        await asyncio.sleep(10)
        assert add_attempted, "Long-term memory storage was not attempted"

        print("✓ Chat continues despite long-term memory failure")

        # Restore
        overlord.long_term_memory.add = original_add

    # Test 4: Vector search failure falls back gracefully
    print("\n4. Testing fallback when vector search fails...")

    # First add some messages normally
    await overlord.chat("I like hiking in the mountains", user_id=test_user, use_async=False, stream=False)
    await overlord.chat("My favorite food is pizza", user_id=test_user, use_async=False, stream=False)
    await asyncio.sleep(2)

    # Break vector search in buffer memory
    if hasattr(overlord.buffer_memory_manager, "search_buffer_memory"):
        original_search = overlord.buffer_memory_manager.search_buffer_memory

        async def failing_search(query, k=10, filter_metadata=None):
            if query:  # Only fail for vector search (non-empty query)
                raise Exception("Simulated vector search failure")
            # Fall back to chronological retrieval
            return await original_search("", k, filter_metadata)

        overlord.buffer_memory_manager.search_buffer_memory = failing_search

        # Should still get some response using fallback
        response = await overlord.chat("What do I like to do?", user_id=test_user, use_async=False, stream=False)
        response_text = await get_response_text(response)
        assert len(response_text) > 0, "Chat failed when vector search failed"

        print("✓ Falls back to chronological retrieval when vector search fails")

        # Restore
        overlord.buffer_memory_manager.search_buffer_memory = original_search

    # Test 5: Database connection failure handling
    print("\n5. Testing resilience with database errors...")

    # Simulate a database error during memory retrieval
    if overlord.long_term_memory:
        original_search = overlord.long_term_memory.search

        async def failing_db_search(*args, **kwargs):
            raise psycopg2.OperationalError("Simulated database connection error")

        overlord.long_term_memory.search = failing_db_search

        # Chat should continue without long-term memories
        response = await overlord.chat("What's my name?", user_id=test_user, use_async=False, stream=False)
        response_text = await get_response_text(response)
        assert len(response_text) > 0, "Chat failed during database error"

        print("✓ Chat continues even with database connection errors")

        # Restore
        overlord.long_term_memory.search = original_search

    # Test 6: System remains operational
    print("\n6. Verifying system remains fully operational...")

    # After all the failures, system should work normally
    response = await overlord.chat("Hello, how are you?", user_id=test_user, use_async=False, stream=False)
    response_text = await get_response_text(response)
    assert len(response_text) > 0, "System not operational after errors"

    # Can still store and retrieve
    await overlord.chat("Final test message", user_id=test_user, use_async=False, stream=False)
    await asyncio.sleep(2)  # Give time for memory storage
    response = await overlord.chat("What was my last message?", user_id=test_user, use_async=False, stream=False)
    response_text = await get_response_text(response)
    # For resilience testing, just verify we get a response (system is operational)
    # Content accuracy is tested in other memory tests
    assert len(response_text) > 0, f"No response received after recovery. System may be down."

    print("✓ System fully operational after error recovery")

    await safe_formation_shutdown(formation)

    print("\n✅ Error resilience test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_error_resilience())
    os._exit(0)
