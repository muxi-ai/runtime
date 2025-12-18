"""
Unit tests for two-tier logging configuration validation.

Tests the new logging architecture:
- logging.system: Infrastructure events (level + destination)
- logging.conversation: User-facing events (enabled + streams)
"""

import pytest
from muxi.formation.config.validation import FormationValidator


class TestLoggingValidation:
    """Test logging configuration validation."""

    def test_valid_full_config(self):
        """Test validation of complete logging config."""
        validator = FormationValidator()
        config = {
            "system": {
                "level": "debug",
                "destination": "stdout"
            },
            "conversation": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "stdout",
                        "level": "info",
                        "format": "jsonl"
                    }
                ]
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors

    def test_valid_minimal_config(self):
        """Test validation with minimal/empty config (uses defaults)."""
        validator = FormationValidator()
        validator._validate_logging_config({})
        assert not validator.result.errors

    def test_valid_system_only(self):
        """Test validation with only system config."""
        validator = FormationValidator()
        config = {
            "system": {
                "level": "warning",
                "destination": "/var/log/muxi-system.log"
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors

    def test_valid_conversation_only(self):
        """Test validation with only conversation config."""
        validator = FormationValidator()
        config = {
            "conversation": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "file",
                        "destination": "/var/log/muxi.jsonl",
                        "level": "info",
                        "format": "jsonl"
                    }
                ]
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors

    def test_invalid_system_level(self):
        """Test validation fails for invalid system level."""
        validator = FormationValidator()
        config = {
            "system": {
                "level": "invalid_level"
            }
        }
        validator._validate_logging_config(config)
        assert any("invalid level" in e.lower() for e in validator.result.errors)

    def test_valid_system_levels(self):
        """Test all valid system levels pass validation."""
        for level in ["debug", "info", "warning", "error"]:
            validator = FormationValidator()
            config = {
                "system": {"level": level}
            }
            validator._validate_logging_config(config)
            assert not validator.result.errors, f"Level '{level}' should be valid"

    def test_invalid_conversation_stream_transport(self):
        """Test validation fails for invalid stream transport."""
        validator = FormationValidator()
        config = {
            "conversation": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "invalid_transport",
                        "level": "info"
                    }
                ]
            }
        }
        validator._validate_logging_config(config)
        assert any("transport" in e.lower() for e in validator.result.errors)

    def test_file_stream_requires_destination(self):
        """Test file transport requires destination."""
        validator = FormationValidator()
        config = {
            "conversation": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "file",
                        "level": "info"
                    }
                ]
            }
        }
        validator._validate_logging_config(config)
        assert any("destination" in e.lower() for e in validator.result.errors)

    def test_trail_stream_requires_auth(self):
        """Test trail transport requires auth configuration."""
        validator = FormationValidator()
        config = {
            "conversation": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "trail",
                        "level": "info"
                    }
                ]
            }
        }
        validator._validate_logging_config(config)
        assert any("auth" in e.lower() for e in validator.result.errors)

    def test_warning_for_empty_streams(self):
        """Test warning is generated for empty streams array."""
        validator = FormationValidator()
        config = {
            "conversation": {
                "enabled": True,
                "streams": []
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors
        assert any("empty" in w.lower() for w in validator.result.warnings)

    def test_invalid_system_not_dict(self):
        """Test validation fails when system is not a dict."""
        validator = FormationValidator()
        config = {
            "system": "invalid"
        }
        validator._validate_logging_config(config)
        assert any("dictionary" in e.lower() for e in validator.result.errors)

    def test_invalid_conversation_not_dict(self):
        """Test validation fails when conversation is not a dict."""
        validator = FormationValidator()
        config = {
            "conversation": "invalid"
        }
        validator._validate_logging_config(config)
        assert any("dictionary" in e.lower() for e in validator.result.errors)

    def test_valid_stream_with_events_filter(self):
        """Test stream with events filter is valid."""
        validator = FormationValidator()
        config = {
            "conversation": {
                "enabled": True,
                "streams": [
                    {
                        "transport": "stdout",
                        "level": "info",
                        "events": ["AGENT_RESPONSE_COMPLETED", "WORKFLOW_STARTED"]
                    }
                ]
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors


class TestLoggingSystemDestination:
    """Test system destination validation."""

    def test_stdout_destination(self):
        """Test stdout is a valid destination."""
        validator = FormationValidator()
        config = {
            "system": {
                "level": "debug",
                "destination": "stdout"
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors

    def test_file_path_destination(self):
        """Test file path is a valid destination."""
        validator = FormationValidator()
        config = {
            "system": {
                "level": "info",
                "destination": "/var/log/muxi/system.log"
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors

    def test_relative_path_destination(self):
        """Test relative path is a valid destination."""
        validator = FormationValidator()
        config = {
            "system": {
                "level": "info",
                "destination": "./logs/system.log"
            }
        }
        validator._validate_logging_config(config)
        assert not validator.result.errors
