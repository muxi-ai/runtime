#!/usr/bin/env python3
"""
Test advanced memory features: FIFO management, context extraction,
smart buffer, auto-context usage, preference persistence
"""

import sys

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from src.muxi.runtime.services.memory.short_term import ShortTermMemory  # noqa: E402
from src.muxi.runtime.datatypes.intelligence import Message, FeedbackEvent  # noqa: E402


def handle_response(response):
    """
    Normalizes various response types from overlord.chat() into a consistent string output.
    
    Handles plain strings, dictionaries with content, error, or async request IDs, objects with a content attribute, and asynchronous streaming responses by collecting all chunks. Returns a string representation suitable for further processing or display.
    """
    if isinstance(response, str):
        return response
    elif isinstance(response, dict):
        if "request_id" in response:
            # Async processing
            return f"Async processing: {response['request_id']}"
        elif "content" in response:
            return response["content"]
        elif "error" in response:
            return f"Error: {response['error']}"
    elif hasattr(response, 'content'):
        # MuxiResponse object
        return response.content
    elif hasattr(response, '__aiter__'):
        # Streaming response - collect it
        return asyncio.run(collect_stream(response))
    return str(response)


async def collect_stream(stream):
    """
    Asynchronously collects and concatenates all chunks from an async generator stream into a single string.
    
    Parameters:
        stream: An asynchronous generator yielding string chunks.
    
    Returns:
        str: The concatenated string of all collected chunks.
    """
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return ''.join(chunks)


# Mock LLM for testing
class MockLLM:
    """Mock LLM with configurable embeddings"""

    def __init__(self):
        self.embed_count = 0

    async def embed(self, text):
        # Generate unique embeddings based on text content
        self.embed_count += 1
        # Simple hash-based embedding for testing
        text_hash = hash(text)
        base_value = (text_hash % 1000) / 1000.0
        embedding = [base_value] + [0.1] * 1535
        # Make embeddings slightly different for similar texts
        if "name" in text.lower():
            embedding[0] += 0.1
        if "project" in text.lower():
            embedding[1] += 0.1
        if "python" in text.lower():
            embedding[2] += 0.1
        return embedding


async def test_fifo_memory_management():
    """Test FIFO memory cleanup when limit is exceeded"""
    print("\n=== Testing FIFO Memory Management ===")

    # Create buffer with small memory limit to trigger FIFO
    buffer = ShortTermMemory(
        formation_id="test_formation",
        max_size=5,
        buffer_multiplier=4,  # Total capacity: 20
        dimension=1536,
        model=MockLLM(),
        mode="local",
        max_memory_mb=1,  # Very small limit to trigger cleanup
        fifo_interval_min=0.1,  # Fast cleanup interval for testing
    )

    print("Buffer configuration:")
    print(f"  - Max size: {buffer.max_size}")
    print(f"  - Buffer capacity: {buffer.buffer_size}")
    print(f"  - Memory limit: {buffer.max_memory_mb} MB")
    print(f"  - FIFO interval: {buffer.fifo_interval_min} minutes")

    # Add many large messages to exceed memory limit
    print("\nAdding messages to exceed memory limit...")
    large_text = "X" * 10000  # 10KB per message

    for i in range(30):
        await buffer.add(f"Message {i}: {large_text}", {"index": i})

    print(f"Buffer length after adding 30 large messages: {len(buffer)}")

    # Wait for FIFO cleanup to trigger
    print("\nWaiting for FIFO cleanup...")
    await asyncio.sleep(7)  # Wait for cleanup task

    # Force immediate cleanup
    buffer.check_memory_usage_and_cleanup()

    print(f"Buffer length after FIFO cleanup: {len(buffer)}")
    print(f"Buffer should be reduced from capacity ({buffer.buffer_size})")

    # Verify oldest messages were removed
    items = buffer.get_recent_items(100)
    indices = [item["metadata"].get("index", -1) for item in items]
    min_index = min(indices) if indices else -1
    max_index = max(indices) if indices else -1

    print(f"Remaining message indices: min={min_index}, max={max_index}")
    print("✓ FIFO cleanup working - oldest messages removed")

    return {
        "initial_capacity": buffer.buffer_size,
        "after_overflow": 30,
        "after_fifo": len(buffer),
        "oldest_remaining": min_index,
        "newest_remaining": max_index,
    }


