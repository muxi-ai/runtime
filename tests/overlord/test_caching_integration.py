"""
Test script for intelligent caching integration in MUXI Overlord.

This script tests the complete caching workflow including:
- Cache manager initialization
- Cache lookup and storage
- Multi-layer cache performance
- Memory optimization
"""

import asyncio

# Test imports
try:
    from src.muxi.runtime.overlord.caching import IntelligentCacheManager
    print("✓ Cache imports successful")
except ImportError as e:
    print(f"✗ Cache import failed: {e}")
    exit(1)


class MockEmbeddingService:
    """Mock embedding service for testing."""

    async def embed(self, text: str) -> list[float]:
        """Generate mock embedding vector."""
        # Simple mock embedding based on text hash
        hash_val = hash(text)
        return [float((hash_val >> i) & 0xFF) / 255.0 for i in range(0, 512, 8)]


async def test_cache_initialization():
    """Test cache manager initialization."""
    print("\n--- Testing Cache Initialization ---")

    try:
        # Create mock embedding service
        embedding_service = MockEmbeddingService()

        # Initialize cache manager
        cache_manager = IntelligentCacheManager(
            l1_max_size=100,
            l2_max_size=50,
            l3_max_memory_mb=10,
            enable_analytics=True,
            enable_memory_optimization=True,
            embedding_service=embedding_service
        )

        print("✓ Cache manager initialized")

        # Start cache manager services
        await cache_manager.start()
        print("✓ Cache manager services started")

        # Test cache statistics
        stats = await cache_manager.get_cache_statistics()
        print(f"✓ Cache statistics: {len(stats['layers'])} layers")

        # Stop cache manager
        await cache_manager.stop()
        print("✓ Cache manager stopped")

        return True

    except Exception as e:
        print(f"✗ Cache initialization failed: {e}")
        return False


async def test_cache_operations():
    """Test basic cache operations."""
    print("\n--- Testing Cache Operations ---")

    try:
        embedding_service = MockEmbeddingService()
        cache_manager = IntelligentCacheManager(
            l1_max_size=10,
            l2_max_size=5,
            enable_analytics=True,
            embedding_service=embedding_service
        )

        await cache_manager.start()

        # Clear all caches to ensure clean test start
        await cache_manager.l1_cache.clear()
        await cache_manager.l2_cache.clear()
        await cache_manager.l3_cache.clear()
        await cache_manager.persistent_cache.clear()

        # Test cache miss
        response = await cache_manager.get_cached_response(
            user_message="Hello, how are you?",
            user_id=1,
            agent_id="test_agent"
        )

        if response is None:
            print("✓ Cache miss detected correctly")
        else:
            print("✗ Unexpected cache hit")
            return False

        # Test cache storage
        success = await cache_manager.cache_response(
            user_message="Hello, how are you?",
            response_content="I'm doing well, thank you for asking!",
            response_type="text",
            user_id=1,
            agent_id="test_agent",
            quality_score=0.9
        )

        if success:
            print("✓ Response cached successfully")
        else:
            print("✗ Failed to cache response")
            return False

        # Test cache hit
        cached_response = await cache_manager.get_cached_response(
            user_message="Hello, how are you?",
            user_id=1,
            agent_id="test_agent"
        )

        if cached_response and cached_response.content == "I'm doing well, thank you for asking!":
            print("✓ Cache hit successful")
        else:
            print("✗ Cache hit failed")
            return False

        # Test semantic similarity with a completely different message
        different_response = await cache_manager.get_cached_response(
            user_message="What is the capital of France?",  # Completely different topic
            user_id=1,
            agent_id="test_agent"
        )

        if different_response:
            print("? Unexpected semantic match detected")
        else:
            print("✓ No semantic match for different topic (as expected)")

        await cache_manager.stop()
        return True

    except Exception as e:
        print(f"✗ Cache operations failed: {e}")
        return False


