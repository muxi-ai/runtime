#!/usr/bin/env python3
"""
Simple Unified Response Format Tests

Basic tests for the unified response format implementation.
"""

import json
import pytest
import sys
from pathlib import Path

# Add the runtime directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.utils.response_converter import (
    create_unified_response,
    extract_user_content,
    create_error_response
)


class TestResponseConverter:
    """Test response conversion utilities"""

    def test_create_unified_response_success(self):
        """Test creating successful unified response"""
        content = [{"type": "text", "text": "Test response", "file": None}]

        response = create_unified_response(
            request_id="test-123",
            status="completed",
            content=content,
            formation_id="test-formation",
            user_id="123",
            processing_time=2.0,
            processing_mode="sync"
        )

        assert response["status"] == "completed"
        assert response["formation_id"] == "test-formation"
        assert response["user_id"] == "123"
        assert len(response["response"]) == 1
        assert response["response"][0]["text"] == "Test response"

    def test_create_error_response(self):
        """Test creating error response"""
        error = ValueError("Test error")
        error_details = create_error_response(error)

        assert error_details["message"] is not None
        assert error_details["code"] is not None

    def test_extract_user_content_simple_text(self):
        """Test extracting user content from simple text"""
        content = "User message content"
        extracted = extract_user_content(content)

        assert len(extracted) == 1
        assert extracted[0]["type"] == "text"
        assert extracted[0]["text"] == "User message content"

    def test_extract_user_content_with_list(self):
        """Test extracting user content from list"""
        content = [
            {"type": "text", "text": "User message"},
            {"type": "text", "text": "More content"}
        ]
        extracted = extract_user_content(content)

        assert len(extracted) == 2
        assert extracted[0]["text"] == "User message"
        assert extracted[1]["text"] == "More content"

    def test_response_serialization(self):
        """Test response serialization to JSON"""
        content = [{"type": "text", "text": "Test content", "file": None}]

        response = create_unified_response(
            request_id="test-456",
            status="completed",
            content=content,
            formation_id="test-formation",
            user_id="456",
            processing_time=1.0,
            processing_mode="sync"
        )

        # Verify JSON serialization
        json_str = json.dumps(response)
        assert isinstance(json_str, str)
        assert "response" in json_str

        # Verify deserialization
        parsed = json.loads(json_str)
        assert parsed["object"] == "response"
        assert parsed["status"] == "completed"
        assert parsed["formation_id"] == "test-formation"
        assert parsed["user_id"] == "456"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
