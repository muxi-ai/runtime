"""
When a scheduled job runs, in plain words.

Covers the cron shapes the schedule parser produces (a time on every day, on chosen days of
the week, on a day of the month or on a date each year; every N minutes or hours, optionally
within an hour range and on chosen days). Any other cron is shown verbatim rather than
described wrongly.
"""

import re
from datetime import datetime
from typing import List, Optional

import pytz

# Cron day-of-week numbers: 0 is Sunday
_DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
_MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_WEEKDAYS = [1, 2, 3, 4, 5]
_EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]


def describe_schedule(
    cron_expression: Optional[str], scheduled_for: Optional[datetime], timezone: str
) -> str:
    """
    Describe when a job runs, with the timezone its schedule is read in.

    Args:
        cron_expression: The recurring job's cron expression (None for a one-time job)
        scheduled_for: The one-time job's run time; a naive value is read as UTC, as the
            scheduler stores it (None for a recurring job)
        timezone: The timezone the job was created in; a one-time run time is shown in UTC
            when the name is not a known timezone

    Returns:
        "every day at 3:30pm (UTC)", "on Tuesday, September 29, 2026 at 9am (Europe/London)",
        or, for a cron this module does not describe, 'on the cron schedule "5 4 * 1 2" (UTC)'
    """
    if scheduled_for is not None:
        if scheduled_for.tzinfo is None:
            scheduled_for = pytz.UTC.localize(scheduled_for)
        try:
            zone = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            zone, timezone = pytz.UTC, "UTC"
        local = scheduled_for.astimezone(zone)
        when = (
            f"on {_DAY_NAMES[local.isoweekday() % 7]}, {_MONTH_NAMES[local.month - 1]} "
            f"{local.day}, {local.year} at {_clock(local.hour, local.minute)}"
        )
    else:
        when = describe_cron(cron_expression) or f'on the cron schedule "{cron_expression}"'
    return f"{when} ({timezone})"


def describe_cron(cron_expression: str) -> Optional[str]:
    """
    Describe a cron expression in plain words.

    Returns:
        The description, or None when the expression has a shape this module does not describe
    """
    fields = cron_expression.split()
    if len(fields) != 5:
        return None
    minute, hour, day_of_month, month, day_of_week = fields

    minute_value = _number(minute, 0, 59)
    if minute_value is not None and re.fullmatch(r"[0-9]+(?:,[0-9]+)*", hour):
        # One or more fixed times of day
        hours = _values(hour, 0, 23)
        days = _days_on_which(day_of_month, month, day_of_week)
        if hours is None or days is None:
            return None
        return f"{days} at {_join([_clock(h, minute_value) for h in hours])}"

    # Repeating through the day
    if month != "*" or day_of_month != "*":
        return None
    days = _every_or_on(day_of_week)
    if days is None:
        return None
    repeat = _repeat_within_day(minute, hour)
    return f"{repeat}{days}" if repeat else None


def _repeat_within_day(minute: str, hour: str) -> Optional[str]:
    """ "every 15 minutes", "every 2 hours", "every hour from 9am to 5pm" and the like."""
    minute_value = _number(minute, 0, 59)
    minute_step = _step(minute, 60)

    if minute_value is not None:
        past = f" at {minute_value} minutes past" if minute_value else ""
        if hour == "*":
            return "every hour" + past
        hour_step = _step(hour, 24)
        if hour_step is not None:
            return ("every hour" if hour_step == 1 else f"every {hour_step} hours") + past
        repeat, first_minute, last_minute = "every hour", minute_value, minute_value
    elif minute_step is not None or minute == "*":
        step = minute_step or 1
        repeat = "every minute" if step == 1 else f"every {step} minutes"
        if hour == "*":
            return repeat
        first_minute, last_minute = 0, 59 // step * step
    else:
        return None

    hour_range = re.fullmatch(r"([0-9]+)-([0-9]+)", hour)
    if hour_range and int(hour_range.group(1)) < int(hour_range.group(2)) <= 23:
        start = _clock(int(hour_range.group(1)), first_minute)
        return f"{repeat} from {start} to {_clock(int(hour_range.group(2)), last_minute)}"
    return None


def _days_on_which(day_of_month: str, month: str, day_of_week: str) -> Optional[str]:
    """ "every day", "every Tuesday and Thursday", "on the 1st of every month" and the like."""
    if month == "*" and day_of_month == "*":
        days = _values(day_of_week, 0, 6)
        if days is None:
            return None
        if days == _EVERY_DAY:
            return "every day"
        if days == _WEEKDAYS:
            return "every weekday"
        return "every " + _join([_DAY_NAMES[d] for d in _monday_first(days)])
    if day_of_week != "*":
        return None
    day = _number(day_of_month, 1, 31)
    if month == "*":
        if day is not None:
            return f"on the {_ordinal(day)} of every month"
        step = re.fullmatch(r"\*/([0-9]+)", day_of_month)
        if step and 1 <= int(step.group(1)) <= 31:
            # Cron restarts the count on the 1st: */3 runs on the 1st, 4th, ... 31st, then the 1st
            n = int(step.group(1))
            return (
                "every day" if n == 1 else f"every {n} days (counting from the 1st of each month)"
            )
        return None
    month_value = _number(month, 1, 12)
    if day is not None and month_value is not None:
        return f"every year on {_MONTH_NAMES[month_value - 1]} {day}"
    return None


def _every_or_on(day_of_week: str) -> Optional[str]:
    """The day-of-week suffix of a repeating schedule: "", " on weekdays", " on Mondays"."""
    days = _values(day_of_week, 0, 6)
    if days is None:
        return None
    if days == _EVERY_DAY:
        return ""
    if days == _WEEKDAYS:
        return " on weekdays"
    return " on " + _join([_DAY_NAMES[d] + "s" for d in _monday_first(days)])


def _number(field: str, low: int, high: int) -> Optional[int]:
    """A single value in [low, high], or None."""
    if re.fullmatch(r"[0-9]+", field) and low <= int(field) <= high:
        return int(field)
    return None


def _step(field: str, period: int) -> Optional[int]:
    """N of a "*/N" minute or hour field when it runs evenly, every N units: N divides the
    period (60 minutes, 24 hours). Otherwise None: ``*/45`` runs at :00 and :45."""
    match = re.fullmatch(r"\*/([0-9]+)", field)
    if match and 1 <= int(match.group(1)) < period and period % int(match.group(1)) == 0:
        return int(match.group(1))
    return None


def _values(field: str, low: int, high: int) -> Optional[List[int]]:
    """The sorted values of "*", "3", "1,3" or "1-5" style fields within [low, high], or None."""
    if field == "*":
        return list(range(low, high + 1))
    values = set()
    for part in field.split(","):
        match = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", part)
        if not match:
            return None
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if not low <= start <= end <= high:
            return None
        values.update(range(start, end + 1))
    return sorted(values)


def _monday_first(days: List[int]) -> List[int]:
    """Cron day numbers ordered Monday to Sunday."""
    return sorted(days, key=lambda day: (day + 6) % 7)


def _clock(hour: int, minute: int) -> str:
    """ "9am", "3:30pm", "12am" (midnight), "12pm" (noon)."""
    suffix = "am" if hour < 12 else "pm"
    hour_12 = hour % 12 or 12
    return f"{hour_12}{suffix}" if minute == 0 else f"{hour_12}:{minute:02d}{suffix}"


def _ordinal(day: int) -> str:
    """1st, 2nd, 3rd, 4th, 11th, 21st."""
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _join(items: List[str]) -> str:
    """ "a", "a and b", "a, b and c"."""
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
