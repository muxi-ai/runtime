"""
Token-based encryption for ZeroMQ observability streams.

This module provides symmetric encryption derived from authentication tokens,
ensuring both authentication and data protection for observability data.
"""

import json
import time
import base64
import hashlib
from typing import Dict, Any
from cryptography.fernet import Fernet


class TokenEncryption:
    """
    Token-based encryption for ZeroMQ observability messages.

    Derives encryption keys from authentication tokens and provides
    format-agnostic encryption that works before message serialization.
    """

    def __init__(self, token: str):
        """
        Initialize encryption with authentication token.

        Args:
            token: Authentication token used for both auth and key derivation
        """
        self.token = token
        # Derive encryption key from token
        key_material = hashlib.sha256(token.encode()).digest()
        self.key = base64.urlsafe_b64encode(key_material[:32])
        self.cipher = Fernet(self.key)

    def encrypt_message(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt raw event data before formatting.

        This method adds authentication token and timestamp, then encrypts
        the entire payload. The result is format-agnostic and can be
        serialized using any format (msgpack, jsonl, protobuf).

        Args:
            event_data: Raw event data to encrypt

        Returns:
            Dictionary with encrypted payload and metadata
        """
        # Add authentication token and timestamp
        authenticated_data = {
            "auth_token": self.token,
            "timestamp": time.time(),
            "event": event_data,
        }

        # Encrypt as JSON (format-neutral)
        json_str = json.dumps(authenticated_data, separators=(",", ":"))
        encrypted_bytes = self.cipher.encrypt(json_str.encode())
        encrypted_payload = base64.b64encode(encrypted_bytes).decode()

        return {"encrypted": True, "payload": encrypted_payload}
