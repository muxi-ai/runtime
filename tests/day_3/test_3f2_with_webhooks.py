"""
Test 3F2 with Webhooks: Real OCR Processing
Perform real OCR on chart images and extract data with webhook support.
"""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_real_ocr_processing_with_webhooks():
    """Test real OCR on chart images with webhook support"""
    print("\n=== Test 3F2 with Webhooks: Real OCR on Chart Images ===")
    print("Goal: Extract actual data from chart images using OCR with webhook support")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        # Test conceptual OCR understanding if no real chart file
        chart_path = Path("test-docs/chart.png")
        if not chart_path.exists():
            print(f"Chart image not found at {chart_path}, testing conceptual OCR understanding...")
            
            # Test OCR understanding
            response = await overlord.chat(
                user_id="test_user_ocr_concept",
                message="If I upload a bar chart image with sales data showing Q1: $100K, Q2: $150K, Q3: $120K, Q4: $180K, how would you extract this data using OCR?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["ocr", "extract", "chart", "data", "text", "recognition", "sales"],
                min_keywords=3,
                min_length=100,
                test_name="OCR Conceptual Understanding"
            )
            
            print(f"OCR Conceptual Test Complete - Async: {is_async}")
            return
        
        # If chart file exists, test real OCR
        with open(chart_path, "rb") as f:
            image_content = f.read()
        
        # Send request with chart image
        print("Sending OCR request for chart data extraction...")
        response = await overlord.chat(
            user_id="test_user_ocr",
            message="Please extract all text and data from this chart using OCR. Include all numbers, labels, and axis values.",
            files=[{
                "filename": chart_path.name,
                "content": image_content,
                "content_type": "image/png",
                "size": len(image_content),
            }],
        )
        
        # Use universal webhook checker for file processing (likely async)
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["chart", "data", "text", "extract", "axis", "label", "value"],
            min_keywords=3,
            min_length=50,
            timeout=60.0,  # Give more time for file processing
            test_name="Real OCR Chart Processing"
        )
        
        print(f"Real OCR Test Complete - Async: {is_async}")
        
        # Additional test for OCR accuracy
        response2 = await overlord.chat(
            user_id="test_user_ocr",
            message="How accurate was the OCR extraction? Were all numbers and labels correctly identified?"
        )
        
        result2, is_async2 = check_response_with_webhook(
            response2,
            expected_keywords=["accurate", "ocr", "number", "label", "extract", "identify"],
            min_keywords=2,
            min_length=30,
            test_name="OCR Accuracy Assessment"
        )
        
        print(f"OCR Accuracy Assessment Complete - Async: {is_async2}")
        
    finally:
        print("🔚 Stopping overlord...")
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_ocr_methodology_with_webhooks():
    """Test understanding of OCR methodology with webhook support"""
    print("\n=== Test 3F2 with Webhooks: OCR Methodology ===")
    
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
            user_id="test_user_ocr_method",
            message="What are the best practices for OCR on different types of images: charts, scanned documents, screenshots, and handwritten text?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["ocr", "chart", "document", "screenshot", "handwritten", "practice", "image", "text"],
            min_keywords=4,
            min_length=150,
            test_name="OCR Methodology"
        )
        
        print(f"OCR Methodology Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_real_ocr_processing_with_webhooks()
        await test_ocr_methodology_with_webhooks()
        print("\nAll OCR webhook tests completed!")
    
    asyncio.run(run_all_tests())