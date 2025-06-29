#!/usr/bin/env python3
"""Test 3F1: Process PDF with async mode - persistent version to see webhook."""

import asyncio
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def test_async_pdf_persistent():
    """Test async PDF processing with persistent running to see webhook."""

    print("TEST 3F1: Async PDF Processing (Persistent)")
    print("Goal: Keep running to see webhook delivery")
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
        files=[
            {
                "filename": pdf_path.name,
                "content": pdf_content,
                "content_type": "application/pdf",
                "size": len(pdf_content),
            }
        ],
        use_async=True,
    )

    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async request submitted!")
        print(f"Request ID: {response['request_id']}")
        print("Session ID: test_session_123")
        print("Webhook URL: https://webhook.site/165c81e9-a78b-4b15-8ecb-75298746f5b9")
        print()
        print("⏳ Background processing has started...")
        print("📋 Check log at: /Users/ran/Desktop/multimodal.log")
        print()
        print("🔄 Keeping process alive to allow webhook delivery...")
        print("🛑 Press Ctrl+C when you see the webhook delivered")
        print()

        # Monitor the request directly in the same async context
        try:
            counter = 0
            while True:
                # Wait a bit
                await asyncio.sleep(5)
                counter += 5

                # Check if we can access the request tracker
                try:
                    request_state = await overlord.request_tracker.get_request(
                        response["request_id"]
                    )
                    if request_state:
                        print(f"[{counter}s] Request status: {request_state.status.value}")
                        if request_state.status.value == "completed":
                            print("\n✅ Request completed! Webhook should have been sent.")
                            print("Check https://webhook.site/165c81e9-a78b-4b15-8ecb-75298746f5b9")
                            # Give it another 5 seconds to ensure webhook is sent
                            await asyncio.sleep(5)
                            break
                    else:
                        print(f"[{counter}s] Request no longer in tracker (may have completed)")
                except Exception as e:
                    print(
                        f"[{counter}s] Still running... (tracker check failed: {type(e).__name__})"
                    )

                # Also check log file size to see if it's growing
                try:
                    log_size = os.path.getsize("/Users/ran/Desktop/multimodal.log")
                    print(f"    Log file size: {log_size} bytes")
                except Exception:
                    pass

                # Don't run forever - timeout after 2 minutes
                if counter >= 120:
                    print("\n⚠️ Timeout reached after 2 minutes. Async task may have failed.")
                    break

        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
    else:
        print(f"❌ Unexpected response: {response}")

    # Don't stop overlord immediately - give async tasks time to complete
    print("\n⏳ Waiting for background tasks to complete...")
    await asyncio.sleep(2)  # Use async sleep instead of time.sleep

    print("\n🔚 Stopping overlord...")
    formation.stop_overlord(timeout_seconds=10.0)  # Use shorter timeout
    print("✅ Test complete!")


def main():
    """Main function to run the async test."""
    try:
        asyncio.run(test_async_pdf_persistent())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
