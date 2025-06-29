"""
MUXI Scheduler Input Validation

Provides comprehensive input validation and sanitization for the scheduler
to prevent security vulnerabilities and ensure data integrity.

Security Features:
- Input sanitization for LLM prompts
- Length validation for all inputs
- Resource limit enforcement
"""

import re
from typing import Optional
from datetime import datetime

from ...utils.datetime_utils import utc_now


class SchedulerInputValidator:
    """Input validator for scheduler operations."""

    # Security limits
    MAX_TITLE_LENGTH = 500
    MAX_PROMPT_LENGTH = 10000
    MAX_USER_ID_LENGTH = 255
    MAX_FORMATION_ID_LENGTH = 255
    MAX_SCHEDULE_TEXT_LENGTH = 1000

    # Dangerous patterns that could be exploited
    DANGEROUS_PATTERNS = [
        r"```[^`]*```",  # Code blocks
        r"<[^>]*>",  # HTML/XML tags
        r"\{[^}]*\}",  # JSON-like structures that could contain code
        r"`[^`]*`",  # Inline code
        r"javascript:",  # JavaScript URLs
        r"data:",  # Data URLs
        r"file://",  # File URLs
        r"\\x[0-9a-fA-F]{2}",  # Hex escape sequences
        r"\\u[0-9a-fA-F]{4}",  # Unicode escape sequences
        r"eval\s*\(",  # eval function calls
        r"exec\s*\(",  # exec function calls
        r"import\s+",  # Python imports
        r"from\s+\w+\s+import",  # Python from imports
        r"__[a-zA-Z]+__",  # Python dunder methods
        r"subprocess\.",  # Subprocess calls
        r"os\.",  # OS module calls
        r"system\(",  # System calls
        r"shell=True",  # Shell execution
    ]

    # Valid patterns for user IDs and formation IDs
    VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

    @staticmethod
    def sanitize_schedule_text(text: str) -> str:
        """
        Sanitize user input for LLM prompts to prevent prompt injection.

        Args:
            text: Raw schedule text from user

        Returns:
            Sanitized text safe for LLM prompts

        Raises:
            ValueError: If text is too long or contains dangerous patterns
        """
        if not text or not isinstance(text, str):
            raise ValueError("Schedule text must be a non-empty string")

        if len(text) > SchedulerInputValidator.MAX_SCHEDULE_TEXT_LENGTH:
            raise ValueError(
                f"Schedule text too long (max {SchedulerInputValidator.MAX_SCHEDULE_TEXT_LENGTH} "
                f"characters)"
            )

        # Remove dangerous patterns
        sanitized = text
        for pattern in SchedulerInputValidator.DANGEROUS_PATTERNS:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

        # Remove multiple whitespace and normalize
        sanitized = re.sub(r"\s+", " ", sanitized).strip()

        # Ensure we still have content after sanitization
        if not sanitized:
            raise ValueError("Schedule text is empty after sanitization")

        return sanitized

    @staticmethod
    def validate_user_id(user_id: str) -> None:
        """
        Validate user ID format and length.

        Args:
            user_id: User identifier

        Raises:
            ValueError: If user_id is invalid
        """
        if not user_id or not isinstance(user_id, str):
            raise ValueError("user_id must be a non-empty string")

        if len(user_id) > SchedulerInputValidator.MAX_USER_ID_LENGTH:
            raise ValueError(
                f"user_id too long (max {SchedulerInputValidator.MAX_USER_ID_LENGTH} characters)"
            )

        if not SchedulerInputValidator.VALID_ID_PATTERN.match(user_id):
            raise ValueError(
                "user_id contains invalid characters (only alphanumeric, underscore, hyphen, "
                "dot allowed)"
            )

    @staticmethod
    def validate_formation_id(formation_id: str) -> None:
        """
        Validate formation ID format and length.

        Args:
            formation_id: Formation identifier

        Raises:
            ValueError: If formation_id is invalid
        """
        if not formation_id or not isinstance(formation_id, str):
            raise ValueError("formation_id must be a non-empty string")

        if len(formation_id) > SchedulerInputValidator.MAX_FORMATION_ID_LENGTH:
            raise ValueError(
                f"formation_id too long (max {SchedulerInputValidator.MAX_FORMATION_ID_LENGTH} "
                f"characters)"
            )

        if not SchedulerInputValidator.VALID_ID_PATTERN.match(formation_id):
            raise ValueError(
                "formation_id contains invalid characters (only alphanumeric, underscore, hyphen, "
                "dot allowed)"
            )

    @staticmethod
    def validate_title(title: str) -> None:
        """
        Validate job title length and content.

        Args:
            title: Job title

        Raises:
            ValueError: If title is invalid
        """
        if not title or not isinstance(title, str):
            raise ValueError("title must be a non-empty string")

        if len(title) > SchedulerInputValidator.MAX_TITLE_LENGTH:
            raise ValueError(
                f"title too long (max {SchedulerInputValidator.MAX_TITLE_LENGTH} characters)"
            )

        # Remove dangerous patterns from title
        for pattern in SchedulerInputValidator.DANGEROUS_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                raise ValueError("title contains potentially dangerous content")

    @staticmethod
    def validate_prompt(prompt: str, field_name: str = "prompt") -> None:
        """
        Validate prompt length and content.

        Args:
            prompt: Prompt text
            field_name: Name of the field for error messages

        Raises:
            ValueError: If prompt is invalid
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError(f"{field_name} must be a non-empty string")

        if len(prompt) > SchedulerInputValidator.MAX_PROMPT_LENGTH:
            raise ValueError(
                f"{field_name} too long (max {SchedulerInputValidator.MAX_PROMPT_LENGTH} characters)"
            )

        # Check for extremely dangerous patterns in prompts
        dangerous_prompt_patterns = [
            r"exec\s*\(",
            r"eval\s*\(",
            r"__import__",
            r"subprocess",
            r"system\(",
            r"shell=True",
        ]

        for pattern in dangerous_prompt_patterns:
            if re.search(pattern, prompt, re.IGNORECASE):
                raise ValueError(f"{field_name} contains potentially dangerous content")

    @staticmethod
    def validate_cron_expression(cron_expr: str) -> None:
        """
        Validate cron expression format and semantic correctness.

        Args:
            cron_expr: Cron expression string

        Raises:
            ValueError: If cron expression is invalid
        """
        if not cron_expr or not isinstance(cron_expr, str):
            raise ValueError("cron_expression must be a non-empty string")

        # Length safety check
        if len(cron_expr) > 100:
            raise ValueError("Cron expression too long")

        # Use croniter for comprehensive validation
        try:
            from croniter import croniter
            from datetime import datetime

            # Test if croniter can parse the expression
            cron = croniter(cron_expr, datetime.now())
            # Try to get the next execution time to ensure it's valid
            next_time = cron.get_next(datetime)
            if next_time is None:
                raise ValueError("Cron expression produces no valid execution times")

        except ImportError:
            raise ValueError("croniter library not available for cron validation")
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {str(e)}")

    @staticmethod
    def validate_job_creation(
        user_id: str,
        formation_id: str,
        title: str,
        original_prompt: str,
        execution_prompt: str,
        cron_expression: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        is_recurring: bool = True,
    ) -> None:
        """
        Comprehensive validation for job creation parameters.

        Args:
            user_id: User identifier
            formation_id: Formation identifier
            title: Job title
            original_prompt: Original user prompt
            execution_prompt: Processed execution prompt
            cron_expression: Cron expression for recurring jobs
            scheduled_for: Datetime for one-time jobs
            is_recurring: Whether job is recurring

        Raises:
            ValueError: If any parameter is invalid
        """
        # Validate required fields
        SchedulerInputValidator.validate_user_id(user_id)
        SchedulerInputValidator.validate_formation_id(formation_id)
        SchedulerInputValidator.validate_title(title)
        SchedulerInputValidator.validate_prompt(original_prompt, "original_prompt")
        SchedulerInputValidator.validate_prompt(execution_prompt, "execution_prompt")

        # Validate job type specific fields
        if is_recurring:
            if not cron_expression:
                raise ValueError("Recurring jobs require a cron_expression")
            SchedulerInputValidator.validate_cron_expression(cron_expression)
            if scheduled_for is not None:
                raise ValueError("Recurring jobs should not have scheduled_for")
        else:
            if not scheduled_for:
                raise ValueError("One-time jobs require a scheduled_for datetime")
            if cron_expression is not None:
                raise ValueError("One-time jobs should not have cron_expression")

            # Validate scheduled_for is in the future
            if scheduled_for <= utc_now():
                raise ValueError("scheduled_for must be in the future")