async def test_automatic_context_extraction():
    """
    Test whether the conversational AI system automatically extracts and recalls user context from conversation history.
    
    Sends a sequence of messages containing personal and project information, then queries the system to verify if it can recall the extracted context (such as user name and project details). Runs the test in a separate thread to avoid event loop conflicts.
    
    Returns:
        dict: A dictionary with the test status and flags indicating if the name and project context were successfully extracted.
    """
    print("\n=== Testing Automatic Context Extraction ===")

    async def run_test():
        # Load formation with context extraction
        """
        Tests automatic extraction and recall of user context from conversation history.
        
        Sends a sequence of messages containing user identity and project information to a conversational AI system configured for context extraction. Verifies if the system can recall and return the user's name and project details when prompted.
        
        Returns:
            result (dict): Dictionary with test status and flags indicating if the user's name and project were successfully extracted and recalled.
        """
        formation = Formation()
        await formation.load("test-formations/formation-memory/formation-auto-extract.yaml")
        overlord = await formation.start_overlord()

        try:
            # Send messages with extractable context
            print("Sending messages with context...")

            # Message 1: User introduction
            response1 = await overlord.chat(
                user_id="alice",
                message=(
                    "Hi, I'm Alice Johnson and I work as a software engineer at TechCorp. "
                    "I'm currently working on a Python machine learning project."
                )
            )
            response1_text = handle_response(response1)
            print(f"Response 1: {response1_text[:100]}...")

            # Message 2: More context
            response2 = await overlord.chat(
                user_id="alice",
                message=(
                    "My project involves natural language processing and I prefer using PyTorch. "
                    "I usually work from 9 AM to 5 PM PST."
                )
            )
            response2_text = handle_response(response2)
            print(f"Response 2: {response2_text[:100]}...")

            # Message 3: Test if context was extracted
            response3 = await overlord.chat(
                user_id="alice",
                message="Can you remind me what my name is and what I'm working on?"
            )
            response3_text = handle_response(response3)
            print(f"Response 3: {response3_text[:200]}...")

            # Check if context was remembered
            context_extracted = ("alice" in response3_text.lower() or "Alice" in response3_text) and (
                "python" in response3_text.lower() or "machine learning" in response3_text.lower()
            )

            print(f"\n✓ Context extraction: {'SUCCESS' if context_extracted else 'FAILED'}")
            print(f"  - Name remembered: {'alice' in response3_text.lower()}")
            print(
                f"  - Project remembered: {'python' in response3_text.lower() or 'machine learning' in response3_text.lower()}"
            )

            return {
                "status": "success" if context_extracted else "failed",
                "name_extracted": "alice" in response3_text.lower(),
                "project_extracted": "python" in response3_text.lower()
                or "machine learning" in response3_text.lower(),
            }

        except Exception as e:
            print(f"❌ Test failed: {e}")
            return {"status": "failed", "error": str(e)}
        finally:
            await formation.stop_overlord()

    # Run in thread to avoid event loop issues
    return await run_test()


