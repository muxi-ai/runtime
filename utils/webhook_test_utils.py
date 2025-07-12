"""
Webhook testing utilities for Day 3 tests.
Provides common functions for webhook verification in async processing tests.
"""

import re
import time
import sys
import pytest
from typing import Optional, Dict, Any, List, Tuple

# Add utils to path for webhook_log_reader
sys.path.insert(0, "utils")
from webhook_log_reader import WebhookLogReader, clear_webhook_logs


def extract_request_id(response: str) -> Optional[str]:
    """
    Extract request ID from async response.

    Looks for patterns like:
    - "request_id: req_xxxxx"
    - "Request ID: req_xxxxx"
    - Just "req_xxxxx" in the response
    """
    if not isinstance(response, str):
        return None

    # Try different patterns
    patterns = [
        r'req_[a-zA-Z0-9_-]+',               # Direct req_xxx pattern (most common)
        r'request[_\s]id[:\s]+([^\s,\.]+)',  # request_id: xxx or Request ID: xxx
        r'"request_id"[:\s]+"([^"]+)"',      # JSON-style "request_id": "xxx"
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            if pattern.startswith('req_'):
                return match.group(0)
            else:
                result = match.group(1) if match.groups() else match.group(0)
                # Clean up the result
                result = result.strip('"').strip().rstrip('.')
                return result
    return None


def wait_for_webhook_result(request_id: str, timeout: float = 30.0, verbose: bool = True) -> Optional[str]:
    """
    Wait for webhook result and return the content.

    Args:
        request_id: The async request ID to wait for
        timeout: Maximum time to wait in seconds
        verbose: Whether to print status messages

    Returns:
        The webhook result content if found, None otherwise
    """
    if not request_id:
        if verbose:
            print("⚠️  No request ID provided")
        return None

    reader = WebhookLogReader()

    if verbose:
        print(f"⏳ Waiting for webhook with request_id: {request_id}")

    webhook = reader.wait_for_webhook(request_id, timeout=timeout)

    if webhook:
        body = webhook.get('body', {})
        if isinstance(body, dict):
            # Try to get result from different possible locations
            result = body.get('result') or body.get('response')
            status = body.get('status', 'unknown')

            if verbose:
                print(f"✓ Webhook received for {request_id}")
                print(f"  Status: {status}")
                print(f"  Timestamp: {webhook.get('timestamp', 'unknown')}")
                
                # If response is an array of content items, extract text
                if isinstance(result, list):
                    text_parts = []
                    for item in result:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text_parts.append(item.get('text', ''))
                    result = ' '.join(text_parts) if text_parts else str(result)

                if isinstance(result, str):
                    preview_len = min(200, len(result))
                    print(f"  Result preview: {result[:preview_len]}...")
                    print(f"  Result length: {len(result)} characters")
                elif isinstance(result, dict):
                    print(f"  Result type: dict with keys: {list(result.keys())}")
                else:
                    print(f"  Result type: {type(result).__name__}")

            return result
        else:
            if verbose:
                print(f"⚠️  Webhook body is not a dict: {type(body).__name__}")
            return body if isinstance(body, str) else str(body)
    else:
        if verbose:
            print(f"⏱️  No webhook received within {timeout}s timeout")

    return None


def verify_webhook_content(
    webhook_result: str,
    expected_keywords: List[str],
    min_keywords: int = None,
    min_length: int = 100,
    description: str = "webhook result"
) -> bool:
    """
    Verify webhook content contains expected keywords and meets length requirements.

    Args:
        webhook_result: The webhook result content
        expected_keywords: List of keywords to look for
        min_keywords: Minimum number of keywords that must be found (default: half of expected)
        min_length: Minimum length of the result
        description: Description for error messages

    Returns:
        True if verification passes

    Raises:
        AssertionError if verification fails
    """
    if not webhook_result:
        raise AssertionError(f"No {description} received")

    # Check length
    actual_length = len(webhook_result)
    assert actual_length >= min_length, \
        f"{description} should be at least {min_length} characters, got {actual_length}"

    # Check keywords
    result_lower = webhook_result.lower()
    found_keywords = []

    for keyword in expected_keywords:
        if keyword.lower() in result_lower:
            found_keywords.append(keyword)

    if min_keywords is None:
        min_keywords = max(1, len(expected_keywords) // 2)

    assert len(found_keywords) >= min_keywords, \
        f"{description} should contain at least {min_keywords} of {expected_keywords}, found: {found_keywords}"

    print(f"✓ {description} verification passed:")
    print(f"  - Length: {actual_length} characters")
    print(f"  - Found keywords: {found_keywords}")

    return True


def is_async_response(response: Any) -> bool:
    """
    Check if a response is an async response with webhook info.
    Handles both string and dict responses.

    Args:
        response: The response from overlord.chat()

    Returns:
        True if response contains webhook URL, False otherwise
    """
    # Check for dict-style async response (most reliable)
    if isinstance(response, dict):
        return (
            response.get('status') == 'processing' and
            'webhook_url' in response and
            'request_id' in response
        )

    # Check for string-style async response (legacy format)
    if isinstance(response, str):
        response_lower = response.lower()
        return (
            "processing async request" in response_lower and
            "webhook" in response_lower and
            ("req_" in response or "request_id" in response_lower)
        )

    return False


def check_response_with_webhook(
    response: Any,
    expected_keywords: List[str] = None,
    min_keywords: int = None,
    min_length: int = 50,
    timeout: float = 30.0,
    test_name: str = "Test"
) -> Tuple[Optional[str], bool]:
    """
    Universal response checker that handles both sync and async responses.
    Always checks if response is async based on structure, not assumptions.

    Args:
        response: The response from overlord.chat()
        expected_keywords: Keywords to verify in result
        min_keywords: Minimum keywords required
        min_length: Minimum result length
        timeout: Webhook timeout
        test_name: Name for logging

    Returns:
        Tuple of (response_text, is_async) where:
        - response_text is the actual response content (from sync or webhook)
        - is_async indicates if this was an async response
    """
    print(f"\n--- {test_name} ---")
    print(f"Response type: {type(response).__name__}")

    # Check if it's an async response by examining structure
    if is_async_response(response):
        print("✓ Detected async processing response")

        # Handle dict response
        if isinstance(response, dict):
            request_id = response.get('request_id')
            webhook_url = response.get('webhook_url')
            status = response.get('status')

            print(f"  Status: {status}")
            print(f"  Request ID: {request_id}")
            print(f"  Webhook URL: {webhook_url}")

            # Wait for webhook
            webhook_result = wait_for_webhook_result(request_id, timeout=timeout)

            if webhook_result:
                # Convert to string if needed
                if isinstance(webhook_result, dict):
                    # If it's a dict with 'response' field, extract the text
                    if 'response' in webhook_result and isinstance(webhook_result['response'], list):
                        # Handle response array format
                        text_parts = []
                        for item in webhook_result['response']:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                text_parts.append(item.get('text', ''))
                        webhook_result = ' '.join(text_parts)
                    else:
                        webhook_result = str(webhook_result)

                # Verify content if requested
                if expected_keywords:
                    verify_webhook_content(
                        webhook_result,
                        expected_keywords,
                        min_keywords=min_keywords,
                        min_length=min_length,
                        description=f"{test_name} webhook result"
                    )

                return webhook_result, True
            else:
                raise AssertionError(f"No webhook received for async response within {timeout}s")

        # Handle string async response (legacy)
        else:
            request_id = extract_request_id(response)
            if request_id:
                print(f"✓ Extracted request ID: {request_id}")

                webhook_result = wait_for_webhook_result(request_id, timeout=timeout)
                if webhook_result:
                    if expected_keywords:
                        verify_webhook_content(
                            webhook_result,
                            expected_keywords,
                            min_keywords=min_keywords,
                            min_length=min_length,
                            description=f"{test_name} webhook result"
                        )
                    return webhook_result, True

            raise AssertionError("Could not extract request ID from async response")

    else:
        # Handle sync response
        print("ℹ️  Response was synchronous (not async)")

        # Convert response to string if needed
        if hasattr(response, '__aiter__'):
            # Handle async generator - this shouldn't happen in sync context
            raise TypeError("Received async generator in sync context")
        else:
            result = str(response) if not isinstance(response, str) else response

        print(f"  Response length: {len(result)} characters")

        # Verify content if requested
        if expected_keywords:
            verify_webhook_content(
                result,
                expected_keywords,
                min_keywords=min_keywords,
                min_length=min_length,
                description=f"{test_name} response"
            )

        return result, False


def check_async_response_with_webhook(
    response: Any,
    expected_keywords: List[str] = None,
    min_keywords: int = None,
    min_length: int = 100,
    timeout: float = 30.0,
    test_name: str = "Async test"
) -> Optional[str]:
    """
    Legacy function maintained for backward compatibility.
    Use check_response_with_webhook() for new tests as it handles both sync and async.

    Returns webhook result if async, None if synchronous response.
    """
    result, is_async = check_response_with_webhook(
        response, expected_keywords, min_keywords, min_length, timeout, test_name
    )
    return result if is_async else None


def setup_webhook_test():
    """Setup function to call before webhook tests"""
    print("\n" + "="*60)
    print("🪝 Webhook Test Setup")
    print("="*60)
    print("⚠️  Ensure webhook server is running: python utils/webhook_server.py")
    print("📍 Webhook URL should be: http://127.0.0.1:8765/")
    print("🧹 Clearing previous webhook logs...")

    clear_webhook_logs()

    print("✓ Ready for webhook testing")
    print("="*60 + "\n")
