"""
Unit tests for load-time validation of the proactiveness formation blocks.

Pins that the FormationValidator rejects malformed 'proactive'/'commands'
blocks, enforces the heartbeat-requires-scheduler cross-check, validates
the agent 'soul' field, and that formations WITHOUT any of these blocks
validate exactly as before (inert-when-unconfigured).
"""

from muxi.runtime.formation.config.validation import FormationValidator


def _errors_mentioning(validator: FormationValidator, needle: str) -> list:
    return [e for e in validator.result.errors if needle.lower() in e.lower()]


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


class TestInertWhenUnconfigured:
    def test_formation_without_proactive_blocks_validates_clean(self):
        validator = FormationValidator()
        validator._validate_formation_structure(_base_formation())
        assert validator.result.errors == []

    def test_formation_with_valid_blocks_validates_clean(self):
        validator = FormationValidator()
        validator._validate_formation_structure(
            _base_formation(
                proactive={
                    "channels": {"telegram": {"transformer": "telegram-notify"}},
                    "default_channel": "telegram",
                },
                commands={"aliases": {"tasks": "weekly-report"}},
            )
        )
        assert validator.result.errors == []


class TestProactiveBlock:
    def test_malformed_proactive_block_rejected(self):
        validator = FormationValidator()
        validator._validate_formation_structure(
            _base_formation(proactive={"channels": {"telegram": {}}})
        )
        assert _errors_mentioning(validator, "transformer")

    def test_heartbeat_requires_scheduler(self):
        validator = FormationValidator()
        validator._validate_formation_structure(
            _base_formation(
                proactive={
                    "channels": {"telegram": {"transformer": "t"}},
                    "heartbeat": {"enabled": True},
                }
            )
        )
        assert _errors_mentioning(validator, "scheduler")

    def test_heartbeat_with_scheduler_enabled_is_clean(self):
        validator = FormationValidator()
        validator._validate_formation_structure(
            _base_formation(
                scheduler={"enabled": True},
                proactive={
                    "channels": {"telegram": {"transformer": "t"}},
                    "heartbeat": {"enabled": True},
                },
            )
        )
        assert not _errors_mentioning(validator, "heartbeat")

    def test_disabled_heartbeat_does_not_require_scheduler(self):
        validator = FormationValidator()
        validator._validate_formation_structure(
            _base_formation(
                proactive={
                    "channels": {"telegram": {"transformer": "t"}},
                    "heartbeat": {"enabled": False},
                }
            )
        )
        assert validator.result.errors == []


class TestCommandsBlock:
    def test_malformed_commands_block_rejected(self):
        validator = FormationValidator()
        validator._validate_formation_structure(
            _base_formation(commands={"aliases": "not-a-mapping"})
        )
        assert _errors_mentioning(validator, "aliases")


class TestAgentSoulField:
    def test_valid_soul_path_accepted(self):
        validator = FormationValidator()
        validator._validate_agents(
            [{"id": "main", "name": "Main", "description": "d", "soul": "./SOUL.md"}]
        )
        assert not _errors_mentioning(validator, "soul")

    def test_empty_soul_rejected(self):
        validator = FormationValidator()
        validator._validate_agents(
            [{"id": "main", "name": "Main", "description": "d", "soul": "  "}]
        )
        assert _errors_mentioning(validator, "soul")

    def test_non_string_soul_rejected(self):
        validator = FormationValidator()
        validator._validate_agents(
            [{"id": "main", "name": "Main", "description": "d", "soul": ["SOUL.md"]}]
        )
        assert _errors_mentioning(validator, "soul")
