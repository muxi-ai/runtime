"""A schedule that names no time runs at the formation's default time.

``scheduler.default_time`` (default "09:00") takes the clock forms the schedule parser reads
("08:30", "8:30am", "9am", "21:15"); anything else refuses the formation at load. It is used
only where a schedule names no time:

- recurring, once on each day named: "daily", "every day", "every weekday", "every
  weekend", "every N days", "every monday", "every mon and thu", "weekly" / "every week"
  (Monday), "monthly" / "every month" (the 1st);
- one-time, a date alone ("tomorrow", "next week", "demain"): the model reads the date and
  reports ``"time_given": false``, and the job runs at the default time on that date.

An interval ("every 15 minutes", "hourly") never gets it. An interval that also names a time
of day ("every 15 minutes ... at 9am") conflicts, so the model reads it instead of the
pattern path flattening it to "0 9 * * *". Text that names a time the patterns do not read
("at sunset", "after lunch") goes to the model too. The parser reports when it used the
default, so the reply can say so.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
import pytz

from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.services.scheduler import parser as parser_module
from muxi.runtime.services.scheduler.cache import SchedulerCache
from muxi.runtime.services.scheduler.parser import (
    ParsedSchedule,
    ScheduleNotUnderstoodError,
    ScheduleParser,
    parse_clock_time,
)

# A Monday, 10:00 UTC
NOW = pytz.UTC.localize(datetime(2026, 9, 28, 10, 0))


class FakeLLM:
    """Answers every prompt with a fixed reply and keeps the prompts it was given."""

    def __init__(self, reply: str = ""):
        self.reply = reply
        self.prompts = []

    async def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def parser(monkeypatch):
    monkeypatch.setattr(parser_module, "utc_now", lambda: NOW)
    return ScheduleParser(cache=SchedulerCache(), default_time="8:30am")


def with_llm(parser: ScheduleParser, llm) -> ScheduleParser:
    async def get_llm():
        return llm

    parser._get_llm = get_llm
    return parser


def as_job_type(parser: ScheduleParser, text: str, job_type: str) -> ScheduleParser:
    """Settle the job type up front, as a cached detection would, so no model is asked."""
    parser.cache.cache_job_type(text, job_type)
    return parser


def utc(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return pytz.UTC.localize(datetime(2026, month, day, hour, minute))


def _base_formation(**extra) -> dict:
    config = {
        "schema": "1.0.0",
        "id": "test-formation",
        "description": "Test formation",
        "llm": {"models": [{"text": "openai/gpt-4o-mini"}]},
        "agents": [{"id": "main", "name": "Main", "description": "Main agent"}],
    }
    config.update(extra)
    return config


def _default_time_errors(scheduler: dict) -> list:
    validator = FormationValidator()
    validator._validate_formation_structure(_base_formation(scheduler=scheduler))
    return [e for e in validator.result.errors if "default_time" in e]


# The key


@pytest.mark.parametrize(
    "value, clock",
    [
        ("08:30", (8, 30)),
        ("8:30am", (8, 30)),
        ("9am", (9, 0)),
        ("21:15", (21, 15)),
        ("21h15", (21, 15)),
        (" 9 PM ", (21, 0)),
        ("12am", (0, 0)),
    ],
)
def test_clock_forms_are_read(value, clock):
    assert parse_clock_time(value) == clock
    assert _default_time_errors({"enabled": True, "default_time": value}) == []


@pytest.mark.parametrize(
    "value",
    [
        "25:00",
        "13pm",
        "9:75am",
        "130pm",
        "9",
        "noon",
        "morning",
        "9am tomorrow",
        "at 9am",
        "",
        1275,  # YAML reads an unquoted 21:15 as 1275
        None,
    ],
)
def test_anything_else_refuses_the_formation(value):
    assert parse_clock_time(value) is None
    errors = _default_time_errors({"enabled": True, "default_time": value})
    assert len(errors) == 1
    assert "clock time" in errors[0]


def test_unset_key_is_valid_and_defaults_to_nine():
    assert _default_time_errors({"enabled": True}) == []
    assert ScheduleParser().default_time == (9, 0)


async def test_scheduler_config_route_shows_the_default(serve):
    formation = SimpleNamespace(formation_id="f", config={"scheduler": {"enabled": True}})

    async with serve(formation) as client:
        response = await client.get("/v1/scheduler", headers={"X-Muxi-Admin-Key": "admin-key"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["default_time"] == "09:00"


def test_parser_refuses_a_default_that_is_not_a_clock_time():
    with pytest.raises(ValueError):
        ScheduleParser(default_time="25:00")


# Recurring schedules without a time


@pytest.mark.parametrize(
    "text, cron",
    [
        ("daily", "30 8 * * *"),
        ("every day", "30 8 * * *"),
        ("remind me daily to stretch", "30 8 * * *"),
        ("every weekday", "30 8 * * 1-5"),
        ("every weekdays", "30 8 * * 1-5"),
        ("every weekend", "30 8 * * 0,6"),
        ("every 3 days", "30 8 */3 * *"),
        ("every monday", "30 8 * * 1"),
        ("every monday to water the plants", "30 8 * * 1"),
        ("every tues and thurs", "30 8 * * 2,4"),
        ("every mon, wed and fri", "30 8 * * 1,3,5"),
        ("weekly", "30 8 * * 1"),
        ("every week", "30 8 * * 1"),
        ("weekly on fridays", "30 8 * * 5"),
        ("monthly", "30 8 1 * *"),
        ("every month", "30 8 1 * *"),
    ],
)
async def test_recurring_schedule_without_a_time_runs_at_the_default(parser, text, cron):
    assert await parser._try_pattern_matching(text) == ParsedSchedule(
        cron_expression=cron, default_time_used=True
    )


@pytest.mark.parametrize(
    "text, cron",
    [
        ("every day at 7pm", "0 19 * * *"),
        ("daily at 9:15am", "15 9 * * *"),
        ("every monday at 9am", "0 9 * * 1"),
        ("remind me at 9am every monday", "0 9 * * 1"),
        ("weekly at 5pm", "0 17 * * 1"),
        ("every month at noon", "0 12 1 * *"),
        ("every weekday in the morning", "0 9 * * 1-5"),
    ],
)
async def test_a_given_time_is_kept(parser, text, cron):
    assert await parser._try_pattern_matching(text) == ParsedSchedule(cron_expression=cron)


@pytest.mark.parametrize(
    "text, cron",
    [
        ("every 15 minutes", "*/15 * * * *"),
        ("every 2 hours", "0 */2 * * *"),
        ("every hour", "0 * * * *"),
        ("hourly", "0 * * * *"),
        ("every 30 minutes on weekdays", "*/30 * * * 1-5"),
    ],
)
async def test_intervals_never_get_the_default(parser, text, cron):
    assert await parser._try_pattern_matching(text) == ParsedSchedule(cron_expression=cron)


@pytest.mark.parametrize(
    "text",
    [
        # An interval and a time of day conflict
        "every 15 minutes at 9am",
        "every 15 minutes starting at 9am",
        "every 2 hours from 9am",
        "hourly in the morning",
        # A time the patterns do not read, or something else the default would ignore
        "every day at sunset",
        "every monday after lunch",
        "daily before bed",
        "every day until friday",
        "remind me every monday to review the 3 reports",
        "daily on weekdays",
        # A day outside the matched phrase would be dropped
        "every monday or friday",
        "every monday or friday at 9am",
        "every monday and every friday",
        "every tues and thurs or sat",
    ],
)
async def test_the_model_reads_what_the_patterns_should_not_flatten(parser, text):
    assert await parser._try_pattern_matching(text) is None


async def test_conflicting_schedule_goes_to_the_model(parser):
    text = "every 15 minutes starting at 9am"
    llm = FakeLLM(reply="*/15 9-23 * * *")

    parsed = await with_llm(as_job_type(parser, text, "recurring"), llm).parse_schedule(text)

    assert parsed == ParsedSchedule(cron_expression="*/15 9-23 * * *")
    assert len(llm.prompts) == 1


async def test_conflicting_schedule_with_an_invalid_model_answer_is_not_understood(parser):
    text = "every 15 minutes at 9am"
    parser = with_llm(as_job_type(parser, text, "recurring"), FakeLLM(reply="no idea"))

    with pytest.raises(ScheduleNotUnderstoodError):
        await parser.parse_schedule(text)


async def test_pattern_schedule_reports_the_default_through_parse_schedule(parser):
    text = "remind me every monday to water the plants"
    parser = with_llm(as_job_type(parser, text, "recurring"), None)

    assert await parser.parse_schedule(text) == ParsedSchedule(
        cron_expression="30 8 * * 1", default_time_used=True
    )


async def test_model_schedule_does_not_claim_the_default(parser):
    text = "chaque lundi"
    llm = FakeLLM(reply="30 8 * * 1")

    parsed = await with_llm(as_job_type(parser, text, "recurring"), llm).parse_schedule(text)

    assert parsed == ParsedSchedule(cron_expression="30 8 * * 1")
    # The model is told the default time
    assert "08:30" in llm.prompts[0]
    assert '"30 8 * * 1"' in llm.prompts[0]


# One-time schedules without a time


def model_answer(day: int, hour: int = 0, time_given=None, timezone: str = "UTC") -> str:
    flag = "" if time_given is None else f', "time_given": {time_given}'
    return (
        f'{{"year": 2026, "month": 10, "day": {day}, "hour": {hour}, "minute": 0, '
        f'"timezone": "{timezone}"{flag}}}'
    )


@pytest.mark.parametrize(
    "text, timezone, scheduled_for",
    [
        ("remind me tomorrow to call mom", "UTC", utc(10, 5, 8, 30)),
        ("next week", "Europe/London", utc(10, 5, 7, 30)),
        ("demain", "America/New_York", utc(10, 5, 12, 30)),
    ],
)
async def test_date_without_a_time_runs_at_the_default(parser, text, timezone, scheduled_for):
    llm = FakeLLM(reply=model_answer(5, time_given="false", timezone=timezone))
    parser = with_llm(as_job_type(parser, text, "one_time"), llm)

    assert await parser.parse_schedule(text, timezone) == ParsedSchedule(
        scheduled_for=scheduled_for, default_time_used=True
    )


@pytest.mark.parametrize("time_given", ["true", None])
async def test_date_with_a_time_keeps_it(parser, time_given):
    text = "on monday at 3pm"
    llm = FakeLLM(reply=model_answer(5, hour=15, time_given=time_given))
    parser = with_llm(as_job_type(parser, text, "one_time"), llm)

    assert await parser.parse_schedule(text) == ParsedSchedule(scheduled_for=utc(10, 5, 15))


@pytest.mark.parametrize("time_given", ['"no"', "0", "null"])
async def test_time_given_must_be_a_boolean(parser, time_given):
    text = "tomorrow"
    llm = FakeLLM(reply=model_answer(5, time_given=time_given))
    parser = with_llm(as_job_type(parser, text, "one_time"), llm)

    with pytest.raises(ScheduleNotUnderstoodError):
        await parser.parse_schedule(text)


async def test_one_time_prompt_carries_the_default(parser):
    text = "next week"
    llm = FakeLLM(reply=model_answer(5, time_given="false"))

    await with_llm(as_job_type(parser, text, "one_time"), llm).parse_schedule(text)

    assert '"time_given": true' in llm.prompts[0]
    assert "then use the default time,\n08:30" in llm.prompts[0]
    # A time relative to now fixes the moment: it is a time given
    assert "neither a time of day nor a time\nrelative to now" in llm.prompts[0]
    assert '"in 3 hours" → 3 hours from now, time_given true' in llm.prompts[0]
    assert "the Monday of next week at 08:30, time_given false" in llm.prompts[0]


async def test_one_time_fallback_does_not_claim_the_default(parser):
    text = "tomorrow at 3pm"
    parser = with_llm(as_job_type(parser, text, "one_time"), None)

    assert await parser.parse_schedule(text) == ParsedSchedule(scheduled_for=utc(9, 29, 15))
