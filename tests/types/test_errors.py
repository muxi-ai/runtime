"""
Unit tests for the error code registry.
"""

import unittest
from src.muxi.datatypes.errors import (
    ErrorCodeInfo,
    ERROR_CODE_REGISTRY,
    get_error_info,
    get_error_message,
    get_http_status,
    create_error_details
)


class TestErrorCodeRegistry(unittest.TestCase):
    """Test cases for the error code registry."""

    def test_error_code_info_structure(self):
        """Test ErrorCodeInfo dataclass structure."""
        error_info = ErrorCodeInfo(
            code="TEST_ERROR",
            message="Test error message",
            http_status=400,
            category="test",
            description="Test description"
        )

        self.assertEqual(error_info.code, "TEST_ERROR")
        self.assertEqual(error_info.message, "Test error message")
        self.assertEqual(error_info.http_status, 400)
        self.assertEqual(error_info.category, "test")
        self.assertEqual(error_info.description, "Test description")

    def test_error_registry_completeness(self):
        """Test that error registry contains expected error codes."""
        expected_codes = [
            "INTERNAL_ERROR", "SYSTEM_OVERLOAD", "TIMEOUT", "CANCELLED",
            "UNAUTHORIZED", "FORBIDDEN", "BAD_CREDENTIALS",
            "INVALID_REQUEST", "INVALID_PARAMS", "PARSE_ERROR", "METHOD_NOT_FOUND",
            "AGENT_NOT_FOUND", "FORMATION_NOT_FOUND", "TOOL_NOT_FOUND", "RESOURCE_NOT_FOUND",
            "PROCESSING_ERROR", "TOOL_EXECUTION_ERROR", "LLM_ERROR", "CLARIFICATION_FAILED",
            "RATE_LIMITED", "LLM_RATE_LIMITED",
            "CONNECTION_ERROR", "NETWORK_ERROR", "BAD_GATEWAY", "WEBHOOK_DELIVERY_FAILED",
            "MCP_CONNECTION_ERROR", "MCP_PROTOCOL_ERROR", "MCP_TOOL_TIMEOUT"
        ]

        for code in expected_codes:
            self.assertIn(code, ERROR_CODE_REGISTRY, f"Missing error code: {code}")

        # Verify all entries are ErrorCodeInfo instances
        for code, info in ERROR_CODE_REGISTRY.items():
            self.assertIsInstance(info, ErrorCodeInfo)
            self.assertEqual(info.code, code)
            self.assertIsInstance(info.message, str)
            self.assertIsInstance(info.http_status, int)
            self.assertIsInstance(info.category, str)
            self.assertIsInstance(info.description, str)

    def test_get_error_info(self):
        """Test get_error_info function."""
        # Test existing error code
        info = get_error_info("INTERNAL_ERROR")
        self.assertIsNotNone(info)
        self.assertEqual(info.code, "INTERNAL_ERROR")
        self.assertEqual(info.http_status, 500)

        # Test non-existing error code
        info = get_error_info("NON_EXISTENT_ERROR")
        self.assertIsNone(info)

    def test_get_error_message(self):
        """Test get_error_message function."""
        # Test existing error code
        message = get_error_message("TIMEOUT")
        self.assertEqual(message, "Operation timed out")

        # Test non-existing error code with default
        message = get_error_message("NON_EXISTENT_ERROR")
        self.assertEqual(message, "An error occurred")

        # Test non-existing error code with custom default
        message = get_error_message("NON_EXISTENT_ERROR", "Custom default")
        self.assertEqual(message, "Custom default")

    def test_get_http_status(self):
        """Test get_http_status function."""
        # Test existing error code
        status = get_http_status("UNAUTHORIZED")
        self.assertEqual(status, 401)

        # Test non-existing error code with default
        status = get_http_status("NON_EXISTENT_ERROR")
        self.assertEqual(status, 500)

        # Test non-existing error code with custom default
        status = get_http_status("NON_EXISTENT_ERROR", 400)
        self.assertEqual(status, 400)

    def test_create_error_details(self):
        """Test create_error_details function."""
        # Test with existing error code
        details = create_error_details("TIMEOUT")
        expected = {
            "code": "TIMEOUT",
            "message": "Operation timed out",
            "trace": None
        }
        self.assertEqual(details, expected)

        # Test with custom message
        details = create_error_details("TIMEOUT", "Custom timeout message")
        expected = {
            "code": "TIMEOUT",
            "message": "Custom timeout message",
            "trace": None
        }
        self.assertEqual(details, expected)

        # Test with trace
        details = create_error_details("TIMEOUT", trace="Stack trace here")
        expected = {
            "code": "TIMEOUT",
            "message": "Operation timed out",
            "trace": "Stack trace here"
        }
        self.assertEqual(details, expected)

        # Test with non-existing error code
        details = create_error_details("NON_EXISTENT_ERROR", "Custom message")
        expected = {
            "code": "NON_EXISTENT_ERROR",
            "message": "Custom message",
            "trace": None
        }
        self.assertEqual(details, expected)

    def test_error_categories(self):
        """Test that error codes are properly categorized."""
        categories = {}
        for code, info in ERROR_CODE_REGISTRY.items():
            if info.category not in categories:
                categories[info.category] = []
            categories[info.category].append(code)

        # Verify expected categories exist
        expected_categories = [
            "system", "auth", "validation", "resource",
            "processing", "rate_limit", "network", "mcp"
        ]
        for category in expected_categories:
            self.assertIn(category, categories, f"Missing category: {category}")

        # Verify specific categorizations
        self.assertIn("INTERNAL_ERROR", categories["system"])
        self.assertIn("UNAUTHORIZED", categories["auth"])
        self.assertIn("INVALID_REQUEST", categories["validation"])
        self.assertIn("AGENT_NOT_FOUND", categories["resource"])
        self.assertIn("PROCESSING_ERROR", categories["processing"])
        self.assertIn("RATE_LIMITED", categories["rate_limit"])
        self.assertIn("NETWORK_ERROR", categories["network"])
        self.assertIn("MCP_CONNECTION_ERROR", categories["mcp"])

    def test_http_status_mappings(self):
        """Test that HTTP status codes are appropriate."""
        # Test specific mappings
        self.assertEqual(get_http_status("UNAUTHORIZED"), 401)
        self.assertEqual(get_http_status("FORBIDDEN"), 403)
        self.assertEqual(get_http_status("RESOURCE_NOT_FOUND"), 404)
        self.assertEqual(get_http_status("TIMEOUT"), 408)
        self.assertEqual(get_http_status("RATE_LIMITED"), 429)
        self.assertEqual(get_http_status("INTERNAL_ERROR"), 500)
        self.assertEqual(get_http_status("BAD_GATEWAY"), 502)
        self.assertEqual(get_http_status("SYSTEM_OVERLOAD"), 503)


if __name__ == "__main__":
    unittest.main()
