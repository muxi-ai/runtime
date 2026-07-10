"""
Unit tests for the ``coding:`` block configuration (coding-agent delegation).

Covers the fail-fast load validation matrix: block schema, adapter schema
(both session shapes + the captured-id path), the secrets-placement rule
(``${{ secrets.* }}`` under ``coding.env`` ONLY), bundled template
resolution with formation-local shadowing, the inline escape hatch,
environment-dependent runtime checks (binary presence, workdir roots,
groups existence), and inert-when-unconfigured pinning.
"""

import os
import sys

import pytest

from muxi.runtime.services.coding import (
    AdapterConfig,
    CodingConfigError,
    find_workdir_root,
    list_bundled_adapters,
    parse_coding_config,
    resolve_adapter_template,
    validate_coding_runtime,
)
from muxi.runtime.services.coding.config import parse_duration

# A minimal valid inline adapter (echo-style; command validity is not
# checked by the structural parser).
INLINE = {
    "command": "mytool",
    "args": {
        "base": ["run"],
        "prompt": ["{prompt}"],
        "session": ["--session", "{id}"],
        "model": ["--model", "{model}"],
    },
    "output": "json",
    "parse": {"result": "$.result", "session_id": "$.session_id"},
}


def block(**overrides):
    raw = {"workdirs": ["./ws"], **INLINE}
    raw.update(overrides)
    return raw


# ===================================================================
# Inert when unconfigured (pinned)
# ===================================================================


class TestInert:
    def test_absent_block_parses_to_none(self):
        assert parse_coding_config(None) is None

    def test_formation_without_block_stays_inert(self):
        from muxi.runtime.formation.formation import Formation

        formation = Formation.__new__(Formation)
        formation.config = {"id": "no-coding"}
        formation._coding_config = "sentinel"
        formation._coding_prepared = False
        formation._secret_placeholders = {}
        formation._formation_path = None
        formation._setup_coding()
        assert formation._coding_config is None

    def test_coding_tools_unavailable_without_service(self):
        from types import SimpleNamespace

        from muxi.runtime.formation.agents.coding_dispatch import coding_tools_available

        assert coding_tools_available(SimpleNamespace()) is False
        assert coding_tools_available(SimpleNamespace(delegation_service=None)) is False
        assert coding_tools_available(SimpleNamespace(delegation_service=object())) is True


# ===================================================================
# Block schema
# ===================================================================


class TestBlockSchema:
    def test_valid_inline_block_defaults(self):
        config = parse_coding_config(block())
        assert config.client is None
        assert config.adapter.command == "mytool"
        assert config.cleanup == "delete"
        assert config.timeout_seconds == 1800
        assert config.max_concurrent == 3
        assert config.groups == []
        assert config.extra_args == []
        assert config.env == {}

    def test_not_a_mapping(self):
        with pytest.raises(CodingConfigError, match="must be a mapping"):
            parse_coding_config(["nope"])

    def test_unknown_keys_rejected(self):
        with pytest.raises(CodingConfigError, match="unknown key"):
            parse_coding_config(block(sandbox=True))

    def test_workdirs_required(self):
        raw = block()
        raw.pop("workdirs")
        with pytest.raises(CodingConfigError, match="workdirs is required"):
            parse_coding_config(raw)

    def test_workdirs_must_be_nonempty(self):
        with pytest.raises(CodingConfigError, match="at least one"):
            parse_coding_config(block(workdirs=[]))

    def test_output_enum(self):
        with pytest.raises(CodingConfigError, match="output must be one of"):
            parse_coding_config(block(output="xml"))

    def test_cleanup_enum(self):
        with pytest.raises(CodingConfigError, match="cleanup must be one of"):
            parse_coding_config(block(cleanup="purge"))

    def test_timeout_parsing(self):
        assert parse_coding_config(block(timeout="45s")).timeout_seconds == 45
        assert parse_coding_config(block(timeout="30m")).timeout_seconds == 1800
        assert parse_coding_config(block(timeout="2h")).timeout_seconds == 7200
        with pytest.raises(CodingConfigError, match="duration"):
            parse_coding_config(block(timeout="soon"))

    def test_max_concurrent_validation(self):
        assert parse_coding_config(block(max_concurrent=1)).max_concurrent == 1
        with pytest.raises(CodingConfigError, match="max_concurrent"):
            parse_coding_config(block(max_concurrent=0))
        with pytest.raises(CodingConfigError, match="max_concurrent"):
            parse_coding_config(block(max_concurrent="three"))
        with pytest.raises(CodingConfigError, match="max_concurrent"):
            parse_coding_config(block(max_concurrent=True))

    def test_model_must_be_nonempty(self):
        with pytest.raises(CodingConfigError, match="coding.model"):
            parse_coding_config(block(model="  "))

    def test_model_without_adapter_model_fragment(self):
        raw = block(model="some-model")
        raw["args"] = {"base": ["run"], "prompt": ["{prompt}"]}
        with pytest.raises(CodingConfigError, match="no args.model fragment"):
            parse_coding_config(raw)

    def test_env_must_be_string_map(self):
        with pytest.raises(CodingConfigError, match="coding.env"):
            parse_coding_config(block(env={"KEY": 42}))

    def test_client_and_inline_mutually_exclusive(self):
        with pytest.raises(CodingConfigError, match="mutually exclusive"):
            parse_coding_config(block(client="droid"))

    def test_neither_client_nor_inline(self):
        with pytest.raises(CodingConfigError, match="requires either 'client'"):
            parse_coding_config({"workdirs": ["./ws"]})

    def test_duration_helper(self):
        assert parse_duration("500ms", key="timeout") == 0.5
        assert parse_duration(90, key="timeout") == 90.0
        with pytest.raises(CodingConfigError):
            parse_duration(-1, key="timeout")


