"""
Unit tests for the response conversion utilities.
"""

import unittest
from unittest.mock import patch, MagicMock
from src.muxi.runtime.utils.response_converter import (
    convert_onellm_to_muxi_content,
    extract_user_content,
    create_unified_response,
    create_error_response
)


class TestResponseConverter(unittest.TestCase):
    """Test cases for the response converter."""

    def test_convert_onellm_to_muxi_content_text(self):
        """Test converting OneLLM text content to MUXI format."""
        onellm_content = [
            {"type": "text", "text": "Hello, world!"}
        ]

        result = convert_onellm_to_muxi_content(onellm_content)

        expected = [
            {
                "type": "text",
                "text": "Hello, world!",
                "file": None
            }
        ]

        self.assertEqual(result, expected)

    def test_convert_onellm_to_muxi_content_image(self):
        """Test converting OneLLM image_url content to MUXI format."""
        onellm_content = [
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/image.jpg"}
            }
        ]

        result = convert_onellm_to_muxi_content(onellm_content)

        expected = [
            {
                "type": "file",
                "text": None,
                "file": {
                    "type": "image",
                    "url": "https://example.com/image.jpg"
                }
            }
        ]

        self.assertEqual(result, expected)

    def test_convert_onellm_to_muxi_content_mixed(self):
        """Test converting mixed OneLLM content to MUXI format."""
        onellm_content = [
            {"type": "text", "text": "Here's an image:"},
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/image.jpg"}
            },
            {"type": "text", "text": "What do you think?"}
        ]

        result = convert_onellm_to_muxi_content(onellm_content)

        expected = [
            {
                "type": "text",
                "text": "Here's an image:",
                "file": None
            },
            {
                "type": "file",
                "text": None,
                "file": {
                    "type": "image",
                    "url": "https://example.com/image.jpg"
                }
            },
            {
                "type": "text",
                "text": "What do you think?",
                "file": None
            }
        ]

        self.assertEqual(result, expected)

    def test_extract_user_content_string(self):
        """Test extracting user content from string message."""
        content = "Hello, how are you?"

        result = extract_user_content(content)

        expected = [
            {
                "type": "text",
                "text": "Hello, how are you?",
                "file": None
            }
        ]

        self.assertEqual(result, expected)

    def test_extract_user_content_text_items(self):
        """Test extracting user content from text content items."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"}
        ]

        result = extract_user_content(content)

        expected = [
            {
                "type": "text",
                "text": "Hello",
                "file": None
            },
            {
                "type": "text",
                "text": "World",
                "file": None
            }
        ]

        self.assertEqual(result, expected)

    def test_extract_user_content_filter_tool_calls(self):
        """Test that tool calls are filtered out from user content."""
        content = [
            {"type": "text", "text": "I'll help you with that."},
            {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "name": "get_weather",
                        "parameters": {"location": "New York"}
                    }
                ]
            },
            {"type": "text", "text": "Here's the result."}
        ]

        result = extract_user_content(content)

        expected = [
            {
                "type": "text",
                "text": "I'll help you with that.",
                "file": None
            },
            {
                "type": "text",
                "text": "Here's the result.",
                "file": None
            }
        ]

        self.assertEqual(result, expected)

    def test_extract_user_content_empty_text(self):
        """Test that empty text content is filtered out."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": ""},
            {"type": "text", "text": "World"}
        ]

        result = extract_user_content(content)

        expected = [
            {
                "type": "text",
                "text": "Hello",
                "file": None
            },
            {
                "type": "text",
                "text": "World",
                "file": None
            }
        ]

        self.assertEqual(result, expected)

    def test_extract_user_content_file_items(self):
        """Test extracting file content items."""
        content = [
            {
                "type": "file",
                "file": {
                    "type": "image",
                    "url": "https://example.com/image.jpg"
                }
            }
        ]

        result = extract_user_content(content)

        expected = [
            {
                "type": "file",
                "text": None,
                "file": {
                    "type": "image",
                    "url": "https://example.com/image.jpg"
                }
            }
        ]

        self.assertEqual(result, expected)

    @patch('time.time')
    def test_create_unified_response_basic(self, mock_time):
        """Test creating a basic unified response."""
        mock_time.return_value = 1699123456.789

        content = [
            {
                "type": "text",
                "text": "Hello, world!",
                "file": None
            }
        ]

        result = create_unified_response(
            request_id="req_abc123",
            status="completed",
            content=content,
            formation_id="customer-support",
            user_id="user_123"
        )

        expected = {
            "id": "req_abc123",
            "object": "response",
            "status": "completed",
            "timestamp": 1699123456789,
            "formation_id": "customer-support",
            "user_id": "user_123",
            "processing_time": None,
            "processing_mode": "sync",
            "webhook_url": None,
            "error": None,
            "response": content
        }

        self.assertEqual(result, expected)

    @patch('time.time')
    def test_create_unified_response_async(self, mock_time):
        """Test creating an async unified response."""
        mock_time.return_value = 1699123456.789

        content = []

        result = create_unified_response(
            request_id="req_def456",
            status="processing",
            content=content,
            formation_id="data-analysis",
            processing_mode="async",
            webhook_url="https://example.com/webhook",
            user_id="user_456"
        )

        expected = {
            "id": "req_def456",
            "object": "response",
            "status": "processing",
            "timestamp": 1699123456789,
            "formation_id": "data-analysis",
            "user_id": "user_456",
            "processing_time": None,
            "processing_mode": "async",
            "webhook_url": "https://example.com/webhook",
            "error": None,
            "response": content
        }

        self.assertEqual(result, expected)

    @patch('time.time')
    def test_create_unified_response_with_error(self, mock_time):
        """Test creating a unified response with error details."""
        mock_time.return_value = 1699123456.789

        error_details = {
            "code": "TIMEOUT",
            "message": "Operation timed out",
            "trace": None
        }

        result = create_unified_response(
            request_id="req_error123",
            status="failed",
            content=[],
            formation_id="test-formation",
            error=error_details,
            processing_time=5.5
        )

        expected = {
            "id": "req_error123",
            "object": "response",
            "status": "failed",
            "timestamp": 1699123456789,
            "formation_id": "test-formation",
            "user_id": None,
            "processing_time": 5.5,
            "processing_mode": "sync",
            "webhook_url": None,
            "error": error_details,
            "response": []
        }

        self.assertEqual(result, expected)

    @patch('src.muxi.runtime.utils.response_converter.classify_error_code')
    @patch('src.muxi.runtime.utils.response_converter.get_error_info')
    @patch('traceback.format_exc')
    def test_create_error_response(self, mock_traceback, mock_get_error_info, mock_classify):
        """Test creating error response from exception."""
        # Setup mocks
        mock_classify.return_value = "TIMEOUT"
        mock_error_info = MagicMock()
        mock_error_info.message = "Operation timed out"
        mock_get_error_info.return_value = mock_error_info
        mock_traceback.return_value = "Stack trace here"

        exception = TimeoutError("Request timed out")

        result = create_error_response(exception, include_trace=True)

        expected = {
            "code": "TIMEOUT",
            "message": "Operation timed out",
            "trace": "Stack trace here"
        }

        self.assertEqual(result, expected)
        mock_classify.assert_called_once_with(exception)
        mock_get_error_info.assert_called_once_with("TIMEOUT")

    @patch('src.muxi.runtime.utils.response_converter.classify_error_code')
    @patch('src.muxi.runtime.utils.response_converter.get_error_info')
    def test_create_error_response_no_trace(self, mock_get_error_info, mock_classify):
        """Test creating error response without trace."""
        # Setup mocks
        mock_classify.return_value = "INVALID_PARAMS"
        mock_error_info = MagicMock()
        mock_error_info.message = "Invalid parameters provided"
        mock_get_error_info.return_value = mock_error_info

        exception = ValueError("Invalid value")

        result = create_error_response(exception, include_trace=False)

        expected = {
            "code": "INVALID_PARAMS",
            "message": "Invalid parameters provided",
            "trace": None
        }

        self.assertEqual(result, expected)

    @patch('src.muxi.runtime.utils.response_converter.classify_error_code')
    @patch('src.muxi.runtime.utils.response_converter.get_error_info')
    def test_create_error_response_unknown_error(self, mock_get_error_info, mock_classify):
        """Test creating error response for unknown error code."""
        # Setup mocks
        mock_classify.return_value = "UNKNOWN_ERROR"
        mock_get_error_info.return_value = None

        exception = Exception("Unknown error")

        result = create_error_response(exception)

        expected = {
            "code": "UNKNOWN_ERROR",
            "message": "Unknown error",
            "trace": None
        }

        self.assertEqual(result, expected)

    def test_convert_onellm_to_muxi_content_empty(self):
        """Test converting empty OneLLM content."""
        result = convert_onellm_to_muxi_content([])
        self.assertEqual(result, [])

    def test_extract_user_content_empty_list(self):
        """Test extracting from empty content list."""
        result = extract_user_content([])
        self.assertEqual(result, [])

    def test_extract_user_content_empty_string(self):
        """Test extracting from empty string."""
        result = extract_user_content("")
        expected = [
            {
                "type": "text",
                "text": "",
                "file": None
            }
        ]
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
