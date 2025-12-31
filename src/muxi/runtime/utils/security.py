"""
Security utilities for the MUXI runtime.

Provides functions for redacting sensitive information from strings
before logging, streaming, or other output operations.
"""

import re
from typing import Optional


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

    # Patterns for common API key formats
    # Matches strings like: sk-..., api_key=..., apikey:..., etc.
    api_key_patterns = [
        # OpenAI style keys
        (r'\bsk-[A-Za-z0-9-]{20,}\b', 'sk-****'),
        # Generic API keys with common prefixes
        (
            r'\b(api[-_]?key|apikey|api[-_]?token|access[-_]?token|'
            r'auth[-_]?token|bearer)\s*[:=]\s*["\']?([A-Za-z0-9+/=_-]{20,})["\']?',
            r'\1=****'
        ),
        # AWS Access Keys
        (r'\bAKIA[A-Z0-9]{16}\b', 'AKIA****'),
        # AWS Secret Keys
        (r'\b[A-Za-z0-9+/]{40}\b(?=.*aws|.*secret)', '****'),
        # GitHub tokens
        (r'\bghp_[A-Za-z0-9]{36}\b', 'ghp_****'),
        (r'\bgho_[A-Za-z0-9]{36}\b', 'gho_****'),
        (r'\bghu_[A-Za-z0-9]{36}\b', 'ghu_****'),
        # Google API keys
        (r'\bAIza[A-Za-z0-9_-]{35}\b', 'AIza****'),
        # Slack tokens
        (r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b', 'xox*-****'),
    ]

    # Password patterns
    password_patterns = [
        # With explicit delimiter
        (r'(password|passwd|pwd|pass)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', r'\1=****'),
        # With "is" or space
        (r'(password|passwd|pwd|pass)\s+(is\s+)?([^\s"\']{8,})', r'\1 ****'),
        (r'(secret|client_secret)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', r'\1=****'),
    ]

    # Credit card patterns (basic - matches 13-19 digit numbers with optional formatting)
    credit_card_pattern = r'\b(?:\d{4}[-\s]?){3}\d{1,7}\b'

    # SSN pattern (US format: XXX-XX-XXXX or XXXXXXXXX)
    ssn_pattern = r'\b\d{3}-?\d{2}-?\d{4}\b'

    # Email pattern (partial redaction)
    email_pattern = r'\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'

    # Phone number pattern (US format)
    phone_pattern = r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'

    # Database connection strings
    db_patterns = [
        (r'(mongodb|postgres|postgresql|mysql|redis|sqlite)://[^\s]+', r'\1://****'),
        (r'(host|server)\s*[:=]\s*["\']?([^\s"\']+)["\']?', r'\1=****'),
    ]

    # Apply all redactions
    for pattern, replacement in api_key_patterns:
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)

    for pattern, replacement in password_patterns:
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)

    for pattern, replacement in db_patterns:
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)

    # Credit cards
    redacted = re.sub(credit_card_pattern, '****-****-****-****', redacted)

    # SSNs
    redacted = re.sub(ssn_pattern, '***-**-****', redacted)

    # Emails (show first char and domain)
    redacted = re.sub(email_pattern, lambda m: m.group(1)[0] + '****@' + m.group(2), redacted)

    # Phone numbers
    redacted = re.sub(phone_pattern, '***-***-****', redacted)

    # JWT tokens (they start with ey and are base64)
    redacted = re.sub(r'\bey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', 'ey****.****.****.', redacted)

    # Generic long hex strings that might be tokens (40+ chars)
    redacted = re.sub(r'\b[a-fA-F0-9]{40,}\b', '****', redacted)

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
    # Remove any remaining potential sensitive keywords
    sensitive_words = [
        r'\b(private|confidential|internal|secret|credential|token|key|password|auth)\b',
    ]
    for pattern in sensitive_words:
        sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)

    # Remove any URLs that might contain sensitive parameters
    sanitized = re.sub(r'https?://[^\s]+', '[URL]', sanitized)

    # Remove file paths that might reveal system structure
    sanitized = re.sub(r'[/\\](?:Users|home|var|etc|opt)[/\\][^\s]+', '[PATH]', sanitized)

    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length-3] + "..."

    # Clean up any consecutive spaces or newlines
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()

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
