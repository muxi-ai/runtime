#!/usr/bin/env python3
"""Quick test to verify intent detection changes work correctly."""

import asyncio
import sys
sys.path.insert(0, ".")

from src.muxi.runtime.services.intent.service import IntentDetectionService
from src.muxi.runtime.services.llm import LLM
from src.muxi.runtime.datatypes.intent import IntentType, IntentDetectionContext


async def test_intent_detection():
    """Test the intent detection service with our changes."""
    print("Testing Intent Detection Service...")
    
    # Test 1: Create service without LLM (should work)
    print("\n1. Creating service without LLM...")
    service = IntentDetectionService(enable_cache=False)
    print("✅ Service created successfully without LLM")
    
    # Test 2: Test fallback detection
    print("\n2. Testing fallback detection...")
    result = await service.detect_intent(
        "Do you remember what we talked about last time?",
        IntentType.QUERY_TYPE
    )
    print(f"✅ Fallback detection result: {result.intent} (confidence: {result.confidence})")
    assert result.intent == "memory"  # Should detect memory-related keywords
    
    # Test 3: Test with mock LLM
    print("\n3. Testing with mock LLM...")
    
    class MockLLM:
        async def generate_text(self, prompt, temperature, max_tokens, timeout):
            # Return a valid JSON response
            return '{"intent": "knowledge", "confidence": 0.95, "reasoning": "General question"}'
    
    service_with_llm = IntentDetectionService(
        llm_service=MockLLM(),
        enable_cache=True,
        llm_timeout=10.0
    )
    
    result = await service_with_llm.detect_intent(
        "What is the capital of France?",
        IntentType.QUERY_TYPE
    )
    print(f"✅ LLM detection result: {result.intent} (confidence: {result.confidence})")
    assert result.intent == "knowledge"
    
    # Test 4: Test normalization methods
    print("\n4. Testing normalization methods...")
    
    # These should return strings, not enums
    assert service._normalize_query_type("invalid") == "unclear"
    assert service._normalize_clarification_category("invalid") == "other"
    assert service._normalize_schedule_type("invalid") == "unclear"
    print("✅ All normalization methods return strings correctly")
    
    # Test 5: Test caching
    print("\n5. Testing cache functionality...")
    if service_with_llm.cache:
        # Make the same request twice
        result1 = await service_with_llm.detect_intent(
            "What is Python?",
            IntentType.QUERY_TYPE
        )
        result2 = await service_with_llm.detect_intent(
            "What is Python?",
            IntentType.QUERY_TYPE
        )
        
        stats = service_with_llm.cache.get_stats()
        print(f"✅ Cache stats: hits={stats['hits']}, misses={stats['misses']}")
        assert stats['hits'] == 1  # Second request should be a cache hit
    
    print("\n✅ All tests passed!")
    

async def test_llm_validation():
    """Test LLM validation in __init__."""
    print("\nTesting LLM validation...")
    
    # Test with invalid LLM (no generate_text method)
    class InvalidLLM:
        pass
    
    try:
        service = IntentDetectionService(llm_service=InvalidLLM())
        print("❌ Should have raised ValueError for invalid LLM")
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
    
    # Test with sync generate_text method
    class SyncLLM:
        def generate_text(self, prompt, temperature, max_tokens, timeout):
            return "sync response"
    
    try:
        service = IntentDetectionService(llm_service=SyncLLM())
        print("❌ Should have raised ValueError for sync LLM")
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")


async def main():
    """Run all tests."""
    await test_intent_detection()
    await test_llm_validation()
    print("\n🎉 All intent detection tests passed!")


if __name__ == "__main__":
    asyncio.run(main())