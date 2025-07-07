"""
Test 3B3: Audio Metadata Extraction
Tests the system's ability to extract and analyze audio metadata and properties.
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
async def formation():
    """Load multimodal test formation"""
    # Load the directory, not the file, to enable agent auto-discovery
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


def test_audio_format_analysis(overlord):
    """Test analysis of audio format and properties"""
    print("\n=== Test 3B3: Audio Format Analysis ===")
    
    # Simulate audio format analysis
    upload_response = get_response(
        overlord.chat(
            user_id="test_user_format",
            message="I analyzed an audio file with these properties: "
                    "Format: WAV (PCM), Sample Rate: 44.1 kHz, Bit Depth: 16-bit, "
                    "Channels: Stereo, Duration: 12:34, File Size: 132 MB. "
                    "The audio appears to be a podcast recording with good quality. "
                    "Please explain what these technical properties mean for audio quality.",
            use_async=False
        )
    )
    
    print(f"Audio Format Response: {upload_response}")
    
    # Verify response
    assert upload_response, "Should receive a response"
    assert len(upload_response) > 50, "Response should contain format analysis"
    
    # Response should mention audio properties
    response_lower = upload_response.lower()
    audio_properties = ['audio', 'format', 'wav', 'sound', 'quality', 'sample']
    matches = sum(1 for word in audio_properties if word in response_lower)
    assert matches >= 2, f"Response should mention audio properties, found {matches}"


def test_podcast_content_structure(overlord):
    """Test analysis of podcast content structure"""
    print("\n=== Test 3B3: Podcast Content Structure ===")
    
    # Simulate podcast structure analysis
    upload_response = get_response(
        overlord.chat(
            user_id="test_user_podcast",
            message="I analyzed a podcast audio file and found this structure: "
                    "1. Intro music (0:00-0:30) with upbeat jingle "
                    "2. Host introduction (0:30-2:00) - single speaker "
                    "3. Guest interview segment (2:00-25:00) - two speakers in dialogue "
                    "4. Sponsor messages (25:00-26:30) - different voice "
                    "5. Closing remarks (26:30-28:00) - host only "
                    "6. Outro music (28:00-28:30). "
                    "Describe this podcast structure and any insights about the content format.",
            use_async=False
        )
    )
    
    print(f"Podcast Structure Response: {upload_response}")
    
    # Verify response
    assert upload_response, "Should receive a response"
    assert len(upload_response) > 100, "Response should contain detailed analysis"
    
    # Response should describe content structure
    response_lower = upload_response.lower()
    structure_words = ['podcast', 'segment', 'structure', 'content', 'section', 'audio']
    matches = sum(1 for word in structure_words if word in response_lower)
    assert matches >= 2, f"Response should describe structure, found {matches}"


def test_audio_duration_analysis(overlord):
    """Test analysis of audio duration and pacing"""
    print("\n=== Test 3B3: Audio Duration Analysis ===")
    
    user_id = "test_user_duration"
    
    # Analyze short audio
    response1 = get_response(
        overlord.chat(
            user_id=user_id,
            message="I analyzed a short audio file: Duration 10 seconds, appears to be a voice note. "
                    "The speaker talks quickly, covering 3 key points in rapid succession. "
                    "Comment on the pacing and effectiveness of such short audio messages.",
            use_async=False
        )
    )
    
    print(f"Short Audio Analysis: {response1}")
    
    # Analyze longer audio comparison
    response2 = get_response(
        overlord.chat(
            user_id=user_id,
            message="I now analyzed a longer audio file: Duration 2 minutes 15 seconds, a meeting recording. "
                    "This has a slower pace with pauses between speakers. "
                    "How does this duration and pacing compare to the previous 10-second voice note?",
            use_async=False
        )
    )
    
    print(f"Long Audio Comparison: {response2}")
    
    # Verify duration awareness
    assert response2, "Should receive a response"
    response_lower = response2.lower()
    duration_words = ['duration', 'length', 'long', 'short', 'time', 'minute']
    matches = sum(1 for word in duration_words if word in response_lower)
    assert matches >= 1, f"Response should discuss duration, found {matches}"


def test_audio_quality_assessment(overlord):
    """Test assessment of audio quality"""
    print("\n=== Test 3B3: Audio Quality Assessment ===")
    
    # Simulate audio quality analysis
    upload_response = get_response(
        overlord.chat(
            user_id="test_user_quality",
            message="I analyzed the audio quality of a speech recording: "
                    "Clarity: Excellent - crisp vocal reproduction with no distortion. "
                    "Background noise: Minimal - slight room tone but no distracting sounds. "
                    "Dynamic range: Good - voice levels consistent throughout. "
                    "Production quality: Professional - appears to use quality microphone and acoustic treatment. "
                    "Overall assessment: Broadcast-quality recording suitable for podcast or presentation. "
                    "What makes this a high-quality audio recording?",
            use_async=False
        )
    )
    
    print(f"Audio Quality Response: {upload_response}")
    
    # Verify quality assessment
    assert upload_response, "Should receive a response"
    response_lower = upload_response.lower()
    quality_words = ['quality', 'clear', 'audio', 'sound', 'noise', 'recording']
    matches = sum(1 for word in quality_words if word in response_lower)
    assert matches >= 2, f"Response should assess quality, found {matches}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])