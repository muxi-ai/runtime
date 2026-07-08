"""
Unit tests for the formation-level 'proactive' block parser.

Covers inert-when-absent behavior, channel declarations, default channel
resolution rules, heartbeat interval/target/active-hours parsing, and
fail-fast errors on malformed blocks (the formation validator reuses this
parser, so these tests pin load-time validation too).
"""

from datetime import time as dt_time

import pytest

from muxi.runtime.formation.proactive import parse_proactive_config
from muxi.runtime.formation.proactive.config import parse_interval


class TestInertWhenAbsent:
    def test_absent_block_parses_to_none(self):
        assert parse_proactive_config(None) is None

    def test_non_mapping_fails_fast(self):
        with pytest.raises(ValueError, match="'proactive' must be a mapping"):
            parse_proactive_config(["telegram"])

    def test_unknown_key_fails_fast(self):
        with pytest.raises(ValueError, match="unknown 'proactive' key"):
            parse_proactive_config({"chanels": {}})  # typo'd key


class TestChannels:
    def test_channels_parsed(self):
        config = parse_proactive_config(
            {"channels": {"telegram": {"transformer": "telegram-notify"}}}
        )
        assert config.channels["telegram"].transformer == "telegram-notify"

    def test_channel_requires_transformer(self):
        with pytest.raises(ValueError, match="transformer"):
            parse_proactive_config({"channels": {"telegram": {}}})

    def test_reserved_channel_names_rejected(self):
        for reserved in ("last", "preferred", "webhook"):
            with pytest.raises(ValueError, match="reserved"):
                parse_proactive_config({"channels": {reserved: {"transformer": "t"}}})

    def test_invalid_channel_name_rejected(self):
        with pytest.raises(ValueError, match="invalid channel name"):
            parse_proactive_config({"channels": {"bad name!": {"transformer": "t"}}})

    def test_unknown_channel_key_rejected(self):
        with pytest.raises(ValueError, match="unknown 'proactive.channels.telegram' key"):
            parse_proactive_config({"channels": {"telegram": {"transformer": "t", "token": "x"}}})


class TestDefaultChannel:
    def test_default_channel_must_be_declared(self):
        with pytest.raises(ValueError, match="default_channel"):
            parse_proactive_config(
                {"channels": {"a": {"transformer": "t"}}, "default_channel": "b"}
            )

    def test_webhook_default_is_always_valid(self):
        config = parse_proactive_config({"default_channel": "webhook"})
        assert config.default_channel == "webhook"

    def test_declared_default_accepted(self):
        config = parse_proactive_config(
            {"channels": {"a": {"transformer": "t"}}, "default_channel": "a"}
        )
        assert config.default_channel == "a"


class TestIntervalParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("30m", 1800),
            ("every 30m", 1800),
            ("2h", 7200),
            ("45s", 45),
            ("Every 1H", 3600),
        ],
    )
    def test_valid_intervals(self, raw, expected):
        assert parse_interval(raw) == expected

    @pytest.mark.parametrize("raw", ["", "30", "m30", "every", "1d", "-5m", None, 30])
    def test_invalid_intervals_fail_fast(self, raw):
        with pytest.raises(ValueError):
            parse_interval(raw)


class TestHeartbeat:
    def _base(self, **heartbeat):
        return {
            "channels": {"telegram": {"transformer": "t"}},
            "heartbeat": heartbeat,
        }

    def test_defaults(self):
        config = parse_proactive_config(self._base())
        hb = config.heartbeat
        assert hb.enabled is True
        assert hb.interval_seconds == 1800
        assert hb.target == "last"
        assert hb.active_hours is None

    def test_disabled(self):
        config = parse_proactive_config(self._base(enabled=False))
        assert config.heartbeat.enabled is False

    def test_target_must_be_reserved_or_declared(self):
        with pytest.raises(ValueError, match="not a declared channel"):
            parse_proactive_config(self._base(target="slack"))
        config = parse_proactive_config(self._base(target="telegram"))
        assert config.heartbeat.target == "telegram"

    def test_active_hours_parsed(self):
        config = parse_proactive_config(
            self._base(
                active_hours={
                    "start": "09:00",
                    "end": "18:30",
                    "timezone": "Europe/London",
                    "weekends": False,
                }
            )
        )
        hours = config.heartbeat.active_hours
        assert hours.start == dt_time(9, 0)
        assert hours.end == dt_time(18, 30)
        assert hours.timezone == "Europe/London"
        assert hours.weekends is False

    def test_active_hours_user_timezone(self):
        config = parse_proactive_config(
            self._base(active_hours={"start": "08:00", "end": "20:00", "timezone": "user"})
        )
        assert config.heartbeat.active_hours.timezone == "user"

    def test_active_hours_requires_start_and_end(self):
        with pytest.raises(ValueError, match="requires both 'start' and 'end'"):
            parse_proactive_config(self._base(active_hours={"start": "09:00"}))

    def test_active_hours_invalid_time_rejected(self):
        with pytest.raises(ValueError, match="HH:MM"):
            parse_proactive_config(self._base(active_hours={"start": "9am", "end": "18:00"}))

    def test_active_hours_unknown_timezone_rejected(self):
        with pytest.raises(ValueError, match="unknown timezone"):
            parse_proactive_config(
                self._base(
                    active_hours={"start": "09:00", "end": "18:00", "timezone": "Mars/Olympus"}
                )
            )

    def test_unknown_heartbeat_key_rejected(self):
        with pytest.raises(ValueError, match="unknown 'proactive.heartbeat' key"):
            parse_proactive_config(self._base(schedule="every 30m"))

    def test_sop_name_charset_enforced(self):
        with pytest.raises(ValueError, match="sop"):
            parse_proactive_config(self._base(sop="../../etc/passwd"))
