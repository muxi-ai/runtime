"""
Webhook management for async request completion notifications.

This module handles webhook delivery for async completions with
retry logic and error handling.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List
import aiohttp


# Import unified response types
from ...types.response import MuxiUnifiedResponse, MuxiContentItem, MuxiErrorDetails
from ...utils.response_converter import create_unified_response


@dataclass
class ClarificationWebhookPayload:
    """Webhook payload for clarification questions in async mode."""

    request_id: str
    clarification_question: str
    clarification_request_id: Optional[str] = None
    original_message: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "status": "awaiting_clarification",
            "clarification_question": self.clarification_question,
            "clarification_request_id": self.clarification_request_id,
            "original_message": self.original_message,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
        }


class WebhookManager:
    """Handles webhook delivery for async completions with retry logic."""

    def __init__(self, default_retries: int = 3, default_timeout: int = 10):
        """
        Initialize webhook manager.

        Args:
            default_retries: Default number of retry attempts
            default_timeout: Default timeout in seconds for webhook requests
        """
        self.default_retries = default_retries
        self.default_timeout = default_timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.default_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def deliver_completion(
        self,
        webhook_url: str,
        request_id: str,
        result: Any = None,
        error: Optional[str] = None,
        processing_time: Optional[float] = None,
        processing_mode: Optional[str] = None,  # async or sync
        user_id: Optional[str] = None,
        formation_id: Optional[str] = None,
        retries: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> bool:
        """
        Deliver async completion to webhook URL using unified response format.

        Args:
            webhook_url: URL to deliver the webhook to
            request_id: Request ID that completed
            result: Result data (if successful)
            error: Error message (if failed)
            processing_time: Time taken to process the request
            processing_mode: Processing mode (async or sync)
            user_id: User identifier
            formation_id: Formation identifier
            retries: Number of retry attempts (uses default if None)
            timeout: Request timeout (uses default if None)

        Returns:
            True if delivery was successful, False otherwise
        """
        max_retries = retries if retries is not None else self.default_retries
        request_timeout = timeout if timeout is not None else self.default_timeout

        # Create unified response payload
        if error:
            # Failed completion
            error_details: MuxiErrorDetails = {
                "code": "processing_failed",
                "message": error,
                "trace": None,
            }
            unified_response = create_unified_response(
                request_id=request_id,
                status="failed",
                content=[],
                formation_id=formation_id,
                user_id=user_id,
                processing_time=processing_time,
                processing_mode=processing_mode or "async",
                webhook_url=webhook_url,
                error=error_details,
            )
        else:
            # Successful completion
            # Convert result to content items
            response_content = []
            if result:
                if hasattr(result, "content"):
                    # MuxiResponse or similar object
                    content_str = str(result.content)
                else:
                    content_str = str(result)

                response_content: List[MuxiContentItem] = [
                    {"type": "text", "text": content_str}
                ]

            unified_response = create_unified_response(
                request_id=request_id,
                status="completed",
                content=response_content,
                formation_id=formation_id,
                user_id=user_id,
                processing_time=processing_time,
                processing_mode=processing_mode or "async",
                webhook_url=webhook_url,
                error=None,
            )

        for attempt in range(max_retries + 1):
            try:
                success = await self._deliver_webhook(
                    webhook_url, unified_response, request_timeout
                )
                if success:
                    if attempt > 0:
                        #  Webhook info - TODO: add observability
                        _ = None  # remove this after implementing observability
                        #     f"✅ Webhook delivered successfully for request "
                        #     f"{request_id} (succeeded on attempt {attempt + 1})"
                        # )
                    else:
                        #  Webhook info - TODO: add observability
                        _ = None  # remove this after implementing observability
                        #     f"✅ Webhook delivered successfully for request "
                        #     f"{request_id}"
                        # )
                    return True
                else:
                    if attempt < max_retries:
                        #  Webhook warning - TODO: add observability
                        _ = None  # remove this after implementing observability
                        #     f"🔄 Webhook delivery attempt "
                        #     f"{attempt + 1}/{max_retries + 1} failed "
                        #     f"for request {request_id}, retrying..."
                        # )
                    else:
                        #  Webhook error - TODO: add observability
                        _ = None  # remove this after implementing observability
                        # f"❌ Webhook delivery failed permanently for "
                        #     f"request {request_id} after {max_retries + 1} "
                        #     f"attempts"
                        # )

            except Exception as e:
                # Provide elegant error messages instead of verbose HTTP details
                _ = self._summarize_webhook_error(e)
                if attempt < max_retries:
                    #  Webhook warning - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"🔄 Webhook delivery attempt "
                    #     f"{attempt + 1}/{max_retries + 1} failed "
                    #     f"for request {request_id}: {error_summary}"
                    # )
                else:
                    #  Webhook error - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"❌ Webhook delivery failed permanently for "
                    #     f"request {request_id}: {error_summary}"
                    # )

            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                wait_time = min(2**attempt, 60)  # Cap at 60 seconds
                #  Webhook debug - TODO: add observability
                await asyncio.sleep(wait_time)

        return False

    def _clean_payload_for_serialization(self, payload: MuxiUnifiedResponse) -> Dict[str, Any]:
        """
        Clean the payload for JSON serialization by removing null fields from content items.

        Args:
            payload: The unified response payload

        Returns:
            Cleaned dictionary ready for JSON serialization
        """
        payload_dict = dict(payload)

        # Clean the response content items
        if "response" in payload_dict and payload_dict["response"]:
            cleaned_response = []
            for item in payload_dict["response"]:
                cleaned_item = {"type": item["type"]}

                # Only include non-null fields
                if item["type"] == "text" and item.get("text") is not None:
                    cleaned_item["text"] = item["text"]
                elif item["type"] == "file" and item.get("file") is not None:
                    cleaned_item["file"] = item["file"]

                cleaned_response.append(cleaned_item)

            payload_dict["response"] = cleaned_response

        return payload_dict

    def _summarize_webhook_error(self, exception: Exception) -> str:
        """
        Convert verbose HTTP exceptions into concise, elegant error summaries.

        Args:
            exception: The exception that occurred during webhook delivery

        Returns:
            A concise, user-friendly error message
        """
        error_str = str(exception).lower()

        # Connection refused/failed
        if "connection refused" in error_str or "connect call failed" in error_str:
            return "Connection refused (service unavailable)"

        # Timeout errors
        if "timeout" in error_str or "timed out" in error_str:
            return "Request timeout"

        # DNS/host resolution errors
        if (
            "name or service not known" in error_str
            or "nodename nor servname provided" in error_str
        ):
            return "Host not found (DNS resolution failed)"

        # SSL/TLS errors
        if "ssl" in error_str and ("certificate" in error_str or "handshake" in error_str):
            return "SSL/TLS handshake failed"

        # HTTP status errors
        if hasattr(exception, "status"):
            status = getattr(exception, "status")
            if status >= 500:
                return f"Server error (HTTP {status})"
            elif status >= 400:
                return f"Client error (HTTP {status})"
            else:
                return f"HTTP {status}"

        # Network unreachable
        if "network is unreachable" in error_str:
            return "Network unreachable"

        # Generic fallback
        exception_type = type(exception).__name__
        if len(str(exception)) > 100:
            return f"{exception_type} (connection failed)"
        else:
            return f"{exception_type}: {str(exception)[:50]}..."

    async def _deliver_webhook(
        self, webhook_url: str, payload: MuxiUnifiedResponse, timeout: int
    ) -> bool:
        """
        Internal method to deliver a single webhook using unified response format.

        Args:
            webhook_url: URL to deliver the webhook to
            payload: Unified response payload to send
            timeout: Request timeout in seconds

        Returns:
            True if delivery was successful, False otherwise
        """
        try:
            session = await self._get_session()

            # Convert unified response to dict for JSON serialization, excluding null fields
            payload_dict = self._clean_payload_for_serialization(payload)

            async with session.post(
                webhook_url, json=payload_dict, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                # Consider 2xx status codes as successful
                if 200 <= response.status < 300:
                    #  Webhook debug - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"Webhook delivered successfully (HTTP {response.status})"
                    # )
                    return True
                else:
                    #  Webhook warning - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"Webhook delivery failed with HTTP {response.status}"
                    # )
                    return False

        except Exception as e:
            #  Webhook debug - TODO: add observability
            _ = e  # remove this after implementing observability
            return False

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def deliver_clarification(
        self,
        webhook_url: str,
        request_id: str,
        clarification_question: str,
        clarification_request_id: Optional[str] = None,
        original_message: Optional[str] = None,
        user_id: Optional[str] = None,
        retries: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> bool:
        """
        Deliver clarification question to webhook URL.

        Args:
            webhook_url: URL to deliver the webhook to
            request_id: Original request ID
            clarification_question: Question that needs clarification
            clarification_request_id: ID for the clarification request
            original_message: Original user message
            user_id: User identifier
            retries: Number of retry attempts (uses default if None)
            timeout: Request timeout (uses default if None)

        Returns:
            True if delivery was successful, False otherwise
        """
        max_retries = retries if retries is not None else self.default_retries
        request_timeout = timeout if timeout is not None else self.default_timeout

        # Create clarification payload
        payload = ClarificationWebhookPayload(
            request_id=request_id,
            clarification_question=clarification_question,
            clarification_request_id=clarification_request_id,
            original_message=original_message,
            user_id=user_id,
        )

        for attempt in range(max_retries + 1):
            try:
                success = await self._deliver_clarification_webhook(
                    webhook_url, payload, request_timeout
                )
                if success:
                    if attempt > 0:
                        #  Webhook info - TODO: add observability
                        _ = None  # remove this after implementing observability
                        #     f"✅ Clarification webhook delivered successfully "
                        #     f"for request {request_id} (succeeded on attempt "
                        #     f"{attempt + 1})"
                        # )
                    else:
                        #  Webhook info - TODO: add observability
                        _ = None  # remove this after implementing observability
                        #     f"✅ Clarification webhook delivered successfully "
                        #     f"for request {request_id}"
                        # )
                    return True
                else:
                    if attempt < max_retries:
                        #  Webhook warning - TODO: add observability
                        _ = None  # remove this after implementing observability
                        #     f"🔄 Clarification webhook delivery attempt "
                        #     f"{attempt + 1}/{max_retries + 1} failed "
                        #     f"for request {request_id}, retrying..."
                        # )
                    else:
                        #  Webhook error - TODO: add observability
                        _ = None  # remove this after implementing observability
                        #     f"❌ Clarification webhook delivery failed "
                        #     f"permanently for request {request_id} "
                        #     f"after {max_retries + 1} attempts"
                        # )

            except Exception as e:
                _ = self._summarize_webhook_error(e)
                if attempt < max_retries:
                    #  Webhook warning - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"🔄 Clarification webhook delivery attempt "
                    #     f"{attempt + 1}/{max_retries + 1} failed "
                    #     f"for request {request_id}: {error_summary}"
                    # )
                else:
                    #  Webhook error - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"❌ Clarification webhook delivery failed "
                    #     f"permanently for request {request_id}: "
                    #     f"{error_summary}"
                    # )

            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                wait_time = min(2**attempt, 60)  # Cap at 60 seconds
                #  Webhook debug - TODO: add observability
                await asyncio.sleep(wait_time)

        return False

    async def _deliver_clarification_webhook(
        self, webhook_url: str, payload: ClarificationWebhookPayload, timeout: int
    ) -> bool:
        """
        Internal method to deliver a clarification webhook.

        Args:
            webhook_url: URL to deliver the webhook to
            payload: Clarification payload to send
            timeout: Request timeout in seconds

        Returns:
            True if delivery was successful, False otherwise
        """
        try:
            session = await self._get_session()

            async with session.post(
                webhook_url, json=payload.to_dict(), timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                # Consider 2xx status codes as successful
                if 200 <= response.status < 300:
                    #  Webhook debug - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"Clarification webhook delivered successfully "
                    #     f"(HTTP {response.status})"
                    # )
                    return True
                else:
                    #  Webhook warning - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"Clarification webhook delivery failed with "
                    #     f"HTTP {response.status}"
                    # )
                    return False

        except Exception as e:
            #  Webhook debug - TODO: add observability
            _ = e  # remove this after implementing observability
            return False
