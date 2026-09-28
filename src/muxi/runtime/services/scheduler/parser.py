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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ...datatypes.intent import IntentDetectionContext, IntentType
from ...services.intent import IntentDetectionService
from ...services.llm import LLM
from ...utils.datetime_utils import utc_now
from ...utils.fastjson import json
from .. import observability
from .validation import SchedulerInputValidator


class ScheduleUnavailableError(Exception):
    """The schedule needs the model, and the model is unavailable: not configured, erroring,
    timing out, or behind an open circuit breaker. The same text may parse later."""


class ScheduleNotUnderstoodError(ValueError):
    """The text is not a schedule the parser can express, or the model's answer was not a
    valid schedule. Retrying the same text will not help; rephrasing may."""


@dataclass(frozen=True)
class ParsedSchedule:
    """A parsed schedule: the cron expression of a recurring job, or the run time (UTC) of a
    one-time job. ``default_time_used`` is True when the text named no time and the parser
    ran the job at the default time."""

    cron_expression: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    default_time_used: bool = False


# The time of day a schedule that names no time runs at, unless the formation sets
# ``scheduler.default_time``
DEFAULT_TIME = "09:00"


# The one day vocabulary for every day-name match in this module: full names, plurals and
# common abbreviations, each matched as a whole word.
_DAY_NAMES = {
    "monday": "1",
    "tuesday": "2",
    "wednesday": "3",
    "thursday": "4",
    "friday": "5",
    "saturday": "6",
    "sunday": "0",
    "mondays": "1",
    "tuesdays": "2",
    "wednesdays": "3",
    "thursdays": "4",
    "fridays": "5",
    "saturdays": "6",
    "sundays": "0",
    "mon": "1",
    "tue": "2",
    "tues": "2",
    "wed": "3",
    "thu": "4",
    "thur": "4",
    "thurs": "4",
    "fri": "5",
    "sat": "6",
    "sun": "0",
}
_DAY_NAME_PATTERN = r"\b(?:" + "|".join(sorted(_DAY_NAMES, key=len, reverse=True)) + r")\b"

# Words that name a time, a date, a window or another frequency. A no-model fallback rule
# refuses text that still holds one of these once its own phrase is removed, because the
# rule would silently ignore it.
_SCHEDULE_WORDS_PATTERN = (
    r"\b(?:today|tonight|tomorrow|every|each|daily|weekly|monthly|yearly|hourly"
    r"|minutes?|hours?|days?|weeks?|months?|years?|weekdays?|weekends?|nights?"
    r"|between|during|from|until|till|through|except|excluding|unless|before|after|starting"
    r"|quarter|half|past|january|february|march|april|may|june|july|august|september"
    r"|october|november|december)\b"
)

# "every minute", "every 15 minutes", "every hour", "every 2 hours", "hourly"
_FALLBACK_INTERVAL_PATTERN = r"\b(?:every\s+(?:(?P<count>\d+)\s+)?(?P<unit>minute|hour)s?|hourly)\b"
# "in 20 minutes", "in 2 hours"
_FALLBACK_RELATIVE_PATTERN = r"\bin\s+(?P<count>\d+)\s+(?P<unit>minute|hour)s?\b"
# "today", "tomorrow"
_FALLBACK_DAY_PATTERN = r"\b(?:today|tomorrow)\b"
# "at" left over once a schedule's phrase is removed: a time in words the patterns do not
# read ("at sunset", "at the end of the day")
_AT_PATTERN = r"\bat\b"


def _without(text: str, match: re.Match) -> str:
    """The text with the match's span replaced by a space."""
    start, end = match.span()
    return text[:start] + " " + text[end:]


def _fallback_or_raise(result, error: Exception):
    """The fallback's result, or ``error`` when the fallback could not parse the text."""
    if result is None:
        raise error
    return result


