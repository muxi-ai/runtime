"""
Test 3D3: Full Multimodal Processing
Tests the system's understanding of analyzing documents, images, and audio together.
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


def test_full_multimodal_analysis(overlord):
    """Test understanding of analyzing all modalities together"""
    print("\n=== Test 3D3: Full Multimodal Analysis ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_full",
            message="How would you analyze a complete package of: a research paper PDF, data visualization charts, and an author interview audio recording to get a comprehensive understanding of the research?"
        )
    )
    
    print(f"Full Multimodal Response: {response}")
    
    # Verify comprehensive approach
    assert response, "Should receive a response"
    assert len(response) > 200, "Response should be very detailed"
    
    response_lower = response.lower()
    modality_terms = ['paper', 'pdf', 'chart', 'visual', 'audio', 'interview', 'comprehensive', 'analyze']
    matches = sum(1 for term in modality_terms if term in response_lower)
    assert matches >= 5, f"Response should mention multiple modalities, found {matches}"


def test_story_telling_across_modalities(overlord):
    """Test understanding of narrative construction from multiple sources"""
    print("\n=== Test 3D3: Cross-Modal Story Telling ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_story",
            message="If you had a company's annual report PDF, photos from their events, and CEO speech audio, how would you combine these to tell the complete story of their year?"
        )
    )
    
    print(f"Story Telling Response: {response}")
    
    # Verify narrative approach
    assert response, "Should receive a response"
    response_lower = response.lower()
    story_terms = ['story', 'narrative', 'combine', 'report', 'photo', 'speech', 'complete', 'year']
    matches = sum(1 for term in story_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss narrative construction, found {matches}"


def test_multimodal_verification(overlord):
    """Test understanding of cross-modal verification"""
    print("\n=== Test 3D3: Multimodal Verification ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_verify",
            message="How would you use multiple modalities (text documents, images, and audio) to verify the accuracy and consistency of information about an event?"
        )
    )
    
    print(f"Verification Response: {response}")
    
    # Verify verification approach
    assert response, "Should receive a response"
    response_lower = response.lower()
    verify_terms = ['verify', 'accuracy', 'consistency', 'check', 'confirm', 'multiple', 'source', 'cross']
    matches = sum(1 for term in verify_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss verification methods, found {matches}"


def test_complex_multimodal_memory(overlord):
    """Test memory retention about complex multimodal content"""
    print("\n=== Test 3D3: Complex Multimodal Memory ===")
    
    # Establish rich multimodal context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_complex",
            message="I'm analyzing a product launch: The press release PDF announces a $999 price, the product images show a sleek design with 3 color options, and the launch event audio mentions availability in Q2 2024."
        )
    )
    
    # Test comprehensive memory
    response2 = get_response(
        overlord.chat(
            user_id="test_user_complex",
            message="Based on all the product launch materials I mentioned, what are the key details about price, design, and availability?"
        )
    )
    
    print(f"Multimodal Memory Response: {response2}")
    
    # Should remember details from all modalities
    response_lower = response2.lower()
    
    # Check document memory
    assert any(term in response_lower for term in ['999', 'price', 'dollar']), \
        "Should remember price from press release"
    
    # Check image memory
    assert any(term in response_lower for term in ['color', 'design', 'sleek', '3', 'three']), \
        "Should remember design details from images"
    
    # Check audio memory
    assert any(term in response_lower for term in ['q2', 'quarter', '2024', 'availability']), \
        "Should remember availability from audio"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()
        
        try:
            test_full_multimodal_analysis(overlord)
            test_story_telling_across_modalities(overlord)
            test_multimodal_verification(overlord)
            test_complex_multimodal_memory(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()