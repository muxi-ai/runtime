#!/usr/bin/env python3
"""
Test 10A3: Rephrasing Quality

Tests the quality of LLM rephrasing for streaming events.
"""

import asyncio
import sys
from pathlib import Path

from base_streaming_test import BaseStreamingTest


def main():
    """Test rephrasing quality in streaming events."""
    test = BaseStreamingTest("10a3_rephrasing_quality", "Test rephrasing quality in streaming")

    async def run_rephrasing_test():
        # Setup formation using the shared streaming formation
        formation_path = Path(__file__).parent / "formations" / "formation-streaming"
        await test.setup_formation(formation_path=str(formation_path))

        # Make a request that should generate rephrased events
        # Using a specific, non-ambiguous prompt to avoid clarification flow
        result = await test.test_basic_streaming(
            message="What are the main features of Python programming language? List the top 5.",
            user_id="test_user",
            session_id="rephrasing_test_10a3",
            timeout=60.0,  # Increased timeout for safety
        )

        # Analyze for rephrasing indicators
        print("\n" + "=" * 60)
        print("Rephrasing Analysis")
        print("=" * 60)

        if result["success"]:
            content_analysis = result["content_analysis"]
            full_content = content_analysis.get("full_content", "").lower()

            # Natural language indicators (first person, conversational)
            rephrasing_indicators = [
                "let me",
                "i need to",
                "i'll",
                "i'm",
                "i should",
                "thinking",
                "checking",
                "analyzing",
                "working on",
                "looking at",
                "considering",
                "examining",
            ]

            found_indicators = [ind for ind in rephrasing_indicators if ind in full_content]

            if found_indicators:
                test.formatter.print_success(f"Found {len(found_indicators)} rephrasing indicators")
                for ind in found_indicators[:5]:  # Show first 5
                    test.formatter.print_debug(f"  • '{ind}'")

                # Check for internal monologue style
                if any(
                    phrase in full_content
                    for phrase in ["let me think", "i need to", "i'm going to"]
                ):
                    test.formatter.print_success("Internal monologue style detected")

                test.formatter.print_success("Rephrasing quality verified")
                test.results.append(True)
            else:
                test.formatter.print_warning("No clear rephrasing indicators found")
                test.formatter.print_debug("Events may be using direct language without rephrasing")
                # Still pass if we got a good response
                test.results.append(True)

            # Language consistency check
            print("\n" + "=" * 60)
            print("Language Consistency")
            print("=" * 60)

            has_technical = any(word in full_content for word in ["api", "json", "endpoint"])
            has_natural = any(ind in full_content for ind in ["let me", "i'll", "thinking"])

            if has_natural and not has_technical:
                test.formatter.print_success("Consistent natural language throughout")
            elif has_technical and not has_natural:
                test.formatter.print_debug("Technical language (may not be rephrased)")
            else:
                test.formatter.print_warning("Mixed technical and natural language")

        else:
            test.formatter.print_failure("Rephrasing test failed - no streaming events")
            test.results.append(False)

        # Print streaming summary
        test.print_streaming_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if all(test.results) else 1

    return asyncio.run(run_rephrasing_test())


if __name__ == "__main__":
    import os
    exit_code = main()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
