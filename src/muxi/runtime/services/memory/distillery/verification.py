# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Distillery Signature Verification - Ed25519 Batch Auth
# Description:  Public key parsing and fail-closed batch signature checks
# Role:         Authenticates POST /v1/memories/distilled batches
# Usage:        Used by the distilled route and MemoryDistilleryService
# Author:       Muxi Framework Team
#
# Memory Distillery (Phase 3b). Every distilled batch must be signed with
# the registered distillery's Ed25519 private key. The signed message is:
#
#     b"muxi-distillery-v1\n" + timestamp + b"\n" + distillery_id + b"\n" + body
#
# where `timestamp` is the X-Distillery-Timestamp header (unix seconds,
# exactly as sent), `distillery_id` is the X-Distillery-ID header, and
# `body` is the RAW request body bytes. Signing the exact bytes on the wire
# (rather than re-canonicalized JSON) removes every canonicalization
# ambiguity between signer and verifier -- the distillery signs precisely
# what it POSTs. The domain-separation prefix and the header bindings stop
# cross-protocol reuse and batch replay against a different distillery id.
#
# Security posture:
# - Fail-closed: ANY parsing/verification error is an authentication
#   failure. There is no "skip verification" path.
# - Constant-time-safe: verification goes through the cryptography
#   library's Ed25519 verify (no signature byte comparison in Python, no
#   early-exit string equality on secrets).
# - Replay protection: timestamps outside the +/- max-age window are
#   rejected before any signature math runs.
# =============================================================================

import base64
import binascii
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

# Domain-separation prefix for signed messages (versioned so the signing
# contract can evolve without ambiguity).
SIGNATURE_DOMAIN = b"muxi-distillery-v1"

# Registered public keys carry this prefix (PRD "Distillery Registration").
PUBLIC_KEY_PREFIX = "ed25519:"

# Replay window default (PRD: batches older than 5 minutes are rejected).
DEFAULT_SIGNATURE_MAX_AGE_SECONDS = 300

# Raw Ed25519 public keys are exactly 32 bytes.
_RAW_KEY_LENGTH = 32


class SignatureVerificationError(Exception):
    """A batch failed authentication. Message is safe to return to callers."""


def parse_public_key(public_key: str) -> Ed25519PublicKey:
    """Parse a registered public key string into an Ed25519 key object.

    Accepts ``ed25519:<base64>`` (prefix optional) where the base64 decodes
    to either a DER SubjectPublicKeyInfo blob (the PRD's ``MCowBQYDK2Vw...``
    shape) or raw 32-byte Ed25519 public bytes.

    Raises:
        ValueError: When the key cannot be parsed as an Ed25519 public key.
    """
    if not isinstance(public_key, str) or not public_key.strip():
        raise ValueError("public_key must be a non-empty string")
    encoded = public_key.strip()
    if encoded.lower().startswith(PUBLIC_KEY_PREFIX):
        encoded = encoded[len(PUBLIC_KEY_PREFIX) :]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"public_key is not valid base64: {exc}") from exc

    if len(raw) == _RAW_KEY_LENGTH:
        return Ed25519PublicKey.from_public_bytes(raw)
    try:
        key = load_der_public_key(raw)
    except Exception as exc:
        raise ValueError(f"public_key is not a DER-encoded public key: {exc}") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"public_key must be Ed25519, got {type(key).__name__}")
    return key


def check_timestamp(
    timestamp_header: Optional[str],
    now: float,
    max_age_seconds: int = DEFAULT_SIGNATURE_MAX_AGE_SECONDS,
) -> int:
    """Validate the replay-protection timestamp header.

    The window is symmetric (+/- max_age_seconds) so modest clock skew on
    either side doesn't reject honest batches while stale captures do.

    Returns the parsed unix timestamp.

    Raises:
        SignatureVerificationError: Missing, malformed, or out-of-window.
    """
    if not timestamp_header:
        raise SignatureVerificationError("X-Distillery-Timestamp header is required")
    try:
        timestamp = int(str(timestamp_header).strip())
    except (TypeError, ValueError):
        raise SignatureVerificationError(
            "X-Distillery-Timestamp must be an integer unix timestamp (seconds)"
        )
    if abs(now - timestamp) > max_age_seconds:
        raise SignatureVerificationError(
            f"Batch timestamp outside the {max_age_seconds}s replay-protection window"
        )
    return timestamp


def signed_message(timestamp: str, distillery_id: str, body: bytes) -> bytes:
    """Build the exact byte string a distillery signs for one batch."""
    return b"\n".join(
        [
            SIGNATURE_DOMAIN,
            str(timestamp).strip().encode("utf-8"),
            distillery_id.encode("utf-8"),
            body,
        ]
    )


def verify_signature(
    public_key: str,
    signature_header: Optional[str],
    timestamp: str,
    distillery_id: str,
    body: bytes,
) -> None:
    """Verify one batch signature; fail-closed on any error.

    Args:
        public_key: The registered key string (``ed25519:...``).
        signature_header: X-Distillery-Signature (base64 Ed25519 signature).
        timestamp: X-Distillery-Timestamp exactly as sent.
        distillery_id: X-Distillery-ID exactly as sent.
        body: Raw request body bytes.

    Raises:
        SignatureVerificationError: On any missing, malformed, or invalid
            input. The message never reveals which check failed beyond
            what the caller needs for a 401.
    """
    if not signature_header:
        raise SignatureVerificationError("X-Distillery-Signature header is required")
    try:
        key = parse_public_key(public_key)
        signature = base64.b64decode(str(signature_header).strip(), validate=True)
        key.verify(signature, signed_message(timestamp, distillery_id, body))
    except SignatureVerificationError:
        raise
    except Exception:
        # Fail-closed: malformed base64, bad key material, and an
        # InvalidSignature are all the same authentication failure to the
        # caller -- no distinguishing detail leaks.
        raise SignatureVerificationError("Batch signature verification failed")
