#!/usr/bin/env python3
"""
Test 10A2: Stream Content Quality

Tests that streaming content is coherent and complete when reassembled.
"""

import asyncio
import sys
from pathlib import Path

from .base_streaming_test import BaseStreamingTest


def main():
    """Test stream content quality and completeness."""
    test = BaseStreamingTest("10a2_stream_content", "Test stream content quality and completeness")

    async def run_content_test():
        # Setup formation using the shared streaming formation
        formation_path = Path(__file__).parent / "formations" / "formation-streaming"
        await test.setup_formation(formation_path=str(formation_path))

        # Test with a request that should produce substantial content
        result = await test.test_basic_streaming(
            message="Explain the history of artificial intelligence from the 1950s to today",
            user_id="test_user",
            session_id="content_test_10a2",
            expected_keywords=["artificial intelligence", "history", "1950s"],
            timeout=45.0,
        )

        success = result["success"]

        if success:
            # Additional content quality checks
            content_analysis = result["content_analysis"]

            # Check content length (should be substantial for this topic)
            min_content_length = 200  # Minimum expected content length
            if content_analysis["total_content_length"] < min_content_length:
                test.formatter.print_warning(
                    f"Content length {content_analysis['total_content_length']} below minimum {min_content_length}"
                )
                success = False

            # Check for coherent sentences (basic check)
            full_content = content_analysis["full_content"]
            sentence_endings = (
                full_content.count(".") + full_content.count("!") + full_content.count("?")
            )
            if sentence_endings < 3:  # Should have at least a few complete sentences
                test.formatter.print_warning(
                    f"Content appears incomplete (only {sentence_endings} sentence endings)"
                )
                success = False

            # Check event distribution
            if content_analysis["content_events"] == 0:
                test.formatter.print_error("No content events received")
                success = False

            if success:
                test.formatter.print_success("Stream content quality test passed")
                test.formatter.print_debug(
                    f"Content length: {content_analysis['total_content_length']} characters"
                )
                test.formatter.print_debug(f"Sentence endings: {sentence_endings}")
            else:
                test.formatter.print_failure("Stream content quality test failed")

        else:
            test.formatter.print_failure("Basic streaming failed")

        # Test stream interruption behavior
        print("\n" + "=" * 60); print("Testing Stream Interruption"); print("=" * 60)
        interrupt_result = await test.test_stream_interruption(
            message="Write a detailed essay about machine learning algorithms",
            interrupt_after=3.0,
            user_id="test_user",
            session_id="interrupt_test_10a2",
        )

        interrupt_success = interrupt_result["success"]
        if interrupt_success:
            test.formatter.print_success("Stream interruption handled gracefully")
            test.formatter.print_debug(
                f"Events before interrupt: {interrupt_result['events_before_interrupt']}"
            )
        else:
            test.formatter.print_failure("Stream interruption not handled properly")

        # Overall success
        overall_success = success and interrupt_success

        # Record result
        test.results.append(overall_success)

        # Print streaming-specific summary
        test.print_streaming_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if overall_success else 1

    return asyncio.run(run_content_test())


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
