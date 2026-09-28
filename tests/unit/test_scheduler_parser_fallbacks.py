"""The schedule parser never guesses a schedule.

Without the model, a fallback returns a schedule only when the text fixes it exactly:
an interval ("every minute", "every 15 minutes", "every hour", "hourly", "every 2 hours")
for a recurring job, or "in N minutes/hours" and "today/tomorrow at <clock time>" for a
one-time job, and only when nothing else in the text names a time, day, date, window or
frequency the rule would ignore. It never fills in a time or a day: the midnight,
Sunday-midnight and 09:00 defaults are gone.

When no schedule comes out, the parser raises one of two errors:
ScheduleUnavailableError when the model was needed and was missing or failed (the same
text may parse later), ScheduleNotUnderstoodError when the text was rejected or the
model's answer was not a valid schedule (the user has to rephrase).
"""

from datetime import datetime

import pytest
import pytz

from muxi.runtime.services.scheduler import parser as parser_module
from muxi.runtime.services.scheduler.circuit_breaker import CircuitBreakerError
from muxi.runtime.services.scheduler.parser import (
    ScheduleNotUnderstoodError,
    ScheduleParser,
    ScheduleUnavailableError,
)

# A Monday, 10:00 UTC (11:00 in London)
NOW = pytz.UTC.localize(datetime(2026, 9, 28, 10, 0))


class FakeLLM:
    """Answers every prompt with a fixed reply, or raises a fixed error."""

    def __init__(self, reply: str = "", error: Exception = None):
        self.reply = reply
        self.error = error

    async def generate_text(self, prompt: str) -> str:
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def parser(monkeypatch):
    monkeypatch.setattr(parser_module, "utc_now", lambda: NOW)
    return ScheduleParser()


def with_llm(parser: ScheduleParser, llm) -> ScheduleParser:
    async def get_llm():
        return llm

    parser._get_llm = get_llm
    return parser


