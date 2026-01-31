#!/usr/bin/env python3
"""
Test 11A1: Response Formats

Tests that the system can return responses in different formats (JSON, Markdown, HTML, Text)
when configured appropriately.
"""

import asyncio
import sys

# Use absolute imports when running as script
try:
    from base_formatting_test import BaseFormattingTest
except ImportError:
    # When running as script, adjust path
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from base_formatting_test import BaseFormattingTest


def main():
    """Test all response formats."""
    test = BaseFormattingTest("11a1_response_formats", "Test different response formats")

    async def run_format_test():
        # Setup formation (uses RUNTIME pattern with single base formation)
        await test.setup_formation()

        # Test all formats with a single message
        base_message = "List three benefits of cloud computing"
        format_results = await test.test_all_formats(
            base_message=base_message, user_id="test_user", session_id_prefix="format_test_11a1"
        )

        # Check individual format results
        test.formatter.print_section("Format Test Results")

        all_passed = True
        for fmt, success in format_results.items():
            status = "PASSED" if success else "FAILED"
            test.formatter.print_info(f"  {fmt.upper()} format: {status}")
            if not success:
                all_passed = False

        # Additional specific format tests with different content types
        test.formatter.print_section("Specific Format Tests")

        # Test JSON with structured data request
        json_result = await test.test_response_format(
            message="Create a JSON object with user information including name, email, and preferences",
            expected_format="json",
            user_id="test_user",
            session_id="json_specific_11a1",
        )

        # Test Markdown with documentation request
        markdown_result = await test.test_response_format(
            message="Create a simple README for a Python project with installation and usage instructions",
            expected_format="markdown",
            user_id="test_user",
            session_id="markdown_specific_11a1",
        )

        # Test HTML with webpage content
        html_result = await test.test_response_format(
            message="Create a simple HTML page explaining the benefits of renewable energy",
            expected_format="html",
            user_id="test_user",
            session_id="html_specific_11a1",
        )

        # Test plain text with explanation
        text_result = await test.test_response_format(
            message="Explain what machine learning is in simple terms without any formatting",
            expected_format="text",
            user_id="test_user",
            session_id="text_specific_11a1",
        )

        specific_results = [
            json_result["success"],
            markdown_result["success"],
            html_result["success"],
            text_result["success"],
        ]
        specific_passed = all(specific_results)

        # Overall success
        overall_success = all_passed and specific_passed

        # Record result
        test.results.append(overall_success)

        if overall_success:
            test.formatter.print_success("All response format tests passed")
        else:
            test.formatter.print_failure("Some response format tests failed")

        # Print detailed results for each format
        if test.format_results:
            test.formatter.print_section("Detailed Format Analysis")
            for result in test.format_results[-4:]:  # Show last 4 (specific tests)
                fmt = result["format"]
                validation = result["validation"]

                test.formatter.print_info(f"{fmt.upper()} Format Validation:")
                if fmt == "json":
                    test.formatter.print_debug(
                        f"  Valid JSON: {validation.get('is_valid_json', False)}"
                    )
                    test.formatter.print_debug(
                        f"  Has required fields: {validation.get('has_required_fields', False)}"
                    )
                elif fmt == "markdown":
                    test.formatter.print_debug(
                        f"  Structure score: {validation.get('structure_score', 0)}/5"
                    )
                    test.formatter.print_debug(
                        f"  Has headers: {validation.get('has_headers', False)}"
                    )
                    test.formatter.print_debug(
                        f"  Has code blocks: {validation.get('has_code_blocks', False)}"
                    )
                elif fmt == "html":
                    test.formatter.print_debug(
                        f"  Has HTML tags: {validation.get('has_html_tags', False)}"
                    )
                    test.formatter.print_debug(
                        f"  Has semantic tags: {validation.get('has_semantic_tags', False)}"
                    )
                    test.formatter.print_debug(f"  Tag count: {validation.get('tag_count', 0)}")
                elif fmt == "text":
                    test.formatter.print_debug(
                        f"  Is plain text: {validation.get('is_plain_text', False)}"
                    )
                    test.formatter.print_debug(f"  Word count: {validation.get('word_count', 0)}")

        # Print formatting-specific summary
        test.print_formatting_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if overall_success else 1

    # Run the async test function directly
    try:
        exit_code = asyncio.run(run_format_test())
        return exit_code
    except Exception as e:
        test.formatter.print_error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    import os; os._exit(exit_code)
