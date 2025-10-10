"""
Unit tests for trigger template rendering.

Tests the render_trigger_template function with various data structures
and edge cases.
"""

import pytest
from src.muxi.formation.server.utils import render_trigger_template


class TestTriggerRendering:
    """Test suite for trigger template rendering."""

    def test_simple_substitution(self):
        """Test basic single-level data substitution."""
        template = "Hello ${{ data.name }}!"
        data = {"name": "World"}
        result = render_trigger_template(template, data)
        assert result == "Hello World!"

    def test_nested_substitution(self):
        """Test nested data access with dot notation."""
        template = "Issue #${{ data.issue.number }}: ${{ data.issue.title }}"
        data = {
            "issue": {
                "number": 123,
                "title": "Bug in login"
            }
        }
        result = render_trigger_template(template, data)
        assert result == "Issue #123: Bug in login"

    def test_multi_level_nesting(self):
        """Test deeply nested data access."""
        template = "User: ${{ data.user.profile.name }} (${{ data.user.profile.email }})"
        data = {
            "user": {
                "profile": {
                    "name": "John Doe",
                    "email": "john@example.com"
                }
            }
        }
        result = render_trigger_template(template, data)
        assert result == "User: John Doe (john@example.com)"

    def test_multiple_substitutions(self):
        """Test template with multiple placeholder substitutions."""
        template = """
Issue: ${{ data.title }}
Author: ${{ data.author }}
Status: ${{ data.status }}
""".strip()
        data = {
            "title": "Fix bug",
            "author": "Alice",
            "status": "open"
        }
        result = render_trigger_template(template, data)
        assert "Issue: Fix bug" in result
        assert "Author: Alice" in result
        assert "Status: open" in result

    def test_number_conversion(self):
        """Test that numbers are converted to strings."""
        template = "Count: ${{ data.count }}, Price: ${{ data.price }}"
        data = {
            "count": 42,
            "price": 19.99
        }
        result = render_trigger_template(template, data)
        assert result == "Count: 42, Price: 19.99"

    def test_boolean_conversion(self):
        """Test that booleans are converted to strings."""
        template = "Active: ${{ data.active }}"
        data = {"active": True}
        result = render_trigger_template(template, data)
        assert result == "Active: True"

    def test_whitespace_handling(self):
        """Test that whitespace in placeholders is handled correctly."""
        template = "${{data.key1}} ${{ data.key2 }} ${{  data.key3  }}"
        data = {
            "key1": "A",
            "key2": "B",
            "key3": "C"
        }
        result = render_trigger_template(template, data)
        assert result == "A B C"

    def test_missing_key_error(self):
        """Test that missing keys raise ValueError with helpful message."""
        template = "Hello ${{ data.missing }}!"
        data = {"name": "World"}

        with pytest.raises(ValueError) as exc_info:
            render_trigger_template(template, data)

        assert "data.missing" in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()

    def test_missing_nested_key_error(self):
        """Test that missing nested keys raise ValueError."""
        template = "Value: ${{ data.user.missing }}"
        data = {"user": {"name": "Alice"}}

        with pytest.raises(ValueError) as exc_info:
            render_trigger_template(template, data)

        assert "data.user.missing" in str(exc_info.value)

    def test_non_dict_access_error(self):
        """Test that accessing nested keys on non-dict values raises error."""
        template = "Value: ${{ data.name.first }}"
        data = {"name": "Alice"}  # name is string, not dict

        with pytest.raises(ValueError) as exc_info:
            render_trigger_template(template, data)

        assert "non-dict" in str(exc_info.value).lower()

    def test_empty_template(self):
        """Test that empty template returns empty string."""
        template = ""
        data = {"key": "value"}
        result = render_trigger_template(template, data)
        assert result == ""

    def test_template_without_placeholders(self):
        """Test that template without placeholders returns unchanged."""
        template = "This is a static message."
        data = {"key": "value"}
        result = render_trigger_template(template, data)
        assert result == template

    def test_empty_data(self):
        """Test that empty data dict works when no placeholders."""
        template = "Static message"
        data = {}
        result = render_trigger_template(template, data)
        assert result == template

    def test_github_issue_template(self):
        """Test realistic GitHub issue template."""
        template = """New GitHub issue from ${{ data.repository }}:

**Issue #${{ data.issue.number }}**: ${{ data.issue.title }}

**Author**: ${{ data.issue.author }}
**State**: ${{ data.issue.state }}"""

        data = {
            "repository": "muxi/runtime",
            "issue": {
                "number": 123,
                "title": "Bug in trigger system",
                "author": "user123",
                "state": "open"
            }
        }

        result = render_trigger_template(template, data)
        assert "New GitHub issue from muxi/runtime" in result
        assert "Issue #123" in result
        assert "Bug in trigger system" in result
        assert "user123" in result  # Author value present
        assert "open" in result  # State value present

    def test_linear_ticket_template(self):
        """Test realistic Linear ticket template."""
        template = """Linear ticket: ${{ data.ticket.identifier }}
Title: ${{ data.ticket.title }}
Priority: ${{ data.ticket.priority }}"""

        data = {
            "ticket": {
                "identifier": "ENG-456",
                "title": "Implement triggers",
                "priority": "high"
            }
        }

        result = render_trigger_template(template, data)
        assert "ENG-456" in result
        assert "Implement triggers" in result
        assert "high" in result

    def test_special_characters_in_values(self):
        """Test that special characters in values are preserved."""
        template = "Message: ${{ data.message }}"
        data = {"message": "Hello! @user #123 $test & <html>"}
        result = render_trigger_template(template, data)
        assert result == "Message: Hello! @user #123 $test & <html>"

    def test_multiline_values(self):
        """Test that multiline values are handled correctly."""
        template = "Description:\n${{ data.description }}"
        data = {
            "description": "Line 1\nLine 2\nLine 3"
        }
        result = render_trigger_template(template, data)
        assert "Line 1\nLine 2\nLine 3" in result

    def test_none_value_handling(self):
        """Test that None values are converted to string."""
        template = "Value: ${{ data.value }}"
        data = {"value": None}
        result = render_trigger_template(template, data)
        assert result == "Value: None"

    def test_list_value_conversion(self):
        """Test that list values are converted to strings."""
        template = "Tags: ${{ data.tags }}"
        data = {"tags": ["bug", "urgent", "backend"]}
        result = render_trigger_template(template, data)
        assert "['bug', 'urgent', 'backend']" in result

    def test_dict_value_conversion(self):
        """Test that dict values are converted to strings."""
        template = "Metadata: ${{ data.metadata }}"
        data = {"metadata": {"key": "value", "count": 42}}
        result = render_trigger_template(template, data)
        # Dict string representation should be present
        assert "key" in result
        assert "value" in result

    def test_underscore_in_keys(self):
        """Test that underscores in key names work correctly."""
        template = "User: ${{ data.user_name }} ID: ${{ data.user_id }}"
        data = {
            "user_name": "alice",
            "user_id": 123
        }
        result = render_trigger_template(template, data)
        assert result == "User: alice ID: 123"

    def test_numbers_in_keys(self):
        """Test that numbers in key names work correctly."""
        template = "Value: ${{ data.key123 }}"
        data = {"key123": "test"}
        result = render_trigger_template(template, data)
        assert result == "Value: test"

    def test_case_sensitive_keys(self):
        """Test that key names are case-sensitive."""
        template = "${{ data.Name }} ${{ data.name }}"
        data = {
            "Name": "Alice",
            "name": "Bob"
        }
        result = render_trigger_template(template, data)
        assert result == "Alice Bob"

    def test_list_indexing(self):
        """Test basic list indexing with numeric keys."""
        template = "First: ${{ data.items.0 }}, Second: ${{ data.items.1 }}"
        data = {"items": ["apple", "banana", "cherry"]}
        result = render_trigger_template(template, data)
        assert result == "First: apple, Second: banana"

    def test_list_nested_dict_access(self):
        """Test accessing dict properties inside list elements."""
        template = "Label: ${{ data.labels.0.name }}, Color: ${{ data.labels.0.color }}"
        data = {
            "labels": [
                {"name": "bug", "color": "red"},
                {"name": "feature", "color": "blue"}
            ]
        }
        result = render_trigger_template(template, data)
        assert result == "Label: bug, Color: red"

    def test_list_multiple_indices(self):
        """Test accessing multiple list indices."""
        template = "${{ data.tags.0 }}, ${{ data.tags.1 }}, ${{ data.tags.2 }}"
        data = {"tags": ["urgent", "backend", "bug"]}
        result = render_trigger_template(template, data)
        assert result == "urgent, backend, bug"

    def test_nested_list_access(self):
        """Test nested structure with lists at multiple levels."""
        template = "Author: ${{ data.issue.labels.0.name }}"
        data = {
            "issue": {
                "labels": [
                    {"name": "enhancement"},
                    {"name": "priority-high"}
                ]
            }
        }
        result = render_trigger_template(template, data)
        assert result == "Author: enhancement"

    def test_list_index_out_of_range(self):
        """Test that out of range list index raises ValueError."""
        template = "Item: ${{ data.items.5.name }}"
        data = {"items": [{"name": "a"}]}

        with pytest.raises(ValueError) as exc_info:
            render_trigger_template(template, data)

        assert "index 5 out of range" in str(exc_info.value).lower()
        assert "length: 1" in str(exc_info.value).lower()

    def test_list_non_numeric_key_error(self):
        """Test that non-numeric keys on lists raise ValueError."""
        template = "Item: ${{ data.items.foo }}"
        data = {"items": [1, 2, 3]}

        with pytest.raises(ValueError) as exc_info:
            render_trigger_template(template, data)

        assert "non-numeric key" in str(exc_info.value).lower()
        assert "foo" in str(exc_info.value)

    def test_github_labels_template(self):
        """Test realistic GitHub issue with labels array."""
        template = """Issue: ${{ data.issue.title }}
First Label: ${{ data.issue.labels.0.name }}
Second Label: ${{ data.issue.labels.1.name }}"""

        data = {
            "issue": {
                "title": "Bug fix",
                "labels": [
                    {"name": "bug", "color": "red"},
                    {"name": "urgent", "color": "orange"}
                ]
            }
        }

        result = render_trigger_template(template, data)
        assert "Issue: Bug fix" in result
        assert "First Label: bug" in result
        assert "Second Label: urgent" in result
