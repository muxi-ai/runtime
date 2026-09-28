"""The schedule parser's pattern path reads clock times and day names exactly.

Times: a written time keeps its minutes ("3:30pm" is 15:30, not "30pm"), no pattern
reads part of a longer number ("110pm", "10:305"), and a time that is outside the
clock (hour over 23, 12-hour hour outside 1-12, minute over 59) or is not a clock
time at all raises ScheduleNotUnderstoodError, so no job is created rather than a
cron with an impossible hour or one that runs at some other time. The first time
found is the schedule's; a later clock-like number in the task text is left alone.

Days: a day name counts only as a whole word, in its full form, its plural or a
common abbreviation, in any case, so "month", "friend", "sunset", "wedding" and
"saturated" name no day. The "every <day> at <time>" and "every <day> and <day> at
<time>" patterns read the same vocabulary.
"""

import pytest

from muxi.runtime.services.scheduler.parser import ScheduleNotUnderstoodError, ScheduleParser


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
        ("daily at 9am send me the highlights from 25:00 of the video", "0 9 * * *"),
        ("daily at 09:00 and the 3:1 split", "0 9 * * *"),
        ("daily at 3pm and 10:305", "0 15 * * *"),
        ("daily at 9am and 25:00", "0 9 * * *"),
        ("every day at noon with the 3 amigos", "0 12 * * *"),
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
        "every tuesday and thursday at 25:00",
        "daily at 130pm in the morning",
        "daily at 12:5pm",
        "daily at 10:30pm5",
    ],
)
async def test_unusable_time_refuses_the_schedule(parser, text):
    with pytest.raises(ScheduleNotUnderstoodError):
        await parser._try_pattern_matching(text)


@pytest.mark.parametrize(
    "text", ["25:00", "13pm", "0am", "9:75am", "130pm", "110pm", "10:305", "12:5pm"]
)
def test_unusable_time_is_not_extracted(parser, text):
    with pytest.raises(ScheduleNotUnderstoodError):
        parser._extract_time_from_text(text)


@pytest.mark.parametrize("text", ["every day", "every 15 minutes", "every day at sunset"])
def test_text_without_a_clock_time_has_no_time(parser, text):
    assert parser._extract_time_from_text(text) is None


@pytest.mark.timeout(5)
def test_long_digit_run_is_scanned_in_linear_time(parser):
    assert parser._extract_time_from_text("daily at " + "1" * 200_000) is None


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


@pytest.mark.parametrize(
    "text, cron",
    [
        ("every tues and thurs at 3pm", "0 15 * * 2,4"),
        ("every tuesdays and thursdays at 3pm", "0 15 * * 2,4"),
        ("every mon, wed and fri at 8am", "0 8 * * 1,3,5"),
        ("every sat and sun at 10:30am", "30 10 * * 6,0"),
        ("every tuesday and thursday at 3pm", "0 15 * * 2,4"),
        ("every mondays at 9am", "0 9 * * 1"),
        ("every mon at 9am", "0 9 * * 1"),
        ("every thurs at 5:15pm", "15 17 * * 4"),
        ("every sundays at noon", "0 12 * * 0"),
        ("every weekdays at 9am", "0 9 * * 1-5"),
        ("every weekends at 9am", "0 9 * * 0,6"),
    ],
)
async def test_every_day_patterns_read_the_shared_day_vocabulary(parser, text, cron):
    assert await parser._try_pattern_matching(text) == cron


@pytest.mark.parametrize(
    "text", ["every month at 9am", "every sunny day at 9am", "every monfri at 9am"]
)
async def test_every_day_patterns_match_day_names_as_whole_words(parser, text):
    assert await parser._try_pattern_matching(text) is None