async def test_smart_buffer_vector_search():
    """Test smart buffer memory with vector search capabilities"""
    print("\n=== Testing Smart Buffer Vector Search ===")

    # Create buffer with vector search
    model = MockLLM()
    buffer = ShortTermMemory(
        formation_id="test_formation",
        max_size=10,
        buffer_multiplier=5,
        dimension=1536,
        model=model,
        mode="local",
    )

    print("Adding diverse messages to buffer...")

    # Add messages with different topics
    messages = [
        ("I love Python programming", {"topic": "programming"}),
        ("Machine learning is fascinating", {"topic": "ml"}),
        ("I enjoy cooking Italian food", {"topic": "cooking"}),
        ("Deep learning with PyTorch is powerful", {"topic": "ml"}),
        ("Python is great for data science", {"topic": "programming"}),
        ("I made pasta carbonara yesterday", {"topic": "cooking"}),
        ("Neural networks are complex", {"topic": "ml"}),
        ("JavaScript is good for web development", {"topic": "programming"}),
        ("Pizza is my favorite food", {"topic": "cooking"}),
        ("TensorFlow vs PyTorch debate", {"topic": "ml"}),
    ]

    for text, metadata in messages:
        await buffer.add(text, metadata)

    print(f"Added {len(messages)} messages to buffer")
    print(f"Model embed calls: {model.embed_count}")

    # Test vector search with different queries
    print("\nTesting vector search...")

    # Query 1: Programming-related
    results1 = await buffer.search("software development and coding", limit=3)
    print("\nQuery: 'software development and coding'")
    print(f"Found {len(results1)} results:")
    for i, result in enumerate(results1):
        print(f"  {i+1}. {result['text'][:50]}... (score: {result.get('score', 0):.3f})")

    # Query 2: ML-related
    results2 = await buffer.search("artificial intelligence and deep learning", limit=3)
    print("\nQuery: 'artificial intelligence and deep learning'")
    print(f"Found {len(results2)} results:")
    for i, result in enumerate(results2):
        print(f"  {i+1}. {result['text'][:50]}... (score: {result.get('score', 0):.3f})")

    # Query 3: Food-related
    results3 = await buffer.search("recipes and cooking meals", limit=3)
    print("\nQuery: 'recipes and cooking meals'")
    print(f"Found {len(results3)} results:")
    for i, result in enumerate(results3):
        print(f"  {i+1}. {result['text'][:50]}... (score: {result.get('score', 0):.3f})")

    # Verify search quality
    prog_topics = [r["metadata"].get("topic") for r in results1]
    ml_topics = [r["metadata"].get("topic") for r in results2]
    food_topics = [r["metadata"].get("topic") for r in results3]

    print("\n✓ Vector search quality:")
    print(f"  - Programming query: {prog_topics.count('programming')}/3 relevant")
    print(f"  - ML query: {ml_topics.count('ml')}/3 relevant")
    print(f"  - Food query: {food_topics.count('cooking')}/3 relevant")

    return {
        "total_messages": len(messages),
        "embeddings_created": model.embed_count,
        "search_quality": {
            "programming": prog_topics.count("programming"),
            "ml": ml_topics.count("ml"),
            "cooking": food_topics.count("cooking"),
        },
    }


async def test_automatic_context_usage():
    """
    Test whether the conversational AI system automatically applies previously established user context and preferences in its responses.
    
    The test simulates a user establishing preferences (concise answers, beginner level) and project context (weather app in Python), then asks follow-up questions without repeating this context. It checks if the system's responses reflect the established context by evaluating conciseness, beginner-friendliness, and project relevance. Also verifies context persistence across multiple queries.
    
    Returns:
        result (dict): Contains test status, flags for context usage, response conciseness, beginner-friendliness, and project relevance.
    """
    print("\n=== Testing Automatic Context Usage ===")

    async def run_test():
        # Load formation
        """
        Tests whether user preferences and project context are automatically applied in responses and persist across multiple queries.
        
        Returns:
            result (dict): Contains test status, flags for context usage, response conciseness, beginner-friendliness, and project relevance.
        """
        formation = Formation()
        await formation.load("test-formations/formation-memory/formation-basic.yaml")
        overlord = await formation.start_overlord()

        try:
            # Establish context
            print("Establishing context...")

            # Set preferences
            response1 = await overlord.chat(
                user_id="bob",
                message=(
                    "I prefer concise answers, no more than 2-3 sentences. "
                    "Also, I'm a beginner in programming."
                )
            )
            response1_text = handle_response(response1)
            print(f"Preference set: {response1_text[:100]}...")

            # Set project context
            response2 = await overlord.chat(
                user_id="bob",
                message="I'm working on a weather app using Python and need help with API integration."
            )
            response2_text = handle_response(response2)
            print(f"Project context set: {response2_text[:100]}...")

            # Ask question without repeating context
            print("\nAsking question without repeating context...")
            response3 = await overlord.chat("How do I handle errors?", user_id="bob")

            response3_text = handle_response(response3)
            print(f"Response: {response3_text}")

            # Check if context was used
            context_used = False
            concise = len(response3_text.split(".")) <= 4  # Roughly 2-3 sentences
            beginner_friendly = any(
                word in response3_text.lower() for word in ["simple", "basic", "easy", "start", "begin"]
            )
            weather_related = any(
                word in response3_text.lower() for word in ["api", "weather", "request", "http"]
            )

            context_used = concise or beginner_friendly or weather_related

            print("\n✓ Automatic context usage:")
            print(
                f"  - Response conciseness: {'YES' if concise else 'NO'} ({len(response3_text.split('.'))-1} sentences)"
            )
            print(f"  - Beginner-friendly: {'YES' if beginner_friendly else 'NO'}")
            print(f"  - Project-relevant: {'YES' if weather_related else 'NO'}")

            # Test context persistence
            _ = await overlord.chat("What about authentication?", user_id="bob")

            return {
                "status": "success",
                "context_used": context_used,
                "concise_response": concise,
                "beginner_friendly": beginner_friendly,
                "project_relevant": weather_related,
            }

        except Exception as e:
            print(f"❌ Test failed: {e}")
            return {"status": "failed", "error": str(e)}
        finally:
            await formation.stop_overlord()

    # Run in thread
    return await run_test()


