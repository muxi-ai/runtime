"""
Test 3F5 with Webhooks: Multi-File Processing
Process multiple different file types in one request with webhook support.
"""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_multi_file_processing_with_webhooks():
    """Test processing multiple different file types with webhook support"""
    print("\n=== Test 3F5 with Webhooks: Multi-File Processing ===")
    print("Goal: Process multiple different file types in one request with webhook support")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        # Test conceptual multi-file understanding if no real files
        test_files = [
            "test-docs/small.pdf",
            "test-docs/chart.png", 
            "test-docs/short.m4a"
        ]
        
        missing_files = [f for f in test_files if not Path(f).exists()]
        
        if missing_files:
            print(f"Some test files not found: {missing_files}")
            print("Testing conceptual multi-file processing understanding...")
            
            # Test multi-file processing understanding
            response = await overlord.chat(
                user_id="test_user_multifile_concept",
                message="If I upload multiple files at once - a PDF report, a chart image, and an audio recording - how would you process and correlate the information across all three file types?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["multi", "file", "pdf", "image", "audio", "process", "correlate", "information"],
                min_keywords=4,
                min_length=100,
                test_name="Multi-File Conceptual Understanding"
            )
            
            print(f"Multi-File Conceptual Test Complete - Async: {is_async}")
            return
        
        # If files exist, test real multi-file processing
        files = []
        
        # PDF file
        pdf_path = Path("test-docs/small.pdf")
        if pdf_path.exists():
            with open(pdf_path, "rb") as f:
                pdf_content = f.read()
            files.append({
                "filename": pdf_path.name,
                "content": pdf_content,
                "content_type": "application/pdf",
                "size": len(pdf_content),
            })
            print(f"✓ Added PDF: {pdf_path.name} ({len(pdf_content)} bytes)")
        
        # Image file
        image_path = Path("test-docs/chart.png")
        if image_path.exists():
            with open(image_path, "rb") as f:
                image_content = f.read()
            files.append({
                "filename": image_path.name,
                "content": image_content,
                "content_type": "image/png",
                "size": len(image_content),
            })
            print(f"✓ Added Image: {image_path.name} ({len(image_content)} bytes)")
        
        # Audio file
        audio_path = Path("test-docs/short.m4a")
        if audio_path.exists():
            with open(audio_path, "rb") as f:
                audio_content = f.read()
            files.append({
                "filename": audio_path.name,
                "content": audio_content,
                "content_type": "audio/m4a",
                "size": len(audio_content),
            })
            print(f"✓ Added Audio: {audio_path.name} ({len(audio_content)} bytes)")
        
        if not files:
            print("No files found for multi-file processing test")
            return
        
        # Send multi-file request
        print(f"Sending multi-file analysis request with {len(files)} files...")
        response = await overlord.chat(
            user_id="test_user_multifile",
            message="Please analyze all the uploaded files and create a comprehensive summary that combines insights from all file types.",
            files=files,
        )
        
        # Use universal webhook checker for multi-file processing (very likely async)
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["file", "analysis", "summary", "comprehensive", "insight", "combine"],
            min_keywords=3,
            min_length=100,
            timeout=180.0,  # Give more time for multi-file processing
            test_name="Real Multi-File Processing"
        )
        
        print(f"Real Multi-File Processing Complete - Async: {is_async}")
        
    finally:
        print("🔚 Stopping overlord...")
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_multimodal_integration_strategy_with_webhooks():
    """Test understanding of multimodal integration strategies with webhook support"""
    print("\n=== Test 3F5 with Webhooks: Multimodal Integration Strategy ===")
    
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
            user_id="test_user_integration",
            message="What are the best strategies for integrating and correlating information from multiple file types: text documents, images, audio, and video files in a single analysis?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["strategy", "integrate", "correlate", "multimodal", "document", "image", "audio", "video"],
            min_keywords=4,
            min_length=150,
            test_name="Multimodal Integration Strategy"
        )
        
        print(f"Multimodal Integration Strategy Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_multi_file_processing_with_webhooks()
        await test_multimodal_integration_strategy_with_webhooks()
        print("\nAll multi-file processing webhook tests completed!")
    
    asyncio.run(run_all_tests())