"""
Test 3C3: Video Summarization
Tests the system's understanding of creating summaries from video content.
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


def test_presentation_video_summary(overlord):
    """Test understanding of presentation video summarization"""
    print("\n=== Test 3C3: Presentation Video Summary ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_summary",
            message="What key elements would you include in a summary of a technical presentation video? How would you structure it?"
        )
    )
    
    print(f"Presentation Summary Response: {response}")
    
    # Verify comprehensive summary approach
    assert response, "Should receive a response"
    assert len(response) > 150, "Response should be detailed"
    
    response_lower = response.lower()
    summary_terms = ['summary', 'key', 'point', 'main', 'topic', 'structure', 'overview', 'conclusion']
    matches = sum(1 for term in summary_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss summarization elements, found {matches}"


def test_video_highlight_extraction(overlord):
    """Test understanding of extracting highlights from video"""
    print("\n=== Test 3C3: Video Highlight Extraction ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_highlights",
            message="How would you identify and extract the most important moments or highlights from a long video recording?"
        )
    )
    
    print(f"Highlight Extraction Response: {response}")
    
    # Verify highlight extraction concepts
    assert response, "Should receive a response"
    response_lower = response.lower()
    highlight_terms = ['highlight', 'important', 'moment', 'key', 'extract', 'identify', 'significant', 'clip']
    matches = sum(1 for term in highlight_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss highlight extraction, found {matches}"


def test_multi_speaker_video_summary(overlord):
    """Test understanding of summarizing videos with multiple speakers"""
    print("\n=== Test 3C3: Multi-Speaker Video Summary ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_speakers",
            message="If a panel discussion video has 4 different speakers, how would you organize the summary to capture each person's contributions?"
        )
    )
    
    print(f"Multi-Speaker Summary Response: {response}")
    
    # Verify speaker-aware summarization
    assert response, "Should receive a response"
    response_lower = response.lower()
    speaker_terms = ['speaker', 'person', 'contribution', 'panel', 'organize', 'each', 'different', 'participant']
    matches = sum(1 for term in speaker_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss multi-speaker handling, found {matches}"


def test_video_summary_memory(overlord):
    """Test memory retention about video summarization task"""
    print("\n=== Test 3C3: Video Summary Memory ===")
    
    # Establish context about a specific video
    response1 = get_response(
        overlord.chat(
            user_id="test_user_context",
            message="I need to summarize a 45-minute training video about cybersecurity best practices. It has 5 main sections: password management, phishing, network security, data encryption, and incident response."
        )
    )
    
    # Ask for specific summary approach
    response2 = get_response(
        overlord.chat(
            user_id="test_user_context",
            message="Based on the video I described, what would be the best structure for the summary?"
        )
    )
    
    print(f"Summary Structure Response: {response2}")
    
    # Should remember the video context and sections
    response_lower = response2.lower()
    sections_mentioned = 0
    for section in ['password', 'phishing', 'network', 'encryption', 'incident']:
        if section in response_lower:
            sections_mentioned += 1
    
    assert sections_mentioned >= 3, f"Should mention at least 3 of the 5 sections, found {sections_mentioned}"
    assert any(term in response_lower for term in ['cybersecurity', 'security', 'training']), \
        "Should remember the video topic"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()
        
        try:
            test_presentation_video_summary(overlord)
            test_video_highlight_extraction(overlord)
            test_multi_speaker_video_summary(overlord)
            test_video_summary_memory(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()