def utc(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return pytz.UTC.localize(datetime(2026, month, day, hour, minute))


# Recurring fallback


@pytest.mark.parametrize(
    "text, cron",
    [
        ("every minute", "* * * * *"),
        ("remind me to stretch every minute", "* * * * *"),
        ("every 1 minute", "* * * * *"),
        ("every 15 minutes", "*/15 * * * *"),
        ("every 30 minutes check the queue", "*/30 * * * *"),
        ("every hour", "0 * * * *"),
        ("Drink water HOURLY", "0 * * * *"),
        ("every 2 hours", "0 */2 * * *"),
        ("every 12 hours", "0 */12 * * *"),
    ],
)
def test_recurring_fallback_parses_a_whole_interval(parser, text, cron):
    assert parser._fallback_parse_schedule(text) == cron


@pytest.mark.parametrize(
    "text",
    [
        # Formerly guessed: midnight, Sunday midnight, the 1st at midnight, daily at 09:00
        "every day",
        "daily",
        "every week",
        "weekly",
        "every month",
        "monthly",
        "every monday",
        "remind me to call mom",
        "at 3pm",
        "every day at 9am",
        # Counts that no */N field expresses
        "every 45 minutes",
        "every 7 hours",
        "every 0 minutes",
        "every 60 minutes",
        "every 24 hours",
        # An interval plus something it would ignore
        "every hour on weekdays",
        "every hour on mondays",
        "every hour between 9am and 5pm",
        "every 15 minutes during business hours",
        "every hour in the morning",
        "every hour except lunch",
        "every hour tomorrow",
        "every minute every day",
        "hourly and daily",
        "every hour at quarter past",
        "every hour on the half hour",
        "every hour in december",
        "every hour for 3 days",
        "remind me to take 2 pills every hour",
        # Not English: the fallback reads no other language, so it refuses
        "cada hora",
    ],
)
def test_recurring_fallback_refuses_what_it_cannot_parse_whole(parser, text):
    assert parser._fallback_parse_schedule(text) is None


# One-time fallback


@pytest.mark.parametrize(
    "text, timezone, scheduled_for",
    [
        ("tomorrow at 3pm", "UTC", utc(9, 29, 15)),
        ("remind me tomorrow at 3:30pm to call mom", "UTC", utc(9, 29, 15, 30)),
        ("tomorrow at 15:30", "UTC", utc(9, 29, 15, 30)),
        ("tomorrow at noon", "UTC", utc(9, 29, 12)),
        ("today at 5pm", "UTC", utc(9, 28, 17)),
        ("tomorrow at 9am", "Europe/London", utc(9, 29, 8)),
        ("in 20 minutes", "UTC", utc(9, 28, 10, 20)),
        ("in 1 hour", "UTC", utc(9, 28, 11)),
        ("remind me in 2 hours to stretch", "UTC", utc(9, 28, 12)),
    ],
)
def test_one_time_fallback_parses_a_whole_moment(parser, text, timezone, scheduled_for):
    result = parser._fallback_parse_datetime(text, timezone)
    assert result["job_type"] == "one_time"
    assert result["scheduled_for"] == scheduled_for
    assert result["timezone"] == timezone


@pytest.mark.parametrize(
    "text",
    [
        # Formerly guessed: 09:00 tomorrow, next Monday, the 1st of next month
        "tomorrow",
        "next week",
        "next month",
        "remind me to call mom",
        # Named times are not clock times; midnight tomorrow is ambiguous
        "tomorrow morning",
        "tomorrow evening",
        "tomorrow at midnight",
        # Already past (10:00 now)
        "today at 9am",
        # Something the rule would ignore
        "tomorrow at 3pm and 5pm",
        "tomorrow at 3pm next week",
        "tomorrow at 3pm on friday",
        "in 2 hours tomorrow",
        "in 2 days",
        "in 0 minutes",
        "next friday at 3pm",
        "mañana a las 3pm",
    ],
)
def test_one_time_fallback_refuses_what_it_cannot_parse_whole(parser, text):
    assert parser._fallback_parse_datetime(text, "UTC") is None


def test_one_time_fallback_refuses_an_unusable_clock_time(parser):
    with pytest.raises(ScheduleNotUnderstoodError):
        parser._fallback_parse_datetime("tomorrow at 25:00", "UTC")


# Error types through the model paths


def test_not_understood_is_a_value_error_and_unavailable_is_not():
    assert issubclass(ScheduleNotUnderstoodError, ValueError)
    assert not issubclass(ScheduleUnavailableError, ValueError)


async def test_no_model_and_no_fallback_is_unavailable(parser):
    with pytest.raises(ScheduleUnavailableError):
        await with_llm(parser, None)._llm_parse_schedule("every day", "UTC")


async def test_no_model_uses_the_fallback(parser):
    assert await with_llm(parser, None)._llm_parse_schedule("every minute", "UTC") == "* * * * *"


@pytest.mark.parametrize(
    "error", [RuntimeError("provider down"), TimeoutError(), CircuitBreakerError("open")]
)
async def test_failing_model_is_unavailable(parser, error):
    with pytest.raises(ScheduleUnavailableError):
        await with_llm(parser, FakeLLM(error=error))._llm_parse_schedule("every day", "UTC")


async def test_failing_model_uses_the_fallback(parser):
    llm = FakeLLM(error=RuntimeError("provider down"))
    assert await with_llm(parser, llm)._llm_parse_schedule("every minute", "UTC") == "* * * * *"


async def test_invalid_cron_from_the_model_is_not_understood(parser):
    llm = FakeLLM(reply="I cannot do that")
    with pytest.raises(ScheduleNotUnderstoodError):
        await with_llm(parser, llm)._llm_parse_schedule("every day", "UTC")


async def test_invalid_cron_from_the_model_uses_the_fallback(parser):
    llm = FakeLLM(reply="I cannot do that")
    assert await with_llm(parser, llm)._llm_parse_schedule("every hour", "UTC") == "0 * * * *"


async def test_valid_cron_from_the_model_is_kept(parser):
    llm = FakeLLM(reply="`30 15 * * 2,4`")
    assert await with_llm(parser, llm)._llm_parse_schedule("x", "UTC") == "30 15 * * 2,4"


async def test_rejected_schedule_text_is_not_understood(parser):
    with pytest.raises(ScheduleNotUnderstoodError):
        await with_llm(parser, FakeLLM(reply="0 9 * * *"))._llm_parse_schedule("   ", "UTC")


async def test_one_time_without_model_and_fallback_is_unavailable(parser):
    with pytest.raises(ScheduleUnavailableError):
        await with_llm(parser, None)._parse_specific_datetime("tomorrow", "UTC")


async def test_one_time_without_model_uses_the_fallback(parser):
    result = await with_llm(parser, None)._parse_specific_datetime("tomorrow at 3pm", "UTC")
    assert result["scheduled_for"] == utc(9, 29, 15)


async def test_one_time_with_failing_model_is_unavailable(parser):
    llm = FakeLLM(error=RuntimeError("provider down"))
    with pytest.raises(ScheduleUnavailableError):
        await with_llm(parser, llm)._parse_specific_datetime("next week", "UTC")


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        '{"year": 2026}',
        '{"year": 2026, "month": 13, "day": 1, "hour": 9, "minute": 0, "timezone": "UTC"}',
        '{"year": "x", "month": 1, "day": 1, "hour": 9, "minute": 0, "timezone": "UTC"}',
        '{"year": 2026, "month": 1, "day": 1, "hour": 9, "minute": 0, "timezone": "Mars/Base"}',
    ],
)
async def test_one_time_with_unusable_model_answer_is_not_understood(parser, reply):
    with pytest.raises(ScheduleNotUnderstoodError):
        await with_llm(parser, FakeLLM(reply=reply))._parse_specific_datetime("next week", "UTC")


async def test_one_time_with_unusable_model_answer_uses_the_fallback(parser):
    llm = FakeLLM(reply="not json")
    result = await with_llm(parser, llm)._parse_specific_datetime("in 20 minutes", "UTC")
    assert result["scheduled_for"] == utc(9, 28, 10, 20)


async def test_one_time_with_valid_model_answer_is_kept(parser):
    llm = FakeLLM(
        reply='{"year": 2026, "month": 10, "day": 2, "hour": 14, "minute": 5, "timezone": "UTC"}'
    )
    result = await with_llm(parser, llm)._parse_specific_datetime("friday at 2:05pm", "UTC")
    assert result["scheduled_for"] == utc(10, 2, 14, 5)


async def test_rejected_one_time_text_is_not_understood(parser):
    with pytest.raises(ScheduleNotUnderstoodError):
        await with_llm(parser, FakeLLM(reply="{}"))._parse_specific_datetime("   ", "UTC")
