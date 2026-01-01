"""
Async webhook testing utilities for Day 3 tests.
Provides async functions for webhook verification in async processing tests.
"""

import asyncio
import aiohttp
from typing import Optional, Any, List, Tuple
from .webhook_test_utils import extract_request_id, verify_webhook_content


async def wait_for_webhook_async(
    request_id: str,
    timeout: float = 30.0,
    check_interval: float = 1.0,
    verbose: bool = True
) -> Optional[str]:
    """
    Asynchronously wait for webhook result.

    Args:
        request_id: The async request ID to wait for
        timeout: Maximum time to wait in seconds
        check_interval: How often to check for webhook (seconds)
        verbose: Whether to print status messages

    Returns:
        The webhook result content if found, None otherwise
    """
    if not request_id:
        if verbose:
            print("⚠️  No request ID provided")
        return None

    start_time = asyncio.get_event_loop().time()

    async with aiohttp.ClientSession() as session:
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                async with session.get("http://127.0.0.1:8765/logs") as response:
                    if response.status == 200:
                        data = await response.json()

                        # Check for our webhook
                        for webhook in data.get('logs', []):
                            body = webhook.get('body', {})
                            if isinstance(body, dict) and body.get('id') == request_id:
                                # Found our webhook
                                status = body.get('status', 'unknown')

                                if verbose:
                                    elapsed = asyncio.get_event_loop().time() - start_time
                                    print(f"✓ Webhook received for {request_id} after {elapsed:.1f}s")
                                    print(f"  Status: {status}")

                                # Extract result
                                result = body.get('result') or body.get('response')

                                # If response is an array of content items, extract text
                                if isinstance(result, list):
                                    text_parts = []
                                    for item in result:
                                        if isinstance(item, dict) and item.get('type') == 'text':
                                            text_parts.append(item.get('text', ''))
                                    result = ' '.join(text_parts) if text_parts else str(result)

                                return result

            except Exception as e:
                if verbose:
                    print(f"⚠️  Error checking webhooks: {e}")

            # Wait before next check
            await asyncio.sleep(check_interval)

    if verbose:
        print(f"⏱️  No webhook received within {timeout}s timeout")

    return None


async def check_response_with_webhook_async(
    response: Any,
    expected_keywords: List[str] = None,
    min_keywords: int = None,
    min_length: int = 50,
    timeout: float = 30.0,
    test_name: str = "Test"
) -> Tuple[Optional[str], bool]:
    """
    Async version of check_response_with_webhook.
    Handles both sync and async responses without blocking the event loop.

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
    from .webhook_test_utils import is_async_response

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

            # Wait for webhook asynchronously
            webhook_result = await wait_for_webhook_async(request_id, timeout=timeout)

            if webhook_result:
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

                webhook_result = await wait_for_webhook_async(request_id, timeout=timeout)
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
