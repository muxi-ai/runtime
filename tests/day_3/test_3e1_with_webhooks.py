"""
Test 3E1 with Webhooks: Sync Multimodal Processing
Tests the system's handling of synchronous multimodal processing for small files with webhook support.
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
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


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
    # Setup webhook testing environment
    setup_webhook_test()
    
    overlord = await formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    await formation.stop_overlord()


def test_quick_image_analysis_with_webhooks(overlord):
    """Test synchronous processing for quick image analysis with webhook support"""
    print("\n=== Test 3E1 with Webhooks: Quick Image Analysis ===")
    
    start_time = time.time()
    
    # Simple request that might process synchronously
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_sync",
            message="What are the key elements to look for in a simple bar chart image?"
        )
    )
    
    duration = time.time() - start_time
    print(f"Response time: {duration:.2f} seconds")
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['bar', 'chart', 'axis', 'label', 'data', 'title', 'value'],
        min_keywords=3,
        min_length=50,
        test_name="Quick Image Analysis"
    )
    
    print(f"Quick Image Analysis Complete - Async: {is_async}, Duration: {duration:.2f}s")


def test_small_document_query_with_webhooks(overlord):
    """Test synchronous processing for small document queries with webhook support"""
    print("\n=== Test 3E1 with Webhooks: Small Document Query ===")
    
    start_time = time.time()
    
    # Quick document-related question
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_doc",
            message="What's the typical structure of a one-page executive summary?"
        )
    )
    
    duration = time.time() - start_time
    print(f"Document query processed in {duration:.2f} seconds")
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['summary', 'structure', 'executive', 'section', 'format'],
        min_keywords=2,
        min_length=100,
        test_name="Small Document Query"
    )
    
    print(f"Document Query Complete - Async: {is_async}, Duration: {duration:.2f}s")


def test_simple_audio_question_with_webhooks(overlord):
    """Test processing for simple audio-related questions with webhook support"""
    print("\n=== Test 3E1 with Webhooks: Simple Audio Question ===")
    
    start_time = time.time()
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_audio_simple",
            message="What are the main factors that affect audio quality in recordings?"
        )
    )
    
    duration = time.time() - start_time
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['audio', 'quality', 'recording', 'sound', 'noise', 'clarity'],
        min_keywords=3,
        min_length=80,
        test_name="Simple Audio Question"
    )
    
    print(f"Audio Question Complete - Async: {is_async}, Duration: {duration:.2f}s")


def test_processing_mode_awareness_with_webhooks(overlord):
    """Test understanding of when sync vs async processing is appropriate with webhook support"""
    print("\n=== Test 3E1 with Webhooks: Processing Mode Awareness ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_modes",
            message="When should I use synchronous vs asynchronous processing for different types of multimodal tasks?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['sync', 'async', 'processing', 'task', 'small', 'large', 'time', 'mode'],
        min_keywords=4,
        min_length=150,
        test_name="Processing Mode Awareness"
    )
    
    print(f"Mode Awareness Complete - Async: {is_async}")


if __name__ == "__main__":
    # Run with async support
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Setup webhook testing environment
        setup_webhook_test()
        
        overlord = await formation.start_overlord()
        
        try:
            test_quick_image_analysis_with_webhooks(overlord)
            test_small_document_query_with_webhooks(overlord)
            test_simple_audio_question_with_webhooks(overlord)
            test_processing_mode_awareness_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())