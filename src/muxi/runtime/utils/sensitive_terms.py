"""
Canonical sensitive-term vocabulary shared across redaction sites.

Two sets are exposed because the two consumers match differently:

- ``SENSITIVE_KEY_TERMS`` is **substring**-matched against structured keys and
  extracted memory sentences (``services/memory/extractor.py``). Terms must stay
  specific enough to avoid false positives under substring matching (e.g. a
  generic "key" would wrongly flag "monkey").
- ``SENSITIVE_PREVIEW_TERMS`` is **word-boundary**-matched in free-text message
  previews (``utils/security.py``). It may include broad generic words because
  ``\b`` prevents mid-word matches.

Keeping both in one module gives a single place to evolve the vocabulary while
respecting the distinct matching strategies.
"""

from typing import FrozenSet

# Substring-matched against keys / extracted sentences (memory extractor).
SENSITIVE_KEY_TERMS: FrozenSet[str] = frozenset(
    {
        "password",
        "social_security",
        "ssn",
        "credit_card",
        "bank_account",
        "passport",
        "license",
        "secret",
        "private",
        "confidential",
    }
)

# Word-boundary-matched in free-text previews (sanitize_message_preview).
SENSITIVE_PREVIEW_TERMS: FrozenSet[str] = frozenset(
    {
        "private",
        "confidential",
        "internal",
        "secret",
        "credential",
        "token",
        "key",
        "password",
        "auth",
    }
)
