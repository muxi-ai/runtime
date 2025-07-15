"""
Utility for reading webhook logs in tests.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

# Default log file location (same as in webhook_server.py)
DEFAULT_WEBHOOK_LOG_FILE = "webhook_log.json"


class WebhookLogReader:
    """Read and analyze webhook logs for testing"""

    def __init__(self, log_file: str = DEFAULT_WEBHOOK_LOG_FILE):
        self.log_file = Path(log_file)

    def get_all_webhooks(self) -> List[Dict[str, Any]]:
        """Get all webhook entries from the log"""
        # First try the webhook server API
        try:
            import requests
            response = requests.get("http://127.0.0.1:8765/logs", timeout=1)
            if response.ok:
                data = response.json()
                return data.get('logs', [])
        except Exception:
            pass

        # Fall back to file if server not available
        if not self.log_file.exists():
            return []

        try:
            with open(self.log_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def get_webhooks_by_request_id(self, request_id: str) -> List[Dict[str, Any]]:
        """Get all webhooks for a specific request ID"""
        webhooks = self.get_all_webhooks()
        matching = []

        for webhook in webhooks:
            body = webhook.get("body", {})
            if isinstance(body, dict):
                # Check multiple possible locations for request ID
                # 1. Direct request_id field
                if body.get("request_id") == request_id:
                    matching.append(webhook)
                # 2. ID field (some webhooks use 'id' instead of 'request_id')
                elif body.get("id") == request_id:
                    matching.append(webhook)
                # 3. In nested result
                elif body.get("result", {}).get("request_id") == request_id:
                    matching.append(webhook)
                # 4. In nested response metadata
                elif body.get("response_metadata", {}).get("request_id") == request_id:
                    matching.append(webhook)
            elif isinstance(body, str) and request_id in body:
                # Check in text body
                matching.append(webhook)

        return matching

    def get_latest_webhook(self) -> Optional[Dict[str, Any]]:
        """Get the most recent webhook"""
        webhooks = self.get_all_webhooks()
        return webhooks[-1] if webhooks else None

    def get_webhooks_since(self, timestamp: str) -> List[Dict[str, Any]]:
        """Get all webhooks since a given timestamp"""
        webhooks = self.get_all_webhooks()
        since_dt = datetime.fromisoformat(timestamp)

        matching = []
        for webhook in webhooks:
            webhook_dt = datetime.fromisoformat(webhook["timestamp"])
            if webhook_dt > since_dt:
                matching.append(webhook)

        return matching

    def clear_logs(self):
        """Clear all webhook logs"""
        # First try the webhook server API
        try:
            import requests
            response = requests.delete("http://127.0.0.1:8765/logs", timeout=1)
            if response.ok:
                return
        except Exception:
            pass

        # Fall back to file if server not available
        if self.log_file.exists():
            self.log_file.unlink()

    def wait_for_webhook(self, request_id: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """
        Wait for a webhook with a specific request ID.
        This is a blocking operation that polls the log file.

        Args:
            request_id: The request ID to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            The webhook data if found, None if timeout
        """
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            webhooks = self.get_webhooks_by_request_id(request_id)
            if webhooks:
                return webhooks[0]
            time.sleep(1.0)  # Poll every second

        return None

    def print_webhook_summary(self, webhook: Dict[str, Any]):
        """Print a summary of a webhook for debugging"""
        print("\nWebhook Summary:")
        print(f"  Timestamp: {webhook.get('timestamp')}")
        print(f"  Path: {webhook.get('path')}")

        body = webhook.get("body", {})
        if isinstance(body, dict):
            print(f"  Status: {body.get('status')}")
            print(f"  Request ID: {body.get('request_id')}")

            result = body.get("result", {})
            if result:
                print(f"  Result Type: {type(result).__name__}")
                if isinstance(result, str):
                    print(f"  Result Preview: {result[:200]}...")
                elif isinstance(result, dict):
                    print(f"  Result Keys: {list(result.keys())}")


# Convenience functions for tests
def get_latest_webhook() -> Optional[Dict[str, Any]]:
    """Get the most recent webhook from the default log file"""
    reader = WebhookLogReader()
    return reader.get_latest_webhook()


def get_webhook_for_request(request_id: str) -> Optional[Dict[str, Any]]:
    """Get webhook for a specific request ID from the default log file"""
    reader = WebhookLogReader()
    webhooks = reader.get_webhooks_by_request_id(request_id)
    return webhooks[0] if webhooks else None


def clear_webhook_logs():
    """Clear the default webhook log file"""
    reader = WebhookLogReader()
    reader.clear_logs()
