"""Unit tests for the ``tuning:`` config surface (Self-Improving Formation).

Pins the PRD contract: absent block = defaults on (every formation
self-improves out of the box), ``active: false`` is the off switch,
closed key set with fail-fast validation, booleans rejected where
numbers are expected, and the formation validator delegating to the
service-level parser so the two can never disagree.
"""

import pytest

from muxi.runtime.services.tuning import (
    DEFAULT_INTERVAL_HOURS,
    TuningConfig,
    TuningConfigError,
    parse_tuning_config,
)
from muxi.runtime.services.tuning.service import yaml_declares_file_transport


class TestDefaults:
    def test_absent_block_means_all_defaults_on(self):
        config = parse_tuning_config(None)
        assert config.active is True
        assert config.interval_hours == DEFAULT_INTERVAL_HOURS == 24.0
        assert config.auto_apply is True

    def test_empty_mapping_means_defaults(self):
        assert parse_tuning_config({}) == TuningConfig()

    def test_boolean_shorthand(self):
        assert parse_tuning_config(False).active is False
        assert parse_tuning_config(True) == TuningConfig()


class TestParsing:
    def test_full_block(self):
        config = parse_tuning_config({"active": True, "interval_hours": 6, "auto_apply": False})
        assert config.active is True
        assert config.interval_hours == 6.0
        assert config.auto_apply is False

    def test_fractional_interval(self):
        assert parse_tuning_config({"interval_hours": 0.5}).interval_hours == 0.5

    def test_active_false_is_the_off_switch(self):
        assert parse_tuning_config({"active": False}).active is False


class TestFailFast:
    def test_unknown_key_rejected(self):
        with pytest.raises(TuningConfigError, match="unknown key"):
            parse_tuning_config({"enabled": True})

    def test_non_mapping_rejected(self):
        with pytest.raises(TuningConfigError, match="must be a mapping"):
            parse_tuning_config(["active"])

    def test_boolean_rejected_where_number_expected(self):
        with pytest.raises(TuningConfigError, match="interval_hours must be a number"):
            parse_tuning_config({"interval_hours": True})

    def test_string_interval_rejected(self):
        with pytest.raises(TuningConfigError, match="interval_hours must be a number"):
            parse_tuning_config({"interval_hours": "24"})

    def test_zero_and_negative_interval_rejected(self):
        for value in (0, -1):
            with pytest.raises(TuningConfigError, match="must be positive"):
                parse_tuning_config({"interval_hours": value})

    def test_non_boolean_active_rejected(self):
        with pytest.raises(TuningConfigError, match="active must be a boolean"):
            parse_tuning_config({"active": 1})

    def test_non_boolean_auto_apply_rejected(self):
        with pytest.raises(TuningConfigError, match="auto_apply must be a boolean"):
            parse_tuning_config({"auto_apply": "yes"})


class TestValidatorDelegation:
    def test_formation_validator_reports_tuning_errors(self):
        from muxi.runtime.formation.config.validation import FormationValidator

        validator = FormationValidator()
        validator._validate_tuning_config({"interval_hours": False})
        assert any("Invalid tuning configuration" in error for error in validator.result.errors)

    def test_formation_validator_accepts_valid_block(self):
        from muxi.runtime.formation.config.validation import FormationValidator

        validator = FormationValidator()
        validator._validate_tuning_config({"active": True, "interval_hours": 12})
        assert not validator.result.errors


class TestFileTransportDetection:
    def test_no_logging_config(self):
        assert yaml_declares_file_transport(None) is False
        assert yaml_declares_file_transport({}) is False

    def test_stdout_system_destination_is_not_a_file(self):
        assert yaml_declares_file_transport({"system": {"destination": "stdout"}}) is False

    def test_system_file_destination_detected(self):
        assert (
            yaml_declares_file_transport({"system": {"destination": "/var/log/muxi.jsonl"}}) is True
        )

    def test_conversation_file_stream_detected(self):
        config = {
            "conversation": {
                "enabled": True,
                "streams": [{"transport": "file", "destination": "./events.jsonl"}],
            }
        }
        assert yaml_declares_file_transport(config) is True

    def test_non_file_streams_ignored(self):
        config = {
            "conversation": {
                "enabled": True,
                "streams": [{"transport": "stdout"}, {"transport": "stream", "url": "http://x"}],
            }
        }
        assert yaml_declares_file_transport(config) is False
