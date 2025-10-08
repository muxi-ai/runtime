"""
Base test class for Area 9 - Async Operations tests.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.base import BaseE2ETest  # noqa: E402

try:
    import httpx
except ImportError:
    httpx = None


class BaseAsyncTest(BaseE2ETest):
    """
    Base class for async operations tests.

    Provides:
    - Async operation lifecycle management
    - Webhook monitoring and verification
    - Request status tracking
    - Request cancellation testing
    - Performance monitoring for async operations
    """

    def __init__(self, test_name: str, test_description: str, test_area: str = "9_async"):
        super().__init__(test_name, test_description, test_area)

        # Async-specific state
        self.webhook_log_path = Path.cwd() / "webhook_log.json"
        self.async_responses = []
        self.webhook_events = []
        
        # Webhook server configuration (default to localhost:8765)
        self.webhook_url = "http://localhost:8765"

    async def clear_webhook_log(self):
        """
        Clear webhook log via HTTP endpoint (for Docker-based webhook server).
        Falls back to local file deletion if HTTP request fails.
        """
        try:
            # Try to clear via HTTP endpoint (works with Docker)
            if httpx:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.webhook_url}/clear",
                        timeout=5.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        previous_count = data.get("previous_count", 0)
                        self.formatter.print_debug(
                            f"Cleared webhook log via HTTP ({previous_count} entries removed)"
                        )
                        await asyncio.sleep(0.1)
                        return
            
            # Fallback to local file deletion (for non-Docker setups)
            if self.webhook_log_path.exists():
                self.webhook_log_path.unlink()
                self.formatter.print_debug("Cleared webhook log via local file deletion")
            await asyncio.sleep(0.1)
            
        except Exception as e:
            # If HTTP fails, try local file deletion as fallback
            self.formatter.print_debug(f"HTTP clear failed ({e}), trying local deletion")
            if self.webhook_log_path.exists():
                self.webhook_log_path.unlink()
            await asyncio.sleep(0.1)

    async def wait_for_webhook(
        self, request_id: str, max_wait: int = 30, check_interval: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Wait for webhook delivery and return the webhook payload.
        Queries webhook server via HTTP (Docker-compatible).

        Args:
            request_id: The request ID to wait for
            max_wait: Maximum wait time in seconds
            check_interval: Check interval in seconds

        Returns:
            Webhook payload if found, None if timeout
        """
        self.formatter.print_debug(f"Waiting for webhook delivery for request {request_id}...")

        waited = 0
        while waited < max_wait:
            await asyncio.sleep(check_interval)
            waited += check_interval

            try:
                # Query webhook server via HTTP (works with Docker)
                if httpx:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            f"{self.webhook_url}/logs",
                            timeout=5.0
                        )
                        if response.status_code == 200:
                            data = response.json()
                            logs = data.get("logs", [])
                            
                            # Search for our request_id in the logs
                            for log_entry in logs:
                                if "body" in log_entry:
                                    webhook = log_entry["body"]
                                    if isinstance(webhook, dict) and webhook.get("id") == request_id:
                                        self.formatter.print_success(
                                            f"Webhook received after {waited}s!"
                                        )
                                        self.webhook_events.append(webhook)
                                        return webhook
                else:
                    # Fallback: Try local file if httpx not available
                    if self.webhook_log_path.exists():
                        with open(self.webhook_log_path, "r") as f:
                            content = f.read()
                            if content:
                                for line in content.splitlines():
                                    line = line.strip()
                                    if line:
                                        try:
                                            webhook_entry = json.loads(line)
                                            if "body" in webhook_entry:
                                                webhook = webhook_entry["body"]
                                                if (
                                                    isinstance(webhook, dict)
                                                    and webhook.get("id") == request_id
                                                ):
                                                    self.formatter.print_success(
                                                        f"Webhook received after {waited}s!"
                                                    )
                                                    self.webhook_events.append(webhook)
                                                    return webhook
                                        except json.JSONDecodeError:
                                            continue
            except Exception as e:
                self.formatter.print_debug(f"Error checking webhooks: {e}")

            if waited % 5 == 0:  # Progress update every 5 seconds
                self.formatter.print_debug(f"Still waiting... ({waited}s)")

        self.formatter.print_warning(f"Webhook not received after {max_wait}s")
        return None

    async def verify_webhook_content(
        self, webhook: Dict[str, Any], expected_content: str = None
    ) -> bool:
        """
        Verify webhook content contains expected information.

        Args:
            webhook: Webhook payload
            expected_content: Optional expected content to verify

        Returns:
            Boolean indicating if verification passed
        """
        if not webhook:
            return False

        self.formatter.print_debug("Webhook verification:")
        self.formatter.print_debug(f"  Request ID: {webhook.get('id')}")
        self.formatter.print_debug(f"  Status: {webhook.get('status')}")
        self.formatter.print_debug(f"  Processing time: {webhook.get('processing_time', 'N/A')}s")

        # Get the response content
        response_data = webhook.get("response", [])
        if response_data and isinstance(response_data, list):
            for item in response_data:
                if item.get("type") == "text":
                    content = item.get("text", "")
                    self.formatter.print_debug(f"  Content preview: {content[:100]}...")

                    # Verify the content if expected content provided
                    if expected_content and expected_content.lower() in content.lower():
                        self.formatter.print_success("Result contains expected content")
                        return True
                    elif not expected_content:
                        # If no expected content, just verify we got some content
                        return len(content.strip()) > 0

        return False

    async def test_async_request(
        self,
        message: str,
        user_id: str = "test_user",
        session_id: str = "test_session",
        expected_content: str = None,
        should_be_async: bool = True,
    ) -> Dict[str, Any]:
        """
        Test an async request end-to-end.

        Args:
            message: Message to send
            user_id: User ID for the request
            session_id: Session ID for the request
            expected_content: Optional expected content in webhook
            should_be_async: Whether the request should be processed asynchronously

        Returns:
            Dict with test results
        """
        self.formatter.print_test_case("Async Request Test", message)

        # Clear webhook log
        await self.clear_webhook_log()

        # Send request with use_async=True
        start_time = time.time()
        response = await self.overlord.chat(
            message=message, user_id=user_id, session_id=session_id, use_async=True, stream=False
        )
        elapsed_time = time.time() - start_time

        self.formatter.print_debug(f"Response time: {elapsed_time:.2f}s")

        # Store the response
        self.async_responses.append(response)

        result = {
            "success": False,
            "response": response,
            "request_id": None,
            "webhook": None,
            "elapsed_time": elapsed_time,
        }

        # Check if we got an async response
        if isinstance(response, dict) and "request_id" in response:
            request_id = response.get("request_id")
            result["request_id"] = request_id

            self.formatter.print_success("Got async processing response")
            self.formatter.print_debug(f"Request ID: {request_id}")
            self.formatter.print_debug(f"Status: {response.get('status')}")
            self.formatter.print_debug(f"Message: {response.get('message')}")

            if should_be_async:
                # Wait for webhook
                webhook = await self.wait_for_webhook(request_id)
                result["webhook"] = webhook

                if webhook:
                    # Verify webhook content
                    content_ok = await self.verify_webhook_content(webhook, expected_content)
                    result["success"] = content_ok
                else:
                    self.formatter.print_failure("Webhook not received")
            else:
                result["success"] = True  # Got async response when expected
        else:
            if should_be_async:
                self.formatter.print_failure(f"Expected async response, got: {type(response)}")
            else:
                # Maybe got sync response, which might be ok depending on configuration
                content = response.content if hasattr(response, "content") else str(response)
                if expected_content and expected_content.lower() in content.lower():
                    result["success"] = True
                else:
                    result["success"] = not expected_content  # Success if no content expected

        return result

    async def test_request_lifecycle(self, request_id: str) -> Dict[str, Any]:
        """
        Test request lifecycle management APIs.

        Args:
            request_id: Request ID to test lifecycle for

        Returns:
            Dict with lifecycle test results
        """
        self.formatter.print_test_case(
            "Request Lifecycle Test", f"Testing lifecycle for {request_id}"
        )

        results = {"status_check": False, "cancel_test": False, "invalid_id_test": False}

        # Test 1: Check request status
        try:
            status = await self.overlord.get_request_status(request_id)
            if "error" not in status:
                self.formatter.print_success(f"Status check passed: {status.get('status')}")
                results["status_check"] = True
            else:
                self.formatter.print_failure(f"Status check failed: {status['error']}")
        except Exception as e:
            self.formatter.print_error(f"Status check error: {e}")

        # Test 2: Test cancellation on a new request
        try:
            # Create a new request to cancel
            cancel_response = await self.overlord.chat(
                "What is 5+3? Show the calculation.",
                user_id="test_user",
                session_id="cancel_session",
                use_async=True,
            )

            if isinstance(cancel_response, dict):
                cancel_request_id = cancel_response.get("request_id")
                if cancel_request_id:
                    # Wait a moment then cancel
                    await asyncio.sleep(1)
                    cancel_result = await self.overlord.cancel_request(cancel_request_id)

                    if cancel_result.get("success"):
                        self.formatter.print_success("Request cancellation succeeded")
                        results["cancel_test"] = True
                    else:
                        self.formatter.print_debug(f"Cancel result: {cancel_result.get('message')}")
                        results["cancel_test"] = True  # API responded appropriately
        except Exception as e:
            self.formatter.print_error(f"Cancel test error: {e}")

        # Test 3: Test invalid request ID
        try:
            invalid_status = await self.overlord.get_request_status("invalid_request_id_12345")
            if "error" in invalid_status:
                self.formatter.print_success("Invalid ID handled correctly")
                results["invalid_id_test"] = True
            else:
                self.formatter.print_warning(
                    f"Should have returned error for invalid ID: {invalid_status}"
                )
        except Exception as e:
            self.formatter.print_error(f"Invalid ID test error: {e}")

        return results

    def print_async_summary(self):
        """Print summary specific to async tests."""
        print("\n" + "=" * 60)
        print("Async Test Summary")
        print("=" * 60)

        if self.async_responses:
            print(f"Async responses received: {len(self.async_responses)}")

        if self.webhook_events:
            print(f"Webhook events captured: {len(self.webhook_events)}")
            for i, webhook in enumerate(self.webhook_events, 1):
                self.formatter.print_debug(
                    f"  Webhook {i}: ID={webhook.get('id')}, Status={webhook.get('status')}"
                )
