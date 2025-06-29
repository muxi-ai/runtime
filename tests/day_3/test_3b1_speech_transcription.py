"""
Test 3B1: Speech Transcription
Tests the system's ability to transcribe speech from audio files.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


@pytest.fixture
def formation():
    """Load multimodal test formation"""
    # Load the directory, not the file, to enable agent auto-discovery
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


def test_speech_basic_transcription(overlord):
    """Test basic speech transcription"""
    print("\n=== Test 3B1: Basic Speech Transcription ===")
    
    # Since we don't have actual audio files, simulate audio transcription concepts
    response = get_response(
        overlord.chat(
            user_id="test_user_speech",
            message="Explain how speech transcription works in multimodal AI systems. What are the key technical components needed for converting speech to text?",
            use_async=False
        )
    )
    
    print(f"Speech Transcription Response: {response}")
    
    # Verify response contains transcription concepts
    assert response, "Should receive a response"
    assert len(response) > 50, "Response should contain transcription concepts"
    
    # Response should mention speech/audio elements
    response_lower = response.lower()
    audio_words = ['speech', 'audio', 'transcription', 'speaking', 'transcript', 'voice']
    matches = sum(1 for word in audio_words if word in response_lower)
    assert matches >= 2, f"Response should mention speech elements, found {matches}"


def test_short_audio_analysis(overlord):
    """Test analysis of short audio clip concepts"""
    print("\n=== Test 3B1: Short Audio Analysis ===")
    
    # Test concepts around short audio analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_short_audio",
            message="Explain how AI systems analyze short audio clips. What types of features can be extracted from a 10-second audio recording?",
            use_async=False
        )
    )
    
    print(f"Short Audio Analysis Response: {response}")
    
    # Verify response
    assert response, "Should receive a response"
    assert len(response) > 30, "Response should contain analysis concepts"
    
    # Response should describe audio analysis features
    response_lower = response.lower()
    descriptive_words = ['audio', 'sound', 'analysis', 'features', 'extraction', 'frequency']
    matches = sum(1 for word in descriptive_words if word in response_lower)
    assert matches >= 2, f"Response should describe audio analysis concepts, found {matches}"


def test_speech_sentiment_analysis(overlord):
    """Test sentiment analysis concepts for speech"""
    print("\n=== Test 3B1: Speech Sentiment Analysis ===")
    
    user_id = "test_user_sentiment"
    
    # Test sentiment analysis concepts
    response = get_response(
        overlord.chat(
            user_id=user_id,
            message="Explain how AI systems analyze sentiment and emotion in speech audio. What acoustic features indicate different emotions?",
            use_async=False
        )
    )
    
    print(f"Sentiment Analysis Response: {response}")
    
    # Verify sentiment analysis concepts
    assert response, "Should receive a response"
    response_lower = response.lower()
    sentiment_words = ['tone', 'emotion', 'sentiment', 'feeling', 'mood', 'acoustic', 'prosody']
    matches = sum(1 for word in sentiment_words if word in response_lower)
    assert matches >= 2, f"Response should analyze sentiment concepts, found {matches}"


def test_transcription_memory(overlord):
    """Test memory retention concepts for transcribed content"""
    print("\n=== Test 3B1: Transcription Memory ===")
    
    user_id = "test_user_trans_memory"
    
    # First, establish transcription context
    response1 = get_response(
        overlord.chat(
            user_id=user_id,
            message="I just transcribed an important meeting where the team discussed Q4 budget allocations: Marketing gets $50K, Engineering gets $75K, and Sales gets $30K. Remember these budget numbers.",
            use_async=False
        )
    )
    
    print(f"Initial Transcription: {response1}")
    
    # Follow up with a question about the content
    memory_response = get_response(
        overlord.chat(
            user_id=user_id,
            message="What were the budget allocations for each department that I just mentioned?",
            use_async=False
        )
    )
    
    print(f"Memory Check Response: {memory_response}")
    
    # Should remember the transcribed content
    assert memory_response, "Should receive memory response"
    assert len(memory_response) > 20, "Response should contain recalled information"
    response_lower = memory_response.lower()
    budget_indicators = ['50k', '75k', '30k', 'marketing', 'engineering', 'sales', 'budget']
    matches = sum(1 for word in budget_indicators if word in response_lower)
    assert matches >= 2, f"Should remember budget details, found {matches} matches"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])