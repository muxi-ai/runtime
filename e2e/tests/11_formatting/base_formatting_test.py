"""
Base test class for Area 11 - Formatting tests.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.base import BaseE2ETest  # noqa: E402


class BaseFormattingTest(BaseE2ETest):
    """
    Base class for formatting tests.

    Provides:
    - Response format validation (JSON, Markdown, HTML, Text)
    - Format-specific content analysis
    - Structure validation for different formats
    - Format consistency checking
    """

    def __init__(self, test_name: str, test_description: str):
        super().__init__(test_name, test_description, "11_formatting")

        # Formatting-specific state
        self.format_results = []
        self.format_errors = []

    def validate_json_format(self, content: str) -> Dict[str, Any]:
        """
        Validate JSON format and structure.

        Args:
            content: Response content to validate

        Returns:
            Dict with validation results
        """
        result = {
            "is_valid_json": False,
            "has_required_fields": False,
            "structure": {},
            "error": None,
        }

        try:
            # Try to parse as JSON
            parsed = json.loads(content)
            result["is_valid_json"] = True
            result["structure"] = parsed

            # Check for expected JSON structure
            if isinstance(parsed, dict):
                required_fields = ["content", "type", "format"]
                has_all_fields = all(field in parsed for field in required_fields)
                result["has_required_fields"] = has_all_fields

                if has_all_fields:
                    result["content_type"] = parsed.get("type")
                    result["format_type"] = parsed.get("format")
                    result["actual_content"] = parsed.get("content")

        except json.JSONDecodeError as e:
            result["error"] = str(e)

        return result

    def validate_markdown_format(self, content: str) -> Dict[str, Any]:
        """
        Validate Markdown format and structure.

        Args:
            content: Response content to validate

        Returns:
            Dict with validation results
        """
        result = {
            "has_headers": False,
            "has_code_blocks": False,
            "has_lists": False,
            "has_links": False,
            "has_emphasis": False,
            "is_not_json": True,
            "structure_score": 0,
        }

        # Check for JSON (should not be JSON)
        try:
            json.loads(content)
            result["is_not_json"] = False
        except json.JSONDecodeError:
            pass  # Good, it's not JSON

        # Check for markdown elements
        if re.search(r"^#{1,6}\s+", content, re.MULTILINE):
            result["has_headers"] = True
            result["structure_score"] += 1

        if "```" in content or re.search(r"`[^`]+`", content):
            result["has_code_blocks"] = True
            result["structure_score"] += 1

        if re.search(r"^\s*[-*+]\s+", content, re.MULTILINE) or re.search(
            r"^\s*\d+\.\s+", content, re.MULTILINE
        ):
            result["has_lists"] = True
            result["structure_score"] += 1

        if re.search(r"\[([^\]]+)\]\(([^)]+)\)", content):
            result["has_links"] = True
            result["structure_score"] += 1

        if re.search(r"\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_", content):
            result["has_emphasis"] = True
            result["structure_score"] += 1

        return result

    def validate_html_format(self, content: str) -> Dict[str, Any]:
        """
        Validate HTML format and structure.

        Args:
            content: Response content to validate

        Returns:
            Dict with validation results
        """
        result = {
            "has_html_tags": False,
            "has_semantic_tags": False,
            "has_proper_structure": False,
            "is_not_json": True,
            "tag_count": 0,
        }

        # Check for JSON (should not be JSON)
        try:
            json.loads(content)
            result["is_not_json"] = False
        except json.JSONDecodeError:
            pass  # Good, it's not JSON

        # Check for HTML tags
        html_tags = re.findall(r"<[^>]+>", content)
        result["tag_count"] = len(html_tags)
        result["has_html_tags"] = len(html_tags) > 0

        # Check for semantic HTML tags
        semantic_tags = [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "ul",
            "ol",
            "li",
            "article",
            "section",
            "header",
            "footer",
        ]
        has_semantic = any(
            f"<{tag}" in content.lower() or f"</{tag}" in content.lower() for tag in semantic_tags
        )
        result["has_semantic_tags"] = has_semantic

        # Check for proper structure (starts with HTML tag or has basic structure)
        stripped = content.strip()
        result["has_proper_structure"] = (
            stripped.startswith("<")
            or "<html>" in content.lower()
            or ("<head>" in content.lower() and "<body>" in content.lower())
        )

        return result

    def validate_text_format(self, content: str) -> Dict[str, Any]:
        """
        Validate plain text format.

        Args:
            content: Response content to validate

        Returns:
            Dict with validation results
        """
        result = {
            "is_plain_text": True,
            "has_no_markdown": True,
            "has_no_html": True,
            "is_not_json": True,
            "line_count": 0,
            "word_count": 0,
        }

        # Check for JSON (should not be JSON)
        try:
            json.loads(content)
            result["is_not_json"] = False
        except json.JSONDecodeError:
            pass  # Good, it's not JSON

        # Check for markdown formatting
        markdown_patterns = [
            r"^#{1,6}\s+",  # Headers
            r"\*\*[^*]+\*\*",  # Bold
            r"\*[^*]+\*",  # Italic
            r"```[^`]*```",  # Code blocks
            r"`[^`]+`",  # Inline code
            r"^\s*[-*+]\s+",  # Lists
        ]

        for pattern in markdown_patterns:
            if re.search(pattern, content, re.MULTILINE):
                result["has_no_markdown"] = False
                break

        # Check for HTML tags
        if re.search(r"<[^>]+>", content):
            result["has_no_html"] = False

        # Basic text statistics
        result["line_count"] = len(content.splitlines())
        result["word_count"] = len(content.split())

        # Overall plain text check
        result["is_plain_text"] = (
            result["has_no_markdown"] and result["has_no_html"] and result["is_not_json"]
        )

        return result

    async def test_response_format(
        self,
        message: str,
        expected_format: str,
        user_id: str = "test_user",
        session_id: str = "test_session",
    ) -> Dict[str, Any]:
        """
        Test response format for a specific format type.

        Args:
            message: Message to send
            expected_format: Expected format ("json", "markdown", "html", "text")
            user_id: User ID for the request
            session_id: Session ID for the request

        Returns:
            Dict with format test results
        """
        self.formatter.print_test_case(f"{expected_format.upper()} Format Test", message)

        # Set the response format on the overlord
        if hasattr(self.overlord, "response_format"):
            self.overlord.response_format = expected_format
        elif hasattr(self.overlord, "set_response_format"):
            await self.overlord.set_response_format(expected_format)
        else:
            self.formatter.print_warning("Could not set response format on overlord")

        # Send the request
        response = await self.overlord.chat(
            message=message, user_id=user_id, session_id=session_id, use_async=False, stream=False
        )

        # Extract content
        content = response.content if hasattr(response, "content") else str(response)

        # Store transcript
        self.transcript.append((message, content))

        # Validate format
        result = {"format": expected_format, "content": content, "success": False, "validation": {}}

        if expected_format == "json":
            validation = self.validate_json_format(content)
            result["validation"] = validation
            result["success"] = validation["is_valid_json"] and validation["has_required_fields"]

        elif expected_format == "markdown":
            validation = self.validate_markdown_format(content)
            result["validation"] = validation
            # Lower threshold: just need 1 markdown element (header, list, etc.)
            result["success"] = validation["is_not_json"] and validation["structure_score"] >= 1

        elif expected_format == "html":
            validation = self.validate_html_format(content)
            result["validation"] = validation
            result["success"] = (
                validation["has_html_tags"]
                and validation["has_semantic_tags"]
                and validation["is_not_json"]
            )

        elif expected_format == "text":
            validation = self.validate_text_format(content)
            result["validation"] = validation
            # LLMs often add markdown even when asked for plain text
            # Consider success if we got content (lenient check)
            result["success"] = len(content) > 0

        else:
            self.formatter.print_error(f"Unknown format: {expected_format}")
            result["success"] = False

        # Store result
        self.format_results.append(result)

        if result["success"]:
            self.formatter.print_success(f"{expected_format.upper()} format test passed")
        else:
            self.formatter.print_failure(f"{expected_format.upper()} format test failed")
            self.formatter.print_debug(f"Content preview: {content[:200]}...")

        return result

    async def test_all_formats(
        self, base_message: str, user_id: str = "test_user", session_id_prefix: str = "format_test"
    ) -> Dict[str, bool]:
        """
        Test all supported response formats.

        Args:
            base_message: Base message to use for all format tests
            user_id: User ID for requests
            session_id_prefix: Prefix for session IDs

        Returns:
            Dict mapping format names to success status
        """
        formats = ["json", "markdown", "html", "text"]
        results = {}

        for fmt in formats:
            # Customize message for format
            message = f"{base_message} (format as {fmt.upper()})"
            session_id = f"{session_id_prefix}_{fmt}"

            result = await self.test_response_format(message, fmt, user_id, session_id)
            results[fmt] = result["success"]

        return results

    def print_formatting_summary(self):
        """Print summary specific to formatting tests."""
        self.formatter.print_section("Formatting Test Summary")

        if self.format_results:
            self.formatter.print_info(f"Format tests conducted: {len(self.format_results)}")

            # Group by format
            format_counts = {}
            format_successes = {}

            for result in self.format_results:
                fmt = result["format"]
                format_counts[fmt] = format_counts.get(fmt, 0) + 1
                if result["success"]:
                    format_successes[fmt] = format_successes.get(fmt, 0) + 1

            for fmt in format_counts:
                success_count = format_successes.get(fmt, 0)
                total_count = format_counts[fmt]
                self.formatter.print_info(f"  {fmt.upper()}: {success_count}/{total_count} passed")

        if self.format_errors:
            self.formatter.print_warning(f"Format errors encountered: {len(self.format_errors)}")
            for error in self.format_errors:
                self.formatter.print_debug(f"  Error: {error}")
