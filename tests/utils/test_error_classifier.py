"""
Unit tests for the error classification utility.
"""

import unittest
import asyncio
from src.muxi.runtime.utils.error_classifier import (
    classify_error_code,
    is_retryable_error,
    get_http_status_for_error,
    EXCEPTION_TO_ERROR_CODE
)


class TestErrorClassifier(unittest.TestCase):
    """Test cases for the error classifier."""

    def test_exception_type_classification(self):
        """Test classification based on exception types."""
        # Test ValueError
        error = ValueError("Invalid value")
        self.assertEqual(classify_error_code(error), "INVALID_PARAMS")

        # Test TypeError
        error = TypeError("Wrong type")
        self.assertEqual(classify_error_code(error), "INVALID_PARAMS")

        # Test KeyError
        error = KeyError("missing_key")
        self.assertEqual(classify_error_code(error), "RESOURCE_NOT_FOUND")

        # Test FileNotFoundError
        error = FileNotFoundError("file not found")
        self.assertEqual(classify_error_code(error), "RESOURCE_NOT_FOUND")

        # Test PermissionError
        error = PermissionError("access denied")
        self.assertEqual(classify_error_code(error), "FORBIDDEN")

        # Test ConnectionError
        error = ConnectionError("connection failed")
        self.assertEqual(classify_error_code(error), "CONNECTION_ERROR")

        # Test TimeoutError
        error = TimeoutError("operation timed out")
        self.assertEqual(classify_error_code(error), "TIMEOUT")

        # Test asyncio.TimeoutError
        error = asyncio.TimeoutError("async timeout")
        self.assertEqual(classify_error_code(error), "TIMEOUT")

    def test_message_pattern_classification(self):
        """Test classification based on error message patterns."""
        # Test "not found" patterns
        error = Exception("agent not found")
        self.assertEqual(classify_error_code(error), "AGENT_NOT_FOUND")

        error = Exception("formation not found")
        self.assertEqual(classify_error_code(error), "FORMATION_NOT_FOUND")

        error = Exception("tool not found")
        self.assertEqual(classify_error_code(error), "TOOL_NOT_FOUND")

        error = Exception("resource not found")
        self.assertEqual(classify_error_code(error), "RESOURCE_NOT_FOUND")

        # Test timeout patterns
        error = Exception("operation timeout")
        self.assertEqual(classify_error_code(error), "TIMEOUT")

        error = Exception("request timed out")
        self.assertEqual(classify_error_code(error), "TIMEOUT")

        # Test cancellation patterns
        error = Exception("operation cancelled")
        self.assertEqual(classify_error_code(error), "CANCELLED")

        error = Exception("request canceled")
        self.assertEqual(classify_error_code(error), "CANCELLED")

        # Test authentication patterns
        error = Exception("unauthorized access")
        self.assertEqual(classify_error_code(error), "UNAUTHORIZED")

        error = Exception("authentication failed")
        self.assertEqual(classify_error_code(error), "UNAUTHORIZED")

        # Test permission patterns
        error = Exception("forbidden operation")
        self.assertEqual(classify_error_code(error), "FORBIDDEN")

        error = Exception("permission denied")
        self.assertEqual(classify_error_code(error), "FORBIDDEN")

        # Test rate limiting patterns
        error = Exception("rate limit exceeded")
        self.assertEqual(classify_error_code(error), "RATE_LIMITED")

        error = Exception("too many requests")
        self.assertEqual(classify_error_code(error), "RATE_LIMITED")

        # Test validation patterns
        error = Exception("invalid request format")
        self.assertEqual(classify_error_code(error), "INVALID_REQUEST")

        error = Exception("malformed data")
        self.assertEqual(classify_error_code(error), "INVALID_REQUEST")

    def test_fallback_classification(self):
        """Test fallback to INTERNAL_ERROR for unknown exceptions."""
        error = Exception("unknown error message")
        self.assertEqual(classify_error_code(error), "INTERNAL_ERROR")

        # Custom exception type
        class CustomError(Exception):
            pass

        error = CustomError("custom error")
        self.assertEqual(classify_error_code(error), "INTERNAL_ERROR")

    def test_exception_type_priority(self):
        """Test that specific exception types take priority over message patterns."""
        # ValueError should be INVALID_PARAMS even if message suggests something else
        error = ValueError("agent not found")
        self.assertEqual(classify_error_code(error), "INVALID_PARAMS")

        # TimeoutError should be TIMEOUT even if message suggests something else
        error = TimeoutError("invalid request")
        self.assertEqual(classify_error_code(error), "TIMEOUT")

    def test_is_retryable_error(self):
        """Test retryable error identification."""
        # Retryable errors
        retryable_codes = [
            "TIMEOUT",
            "CONNECTION_ERROR",
            "NETWORK_ERROR",
            "SYSTEM_OVERLOAD",
            "RATE_LIMITED",
            "LLM_RATE_LIMITED"
        ]

        for code in retryable_codes:
            self.assertTrue(is_retryable_error(code), f"{code} should be retryable")

        # Non-retryable errors
        non_retryable_codes = [
            "INVALID_PARAMS",
            "UNAUTHORIZED",
            "FORBIDDEN",
            "RESOURCE_NOT_FOUND",
            "PARSE_ERROR",
            "CANCELLED"
        ]

        for code in non_retryable_codes:
            self.assertFalse(is_retryable_error(code), f"{code} should not be retryable")

    def test_get_http_status_for_error(self):
        """Test HTTP status code retrieval."""
        # Test known error codes
        self.assertEqual(get_http_status_for_error("UNAUTHORIZED"), 401)
        self.assertEqual(get_http_status_for_error("FORBIDDEN"), 403)
        self.assertEqual(get_http_status_for_error("RESOURCE_NOT_FOUND"), 404)
        self.assertEqual(get_http_status_for_error("TIMEOUT"), 408)
        self.assertEqual(get_http_status_for_error("RATE_LIMITED"), 429)
        self.assertEqual(get_http_status_for_error("INTERNAL_ERROR"), 500)

        # Test unknown error code (should default to 500)
        self.assertEqual(get_http_status_for_error("UNKNOWN_ERROR"), 500)

    def test_exception_to_error_code_mapping(self):
        """Test the exception to error code mapping dictionary."""
        # Verify mapping contains expected exception types
        expected_exceptions = [
            ValueError,
            TypeError,
            KeyError,
            FileNotFoundError,
            PermissionError,
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
            Exception  # Fallback
        ]

        for exc_type in expected_exceptions:
            self.assertIn(exc_type, EXCEPTION_TO_ERROR_CODE)

        # Verify mapping values are valid error codes
        for exc_type, error_code in EXCEPTION_TO_ERROR_CODE.items():
            self.assertIsInstance(error_code, str)
            self.assertTrue(len(error_code) > 0)

    def test_case_insensitive_message_matching(self):
        """Test that message pattern matching is case insensitive."""
        # Test uppercase
        error = Exception("AGENT NOT FOUND")
        self.assertEqual(classify_error_code(error), "AGENT_NOT_FOUND")

        # Test mixed case
        error = Exception("Operation TIMEOUT")
        self.assertEqual(classify_error_code(error), "TIMEOUT")

        # Test lowercase
        error = Exception("unauthorized access")
        self.assertEqual(classify_error_code(error), "UNAUTHORIZED")

    def test_complex_error_messages(self):
        """Test classification with complex error messages."""
        # Multiple keywords - should match the first applicable pattern
        error = Exception("The agent 'test-agent' was not found in the system")
        self.assertEqual(classify_error_code(error), "AGENT_NOT_FOUND")

        # Embedded keywords
        error = Exception("Request validation failed: invalid parameters provided")
        self.assertEqual(classify_error_code(error), "INVALID_REQUEST")

        # No matching patterns
        error = Exception("Something went wrong in the system")
        self.assertEqual(classify_error_code(error), "INTERNAL_ERROR")


if __name__ == "__main__":
    unittest.main()
