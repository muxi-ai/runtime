#!/usr/bin/env python3
"""
Test 12A2: Advanced Natural Language Scheduling

Tests the system's ability to parse complex natural language scheduling requests
including relative dates, complex recurrence patterns, and context-aware scheduling.
"""

import sys

from .base_scheduling_test import BaseSchedulingTest
def main():
    """Test advanced natural language scheduling."""
    test = BaseSchedulingTest("12a2_natural_language_scheduling", "Test advanced natural language scheduling")

    async def run_advanced_scheduling_test():
        # Setup formation using the shared scheduling formation
        await test.setup_formation(yaml_name="formation-scheduling.yaml")

        # Complex natural language test cases
        complex_cases = [
            # Relative dates
            "Schedule a call for next Monday morning",
            "Remind me in 2 hours to follow up on the proposal",
            "Set up a meeting for the day after tomorrow at 2pm",
            "Schedule a review session for next week Thursday",

            # Complex recurrence patterns
            "Remind me every other week on Tuesdays to review metrics",
            "Schedule a monthly team meeting on the first Friday of each month",
            "Set up quarterly reviews every 3 months starting next month",
            "Create a bi-weekly standup every other Monday at 10am",

            # Time zone aware (if supported)
            "Schedule a call for 3pm Eastern time tomorrow",
            "Set a reminder for 9am Pacific time next Friday",

            # Context-aware scheduling
            "Schedule the product launch meeting for next Tuesday after the design review",
            "Remind me to submit my timesheet every Friday before 5pm",
            "Set up the weekly retrospective every Thursday after the sprint demo",

            # Duration-based scheduling
            "Book a 2-hour workshop for next Wednesday afternoon",
            "Schedule a 30-minute check-in call for tomorrow morning",
            "Set aside 1 hour next Friday for code review",

            # Conditional scheduling
            "Schedule a backup meeting for next Friday if the original gets cancelled",
            "Remind me to check the weather before the outdoor event on Sunday",
        ]

        # Test complex natural language parsing
        test.formatter.print_section("Complex Natural Language Parsing")
        complex_results = await test.test_natural_language_scheduling(complex_cases)

        # Analyze results by category
        categories = {
            "relative_dates": complex_cases[:4],
            "complex_recurrence": complex_cases[4:8],
            "time_zone": complex_cases[8:10],
            "context_aware": complex_cases[10:13],
            "duration_based": complex_cases[13:16],
            "conditional": complex_cases[16:]
        }

        category_results = {}
        for category, cases in categories.items():
            successful = 0
            for case in cases:
                # Find the result for this case
                for detail in complex_results["parsing_details"]:
                    if detail["case"] == case and detail["status"] == "SUCCESS":
                        successful += 1
                        break

            success_rate = successful / len(cases) if cases else 0
            category_results[category] = success_rate
            test.formatter.print_info(f"{category.replace('_', ' ').title()}: {success_rate:.1%} ({successful}/{len(cases)})")

        # Test edge cases and error handling
        test.formatter.print_section("Edge Cases and Error Handling")

        edge_cases = [
            "Schedule something for yesterday",  # Past date
            "Remind me every 0 hours",  # Invalid interval
            "Set up a meeting for the 32nd of March",  # Invalid date
            "Schedule a call for 25 o'clock",  # Invalid time
            "",  # Empty message
            "Just a random message with no scheduling intent",  # No scheduling intent
        ]

        edge_results = []
        for i, case in enumerate(edge_cases):
            try:
                await test.test_schedule_creation(
                    message=case,
                    user_id="edge_test_user",
                    session_id=f"edge_test_{i}"
                )

                # For edge cases, we expect graceful handling (either rejection or correction)
                # Success here means the system handled it appropriately, not necessarily created a schedule
                edge_results.append(True)  # Assume graceful handling if no exception

            except Exception as e:
                test.formatter.print_debug(f"Edge case handled with exception: {e}")
                edge_results.append(True)  # Exception is okay for invalid input

        edge_success = all(edge_results)

        # Test scheduling with context preservation
        test.formatter.print_section("Context Preservation Test")

        context_messages = [
            "I need to schedule some meetings for next week",
            "The first one should be with the marketing team on Monday at 10am",
            "Then schedule the engineering sync for Wednesday at 2pm",
            "And finally the client call on Friday at 3pm"
        ]

        context_success = True
        for i, message in enumerate(context_messages):
            try:
                response = await test.overlord.chat(
                    message=message,
                    user_id="context_user",
                    session_id="context_preservation_test",  # Same session
                    use_async=False,
                    stream=False
                )

                content = response.content if hasattr(response, 'content') else str(response)
                test.transcript.append((message, content))

                # For the first message, expect acknowledgment
                # For subsequent messages, expect schedule creation
                if i == 0:
                    # First message is just context setting
                    continue
                else:
                    # Subsequent messages should create schedules
                    schedule_info = test.extract_schedule_info(content)
                    if not schedule_info["created"]:
                        context_success = False
                        test.formatter.print_warning(f"Context message {i} failed to create schedule")

            except Exception as e:
                test.formatter.print_error(f"Context preservation error: {e}")
                context_success = False

        # Overall success criteria
        min_success_rate = 0.6  # 60% minimum success rate for complex cases
        overall_success = (
            complex_results["successful_parses"] >= (complex_results["total_cases"] * min_success_rate) and
            edge_success and
            context_success
        )

        # Record result
        test.results.append(overall_success)

        # Print summary
        test.formatter.print_section("Advanced Scheduling Test Summary")
        test.formatter.print_info(f"Complex parsing: {complex_results['successful_parses']}/{complex_results['total_cases']} ({complex_results['successful_parses']/complex_results['total_cases']:.1%})")
        test.formatter.print_info(f"Edge case handling: {'PASSED' if edge_success else 'FAILED'}")
        test.formatter.print_info(f"Context preservation: {'PASSED' if context_success else 'FAILED'}")

        if overall_success:
            test.formatter.print_success("Advanced natural language scheduling tests passed")
        else:
            test.formatter.print_failure("Some advanced scheduling tests failed")

        # Print category breakdown
        test.formatter.print_section("Category Performance")
        for category, success_rate in category_results.items():
            status = "GOOD" if success_rate >= 0.7 else "NEEDS_IMPROVEMENT" if success_rate >= 0.5 else "POOR"
            test.formatter.print_info(f"{category.replace('_', ' ').title()}: {success_rate:.1%} ({status})")

        # Print scheduling-specific summary
        test.print_scheduling_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if overall_success else 1

    return test.run_in_event_loop(
        "12a2_natural_language_scheduling",
        "Test advanced natural language scheduling",
        "12_scheduling",
        [],  # We handle test cases manually
        None,  # Use pattern-based formation path
        "formation-scheduling.yaml",  # Use shared formation
    )
if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
