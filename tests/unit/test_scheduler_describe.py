"""A created job is read back in plain words with its timezone.

Recurring jobs are described from their cron expression; a cron whose shape the
describer does not cover is shown verbatim, never described wrongly and never raising.
One-time jobs show the date and time in the job's timezone.
"""

from datetime import datetime

import pytest
import pytz

from muxi.runtime.services.scheduler.describe import describe_schedule


@pytest.mark.parametrize(
    "cron, words",
    [
        ("30 15 * * *", "every day at 3:30pm"),
        ("30 15 * * 2,4", "every Tuesday and Thursday at 3:30pm"),
        ("0 8 * * 1,3,5", "every Monday, Wednesday and Friday at 8am"),
        ("0 9 * * 1-5", "every weekday at 9am"),
        ("0 10 * * 0,6", "every Saturday and Sunday at 10am"),
        ("0 12 * * 0", "every Sunday at 12pm"),
        ("0 0 * * *", "every day at 12am"),
        ("0 9,17 * * *", "every day at 9am and 5pm"),
        ("0 9 1 * *", "on the 1st of every month at 9am"),
        ("0 9 22 * *", "on the 22nd of every month at 9am"),
        ("0 9 13 * *", "on the 13th of every month at 9am"),
        ("0 9 25 12 *", "every year on December 25 at 9am"),
        ("0 0 */3 * *", "every 3 days at 12am"),
        ("* * * * *", "every minute"),
        ("*/15 * * * *", "every 15 minutes"),
        ("0 * * * *", "every hour"),
        ("15 * * * *", "every hour at 15 minutes past"),
        ("0 */2 * * *", "every 2 hours"),
        ("0 9-17 * * *", "every hour from 9am to 5pm"),
        ("*/30 9-17 * * 1-5", "every 30 minutes from 9am to 5:30pm on weekdays"),
        ("*/15 * * * 1", "every 15 minutes on Mondays"),
    ],
)
def test_recurring_job_is_described_in_plain_words(cron, words):
    assert describe_schedule(cron, None, "UTC") == f"{words} (UTC)"


@pytest.mark.parametrize(
    "cron",
    [
        "5 4 * 1 2",  # every Tuesday in January
        "0 9 * 1 *",  # every day in January: a month without a day of the month
        "0 9 1 * 1",  # day of month and day of week together (cron reads either)
        "* 9 * * *",  # every minute of one hour
        "0,30 9 * * *",  # a minute list
        "0 9 * * 7",  # 7 for Sunday, outside what the parser writes
        "0 25 * * *",  # not a time
        "*/15 */2 * * *",
        "@daily",
        "not a cron",
        "",
    ],
)
def test_unexpected_cron_is_shown_verbatim(cron):
    assert describe_schedule(cron, None, "UTC") == f'on the cron schedule "{cron}" (UTC)'


def test_one_time_job_is_described_in_its_timezone():
    scheduled_for = pytz.UTC.localize(datetime(2026, 9, 29, 14, 30))
    assert (
        describe_schedule(None, scheduled_for, "Europe/London")
        == "on Tuesday, September 29, 2026 at 3:30pm (Europe/London)"
    )


def test_one_time_job_can_fall_on_the_next_local_day():
    scheduled_for = pytz.UTC.localize(datetime(2026, 12, 31, 23, 0))
    assert (
        describe_schedule(None, scheduled_for, "Asia/Tokyo")
        == "on Friday, January 1, 2027 at 8am (Asia/Tokyo)"
    )
