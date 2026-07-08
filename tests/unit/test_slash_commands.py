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

    def test_builtin_disable_map(self):
        config = parse_commands_config({"builtin": {"reset": False, "jobs": True}})
        assert config.builtin == {"reset": False, "jobs": True}

    def test_builtin_unknown_name_fails_fast(self):
        with pytest.raises(ValueError, match="unknown built-in command"):
            parse_commands_config({"builtin": {"not-a-builtin": False}})

    def test_builtin_non_bool_fails_fast(self):
        with pytest.raises(ValueError, match="must be a boolean"):
            parse_commands_config({"builtin": {"reset": "no"}})


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
    def test_sop_command_resolves_to_explicit_invocation(self):
        config = CommandsConfig()
        resolution = resolve_command(parse_slash_command("/weekly-report"), config, SOPS)
        assert resolution.name == "weekly-report"
        # Explicit SOP invocation (resolved by the request analyzer's
        # explicit-SOP path), not inlined SOP content
        assert resolution.message == 'Execute the "weekly-report" SOP.'
        assert resolution.model == "openai/gpt-4o-mini"
        assert resolution.bypass_approval is True

    def test_args_appended_to_invocation(self):
        config = CommandsConfig()
        resolution = resolve_command(
            parse_slash_command("/weekly-report include churn"), config, SOPS
        )
        assert resolution.message.startswith('Execute the "weekly-report" SOP.')
        assert "Command arguments:\ninclude churn" in resolution.message

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

    def test_builtin_resolves_with_descriptor(self):
        resolution = resolve_command(parse_slash_command("/help"), CommandsConfig(), SOPS)
        assert resolution.builtin is BUILTIN_COMMANDS["help"]
        assert resolution.name == "help"
        assert resolution.message == ""

    def test_formation_sop_shadows_builtin(self):
        # Formation-author overrides win: an SOP named like a built-in
        # shadows it (deliberate deviation from the PRD's builtin-first
        # sketch, documented in commands.py).
        sops = {"help": {"content": "Custom help.", "description": "Formation help"}}
        resolution = resolve_command(parse_slash_command("/help"), CommandsConfig(), sops)
        assert resolution.builtin is None
        assert resolution.message == 'Execute the "help" SOP.'

    def test_disabled_builtin_is_invisible(self):
        config = CommandsConfig(builtin={"reset": False})
        assert resolve_command(parse_slash_command("/reset"), config, SOPS) is None
        # Other builtins stay enabled by default
        assert resolve_command(parse_slash_command("/help"), config, SOPS) is not None

    def test_alias_to_builtin(self):
        config = CommandsConfig(aliases={"tasks": "jobs"})
        resolution = resolve_command(parse_slash_command("/tasks list"), config, SOPS)
        assert resolution.builtin is BUILTIN_COMMANDS["jobs"]


class TestAvailableCommands:
    def test_lists_sops_and_aliases(self):
        config = CommandsConfig(aliases={"tasks": "weekly-report", "dangling": "missing"})
        commands = available_commands(config, SOPS)
        assert commands["weekly-report"] == "Weekly status report"
        assert commands["tasks"] == "Weekly status report"
        assert "client-kickoff" in commands
        # Aliases to unknown targets are not advertised
        assert "dangling" not in commands

    def test_lists_builtins_unless_disabled(self):
        commands = available_commands(CommandsConfig(), SOPS)
        for name in ("setup", "help", "status", "jobs", "identity", "channels", "preferences"):
            assert name in commands
        disabled = available_commands(CommandsConfig(builtin={"jobs": False}), SOPS)
        assert "jobs" not in disabled

    def test_sop_description_wins_over_builtin(self):
        sops = {"help": {"content": "x", "description": "Formation help"}}
        commands = available_commands(CommandsConfig(), sops)
        assert commands["help"] == "Formation help"
