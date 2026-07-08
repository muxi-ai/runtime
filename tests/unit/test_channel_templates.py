"""
Unit tests for the bundled channel transformer templates (Phase 2).

Pins that each bundled template (slack, telegram, discord, email) renders a
valid platform payload from a sample substitution context, ships with no
destination URL (dormant/payload-only), and stays inert for formations that
never reference it.
"""

from pathlib import Path

import pytest

from muxi.runtime.formation.background.transformers import (
    BUILTIN_TRANSFORMERS_DIR,
    apply_content_transform,
    build_transformer_variables,
    load_transformer,
    render_template_value,
)

# A formation directory with no transformers/ of its own: every load below
# exercises the builtin fallback exactly as a real formation would.
EMPTY_FORMATION = Path("/nonexistent-formation-dir")


def _render(name, *, response_content, context):
    """Load a bundled template and render its body like delivery does."""
    config = load_transformer(EMPTY_FORMATION, name)
    content = apply_content_transform(response_content, config.content_transform)
    variables = build_transformer_variables(
        response_content=content,
        request_user_id="user-1",
        context=context,
        agent_name="assistant",
    )
    return config, render_template_value(config.body, variables)


class TestDormancy:
    @pytest.mark.parametrize("name", ["slack", "telegram", "discord", "email"])
    def test_no_destination_url_and_no_auth(self, name):
        # Payload formats only: no URLs, no baked-in credentials.
        config = load_transformer(EMPTY_FORMATION, name)
        assert config.url is None
        assert config.auth is None

    def test_unreferenced_names_behave_as_before(self):
        # Inert-when-unreferenced: a formation that does not name a bundled
        # template gets identical behavior to today, including identical
        # errors for unknown transformer names.
        with pytest.raises(ValueError, match="not found"):
            load_transformer(EMPTY_FORMATION, "whatsapp")


class TestSlackTemplate:
    def test_renders_chat_post_message_payload(self):
        _config, body = _render(
            "slack",
            response_content="**Deploy done**",
            context={"channel": "C0ABC123", "thread_ts": "1234.5678"},
        )
        assert body == {
            "channel": "C0ABC123",
            "thread_ts": "1234.5678",
            "text": "**Deploy done**",
        }

    def test_absent_thread_ts_is_dropped(self):
        _config, body = _render(
            "slack",
            response_content="hi",
            context={"channel": "D0XYZ789", "thread_ts": None},
        )
        assert "thread_ts" not in body
        assert body["channel"] == "D0XYZ789"


class TestTelegramTemplate:
    def test_renders_send_message_payload(self):
        _config, body = _render(
            "telegram",
            response_content="Reminder: standup in 15 minutes",
            context={"chat_id": "123456789"},
        )
        assert body == {"chat_id": "123456789", "text": "Reminder: standup in 15 minutes"}

    def test_markdown_stripped_and_length_capped(self):
        config = load_transformer(EMPTY_FORMATION, "telegram")
        assert config.content_transform.format == "text"
        assert config.content_transform.max_length == 4096
        stripped = apply_content_transform("**bold** and `code`", config.content_transform)
        assert stripped == "bold and code"
        capped = apply_content_transform("a" * 5000, config.content_transform)
        assert len(capped) == 4096


class TestDiscordTemplate:
    def test_renders_webhook_content_payload(self):
        _config, body = _render(
            "discord",
            response_content="Build passed",
            context={},
        )
        assert body == {"content": "Build passed"}

    def test_discord_message_limit_enforced(self):
        config = load_transformer(EMPTY_FORMATION, "discord")
        capped = apply_content_transform("x" * 3000, config.content_transform)
        assert len(capped) == 2000


class TestEmailTemplate:
    def test_renders_constructed_message_object(self):
        _config, body = _render(
            "email",
            response_content="Weekly report attached below.",
            context={
                "address": "ran@example.com",
                "from": "Assistant <assistant@example.com>",
                "subject": "Weekly report",
            },
        )
        assert body["from"] == "Assistant <assistant@example.com>"
        assert body["to"] == "ran@example.com"
        assert body["subject"] == "Weekly report"
        assert body["body"] == "Weekly report attached below."
        assert body["headers"]["X-Muxi-Agent"] == "assistant"
        assert body["headers"]["X-Muxi-Timestamp"]  # ISO string, non-empty

    def test_optional_fields_dropped_when_absent(self):
        _config, body = _render(
            "email",
            response_content="hello",
            context={"address": "ran@example.com"},
        )
        assert body["to"] == "ran@example.com"
        assert "from" not in body
        assert "subject" not in body


class TestBundledDirIsPackaged:
    def test_templates_live_inside_the_runtime_package(self):
        # The bundled dir must be under the installed package so wheels and
        # SIF images ship it (package_data includes **/*.yaml).
        package_root = BUILTIN_TRANSFORMERS_DIR
        assert package_root.name == "transformers"
        assert package_root.parent.name == "builtin"
        assert package_root.parent.parent.name == "background"