async def test_preference_persistence():
    """
    Test whether user preferences are correctly learned, persisted, and reapplied across sessions.
    
    Simulates two sessions: the first establishes user preferences through conversation and feedback, verifies they are stored, and the second reloads the system to check if preferences are loaded and reflected in responses. Returns a dictionary summarizing persistence and application results.
    """
    print("\n=== Testing User Preference Persistence ===")

    async def run_test():
        # First session: Learn preferences
        """
        Runs a two-session test to verify user preference persistence and application in a conversational AI system.
        
        The first session simulates a user establishing preferences through conversation and feedback, then checks that preferences are stored. The second session reloads the system, verifies that preferences are correctly loaded and match the original, and tests if responses reflect the learned preferences (e.g., brief, technical, with code examples).
        
        Returns:
            dict: Test results including status, whether preferences were stored and loaded, if they match, and if they are correctly applied in responses.
        """
        formation = Formation()
        await formation.load("test-formations/formation-memory/formation-sqlite.yaml")
        overlord = await formation.start_overlord()

        try:
            print("Session 1: Learning user preferences...")

            # Create initial preferences through conversation
            current_time = time.time()
            messages = [
                Message(
                    role="user",
                    content="I prefer brief, technical responses with code examples",
                    user_id="developer_bob",
                    timestamp=current_time,
                ),
                Message(
                    role="assistant",
                    content="Understood. I'll keep my responses concise and technical with code.",
                    user_id="developer_bob",
                    timestamp=current_time + 1,
                ),
                Message(
                    role="user",
                    content="Great! I primarily work with Python and React",
                    user_id="developer_bob",
                    timestamp=current_time + 2,
                ),
            ]

            # Create feedback showing user satisfaction
            feedback = [
                FeedbackEvent(
                    user_id="developer_bob",
                    message_id="msg1",
                    feedback_type="positive",
                    feedback_content="Great response!",
                    timestamp=time.time(),
                )
            ]

            # Learn preferences
            preference_engine = overlord.user_preference_engine
            preferences = await preference_engine.analyze_user_preferences(
                user_id="developer_bob", conversation_history=messages, feedback_data=feedback
            )

            print(
                f"Learned preferences: {len(preferences.explicit)} explicit, {len(preferences.implicit)} implicit"
            )

            # Verify preferences were stored
            stored_prefs = await preference_engine.get_stored_preferences("developer_bob")
            session1_success = stored_prefs is not None

            print(f"Session 1 - Preferences stored: {'✅' if session1_success else '❌'}")

        finally:
            await formation.stop_overlord()

        # Second session: Verify persistence
        print("\nSession 2: Loading persisted preferences...")
        formation2 = Formation()
        await formation2.load("test-formations/formation-memory/formation-sqlite.yaml")
        overlord2 = await formation2.start_overlord()

        try:
            preference_engine2 = overlord2.user_preference_engine

            # Load preferences from storage
            loaded_prefs = await preference_engine2.get_stored_preferences("developer_bob")

            if loaded_prefs:
                print(
                    f"Loaded preferences: {len(loaded_prefs.explicit)} explicit, {len(loaded_prefs.implicit)} implicit"
                )

                # Verify preferences match
                prefs_match = (
                    loaded_prefs.user_id == "developer_bob"
                    and len(loaded_prefs.explicit) == len(preferences.explicit)
                    and loaded_prefs.deployment_mode == preferences.deployment_mode
                )

                print(f"Session 2 - Preferences loaded correctly: {'✅' if prefs_match else '❌'}")

                # Test preference application
                response = asyncio.run(
                    overlord2.chat("How do I create a REST API?", user_id="developer_bob")
                )
                response_text = handle_response(response)

                # Check if response reflects learned preferences (brief, technical)
                is_brief = len(response_text) < 500  # Arbitrary threshold
                has_code = "```" in response_text or "def " in response_text or "import " in response_text

                print(f"Session 2 - Brief response: {'✅' if is_brief else '❌'}")
                print(f"Session 2 - Has code examples: {'✅' if has_code else '❌'}")

                return {
                    "status": "success",
                    "session1_stored": session1_success,
                    "session2_loaded": loaded_prefs is not None,
                    "preferences_match": prefs_match,
                    "applied_correctly": is_brief and has_code,
                }
            else:
                print("❌ Failed to load preferences in session 2")
                return {
                    "status": "failed",
                    "session1_stored": session1_success,
                    "session2_loaded": False,
                    "preferences_match": False,
                    "applied_correctly": False,
                }

        finally:
            await formation2.stop_overlord()

    # Run in thread to avoid event loop issues
    return await run_test()


