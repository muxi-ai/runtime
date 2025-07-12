"""
Test 3G2 with Webhooks: OCR Accuracy Validation
Validate OCR accuracy on different image types with webhook support.
"""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_ocr_accuracy_validation_with_webhooks():
    """Test OCR accuracy validation with webhook support"""
    print("\n=== Test 3G2 with Webhooks: OCR Accuracy Validation ===")
    
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
            user_id="test_user_ocr_accuracy",
            message="How do you validate OCR accuracy on different types of images: clear text, handwritten notes, low-resolution scans, charts with text, and images with complex backgrounds?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["ocr", "accuracy", "validate", "text", "handwritten", "resolution", "chart", "background"],
            min_keywords=4,
            min_length=150,
            test_name="OCR Accuracy Validation"
        )
        
        print(f"OCR Accuracy Validation Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_ocr_quality_metrics_with_webhooks():
    """Test understanding of OCR quality metrics with webhook support"""
    print("\n=== Test 3G2 with Webhooks: OCR Quality Metrics ===")
    
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
            user_id="test_user_ocr_metrics",
            message="What metrics and techniques can be used to assess OCR quality: character accuracy, word accuracy, confidence scores, and error detection methods?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["metric", "ocr", "quality", "accuracy", "character", "word", "confidence", "error"],
            min_keywords=4,
            min_length=120,
            test_name="OCR Quality Metrics"
        )
        
        print(f"OCR Quality Metrics Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_ocr_accuracy_validation_with_webhooks()
        await test_ocr_quality_metrics_with_webhooks()
        print("\nAll OCR accuracy validation webhook tests completed!")
    
    asyncio.run(run_all_tests())