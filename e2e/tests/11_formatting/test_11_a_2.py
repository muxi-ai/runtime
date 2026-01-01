#!/usr/bin/env python3
"""
Test 11A2: Format Consistency

Tests that response formats remain consistent across multiple requests
and that format switching works properly.
"""

import asyncio
import sys

# Use absolute imports when running as script
try:
    from .base_formatting_test import BaseFormattingTest
except ImportError:
    # When running as script, adjust path
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from base_formatting_test import BaseFormattingTest


def main():
    """Test format consistency and switching."""
    test = BaseFormattingTest("11a2_format_consistency", "Test format consistency and switching")

    async def run_consistency_test():
        # Setup formation (uses RUNTIME pattern with single base formation)
        await test.setup_formation()

        # Test format consistency - multiple requests with same format
        test.formatter.print_section("Format Consistency Test")

        json_messages = [
            "Create a JSON object representing a book with title, author, and publication year",
            "Generate JSON data for a simple user profile",
            "Return a JSON array of programming languages with their types",
        ]

        json_consistency = True
        for i, message in enumerate(json_messages):
            result = await test.test_response_format(
                message=message,
                expected_format="json",
                user_id="test_user",
                session_id=f"json_consistency_{i}",
            )
            if not result["success"]:
                json_consistency = False
                break

        test.formatter.print_info(f"JSON consistency: {'PASSED' if json_consistency else 'FAILED'}")

        # Test format switching - change formats between requests
        test.formatter.print_section("Format Switching Test")

        format_sequence = [
            ("json", "Create a JSON object with weather data"),
            ("markdown", "Write a markdown guide for beginners"),
            ("html", "Create an HTML snippet for a contact form"),
            ("text", "Explain photosynthesis in plain text"),
            ("json", "Return to JSON format with product data"),
        ]

        switching_success = True
        for fmt, message in format_sequence:
            result = await test.test_response_format(
                message=message,
                expected_format=fmt,
                user_id="test_user",
                session_id=f"switching_{fmt}",
            )
            if not result["success"]:
                switching_success = False
                test.formatter.print_warning(f"Format switching failed at {fmt}")

        test.formatter.print_info(
            f"Format switching: {'PASSED' if switching_success else 'FAILED'}"
        )

        # Test format persistence - ensure format persists across session
        test.formatter.print_section("Format Persistence Test")

        # Set markdown format and send multiple messages in same session
        persistence_messages = [
            "Explain machine learning concepts",
            "Create a tutorial for Python functions",
            "Write about data structures",
        ]

        persistence_success = True
        session_id = "persistence_test"

        for i, message in enumerate(persistence_messages):
            result = await test.test_response_format(
                message=message,
                expected_format="markdown",
                user_id="test_user",
                session_id=session_id,
            )
            if not result["success"]:
                persistence_success = False
                test.formatter.print_warning(f"Format persistence failed at message {i+1}")

        test.formatter.print_info(
            f"Format persistence: {'PASSED' if persistence_success else 'FAILED'}"
        )

        # Test format error handling - invalid format graceful degradation
        test.formatter.print_section("Format Error Handling")

        # Try to set an invalid format (should gracefully handle)
        error_handling_success = True
        try:
            # This should either reject gracefully or fall back to default
            if hasattr(test.overlord, "response_format"):
                test.overlord.response_format = "invalid_format"

            response = await test.overlord.chat(
                message="Test with invalid format",
                user_id="test_user",
                session_id="error_handling_test",
                use_async=False,
                stream=False,
            )

            # Should get some response even with invalid format
            content = response.content if hasattr(response, "content") else str(response)
            if not content.strip():
                error_handling_success = False

        except Exception as e:
            # Exception is okay as long as it's handled gracefully
            test.formatter.print_debug(f"Invalid format handling: {e}")

        test.formatter.print_info(
            f"Error handling: {'PASSED' if error_handling_success else 'FAILED'}"
        )

        # Overall success
        overall_success = all(
            [json_consistency, switching_success, persistence_success, error_handling_success]
        )

        # Record result
        test.results.append(overall_success)

        if overall_success:
            test.formatter.print_success("All format consistency tests passed")
        else:
            test.formatter.print_failure("Some format consistency tests failed")

        # Print formatting-specific summary
        test.print_formatting_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if overall_success else 1

    # Run the async test function directly
    try:
        exit_code = asyncio.run(run_consistency_test())
        return exit_code
    except Exception as e:
        test.formatter.print_error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
