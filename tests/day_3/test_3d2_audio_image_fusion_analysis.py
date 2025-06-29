"""
Test 3D2: Audio + Image Fusion Analysis
Tests the system's understanding of analyzing audio and images together.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


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


def test_presentation_audio_slide_fusion(overlord):
    """Test understanding of fusing presentation audio with slide images"""
    print("\n=== Test 3D2: Presentation Audio-Slide Fusion ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_fusion",
            message="How would you analyze a presenter's audio narration together with their slide images to create a comprehensive understanding of the presentation?"
        )
    )
    
    print(f"Audio-Slide Fusion Response: {response}")
    
    # Verify fusion approach
    assert response, "Should receive a response"
    assert len(response) > 150, "Response should be detailed"
    
    response_lower = response.lower()
    fusion_terms = ['audio', 'slide', 'narration', 'visual', 'combine', 'together', 'comprehensive', 'match']
    matches = sum(1 for term in fusion_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss audio-visual fusion, found {matches}"


def test_podcast_image_analysis(overlord):
    """Test understanding of analyzing podcast audio with show notes images"""
    print("\n=== Test 3D2: Podcast-Image Analysis ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_podcast",
            message="If I have a podcast episode audio file and screenshots of the show notes with key topics and timestamps, how would you integrate these for better understanding?"
        )
    )
    
    print(f"Podcast-Image Analysis Response: {response}")
    
    # Verify integration concepts
    assert response, "Should receive a response"
    response_lower = response.lower()
    podcast_terms = ['podcast', 'audio', 'screenshot', 'timestamp', 'topic', 'integrate', 'notes', 'content']
    matches = sum(1 for term in podcast_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss podcast-image integration, found {matches}"


def test_audio_visual_emotion_analysis(overlord):
    """Test understanding of emotion analysis across audio and images"""
    print("\n=== Test 3D2: Audio-Visual Emotion Analysis ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_emotion",
            message="How would you analyze emotions by combining voice tone from audio and facial expressions from images of the same person?"
        )
    )
    
    print(f"Emotion Analysis Response: {response}")
    
    # Verify emotion analysis approach
    assert response, "Should receive a response"
    response_lower = response.lower()
    emotion_terms = ['emotion', 'voice', 'tone', 'facial', 'expression', 'feeling', 'mood', 'analyze']
    matches = sum(1 for term in emotion_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss emotion analysis, found {matches}"


def test_audio_image_context_memory(overlord):
    """Test memory retention about audio-image relationships"""
    print("\n=== Test 3D2: Audio-Image Context Memory ===")
    
    # Establish context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_audio_image",
            message="I'm analyzing a cooking tutorial where the audio explains the recipe steps while images show the ingredients and final dish. The chef mentions using 2 cups of flour, but the ingredient image shows 3 cups."
        )
    )
    
    # Test cross-modal memory and discrepancy detection
    response2 = get_response(
        overlord.chat(
            user_id="test_user_audio_image",
            message="What inconsistency did you notice between the audio and images I described?"
        )
    )
    
    print(f"Inconsistency Detection Response: {response2}")
    
    # Should identify the flour measurement discrepancy
    response_lower = response2.lower()
    assert any(term in response_lower for term in ['flour', 'cup', 'measurement']), \
        "Should mention the flour measurement"
    assert any(term in response_lower for term in ['2', 'two', '3', 'three']), \
        "Should mention the specific numbers"
    assert any(term in response_lower for term in ['inconsistency', 'discrepancy', 'different', 'mismatch']), \
        "Should identify it as an inconsistency"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()
        
        try:
            test_presentation_audio_slide_fusion(overlord)
            test_podcast_image_analysis(overlord)
            test_audio_visual_emotion_analysis(overlord)
            test_audio_image_context_memory(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()