#!/usr/bin/env python3
"""
Test 12A1: Basic Scheduling Detection and Creation

Tests that the scheduler correctly detects and creates both recurring and one-off schedules
from natural language requests.
"""

import sys

from .base_scheduling_test import BaseSchedulingTest


def main():
    """Test basic scheduling functionality."""
    test = BaseSchedulingTest(
        "12a1_basic_scheduling", "Test basic scheduling detection and creation"
    )

    async def run_scheduling_test():
        # Setup formation using the shared scheduling formation
        await test.setup_formation(yaml_name="formation-scheduling.yaml")

        # Define test cases for different schedule types
        schedule_requests = [
            {"message": "Remind me every day at 9am to check emails", "expected_type": "recurring"},
            {"message": "Schedule a meeting tomorrow at 3pm", "expected_type": "one-time"},
            {"message": "Schedule team sync every Monday at 2pm", "expected_type": "recurring"},
            {
                "message": "Set a reminder for next Friday at 10am to review reports",
                "expected_type": "one-time",
            },
            {
                "message": "Create a weekly reminder every Wednesday at 1pm for status updates",
                "expected_type": "recurring",
            },
        ]

        # Test schedule creation
        test.formatter.print_section("Basic Schedule Creation Tests")
        creation_results = await test.test_multiple_schedules(
            schedule_requests=schedule_requests,
            user_id="test_user",
            session_id_prefix="basic_scheduling",
        )

        creation_success = all(creation_results)

        # Test natural language variations
        nl_test_cases = [
            "remind me daily to take vitamins",
            "set up a meeting for next Tuesday at 4pm",
            "schedule a call every other week",
            "create a monthly reminder for the 15th",
            "set an appointment for tomorrow morning",
            "remind me weekly on Fridays to submit timesheet",
        ]

        test.formatter.print_section("Natural Language Parsing Tests")
        nl_results = await test.test_natural_language_scheduling(nl_test_cases)
        nl_success = nl_results["successful_parses"] >= (
            nl_results["total_cases"] * 0.7
        )  # 70% success rate

        # Test schedule management operations
        test.formatter.print_section("Schedule Management Tests")
        management_results = await test.test_schedule_management(
            user_id="test_user", session_id="management_test"
        )

        management_success = management_results["list_schedules"]  # At minimum, listing should work

        # Overall success
        overall_success = creation_success and nl_success and management_success

        # Record result
        test.results.append(overall_success)

        # Print detailed results
        test.formatter.print_section("Test Results Summary")
        test.formatter.print_info(f"Basic creation: {'PASSED' if creation_success else 'FAILED'}")
        test.formatter.print_info(
            f"Natural language: {'PASSED' if nl_success else 'FAILED'} ({nl_results['successful_parses']}/{nl_results['total_cases']})"  # noqa: E501
        )
        test.formatter.print_info(f"Management: {'PASSED' if management_success else 'FAILED'}")

        if overall_success:
            test.formatter.print_success("All basic scheduling tests passed")
        else:
            test.formatter.print_failure("Some basic scheduling tests failed")

        # Print detailed natural language results
        if nl_results["parsing_details"]:
            test.formatter.print_section("Natural Language Parsing Details")
            for detail in nl_results["parsing_details"]:
                status_symbol = "✓" if detail["status"] == "SUCCESS" else "✗"
                test.formatter.print_debug(f"{status_symbol} {detail['case']}")

                schedule_info = detail["schedule_info"]
                if schedule_info.get("schedule_type"):
                    test.formatter.print_debug(f"    Type: {schedule_info['schedule_type']}")
                if schedule_info.get("job_id"):
                    test.formatter.print_debug(f"    ID: {schedule_info['job_id']}")

        # Print scheduling-specific summary
        test.print_scheduling_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if overall_success else 1

    return test.run_in_event_loop(
        "12a1_basic_scheduling",
        "Test basic scheduling detection and creation",
        "12_scheduling",
        [],  # We handle test cases manually
        None,  # Use pattern-based formation path
        "formation-scheduling.yaml",  # Use shared formation
    )


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
