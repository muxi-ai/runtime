"""
Webhook management for async request completion notifications.

This module handles webhook delivery for async completions with
retry logic and error handling.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Dict
import aiohttp
import logging


logger = logging.getLogger(__name__)


@dataclass
class WebhookPayload:
    """Standardized webhook completion payload."""
    request_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None
    processing_mode: Optional[str] = None  # NEW: async or sync
    user_id: Optional[str] = None  # NEW: user identifier
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "processing_time": self.processing_time,
            "processing_mode": self.processing_mode,
            "user_id": self.user_id,
            "timestamp": self.timestamp
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
        processing_mode: Optional[str] = None,  # NEW: async or sync
        user_id: Optional[str] = None,  # NEW: user identifier
        retries: Optional[int] = None,
        timeout: Optional[int] = None
    ) -> bool:
        """
        Deliver async completion to webhook URL.

        Args:
            webhook_url: URL to deliver the webhook to
            request_id: Request ID that completed
            result: Result data (if successful)
            error: Error message (if failed)
            processing_time: Time taken to process the request
            processing_mode: Processing mode (async or sync)
            user_id: User identifier
            retries: Number of retry attempts (uses default if None)
            timeout: Request timeout (uses default if None)

        Returns:
            True if delivery was successful, False otherwise
        """
        max_retries = retries if retries is not None else self.default_retries
        request_timeout = (
            timeout if timeout is not None else self.default_timeout
        )

        # Determine status based on presence of error
        status = "failed" if error else "completed"

        # Create webhook payload
        payload = WebhookPayload(
            request_id=request_id,
            status=status,
            result=result,
            error=error,
            processing_time=processing_time,
            processing_mode=processing_mode,
            user_id=user_id
        )

        for attempt in range(max_retries + 1):
            try:
                success = await self._deliver_webhook(
                    webhook_url,
                    payload,
                    request_timeout
                )
                if success:
                    logger.info(
                        f"Webhook delivered successfully for request "
                        f"{request_id} on attempt {attempt + 1}"
                    )
                    return True
                else:
                    logger.warning(
                        f"Webhook delivery failed for request "
                        f"{request_id} on attempt {attempt + 1}"
                    )

            except Exception as e:
                logger.error(
                    f"Webhook delivery error for request {request_id} "
                    f"on attempt {attempt + 1}: {e}"
                )

            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                wait_time = min(2 ** attempt, 60)  # Cap at 60 seconds
                await asyncio.sleep(wait_time)

        logger.error(
            f"Webhook delivery failed permanently for request {request_id} "
            f"after {max_retries + 1} attempts"
        )
        return False

    async def _deliver_webhook(
        self,
        webhook_url: str,
        payload: WebhookPayload,
        timeout: int
    ) -> bool:
        """
        Internal method to deliver a single webhook.

        Args:
            webhook_url: URL to deliver the webhook to
            payload: Webhook payload to send
            timeout: Request timeout in seconds

        Returns:
            True if delivery was successful, False otherwise
        """
        session = await self._get_session()

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MUXI-Runtime/1.0",
        }

        try:
            async with session.post(
                webhook_url,
                json=payload.to_dict(),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status >= 200 and response.status < 300:
                    return True
                else:
                    logger.warning(
                        f"Webhook returned status {response.status}: "
                        f"{await response.text()}"
                    )
                    return False

        except asyncio.TimeoutError:
            logger.error(f"Webhook delivery timed out after {timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Webhook delivery exception: {e}")
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
