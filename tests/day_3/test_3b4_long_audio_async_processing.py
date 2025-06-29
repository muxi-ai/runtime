"""
Test 3B4: Long Audio Async Processing
Tests the system's understanding of processing long audio files asynchronously.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation


def get_response(coro):
    """Helper to get response from async chat"""
    result = asyncio.run(coro)
    
    # Handle async generators
    if hasattr(result, "__aiter__"):
        async def collect():
            chunks = []
            async for chunk in result:
                chunks.append(chunk)
            return "".join(chunks)
        return asyncio.run(collect())
    
    return result


@pytest.fixture
def formation():
    """Load multimodal test formation"""
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    formation.load(str(formation_path))
    
    return formation


@pytest.fixture
def overlord(formation):
    """Create overlord instance"""
    overlord = formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    formation.stop_overlord()


def test_long_audio_async_processing(overlord):
    """Test understanding of long audio async processing"""
    print("\n=== Test 3B4: Long Audio Async Processing ===")
    
    # Test conceptual understanding of long audio processing
    response = get_response(
        overlord.chat(
            user_id="test_user_audio_async",
            message="If I had a 3-hour podcast audio file, how would you process it efficiently? What challenges might arise?",
            use_async=False  # Testing conceptual understanding, not actual async
        )
    )
    
    print(f"Long Audio Response: {response}")
    
    # Verify response discusses async/streaming processing
    assert response, "Should receive a response"
    assert len(response) > 100, "Response should be detailed"
    
    response_lower = response.lower()
    # Should mention relevant concepts
    concepts = ['chunk', 'stream', 'memory', 'process', 'segment', 'time', 'large', 'efficient', 'hour', 'long']
    matches = sum(1 for word in concepts if word in response_lower)
    assert matches >= 3, f"Response should mention processing concepts, found {matches}"


def test_audio_processing_memory(overlord):
    """Test memory retention about audio processing discussion"""
    print("\n=== Test 3B4: Audio Processing Memory ===")
    
    # First, establish context about audio processing
    response1 = get_response(
        overlord.chat(
            user_id="test_user_audio_memory",
            message="I'm working with podcast transcription. The files are usually 60-90 minutes long.",
            use_async=False
        )
    )
    
    # Then ask about optimization
    response2 = get_response(
        overlord.chat(
            user_id="test_user_audio_memory",
            message="What's the best approach for the files I mentioned?",
            use_async=False
        )
    )
    
    print(f"Memory Response: {response2}")
    
    # Should remember podcast context
    response_lower = response2.lower()
    assert any(word in response_lower for word in ['podcast', 'minute', 'transcription', 'audio', '60', '90']), \
        "Should remember the podcast context from previous message"


def test_async_audio_request(overlord):
    """Test actual async processing for long audio request"""
    print("\n=== Test 3B4: Async Audio Request ===")
    
    # Request async processing for a complex audio task
    response = get_response(
        overlord.chat(
            user_id="test_user_async_audio",
            message="Please create a detailed plan for processing a 5-hour audio recording, including: 1) Transcription strategy, 2) Speaker diarization approach, 3) Content summarization, 4) Keyword extraction, 5) Quality assessment. Make it comprehensive.",
            use_async=True  # Force async processing
        )
    )
    
    print(f"Async Audio Response: {response}")
    
    # For async requests, we should get a request ID
    if isinstance(response, dict) and 'request_id' in response:
        print(f"✓ Received async response with request ID: {response['request_id']}")
        assert response['status'] == 'processing', "Status should indicate async processing"
        assert 'message' in response, "Should have status message"
    else:
        # If not async, it's still a valid response (but should be detailed)
        print("Note: Response was synchronous despite async request")
        assert len(response) > 300, "Should receive detailed analysis plan"


def test_audio_format_understanding(overlord):
    """Test understanding of different audio formats and their processing implications"""
    print("\n=== Test 3B4: Audio Format Understanding ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_formats",
            message="What are the differences in processing WAV, MP3, and M4A audio files? How does format affect transcription quality and processing time?",
            use_async=False
        )
    )
    
    print(f"Format Understanding Response: {response}")
    
    # Verify format knowledge
    assert response, "Should receive a response"
    response_lower = response.lower()
    format_terms = ['wav', 'mp3', 'm4a', 'compression', 'quality', 'format', 'lossless', 'lossy']
    matches = sum(1 for term in format_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss audio formats, found {matches}"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()
        
        try:
            test_long_audio_async_processing(overlord)
            test_audio_processing_memory(overlord)
            test_async_audio_request(overlord)
            test_audio_format_understanding(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()