# ===================================================================
# Secrets-placement rule (D11)
# ===================================================================


class TestSecretsPlacement:
    def test_secrets_in_env_allowed(self):
        config = parse_coding_config(block(env={"API_KEY": "${{ secrets.API_KEY }}"}))
        assert config.env["API_KEY"] == "${{ secrets.API_KEY }}"

    def test_secrets_in_extra_args_rejected_pointing_at_env(self):
        with pytest.raises(CodingConfigError) as excinfo:
            parse_coding_config(block(extra_args=["--token", "${{ secrets.TOKEN }}"]))
        assert "coding.env" in str(excinfo.value)
        assert "ps" in str(excinfo.value)

    def test_secrets_in_model_rejected(self):
        with pytest.raises(CodingConfigError, match="coding.env"):
            parse_coding_config(block(model="${{ secrets.MODEL }}"))

    def test_secrets_in_inline_adapter_args_rejected(self):
        raw = block()
        raw["args"] = dict(raw["args"], base=["run", "${{ secrets.SNEAKY }}"])
        with pytest.raises(CodingConfigError, match="coding.env"):
            parse_coding_config(raw)

    def test_secrets_in_adapter_template_file_rejected(self, tmp_path):
        adapter_dir = tmp_path / "coding"
        adapter_dir.mkdir()
        (adapter_dir / "sneaky.yaml").write_text(
            "name: sneaky\n"
            "command: mytool\n"
            "args:\n"
            "  base: ['--key', '${{ secrets.KEY }}']\n"
            "  prompt: ['{prompt}']\n"
        )
        with pytest.raises(CodingConfigError, match="coding.env"):
            parse_coding_config(
                {"client": "sneaky", "workdirs": ["./ws"]}, formation_dir=str(tmp_path)
            )


# ===================================================================
# Adapter schema (both session shapes + captured-id path)
# ===================================================================


