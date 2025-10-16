"""
MUXI Scheduler Natural Language Parser

Converts natural language schedule descriptions into cron expressions
and generates dynamic exclusion rules using LLM capabilities.

Key Features:
- Natural language to cron expression conversion
- Timezone-aware scheduling with DST handling
- Dynamic exclusion rule generation via LLM
- Common schedule pattern recognition
- Multilingual support through LLM processing

Examples:
- "every day at 9am" → "0 9 * * *"
- "every Monday at 2pm" → "0 14 * * 1"
- "every hour during business hours" → "0 9-17 * * 1-5"
- "every 15 minutes" → "*/15 * * * *"

Exclusions:
- "except weekends" → cron pattern "0 0 * * 0,6"
- "except holidays" → dynamic holiday detection rules
- "only during business hours" → inverse exclusion logic
"""

import re
from typing import Dict, Optional, Any, Union, List, Tuple
from datetime import datetime, timedelta
import pytz
import json

from .. import observability
from ...services.llm import LLM
from ...services.intent import IntentDetectionService
from ...datatypes.intent import IntentType, IntentDetectionContext
from ...utils.datetime_utils import utc_now
from .validation import SchedulerInputValidator


class ScheduleParser:
    """
    Natural language schedule parser for MUXI scheduler.

    Converts human-readable schedule descriptions into cron expressions
    and generates dynamic exclusion rules for complex scheduling needs.
    """

    def __init__(self, cache=None, circuit_breaker=None):
        """
        Initialize schedule parser.

        Args:
            cache: Optional SchedulerCache instance for caching results
            circuit_breaker: Optional LLMCircuitBreaker for fault tolerance
        """
        self.llm = None  # Will be initialized when needed
        self.cache = cache
        self.circuit_breaker = circuit_breaker

        # Common time patterns
        self.time_patterns = {
            # 12-hour format
            r"(\d{1,2})\s*(am|pm)": self._parse_12hour,
            r"(\d{1,2}):(\d{2})\s*(am|pm)": self._parse_12hour_minutes,
            # 24-hour format
            r"(\d{1,2}):(\d{2})": self._parse_24hour,
            r"(\d{1,2})h(\d{2})": self._parse_24hour,
            # Named times
            r"(morning|noon|afternoon|evening|midnight)": self._parse_named_time,
        }

        # Common frequency patterns
        self.frequency_patterns = {
            r"every\s+(\d+)\s+minutes?": lambda m: f"*/{m.group(1)} * * * *",
            r"every\s+(\d+)\s+hours?": lambda m: f"0 */{m.group(1)} * * *",
            r"every\s+(\d+)\s+days?": lambda m: f"0 0 */{m.group(1)} * *",
            r"every\s+hour": lambda m: "0 * * * *",
            r"every\s+day": lambda m: "0 0 * * *",
            r"hourly": lambda m: "0 * * * *",
            r"daily": lambda m: "0 0 * * *",
            r"weekly": lambda m: "0 0 * * 0",
            r"monthly": lambda m: "0 0 1 * *",
        }

        # Day patterns
        self.day_patterns = {
            "monday": "1",
            "tuesday": "2",
            "wednesday": "3",
            "thursday": "4",
            "friday": "5",
            "saturday": "6",
            "sunday": "0",
            "mon": "1",
            "tue": "2",
            "wed": "3",
            "thu": "4",
            "fri": "5",
            "sat": "6",
            "sun": "0",
            "weekdays": "1-5",
            "weekends": "0,6",
            "business days": "1-5",
            "work days": "1-5",
        }

        pass  # REMOVED: init-phase observe() call

    async def _get_llm(self) -> Optional[LLM]:
        """Get LLM instance for natural language processing."""
        if not self.llm:
            try:
                # Try to get LLM from context or create new instance
                self.llm = LLM()
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e)},
                    description="Failed to initialize LLM for schedule parsing",
                )
                return None
        return self.llm

    async def parse_schedule(
        self, schedule_text: str, timezone: str = "UTC"
    ) -> Union[str, Dict[str, Any]]:
        """
        Parse natural language schedule into cron expression or specific datetime.

        Args:
            schedule_text: Natural language schedule description
            timezone: Target timezone for the schedule

        Returns:
            For recurring jobs: Cron expression string
            For one-time jobs: Dict with job type and scheduled datetime
        """
        schedule_lower = schedule_text.lower().strip()

        pass  # REMOVED: init-phase observe() call

        # First, detect if this is a one-time or recurring job
        job_type = await self._detect_job_type(schedule_text)

        if job_type == "one_time":
            # Parse as specific datetime
            datetime_result = await self._parse_specific_datetime(schedule_text, timezone)

            pass  # REMOVED: init-phase observe() call

            return datetime_result

        else:
            # Parse as recurring job (existing logic)
            # Try pattern matching first for common cases
            cron_expr = await self._try_pattern_matching(schedule_lower)

            if cron_expr:
                pass  # REMOVED: init-phase observe() call
                return cron_expr

            # Fall back to LLM parsing for complex cases
            cron_expr = await self._llm_parse_schedule(schedule_text, timezone)

            pass  # REMOVED: init-phase observe() call

            return cron_expr

    async def _detect_job_type(self, schedule_text: str) -> str:
        """
        Detect whether this is a one-time or recurring job request.

        Uses IntentDetectionService for language-agnostic detection,
        with caching to avoid redundant LLM calls for similar requests.

        Args:
            schedule_text: Natural language schedule description

        Returns:
            "one_time" or "recurring"
        """
        # Check cache first
        if self.cache:
            cached_type = self.cache.get_cached_job_type(schedule_text)
            if cached_type:
                return cached_type

        # Try to use intent detection service
        try:
            # Get or create intent detection service
            if not hasattr(self, "_intent_detector"):
                # Use existing LLM instance if available
                llm_service = self.llm

                self._intent_detector = IntentDetectionService(
                    llm_service=llm_service, enable_cache=True
                )

            # Use intent detection for schedule type
            result = await self._intent_detector.detect_intent(
                text=schedule_text,
                intent_type=IntentType.SCHEDULE_TYPE,
                context=IntentDetectionContext(),
            )

            # Map intent to job type
            if result.confidence > 0.7:  # High confidence
                if result.intent == "one_time":
                    job_type = "one_time"
                elif result.intent == "recurring":
                    job_type = "recurring"
                else:
                    # Unclear, use LLM fallback
                    job_type = await self._llm_detect_job_type(schedule_text)
            else:
                # Low confidence, use LLM fallback
                job_type = await self._llm_detect_job_type(schedule_text)

            # Cache the result
            if self.cache:
                self.cache.cache_job_type(schedule_text, job_type)

            return job_type

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "schedule_text": schedule_text[:100],
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Intent detection failed for schedule type: {str(e)}",
            )

            # Fall back to keyword-based detection
            return await self._fallback_detect_job_type(schedule_text)

    async def _fallback_detect_job_type(self, schedule_text: str) -> str:
        """
        Fallback keyword-based job type detection.

        Used when intent detection service is not available.
        """
        schedule_lower = schedule_text.lower().strip()

        # Common one-time indicators
        one_time_patterns = [
            r"\bnext\s+(week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"\btomorrow\b",
            r"\btoday\b",
            r"\bthis\s+(week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"\bon\s+(january|february|march|april|may|june|july|august|september|october|november|december)",
            r"\bon\s+\d{1,2}(st|nd|rd|th)",
            r"\bat\s+\d{1,2}:\d{2}\s+(on|next)",
            r"\bin\s+\d+\s+(days?|weeks?|months?)",
            r"\bafter\s+\d+\s+(days?|weeks?|months?)",
            r"\bon\s+\d{4}-\d{2}-\d{2}",  # Date format YYYY-MM-DD
            r"\bon\s+\d{1,2}/\d{1,2}(/\d{4})?",  # Date format M/D or M/D/YYYY
        ]

        # Common recurring indicators
        recurring_patterns = [
            r"\bevery\s+(day|week|month|year|hour|minute)",
            r"\bdaily\b",
            r"\bweekly\b",
            r"\bmonthly\b",
            r"\byearly\b",
            r"\bhourly\b",
            r"\bevery\s+\d+\s+(days?|weeks?|months?|hours?|minutes?)",
            r"\bevery\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"\bevery\s+(morning|afternoon|evening)",
        ]

        # Check for one-time patterns first
        for pattern in one_time_patterns:
            if re.search(pattern, schedule_lower):
                job_type = "one_time"
                # Cache the result
                if self.cache:
                    self.cache.cache_job_type(schedule_text, job_type)
                return job_type

        # Check for recurring patterns
        for pattern in recurring_patterns:
            if re.search(pattern, schedule_lower):
                job_type = "recurring"
                # Cache the result
                if self.cache:
                    self.cache.cache_job_type(schedule_text, job_type)
                return job_type

        # If no clear pattern, use LLM to determine
        job_type = await self._llm_detect_job_type(schedule_text)

        # Cache the LLM result
        if self.cache:
            self.cache.cache_job_type(schedule_text, job_type)

        return job_type

    async def _llm_detect_job_type(self, schedule_text: str) -> str:
        """
        Use LLM to detect job type when patterns are unclear.

        Args:
            schedule_text: Natural language schedule description

        Returns:
            "one_time" or "recurring"
        """
        llm = await self._get_llm()

        if not llm:
            # Fallback to recurring if LLM unavailable
            return "recurring"

        # SECURITY: Sanitize input to prevent prompt injection
        try:
            sanitized_text = SchedulerInputValidator.sanitize_schedule_text(schedule_text)
        except ValueError as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "schedule_text": schedule_text[:100],  # Log only first 100 chars
                    "error": str(e),
                },
                description=f"Schedule text sanitization failed: {e}",
            )
            return "recurring"  # Safe fallback

        # Use parameterized prompt construction for security
        prompt_template = """Determine if this is a ONE-TIME task or a RECURRING task.

Task: {task_text}
(Input has been sanitized for security)

ONE-TIME tasks are executed once at a specific time:
- "remind me tomorrow at 2pm"
- "send report next Friday"
- "check status on December 25th"
- "do X next week"

RECURRING tasks are repeated on a schedule:
- "remind me every day at 2pm"
- "send report every Friday"
- "check status daily"
- "do X every week"

Respond with ONLY: "one_time" or "recurring"
"""

        # Limit length for additional safety and truncate if needed
        safe_text = sanitized_text[:200] if len(sanitized_text) > 200 else sanitized_text
        prompt = prompt_template.format(task_text=safe_text)

        async def call_llm():
            """Inner function to call LLM."""
            response = await llm.generate_text(prompt)
            result = response.strip().lower()

            if "one_time" in result:
                return "one_time"
            elif "recurring" in result:
                return "recurring"
            else:
                # Default to recurring if unclear
                return "recurring"

        try:
            # Use circuit breaker if available
            if self.circuit_breaker:
                from .circuit_breaker import CircuitBreakerError

                result = await self.circuit_breaker.call(call_llm)
            else:
                result = await call_llm()

            return result

        except CircuitBreakerError as e:
            # Circuit breaker is open - fallback to recurring
            observability.observe(
                event_type=observability.SystemEvents.SCHEDULER_CIRCUIT_BREAKER_ACTIVATED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "fallback": "recurring"},
                description="Circuit breaker open, using fallback job type",
            )
            return "recurring"

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"schedule_text": schedule_text, "error": str(e)},
                description=f"LLM job type detection failed: {e}",
            )
            return "recurring"  # Safe fallback

    async def _parse_specific_datetime(
        self, schedule_text: str, timezone: str = "UTC"
    ) -> Optional[Dict[str, Any]]:
        """
        Parse specific datetime for one-time jobs.

        Args:
            schedule_text: Natural language schedule description
            timezone: Target timezone for the schedule

        Returns:
            Dict with job type and scheduled datetime, or None if parsing fails
        """
        llm = await self._get_llm()

        if not llm:
            # Fallback to basic datetime parsing
            return self._fallback_parse_datetime(schedule_text, timezone)

        # Get current time in the target timezone
        tz = pytz.timezone(timezone)
        current_time = utc_now().astimezone(tz)

        # SECURITY: Sanitize input to prevent prompt injection
        try:
            sanitized_text = SchedulerInputValidator.sanitize_schedule_text(schedule_text)
        except ValueError as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "schedule_text": schedule_text[:100],  # Log only first 100 chars
                    "error": str(e),
                },
                description=f"Schedule text sanitization failed: {e}",
            )
            return None  # Safe fallback

        safe_text = sanitized_text[:200] if len(sanitized_text) > 200 else sanitized_text
        prompt_template = """Parse this request into a specific date and time.

Request: {request_text}
(Input has been sanitized for security)"""

        prompt = (
            prompt_template.format(request_text=safe_text)
            + f"""

Current date/time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}
Target timezone: {timezone}

Parse the request and return ONLY a JSON object with this exact format:
{{
    "year": 2025,
    "month": 6,
    "day": 22,
    "hour": 14,
    "minute": 30,
    "timezone": "{timezone}"
}}

Examples:
- "tomorrow at 2pm" → tomorrow's date at 14:00
- "next Friday at 9am" → next Friday's date at 09:00
- "on December 25th at noon" → 2025-12-25 at 12:00
- "next week" → one week from today at 09:00 (default time)
- "in 3 days at 3:30pm" → 3 days from now at 15:30

Return only valid JSON, no explanation.
"""
        )

        response = None
        try:
            response = await llm.generate_text(prompt)

            # Clean up response - remove markdown code blocks if present
            clean_response = response.strip()
            if clean_response.startswith("```"):
                # Remove markdown code block markers
                lines = clean_response.split("\n")
                # Remove first line (```json or ```)
                if len(lines) > 2:
                    lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_response = "\n".join(lines).strip()

            # Parse JSON response
            datetime_data = json.loads(clean_response)

            # Validate required fields
            required_fields = ["year", "month", "day", "hour", "minute", "timezone"]
            if not all(field in datetime_data for field in required_fields):
                raise ValueError("Missing required datetime fields")

            # Create datetime object
            target_tz = pytz.timezone(datetime_data["timezone"])
            scheduled_datetime = target_tz.localize(
                datetime(
                    year=datetime_data["year"],
                    month=datetime_data["month"],
                    day=datetime_data["day"],
                    hour=datetime_data["hour"],
                    minute=datetime_data["minute"],
                )
            )

            # Convert to UTC for storage
            scheduled_datetime_utc = scheduled_datetime.astimezone(pytz.UTC)

            return {
                "job_type": "one_time",
                "scheduled_for": scheduled_datetime_utc,
                "timezone": timezone,
                "original_text": schedule_text,
            }

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            observability.observe(
                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "scheduler_parser",
                    "schedule_text": schedule_text,
                    "response": response[:200] if response is not None else "No response",
                    "error": str(e),
                    "error_type": "datetime_parsing_failed",
                },
                description=f"Failed to parse specific datetime from LLM response: {e}",
            )
            return self._fallback_parse_datetime(schedule_text, timezone)

    def _fallback_parse_datetime(self, schedule_text: str, timezone: str) -> Dict[str, Any]:
        """
        Fallback datetime parsing without LLM.

        Args:
            schedule_text: Natural language schedule description
            timezone: Target timezone

        Returns:
            Dict with basic datetime parsing
        """
        schedule_lower = schedule_text.lower().strip()
        tz = pytz.timezone(timezone)
        current_time = utc_now().astimezone(tz)

        # Basic patterns for common cases
        if "tomorrow" in schedule_lower:
            scheduled_time = current_time + timedelta(days=1)
            scheduled_time = scheduled_time.replace(hour=9, minute=0, second=0, microsecond=0)
        elif "next week" in schedule_lower:
            days_ahead = 7 - current_time.weekday()  # Days until next Monday
            if days_ahead == 0:  # If today is Monday
                days_ahead = 7
            scheduled_time = current_time + timedelta(days=days_ahead)
            scheduled_time = scheduled_time.replace(hour=9, minute=0, second=0, microsecond=0)
        elif "next month" in schedule_lower:
            # First day of next month
            if current_time.month == 12:
                scheduled_time = current_time.replace(
                    year=current_time.year + 1,
                    month=1,
                    day=1,
                    hour=9,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                scheduled_time = current_time.replace(
                    month=current_time.month + 1, day=1, hour=9, minute=0, second=0, microsecond=0
                )
        else:
            # Default to tomorrow at 9am
            scheduled_time = current_time + timedelta(days=1)
            scheduled_time = scheduled_time.replace(hour=9, minute=0, second=0, microsecond=0)

        # Convert to UTC
        scheduled_time_utc = scheduled_time.astimezone(pytz.UTC)

        return {
            "job_type": "one_time",
            "scheduled_for": scheduled_time_utc,
            "timezone": timezone,
            "original_text": schedule_text,
        }

    async def _try_pattern_matching(self, schedule_text: str) -> Optional[str]:
        """
        Try to parse schedule using pattern matching.

        Args:
            schedule_text: Lowercase schedule text

        Returns:
            Cron expression or None if no pattern matched
        """
        # Check frequency patterns first
        for pattern, cron_func in self.frequency_patterns.items():
            match = re.search(pattern, schedule_text)
            if match:
                base_cron = cron_func(match)

                # Check for time specification
                time_spec = self._extract_time_from_text(schedule_text)
                if time_spec:
                    hour, minute = time_spec
                    # Replace hour and minute in cron
                    parts = base_cron.split()
                    if len(parts) >= 2:
                        parts[0] = str(minute)
                        parts[1] = str(hour)
                    base_cron = " ".join(parts)

                # Check for day specification
                day_spec = self._extract_day_from_text(schedule_text)
                if day_spec:
                    parts = base_cron.split()
                    if len(parts) >= 5:
                        parts[4] = day_spec
                    base_cron = " ".join(parts)

                return base_cron

        # Check for specific day + time patterns
        day_time_pattern = (
            r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekdays?|weekends?)"
            r"\s+(?:at\s+)?(.+)"
        )
        match = re.search(day_time_pattern, schedule_text)
        if match:
            day_text = match.group(1)
            time_text = match.group(2)

            day_spec = self.day_patterns.get(day_text)
            time_spec = self._extract_time_from_text(time_text)

            if day_spec and time_spec:
                hour, minute = time_spec
                return f"{minute} {hour} * * {day_spec}"

        # Check for daily at specific time
        daily_time_pattern = r"(?:every\s+day|daily)\s+(?:at\s+)?(.+)"
        match = re.search(daily_time_pattern, schedule_text)
        if match:
            time_text = match.group(1)
            time_spec = self._extract_time_from_text(time_text)

            if time_spec:
                hour, minute = time_spec
                return f"{minute} {hour} * * *"

        return None

    def _extract_time_from_text(self, text: str) -> Optional[Tuple[int, int]]:
        """
        Extract time (hour, minute) from text.

        Args:
            text: Text to extract time from

        Returns:
            Tuple of (hour, minute) or None
        """
        for pattern, parser in self.time_patterns.items():
            match = re.search(pattern, text)
            if match:
                return parser(match)

        return None

    def _extract_day_from_text(self, text: str) -> Optional[str]:
        """
        Extract day specification from text.

        Args:
            text: Text to extract day from

        Returns:
            Cron day specification or None
        """
        for day_text, day_spec in self.day_patterns.items():
            if day_text in text:
                return day_spec

        return None

    def _parse_12hour(self, match) -> Tuple[int, int]:
        """Parse 12-hour time format."""
        hour = int(match.group(1))
        am_pm = match.group(2).lower()

        if am_pm == "pm" and hour != 12:
            hour += 12
        elif am_pm == "am" and hour == 12:
            hour = 0

        return hour, 0

    def _parse_12hour_minutes(self, match) -> Tuple[int, int]:
        """Parse 12-hour time format with minutes."""
        hour = int(match.group(1))
        minute = int(match.group(2))
        am_pm = match.group(3).lower()

        if am_pm == "pm" and hour != 12:
            hour += 12
        elif am_pm == "am" and hour == 12:
            hour = 0

        return hour, minute

    def _parse_24hour(self, match) -> Tuple[int, int]:
        """Parse 24-hour time format."""
        hour = int(match.group(1))
        minute = int(match.group(2))
        return hour, minute

    def _parse_named_time(self, match) -> Tuple[int, int]:
        """Parse named time descriptions."""
        time_name = match.group(1).lower()

        time_map = {
            "morning": (9, 0),
            "noon": (12, 0),
            "afternoon": (14, 0),
            "evening": (18, 0),
            "midnight": (0, 0),
        }

        return time_map.get(time_name, (9, 0))

    async def _llm_parse_schedule(self, schedule_text: str, timezone: str) -> str:
        """
        Use LLM to parse complex schedule descriptions with enhanced prompting.

        Args:
            schedule_text: Natural language schedule description
            timezone: Target timezone

        Returns:
            Cron expression
        """
        llm = await self._get_llm()

        if not llm:
            # Fallback to pattern matching if LLM unavailable
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                description="LLM unavailable, using pattern fallback for schedule parsing",
            )
            return self._fallback_parse_schedule(schedule_text)

        # SECURITY: Sanitize input to prevent prompt injection
        try:
            sanitized_text = SchedulerInputValidator.sanitize_schedule_text(schedule_text)
        except ValueError as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"schedule_text": schedule_text[:100], "error": str(e)},
                description=f"Schedule text sanitization failed: {e}",
            )
            return None  # Safe fallback

        safe_text = sanitized_text[:200] if len(sanitized_text) > 200 else sanitized_text

        # Enhanced prompt with better instructions and examples
        prompt_template = """You are a cron expression generator. Convert natural language schedules to cron format.

SCHEDULE: {schedule_text}
(Input has been sanitized for security)"""

        prompt = (
            prompt_template.format(schedule_text=safe_text)
            + f"""
TIMEZONE: {timezone}

CRON FORMAT: minute hour day-of-month month day-of-week
- minute: 0-59
- hour: 0-23 (24-hour format, adjust for timezone if needed)
- day-of-month: 1-31
- month: 1-12
- day-of-week: 0-6 (0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday)

SPECIAL CHARACTERS:
- * = any value
- */N = every N units (e.g., */15 = every 15 minutes)
- N-M = range (e.g., 1-5 = Monday to Friday)
- N,M,O = list (e.g., 1,3,5 = Monday, Wednesday, Friday)

EXAMPLES:
- "every day at 9am" → "0 9 * * *"
- "every Monday at 2:30pm" → "30 14 * * 1"
- "every 15 minutes" → "*/15 * * * *"
- "every weekday at noon" → "0 12 * * 1-5"
- "every hour between 9am and 5pm" → "0 9-17 * * *"
- "every Tuesday and Thursday at 3pm" → "0 15 * * 2,4"
- "every first day of the month at midnight" → "0 0 1 * *"
- "every 30 minutes during business hours on weekdays" → "*/30 9-17 * * 1-5"

IMPORTANT: Return ONLY the cron expression, no explanation or additional text.
"""
        )

        try:
            response = await llm.generate_text(prompt)
            cron_expr = response.strip()

            # Clean up response (remove quotes, extra whitespace)
            cron_expr = cron_expr.strip("'\"` \n\r")

            # Validate cron expression format
            if self._validate_cron_expression(cron_expr):
                return cron_expr
            else:
                # Try to fix common issues
                fixed_cron = self._attempt_cron_fix(cron_expr)
                if fixed_cron and self._validate_cron_expression(fixed_cron):
                    observability.observe(
                        event_type=observability.SystemEvents.CRON_EXPRESSION_FIXED,
                        level=observability.EventLevel.INFO,
                        data={"original_cron": cron_expr, "fixed_cron": fixed_cron},
                        description="Fixed invalid cron expression from LLM",
                    )
                    return fixed_cron

                # Fallback to default if still invalid
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={"original_text": schedule_text, "invalid_cron": cron_expr},
                    description="LLM generated invalid cron expression",
                )
                return self._fallback_parse_schedule(schedule_text)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"original_text": schedule_text, "error": str(e)},
                description=f"LLM schedule parsing failed: {e}",
            )
            return self._fallback_parse_schedule(schedule_text)

    def _validate_cron_expression(self, cron_expr: str) -> bool:
        """
        Validate cron expression format.

        Args:
            cron_expr: Cron expression to validate

        Returns:
            True if valid, False otherwise
        """
        parts = cron_expr.strip().split()

        if len(parts) != 5:
            return False

        # Basic pattern check for each field
        patterns = [
            r"^(\*|([0-5]?\d)(,([0-5]?\d))*|([0-5]?\d)-([0-5]?\d)|\*/\d+)$",  # minute
            r"^(\*|([01]?\d|2[0-3])(,([01]?\d|2[0-3]))*|([01]?\d|2[0-3])-([01]?\d|2[0-3])|\*/\d+)$",  # hour
            r"^(\*|([12]?\d|3[01])(,([12]?\d|3[01]))*|([12]?\d|3[01])-([12]?\d|3[01])|\*/\d+)$",  # day
            r"^(\*|([1-9]|1[0-2])(,([1-9]|1[0-2]))*|([1-9]|1[0-2])-([1-9]|1[0-2])|\*/\d+)$",  # month
            r"^(\*|[0-6](,[0-6])*|[0-6]-[0-6]|\*/\d+)$",  # day of week
        ]

        for i, part in enumerate(parts):
            if not re.match(patterns[i], part):
                return False

        return True

    async def generate_exclusion_rules(
        self, exclusion_descriptions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Generate dynamic exclusion rules from natural language descriptions.

        Args:
            exclusion_descriptions: List of exclusion descriptions

        Returns:
            List of exclusion rule dicts
        """
        if not exclusion_descriptions:
            return []

        llm = await self._get_llm()
        exclusion_rules = []

        observability.observe(
            event_type=observability.ConversationEvents.EXCLUSION_RULES_GENERATION_STARTED,
            level=observability.EventLevel.INFO,
            data={"exclusion_count": len(exclusion_descriptions)},
            description="Starting exclusion rules generation",
        )

        for description in exclusion_descriptions:
            try:
                if llm:
                    rule = await self._generate_single_exclusion_rule(llm, description)
                    if rule:
                        exclusion_rules.append(rule)
                else:
                    # Fallback exclusion rule generation
                    rule = self._generate_fallback_exclusion_rule(description)
                    if rule:
                        exclusion_rules.append(rule)
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={"description": description, "error": str(e)},
                    description=f"Failed to generate exclusion rule: {e}",
                )

        observability.observe(
            event_type=observability.ConversationEvents.EXCLUSION_RULES_GENERATED,
            level=observability.EventLevel.INFO,
            data={
                "rules_generated": len(exclusion_rules),
                "original_descriptions": len(exclusion_descriptions),
            },
            description="Exclusion rules generation completed",
        )

        return exclusion_rules

    async def _generate_single_exclusion_rule(
        self, llm: LLM, description: str
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a single exclusion rule from description.

        Args:
            llm: LLM instance
            description: Exclusion description

        Returns:
            Exclusion rule dict or None
        """
        # SECURITY: Sanitize input to prevent prompt injection
        try:
            sanitized_description = SchedulerInputValidator.sanitize_schedule_text(description)
        except ValueError as e:
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"description": description[:100], "error": str(e)},
                description=f"Exclusion description validation failed: {e}",
            )
            return {"type": "unknown", "pattern": "", "description": "Invalid exclusion"}

        safe_description = (
            sanitized_description[:200]
            if len(sanitized_description) > 200
            else sanitized_description
        )

        prompt_template = """
Convert the following exclusion description into a rule that represents when to EXCLUDE execution.

Exclusion: {description}
(Input has been sanitized for security)"""

        prompt = (
            prompt_template.format(description=safe_description)
            + """

Return a JSON object with:
- "type": "cron" or "complex_date"
- "pattern": the cron expression (for type="cron") OR a complex date pattern (for type="complex_date")
- "description": human-readable description of the exclusion

For complex date patterns that can't be expressed as simple cron, use type="complex_date" with a structured pattern.

Examples:
- "except weekends" → {{"type": "cron", "pattern": "* * * * 0,6",
  "description": "Exclude weekends (Saturday and Sunday)"}}
- "not during lunch hour" → {{"type": "cron", "pattern": "* 12 * * *", "description": "Exclude 12pm hour"}}
- "except holidays" → {{"type": "cron", "pattern": "* * 1,25 12 *", "description": "Exclude Christmas and New Year"}}
- "except the last Friday of each month" → {{"type": "complex_date", "pattern": "last_friday_of_month",
  "description": "Exclude the last Friday of each month"}}
- "except the first Monday of the month" → {{"type": "complex_date", "pattern": "first_monday_of_month",
  "description": "Exclude the first Monday of each month"}}
- "except every 3rd Tuesday" → {{"type": "complex_date", "pattern": "nth_weekday:3:tuesday",
  "description": "Exclude every 3rd Tuesday of the month"}}
- "außer am letzten Freitag des Monats" → {{"type": "complex_date", "pattern": "last_friday_of_month",
  "description": "Exclude the last Friday of each month"}}
- "sauf le premier lundi du mois" → {{"type": "complex_date", "pattern": "first_monday_of_month",
  "description": "Exclude the first Monday of each month"}}

Complex date patterns should use these structured formats:
- "first_DAY_of_month" - First occurrence of DAY in month
- "last_DAY_of_month" - Last occurrence of DAY in month
- "nth_weekday:N:DAY" - Nth occurrence of DAY in month (N=1-5)
- "nth_day:N" - Nth day of month
- "last_day_minus:N" - N days before end of month

Return only valid JSON, no explanation.
"""
        )

        response = None
        try:
            response = await llm.generate_text(prompt)

            # Try to parse JSON response
            import json

            rule_data = json.loads(response.strip())

            # Validate required fields
            if all(key in rule_data for key in ["type", "pattern", "description"]):
                # Validate based on type
                if rule_data["type"] == "cron":
                    # Validate cron pattern
                    if self._validate_cron_expression(rule_data["pattern"]):
                        return rule_data
                elif rule_data["type"] == "complex_date":
                    # Validate complex date pattern format
                    if self._validate_complex_date_pattern(rule_data["pattern"]):
                        return rule_data

            return None

        except (json.JSONDecodeError, KeyError) as e:
            observability.observe(
                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "description": description,
                    "response": response[:200] if response is not None else "No response",
                    "error": str(e),
                },
                description=f"Failed to parse exclusion rule JSON from LLM response: {e}",
            )
            return None

    async def convert_timezone_cron(self, cron_expr: str, from_tz: str, to_tz: str) -> str:
        """
        Convert cron expression from one timezone to another.

        Args:
            cron_expr: Original cron expression
            from_tz: Source timezone
            to_tz: Target timezone

        Returns:
            Converted cron expression
        """
        try:
            from_timezone = pytz.timezone(from_tz)
            to_timezone = pytz.timezone(to_tz)

            # Parse cron expression
            parts = cron_expr.split()
            if len(parts) != 5:
                return cron_expr  # Invalid format, return as-is

            minute, hour, day, month, dow = parts

            # Only convert if hour is specific (not * or ranges)
            if hour.isdigit():
                # Create a sample datetime in the from timezone
                sample_time = datetime.now(from_timezone).replace(
                    hour=int(hour), minute=int(minute) if minute.isdigit() else 0
                )

                # Convert to target timezone
                converted_time = sample_time.astimezone(to_timezone)

                # Update cron expression
                parts[0] = str(converted_time.minute) if minute.isdigit() else minute
                parts[1] = str(converted_time.hour)

                converted_cron = " ".join(parts)

                observability.observe(
                    event_type=observability.SystemEvents.CRON_TIMEZONE_CONVERTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "original_cron": cron_expr,
                        "converted_cron": converted_cron,
                        "from_timezone": from_tz,
                        "to_timezone": to_tz,
                    },
                    description="Cron expression timezone converted",
                )

                return converted_cron

            return cron_expr  # No conversion needed

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "cron_expression": cron_expr,
                    "from_timezone": from_tz,
                    "to_timezone": to_tz,
                    "error": str(e),
                },
                description=f"Cron timezone conversion failed: {e}",
            )
            return cron_expr  # Return original on error

    def _attempt_cron_fix(self, cron_expr: str) -> Optional[str]:
        """
        Attempt to fix common cron expression issues.

        Args:
            cron_expr: Potentially invalid cron expression

        Returns:
            Fixed cron expression or None if unfixable
        """
        try:
            # Remove extra spaces and normalize
            normalized = " ".join(cron_expr.split())

            # Common fixes
            fixes = [
                # Fix 6-field format (seconds included)
                lambda x: " ".join(x.split()[1:]) if len(x.split()) == 6 else x,
                # Fix quoted expressions
                lambda x: x.strip("'\""),
                # Fix common typos
                lambda x: x.replace("*/", "*/").replace(" /", "/"),
                # Fix range issues
                lambda x: x.replace("1-7", "0-6").replace("7", "0") if x.split()[-1:] else x,
            ]

            fixed = normalized
            for fix in fixes:
                fixed = fix(fixed)
                if self._validate_cron_expression(fixed):
                    return fixed

            return None

        except Exception:
            return None

    def _fallback_parse_schedule(self, schedule_text: str) -> str:
        """
        Fallback schedule parsing without LLM.

        Args:
            schedule_text: Natural language schedule description

        Returns:
            Basic cron expression
        """
        schedule_lower = schedule_text.lower().strip()

        # Very basic fallback patterns
        fallback_patterns = {
            "every minute": "* * * * *",
            "every hour": "0 * * * *",
            "every day": "0 0 * * *",
            "daily": "0 0 * * *",
            "every week": "0 0 * * 0",
            "weekly": "0 0 * * 0",
            "every month": "0 0 1 * *",
            "monthly": "0 0 1 * *",
        }

        # Check for exact matches
        for pattern, cron in fallback_patterns.items():
            if pattern in schedule_lower:
                return cron

        # Extract time if present
        time_match = re.search(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", schedule_lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            am_pm = time_match.group(3)

            if am_pm:
                if am_pm == "pm" and hour != 12:
                    hour += 12
                elif am_pm == "am" and hour == 12:
                    hour = 0

            # Check for day specification
            if "daily" in schedule_lower or "every day" in schedule_lower:
                return f"{minute} {hour} * * *"
            elif "monday" in schedule_lower:
                return f"{minute} {hour} * * 1"
            elif "tuesday" in schedule_lower:
                return f"{minute} {hour} * * 2"
            elif "wednesday" in schedule_lower:
                return f"{minute} {hour} * * 3"
            elif "thursday" in schedule_lower:
                return f"{minute} {hour} * * 4"
            elif "friday" in schedule_lower:
                return f"{minute} {hour} * * 5"
            elif "saturday" in schedule_lower:
                return f"{minute} {hour} * * 6"
            elif "sunday" in schedule_lower:
                return f"{minute} {hour} * * 0"
            else:
                return f"{minute} {hour} * * *"  # Default to daily

        # Ultimate fallback - daily at 9 AM
        observability.observe(
            event_type=observability.ErrorEvents.WARNING,
            level=observability.EventLevel.WARNING,
            data={"original_text": schedule_text},
            description="Using ultimate fallback schedule (daily at 9 AM)",
        )
        return "0 9 * * *"

    def _generate_fallback_exclusion_rule(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Generate fallback exclusion rule without LLM.

        Args:
            description: Exclusion description

        Returns:
            Exclusion rule dict or None
        """
        description_lower = description.lower().strip()

        # Common exclusion patterns
        exclusion_patterns = {
            "weekends": {
                "type": "cron",
                "pattern": "* * * * 0,6",
                "description": "Exclude weekends (Saturday and Sunday)",
            },
            "weekdays": {
                "type": "cron",
                "pattern": "* * * * 1-5",
                "description": "Exclude weekdays (Monday to Friday)",
            },
            "business hours": {
                "type": "cron",
                "pattern": "* 9-17 * * 1-5",
                "description": "Exclude business hours (9am-5pm weekdays)",
            },
            "night": {
                "type": "cron",
                "pattern": "* 22-6 * * *",
                "description": "Exclude night hours (10pm-6am)",
            },
            "lunch": {
                "type": "cron",
                "pattern": "* 12 * * *",
                "description": "Exclude lunch hour (12pm)",
            },
            "holidays": {
                "type": "cron",
                "pattern": "* * 1,25 12 *",  # Christmas and New Year
                "description": "Exclude major holidays (Dec 1st, 25th)",
            },
        }

        # Check for pattern matches
        for pattern, rule in exclusion_patterns.items():
            if pattern in description_lower:
                return rule

        # If no pattern matched, create a basic rule
        observability.observe(
            event_type=observability.ErrorEvents.WARNING,
            level=observability.EventLevel.WARNING,
            data={"description": description},
            description="Using generic exclusion rule for unrecognized description",
        )

        return {
            "type": "cron",
            "pattern": "* * * * 0,6",  # Default to excluding weekends
            "description": f"Exclude based on: {description}",
        }

    def _validate_complex_date_pattern(self, pattern: str) -> bool:
        """
        Validate complex date pattern format.

        Args:
            pattern: Complex date pattern to validate

        Returns:
            True if valid, False otherwise
        """
        # Valid weekdays for validation
        valid_weekdays = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        pattern_lower = pattern.lower()

        # Check specific pattern formats
        if re.match(r"^first_\w+_of_month$", pattern_lower):
            weekday = pattern_lower[6:-9]  # Extract weekday
            return weekday in valid_weekdays

        elif re.match(r"^last_\w+_of_month$", pattern_lower):
            weekday = pattern_lower[5:-9]  # Extract weekday
            return weekday in valid_weekdays

        elif re.match(r"^nth_weekday:\d+:\w+$", pattern_lower):
            parts = pattern_lower.split(":")
            if len(parts) == 3:
                try:
                    n = int(parts[1])
                    if 1 <= n <= 5 and parts[2] in valid_weekdays:
                        return True
                except ValueError:
                    pass
            return False

        elif re.match(r"^nth_day:\d+$", pattern_lower):
            try:
                day = int(pattern_lower[8:])
                return 1 <= day <= 31
            except ValueError:
                return False

        elif re.match(r"^last_day_minus:\d+$", pattern_lower):
            try:
                days = int(pattern_lower[15:])
                return 0 <= days <= 30
            except ValueError:
                return False

        return False
