"""
Security utilities for the MUXI runtime.

Provides functions for redacting sensitive information from strings
before logging, streaming, or other output operations.
"""

import re
from typing import Optional

from .redaction import get_entity_detector, mask_spans
from .sensitive_terms import SENSITIVE_PREVIEW_TERMS

# All redaction patterns are compiled once at import time; the redactor
# runs on every observability event, so per-call compilation and list
# construction are pure hot-path overhead. Pattern strings and flags are
# identical to the originals.

# Patterns for common API key formats
# Matches strings like: sk-..., api_key=..., apikey:..., etc.
_API_KEY_PATTERNS = [
    # OpenAI style keys
    (re.compile(r"\bsk-[A-Za-z0-9-]{20,}\b", re.IGNORECASE), "sk-****"),
    # Generic API keys with common prefixes
    (
        re.compile(
            r"\b(api[-_]?key|apikey|api[-_]?token|access[-_]?token|"
            r'auth[-_]?token|bearer)\s*[:=]\s*["\']?([A-Za-z0-9+/=_-]{20,})["\']?',
            re.IGNORECASE,
        ),
        r"\1=****",
    ),
    # AWS Access Keys
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b", re.IGNORECASE), "AKIA****"),
    # AWS Secret Keys
    (re.compile(r"\b[A-Za-z0-9+/]{40}\b(?=.*aws|.*secret)", re.IGNORECASE), "****"),
    # GitHub tokens
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b", re.IGNORECASE), "ghp_****"),
    (re.compile(r"\bgho_[A-Za-z0-9]{36}\b", re.IGNORECASE), "gho_****"),
    (re.compile(r"\bghu_[A-Za-z0-9]{36}\b", re.IGNORECASE), "ghu_****"),
    # Google API keys
    (re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b", re.IGNORECASE), "AIza****"),
    # Slack tokens
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", re.IGNORECASE), "xox*-****"),
]

# Password patterns
_PASSWORD_PATTERNS = [
    # With explicit delimiter
    (
        re.compile(
            r'(password|passwd|pwd|pass)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', re.IGNORECASE
        ),
        r"\1=****",
    ),
    # With "is" or space
    (re.compile(r'(password|passwd|pwd|pass)\s+(is\s+)?([^\s"\']{8,})', re.IGNORECASE), r"\1 ****"),
    (
        re.compile(r'(secret|client_secret)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', re.IGNORECASE),
        r"\1=****",
    ),
]

# Database connection strings
_DB_PATTERNS = [
    (
        re.compile(r"(mongodb|postgres|postgresql|mysql|redis|sqlite)://[^\s]+", re.IGNORECASE),
        r"\1://****",
    ),
    (re.compile(r'(host|server)\s*[:=]\s*["\']?([^\s"\']+)["\']?', re.IGNORECASE), r"\1=****"),
]

# SSN pattern (US format: XXX-XX-XXXX or XXXXXXXXX)
_SSN_PATTERN = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")

# Email pattern (partial redaction)
_EMAIL_PATTERN = re.compile(r"\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b")

# Phone number pattern (US format)
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

# JWT tokens (they start with ey and are base64)
_JWT_PATTERN = re.compile(r"\bey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

# Generic long hex strings that might be tokens (40+ chars)
_HEX_TOKEN_PATTERN = re.compile(r"\b[a-fA-F0-9]{40,}\b")

# Credit card candidates (validated with Luhn before masking)
_CARD_CANDIDATE_PATTERN = re.compile(r"\b\d[\d -]{11,21}\d\b")
_NON_DIGIT_PATTERN = re.compile(r"\D")


def _luhn_valid(digits: str) -> bool:
    """Return True if a digit string passes the Luhn checksum."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_credit_cards(text: str) -> str:
    """Mask digit sequences that are valid credit-card numbers (Luhn + length)."""

    def _mask(match: re.Match) -> str:
        digits = _NON_DIGIT_PATTERN.sub("", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            # Length-accurate placeholder: one "****" group per 4 digits so a
            # 15-digit Amex or 19-digit card is not misrepresented as 16-digit.
            return "-".join("****" for _ in range((len(digits) + 3) // 4))
        return match.group(0)

    return _CARD_CANDIDATE_PATTERN.sub(_mask, text)


def redact_sensitive_content(text: Optional[str]) -> str:
    """
    Redact potentially sensitive information from text.

    Masks common patterns for:
    - API keys and tokens
    - Passwords and secrets
    - Credit card numbers
    - Social Security Numbers (SSN)
    - Email addresses (partially)
    - Phone numbers
    - AWS credentials
    - Database connection strings

    Args:
        text: Text that may contain sensitive information

    Returns:
        Text with sensitive patterns replaced with redacted placeholders
    """
    if not text:
        return ""

    redacted = str(text)

    # Apply all redactions
    for pattern, replacement in _API_KEY_PATTERNS:
        redacted = pattern.sub(replacement, redacted)

    for pattern, replacement in _PASSWORD_PATTERNS:
        redacted = pattern.sub(replacement, redacted)

    for pattern, replacement in _DB_PATTERNS:
        redacted = pattern.sub(replacement, redacted)

    # Credit cards (Luhn-validated to avoid masking arbitrary long digit strings)
    redacted = _redact_credit_cards(redacted)

    # SSNs
    redacted = _SSN_PATTERN.sub("***-**-****", redacted)

    # Emails (show first char and domain)
    redacted = _EMAIL_PATTERN.sub(lambda m: m.group(1)[0] + "****@" + m.group(2), redacted)

    # Phone numbers
    redacted = _PHONE_PATTERN.sub("***-***-****", redacted)

    # JWT tokens (they start with ey and are base64)
    redacted = _JWT_PATTERN.sub("ey****.****.****.", redacted)

    # Generic long hex strings that might be tokens (40+ chars)
    redacted = _HEX_TOKEN_PATTERN.sub("****", redacted)

    # Optional second layer: entity detection (names, addresses, orgs, DOB,
    # financial). No-op unless an entity detector is registered at startup.
    detector = get_entity_detector()
    if detector is not None and redacted:
        redacted = mask_spans(redacted, detector.detect(redacted))

    return redacted


def sanitize_message_preview(message: Optional[str], max_length: int = 200) -> str:
    """
    Create a sanitized preview of a message for streaming/logging.

    This function is designed specifically for streaming contexts where
    message previews might be exposed in metadata. It applies aggressive
    sanitization to prevent any potential PII or secret leakage.

    Args:
        message: Original message that may contain sensitive data
        max_length: Maximum length of the preview (default 200)

    Returns:
        Sanitized, truncated message safe for streaming metadata.
        Never returns empty string - provides fallback.
    """
    # Handle None or empty input
    if not message:
        return "[empty message]"

    # Convert to string if needed
    message_str = str(message).strip()

    if not message_str:
        return "[empty message]"

    # First apply redaction to remove sensitive patterns
    sanitized = redact_sensitive_content(message_str)

    # Additional aggressive sanitization for streaming context
    # Remove any remaining potential sensitive keywords (shared vocabulary)
    keyword_pattern = r"\b(" + "|".join(sorted(map(re.escape, SENSITIVE_PREVIEW_TERMS))) + r")\b"
    sanitized = re.sub(keyword_pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)

    # Remove any URLs that might contain sensitive parameters
    sanitized = re.sub(r"https?://[^\s]+", "[URL]", sanitized)

    # Remove file paths that might reveal system structure
    sanitized = re.sub(r"[/\\](?:Users|home|var|etc|opt)[/\\][^\s]+", "[PATH]", sanitized)

    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[: max_length - 3] + "..."

    # Clean up any consecutive spaces or newlines
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # Ensure we never return empty
    if not sanitized:
        return "[redacted message]"

    return sanitized


def redact_message_preview(message: str, max_length: int = 500) -> str:
    """
    Create a redacted preview of a message for logging/streaming.

    DEPRECATED: Use sanitize_message_preview() for streaming contexts.

    Args:
        message: Original message that may contain sensitive data
        max_length: Maximum length of the preview (default 500)

    Returns:
        Truncated and redacted message safe for output
    """
    if not message:
        return ""

    # First truncate to max length
    preview = message[:max_length]

    # Then redact sensitive content
    return redact_sensitive_content(preview)
