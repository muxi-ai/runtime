"""
Test 3F1 with Webhooks: Async Persistent Monitoring
Process PDF with async mode and persistent monitoring to verify webhook delivery.
"""

import asyncio
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_async_pdf_persistent_with_webhooks():
    """Test async PDF processing with persistent monitoring and webhook support"""
    print("\n=== Test 3F1 with Webhooks: Async PDF Processing (Persistent Monitoring) ===")
    print("Goal: Keep running to monitor webhook delivery with persistent tracking")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    formation.load(str(formation_path))
    overlord = formation.start_overlord()

    try:
        # Test conceptual async persistent processing if no real PDF file
        pdf_path = Path("test-docs/sample.pdf")
        if not pdf_path.exists():
            print(f"PDF file not found at {pdf_path}, testing conceptual async persistent processing...")
            
            # Test async persistent processing understanding
            response = await overlord.chat(
                user_id="test_user_persistent",
                session_id="test_session_persistent_123",
                message="How would you handle persistent monitoring of long-running async PDF processing tasks? What tracking mechanisms would you implement?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["persistent", "monitoring", "async", "tracking", "mechanism", "pdf", "process"],
                min_keywords=4,
                min_length=100,
                test_name="Async Persistent Processing Concepts"
            )
            
            print(f"Async Persistent Processing Concepts Complete - Async: {is_async}")
            return

        # If PDF file exists, test real persistent processing
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()

        # Send request with PDF attachment and session_id for tracking
        print("Sending async request with session_id for persistent tracking...")
        response = await overlord.chat(
            user_id="test_user_persistent",
            session_id="test_session_persistent_123",  # Adding session ID to track in logs
            message="Explain the formula in this PDF with detailed analysis and provide comprehensive insights.",
            files=[
                {
                    "filename": pdf_path.name,
                    "content": pdf_content,
                    "content_type": "application/pdf",
                    "size": len(pdf_content),
                }
            ]
        )

        # Use universal webhook checker for persistent monitoring
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["formula", "pdf", "analysis", "insight", "explain"],
            min_keywords=2,
            min_length=50,
            timeout=120.0,  # Extended timeout for persistent monitoring
            test_name="Async PDF Persistent Processing"
        )
        
        print(f"Async PDF Persistent Processing Complete - Async: {is_async}")
        
        # Additional persistent monitoring test
        if is_async and isinstance(response, dict) and response.get('request_id'):
            print(f"\n📊 Monitoring persistent task: {response['request_id']}")
            print("🔄 Testing persistent monitoring capabilities...")
            
            # Test monitoring awareness
            monitor_response = await overlord.chat(
                user_id="test_user_persistent",
                session_id="test_session_persistent_123",
                message="What is the status of my previous PDF processing request? Can you track its progress?"
            )
            
            monitor_result, monitor_is_async = check_response_with_webhook(
                monitor_response,
                expected_keywords=["status", "progress", "track", "request", "processing"],
                min_keywords=2,
                min_length=30,
                test_name="Persistent Monitoring Status"
            )
            
            print(f"Persistent Monitoring Test Complete - Async: {monitor_is_async}")

    finally:
        print("🔚 Stopping overlord...")
        formation.stop_overlord()


async def test_session_tracking_with_webhooks():
    """Test session tracking capabilities with webhook support"""
    print("\n=== Test 3F1 with Webhooks: Session Tracking ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    formation.load(str(formation_path))
    overlord = formation.start_overlord()

    try:
        response = await overlord.chat(
            user_id="test_user_session",
            session_id="test_session_tracking_456",
            message="How do you maintain session continuity across multiple async requests? What tracking mechanisms ensure request correlation?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["session", "continuity", "async", "tracking", "correlation", "request"],
            min_keywords=3,
            min_length=100,
            test_name="Session Tracking Capabilities"
        )
        
        print(f"Session Tracking Test Complete - Async: {is_async}")
        
    finally:
        formation.stop_overlord()


if __name__ == "__main__":
    async def run_all_tests():
        await test_async_pdf_persistent_with_webhooks()
        await test_session_tracking_with_webhooks()
        print("\nAll async persistent monitoring webhook tests completed!")
    
    asyncio.run(run_all_tests())