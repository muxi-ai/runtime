"""
Unit tests for slash command parsing and resolution.

Covers the parser's edge cases (paths, bare slashes, multiline arguments,
unicode), the 'commands' config block parser (inert when absent), alias
expansion, SOP resolution, and the built-in registry extension point.
"""

import pytest

from muxi.runtime.formation.commands import (
    BUILTIN_COMMANDS,
    CommandsConfig,
    available_commands,
    parse_commands_config,
    parse_slash_command,
    resolve_command,
)


class TestParser:
    def test_simple_command(self):
        command = parse_slash_command("/help")
        assert command.name == "help"
        assert command.args == ""

    def test_command_with_args(self):
        command = parse_slash_command("/jobs pause 1")
        assert command.name == "jobs"
        assert command.args == "pause 1"

    def test_leading_and_trailing_whitespace(self):
        command = parse_slash_command("  /status  ")
        assert command.name == "status"
        assert command.args == ""

    def test_multiline_args_preserved(self):
        command = parse_slash_command("/report Q3 numbers:\n- revenue\n- churn")
        assert command.name == "report"
        assert command.args == "Q3 numbers:\n- revenue\n- churn"

    def test_hyphen_and_underscore_names(self):
        assert parse_slash_command("/weekly-report").name == "weekly-report"
        assert parse_slash_command("/new_employee").name == "new_employee"

    @pytest.mark.parametrize(
        "message",
        [
            "/",  # bare slash
            "//",  # double slash
            "/usr/bin/env python",  # filesystem path
            "/name!",  # invalid charset
            "hello /world",  # slash mid-message
            "",  # empty
            "   ",  # whitespace only
            "no slash here",
        ],
    )
    def test_non_commands_flow_through(self, message):
        assert parse_slash_command(message) is None

    def test_non_string_input(self):
        assert parse_slash_command(None) is None
        assert parse_slash_command(42) is None


class TestConfigParsing:
    def test_absent_block_is_inert(self):
        assert parse_commands_config(None) is None

    def test_defaults(self):
        config = parse_commands_config({})
        assert config.enabled is True
        assert config.aliases == {}

    def test_disabled(self):
        config = parse_commands_config({"enabled": False})
        assert config.enabled is False

    def test_aliases(self):
        config = parse_commands_config({"aliases": {"tasks": "weekly-report"}})
        assert config.aliases == {"tasks": "weekly-report"}

    def test_unknown_key_fails_fast(self):
        with pytest.raises(ValueError, match="unknown 'commands' key"):
            parse_commands_config({"alias": {}})

    def test_invalid_alias_fails_fast(self):
        with pytest.raises(ValueError, match="invalid command alias"):
            parse_commands_config({"aliases": {"bad alias": "target"}})
        with pytest.raises(ValueError, match="invalid alias target"):
            parse_commands_config({"aliases": {"ok": "bad target"}})


SOPS = {
    "weekly-report": {
        "content": "Generate the weekly report.",
        "description": "Weekly status report",
        "model": "openai/gpt-4o-mini",
        "bypass_approval": True,
    },
    "client-kickoff": {"content": "Run the kickoff checklist.", "description": "Kickoff"},
}


class TestResolution:
    def test_sop_command_resolves(self):
        config = CommandsConfig()
        resolution = resolve_command(parse_slash_command("/weekly-report"), config, SOPS)
        assert resolution.name == "weekly-report"
        assert resolution.message == "Generate the weekly report."
        assert resolution.model == "openai/gpt-4o-mini"
        assert resolution.bypass_approval is True

    def test_args_appended_to_sop_message(self):
        config = CommandsConfig()
        resolution = resolve_command(
            parse_slash_command("/weekly-report include churn"), config, SOPS
        )
        assert resolution.message.startswith("Generate the weekly report.")
        assert "## Command Arguments\ninclude churn" in resolution.message

    def test_alias_expansion(self):
        config = CommandsConfig(aliases={"tasks": "weekly-report"})
        resolution = resolve_command(parse_slash_command("/tasks"), config, SOPS)
        assert resolution.name == "weekly-report"

    def test_unknown_command_returns_none(self):
        config = CommandsConfig()
        assert resolve_command(parse_slash_command("/nope"), config, SOPS) is None

    def test_no_sops_returns_none(self):
        config = CommandsConfig()
        assert resolve_command(parse_slash_command("/weekly-report"), config, None) is None

    def test_builtin_registry_takes_precedence(self):
        def fake_builtin(command):
            from muxi.runtime.formation.commands import CommandResolution

            return CommandResolution(name="weekly-report", message="builtin ran")

        BUILTIN_COMMANDS["weekly-report"] = fake_builtin
        try:
            config = CommandsConfig()
            resolution = resolve_command(parse_slash_command("/weekly-report"), config, SOPS)
            assert resolution.message == "builtin ran"
        finally:
            del BUILTIN_COMMANDS["weekly-report"]


class TestAvailableCommands:
    def test_lists_sops_and_aliases(self):
        config = CommandsConfig(aliases={"tasks": "weekly-report", "dangling": "missing"})
        commands = available_commands(config, SOPS)
        assert commands["weekly-report"] == "Weekly status report"
        assert commands["tasks"] == "Weekly status report"
        assert "client-kickoff" in commands
        # Aliases to unknown targets are not advertised
        assert "dangling" not in commands
