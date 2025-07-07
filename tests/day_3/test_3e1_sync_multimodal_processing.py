"""
Test 3E1: Sync Multimodal Processing
Tests the system's handling of synchronous multimodal processing for small files.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    await formation.load(str(formation_path))
    
    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    overlord = await formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    await formation.stop_overlord()


def test_quick_image_analysis(overlord):
    """Test synchronous processing for quick image analysis"""
    print("\n=== Test 3E1: Quick Image Analysis ===")
    
    start_time = time.time()
    
    # Simple request that should process synchronously
    response = get_response(
        overlord.chat(
            user_id="test_user_sync",
            message="What are the key elements to look for in a simple bar chart image?",
            use_async=False  # Force sync
        )
    )
    
    duration = time.time() - start_time
    print(f"Response time: {duration:.2f} seconds")
    print(f"Sync Response: {response}")
    
    # Verify synchronous processing
    assert isinstance(response, str), "Should receive direct string response"
    assert len(response) > 50, "Response should be meaningful"
    assert duration < 10, "Sync processing should be relatively quick"
    
    # Content verification
    response_lower = response.lower()
    chart_terms = ['bar', 'chart', 'axis', 'label', 'data', 'title', 'value']
    matches = sum(1 for term in chart_terms if term in response_lower)
    assert matches >= 3, f"Response should mention chart elements, found {matches}"


def test_small_document_query(overlord):
    """Test synchronous processing for small document queries"""
    print("\n=== Test 3E1: Small Document Query ===")
    
    start_time = time.time()
    
    # Quick document-related question
    response = get_response(
        overlord.chat(
            user_id="test_user_doc",
            message="What's the typical structure of a one-page executive summary?",
            use_async=False
        )
    )
    
    duration = time.time() - start_time
    print(f"Document query processed in {duration:.2f} seconds")
    
    # Verify quick sync response
    assert isinstance(response, str), "Should be synchronous string response"
    assert duration < 15, "Should process quickly"
    assert len(response) > 100, "Should provide detailed structure information"


def test_sync_multimodal_concepts(overlord):
    """Test synchronous handling of multimodal concept questions"""
    print("\n=== Test 3E1: Sync Multimodal Concepts ===")
    
    # Quick multimodal understanding question
    response = get_response(
        overlord.chat(
            user_id="test_user_concepts",
            message="Can you quickly list the main differences between analyzing images versus audio files?",
            use_async=False
        )
    )
    
    print(f"Concept Response: {response}")
    
    # Verify response covers both modalities
    response_lower = response.lower()
    assert 'image' in response_lower and 'audio' in response_lower, \
        "Should mention both modalities"
    assert any(term in response_lower for term in ['visual', 'pixel', 'color', 'spatial']), \
        "Should mention image characteristics"
    assert any(term in response_lower for term in ['sound', 'frequency', 'time', 'wave']), \
        "Should mention audio characteristics"


def test_sync_memory_recall(overlord):
    """Test synchronous memory recall for multimodal content"""
    print("\n=== Test 3E1: Sync Memory Recall ===")
    
    # Establish context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_recall",
            message="I'm working with a 2-page PDF and a small PNG icon file.",
            use_async=False
        )
    )
    
    start_time = time.time()
    
    # Quick recall question
    response2 = get_response(
        overlord.chat(
            user_id="test_user_recall",
            message="What file types did I mention?",
            use_async=False
        )
    )
    
    duration = time.time() - start_time
    print(f"Memory recall in {duration:.2f} seconds")
    print(f"Recall Response: {response2}")
    
    # Should quickly recall the file types
    assert duration < 5, "Memory recall should be very fast"
    response_lower = response2.lower()
    assert 'pdf' in response_lower, "Should recall PDF"
    assert 'png' in response_lower, "Should recall PNG"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        try:
            test_quick_image_analysis(overlord)
            test_small_document_query(overlord)
            test_sync_multimodal_concepts(overlord)
            test_sync_memory_recall(overlord)
            print("\nAll tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())
        future = executor.submit(run_test)
        future.result()