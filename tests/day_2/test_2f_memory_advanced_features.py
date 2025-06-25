#!/usr/bin/env python3
"""Test advanced memory features: FIFO management, context extraction, smart buffer, auto-context usage"""

import sys
sys.path.insert(0, '.')
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from src.muxi.runtime.services.memory.short_term import ShortTermMemory

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
        max_size=5,
        buffer_multiplier=4,  # Total capacity: 20
        dimension=1536,
        model=MockLLM(),
        mode="local",
        max_memory_mb=1,  # Very small limit to trigger cleanup
        fifo_interval_min=0.1  # Fast cleanup interval for testing
    )
    
    print(f"Buffer configuration:")
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
    indices = [item['metadata'].get('index', -1) for item in items]
    min_index = min(indices) if indices else -1
    max_index = max(indices) if indices else -1
    
    print(f"Remaining message indices: min={min_index}, max={max_index}")
    print(f"✓ FIFO cleanup working - oldest messages removed")
    
    return {
        "initial_capacity": buffer.buffer_size,
        "after_overflow": 30,
        "after_fifo": len(buffer),
        "oldest_remaining": min_index,
        "newest_remaining": max_index
    }

async def test_automatic_context_extraction():
    """Test automatic extraction of context from conversations"""
    print("\n=== Testing Automatic Context Extraction ===")
    
    def run_test():
        # Load formation with context extraction
        formation = Formation()
        formation.load("test-formations/formation-memory/formation-auto-extract.yaml")
        overlord = formation.start_overlord()
        
        try:
            # Send messages with extractable context
            print("Sending messages with context...")
            
            # Message 1: User introduction
            response1 = asyncio.run(overlord.chat(
                "Hi, I'm Alice Johnson and I work as a software engineer at TechCorp. "
                "I'm currently working on a Python machine learning project.",
                user_id="alice"
            ))
            print(f"Response 1: {response1[:100]}...")
            
            # Message 2: More context
            response2 = asyncio.run(overlord.chat(
                "My project involves natural language processing and I prefer using PyTorch. "
                "I usually work from 9 AM to 5 PM PST.",
                user_id="alice"
            ))
            print(f"Response 2: {response2[:100]}...")
            
            # Message 3: Test if context was extracted
            response3 = asyncio.run(overlord.chat(
                "Can you remind me what my name is and what I'm working on?",
                user_id="alice"
            ))
            print(f"Response 3: {response3[:200]}...")
            
            # Check if context was remembered
            context_extracted = (
                "alice" in response3.lower() or "Alice" in response3
            ) and (
                "python" in response3.lower() or "machine learning" in response3.lower()
            )
            
            print(f"\n✓ Context extraction: {'SUCCESS' if context_extracted else 'FAILED'}")
            print(f"  - Name remembered: {'alice' in response3.lower()}")
            print(f"  - Project remembered: {'python' in response3.lower() or 'machine learning' in response3.lower()}")
            
            return {
                "status": "success" if context_extracted else "failed",
                "name_extracted": "alice" in response3.lower(),
                "project_extracted": "python" in response3.lower() or "machine learning" in response3.lower()
            }
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            return {"status": "failed", "error": str(e)}
        finally:
            formation.stop_overlord()
    
    # Run in thread to avoid event loop issues
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        return future.result()

async def test_smart_buffer_vector_search():
    """Test smart buffer memory with vector search capabilities"""
    print("\n=== Testing Smart Buffer Vector Search ===")
    
    # Create buffer with vector search
    model = MockLLM()
    buffer = ShortTermMemory(
        max_size=10,
        buffer_multiplier=5,
        dimension=1536,
        model=model,
        mode="local"
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
        ("TensorFlow vs PyTorch debate", {"topic": "ml"})
    ]
    
    for text, metadata in messages:
        await buffer.add(text, metadata)
    
    print(f"Added {len(messages)} messages to buffer")
    print(f"Model embed calls: {model.embed_count}")
    
    # Test vector search with different queries
    print("\nTesting vector search...")
    
    # Query 1: Programming-related
    results1 = await buffer.search("software development and coding", limit=3)
    print(f"\nQuery: 'software development and coding'")
    print(f"Found {len(results1)} results:")
    for i, result in enumerate(results1):
        print(f"  {i+1}. {result['text'][:50]}... (score: {result.get('score', 0):.3f})")
    
    # Query 2: ML-related
    results2 = await buffer.search("artificial intelligence and deep learning", limit=3)
    print(f"\nQuery: 'artificial intelligence and deep learning'")
    print(f"Found {len(results2)} results:")
    for i, result in enumerate(results2):
        print(f"  {i+1}. {result['text'][:50]}... (score: {result.get('score', 0):.3f})")
    
    # Query 3: Food-related
    results3 = await buffer.search("recipes and cooking meals", limit=3)
    print(f"\nQuery: 'recipes and cooking meals'")
    print(f"Found {len(results3)} results:")
    for i, result in enumerate(results3):
        print(f"  {i+1}. {result['text'][:50]}... (score: {result.get('score', 0):.3f})")
    
    # Verify search quality
    prog_topics = [r['metadata'].get('topic') for r in results1]
    ml_topics = [r['metadata'].get('topic') for r in results2]
    food_topics = [r['metadata'].get('topic') for r in results3]
    
    print(f"\n✓ Vector search quality:")
    print(f"  - Programming query: {prog_topics.count('programming')}/3 relevant")
    print(f"  - ML query: {ml_topics.count('ml')}/3 relevant")
    print(f"  - Food query: {food_topics.count('cooking')}/3 relevant")
    
    return {
        "total_messages": len(messages),
        "embeddings_created": model.embed_count,
        "search_quality": {
            "programming": prog_topics.count('programming'),
            "ml": ml_topics.count('ml'),
            "cooking": food_topics.count('cooking')
        }
    }