class TestAdapterSchema:
    def test_missing_command(self):
        raw = block()
        raw.pop("command")
        raw["args"] = {"prompt": ["{prompt}"]}
        with pytest.raises(CodingConfigError, match="requires either 'client'|command"):
            parse_coding_config(raw)

    def test_missing_prompt(self):
        raw = block()
        raw["args"] = {"base": ["run"]}
        with pytest.raises(CodingConfigError, match="args.prompt is required"):
            parse_coding_config(raw)

    def test_prompt_placeholder_required(self):
        raw = block()
        raw["args"] = dict(raw["args"], prompt=["run-it"])
        with pytest.raises(CodingConfigError, match="prompt.*placeholder|placeholder"):
            parse_coding_config(raw)

    def test_prompt_stdin(self):
        raw = block()
        raw["args"] = dict(raw["args"], prompt="stdin")
        assert parse_coding_config(raw).adapter.prompt == "stdin"

    def test_session_and_pair_conflict(self):
        raw = block()
        raw["args"] = dict(raw["args"], session_resume=["--resume", "{id}"])
        with pytest.raises(CodingConfigError, match="not both"):
            parse_coding_config(raw)

    def test_session_new_requires_resume(self):
        raw = block()
        args = dict(raw["args"])
        args.pop("session")
        args["session_new"] = ["--session-id", "{id}"]
        raw["args"] = args
        with pytest.raises(CodingConfigError, match="session_new requires"):
            parse_coding_config(raw)

    def test_session_id_placeholder_required(self):
        raw = block()
        raw["args"] = dict(raw["args"], session=["--session-id"])
        with pytest.raises(CodingConfigError, match="\\{id\\}"):
            parse_coding_config(raw)

    def test_captured_id_adapter_shape(self):
        raw = block()
        args = dict(raw["args"])
        args.pop("session")
        args["session_resume"] = ["--resume", "{id}"]
        raw["args"] = args
        adapter = parse_coding_config(raw).adapter
        assert adapter.captures_session_id is True
        assert adapter.generates_session_id is False
        assert adapter.supports_resume is True

    def test_captured_id_requires_parse_session_id(self):
        raw = block()
        args = dict(raw["args"])
        args.pop("session")
        args["session_resume"] = ["--resume", "{id}"]
        raw["args"] = args
        raw["parse"] = {"result": "$.result"}
        with pytest.raises(CodingConfigError, match="parse.session_id"):
            parse_coding_config(raw)

    def test_captured_id_cannot_use_text_output(self):
        raw = block()
        args = dict(raw["args"])
        args.pop("session")
        args["session_resume"] = ["--resume", "{id}"]
        raw["args"] = args
        raw["output"] = "text"
        raw.pop("parse")
        with pytest.raises(CodingConfigError, match="text"):
            parse_coding_config(raw)

    def test_parse_with_text_output_rejected(self):
        raw = block(output="text")
        with pytest.raises(CodingConfigError, match="parse selectors have no effect"):
            parse_coding_config(raw)

    def test_idempotent_session_generates_id(self):
        adapter = parse_coding_config(block()).adapter
        assert adapter.generates_session_id is True
        assert adapter.captures_session_id is False
        assert adapter.supports_resume is True

    def test_forbidden_extra_args_rejected(self):
        with pytest.raises(CodingConfigError, match="MUXI sets the"):
            parse_coding_config(
                {"client": "droid", "workdirs": ["./ws"], "extra_args": ["--cwd", "/tmp"]}
            )


# ===================================================================
# Template resolution (bundled, shadowing, inline escape hatch)
# ===================================================================


class TestTemplateResolution:
    def test_bundled_templates_ship(self):
        names = list_bundled_adapters()
        assert "claude-code" in names
        assert "droid" in names

    def test_bundled_claude_code_shape(self):
        adapter = resolve_adapter_template("claude-code", None)
        assert adapter.command == "claude"
        assert adapter.prompt == "stdin"
        assert adapter.output == "stream-json"
        assert adapter.session_new == ["--session-id", "{id}"]
        assert adapter.session_resume == ["--resume", "{id}"]
        assert adapter.generates_session_id is True
        assert adapter.parse_result == "$.result"
        assert adapter.parse_session_id == "$.session_id"
        assert "--worktree" in adapter.forbidden_extra_args

    def test_bundled_droid_shape(self):
        adapter = resolve_adapter_template("droid", None)
        assert adapter.command == "droid"
        assert adapter.prompt == ["{prompt}"]
        assert adapter.output == "json"
        # Verified 2026-07-10 against droid 0.169.0: --session-id with a
        # fresh id CREATES the session, so the template uses the single
        # idempotent fragment.
        assert adapter.session == ["--session-id", "{id}"]
        assert adapter.generates_session_id is True
        assert "--cwd" in adapter.forbidden_extra_args

    def test_unknown_client_lists_bundled(self):
        with pytest.raises(CodingConfigError) as excinfo:
            parse_coding_config({"client": "nope", "workdirs": ["./ws"]})
        assert "claude-code" in str(excinfo.value)
        assert "droid" in str(excinfo.value)

    def test_client_name_pattern(self):
        with pytest.raises(CodingConfigError, match="template name"):
            parse_coding_config({"client": "../evil", "workdirs": ["./ws"]})

    def test_formation_local_shadows_bundled(self, tmp_path):
        adapter_dir = tmp_path / "coding"
        adapter_dir.mkdir()
        (adapter_dir / "droid.yaml").write_text(
            "name: droid\n"
            "command: my-droid-wrapper\n"
            "args:\n"
            "  base: ['exec']\n"
            "  prompt: ['{prompt}']\n"
            "output: text\n"
        )
        adapter = resolve_adapter_template("droid", str(tmp_path))
        assert adapter.command == "my-droid-wrapper"
        # Without the local file the bundled template still resolves.
        assert resolve_adapter_template("droid", None).command == "droid"

    def test_template_name_must_match_filename(self, tmp_path):
        adapter_dir = tmp_path / "coding"
        adapter_dir.mkdir()
        (adapter_dir / "alias.yaml").write_text(
            "name: other\ncommand: x\nargs:\n  prompt: ['{prompt}']\n"
        )
        with pytest.raises(CodingConfigError, match="filename requires"):
            resolve_adapter_template("alias", str(tmp_path))

    def test_structural_pass_skips_client_resolution(self):
        config = parse_coding_config(
            {"client": "not-installed-anywhere", "workdirs": ["./ws"]},
            resolve_client=False,
        )
        assert config.adapter is None
        assert config.client == "not-installed-anywhere"


