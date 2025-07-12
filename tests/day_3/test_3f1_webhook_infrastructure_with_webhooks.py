"""
Test 3F1 with Webhooks: Webhook Infrastructure
Test webhook infrastructure with observability event capture and monitoring.
"""

import asyncio
import sys
import os
import time
import requests
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


class ObservabilityCapture:
    """Capture observability events for display and testing."""

    def __init__(self):
        self.events = []
        self._original_observe = None

    def __enter__(self):
        # Import and patch the observe function
        try:
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
                print(f"📊 observability event: {event_str}")

                # Call original function
                return self._original_observe(**kwargs)

            observability.observe = capture_observe
        except ImportError:
            print("⚠️  Observability module not available, using mock capture")
        
        return self

    def __exit__(self, *args):
        # Restore original function
        try:
            from src.muxi.runtime.services import observability
            if self._original_observe:
                observability.observe = self._original_observe
        except ImportError:
            pass


async def check_request_status_with_webhooks(overlord, request_id, max_wait=60):
    """Poll request status until completion or timeout with webhook awareness."""
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            # Get request status if tracker available
            if hasattr(overlord, 'request_tracker'):
                request_state = await overlord.request_tracker.get_request(request_id)
                
                if request_state:
                    print(f"📊 Request status: {request_state.status.value}")
                    
                    if request_state.status.value == "completed":
                        print(f"✅ Request completed in {request_state.processing_time:.2f} seconds")
                        return request_state
                    elif request_state.status.value == "failed":
                        print(f"❌ Request failed: {request_state.error}")
                        return request_state
                else:
                    print(f"⚠️  Request {request_id} not found in tracker")
            else:
                print("⚠️  Request tracker not available")
                
        except Exception as e:
            print(f"⚠️  Error checking request status: {e}")
        
        await asyncio.sleep(5)
    
    print(f"⏱️  Request status check timed out after {max_wait} seconds")
    return None


async def test_webhook_infrastructure_monitoring_with_webhooks():
    """Test webhook infrastructure with observability monitoring"""
    print("\n=== Test 3F1 with Webhooks: Webhook Infrastructure Monitoring ===")
    print("Goal: Test webhook infrastructure with observability event capture")
    
    # Setup webhook testing environment
    setup_webhook_test()

    with ObservabilityCapture() as obs_capture:
        # Load formation
        formation_path = Path("test-formations/formation-multimodal")
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()

        try:
            # Test infrastructure monitoring concepts
            response = await overlord.chat(
                user_id="test_user_infrastructure",
                message="How do you monitor webhook infrastructure health? What observability events should be tracked for async processing systems?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["webhook", "infrastructure", "monitoring", "observability", "event", "async", "health"],
                min_keywords=4,
                min_length=120,
                test_name="Webhook Infrastructure Monitoring"
            )
            
            print(f"Webhook Infrastructure Monitoring Complete - Async: {is_async}")
            print(f"📊 Captured {len(obs_capture.events)} observability events")
            
            # Test request status monitoring if we got an async response
            if is_async and isinstance(response, dict) and response.get('request_id'):
                print(f"\n🔍 Testing request status monitoring for: {response['request_id']}")
                status_result = await check_request_status_with_webhooks(
                    overlord, response['request_id'], max_wait=30
                )
                
                if status_result:
                    print(f"✅ Successfully monitored request lifecycle")
                else:
                    print(f"⚠️  Request monitoring completed without detailed status")

        finally:
            print("🔚 Stopping overlord...")
            formation.stop_overlord()


async def test_observability_event_capture_with_webhooks():
    """Test observability event capture during webhook processing"""
    print("\n=== Test 3F1 with Webhooks: Observability Event Capture ===")
    
    # Setup webhook testing environment
    setup_webhook_test()

    with ObservabilityCapture() as obs_capture:
        # Load formation
        formation_path = Path("test-formations/formation-multimodal")
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()

        try:
            response = await overlord.chat(
                user_id="test_user_observability",
                message="What observability events are most critical for tracking webhook delivery success and failure rates in async processing systems?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["observability", "event", "webhook", "delivery", "success", "failure", "tracking"],
                min_keywords=4,
                min_length=100,
                test_name="Observability Event Capture"
            )
            
            print(f"Observability Event Capture Complete - Async: {is_async}")
            
            # Report captured events
            if obs_capture.events:
                print(f"\n📊 Observability Events Captured ({len(obs_capture.events)}):")
                for i, event in enumerate(obs_capture.events[-5:], 1):  # Show last 5 events
                    print(f"  {i}. {event}")
            else:
                print("ℹ️  No observability events captured (may be using mock)")

        finally:
            formation.stop_overlord()


if __name__ == "__main__":
    async def run_all_tests():
        await test_webhook_infrastructure_monitoring_with_webhooks()
        await test_observability_event_capture_with_webhooks()
        print("\nAll webhook infrastructure monitoring tests completed!")
    
    asyncio.run(run_all_tests())