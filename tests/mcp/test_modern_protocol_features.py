# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Modern Protocol Features Tests
# Description:  Test suite for MCP 2025-06-18 protocol enhancements
# Role:         Validates modern MCP protocol features and compatibility
# Usage:        Run via pytest to verify protocol feature implementation
# Author:       Muxi Framework Team
#
# This test suite validates the modern protocol features implementation
# according to the MCP 2025-06-18 specification. Tests include:
#
# 1. Display Name Enhancement
#    - Title field prioritization
#    - Fallback to name field
#    - Edge cases and malformed data
#
# 2. Structured Output Processing
#    - Modern structured format handling
#    - Legacy format compatibility
#    - Metadata field support
#
# 3. Elicitation Request Handling
#    - Complete elicitation workflow
#    - Field validation and requirements
#    - Response format standardization
#
# 4. Resource Links Support
#    - Link extraction and processing
#    - Multiple link types
#    - Relationship handling
#
# This test suite implements the testing strategy specified in the
# Streamable HTTP implementation plan Phase 3.1.
# =============================================================================

import sys
import os
from unittest.mock import Mock

# Add the source directory to Python path for importing muxi modules
if os.path.join(os.path.dirname(__file__), '../../src') not in sys.path:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from src.muxi.runtime.services.mcp.transports import ModernProtocolFeatures


