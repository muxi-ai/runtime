"""The schedule parser's pattern path reads clock times and day names exactly.

Times: a written time keeps its minutes ("3:30pm" is 15:30, not "30pm"), a pattern
never matches the tail of a longer number ("110pm", "10:305"), and a time outside
the clock (hour over 23, 12-hour hour outside 1-12, minute over 59) makes the
pattern path return None so the LLM parser handles the text instead of a cron
with an impossible or silently dropped hour.

Days: a day name counts only as a whole word, in its full form, its plural or a
common abbreviation, in any case, so "month", "friend", "sunset", "wedding" and
"saturated" name no day.
"""

import pytest

from muxi.runtime.services.scheduler.parser import ScheduleParser


@pytest.fixture
def parser():
    return ScheduleParser()


@pytest.mark.parametrize(
    "text, cron",
    [
        ("every day at 3:30pm", "30 15 * * *"),
        ("daily at 9:15am", "15 9 * * *"),
        ("every monday at 10:45am", "45 10 * * 1"),
        ("every day at 3:30 pm", "30 15 * * *"),
        ("daily at 12:15am", "15 0 * * *"),
        ("daily at 12:30pm", "30 12 * * *"),
        ("daily at 12pm", "0 12 * * *"),
        ("daily at 12am", "0 0 * * *"),
        ("daily at 9am", "0 9 * * *"),
        ("daily at 9 pm", "0 21 * * *"),
        ("daily at 15:30", "30 15 * * *"),
        ("daily at 21h30", "30 21 * * *"),
        ("every tuesday and thursday at 3:30pm", "30 15 * * 2,4"),
        ("every day at noon", "0 12 * * *"),
    ],
)
async def test_time_is_read_with_its_minutes(parser, text, cron):
    assert await parser._try_pattern_matching(text) == cron


@pytest.mark.parametrize(
    "text",
    [
        "every day at 25:00",
        "daily at 24:00",
        "daily at 13pm",
        "daily at 0am",
        "daily at 9:75am",
        "daily at 130pm",
        "daily at 110pm",
        "daily at 10:305",
        "every monday at 25:00",
    ],
)
async def test_unusable_time_leaves_the_pattern_path(parser, text):
    assert await parser._try_pattern_matching(text) is None


@pytest.mark.parametrize("text", ["25:00", "13pm", "0am", "9:75am", "130pm", "110pm", "10:305"])
def test_unusable_time_is_not_extracted(parser, text):
    assert parser._extract_time_from_text(text) is None


@pytest.mark.parametrize(
    "text, cron",
    [
        ("monthly at 9am", "0 9 1 * *"),
        ("remind my friend daily at 9am", "0 9 * * *"),
        ("every day at sunset", "0 0 * * *"),
        ("wedding prep daily at 8am", "0 8 * * *"),
        ("saturated inbox check daily at 7am", "0 7 * * *"),
    ],
)
async def test_ordinary_words_pick_no_day(parser, text, cron):
    assert await parser._try_pattern_matching(text) == cron


@pytest.mark.parametrize(
    "text", ["month", "monthly", "friend", "sunset", "wedding", "saturated", "thus", "tuesdayish"]
)
def test_ordinary_words_are_not_days(parser, text):
    assert parser._extract_day_from_text(text) is None


@pytest.mark.parametrize(
    "text, day",
    [
        ("on monday", "1"),
        ("on Mondays", "1"),
        ("MON", "1"),
        ("tue", "2"),
        ("tues", "2"),
        ("tuesdays", "2"),
        ("wed", "3"),
        ("wednesdays", "3"),
        ("thu", "4"),
        ("thur", "4"),
        ("Thurs", "4"),
        ("thursdays", "4"),
        ("fri", "5"),
        ("fridays", "5"),
        ("sat", "6"),
        ("saturdays", "6"),
        ("sun", "0"),
        ("Sundays", "0"),
        ("weekdays", "1-5"),
        ("weekends", "0,6"),
        ("business days", "1-5"),
        ("work days", "1-5"),
    ],
)
def test_day_names_abbreviations_and_plurals_are_days(parser, text, day):
    assert parser._extract_day_from_text(text) == day


@pytest.mark.parametrize(
    "text, cron",
    [
        ("daily at 9am on mondays", "0 9 * * 1"),
        ("daily at 9am on thurs", "0 9 * * 4"),
        ("every day at 9am on weekdays", "0 9 * * 1-5"),
        ("every day at 9am on weekends", "0 9 * * 0,6"),
        ("every weekdays at 9am", "0 9 * * 1-5"),
    ],
)
async def test_day_names_set_the_day_of_week(parser, text, cron):
    assert await parser._try_pattern_matching(text) == cron
