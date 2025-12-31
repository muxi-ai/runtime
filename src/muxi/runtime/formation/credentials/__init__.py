"""
Credential management module for user-specific service authentication.

This module provides:
- CredentialResolver: Base credential storage and resolution
- EncryptedCredentialResolver: Encrypted credential storage with per-user key derivation
- CredentialHandler: LLM-based credential detection and processing logic
- Credential exceptions for error handling
"""

from .resolver import CredentialResolver
from .encrypted import EncryptedCredentialResolver
from .exceptions import MissingCredentialError, AmbiguousCredentialError
from .handler import CredentialHandler

__all__ = [
    "CredentialResolver",
    "EncryptedCredentialResolver",
    "MissingCredentialError",
    "AmbiguousCredentialError",
    "CredentialHandler",
]
