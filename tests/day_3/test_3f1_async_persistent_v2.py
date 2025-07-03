#!/usr/bin/env python3
"""Test 3F1: Process PDF with async mode - proper async version."""

import asyncio
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation


async def main():
    """Test async PDF processing with proper async context."""

    print("TEST 3F1: Async PDF Processing (Proper Async Version)")
    print("Goal: Keep async task alive to see webhook delivery")
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
    response = await overlord.chat(
        user_id="test_user",
        session_id="test_session_123",  # Adding session ID to track in logs
        message="explain the formula in this pdf",
        files=[{
            "filename": pdf_path.name,
            "content": pdf_content,
            "content_type": "application/pdf",
            "size": len(pdf_content),
        }],
        use_async=True,
    )

    if isinstance(response, dict) and "request_id" in response:
        print(f"\n✅ Async request submitted!")
        print(f"Request ID: {response['request_id']}")
        print(f"Session ID: test_session_123")
        print(f"Webhook URL: https://webhook.site/ef0cfa0f-4d38-443d-b459-ed5233fe6fbd")
        print()
        print("⏳ Background processing has started...")
        print("📋 Check log at: /Users/ran/Desktop/multimodal.log")
        print()
        print("🔄 Monitoring async task completion...")
        print("🛑 Press Ctrl+C to stop monitoring")
        print()

        # Monitor the request status
        counter = 0
        max_wait = 120  # 2 minutes max

        try:
            while counter < max_wait:
                await asyncio.sleep(5)
                counter += 5

                # Check if we can access the request tracker
                try:
                    request_state = await overlord.request_tracker.get_request(response['request_id'])
                    if request_state:
                        print(f"[{counter}s] Request status: {request_state.status.value}")
                        if request_state.status.value == "completed":
                            print("\n✅ Request completed! Webhook should have been sent.")
                            print("Check https://webhook.site/ef0cfa0f-4d38-443d-b459-ed5233fe6fbd")
                            # Give it another 5 seconds to ensure webhook is sent
                            await asyncio.sleep(5)
                            break
                    else:
                        print(f"[{counter}s] Request no longer in tracker (may have completed)")
                        # Check log to see if completion event was emitted
                        await asyncio.sleep(5)
                        break
                except Exception as e:
                    print(f"[{counter}s] Still running... (tracker error: {type(e).__name__})")

                # Check background tasks
                if hasattr(overlord, '_background_tasks'):
                    print(f"    Active background tasks: {len(overlord._background_tasks)}")

                # Also check log file size to see if it's growing
                try:
                    log_size = os.path.getsize("/Users/ran/Desktop/multimodal.log")
                    print(f"    Log file size: {log_size} bytes")
                except:
                    pass

        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
    else:
        print(f"❌ Unexpected response: {response}")

    # Wait a bit more to ensure all async operations complete
    print("\n⏳ Waiting for any remaining async operations...")
    await asyncio.sleep(5)

    print("\n🔚 Stopping overlord...")
    formation.stop_overlord(timeout_seconds=10.0)
    print("✅ Test complete!")


if __name__ == "__main__":
    # Run in a single event loop to keep async tasks alive
    asyncio.run(main())
