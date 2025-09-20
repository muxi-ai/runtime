"""
Base test class for Area 12 - Scheduling tests.
"""

import re
from typing import Dict, Any, List

from ..common.base import BaseE2ETest


class BaseSchedulingTest(BaseE2ETest):
    """
    Base class for scheduling tests.

    Provides:
    - Schedule creation verification
    - Natural language schedule parsing
    - Schedule execution monitoring
    - Recurring vs one-time schedule handling
    - Schedule cancellation testing
    """

    def __init__(self, test_name: str, test_description: str):
        super().__init__(test_name, test_description, "12_scheduling")

        # Scheduling-specific state
        self.created_schedules = []
        self.schedule_results = []
        self.schedule_errors = []

    def extract_schedule_info(self, response_content: str) -> Dict[str, Any]:
        """
        Extract schedule information from response content.

        Args:
            response_content: Response content to analyze

        Returns:
            Dict with extracted schedule information
        """
        schedule_info = {
            "created": False,
            "job_id": None,
            "schedule_type": None,
            "schedule_time": None,
            "description": None,
            "status": None,
        }

        content_lower = response_content.lower()

        # Check if schedule was created
        creation_indicators = [
            "scheduled successfully",
            "schedule created",
            "job created",
            "task scheduled",
            "reminder set",
        ]

        for indicator in creation_indicators:
            if indicator in content_lower:
                schedule_info["created"] = True
                break

        # Extract job ID
        job_id_patterns = [
            r"job id:?\s*([a-zA-Z0-9-_]+)",
            r"schedule id:?\s*([a-zA-Z0-9-_]+)",
            r"task id:?\s*([a-zA-Z0-9-_]+)",
            r"id:?\s*([a-zA-Z0-9-_]+)",
        ]

        for pattern in job_id_patterns:
            match = re.search(pattern, content_lower)
            if match:
                schedule_info["job_id"] = match.group(1)
                break

        # Determine schedule type
        if any(word in content_lower for word in ["daily", "every day", "recurring", "repeat"]):
            schedule_info["schedule_type"] = "recurring"
        elif any(word in content_lower for word in ["once", "tomorrow", "next", "one-time"]):
            schedule_info["schedule_type"] = "one-time"
        elif any(word in content_lower for word in ["weekly", "monthly", "yearly"]):
            schedule_info["schedule_type"] = "recurring"

        # Extract time information
        time_patterns = [
            r"(\d{1,2}:\d{2}\s*(?:am|pm)?)",
            r"(\d{1,2}\s*(?:am|pm))",
            r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        ]

        for pattern in time_patterns:
            match = re.search(pattern, content_lower)
            if match:
                schedule_info["schedule_time"] = match.group(1)
                break

        return schedule_info

    async def test_schedule_creation(
        self,
        message: str,
        expected_type: str = None,
        user_id: str = "test_user",
        session_id: str = "test_session",
    ) -> Dict[str, Any]:
        """
        Test schedule creation from natural language.

        Args:
            message: Scheduling message to send
            expected_type: Expected schedule type ("recurring" or "one-time")
            user_id: User ID for the request
            session_id: Session ID for the request

        Returns:
            Dict with schedule creation results
        """
        self.formatter.print_test_case("Schedule Creation Test", message)

        # Send the scheduling request
        response = await self.overlord.chat(
            message=message, user_id=user_id, session_id=session_id, use_async=False, stream=False
        )

        # Extract content
        content = response.content if hasattr(response, "content") else str(response)

        # Store transcript
        self.transcript.append((message, content))

        # Extract schedule information
        schedule_info = self.extract_schedule_info(content)

        result = {
            "message": message,
            "response": content,
            "schedule_info": schedule_info,
            "success": False,
            "type_match": False,
        }

        # Check if schedule was created
        if schedule_info["created"]:
            result["success"] = True
            self.formatter.print_success("Schedule created successfully")

            if schedule_info["job_id"]:
                self.formatter.print_debug(f"Job ID: {schedule_info['job_id']}")
                self.created_schedules.append(schedule_info["job_id"])

            if schedule_info["schedule_type"]:
                self.formatter.print_debug(f"Schedule type: {schedule_info['schedule_type']}")

            if schedule_info["schedule_time"]:
                self.formatter.print_debug(f"Schedule time: {schedule_info['schedule_time']}")

            # Check type match if expected
            if expected_type:
                result["type_match"] = schedule_info["schedule_type"] == expected_type
                if result["type_match"]:
                    self.formatter.print_success(f"Schedule type matches expected: {expected_type}")
                else:
                    self.formatter.print_warning(
                        f"Expected {expected_type}, got {schedule_info['schedule_type']}"
                    )

        else:
            self.formatter.print_failure("Schedule creation failed or not detected")
            self.formatter.print_debug(f"Response: {content[:200]}...")

        # Store result
        self.schedule_results.append(result)

        return result

    async def test_multiple_schedules(
        self,
        schedule_requests: List[Dict[str, Any]],
        user_id: str = "test_user",
        session_id_prefix: str = "schedule_test",
    ) -> List[bool]:
        """
        Test multiple schedule creation requests.

        Args:
            schedule_requests: List of schedule request dicts with 'message' and optional 'expected_type'
            user_id: User ID for requests
            session_id_prefix: Prefix for session IDs

        Returns:
            List of success status for each request
        """
        results = []

        for i, request in enumerate(schedule_requests):
            message = request["message"]
            expected_type = request.get("expected_type")
            session_id = f"{session_id_prefix}_{i}"

            result = await self.test_schedule_creation(
                message=message, expected_type=expected_type, user_id=user_id, session_id=session_id
            )

            success = result["success"]
            if expected_type:
                success = success and result["type_match"]

            results.append(success)

        return results

    async def test_schedule_management(
        self, job_id: str = None, user_id: str = "test_user", session_id: str = "management_test"
    ) -> Dict[str, Any]:
        """
        Test schedule management operations (list, cancel, modify).

        Args:
            job_id: Optional specific job ID to test operations on
            user_id: User ID for requests
            session_id: Session ID for requests

        Returns:
            Dict with management operation results
        """
        self.formatter.print_test_case(
            "Schedule Management Test", f"Testing management for {job_id or 'all schedules'}"
        )

        results = {"list_schedules": False, "cancel_schedule": False, "modify_schedule": False}

        # Test listing schedules
        try:
            list_response = await self.overlord.chat(
                message="Show me all my scheduled tasks",
                user_id=user_id,
                session_id=session_id,
                use_async=False,
                stream=False,
            )

            list_content = (
                list_response.content if hasattr(list_response, "content") else str(list_response)
            )

            if any(
                word in list_content.lower() for word in ["schedule", "task", "job", "reminder"]
            ):
                results["list_schedules"] = True
                self.formatter.print_success("Schedule listing works")
            else:
                self.formatter.print_warning("Schedule listing may not be working")

        except Exception as e:
            self.formatter.print_error(f"Schedule listing error: {e}")

        # Test canceling a schedule (if we have job IDs)
        if job_id or self.created_schedules:
            cancel_id = job_id or (self.created_schedules[0] if self.created_schedules else None)

            if cancel_id:
                try:
                    cancel_response = await self.overlord.chat(
                        message=f"Cancel the scheduled task with ID {cancel_id}",
                        user_id=user_id,
                        session_id=session_id,
                        use_async=False,
                        stream=False,
                    )

                    cancel_content = (
                        cancel_response.content
                        if hasattr(cancel_response, "content")
                        else str(cancel_response)
                    )

                    if any(
                        word in cancel_content.lower()
                        for word in ["cancelled", "canceled", "removed", "deleted"]
                    ):
                        results["cancel_schedule"] = True
                        self.formatter.print_success("Schedule cancellation works")
                    else:
                        self.formatter.print_warning("Schedule cancellation may not be working")

                except Exception as e:
                    self.formatter.print_error(f"Schedule cancellation error: {e}")

        return results

    async def test_natural_language_scheduling(self, test_cases: List[str]) -> Dict[str, Any]:
        """
        Test natural language schedule parsing with various formats.

        Args:
            test_cases: List of natural language scheduling requests

        Returns:
            Dict with natural language parsing results
        """
        self.formatter.print_section("Natural Language Scheduling Test")

        results = {
            "total_cases": len(test_cases),
            "successful_parses": 0,
            "failed_parses": 0,
            "parsing_details": [],
        }

        for i, test_case in enumerate(test_cases):
            self.formatter.print_debug(f"Testing: {test_case}")

            result = await self.test_schedule_creation(
                message=test_case, user_id="nl_test_user", session_id=f"nl_test_{i}"
            )

            if result["success"]:
                results["successful_parses"] += 1
                status = "SUCCESS"
            else:
                results["failed_parses"] += 1
                status = "FAILED"

            results["parsing_details"].append(
                {"case": test_case, "status": status, "schedule_info": result["schedule_info"]}
            )

        success_rate = (
            results["successful_parses"] / results["total_cases"]
            if results["total_cases"] > 0
            else 0
        )
        self.formatter.print_info(f"Natural language parsing success rate: {success_rate:.1%}")

        return results

    def print_scheduling_summary(self):
        """Print summary specific to scheduling tests."""
        self.formatter.print_section("Scheduling Test Summary")

        if self.schedule_results:
            total_tests = len(self.schedule_results)
            successful_creations = sum(1 for r in self.schedule_results if r["success"])

            self.formatter.print_info(
                f"Schedule creation tests: {successful_creations}/{total_tests}"
            )

            # Analyze schedule types
            type_counts = {}
            for result in self.schedule_results:
                schedule_type = result["schedule_info"].get("schedule_type")
                if schedule_type:
                    type_counts[schedule_type] = type_counts.get(schedule_type, 0) + 1

            if type_counts:
                self.formatter.print_info("Schedule types created:")
                for schedule_type, count in type_counts.items():
                    self.formatter.print_debug(f"  {schedule_type}: {count}")

        if self.created_schedules:
            self.formatter.print_info(f"Created schedule IDs: {len(self.created_schedules)}")
            for schedule_id in self.created_schedules[:3]:  # Show first 3
                self.formatter.print_debug(f"  {schedule_id}")

        if self.schedule_errors:
            self.formatter.print_warning(
                f"Schedule errors encountered: {len(self.schedule_errors)}"
            )
            for error in self.schedule_errors:
                self.formatter.print_debug(f"  Error: {error}")