def parse_clock_time(value: Any) -> Optional[Tuple[int, int]]:
    """
    Read a configured clock time, such as ``scheduler.default_time``.

    Returns:
        (hour, minute) when ``value`` is a string holding exactly one clock time in a form the
        schedule parser reads ("08:30", "8:30am", "9am", "21:15", "21h15"), else None
    """
    return ScheduleParser().read_clock_time(value)


class ScheduleParser:
    """
    Natural language schedule parser for MUXI scheduler.

    Converts human-readable schedule descriptions into cron expressions
    and generates dynamic exclusion rules for complex scheduling needs.
    """

    def __init__(self, cache=None, circuit_breaker=None, default_time: str = DEFAULT_TIME):
        """
        Initialize schedule parser.

        Args:
            cache: Optional SchedulerCache instance for caching results
            circuit_breaker: Optional LLMCircuitBreaker for fault tolerance
            default_time: The clock time a schedule that names no time runs at ("09:00",
                "8:30am")

        Raises:
            ValueError: ``default_time`` is not a clock time
        """
        self.llm = None  # Will be initialized when needed
        self.cache = cache
        self.circuit_breaker = circuit_breaker

        # Common time patterns, most specific first; the first pattern that matches decides.
        # A number never starts after a digit or a colon and must end at a word boundary, so
        # no pattern reads part of a longer one ("30pm" in "3:30pm", "10pm" in "110pm",
        # "5pm" in "12:5pm", "10:30" in "10:305").
        self.time_patterns = {
            # 12-hour format
            r"(?<![\d:])(\d{1,2}):(\d{2})\s*(am|pm)\b": self._parse_12hour_minutes,
            r"(?<![\d:])(\d{1,2})\s*(am|pm)\b": self._parse_12hour,
            # 24-hour format
            r"(?<![\d:])(\d{1,2}):(\d{2})\b": self._parse_24hour,
            r"(?<![\d:])(\d{1,2})h(\d{2})\b": self._parse_24hour,
            # Anything else clock-shaped ("130pm", "10:305", "12:5pm") is not a usable time
            r"(?<![\d:])\d+\s*(?:am|pm)(?![a-z])|(?<![\d:])\d+:\d+|(?<![\d:])\d+h\d+": (
                lambda match: None
            ),
            # Named times
            r"(morning|noon|afternoon|evening|midnight)": self._parse_named_time,
        }

        # Intervals through the day: the whole cron expression
        self.interval_patterns = {
            r"every\s+(\d+)\s+minutes?": lambda m: f"*/{m.group(1)} * * * *",
            r"every\s+(\d+)\s+hours?": lambda m: f"0 */{m.group(1)} * * *",
            r"every\s+hour": lambda m: "0 * * * *",
            r"hourly": lambda m: "0 * * * *",
        }

        # Once on each day named: the day-of-month, month and day-of-week fields. The time is
        # the one the text gives, else the default time.
        self.day_frequency_patterns = {
            r"every\s+(\d+)\s+days?": lambda m: f"*/{m.group(1)} * *",
            r"every\s+day\b": lambda m: "* * *",
            r"\bdaily\b": lambda m: "* * *",
            r"every\s+week\b": lambda m: "* * 1",  # Monday
            r"\bweekly\b": lambda m: "* * 1",
            r"every\s+month\b": lambda m: "1 * *",
            r"\bmonthly\b": lambda m: "1 * *",
        }

        # Day patterns (each key matches only as a whole word)
        self.day_patterns = {
            **_DAY_NAMES,
            "weekdays": "1-5",
            "weekends": "0,6",
            "weekday": "1-5",
            "weekend": "0,6",
            "business days": "1-5",
            "work days": "1-5",
        }

        self.default_time = self.read_clock_time(default_time)
        if self.default_time is None:
            raise ValueError(f"Scheduler default time is not a clock time: {default_time!r}")

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

    async def parse_schedule(self, schedule_text: str, timezone: str = "UTC") -> ParsedSchedule:
        """
        Parse natural language schedule into cron expression or specific datetime.

        Args:
            schedule_text: Natural language schedule description
            timezone: The timezone the schedule is read in

        Returns:
            The cron expression of a recurring job or the run time (UTC) of a one-time job, and
            whether the default time was used because the text named no time

        Raises:
            ScheduleUnavailableError: The schedule needs the model and the model is unavailable.
            ScheduleNotUnderstoodError: The text is not a schedule the parser can express.
        """
        schedule_lower = schedule_text.lower().strip()

        # First, detect if this is a one-time or recurring job
        job_type = await self._detect_job_type(schedule_text)

        if job_type == "one_time":
            datetime_result = await self._parse_specific_datetime(schedule_text, timezone)
            return ParsedSchedule(
                scheduled_for=datetime_result["scheduled_for"],
                default_time_used=datetime_result["default_time_used"],
            )

        # Recurring: pattern matching first for common cases, then the model
        parsed = await self._try_pattern_matching(schedule_lower)
        if parsed:
            return parsed

        cron_expr = await self._llm_parse_schedule(schedule_text, timezone)
        return ParsedSchedule(cron_expression=cron_expr)

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
    ) -> Dict[str, Any]:
        """
        Parse specific datetime for one-time jobs.

        Args:
            schedule_text: Natural language schedule description
            timezone: Target timezone for the schedule

        Returns:
            Dict with job type, scheduled datetime and ``default_time_used``: the model reported
            that the request names no time of day, so the default time was used

        Raises:
            ScheduleUnavailableError: The model is unavailable or its call failed, and the
                fallback cannot parse the text.
            ScheduleNotUnderstoodError: The text was rejected, or the model's answer was not
                a valid date and time and the fallback cannot parse the text.
        """
        llm = await self._get_llm()

        if not llm:
            return _fallback_or_raise(
                self._fallback_parse_datetime(schedule_text, timezone),
                ScheduleUnavailableError("No model is available to parse the date and time"),
            )

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
            raise ScheduleNotUnderstoodError(f"Schedule text was rejected: {e}") from e

        safe_text = sanitized_text[:200] if len(sanitized_text) > 200 else sanitized_text
        default_hour, default_minute = self.default_time
        prompt_template = """Parse this request into a specific date and time.

Request: {request_text}
(Input has been sanitized for security)"""

        prompt = prompt_template.format(request_text=safe_text) + f"""

Current date/time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}
Target timezone: {timezone}

Parse the request and return ONLY a JSON object with this exact format:
{{
    "year": 2025,
    "month": 6,
    "day": 22,
    "hour": 14,
    "minute": 30,
    "timezone": "{timezone}",
    "time_given": true
}}

"time_given" is false when the request names a day ("tomorrow", "next week", "in 3 days") but
no time of day; then use the default time, {default_hour:02d}:{default_minute:02d}. It is true
when the request names a time of day, or an offset in hours or minutes ("in 3 hours", "in 20
minutes"), which fixes the moment.

Examples:
- "tomorrow at 2pm" → tomorrow's date at 14:00
- "next Friday at 9am" → next Friday's date at 09:00
- "on December 25th at noon" → 2025-12-25 at 12:00
- "next week" → the Monday of next week at {default_hour:02d}:{default_minute:02d}, time_given false
- "in 3 days at 3:30pm" → 3 days from now at 15:30
- "in 3 days" → 3 days from now at {default_hour:02d}:{default_minute:02d}, time_given false
- "in 3 hours" → 3 hours from now, time_given true

Return only valid JSON, no explanation.
"""

        try:
            response = await llm.generate_text(prompt)
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"original_text": schedule_text, "error": str(e)},
                description=f"LLM date and time parsing failed: {e}",
            )
            return _fallback_or_raise(
                self._fallback_parse_datetime(schedule_text, timezone),
                ScheduleUnavailableError(f"The model failed to parse the date and time: {e}"),
            )

        try:
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

            # A request that names no time runs at the default time on the date read; the
            # flag is optional, and a missing one keeps the model's time
            time_given = datetime_data.get("time_given", True)
            if not isinstance(time_given, bool):
                raise ValueError("time_given is not a boolean")
            if time_given:
                hour, minute = datetime_data["hour"], datetime_data["minute"]
            else:
                hour, minute = self.default_time

            # Create datetime object
            target_tz = pytz.timezone(datetime_data["timezone"])
            scheduled_datetime = target_tz.localize(
                datetime(
                    year=datetime_data["year"],
                    month=datetime_data["month"],
                    day=datetime_data["day"],
                    hour=hour,
                    minute=minute,
                )
            )

            # Convert to UTC for storage
            scheduled_datetime_utc = scheduled_datetime.astimezone(pytz.UTC)

            return {
                "job_type": "one_time",
                "scheduled_for": scheduled_datetime_utc,
                "timezone": timezone,
                "original_text": schedule_text,
                "default_time_used": not time_given,
            }

        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            observability.observe(
                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "scheduler_parser",
                    "schedule_text": schedule_text,
                    "response": str(response)[:200],
                    "error": str(e),
                    "error_type": "datetime_parsing_failed",
                },
                description=f"Failed to parse specific datetime from LLM response: {e}",
            )
            return _fallback_or_raise(
                self._fallback_parse_datetime(schedule_text, timezone),
                ScheduleNotUnderstoodError(f"The model's date and time was not usable: {e}"),
            )

    def _fallback_parse_datetime(
        self, schedule_text: str, timezone: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a one-time schedule without the model, only when the text fixes the moment
        exactly. Nothing is ever filled in: a missing time or date means no schedule.

        Parsed:
        - "in N minutes" / "in N hours" (N at least 1): now plus that interval.
        - "today at <time>" / "tomorrow at <time>", where <time> is a clock time ("3pm",
          "3:30pm", "15:30", "21h30") or "noon", and the moment is still ahead.

        Refused (None) otherwise, and also when the rest of the text still names a time, a
        day, a date, a window or a frequency the rule would ignore: any digit, a named time
        ("morning", "midnight"), a day name, or a word such as "next week", "every",
        "between" or a month name.

        Args:
            schedule_text: Natural language schedule description
            timezone: Target timezone

        Returns:
            Dict with the one-time schedule, or None when the text is not one of the forms above

        Raises:
            ScheduleNotUnderstoodError: The time found is not a usable clock time ("25:00").
        """
        text = schedule_text.lower().strip()
        tz = pytz.timezone(timezone)
        current_time = utc_now().astimezone(tz)

        relative = re.search(_FALLBACK_RELATIVE_PATTERN, text)
        if relative:
            if self._names_other_time(_without(text, relative)):
                return None
            count = int(relative.group("count"))
            if count < 1:
                return None
            unit = "minutes" if relative.group("unit") == "minute" else "hours"
            scheduled_time = current_time + timedelta(**{unit: count})
        else:
            day = re.search(_FALLBACK_DAY_PATTERN, text)
            if not day:
                return None
            rest = _without(text, day)
            found = self._match_time(rest)
            if not found:
                return None
            time_match, (hour, minute) = found
            if not (re.search(r"\d", time_match.group(0)) or time_match.group(0) == "noon"):
                return None  # "morning", "evening" and the like are not a clock time
            if self._names_other_time(_without(rest, time_match)):
                return None
            date = current_time.date() + timedelta(days=1 if day.group(0) == "tomorrow" else 0)
            scheduled_time = tz.localize(datetime(date.year, date.month, date.day, hour, minute))
            if scheduled_time <= current_time:
                return None

        return {
            "job_type": "one_time",
            "scheduled_for": scheduled_time.astimezone(pytz.UTC),
            "timezone": timezone,
            "original_text": schedule_text,
            "default_time_used": False,
        }

    def _names_other_time(self, text: str) -> bool:
        """Whether the text names a time, day, date, window or frequency: what a fallback rule
        would ignore if it parsed the rest of the text."""
        return bool(
            re.search(r"\d", text)
            or re.search(_SCHEDULE_WORDS_PATTERN, text)
            or self._extract_time_from_text(text)
            or self._extract_day_from_text(text)
        )

    async def _try_pattern_matching(self, schedule_text: str) -> Optional[ParsedSchedule]:
        """
        Try to parse schedule using pattern matching.

        A schedule that runs once on each day it names ("daily", "every monday", "weekly",
        "every 3 days") runs at the time the text gives, else at the default time. An
        interval ("every 15 minutes", "hourly") that also names a time of day is left to the
        model: the two conflict.

        Args:
            schedule_text: Lowercase schedule text

        Returns:
            The schedule, or None if no pattern matched or the text is for the model to read

        Raises:
            ScheduleNotUnderstoodError: The time found is not a usable clock time.
        """
        # Intervals through the day
        for pattern, cron_func in self.interval_patterns.items():
            match = re.search(pattern, schedule_text)
            if match:
                if self._extract_time_from_text(schedule_text):
                    # "every 15 minutes ... at 9am": an interval and a time of day conflict
                    return None
                parts = cron_func(match).split()
                day_spec = self._extract_day_from_text(schedule_text)
                if day_spec:
                    parts[4] = day_spec
                return ParsedSchedule(cron_expression=" ".join(parts))

        # Once a day, week or month, or every N days
        for pattern, days_func in self.day_frequency_patterns.items():
            match = re.search(pattern, schedule_text)
            if match:
                day_of_month, month, day_of_week = days_func(match).split()
                day_of_week = self._extract_day_from_text(schedule_text) or day_of_week
                return self._once_a_day(
                    schedule_text, match, f"{day_of_month} {month} {day_of_week}"
                )

        # Several days (e.g. "every Tuesday and Thursday at 3pm"). Must be checked BEFORE the
        # single-day pattern to avoid partial matches. A day named outside the matched phrase
        # ("every monday or friday") would be dropped, so the model reads that text.
        multi_day_pattern = rf"every\s+((?:{_DAY_NAME_PATTERN}(?:\s*(?:,|and)\s*)?)+)"
        match = re.search(multi_day_pattern, schedule_text)
        if match:
            found_days = re.findall(_DAY_NAME_PATTERN, match.group(1))
            if len(found_days) > 1:
                if self._extract_day_from_text(_without(schedule_text, match)):
                    return None
                day_specs = ",".join(self.day_patterns[d] for d in found_days)
                return self._once_a_day(schedule_text, match, f"* * {day_specs}")

        # One day, or weekdays or weekends
        day_pattern = rf"every\s+({_DAY_NAME_PATTERN}|\bweekdays?\b|\bweekends?\b)"
        match = re.search(day_pattern, schedule_text)
        if match:
            if self._extract_day_from_text(_without(schedule_text, match)):
                return None
            return self._once_a_day(
                schedule_text, match, f"* * {self.day_patterns[match.group(1)]}"
            )

        return None

    def _once_a_day(
        self, schedule_text: str, match: re.Match, days: str
    ) -> Optional[ParsedSchedule]:
        """
        The schedule that runs once on each of ``days`` (the day-of-month, month and
        day-of-week fields), at the time the text gives, else at the default time.

        When the text gives no time, the default is used only if the rest of the text (without
        the matched schedule phrase) names nothing the default would ignore: no digit, no
        schedule word such as "after", "between", "tonight" or "weekdays", and no "at" ("every
        day at sunset"). Otherwise the model reads the text.

        Returns:
            The schedule, or None when the text is for the model to read

        Raises:
            ScheduleNotUnderstoodError: The time found is not a usable clock time.
        """
        time_spec = self._extract_time_from_text(schedule_text)
        if time_spec:
            hour, minute = time_spec
            return ParsedSchedule(cron_expression=f"{minute} {hour} {days}")

        rest = _without(schedule_text, match)
        if (
            re.search(r"\d", rest)
            or re.search(_SCHEDULE_WORDS_PATTERN, rest)
            or re.search(_AT_PATTERN, rest)
        ):
            return None

        hour, minute = self.default_time
        return ParsedSchedule(cron_expression=f"{minute} {hour} {days}", default_time_used=True)

    def _extract_time_from_text(self, text: str) -> Optional[Tuple[int, int]]:
        """
        Extract time (hour, minute) from text.

        Args:
            text: Text to extract time from

        Returns:
            Tuple of (hour, minute), or None when the text holds no time

        Raises:
            ScheduleNotUnderstoodError: The time found is out of range ("25:00", "13pm") or
                not a clock time ("130pm", "10:305"). Dropping it would schedule the job at
                some other time, so the schedule is refused instead.
        """
        found = self._match_time(text)
        return found[1] if found else None

    def read_clock_time(self, value: Any) -> Optional[Tuple[int, int]]:
        """
        Read a string that is exactly one clock time: "08:30", "8:30am", "9am", "21:15",
        "21h15". A named time ("noon"), extra words or an unusable time ("25:00") is not one.

        Returns:
            (hour, minute), or None when ``value`` is not a clock time
        """
        if not isinstance(value, str):
            return None
        text = value.strip().lower()
        try:
            found = self._match_time(text)
        except ScheduleNotUnderstoodError:
            return None
        if not found or found[0].span() != (0, len(text)) or not re.search(r"\d", text):
            return None
        return found[1]

    def _match_time(self, text: str) -> Optional[Tuple[re.Match, Tuple[int, int]]]:
        """
        Find the first time in text, as ``_extract_time_from_text`` does, together with the
        match it was read from.

        Raises:
            ScheduleNotUnderstoodError: The time found is not a usable clock time.
        """
        for pattern, parser in self.time_patterns.items():
            match = re.search(pattern, text)
            if match:
                time_spec = parser(match)
                if time_spec is None:
                    raise ScheduleNotUnderstoodError(
                        f"Schedule time is not a usable clock time: {match.group(0)!r}"
                    )
                return match, time_spec

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
            # Whole words only: "mon" must not match "month", nor "fri" match "friend"
            if re.search(rf"\b{day_text}\b", text, re.IGNORECASE):
                return day_spec

        return None

    def _parse_12hour(self, match) -> Optional[Tuple[int, int]]:
        """Parse 12-hour time format; None when the hour is not 1-12."""
        hour = int(match.group(1))
        am_pm = match.group(2).lower()

        if not 1 <= hour <= 12:
            return None
        if am_pm == "pm" and hour != 12:
            hour += 12
        elif am_pm == "am" and hour == 12:
            hour = 0

        return hour, 0

    def _parse_12hour_minutes(self, match) -> Optional[Tuple[int, int]]:
        """Parse 12-hour time format with minutes; None when the hour is not 1-12 or the
        minute is over 59."""
        hour = int(match.group(1))
        minute = int(match.group(2))
        am_pm = match.group(3).lower()

        if not 1 <= hour <= 12 or minute > 59:
            return None
        if am_pm == "pm" and hour != 12:
            hour += 12
        elif am_pm == "am" and hour == 12:
            hour = 0

        return hour, minute

    def _parse_24hour(self, match) -> Optional[Tuple[int, int]]:
        """Parse 24-hour time format; None when the hour is over 23 or the minute over 59."""
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            return None
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

        Raises:
            ScheduleUnavailableError: The model is unavailable or its call failed, and the
                fallback cannot parse the text.
            ScheduleNotUnderstoodError: The text was rejected, or the model's answer was not
                a valid cron expression and the fallback cannot parse the text.
        """
        llm = await self._get_llm()

        if not llm:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                description="LLM unavailable, using pattern fallback for schedule parsing",
            )
            return _fallback_or_raise(
                self._fallback_parse_schedule(schedule_text),
                ScheduleUnavailableError("No model is available to parse the schedule"),
            )

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
            raise ScheduleNotUnderstoodError(f"Schedule text was rejected: {e}") from e

        safe_text = sanitized_text[:200] if len(sanitized_text) > 200 else sanitized_text
        hour, minute = self.default_time

        # Enhanced prompt with better instructions and examples
        prompt_template = """You are a cron expression generator. Convert natural language schedules to cron format.

SCHEDULE: {schedule_text}
(Input has been sanitized for security)"""

        prompt = prompt_template.format(schedule_text=safe_text) + f"""
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

DEFAULT TIME: a schedule that runs on certain days but names no time of day runs at {hour:02d}:{minute:02d}
(e.g., "every Monday" → "{minute} {hour} * * 1"); "every week" runs on Monday.

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

        try:
            response = await llm.generate_text(prompt)
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"original_text": schedule_text, "error": str(e)},
                description=f"LLM schedule parsing failed: {e}",
            )
            return _fallback_or_raise(
                self._fallback_parse_schedule(schedule_text),
                ScheduleUnavailableError(f"The model failed to parse the schedule: {e}"),
            )

        # Clean up response (remove quotes, extra whitespace)
        cron_expr = str(response).strip().strip("'\"` \n\r")

        # Validate cron expression format
        if self._validate_cron_expression(cron_expr):
            return cron_expr

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

        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"original_text": schedule_text, "invalid_cron": cron_expr},
            description="LLM generated invalid cron expression",
        )
        return _fallback_or_raise(
            self._fallback_parse_schedule(schedule_text),
            ScheduleNotUnderstoodError(f"The model's cron expression is not valid: {cron_expr!r}"),
        )

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

        prompt = prompt_template.format(description=safe_description) + """

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

        response = None
        try:
            response = await llm.generate_text(prompt)

            # Try to parse JSON response
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

    def _fallback_parse_schedule(self, schedule_text: str) -> Optional[str]:
        """
        Parse a recurring schedule without the model, only when the text fixes the schedule
        exactly. Nothing is ever filled in: a missing time or day means no schedule.

        Parsed, when the text holds exactly one of these phrases:
        - "every minute" -> ``* * * * *``; "every N minutes", N dividing 60 (1, 2, 3, 4, 5, 6,
          10, 12, 15, 20, 30) -> ``*/N * * * *``.
        - "every hour" / "hourly" -> ``0 * * * *``; "every N hours", N dividing 24 (1, 2, 3,
          4, 6, 8, 12) -> ``0 */N * * *``.
        Other counts are refused: ``*/45`` would run at :00 and :45, not every 45 minutes.

        Refused (None) otherwise, and also when the rest of the text still names a time, a
        day, a date, a window or another frequency the rule would ignore: any digit, a clock
        or named time ("9am", "morning"), a day name, or a word such as "daily", "every",
        "weekdays", "between", "during", "except" or a month name.

        Args:
            schedule_text: Natural language schedule description

        Returns:
            Cron expression, or None when the text is not one of the forms above
        """
        text = schedule_text.lower().strip()

        match = re.search(_FALLBACK_INTERVAL_PATTERN, text)
        if not match or self._names_other_time(_without(text, match)):
            return None

        count = int(match.group("count") or 1)
        if match.group("unit") == "minute":
            if not 1 <= count < 60 or 60 % count:
                return None
            return "* * * * *" if count == 1 else f"*/{count} * * * *"
        if not 1 <= count < 24 or 24 % count:
            return None
        return "0 * * * *" if count == 1 else f"0 */{count} * * *"

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