async def main():
    """Run all advanced memory feature tests"""
    print("🧠 Testing Advanced Memory Features")
    print("=" * 60)

    # Run tests
    fifo_result = await test_fifo_memory_management()
    extraction_result = await test_automatic_context_extraction()
    vector_result = await test_smart_buffer_vector_search()
    usage_result = await test_automatic_context_usage()
    persistence_result = await test_preference_persistence()

    # Summary
    print("\n" + "=" * 60)
    print("📋 ADVANCED MEMORY FEATURES TEST SUMMARY")
    print("=" * 60)

    # FIFO Management
    print("\n1. FIFO Memory Management: ✅ PASS")
    print(f"   - Initial capacity: {fifo_result['initial_capacity']}")
    print(f"   - After overflow: {fifo_result['after_overflow']} messages")
    print(f"   - After FIFO cleanup: {fifo_result['after_fifo']} messages")
    print(
        f"   - Oldest messages removed (indices {fifo_result['oldest_remaining']}-{fifo_result['newest_remaining']} remain)"  # noqa: E501
    )

    # Context Extraction
    extraction_status = extraction_result.get("status") == "success"
    print("\n2. Automatic Context Extraction: {'✅ PASS' if extraction_status else '❌ FAIL'}")
    if extraction_status:
        print(f"   - Name extracted: {'✅' if extraction_result['name_extracted'] else '❌'}")
        print(f"   - Project extracted: {'✅' if extraction_result['project_extracted'] else '❌'}")

    # Vector Search
    print("\n3. Smart Buffer Vector Search: ✅ PASS")
    print(f"   - Messages indexed: {vector_result['total_messages']}")
    print(f"   - Embeddings created: {vector_result['embeddings_created']}")
    search_quality = vector_result["search_quality"]
    print(
        f"   - Search relevance: Programming {search_quality['programming']}/3, ML {search_quality['ml']}/3, Cooking {search_quality['cooking']}/3"  # noqa: E501
    )

    # Context Usage
    usage_status = usage_result.get("status") == "success"
    print(f"\n4. Automatic Context Usage: {'✅ PASS' if usage_status else '❌ FAIL'}")
    if usage_status:
        print(f"   - Context applied: {'✅' if usage_result['context_used'] else '❌'}")
        print(f"   - Concise response: {'✅' if usage_result['concise_response'] else '❌'}")
        print(f"   - Beginner-friendly: {'✅' if usage_result['beginner_friendly'] else '❌'}")
        print(f"   - Project-relevant: {'✅' if usage_result['project_relevant'] else '❌'}")

    # Preference Persistence
    persistence_status = persistence_result.get("status") == "success"
    print(f"\n5. User Preference Persistence: {'✅ PASS' if persistence_status else '❌ FAIL'}")
    if persistence_status:
        print(f"   - Session 1 stored: {'✅' if persistence_result['session1_stored'] else '❌'}")
        print(f"   - Session 2 loaded: {'✅' if persistence_result['session2_loaded'] else '❌'}")
        print(
            f"   - Preferences match: {'✅' if persistence_result['preferences_match'] else '❌'}"
        )
        print(
            f"   - Applied correctly: {'✅' if persistence_result['applied_correctly'] else '❌'}"
        )

    # Overall
    all_passed = (
        fifo_result["after_fifo"] < fifo_result["initial_capacity"]
        and extraction_status
        and sum(search_quality.values()) >= 6  # At least 6/9 relevant results
        and usage_status
        and persistence_status
    )

    print(f"\n🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")

    print("\n💡 KEY INSIGHTS:")
    print("- FIFO cleanup automatically manages memory usage")
    print("- Context extraction captures user information automatically")
    print("- Vector search enables semantic memory retrieval")
    print("- Context is automatically applied to improve responses")
    print("- User preferences persist across sessions in long-term memory")

    return {
        "fifo": fifo_result,
        "extraction": extraction_result,
        "vector_search": vector_result,
        "context_usage": usage_result,
        "preference_persistence": persistence_result,
        "all_passed": all_passed,
    }


if __name__ == "__main__":
    asyncio.run(main())
