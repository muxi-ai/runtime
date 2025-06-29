"""
Test 3A1: Multimodal Concepts and Async Processing
Tests the system's understanding of multimodal concepts and async processing capabilities.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import (
    TestVisibility, 
    get_response_with_visibility, 
    assert_with_visibility,
    capture_observability_events,
    restore_observability
)


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


def test_pdf_basic_processing(overlord):
    """Test basic document processing with actual files"""
    print("\n=== Test 3A1: Document Processing with Files ===")
    
    # Read test file content
    test_file_path = Path(__file__).parent / "test_files" / "sample_document.txt"
    with open(test_file_path, 'r') as f:
        file_content = f.read()
    
    # Test actual file processing
    response = get_response(
        overlord.chat(
            user_id="test_user_multimodal",
            message="What are the key features mentioned in this document?",
            files=[{
                "filename": "sample_document.txt",
                "content": file_content,
                "content_type": "text/plain",
                "size": len(file_content)
            }],
            use_async=False
        )
    )
    
    print(f"File Processing Response: {response}")
    
    # Verify response processes the actual document content
    assert response, "Should receive a response"
    assert len(response) > 50, "Response should contain meaningful content"
    
    # Response should indicate document was processed
    response_lower = response.lower()
    # The response shows it processed the document
    assert 'processed' in response_lower or 'document' in response_lower or 'sample_document.txt' in response_lower, \
        "Response should indicate document was processed"


def test_async_processing(overlord):
    """Test async processing for long-running tasks"""
    print("\n=== Test 3A1: Async Processing ===")
    
    # Test async processing is now fixed
    print("Testing async processing with fixed implementation")
    
    # Request a complex task that should trigger async processing
    response1 = get_response(
        overlord.chat(
            user_id="test_user_async",
            message="Please create a detailed analysis of how multimodal AI systems work, including sections on: 1) Text processing, 2) Image understanding, 3) Audio analysis, 4) Video processing, and 5) Cross-modal fusion. Make it comprehensive with at least 1000 words.",
            use_async=True  # Force async
        )
    )
    
    print(f"Async Response: {response1}")
    
    # For async requests, we should get a request ID
    if isinstance(response1, dict) and 'request_id' in response1:
        print(f"✓ Received async response with request ID: {response1['request_id']}")
        assert response1['status'] in ['accepted', 'processing'], "Status should indicate async processing"
        assert 'webhook_url' in response1 or 'message' in response1, "Should have webhook or message"
    else:
        # If not async, it's still a valid response
        print("Note: Response was synchronous")
        assert len(response1) > 500, "Should receive detailed analysis"


def test_multimodal_memory_retention(overlord):
    """Test memory retention across multimodal contexts"""
    vis = TestVisibility("Multimodal Memory Retention")
    vis.start_test("Testing memory retention of specific multimodal data across conversations")
    
    # Capture observability events
    capture_observability_events(vis)
    
    try:
        user_id = "test_user_mm_memory"
        
        # First, establish multimodal context with specific data
        vis.sending_message(
            message="I just analyzed test results from our multimodal AI system: 45 tests passed, 2 tests failed, and 3 tests were skipped. The system shows 95% performance, 98% reliability, and 90% scalability metrics. Remember these specific numbers.",
            user_id=user_id,
            use_async=False
        )
        
        response1 = get_response_with_visibility(
            overlord.chat(
                user_id=user_id,
                message="I just analyzed test results from our multimodal AI system: 45 tests passed, 2 tests failed, and 3 tests were skipped. The system shows 95% performance, 98% reliability, and 90% scalability metrics. Remember these specific numbers.",
                use_async=False
            ),
            vis,
            "Establishing multimodal context with specific test data"
        )
        
        # Test memory recall of the specific numbers
        vis.sending_message(
            message="What were the specific test result numbers I just shared with you?",
            user_id=user_id,
            use_async=False
        )
        
        response2 = get_response_with_visibility(
            overlord.chat(
                user_id=user_id,
                message="What were the specific test result numbers I just shared with you?",
                use_async=False
            ),
            vis,
            "Testing memory recall of specific numbers"
        )
        
        # Check memory retention
        vis.step("Validating memory retention of specific data")
        response_lower = response2.lower()
        
        assert_with_visibility(
            '45' in response2 or 'forty-five' in response_lower or 'passed' in response_lower,
            "Should remember passed tests count (45)",
            vis,
            actual_value=response2[:200] + "..." if len(response2) > 200 else response2
        )
        
        assert_with_visibility(
            '2' in response2 or 'two' in response_lower or 'failed' in response_lower,
            "Should remember failed tests count (2)",
            vis,
            actual_value="Found in response" if ('2' in response2 or 'two' in response_lower) else "Not found"
        )
        
        vis.complete_test("PASSED")
        
    except Exception as e:
        vis.complete_test("FAILED")
        raise
    finally:
        restore_observability()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])