"""
Test 3B4 with Webhooks: Long Audio Async Processing
Tests the system's understanding of processing long audio files asynchronously with webhook support.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
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


def test_long_audio_async_processing_with_webhooks(overlord):
    """Test understanding of long audio async processing with webhook support"""
    print("\n=== Test 3B4 with Webhooks: Long Audio Async Processing ===")
    
    # Test conceptual understanding of long audio processing
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_audio_async",
            message="If I had a 3-hour podcast audio file, how would you process it efficiently? What challenges might arise?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['chunk', 'stream', 'memory', 'process', 'segment', 'time', 'large', 'efficient', 'hour', 'long'],
        min_keywords=3,
        min_length=100,
        test_name="Long Audio Processing"
    )
    
    print(f"Long Audio Processing Complete - Async: {is_async}")


def test_audio_processing_memory_with_webhooks(overlord):
    """Test memory retention about audio processing discussion with webhook support"""
    print("\n=== Test 3B4 with Webhooks: Audio Processing Memory ===")
    
    # First, establish context about audio processing
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_audio_memory",
            message="I'm working with podcast transcription. The files are usually 60-90 minutes long."
        )
    )
    
    # Check first response
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['podcast', 'transcription', 'audio', 'file'],
        min_keywords=1,
        min_length=20,
        test_name="Audio Context Setup"
    )
    
    # Then ask about optimization
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_audio_memory",
            message="What's the best approach for the files I mentioned?"
        )
    )
    
    # Check memory response - should remember context
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['podcast', 'minute', 'transcription', 'audio', '60', '90'],
        min_keywords=1,
        min_length=30,
        test_name="Audio Memory Test"
    )
    
    print(f"Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


def test_async_audio_request_with_webhooks(overlord):
    """Test actual async processing for long audio request with webhook support"""
    print("\n=== Test 3B4 with Webhooks: Async Audio Request ===")
    
    # Request processing for a complex audio task (likely to be async)
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_async_audio",
            message="Please create a detailed plan for processing a 5-hour audio recording, including: 1) Transcription strategy, 2) Speaker diarization approach, 3) Content summarization, 4) Keyword extraction, 5) Quality assessment. Make it comprehensive."
        )
    )
    
    # Use universal webhook checker - expect this to be complex enough for async
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['transcription', 'strategy', 'plan', 'processing', 'audio', 'hour'],
        min_keywords=3,
        min_length=300,
        timeout=45.0,  # Give more time for this complex request
        test_name="Async Audio Plan"
    )
    
    print(f"Async Audio Request Complete - Async: {is_async}")


def test_audio_format_understanding_with_webhooks(overlord):
    """Test understanding of different audio formats and their processing implications with webhook support"""
    print("\n=== Test 3B4 with Webhooks: Audio Format Understanding ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_formats",
            message="What are the differences in processing WAV, MP3, and M4A audio files? How does format affect transcription quality and processing time?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['wav', 'mp3', 'm4a', 'compression', 'quality', 'format', 'lossless', 'lossy'],
        min_keywords=4,
        min_length=50,
        test_name="Audio Format Understanding"
    )
    
    print(f"Format Understanding Complete - Async: {is_async}")


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
            test_long_audio_async_processing_with_webhooks(overlord)
            test_audio_processing_memory_with_webhooks(overlord)
            test_async_audio_request_with_webhooks(overlord)
            test_audio_format_understanding_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())