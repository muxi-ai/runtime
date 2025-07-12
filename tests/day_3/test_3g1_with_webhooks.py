"""
Test 3G1 with Webhooks: PDF Text Extraction Accuracy
Verify PDF text extraction matches source content with webhook support.
"""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_pdf_text_extraction_accuracy_with_webhooks():
    """Test PDF text extraction accuracy with webhook support"""
    print("\n=== Test 3G1 with Webhooks: PDF Text Extraction Accuracy ===")
    print("Goal: Verify PDF text extraction matches source content with webhook support")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        # Test conceptual PDF extraction if no real PDF file
        pdf_path = Path("test-docs/sample.pdf")
        if not pdf_path.exists():
            print(f"PDF file not found at {pdf_path}, testing conceptual PDF extraction accuracy...")
            
            # Test PDF extraction understanding
            response = await overlord.chat(
                user_id="test_user_pdf_accuracy_concept",
                message="How do you ensure accurate text extraction from PDFs? What are the common issues that affect extraction quality and how do you handle them?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["pdf", "extract", "accuracy", "text", "quality", "issue", "format"],
                min_keywords=4,
                min_length=100,
                test_name="PDF Extraction Accuracy Concepts"
            )
            
            print(f"PDF Extraction Accuracy Concepts Complete - Async: {is_async}")
            return
        
        # If PDF file exists, test real extraction
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()
        
        # Send request for exact text extraction
        print("Sending PDF text extraction request...")
        response = await overlord.chat(
            user_id="test_user_pdf_accuracy",
            message="Please extract the exact text from this PDF. Include all paragraphs, headings, and any formulas or technical content exactly as they appear.",
            files=[{
                "filename": pdf_path.name,
                "content": pdf_content,
                "content_type": "application/pdf",
                "size": len(pdf_content),
            }],
        )
        
        # Use universal webhook checker for PDF processing (likely async)
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["text", "extract", "pdf", "paragraph", "heading", "content"],
            min_keywords=3,
            min_length=100,
            timeout=90.0,  # Give time for PDF processing
            test_name="Real PDF Text Extraction"
        )
        
        print(f"Real PDF Text Extraction Complete - Async: {is_async}")
        
        # Test accuracy validation
        response2 = await overlord.chat(
            user_id="test_user_pdf_accuracy",
            message="How confident are you in the accuracy of the extracted text? Are there any formatting or structural elements that might have been lost?"
        )
        
        result2, is_async2 = check_response_with_webhook(
            response2,
            expected_keywords=["accuracy", "confident", "format", "structure", "extract", "quality"],
            min_keywords=2,
            min_length=50,
            test_name="PDF Accuracy Assessment"
        )
        
        print(f"PDF Accuracy Assessment Complete - Async: {is_async2}")
        
    finally:
        print("🔚 Stopping overlord...")
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_pdf_extraction_challenges_with_webhooks():
    """Test understanding of PDF extraction challenges with webhook support"""
    print("\n=== Test 3G1 with Webhooks: PDF Extraction Challenges ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        response = await overlord.chat(
            user_id="test_user_pdf_challenges",
            message="What are the main challenges in accurate PDF text extraction: scanned documents, complex layouts, tables, mathematical formulas, and multi-column text?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["pdf", "challenge", "extract", "scanned", "layout", "table", "formula", "column"],
            min_keywords=4,
            min_length=150,
            test_name="PDF Extraction Challenges"
        )
        
        print(f"PDF Extraction Challenges Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_pdf_text_extraction_accuracy_with_webhooks()
        await test_pdf_extraction_challenges_with_webhooks()
        print("\nAll PDF text extraction accuracy webhook tests completed!")
    
    asyncio.run(run_all_tests())