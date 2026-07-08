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


def _write_transformer(formation_dir, name, url=None):
    transformers_dir = formation_dir / "transformers"
    transformers_dir.mkdir(exist_ok=True)
    endpoint = f"endpoint:\n  url: {url}\n" if url else ""
    (transformers_dir / f"{name}.yaml").write_text(
        f"name: {name}\n{endpoint}" 'body:\n  text: "${{ response.content }}"\n'
    )


def _write_trigger(formation_dir, name, frontmatter):
    triggers_dir = formation_dir / "triggers"
    triggers_dir.mkdir(exist_ok=True)
    (triggers_dir / f"{name}.md").write_text(f"---\n{frontmatter}---\nBody: ${{{{ data.x }}}}\n")


class TestTriggerTransformerUrlValidation:
    """Load-time URL resolution for the transformer+webhook composition."""

    def test_url_less_transformer_without_webhook_rejected(self, tmp_path):
        _write_transformer(tmp_path, "shape-only")
        _write_trigger(tmp_path, "notify", "transformer: shape-only\n")
        validator = FormationValidator()
        validator._validate_trigger_transformer_urls(tmp_path / "triggers", tmp_path)
        assert _errors_mentioning(validator, "no 'endpoint.url'")

    def test_composition_with_webhook_is_clean(self, tmp_path):
        _write_transformer(tmp_path, "shape-only")
        _write_trigger(
            tmp_path, "notify", "transformer: shape-only\nwebhook: https://bridge.test/n\n"
        )
        validator = FormationValidator()
        validator._validate_trigger_transformer_urls(tmp_path / "triggers", tmp_path)
        assert validator.result.errors == []

    def test_transformer_with_own_url_is_clean(self, tmp_path):
        _write_transformer(tmp_path, "with-url", url="https://own.test/n")
        _write_trigger(tmp_path, "notify", "transformer: with-url\n")
        validator = FormationValidator()
        validator._validate_trigger_transformer_urls(tmp_path / "triggers", tmp_path)
        assert validator.result.errors == []

    def test_bundled_template_without_webhook_rejected(self, tmp_path):
        # Referencing a bundled dormant template (no URL by design) without
        # supplying a destination fails at load time
        _write_trigger(tmp_path, "slack-out", "transformer: slack\n")
        validator = FormationValidator()
        validator._validate_trigger_transformer_urls(tmp_path / "triggers", tmp_path)
        assert _errors_mentioning(validator, "no 'endpoint.url'")

    def test_bundled_template_with_webhook_is_clean(self, tmp_path):
        _write_trigger(
            tmp_path, "slack-out", "transformer: slack\nwebhook: https://bridge.test/slack\n"
        )
        validator = FormationValidator()
        validator._validate_trigger_transformer_urls(tmp_path / "triggers", tmp_path)
        assert validator.result.errors == []

    def test_triggers_without_transformers_are_ignored(self, tmp_path):
        _write_trigger(tmp_path, "plain", "webhook: https://x.test/h\n")
        (tmp_path / "triggers" / "no-frontmatter.md").write_text("Plain: ${{ data.x }}\n")
        validator = FormationValidator()
        validator._validate_trigger_transformer_urls(tmp_path / "triggers", tmp_path)
        assert validator.result.errors == []

    def test_missing_transformer_file_keeps_request_time_semantics(self, tmp_path):
        # Missing transformer files stay a request-time 400 (unchanged), so
        # the load-time URL check skips them instead of erroring
        _write_trigger(tmp_path, "notify", "transformer: does-not-exist\n")
        validator = FormationValidator()
        validator._validate_trigger_transformer_urls(tmp_path / "triggers", tmp_path)
        assert validator.result.errors == []


class TestProactiveChannelUrlValidation:
    """Load-time URL resolution for proactive channel declarations."""

    def test_url_less_transformer_without_channel_url_rejected(self, tmp_path):
        _write_transformer(tmp_path, "shape-only")
        validator = FormationValidator()
        validator._validate_proactive_channel_transformers(
            tmp_path, {"proactive": {"channels": {"chan-a": {"transformer": "shape-only"}}}}
        )
        assert _errors_mentioning(validator, "proactive.channels.chan-a")

    def test_channel_url_satisfies_url_less_transformer(self, tmp_path):
        _write_transformer(tmp_path, "shape-only")
        validator = FormationValidator()
        validator._validate_proactive_channel_transformers(
            tmp_path,
            {
                "proactive": {
                    "channels": {
                        "chan-a": {"transformer": "shape-only", "url": "https://bridge.test/a"}
                    }
                }
            },
        )
        assert validator.result.errors == []

    def test_bundled_template_channel_with_url_is_clean(self, tmp_path):
        validator = FormationValidator()
        validator._validate_proactive_channel_transformers(
            tmp_path,
            {
                "proactive": {
                    "channels": {"slack": {"transformer": "slack", "url": "https://b.test/s"}}
                }
            },
        )
        assert validator.result.errors == []

    def test_missing_transformer_rejected(self, tmp_path):
        validator = FormationValidator()
        validator._validate_proactive_channel_transformers(
            tmp_path, {"proactive": {"channels": {"chan-a": {"transformer": "missing"}}}}
        )
        assert _errors_mentioning(validator, "not found")

    def test_absent_proactive_block_is_inert(self, tmp_path):
        validator = FormationValidator()
        validator._validate_proactive_channel_transformers(tmp_path, {})
        assert validator.result.errors == []


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
