"""
Unit tests for security utilities.
"""

from muxi.utils.security import sanitize_message_preview, redact_sensitive_content


class TestSanitizeMessagePreview:
    """Test message sanitization for streaming contexts."""

    def test_handles_none_input(self):
        """Test that None input returns safe fallback."""
        result = sanitize_message_preview(None)
        assert result == "[empty message]"

    def test_handles_empty_string(self):
        """Test that empty string returns safe fallback."""
        result = sanitize_message_preview("")
        assert result == "[empty message]"
        result = sanitize_message_preview("   ")
        assert result == "[empty message]"

    def test_redacts_api_keys(self):
        """Test redaction of various API key formats."""
        # OpenAI key
        result = sanitize_message_preview("My key is sk-proj-abcd1234efgh5678ijkl")
        assert "sk-****" in result
        assert "abcd1234" not in result

        # Generic API key
        result = sanitize_message_preview("api_key=super_secret_key_12345678901234567890")
        assert "api_key=****" in result.lower() or "[REDACTED]" in result
        assert "super_secret" not in result

        # GitHub token
        result = sanitize_message_preview("token: ghp_abcdefghijklmnopqrstuvwxyz0123456789")
        assert "ghp_****" in result or "[REDACTED]" in result
        assert "abcdefgh" not in result

    def test_redacts_jwt_tokens(self):
        """Test redaction of JWT tokens."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123"
        result = sanitize_message_preview(f"Bearer {jwt}")
        assert "ey****" in result
        assert "eyJhbGc" not in result

    def test_redacts_passwords(self):
        """Test redaction of passwords."""
        result = sanitize_message_preview("password: mySecretPass123!")
        assert "[REDACTED]" in result or "****" in result
        assert "mySecretPass" not in result

    def test_redacts_emails(self):
        """Test partial redaction of email addresses."""
        result = sanitize_message_preview("Contact me at john.doe@example.com")
        assert "j****@example.com" in result
        assert "john.doe" not in result

    def test_redacts_phone_numbers(self):
        """Test redaction of phone numbers."""
        result = sanitize_message_preview("Call me at 555-123-4567")
        assert "***-***-****" in result
        assert "555-123-4567" not in result

    def test_redacts_credit_cards(self):
        """Test redaction of credit card numbers."""
        result = sanitize_message_preview("Card: 4532-1234-5678-9012")
        assert "****-****-****-****" in result
        assert "4532" not in result

    def test_redacts_ssn(self):
        """Test redaction of SSN."""
        result = sanitize_message_preview("SSN: 123-45-6789")
        assert "***-**-****" in result
        assert "123-45" not in result

    def test_redacts_database_urls(self):
        """Test redaction of database connection strings."""
        result = sanitize_message_preview("Connect to mongodb://user:pass@host:27017/db")
        assert "mongodb://****" in result
        assert "user:pass" not in result

    def test_redacts_urls(self):
        """Test that URLs are replaced."""
        result = sanitize_message_preview("Visit https://api.example.com/secret?key=123")
        assert "[URL]" in result
        assert "example.com" not in result
        assert "key=123" not in result

    def test_redacts_file_paths(self):
        """Test that system paths are redacted."""
        result = sanitize_message_preview("File at /home/user/secrets/api_keys.txt")
        assert "[PATH]" in result
        assert "/home/user" not in result

    def test_redacts_sensitive_keywords(self):
        """Test that sensitive keywords are redacted."""
        keywords = ["private", "confidential", "secret", "credential", "token", "password"]
        for keyword in keywords:
            result = sanitize_message_preview(f"This is a {keyword} document")
            assert "[REDACTED]" in result
            assert keyword.lower() not in result.lower()

    def test_truncates_long_messages(self):
        """Test that long messages are truncated."""
        long_message = "This is a very long message " * 20  # Mix of letters, not just 'a'
        result = sanitize_message_preview(long_message, max_length=200)
        assert len(result) == 200  # 197 chars + "..."
        assert result.endswith("...")

    def test_preserves_safe_content(self):
        """Test that safe content is preserved."""
        safe_message = "Please help me write a Python function"
        result = sanitize_message_preview(safe_message)
        assert "Python function" in result
        assert "[REDACTED]" not in result

    def test_cleans_whitespace(self):
        """Test that excessive whitespace is cleaned."""
        result = sanitize_message_preview("Hello\n\n\r\n   world   \t\t  test")
        assert result == "Hello world test"

    def test_combined_sensitive_content(self):
        """Test handling of multiple sensitive items."""
        message = """
        My API key is sk-proj-abc123xyz789def456ghi012jkl345 and my password is SuperSecret123.
        Email me at admin@company.com or call 555-867-5309.
        Connect via https://db.internal.com/admin?token=xyz
        """
        result = sanitize_message_preview(message)

        # Check all sensitive data is removed
        assert "abc123xyz789" not in result  # Part of API key should be gone
        assert "SuperSecret" not in result
        assert "admin@company.com" not in result  # Email should be masked
        assert "555-867" not in result
        assert "db.internal.com" not in result
        assert "[URL]" in result or "[REDACTED]" in result

    def test_never_returns_empty(self):
        """Test that function never returns empty string."""
        # Even if everything gets redacted
        result = sanitize_message_preview("password secret token")
        assert result  # Should not be empty
        assert len(result) > 0


class TestRedactSensitiveContent:
    """Test the core redaction function."""

    def test_preserves_non_sensitive_text(self):
        """Test that normal text is not modified."""
        text = "This is a normal message about coding"
        result = redact_sensitive_content(text)
        assert result == text

    def test_redacts_aws_credentials(self):
        """Test AWS credential redaction."""
        result = redact_sensitive_content("AKIAIOSFODNN7EXAMPLE")
        assert "AKIA****" in result
        assert "IOSFODNN" not in result

    def test_handles_mixed_case(self):
        """Test case-insensitive matching."""
        # Use longer values that will match the 20+ character requirement
        result = redact_sensitive_content(
            "API_KEY=abc123456789012345678901 "
            "Api_Key=def456789012345678901234 "
            "apikey=ghi789012345678901234567"
        )
        assert "abc123456789" not in result
        assert "def456789012" not in result
        assert "ghi789012345" not in result
        assert "****" in result

    def test_preserves_structure(self):
        """Test that non-sensitive structure is preserved."""
        text = "User said: Hello, can you help?"
        result = redact_sensitive_content(text)
        assert result == text
