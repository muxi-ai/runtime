"""The scheduler's user-id rule admits email addresses and nothing wider.

A user id is only ever a lookup key for the scheduler (bound as a query
parameter, never interpolated into SQL or a shell), so the rule admits the
characters an email address carries ("@" and "+") on top of letters, digits,
underscore, hyphen and dot. Whitespace, path separators and control
characters are still rejected, as is anything over the length cap. Formation
ids keep the narrower rule.
"""

import pytest

from muxi.runtime.services.scheduler.validation import SchedulerInputValidator


@pytest.mark.parametrize(
    "user_id",
    [
        "ada@example.com",
        "ada+hero@example.com",
        "Ada.Lovelace@Example.co.uk",
        "U024BE7LH",
        "eun_usr_ada",
        "user-42",
        "a" * SchedulerInputValidator.MAX_USER_ID_LENGTH,
    ],
)
def test_user_id_accepted(user_id):
    SchedulerInputValidator.validate_user_id(user_id)


@pytest.mark.parametrize(
    "user_id",
    [
        "ada @example.com",
        "ada\t@example.com",
        "ada/../example.com",
        "ada\\example.com",
        "ada\x00@example.com",
        "ada@example.com\n",
        "ada\x1b@example.com",
        "ada;drop@example.com",
    ],
)
def test_user_id_with_invalid_characters_rejected(user_id):
    with pytest.raises(ValueError, match="invalid characters"):
        SchedulerInputValidator.validate_user_id(user_id)


def test_user_id_over_length_cap_rejected():
    with pytest.raises(ValueError, match="too long"):
        SchedulerInputValidator.validate_user_id(
            "a" * (SchedulerInputValidator.MAX_USER_ID_LENGTH + 1)
        )


def test_formation_id_still_rejects_email_characters():
    with pytest.raises(ValueError, match="invalid characters"):
        SchedulerInputValidator.validate_formation_id("team@example.com")
