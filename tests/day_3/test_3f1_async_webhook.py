#!/usr/bin/env python3
"""Test 3F1: Process PDF with async mode and verify webhook is sent."""

import asyncio
import sys
import os
import time
import requests
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation


class ObservabilityCapture:
    """Capture observability events for display."""

    def __init__(self):
        self.events = []
        self._original_observe = None

    def __enter__(self):
        # Import and patch the observe function
        from src.muxi.runtime.services import observability

        self._original_observe = observability.observe

        def capture_observe(**kwargs):
            # Capture the event
            event_type = kwargs.get("event_type", "unknown")
            level = kwargs.get("level", "info")
            description = kwargs.get("description", "")
            data = kwargs.get("data", {})

            # Format the event for display
            event_str = f"[{level}] {event_type}"
            if description:
                event_str += f" - {description}"
            if data:
                event_str += f" | data: {data}"

            self.events.append(event_str)
            print(f"observability event: {event_str}")

            # Call original function
            return self._original_observe(**kwargs)

        observability.observe = capture_observe
        return self

    def __exit__(self, *args):
        # Restore original function
        from src.muxi.runtime.services import observability

        if self._original_observe:
            observability.observe = self._original_observe


async def check_request_status(overlord, request_id, max_wait=60):
    """Poll request status until completion or timeout."""
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        # Get request status
        request_state = await overlord.request_tracker.get_request(request_id)
        
        if not request_state:
            print(f"⚠️  Request {request_id} not found in tracker")
            return None
            
        print(f"📊 Request status: {request_state.status.value}")
        
        if request_state.status.value == "completed":
            print(f"✅ Request completed in {request_state.processing_time:.2f} seconds")
            return request_state
        elif request_state.status.value == "failed":
            print(f"❌ Request failed: {request_state.error}")
            return request_state
            
        # Wait before next check
        await asyncio.sleep(2)
    
    print(f"⏱️  Timeout waiting for request completion after {max_wait} seconds")
    return None


def check_webhook_site(webhook_url):
    """Check webhook.site for received webhooks."""
    # Extract the UUID from the webhook URL
    # Format: https://webhook.site/165c81e9-a78b-4b15-8ecb-75298746f5b9
    uuid = webhook_url.split("/")[-1]
    api_url = f"https://webhook.site/token/{uuid}/requests"
    
    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("data"):
                latest = data["data"][0]  # Most recent webhook
                return {
                    "received": True,
                    "timestamp": latest.get("created_at"),
                    "content": latest.get("content"),
                    "headers": latest.get("headers"),
                }
        return {"received": False}
    except Exception as e:
        return {"received": False, "error": str(e)}


def test_3f1_async_pdf_webhook():
    """Test async PDF processing with webhook verification."""

    print("TEST 3F1: Async PDF Processing with Webhook Notification")
    print("Goal: To verify that async processing sends webhook notifications upon completion")
    print()

    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    formation.load(str(formation_path))
    overlord = formation.start_overlord()

    # Get webhook URL from formation
    webhook_url = overlord.formation_config.get("async", {}).get("webhook_url")
    print(f"Webhook URL: {webhook_url}")
    print()

    # Prepare the PDF file
    pdf_path = Path("test-docs/sample.pdf")
    if not pdf_path.exists():
        print(f"ERROR: PDF file not found at {pdf_path}")
        return

    # Create the prompt
    prompt = "explain the formula in this pdf"

    print(f"Prompt sent to overlord.chat:")
    print(f'"{prompt}"')
    print(f"Files: [{pdf_path.name} ({os.path.getsize(pdf_path)} bytes)]")
    print()

    # Capture observability events
    with ObservabilityCapture() as capture:
        try:
            # Read the PDF file
            with open(pdf_path, "rb") as f:
                pdf_content = f.read()

            # Send request with PDF attachment
            response = asyncio.run(
                overlord.chat(
                    user_id="test_user",
                    message=prompt,
                    files=[
                        {
                            "filename": pdf_path.name,
                            "content": pdf_content,
                            "content_type": "application/pdf",
                            "size": len(pdf_content),
                        }
                    ],
                    use_async=True,  # Use async processing to test webhook
                )
            )

            # Handle async response
            if isinstance(response, dict) and "request_id" in response:
                print()
                print("ASYNC REQUEST SUBMITTED:")
                print(f"Request ID: {response.get('request_id')}")
                print(f"Status: {response.get('status')}")
                print(f"Message: {response.get('message')}")
                print(f"Webhook URL: {response.get('processing_info', {}).get('webhook_url', 'Not specified')}")
                print()
                
                request_id = response.get('request_id')
                
                print("✅ Async request submitted successfully")
                print("⏳ Webhook will be sent upon completion to:", webhook_url)
                print()
                print("🔄 Keeping process alive to wait for webhook delivery...")
                print("📋 Check the log file at: /Users/ran/Desktop/multimodal.log")
                print("🛑 Press Ctrl+C when you receive the webhook to stop the test")
                print()
                
                # Keep the process alive until webhook is delivered
                try:
                    max_wait = 60  # Maximum 60 seconds
                    waited = 0
                    print(f"⏱️  Waiting up to {max_wait} seconds for webhook delivery...")
                    while waited < max_wait:
                        time.sleep(1)
                        waited += 1
                        if waited % 10 == 0:
                            print(f"   Still waiting... {waited}/{max_wait} seconds")
                    print(f"\n⚠️  Timeout after {max_wait} seconds - webhook may not have been delivered")
                except KeyboardInterrupt:
                    print("\n🛑 Test interrupted by user")
                
            else:
                print("❌ Unexpected response format (not async)")
                print(f"Response: {response}")

        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
        except Exception as e:
            print(f"❌ Exception occurred: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            formation.stop_overlord()


if __name__ == "__main__":
    test_3f1_async_pdf_webhook()