# src/muxi/utils/zmq_decrypt.py
# Reference implementation for server-side message decryption

import json
import base64
import binascii
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from typing import Dict, Any


def decrypt_zmq_message(encrypted_data: Dict[str, Any], token: str) -> Dict[str, Any]:
    """
    Reference implementation for server-side ZMQ message decryption.

    This function demonstrates how monitoring servers should decrypt
    messages sent by MUXI observability streams with token encryption.

    Args:
        encrypted_data: Encrypted message data from ZMQ stream
        token: Authentication token (same as used for encryption)

    Returns:
        Decrypted event data

    Raises:
        AuthenticationError: If token validation fails
        DecryptionError: If message cannot be decrypted
    """
    if not encrypted_data.get("encrypted"):
        # Handle plaintext messages during migration period
        return encrypted_data

    # Derive decryption key from token (same as encryption)
    key_material = hashlib.sha256(token.encode()).digest()
    key = base64.urlsafe_b64encode(key_material[:32])
    cipher = Fernet(key)

    try:
        # Decrypt payload
        encrypted_bytes = base64.b64decode(encrypted_data["payload"])
        decrypted_json = cipher.decrypt(encrypted_bytes).decode()
        authenticated_data = json.loads(decrypted_json)

        # Validate token
        if authenticated_data.get("auth_token") != token:
            raise AuthenticationError("Invalid token")

        return authenticated_data["event"]

    except (ValueError, KeyError) as e:
        # Missing payload or malformed structure
        raise DecryptionError(f"Failed to decrypt message: {e}")
    except (binascii.Error, UnicodeDecodeError) as e:
        # Invalid base64 or encoding issues
        raise DecryptionError(f"Failed to decrypt message: {e}")
    except json.JSONDecodeError as e:
        # Invalid JSON after decryption
        raise DecryptionError(f"Failed to decrypt message: {e}")
    except InvalidToken:
        # Fernet signature verification failed - wrong token
        raise AuthenticationError("Invalid token")
    except Exception as e:
        # General error fallback
        raise DecryptionError(f"Failed to decrypt message: {e}")


class AuthenticationError(Exception):
    """Raised when token validation fails"""
    pass


class DecryptionError(Exception):
    """Raised when message decryption fails"""
    pass