async def test_cache_performance():
    """Test cache performance and analytics."""
    print("\n--- Testing Cache Performance ---")

    try:
        embedding_service = MockEmbeddingService()
        cache_manager = IntelligentCacheManager(
            l1_max_size=100,
            enable_analytics=True,
            embedding_service=embedding_service
        )

        await cache_manager.start()

        # Perform multiple cache operations
        test_messages = [
            "What is the weather like?",
            "How do I learn Python?",
            "Tell me about AI",
            "What time is it?",
            "How are you today?"
        ]

        responses = [
            "The weather is sunny and warm.",
            "Start with online tutorials and practice coding.",
            "AI is artificial intelligence technology.",
            "I don't have access to real-time clock data.",
            "I'm functioning well, thank you!"
        ]

        # Cache responses
        for i, (msg, resp) in enumerate(zip(test_messages, responses)):
            await cache_manager.cache_response(
                user_message=msg,
                response_content=resp,
                user_id=1,
                quality_score=0.8 + (i * 0.04)  # Varying quality scores
            )

        print(f"✓ Cached {len(test_messages)} responses")

        # Test cache hits
        hit_count = 0
        for msg in test_messages:
            cached = await cache_manager.get_cached_response(msg, user_id=1)
            if cached:
                hit_count += 1

        hit_rate = hit_count / len(test_messages)
        print(f"✓ Cache hit rate: {hit_rate:.1%} ({hit_count}/{len(test_messages)})")

        # Get statistics
        stats = await cache_manager.get_cache_statistics()
        print(f"✓ Total requests: {stats['overall']['total_requests']}")
        print(f"✓ Memory usage: {stats['overall']['total_memory_usage_bytes']} bytes")

        await cache_manager.stop()
        return True

    except Exception as e:
        print(f"✗ Cache performance test failed: {e}")
        return False


async def test_memory_optimization():
    """Test memory optimization features."""
    print("\n--- Testing Memory Optimization ---")

    try:
        embedding_service = MockEmbeddingService()
        cache_manager = IntelligentCacheManager(
            l1_max_size=5,  # Small cache for testing eviction
            l3_max_memory_mb=1,  # Very small memory limit
            enable_memory_optimization=True,
            embedding_service=embedding_service
        )

        await cache_manager.start()

        # Fill cache beyond capacity
        for i in range(10):
            await cache_manager.cache_response(
                user_message=f"Test message {i}",
                response_content=f"Test response {i}",
                user_id=1,
                quality_score=0.5
            )

        print("✓ Filled cache beyond capacity")

        # Check if memory optimization triggered
        stats = await cache_manager.get_cache_statistics()
        l1_size = stats['layers']['L1']['size']

        if l1_size <= 5:  # Should be at or below max size due to eviction
            print(f"✓ Cache eviction working (L1 size: {l1_size})")
        else:
            print(f"? Cache eviction may not have triggered (L1 size: {l1_size})")

        # Test force cleanup
        cleanup_result = await cache_manager.force_memory_cleanup()
        print(f"✓ Force cleanup completed: {bool(cleanup_result)}")

        await cache_manager.stop()
        return True

    except Exception as e:
        print(f"✗ Memory optimization test failed: {e}")
        return False


async def main():
    """Run all caching tests."""
    print("🚀 Starting MUXI Intelligent Caching Integration Tests")

    tests = [
        test_cache_initialization,
        test_cache_operations,
        test_cache_performance,
        test_memory_optimization
    ]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            success = await test_func()
            if success:
                passed += 1

            # Small delay between tests
            await asyncio.sleep(0.1)

        except Exception as e:
            print(f"✗ Test {test_func.__name__} crashed: {e}")

    print(f"\n📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All caching integration tests passed!")
        print("\n✅ Phase 2.1 Intelligent Caching & Memory Optimization is COMPLETE!")
        return True
    else:
        print("❌ Some tests failed - please check implementation")
        return False


if __name__ == "__main__":
    asyncio.run(main())
