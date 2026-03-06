"""
Unit tests for webhook signing functionality.
"""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

from muxi.runtime.formation.background import sign_webhook


class TestSignWebhook:
    """Tests for the sign_webhook function."""

    def test_sign_webhook_returns_header_and_timestamp(self):
        """sign_webhook returns a signature header and timestamp."""
        payload = {"id": "req_123", "status": "completed"}
        secret = "test_secret_key"

        header, timestamp = sign_webhook(payload, secret)

        assert header.startswith("t=")
        assert ",v1=" in header
        assert isinstance(timestamp, int)

    def test_signature_format(self):
        """Signature header has correct format: t={timestamp},v1={hex}."""
        payload = {"id": "req_123", "status": "completed"}
        secret = "test_secret"

        header, timestamp = sign_webhook(payload, secret)

        parts = header.split(",")
        assert len(parts) == 2
        assert parts[0].startswith("t=")
        assert parts[1].startswith("v1=")

        # SHA256 hex is 64 characters
        signature_hex = parts[1].split("=")[1]
        assert len(signature_hex) == 64

    def test_signature_is_deterministic(self):
        """Same payload + secret + timestamp produces same signature."""
        payload = {"id": "req_123", "status": "completed"}
        secret = "test_secret"

        with patch("time.time", return_value=1704067200):
            header1, _ = sign_webhook(payload, secret)
            header2, _ = sign_webhook(payload, secret)

        assert header1 == header2

    def test_different_secrets_produce_different_signatures(self):
        """Different secrets produce different signatures."""
        payload = {"id": "req_123", "status": "completed"}

        with patch("time.time", return_value=1704067200):
            header1, _ = sign_webhook(payload, "secret1")
            header2, _ = sign_webhook(payload, "secret2")

        # Extract just the signature part
        sig1 = header1.split(",v1=")[1]
        sig2 = header2.split(",v1=")[1]

        assert sig1 != sig2

    def test_different_payloads_produce_different_signatures(self):
        """Different payloads produce different signatures."""
        secret = "test_secret"

        with patch("time.time", return_value=1704067200):
            header1, _ = sign_webhook({"id": "req_123"}, secret)
            header2, _ = sign_webhook({"id": "req_456"}, secret)

        sig1 = header1.split(",v1=")[1]
        sig2 = header2.split(",v1=")[1]

        assert sig1 != sig2

    def test_payload_key_order_does_not_affect_signature(self):
        """Payload key order doesn't affect signature (sorted keys)."""
        secret = "test_secret"

        # Different key orders
        payload1 = {"b": 2, "a": 1, "c": 3}
        payload2 = {"a": 1, "c": 3, "b": 2}

        with patch("time.time", return_value=1704067200):
            header1, _ = sign_webhook(payload1, secret)
            header2, _ = sign_webhook(payload2, secret)

        assert header1 == header2

    def test_signature_can_be_verified_manually(self):
        """Signature can be verified using standard HMAC-SHA256."""
        payload = {"id": "req_123", "status": "completed"}
        secret = "test_secret"
        fixed_time = 1704067200

        with patch("time.time", return_value=fixed_time):
            header, timestamp = sign_webhook(payload, secret)

        # Manual verification
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        message = f"{timestamp}.".encode("utf-8") + payload_bytes
        expected_sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

        actual_sig = header.split(",v1=")[1]
        assert actual_sig == expected_sig

    def test_timestamp_is_current_time(self):
        """Timestamp should be close to current time."""
        payload = {"id": "req_123"}
        secret = "test_secret"

        before = int(time.time())
        _, timestamp = sign_webhook(payload, secret)
        after = int(time.time())

        assert before <= timestamp <= after

    def test_empty_payload(self):
        """Empty payload should still produce valid signature."""
        payload = {}
        secret = "test_secret"

        header, timestamp = sign_webhook(payload, secret)

        assert header.startswith("t=")
        assert ",v1=" in header

    def test_complex_payload(self):
        """Complex nested payload should work correctly."""
        payload = {
            "id": "req_123",
            "response": [{"type": "text", "text": "Hello"}],
            "metadata": {"nested": {"deep": True}},
            "numbers": [1, 2, 3],
        }
        secret = "test_secret"

        header, timestamp = sign_webhook(payload, secret)

        assert header.startswith("t=")
        assert ",v1=" in header
        assert len(header.split(",v1=")[1]) == 64
