"""
API key generation utilities for the Overlord.
"""

import secrets
import string
from typing import Literal


def generate_api_key(key_type: Literal["client", "admin"]) -> str:
    """
    Generate a new API key with appropriate prefix.

    Args:
        key_type: Type of key to generate ("client" or "admin").
            Determines the prefix of the generated key.

    Returns:
        A new API key string in the format:
        - Client keys: "sk_muxi_client_[random string]"
        - Admin keys: "sk_muxi_admin_[random string]"
    """
    # Constants for API key generation
    API_KEY_LENGTH = 24
    ALPHABET = string.ascii_letters + string.digits

    # Generate a random string using secure random
    random_part = "".join(secrets.choice(ALPHABET) for _ in range(API_KEY_LENGTH))

    # Add the appropriate prefix based on key type
    prefix = "sk_muxi_client" if key_type == "client" else "sk_muxi_admin"
    return f"{prefix}_{random_part}"
