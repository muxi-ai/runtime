#!/usr/bin/env python3
"""
Test 11A2: Format Consistency

Tests that response formats remain consistent across multiple requests
and that format switching works properly.

Reduced call count (8 LLM calls) to avoid timeout. Self-contained prompts
to avoid triggering clarification.
"""

import asyncio
import sys

try:
    from base_formatting_test import BaseFormattingTest
except ImportError:
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from base_formatting_test import BaseFormattingTest


def main():
    """Test format consistency and switching."""
    test = BaseFormattingTest("11a2_format_consistency", "Test format consistency and switching")

    async def run_consistency_test():
        await test.setup_formation()

        # --- JSON consistency (2 calls instead of 3) ---
        test.formatter.print_section("Format Consistency Test")

        json_messages = [
            "Create a JSON object representing a book with title 'Dune', author 'Frank Herbert', and year 1965",
            "Generate a JSON object for a user profile with name 'Alice', age 30, and email 'alice@example.com'",
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

        # --- Format switching (4 calls instead of 5) ---
        test.formatter.print_section("Format Switching Test")

        format_sequence = [
            ("json", "Create a JSON object with city 'London', temperature 15, and condition 'cloudy'"),
            ("markdown", "Write a short markdown guide to making coffee with a heading and bullet list"),
            ("html", "Create an HTML form with two text inputs for name and email and a submit button"),
            ("text", "Explain photosynthesis in 3-4 plain text sentences without any formatting"),
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

        # --- Format persistence (2 calls instead of 3) ---
        test.formatter.print_section("Format Persistence Test")

        persistence_messages = [
            "Explain what machine learning is in a markdown section with a heading",
            "Write about the three main data structures (arrays, linked lists, trees) using markdown bullet points",
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

        # Overall success (skip error handling sub-test -- not format-related)
        overall_success = all([json_consistency, switching_success, persistence_success])

        test.results.append(overall_success)

        if overall_success:
            test.formatter.print_success("All format consistency tests passed")
        else:
            test.formatter.print_failure("Some format consistency tests failed")

        test.print_formatting_summary()
        await test.cleanup_formation()

        return 0 if overall_success else 1

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
    import os
    os._exit(exit_code)