class TestModernProtocolFeatures:
    """Tests for MCP 2025-06-18 protocol enhancements."""

    def test_display_name_extraction(self):
        """Test title field prioritization for display names."""

        # Test with both title and name - title should be preferred
        tool_info = {
            "name": "file_reader",
            "title": "File Reader Tool",
            "description": "Reads files from the filesystem"
        }
        display_name = ModernProtocolFeatures.extract_display_name(tool_info)
        assert display_name == "File Reader Tool"

        # Test with only name field - should fall back to name
        tool_info = {
            "name": "file_writer",
            "description": "Writes files to the filesystem"
        }
        display_name = ModernProtocolFeatures.extract_display_name(tool_info)
        assert display_name == "file_writer"

        # Test with neither title nor name - should return default
        tool_info = {
            "description": "A tool without name or title"
        }
        display_name = ModernProtocolFeatures.extract_display_name(tool_info)
        assert display_name == "Unnamed Tool"

        # Test with empty title - should fall back to name
        tool_info = {
            "name": "calculator",
            "title": "",
            "description": "Performs calculations"
        }
        display_name = ModernProtocolFeatures.extract_display_name(tool_info)
        assert display_name == "calculator"

        # Test with None title - should fall back to name
        tool_info = {
            "name": "database_query",
            "title": None,
            "description": "Queries database"
        }
        display_name = ModernProtocolFeatures.extract_display_name(tool_info)
        assert display_name == "database_query"

    def test_structured_output_processing(self):
        """Test structured vs legacy output format handling."""

        # Test modern structured output
        mock_result = Mock()
        mock_result.content = "Structured response content"
        mock_result.isError = False
        mock_result.links = [{"href": "https://example.com", "rel": "related"}]
        mock_result._meta = {"version": "2025-06-18"}

        processed = ModernProtocolFeatures.process_structured_output(mock_result)

        assert processed["type"] == "structured"
        assert processed["content"] == "Structured response content"
        assert processed["isError"] is False
        assert len(processed["links"]) == 1
        assert processed["_meta"]["version"] == "2025-06-18"

        # Test structured output with error
        mock_result.isError = True
        processed = ModernProtocolFeatures.process_structured_output(mock_result)
        assert processed["isError"] is True

        # Test legacy format (simple object/string)
        legacy_result = "Simple string response"
        processed = ModernProtocolFeatures.process_structured_output(legacy_result)

        assert processed["type"] == "legacy"
        assert processed["content"] == "Simple string response"
        assert processed["isError"] is False
        assert processed["links"] == []
        assert processed["_meta"] == {}

        # Test legacy format (dictionary)
        legacy_result = {"result": "legacy response", "status": "ok"}
        processed = ModernProtocolFeatures.process_structured_output(legacy_result)

        assert processed["type"] == "legacy"
        assert processed["content"] == {"result": "legacy response", "status": "ok"}

    def test_metadata_field_support(self):
        """Test _meta field handling across different types."""

        # Test structured output with complex metadata
        mock_result = Mock()
        mock_result.content = "Response with metadata"
        mock_result.isError = False
        mock_result.links = []
        mock_result._meta = {
            "timestamp": "2025-06-18T10:00:00Z",
            "version": "2025-06-18",
            "execution_time_ms": 150,
            "server_version": "1.2.3",
            "capabilities": ["structured_output", "resource_links"]
        }

        processed = ModernProtocolFeatures.process_structured_output(mock_result)

        assert processed["_meta"]["timestamp"] == "2025-06-18T10:00:00Z"
        assert processed["_meta"]["execution_time_ms"] == 150
        assert "structured_output" in processed["_meta"]["capabilities"]

        # Test with missing _meta attribute
        mock_result_no_meta = Mock()
        mock_result_no_meta.content = "Response without metadata"
        mock_result_no_meta.isError = False
        mock_result_no_meta.links = []
        # No _meta attribute

        processed = ModernProtocolFeatures.process_structured_output(mock_result_no_meta)
        assert processed["_meta"] == {}

    def test_elicitation_workflow(self):
        """Test complete elicitation request/response cycle."""

        # Test basic elicitation request
        elicitation_data = {
            "prompt": "Please provide your user ID",
            "fields": ["user_id"],
            "required": ["user_id"]
        }

        result = ModernProtocolFeatures.handle_elicitation_request(elicitation_data)

        assert result["type"] == "elicitation"
        assert result["prompt"] == "Please provide your user ID"
        assert "user_id" in result["fields"]
        assert "user_id" in result["required"]
        assert result["_meta"] == {}

        # Test complex elicitation with multiple fields
        elicitation_data = {
            "prompt": "Please provide additional context for this operation",
            "fields": ["user_context", "preferences", "constraints"],
            "required": ["user_context"],
            "_meta": {
                "elicitation_id": "elicit-789",
                "timeout_seconds": 30,
                "retry_count": 1
            }
        }

        result = ModernProtocolFeatures.handle_elicitation_request(elicitation_data)

        assert result["type"] == "elicitation"
        assert len(result["fields"]) == 3
        assert len(result["required"]) == 1
        assert result["_meta"]["elicitation_id"] == "elicit-789"
        assert result["_meta"]["timeout_seconds"] == 30

        # Test elicitation with missing fields (should use defaults)
        minimal_elicitation = {}
        result = ModernProtocolFeatures.handle_elicitation_request(minimal_elicitation)

        assert result["type"] == "elicitation"
        assert result["prompt"] == "Additional information needed"
        assert result["fields"] == []
        assert result["required"] == []
        assert result["_meta"] == {}

    def test_resource_links_in_results(self):
        """Test resource link extraction and processing."""

        # Test result with multiple resource links
        mock_result = Mock()
        mock_result.content = "Result with multiple resource links"
        mock_result.isError = False
        mock_result.links = [
            {
                "href": "https://api.example.com/docs/endpoint",
                "rel": "documentation",
                "type": "text/html",
                "title": "API Documentation"
            },
            {
                "href": "https://api.example.com/schema",
                "rel": "schema",
                "type": "application/json",
                "title": "Response Schema"
            },
            {
                "href": "https://example.com/related-resource",
                "rel": "related",
                "type": "application/json"
            }
        ]
        mock_result._meta = {}

        processed = ModernProtocolFeatures.process_structured_output(mock_result)

        assert len(processed["links"]) == 3

        # Check documentation link
        doc_link = next(link for link in processed["links"] if link["rel"] == "documentation")
        assert doc_link["href"] == "https://api.example.com/docs/endpoint"
        assert doc_link["title"] == "API Documentation"
        assert doc_link["type"] == "text/html"

        # Check schema link
        schema_link = next(link for link in processed["links"] if link["rel"] == "schema")
        assert schema_link["href"] == "https://api.example.com/schema"
        assert schema_link["title"] == "Response Schema"

        # Check related link (without title)
        related_link = next(link for link in processed["links"] if link["rel"] == "related")
        assert related_link["href"] == "https://example.com/related-resource"
        assert "title" not in related_link or related_link.get("title") is None

    def test_backward_compatibility_fallback(self):
        """Test graceful fallback for servers without new features."""

        # Test tool info without modern fields
        legacy_tool_info = {
            "name": "legacy_tool",
            "description": "A legacy tool without modern features"
        }

        display_name = ModernProtocolFeatures.extract_display_name(legacy_tool_info)
        assert display_name == "legacy_tool"

        # Test legacy response format
        legacy_response = {
            "status": "success",
            "data": "legacy response data"
        }

        processed = ModernProtocolFeatures.process_structured_output(legacy_response)
        assert processed["type"] == "legacy"
        assert processed["isError"] is False
        assert processed["links"] == []
        assert processed["_meta"] == {}

        # Test completely minimal data
        minimal_data = "just a string"
        processed = ModernProtocolFeatures.process_structured_output(minimal_data)
        assert processed["content"] == "just a string"
        assert processed["type"] == "legacy"

    def test_edge_cases_and_malformed_data(self):
        """Test handling of edge cases and malformed data."""

        # Test None input for display name
        display_name = ModernProtocolFeatures.extract_display_name(None)
        assert display_name == "Unnamed Tool"

        # Test empty dictionary for display name
        display_name = ModernProtocolFeatures.extract_display_name({})
        assert display_name == "Unnamed Tool"

        # Test None input for structured output
        processed = ModernProtocolFeatures.process_structured_output(None)
        assert processed["content"] is None
        assert processed["type"] == "legacy"

        # Test empty elicitation data
        result = ModernProtocolFeatures.handle_elicitation_request({})
        assert result["type"] == "elicitation"
        assert result["prompt"] == "Additional information needed"

        # Test None elicitation data
        result = ModernProtocolFeatures.handle_elicitation_request(None)
        assert result["type"] == "elicitation"
        assert result["fields"] == []
        assert result["required"] == []

    def test_protocol_version_compliance(self):
        """Test compliance with MCP 2025-06-18 specification."""

        # Test that all expected fields are present in structured output
        mock_result = Mock()
        mock_result.content = "Test content"
        mock_result.isError = False
        mock_result.links = []
        mock_result._meta = {"test": "metadata"}

        processed = ModernProtocolFeatures.process_structured_output(mock_result)

        # Verify all required fields are present
        required_fields = ["content", "isError", "links", "_meta", "type"]
        for field in required_fields:
            assert field in processed

        # Test elicitation request format compliance
        elicitation_data = {
            "prompt": "Test prompt",
            "fields": ["field1", "field2"],
            "required": ["field1"]
        }

        result = ModernProtocolFeatures.handle_elicitation_request(elicitation_data)

        # Verify all required elicitation fields are present
        required_elicitation_fields = ["type", "prompt", "fields", "required", "_meta"]
        for field in required_elicitation_fields:
            assert field in result

        # Verify type is correctly set
        assert result["type"] == "elicitation"
