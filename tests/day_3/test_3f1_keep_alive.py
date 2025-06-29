#!/usr/bin/env python3
"""Test 3F1: Process PDF with async mode - keep process alive."""

import asyncio
import sys
import os
import time
from pathlib import Path
import signal

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation

# Global flag to track if we should exit
should_exit = False

def signal_handler(signum, frame):
    global should_exit
    print("\n🛑 Received interrupt signal, preparing to exit...")
    should_exit = True

def test_async_pdf_keep_alive():
    """Test async PDF processing while keeping the process alive."""
    
    global should_exit
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    print("TEST 3F1: Async PDF Processing (Keep Alive Version)")
    print("Goal: Keep process and event loop alive for webhook delivery")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    formation.load(str(formation_path))
    overlord = formation.start_overlord()
    
    # Prepare the PDF file
    pdf_path = Path("test-docs/sample.pdf")
    if not pdf_path.exists():
        print(f"ERROR: PDF file not found at {pdf_path}")
        return
    
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()
    
    # Send request with PDF attachment and session_id
    print("Sending async request with session_id...")
    response = asyncio.run(overlord.chat(
        user_id="test_user",
        session_id="test_session_123",
        message="explain the formula in this pdf",
        files=[{
            "filename": pdf_path.name,
            "content": pdf_content,
            "content_type": "application/pdf",
            "size": len(pdf_content),
        }],
        use_async=True,
    ))
    
    if isinstance(response, dict) and "request_id" in response:
        print(f"\n✅ Async request submitted!")
        print(f"Request ID: {response['request_id']}")
        print(f"Session ID: test_session_123")
        print(f"Webhook URL: https://webhook.site/165c81e9-a78b-4b15-8ecb-75298746f5b9")
        print()
        print("⏳ Background processing has started...")
        print("📋 Check log at: /Users/ran/Desktop/multimodal.log")
        print()
        print("🔄 KEEPING PROCESS ALIVE - DO NOT EXIT")
        print("🛑 Press Ctrl+C when you see the webhook delivered")
        print()
        
        # Keep the process alive indefinitely
        counter = 0
        while not should_exit:
            time.sleep(5)
            counter += 5
            
            # Periodic status update
            print(f"[{counter}s] Process still alive, event loop active...")
            
            # Check background tasks if accessible
            if hasattr(overlord, '_background_tasks'):
                print(f"    Active background tasks: {len(overlord._background_tasks)}")
            
            # Check log file
            try:
                log_size = os.path.getsize("/Users/ran/Desktop/multimodal.log")
                print(f"    Log file size: {log_size} bytes")
                
                # Read last few events
                with open("/Users/ran/Desktop/multimodal.log", "r") as f:
                    lines = f.readlines()
                    if len(lines) > 12:  # More events than before
                        print("    📝 New events detected in log!")
            except:
                pass
                
    else:
        print(f"❌ Unexpected response: {response}")
    
    print("\n🔚 Shutting down...")
    print("⏳ Waiting 10 seconds for any final operations...")
    time.sleep(10)
    
    print("🔚 Stopping overlord...")
    formation.stop_overlord(timeout_seconds=30.0)
    print("✅ Test complete!")


if __name__ == "__main__":
    test_async_pdf_keep_alive()