# ===================================================================
# Runtime validation (binary, workdirs, groups)
# ===================================================================


class TestRuntimeValidation:
    def _config(self, tmp_path, **overrides):
        (tmp_path / "ws").mkdir(exist_ok=True)
        raw = block(**overrides)
        raw["command"] = sys.executable  # absolute existing binary
        return parse_coding_config(raw)

    def test_binary_missing_on_path(self, tmp_path):
        raw = block()
        raw["command"] = "definitely-not-a-real-binary-xyz"
        config = parse_coding_config(raw)
        (tmp_path / "ws").mkdir()
        with pytest.raises(CodingConfigError, match="not found on PATH"):
            validate_coding_runtime(config, formation_dir=str(tmp_path))

    def test_absolute_binary_missing(self, tmp_path):
        raw = block()
        raw["command"] = str(tmp_path / "missing-tool")
        config = parse_coding_config(raw)
        (tmp_path / "ws").mkdir()
        with pytest.raises(CodingConfigError, match="not found or not executable"):
            validate_coding_runtime(config, formation_dir=str(tmp_path))

    def test_workdir_root_missing(self, tmp_path):
        config = self._config(tmp_path, workdirs=["./does-not-exist"])
        with pytest.raises(CodingConfigError, match="workdirs root does not exist"):
            validate_coding_runtime(config, formation_dir=str(tmp_path))

    def test_workdir_resolution_relative_to_formation(self, tmp_path):
        config = self._config(tmp_path)
        validate_coding_runtime(config, formation_dir=str(tmp_path))
        assert config.resolved_workdirs == [os.path.realpath(str(tmp_path / "ws"))]

    def test_groups_checked_when_rbac_active(self, tmp_path):
        config = self._config(tmp_path, groups=["engineers"])
        with pytest.raises(CodingConfigError, match="engineers"):
            validate_coding_runtime(config, formation_dir=str(tmp_path), known_groups={"staff"})
        validate_coding_runtime(
            config, formation_dir=str(tmp_path), known_groups={"engineers", "staff"}
        )

    def test_groups_not_checked_when_rbac_inactive(self, tmp_path):
        config = self._config(tmp_path, groups=["engineers"])
        validate_coding_runtime(config, formation_dir=str(tmp_path), known_groups=None)

    def test_find_workdir_root(self, tmp_path):
        (tmp_path / "other").mkdir()
        config = self._config(tmp_path, workdirs=["./ws", "./other"])
        validate_coding_runtime(config, formation_dir=str(tmp_path))
        root, declared = find_workdir_root(config, None)
        assert declared == "./ws"
        root2, declared2 = find_workdir_root(config, "./other")
        assert declared2 == "./other"
        assert root2.endswith("other")
        with pytest.raises(CodingConfigError, match="not a declared"):
            find_workdir_root(config, "/tmp/elsewhere")


# ===================================================================
# AdapterConfig session-shape properties
# ===================================================================


class TestAdapterProperties:
    def test_no_session_support(self):
        adapter = AdapterConfig(command="x", prompt=["{prompt}"])
        assert adapter.generates_session_id is False
        assert adapter.captures_session_id is False
        assert adapter.supports_resume is False
