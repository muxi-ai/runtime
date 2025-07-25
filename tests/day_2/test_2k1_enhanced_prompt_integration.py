#!/usr/bin/env python3
"""
Test 2K1: Enhanced Prompt Integration
Test that long-term memories, buffer, and user profile all contribute to enhanced prompts
"""
import sys
import os
sys.path.insert(0, '.')
import asyncio
import psycopg2
from src.muxi.formation.formation import Formation


async def test_enhanced_prompt_integration():
    """Test integration of all memory types in prompt enhancement."""
    print("\n=== Test 2K1: Enhanced Prompt Integration ===\n")

    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()

    # Clear test data
    test_user = "enhanced_prompt_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()

    formation = Formation()
    await formation.load("test-formations/formation-memory/formation-postgres.yaml")
    overlord = await formation.start_overlord()

    # Build rich context
    print("1. Building comprehensive context...")

    # User identity and work
    await overlord.chat("I'm Emma, a data scientist at Meta", user_id=test_user, use_async=False)
    await asyncio.sleep(3)

    # Specialization
    await overlord.chat("I specialize in recommendation systems", user_id=test_user, use_async=False)
    await asyncio.sleep(3)

    # Technical preferences
    await overlord.chat("I use PyTorch for deep learning", user_id=test_user, use_async=False)
    await asyncio.sleep(3)

    # Recent project context
    await overlord.chat("I'm currently working on improving our video recommendation algorithm", user_id=test_user, use_async=False)
    await asyncio.sleep(3)

    # Personal preference
    await overlord.chat("I prefer reading technical papers over watching video tutorials", user_id=test_user, use_async=False)
    await asyncio.sleep(3)

    print("✓ Built context with identity, work, preferences, and current project")

    # Test contextual question
    print("\n2. Asking context-dependent question...")
    response = await overlord.chat("What frameworks should I learn for my field?", user_id=test_user
    , use_async=False)

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

    # Response should demonstrate use of stored context
    context_indicators = [
        "emma",
        "data scientist",
        "meta",
        "recommendation",
        "pytorch",
        "deep learning",
        "video"
    ]

    response_lower = response_text.lower()
    context_used = [indicator for indicator in context_indicators if indicator in response_lower]

    assert len(context_used) >= 2, \
        f"Response doesn't show enough context usage. Found: {context_used} in: {response_text}"

    print(f"✓ Response uses context: {context_used}")

    # Verify response quality based on context
    technical_terms = [
        "tensorflow", "jax", "scikit", "pandas", "numpy",
        "collaborative filtering", "neural", "embedding",
        "matrix factorization", "transformer"
    ]

    technical_found = [term for term in technical_terms if term in response_lower]
    assert len(technical_found) >= 1, \
        f"Response lacks technical depth despite context. Found: {technical_found}"

    print(f"✓ Response includes relevant technical suggestions: {technical_found}")

    # Test memory priority
    print("\n3. Testing memory priority in responses...")

    # Add many buffer messages to test priority
    for i in range(10):
        await overlord.chat(f"Random message number {i}", user_id=test_user, use_async=False)

    # Ask about core identity (should prioritize long-term memory)
    response = await overlord.chat("Where do I work again?", user_id=test_user, use_async=False)

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

    assert "meta" in response_text.lower(), \
        f"Failed to recall workplace from long-term memory: {response_text}"

    print("✓ Long-term memories prioritized over recent buffer noise")

    # Test comprehensive recall
    print("\n4. Testing comprehensive context recall...")
    response = await overlord.chat("Can you summarize what you know about me and my work?", user_id=test_user
    , use_async=False)

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

    # Should mention multiple aspects
    response_lower = response_text.lower()
    key_facts = {
        "name": "emma" in response_lower,
        "company": "meta" in response_lower,
        "role": "data scientist" in response_lower,
        "specialty": "recommendation" in response_lower,
        "tool": "pytorch" in response_lower,
        "project": "video" in response_lower or "algorithm" in response_lower
    }

    facts_mentioned = sum(key_facts.values())
    assert facts_mentioned >= 4, \
        f"Summary missing key facts. Found {facts_mentioned}/6: {key_facts}"

    print(f"✓ Comprehensive summary includes {facts_mentioned}/6 key facts")

    # Verify memories were stored correctly
    print("\n5. Verifying memory storage...")
    cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT collection) as collections
        FROM memories
        WHERE meta_data->>'user_id' = %s
    """, (test_user,))

    total_memories, collection_count = cur.fetchone()
    assert total_memories >= 5, f"Too few memories stored: {total_memories}"
    assert collection_count >= 2, f"Too few collection types: {collection_count}"

    print(f"✓ Stored {total_memories} memories across {collection_count} collections")

    cur.close()
    conn.close()

    await formation.shutdown()

    print("\n✅ Enhanced prompt integration test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_enhanced_prompt_integration())
    os._exit(0)
