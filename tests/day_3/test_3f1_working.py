#!/usr/bin/env python3
"""Test 3F1: Process PDF with async mode - working version with persistent event loop."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""

    print("TEST 3F1: Async PDF Processing (Working Version)")
    print("Goal: Process PDF asynchronously and deliver webhook")
    print()

    # Load formation (this is sync but we'll handle it)
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()

    # Run sync operations in executor to avoid blocking
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)

    # Prepare the PDF file
    pdf_path = Path("test-docs/sample.pdf")
    if not pdf_path.exists():
        print(f"ERROR: PDF file not found at {pdf_path}")
        return

    with open(pdf_path, "rb") as f:
        pdf_content = f.read()

    # Send request with PDF attachment - AWAIT directly, no asyncio.run()
    print("Sending async request with session_id...")
    response = await overlord.chat(
        user_id="test_user",
        session_id="test_session_123",
        message="explain the formula in this pdf",
        files=[{
            "filename": pdf_path.name,
            "content": pdf_content,
            "content_type": "application/pdf",
            "size": len(pdf_content),
        }],
        # use_async=True,
        # stream=False,
    )

    # Handle different response types
    if isinstance(response, dict) and "request_id" in response:
        # Async response
        print("\n✅ Async request submitted!")
        print(f"Request ID: {response['request_id']}")
        print("Session ID: test_session_123")
        print("Webhook URL: https://webhook.site/ef0cfa0f-4d38-443d-b459-ed5233fe6fbd")
        print()
        print("⏳ Background task is processing...")
        print("📋 Check log at: /Users/ran/Desktop/multimodal.log")
        print()

        # Give the async task time to process
        # Since we're in the same event loop, the task will continue running
        print("⏳ Waiting for async processing to complete...")

        # Check task status periodically
        for i in range(24):  # 2 minutes max
            await asyncio.sleep(5)
            elapsed = (i + 1) * 5

            # Check background tasks
            if hasattr(overlord, '_background_tasks'):
                task_count = len(overlord._background_tasks)
                print(f"[{elapsed}s] Active background tasks: {task_count}")

                if task_count == 0:
                    print("✅ All background tasks completed!")
                    break

            # Check log file for completion
            # Use relative path or environment variable
            log_path = os.getenv("MULTIMODAL_LOG_PATH", "logs/multimodal.log")
            try:
                with open(log_path, "r") as f:
                    content = f.read()
                    if "webhook.delivered" in content or "WEBHOOK_DELIVERED" in content:
                        print("✅ Webhook delivered successfully!")
                        break
                    if f"req_{response['request_id']}" in content and "completed" in content:
                        print("📝 Request processing completed in logs")
            except Exception:
                pass

    elif hasattr(response, '__aiter__'):
        # Streaming response (async generator)
        print("\n📡 Receiving streaming response...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        print(f"\n\n✅ Streaming response complete! Total length: {len(full_response)} chars")

    elif isinstance(response, str):
        # Direct string response
        print(f"\n✅ Sync response received: {response[:100]}...")
        print(f"Response length: {len(response)} chars")

    else:
        print(f"❌ Unexpected response type: {type(response)}")
        print(f"Response: {response}")

    # Give a bit more time for webhook delivery
    print("\n⏳ Waiting 10 more seconds for webhook delivery...")
    await asyncio.sleep(10)

    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


async def main():
    """Main entry point."""
    print("Starting test with persistent event loop...")

    # Run everything in a single event loop that persists until completion
    try:
        await run_async_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
