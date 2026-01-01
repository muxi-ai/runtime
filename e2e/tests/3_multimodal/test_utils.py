"""
Test utilities for Day 3 multimodal tests with enhanced visibility.
"""

import asyncio
import json
import time
from typing import Any, Dict, Optional, Union
from datetime import datetime


class TestVisibility:
    """Helper class to provide visibility into test execution"""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.start_time = time.time()
        self.step_count = 0

    def start_test(self, description: str):
        """Mark the start of a test"""
        print(f"\n{'='*80}")
        print(f"🧪 TEST: {self.test_name}")
        print(f"📝 Description: {description}")
        print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

    def step(self, action: str, details: Optional[str] = None):
        """Log a test step"""
        self.step_count += 1
        elapsed = time.time() - self.start_time
        print(f"\n{'─'*60}")
        print(f"📍 STEP {self.step_count}: {action}")
        if details:
            print(f"   ℹ️  Details: {details}")
        print(f"   ⏱️  Elapsed: {elapsed:.2f}s")
        print(f"{'─'*60}")

    def sending_message(self, message: str, user_id: str, **kwargs):
        """Log when sending a message to overlord"""
        print("\n🔵 SENDING MESSAGE TO OVERLORD:")
        print(f"   User ID: {user_id}")
        print(f"   Message: {message[:200]}{'...' if len(message) > 200 else ''}")
        if kwargs:
            print("   Parameters:")
            for key, value in kwargs.items():
                if key == "webhook_url":
                    print(f"      - {key}: {value}")
                elif key == "use_async":
                    print(f"      - {key}: {value}")
                elif key == "attachments" and value:
                    print(f"      - {key}: {len(value)} files")
                else:
                    print(f"      - {key}: {value}")

    def received_response(self, response: Union[str, Dict[str, Any]]):
        """Log the response received"""
        print("\n🟢 RECEIVED RESPONSE:")
        if isinstance(response, dict):
            print("   Response Type: Dictionary")
            for key, value in response.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"   - {key}: {value[:100]}...")
                else:
                    print(f"   - {key}: {value}")
        else:
            print("   Response Type: String")
            print(f"   Content: {response[:500]}{'...' if len(response) > 500 else ''}")

    def observability_event(
        self, event_type: str, level: str, data: Dict[str, Any], description: str
    ):
        """Log an observability event"""
        print("\n📊 OBSERVABILITY EVENT:")
        print(f"   Type: {event_type}")
        print(f"   Level: {level}")
        print(f"   Description: {description}")
        if data:
            print(f"   Data: {json.dumps(data, indent=6)}")

    def assertion(self, check: str, passed: bool, actual_value: Any = None):
        """Log an assertion check"""
        icon = "✅" if passed else "❌"
        print(f"\n{icon} ASSERTION: {check}")
        if actual_value is not None:
            print(f"   Actual value: {actual_value}")
        if not passed:
            print("   ⚠️  FAILED!")

    def webhook_check(self, webhook_url: str, expected: bool = True):
        """Log webhook expectation"""
        print("\n🔔 WEBHOOK CHECK:")
        print(f"   URL: {webhook_url}")
        print(f"   Expected: {'Should receive webhook' if expected else 'No webhook expected'}")

    def complete_test(self, status: str = "PASSED"):
        """Mark test completion"""
        elapsed = time.time() - self.start_time
        icon = "✅" if status == "PASSED" else "❌"
        print(f"\n{'='*80}")
        print(f"{icon} TEST COMPLETED: {status}")
        print(f"⏱️  Total time: {elapsed:.2f}s")
        print(f"📊 Total steps: {self.step_count}")
        print(f"{'='*80}\n")


def get_response_universal(coro):
    """Universal helper to get response from async chat - handles all response types"""
    result = asyncio.run(coro)

    # Handle different response types
    if isinstance(result, dict) and "request_id" in result:
        # Async response - return a placeholder message
        return f"Processing async request {result['request_id']}. Results will be sent to webhook."
    elif hasattr(result, "__aiter__"):
        # Streaming response - collect all chunks
        async def collect():
            chunks = []
            async for chunk in result:
                chunks.append(chunk)
            return "".join(chunks)
        return asyncio.run(collect())
    elif isinstance(result, str):
        # Direct string response
        return result
    else:
        # For any other type, convert to string
        return str(result)


def is_async_response(response):
    """Check if a response is an async processing response"""
    if isinstance(response, str):
        response_lower = response.lower()
        return "async request" in response_lower and "webhook" in response_lower
    return False


def assert_response_valid(response, min_length=50, required_words=None, context=""):
    """Assert that a response is valid, handling both sync and async responses"""
    assert response, f"Should receive a response{' for ' + context if context else ''}"

    if is_async_response(response):
        # This is an async processing response
        assert "Processing async request" in response, "Should indicate async processing"
        return True  # Async response is valid
    else:
        # This is a sync response with actual content
        assert len(response) >= min_length, f"Response should be at least {min_length} chars{' for ' + context if context else ''}"

        if required_words:
            response_lower = response.lower()
            found = any(word.lower() in response_lower for word in required_words)
            assert found, f"Response should contain one of: {required_words}{' for ' + context if context else ''}"

        return False  # Not async


async def get_response_with_visibility_async(
    coro, visibility: TestVisibility, step_description: str
):
    """Async helper to get response from async chat with visibility"""
    visibility.step(step_description)

    result = await coro

    # Handle async generators
    if hasattr(result, "__aiter__"):
        chunks = []
        async for chunk in result:
            chunks.append(chunk)
        result = "".join(chunks)

    visibility.received_response(result)
    return result


def get_response_with_visibility(coro, visibility: TestVisibility, step_description: str):
    """Sync wrapper for get_response_with_visibility_async"""
    return asyncio.run(get_response_with_visibility_async(coro, visibility, step_description))


def assert_with_visibility(
    condition: bool, message: str, visibility: TestVisibility, actual_value: Any = None
):
    """Assert with visibility logging"""
    visibility.assertion(message, condition, actual_value)
    assert condition, message


# Monkey patch to capture observability events
_original_observe = None


def capture_observability_events(visibility: TestVisibility):
    """Monkey patch observability to capture events"""
    global _original_observe

    try:
        from muxi.runtime.services import observability

        if _original_observe is None:
            _original_observe = observability.observe

        def observe_with_capture(event_type, level, data, description):
            # Extract readable event name
            event_name = str(event_type).split(".")[-1]
            level_name = str(level).split(".")[-1]

            # Print observability event immediately
            print(f"[{level_name}] {event_name}: {description}")

            # Call original
            return _original_observe(event_type, level, data, description)

        observability.observe = observe_with_capture

    except Exception as e:
        print(f"Warning: Could not patch observability: {e}")


def restore_observability():
    """Restore original observability"""
    global _original_observe
    if _original_observe:
        try:
            from muxi.runtime.services import observability

            observability.observe = _original_observe
        except Exception:
            pass