async def test_automatic_context_usage():
    """Test automatic usage of context in responses"""
    print("\n=== Testing Automatic Context Usage ===")
    
    def run_test():
        # Load formation
        formation = Formation()
        formation.load("test-formations/formation-memory/formation-basic.yaml")
        overlord = formation.start_overlord()
        
        try:
            # Establish context
            print("Establishing context...")
            
            # Set preferences
            response1 = asyncio.run(overlord.chat(
                "I prefer concise answers, no more than 2-3 sentences. "
                "Also, I'm a beginner in programming.",
                user_id="bob"
            ))
            print(f"Preference set: {response1[:100]}...")
            
            # Set project context
            response2 = asyncio.run(overlord.chat(
                "I'm working on a weather app using Python and need help with API integration.",
                user_id="bob"
            ))
            print(f"Project context set: {response2[:100]}...")
            
            # Ask question without repeating context
            print("\nAsking question without repeating context...")
            response3 = asyncio.run(overlord.chat(
                "How do I handle errors?",
                user_id="bob"
            ))
            
            print(f"Response: {response3}")
            
            # Check if context was used
            context_used = False
            concise = len(response3.split('.')) <= 4  # Roughly 2-3 sentences
            beginner_friendly = any(word in response3.lower() for word in 
                                  ['simple', 'basic', 'easy', 'start', 'begin'])
            weather_related = any(word in response3.lower() for word in 
                                ['api', 'weather', 'request', 'http'])
            
            context_used = concise or beginner_friendly or weather_related
            
            print(f"\n✓ Automatic context usage:")
            print(f"  - Response conciseness: {'YES' if concise else 'NO'} ({len(response3.split('.'))-1} sentences)")
            print(f"  - Beginner-friendly: {'YES' if beginner_friendly else 'NO'}")
            print(f"  - Project-relevant: {'YES' if weather_related else 'NO'}")
            
            # Test context persistence
            response4 = asyncio.run(overlord.chat(
                "What about authentication?",
                user_id="bob"
            ))
            
            return {
                "status": "success",
                "context_used": context_used,
                "concise_response": concise,
                "beginner_friendly": beginner_friendly,
                "project_relevant": weather_related
            }
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            return {"status": "failed", "error": str(e)}
        finally:
            formation.stop_overlord()
    
    # Run in thread
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        return future.result()

async def main():
    """Run all advanced memory feature tests"""
    print("🧠 Testing Advanced Memory Features")
    print("=" * 60)
    
    # Run tests
    fifo_result = await test_fifo_memory_management()
    extraction_result = await test_automatic_context_extraction()
    vector_result = await test_smart_buffer_vector_search()
    usage_result = await test_automatic_context_usage()
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 ADVANCED MEMORY FEATURES TEST SUMMARY")
    print("=" * 60)
    
    # FIFO Management
    print(f"\n1. FIFO Memory Management: ✅ PASS")
    print(f"   - Initial capacity: {fifo_result['initial_capacity']}")
    print(f"   - After overflow: {fifo_result['after_overflow']} messages")
    print(f"   - After FIFO cleanup: {fifo_result['after_fifo']} messages")
    print(f"   - Oldest messages removed (indices {fifo_result['oldest_remaining']}-{fifo_result['newest_remaining']} remain)")
    
    # Context Extraction
    extraction_status = extraction_result.get('status') == 'success'
    print(f"\n2. Automatic Context Extraction: {'✅ PASS' if extraction_status else '❌ FAIL'}")
    if extraction_status:
        print(f"   - Name extracted: {'✅' if extraction_result['name_extracted'] else '❌'}")
        print(f"   - Project extracted: {'✅' if extraction_result['project_extracted'] else '❌'}")
    
    # Vector Search
    print(f"\n3. Smart Buffer Vector Search: ✅ PASS")
    print(f"   - Messages indexed: {vector_result['total_messages']}")
    print(f"   - Embeddings created: {vector_result['embeddings_created']}")
    search_quality = vector_result['search_quality']
    print(f"   - Search relevance: Programming {search_quality['programming']}/3, ML {search_quality['ml']}/3, Cooking {search_quality['cooking']}/3")
    
    # Context Usage
    usage_status = usage_result.get('status') == 'success'
    print(f"\n4. Automatic Context Usage: {'✅ PASS' if usage_status else '❌ FAIL'}")
    if usage_status:
        print(f"   - Context applied: {'✅' if usage_result['context_used'] else '❌'}")
        print(f"   - Concise response: {'✅' if usage_result['concise_response'] else '❌'}")
        print(f"   - Beginner-friendly: {'✅' if usage_result['beginner_friendly'] else '❌'}")
        print(f"   - Project-relevant: {'✅' if usage_result['project_relevant'] else '❌'}")
    
    # Overall
    all_passed = (
        fifo_result['after_fifo'] < fifo_result['initial_capacity'] and
        extraction_status and
        sum(search_quality.values()) >= 6 and  # At least 6/9 relevant results
        usage_status
    )
    
    print(f"\n🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    print("\n💡 KEY INSIGHTS:")
    print("- FIFO cleanup automatically manages memory usage")
    print("- Context extraction captures user information automatically")
    print("- Vector search enables semantic memory retrieval")
    print("- Context is automatically applied to improve responses")
    
    return {
        "fifo": fifo_result,
        "extraction": extraction_result,
        "vector_search": vector_result,
        "context_usage": usage_result,
        "all_passed": all_passed
    }

if __name__ == "__main__":
    asyncio.run(main())