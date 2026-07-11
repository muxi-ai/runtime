"""
Unit tests for trigger transformers (response formatting + outbound routing).

Covers trigger frontmatter parsing, transformer config validation (fail-fast
on malformed configs), template variable rendering, content transforms,
parse-spec extraction, and real HTTP delivery (local aiohttp sink server,
no mocks) including form encoding, auth, and fallback-on-failure.
"""

from urllib.parse import parse_qs

import pytest
from aiohttp import web

from muxi.runtime.datatypes.ui import (
    UIProvenance,
    build_action_link_widget,
    build_options_widget,
)
from muxi.runtime.formation.background.transformers import (
    BUILTIN_TRANSFORMERS_DIR,
    ContentTransform,
    TransformerConfig,
    apply_content_transform,
    build_transformer_variables,
    build_ui_variables,
    collect_secret_names,
    deliver_via_transformer,
    extract_parse_values,
    extract_path,
    extract_response_files,
    extract_response_ui,
    load_transformer,
    parse_trigger_frontmatter,
    render_template_string,
    render_template_value,
    resolve_secrets,
    resolve_transformer_url,
)
from muxi.runtime.formation.background.webhook_manager import WebhookManager


class FakeSecretsManager:
    """Minimal async secrets source for rendering tests."""

    def __init__(self, secrets):
        self._secrets = secrets

    async def get_secret(self, name):
        return self._secrets.get(name)


# ---------------------------------------------------------------------------
# Trigger frontmatter
# ---------------------------------------------------------------------------


class TestParseTriggerFrontmatter:
    def test_no_frontmatter_is_byte_identical_passthrough(self):
        content = "Test trigger: ${{ data.message }}\n"
        meta, body = parse_trigger_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_leading_horizontal_rule_without_close_is_not_frontmatter(self):
        content = "---\njust markdown, no closing delimiter"
        meta, body = parse_trigger_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_transformer_frontmatter_parsed_and_stripped(self):
        content = (
            "---\n"
            "transformer: slack\n"
            "parse:\n"
            "  message: $.event.text\n"
            "  user_id: $.event.user\n"
            "  context:\n"
            "    channel: $.event.channel\n"
            "---\n"
            "Respond to: ${{ data.event.text }}"
        )
        meta, body = parse_trigger_frontmatter(content)
        assert meta["transformer"] == "slack"
        assert meta["parse"]["context"]["channel"] == "$.event.channel"
        assert body == "Respond to: ${{ data.event.text }}"

    def test_webhook_frontmatter(self):
        content = "---\nwebhook: https://example.com/hook\n---\nbody"
        meta, body = parse_trigger_frontmatter(content)
        assert meta["webhook"] == "https://example.com/hook"
        assert body == "body"

    def test_webhook_and_transformer_compose(self):
        # Phase 2 composition: transformer defines the payload format, the
        # trigger's webhook URL is the delivery destination.
        content = "---\nwebhook: https://x.test/h\ntransformer: slack\n---\nbody"
        meta, body = parse_trigger_frontmatter(content)
        assert meta["webhook"] == "https://x.test/h"
        assert meta["transformer"] == "slack"
        assert body == "body"

    def test_webhook_only_semantics_unchanged(self):
        meta, _body = parse_trigger_frontmatter("---\nwebhook: https://x.test/h\n---\nbody")
        assert meta["webhook"] == "https://x.test/h"
        assert "transformer" not in meta

    def test_transformer_only_semantics_unchanged(self):
        meta, _body = parse_trigger_frontmatter("---\ntransformer: slack\n---\nbody")
        assert meta["transformer"] == "slack"
        assert "webhook" not in meta

    def test_malformed_yaml_fails_fast(self):
        content = "---\ntransformer: [unclosed\n---\nbody"
        with pytest.raises(ValueError, match="invalid YAML"):
            parse_trigger_frontmatter(content)

    def test_unknown_frontmatter_key_fails_fast(self):
        content = "---\ntransfomer: slack\n---\nbody"  # typo'd key
        with pytest.raises(ValueError, match="unknown trigger frontmatter key"):
            parse_trigger_frontmatter(content)

    def test_non_http_webhook_rejected(self):
        content = "---\nwebhook: ftp://example.com/hook\n---\nbody"
        with pytest.raises(ValueError, match="http"):
            parse_trigger_frontmatter(content)

    def test_invalid_transformer_name_rejected(self):
        content = "---\ntransformer: ../../etc/passwd\n---\nbody"
        with pytest.raises(ValueError, match="transformer"):
            parse_trigger_frontmatter(content)

    def test_invalid_parse_spec_rejected(self):
        content = "---\nparse:\n  context: not-a-mapping\n---\nbody"
        with pytest.raises(ValueError, match="parse.context"):
            parse_trigger_frontmatter(content)


# ---------------------------------------------------------------------------
# Parse-spec extraction
# ---------------------------------------------------------------------------


class TestExtractPath:
    def test_simple_dollar_path(self):
        assert extract_path({"event": {"text": "hi"}}, "$.event.text") == "hi"

    def test_path_without_dollar_prefix(self):
        assert extract_path({"a": {"b": 3}}, "a.b") == 3

    def test_bracket_list_index(self):
        data = {"messages": [{"incident": {"summary": "down"}}]}
        assert extract_path(data, "$.messages[0].incident.summary") == "down"

    def test_dot_numeric_list_index(self):
        assert extract_path({"items": ["a", "b"]}, "items.1") == "b"

    def test_missing_key_returns_none(self):
        assert extract_path({"a": 1}, "$.b.c") is None

    def test_index_out_of_range_returns_none(self):
        assert extract_path({"items": []}, "items.0") is None


class TestExtractParseValues:
    def test_no_spec_returns_empty_defaults(self):
        result = extract_parse_values(None, {"anything": 1})
        assert result == {
            "message": None,
            "user_id": None,
            "files": None,
            "context": {},
            "ui_response": None,
        }

    def test_full_extraction(self):
        spec = {
            "message": "$.event.text",
            "user_id": "$.event.user",
            "context": {"channel": "$.event.channel", "thread_ts": "$.event.thread_ts"},
        }
        data = {"event": {"text": "hello", "user": 42, "channel": "C1"}}
        result = extract_parse_values(spec, data)
        assert result["message"] == "hello"
        assert result["user_id"] == "42"  # coerced to string
        assert result["context"] == {"channel": "C1", "thread_ts": None}
        assert result["ui_response"] is None

    def test_ui_response_callback_decoded(self):
        # A Telegram-style callback_query carrying MUXI button callback
        # data decodes into the {id, index} reply hint.
        spec = {"user_id": "$.callback_query.from.id", "ui_response": "$.callback_query.data"}
        data = {"callback_query": {"from": {"id": 7}, "data": "ui_abc123#1"}}
        result = extract_parse_values(spec, data)
        assert result["ui_response"] == {"id": "ui_abc123", "index": 1}
        assert result["user_id"] == "7"

    def test_ui_response_foreign_callback_is_none(self):
        # Callback payloads MUXI did not produce must not become hints.
        spec = {"ui_response": "$.callback_query.data"}
        data = {"callback_query": {"data": "some-other-bots-callback"}}
        assert extract_parse_values(spec, data)["ui_response"] is None

    def test_ui_response_missing_path_is_none(self):
        spec = {"message": "$.message.text", "ui_response": "$.callback_query.data"}
        data = {"message": {"text": "an ordinary message"}}
        result = extract_parse_values(spec, data)
        assert result["ui_response"] is None
        assert result["message"] == "an ordinary message"

    def test_ui_response_must_be_path_string(self):
        with pytest.raises(ValueError, match="parse.ui_response"):
            extract_parse_values({"ui_response": {"id": "$.x"}}, {})


# ---------------------------------------------------------------------------
# Transformer config validation (fail fast)
# ---------------------------------------------------------------------------

VALID_CONFIG = {
    "name": "slack",
    "version": "1.0",
    "endpoint": {"url": "https://slack.test/api", "method": "POST"},
    "auth": {"type": "bearer", "token": "${{ secrets.SLACK_TOKEN }}"},
    "headers": {"Content-Type": "application/json"},
    "body": {"channel": "${{ context.channel }}", "text": "${{ response.content }}"},
    "content_transform": {"max_length": 100, "truncation_suffix": "..."},
}


class TestTransformerConfigValidation:
    def test_valid_config(self):
        config = TransformerConfig.from_dict(VALID_CONFIG)
        assert config.name == "slack"
        assert config.method == "POST"
        assert config.auth.type == "bearer"
        assert config.content_transform.max_length == 100

    def test_method_defaults_to_post(self):
        config = TransformerConfig.from_dict({"name": "t", "endpoint": {"url": "https://x.test"}})
        assert config.method == "POST"

    def test_non_mapping_config_rejected(self):
        with pytest.raises(ValueError, match="mapping"):
            TransformerConfig.from_dict(["not", "a", "dict"])

    def test_missing_name_rejected(self):
        with pytest.raises(ValueError, match="'name'"):
            TransformerConfig.from_dict({"endpoint": {"url": "https://x.test"}})

    def test_missing_endpoint_yields_url_less_transformer(self):
        # Payload-format-only transformers (bundled channel templates) have
        # no endpoint at all: the referencing trigger/channel supplies the URL.
        config = TransformerConfig.from_dict({"name": "t", "body": {"text": "x"}})
        assert config.url is None
        assert config.method == "POST"

    def test_endpoint_without_url_is_valid(self):
        config = TransformerConfig.from_dict({"name": "t", "endpoint": {"method": "PUT"}})
        assert config.url is None
        assert config.method == "PUT"

    def test_non_mapping_endpoint_rejected(self):
        with pytest.raises(ValueError, match="'endpoint'"):
            TransformerConfig.from_dict({"name": "t", "endpoint": "https://x.test"})

    def test_empty_url_rejected(self):
        with pytest.raises(ValueError, match="'endpoint.url'"):
            TransformerConfig.from_dict({"name": "t", "endpoint": {"url": "  "}})

    def test_invalid_method_rejected(self):
        with pytest.raises(ValueError, match="'endpoint.method'"):
            TransformerConfig.from_dict(
                {"name": "t", "endpoint": {"url": "https://x.test", "method": "TELEPORT"}}
            )

    def test_unknown_auth_type_rejected(self):
        with pytest.raises(ValueError, match="'auth.type'"):
            TransformerConfig.from_dict(
                {"name": "t", "endpoint": {"url": "https://x.test"}, "auth": {"type": "oauth2"}}
            )

    def test_bearer_requires_token(self):
        with pytest.raises(ValueError, match="'auth.token'"):
            TransformerConfig.from_dict(
                {"name": "t", "endpoint": {"url": "https://x.test"}, "auth": {"type": "bearer"}}
            )

    def test_basic_requires_username_and_password(self):
        with pytest.raises(ValueError, match="'auth.password'"):
            TransformerConfig.from_dict(
                {
                    "name": "t",
                    "endpoint": {"url": "https://x.test"},
                    "auth": {"type": "basic", "username": "u"},
                }
            )

    def test_header_auth_requires_name_and_value(self):
        with pytest.raises(ValueError, match="'auth.header_value'"):
            TransformerConfig.from_dict(
                {
                    "name": "t",
                    "endpoint": {"url": "https://x.test"},
                    "auth": {"type": "header", "header_name": "X-Auth"},
                }
            )

    def test_invalid_content_transform_format_rejected(self):
        with pytest.raises(ValueError, match="content_transform.format"):
            TransformerConfig.from_dict(
                {
                    "name": "t",
                    "endpoint": {"url": "https://x.test"},
                    "content_transform": {"format": "yaml"},
                }
            )

    def test_non_positive_max_length_rejected(self):
        with pytest.raises(ValueError, match="max_length"):
            TransformerConfig.from_dict(
                {
                    "name": "t",
                    "endpoint": {"url": "https://x.test"},
                    "content_transform": {"max_length": 0},
                }
            )

    def test_non_string_headers_rejected(self):
        with pytest.raises(ValueError, match="'headers'"):
            TransformerConfig.from_dict(
                {"name": "t", "endpoint": {"url": "https://x.test"}, "headers": {"X-N": 1}}
            )

    def test_invalid_body_type_rejected(self):
        with pytest.raises(ValueError, match="'body'"):
            TransformerConfig.from_dict(
                {"name": "t", "endpoint": {"url": "https://x.test"}, "body": 42}
            )


class TestLoadTransformer:
    def test_load_valid_transformer(self, tmp_path):
        transformers_dir = tmp_path / "transformers"
        transformers_dir.mkdir()
        (transformers_dir / "slack.yaml").write_text(
            "name: slack\nendpoint:\n  url: https://slack.test/api\n"
        )
        config = load_transformer(tmp_path, "slack")
        assert config.name == "slack"
        assert config.url == "https://slack.test/api"

    def test_missing_transformer_fails_fast(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            load_transformer(tmp_path, "nope")

    def test_path_traversal_name_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="invalid transformer name"):
            load_transformer(tmp_path, "../secrets")

    def test_name_mismatch_rejected(self, tmp_path):
        transformers_dir = tmp_path / "transformers"
        transformers_dir.mkdir()
        (transformers_dir / "slack.yaml").write_text(
            "name: telegram\nendpoint:\n  url: https://x.test\n"
        )
        with pytest.raises(ValueError, match="must match the filename"):
            load_transformer(tmp_path, "slack")

    def test_malformed_yaml_fails_fast(self, tmp_path):
        transformers_dir = tmp_path / "transformers"
        transformers_dir.mkdir()
        (transformers_dir / "bad.yaml").write_text("name: [unclosed\n")
        with pytest.raises(ValueError, match="invalid YAML"):
            load_transformer(tmp_path, "bad")


class TestBundledTemplates:
    """Bundled dormant channel templates (Phase 2)."""

    BUNDLED = ["slack", "telegram", "discord", "email"]

    def test_bundled_templates_exist(self):
        assert BUILTIN_TRANSFORMERS_DIR.is_dir()
        names = sorted(p.stem for p in BUILTIN_TRANSFORMERS_DIR.glob("*.yaml"))
        assert names == sorted(self.BUNDLED)

    @pytest.mark.parametrize("name", BUNDLED)
    def test_bundled_template_loads_without_url(self, tmp_path, name):
        # Loads via the builtin fallback from a formation with no transformers
        # directory at all; payload format only, no destination URL.
        config = load_transformer(tmp_path, name)
        assert config.name == name
        assert config.url is None
        assert config.method == "POST"
        assert config.body, f"bundled template '{name}' must define a body"

    def test_formation_local_file_shadows_bundled_template(self, tmp_path):
        transformers_dir = tmp_path / "transformers"
        transformers_dir.mkdir()
        (transformers_dir / "slack.yaml").write_text(
            "name: slack\nendpoint:\n  url: https://my-bridge.test/slack\n"
            'body:\n  text: "${{ response.content }}"\n'
        )
        config = load_transformer(tmp_path, "slack")
        assert config.url == "https://my-bridge.test/slack"

    def test_unknown_name_still_fails_fast(self, tmp_path):
        # Inert-when-unreferenced pin: names matching neither a formation
        # file nor a bundled template error exactly as before.
        with pytest.raises(ValueError, match="not found"):
            load_transformer(tmp_path, "matrix")


class TestResolveTransformerUrl:
    def test_override_wins_over_transformer_url(self):
        transformer = TransformerConfig.from_dict(
            {"name": "t", "endpoint": {"url": "https://own.test"}}
        )
        assert resolve_transformer_url(transformer, "https://override.test") == (
            "https://override.test"
        )

    def test_transformer_url_used_without_override(self):
        transformer = TransformerConfig.from_dict(
            {"name": "t", "endpoint": {"url": "https://own.test"}}
        )
        assert resolve_transformer_url(transformer, None) == "https://own.test"

    def test_no_url_anywhere_fails_fast(self):
        transformer = TransformerConfig.from_dict({"name": "t"})
        with pytest.raises(ValueError, match="no 'endpoint.url'"):
            resolve_transformer_url(transformer, None)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TestTemplateRendering:
    def _variables(self, **overrides):
        variables = build_transformer_variables(
            response_content="Agent says hi",
            response_files=[{"name": "report.pdf"}],
            response_metadata={"model": "gpt-4o-mini"},
            request_message="original question",
            request_user_id="U123",
            context={"channel": "C42", "thread_ts": None},
            agent_name="assistant",
            secrets={"TOKEN": "sekrit"},
        )
        variables.update(overrides)
        return variables

    def test_mixed_string_substitution(self):
        result = render_template_string(
            "[${{ context.channel }}] ${{ response.content }}", self._variables()
        )
        assert result == "[C42] Agent says hi"

    def test_whole_placeholder_preserves_native_type(self):
        result = render_template_string("${{ response.files }}", self._variables())
        assert result == [{"name": "report.pdf"}]

    def test_missing_context_renders_empty_string_in_mixed(self):
        result = render_template_string("x=${{ context.nope }}!", self._variables())
        assert result == "x=!"

    def test_missing_secret_raises(self):
        with pytest.raises(ValueError, match="secret 'MISSING'"):
            render_template_string("${{ secrets.MISSING }}", self._variables())

    def test_metadata_and_agent_and_timestamp(self):
        variables = self._variables()
        assert render_template_string("${{ response.metadata.model }}", variables) == "gpt-4o-mini"
        assert render_template_string("${{ agent.name }}", variables) == "assistant"
        assert render_template_string("${{ timestamp }}", variables)  # ISO string, non-empty

    def test_dict_rendering_drops_none_values(self):
        body = {
            "channel": "${{ context.channel }}",
            "thread_ts": "${{ context.thread_ts }}",  # None -> dropped
            "text": "${{ response.content }}",
        }
        rendered = render_template_value(body, self._variables())
        assert rendered == {"channel": "C42", "text": "Agent says hi"}

    def test_nested_structures_render(self):
        body = {"blocks": [{"text": "${{ request.message }}"}], "n": 7}
        rendered = render_template_value(body, self._variables())
        assert rendered == {"blocks": [{"text": "original question"}], "n": 7}

    def test_collect_secret_names(self):
        config = TransformerConfig.from_dict(
            {
                "name": "t",
                "endpoint": {"url": "https://api.test/${{ secrets.PATH_KEY }}"},
                "auth": {
                    "type": "basic",
                    "username": "${{ secrets.USER }}",
                    "password": "${{ secrets.PASS }}",
                },
                "headers": {"X-K": "${{ secrets.HEADER_KEY }}"},
                "body": {"token": "${{ secrets.BODY_KEY }}", "text": "${{ response.content }}"},
            }
        )
        assert collect_secret_names(config) == {
            "PATH_KEY",
            "USER",
            "PASS",
            "HEADER_KEY",
            "BODY_KEY",
        }

    async def test_resolve_secrets_missing_raises(self):
        with pytest.raises(ValueError, match="secret 'NOPE' not found"):
            await resolve_secrets({"NOPE"}, FakeSecretsManager({}))

    async def test_resolve_secrets_requires_manager_when_referenced(self):
        with pytest.raises(ValueError, match="no\\s+secrets manager"):
            await resolve_secrets({"X"}, None)


# ---------------------------------------------------------------------------
# Content transforms
# ---------------------------------------------------------------------------


class TestContentTransform:
    def test_no_transform_passthrough(self):
        assert apply_content_transform("**bold**", None) == "**bold**"

    def test_markdown_format_passthrough(self):
        transform = ContentTransform.from_dict({"format": "markdown"})
        assert apply_content_transform("**bold**", transform) == "**bold**"

    def test_text_format_strips_markdown(self):
        transform = ContentTransform.from_dict({"format": "text"})
        content = "# Alert\n**CPU** is at *99%* — see [runbook](https://r.test) `now`"
        result = apply_content_transform(content, transform)
        assert result == "Alert\nCPU is at 99% — see runbook (https://r.test) now"

    def test_html_format_converts_and_escapes(self):
        transform = ContentTransform.from_dict({"format": "html"})
        result = apply_content_transform("**bold** & <script>", transform)
        assert result == "<p><strong>bold</strong> &amp; &lt;script&gt;</p>"

    def test_html_format_renders_http_links(self):
        transform = ContentTransform.from_dict({"format": "html"})
        result = apply_content_transform("see [docs](https://docs.test/page)", transform)
        assert result == '<p>see <a href="https://docs.test/page">docs</a></p>'

    def test_html_format_drops_unsafe_link_schemes(self):
        transform = ContentTransform.from_dict({"format": "html"})
        result = apply_content_transform("[x](javascript:alert(1))", transform)
        # The link regex stops at the first ")", so the closing paren of the
        # payload survives as literal text; the anchor itself must not render.
        assert result == "<p>x)</p>"
        assert "<a" not in result
        assert "javascript" not in result

    def test_html_format_drops_data_uri_links(self):
        transform = ContentTransform.from_dict({"format": "html"})
        result = apply_content_transform("[x](data:text/html;base64,PHNjcmlwdD4=)", transform)
        assert result == "<p>x</p>"
        assert "<a" not in result

    def test_truncation_never_exceeds_max_length(self):
        transform = ContentTransform.from_dict({"max_length": 10, "truncation_suffix": "..."})
        result = apply_content_transform("a" * 50, transform)
        assert result == "a" * 7 + "..."
        assert len(result) == 10

    def test_truncation_with_long_suffix_never_exceeds_max_length(self):
        transform = ContentTransform.from_dict(
            {"max_length": 5, "truncation_suffix": "[truncated]"}
        )
        result = apply_content_transform("a" * 50, transform)
        assert len(result) == 5
        assert result == "[trun"

    def test_truncation_not_applied_when_short(self):
        transform = ContentTransform.from_dict({"max_length": 160})
        assert apply_content_transform("short", transform) == "short"


class TestExtractResponseFiles:
    def test_unified_response_dict(self):
        response = {
            "response": [
                {"type": "text", "text": "hi"},
                {"type": "file", "file": {"name": "a.pdf"}},
            ]
        }
        assert extract_response_files(response) == [{"name": "a.pdf"}]

    def test_plain_string_has_no_files(self):
        assert extract_response_files("just text") == []


# ---------------------------------------------------------------------------
# Channel-native widget rendering (Response Envelope UI, P3)
# ---------------------------------------------------------------------------


def _options_widget():
    return build_options_widget(
        prompt="Which account?",
        options=[{"value": "acme-prod", "label": "Prod"}, {"value": "acme-dev", "label": "Dev"}],
    )


def _link_widget():
    return build_action_link_widget(
        label="Connect GitHub",
        url="https://auth.acme.com/connect/github",
        source=UIProvenance.FORMATION_CONFIG,
    )


class TestExtractResponseUI:
    def test_object_with_ui_attribute(self):
        class Response:
            ui = [{"type": "options", "id": "ui_x"}]

        assert extract_response_ui(Response()) == [{"type": "options", "id": "ui_x"}]

    def test_dict_with_ui_key(self):
        assert extract_response_ui({"ui": [{"type": "options"}]}) == [{"type": "options"}]

    def test_no_ui_is_empty(self):
        assert extract_response_ui({"response": []}) == []
        assert extract_response_ui("just text") == []
        assert extract_response_ui(None) == []

    def test_non_dict_entries_dropped(self):
        assert extract_response_ui({"ui": ["junk", None, {"type": "options"}]}) == [
            {"type": "options"}
        ]


class TestBuildUIVariables:
    def test_no_widgets_yields_all_none(self):
        # The zero-change discipline: every channel entry is None so
        # templating drops the keys from dict bodies.
        variables = build_ui_variables(None, "text")
        assert variables["telegram"]["reply_markup"] is None
        assert variables["slack"]["blocks"] is None
        assert variables["discord"]["components"] is None
        assert build_ui_variables([], "text") == variables

    def test_telegram_inline_keyboard(self):
        widget = _options_widget()
        link = _link_widget()
        markup = build_ui_variables([widget, link], "text")["telegram"]["reply_markup"]
        assert markup == {
            "inline_keyboard": [
                [{"text": "Prod", "callback_data": f"{widget['id']}#0"}],
                [{"text": "Dev", "callback_data": f"{widget['id']}#1"}],
                [{"text": "Connect GitHub", "url": "https://auth.acme.com/connect/github"}],
            ]
        }

    def test_telegram_callback_data_within_limit(self):
        widget = build_options_widget(
            prompt="?", options=[{"value": "v" * 300, "label": "L" * 300}] * 3
        )
        markup = build_ui_variables([widget], "text")["telegram"]["reply_markup"]
        for row in markup["inline_keyboard"]:
            for button in row:
                if "callback_data" in button:
                    assert len(button["callback_data"].encode("utf-8")) <= 64

    def test_slack_blocks_carry_text_and_buttons(self):
        widget = _options_widget()
        blocks = build_ui_variables([widget], "The text fallback")["slack"]["blocks"]
        # Section first: Slack renders blocks INSTEAD of top-level text,
        # so the text-fallback duty requires the text inside the blocks.
        assert blocks[0] == {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "The text fallback"},
        }
        actions = blocks[1]
        assert actions["type"] == "actions"
        assert actions["block_id"] == widget["id"]
        assert [e["text"]["text"] for e in actions["elements"]] == ["Prod", "Dev"]
        assert [e["value"] for e in actions["elements"]] == [
            f"{widget['id']}#0",
            f"{widget['id']}#1",
        ]

    def test_slack_action_link_is_url_button(self):
        link = _link_widget()
        blocks = build_ui_variables([link], "text")["slack"]["blocks"]
        button = blocks[1]["elements"][0]
        assert button["url"] == "https://auth.acme.com/connect/github"
        assert "value" not in button  # nothing to reply with; the link IS the action

    def test_slack_section_text_clamped(self):
        blocks = build_ui_variables([_options_widget()], "x" * 4000)["slack"]["blocks"]
        assert len(blocks[0]["text"]["text"]) <= 3000

    def test_discord_components_rows_of_five(self):
        widget = build_options_widget(
            prompt="?", options=[{"value": f"v{i}", "label": f"L{i}"} for i in range(7)]
        )
        components = build_ui_variables([widget], "text")["discord"]["components"]
        assert [len(row["components"]) for row in components] == [5, 2]
        first = components[0]["components"][0]
        assert first == {"type": 2, "style": 2, "label": "L0", "custom_id": f"{widget['id']}#0"}

    def test_discord_row_cap_drops_overflow(self):
        # Two full options widgets exceed Discord's 5-row limit; overflow
        # buttons are dropped (the text fallback carries every choice).
        widgets = [
            build_options_widget(prompt="?", options=[{"value": f"w{n}o{i}"} for i in range(20)])
            for n in range(2)
        ]
        components = build_ui_variables(widgets, "text")["discord"]["components"]
        assert len(components) == 5
        assert sum(len(row["components"]) for row in components) == 25

    def test_discord_action_link_is_link_button(self):
        link = _link_widget()
        components = build_ui_variables([link], "text")["discord"]["components"]
        button = components[0]["components"][0]
        assert button["style"] == 5
        assert button["url"] == "https://auth.acme.com/connect/github"
        assert "custom_id" not in button

    def test_unknown_widget_types_skipped(self):
        variables = build_ui_variables([{"type": "hologram", "id": "ui_x"}], "text")
        assert variables["telegram"]["reply_markup"] is None
        assert variables["slack"]["blocks"] is None
        assert variables["discord"]["components"] is None


class TestBundledTemplateWidgetRendering:
    """The updated bundled templates: widgets additive, text-only unchanged."""

    def _render_bundled_body(self, tmp_path, name, response_ui, content="Pick one"):
        config = load_transformer(tmp_path, name)
        variables = build_transformer_variables(
            response_content=content,
            response_ui=response_ui,
            context={"chat_id": "42", "channel": "C1", "thread_ts": None},
        )
        return render_template_value(config.body, variables)

    def test_telegram_text_only_body_unchanged(self, tmp_path):
        # The zero-change pin: without widgets the rendered payload is
        # key-for-key what the pre-P3 template produced.
        body = self._render_bundled_body(tmp_path, "telegram", response_ui=None)
        assert body == {"chat_id": "42", "text": "Pick one"}

    def test_telegram_widgets_render_inline_keyboard(self, tmp_path):
        widget = _options_widget()
        body = self._render_bundled_body(tmp_path, "telegram", response_ui=[widget])
        assert body["text"] == "Pick one"  # text always ships
        labels = [b["text"] for row in body["reply_markup"]["inline_keyboard"] for b in row]
        assert labels == ["Prod", "Dev"]

    def test_slack_text_only_body_unchanged(self, tmp_path):
        body = self._render_bundled_body(tmp_path, "slack", response_ui=[])
        assert body == {"channel": "C1", "text": "Pick one"}

    def test_slack_widgets_render_blocks(self, tmp_path):
        body = self._render_bundled_body(tmp_path, "slack", response_ui=[_options_widget()])
        assert body["text"] == "Pick one"  # notification fallback stays
        assert body["blocks"][0]["text"]["text"] == "Pick one"
        assert body["blocks"][1]["type"] == "actions"

    def test_discord_text_only_body_unchanged(self, tmp_path):
        body = self._render_bundled_body(tmp_path, "discord", response_ui=None)
        assert body == {"content": "Pick one"}

    def test_discord_widgets_render_components(self, tmp_path):
        body = self._render_bundled_body(tmp_path, "discord", response_ui=[_link_widget()])
        assert body["content"] == "Pick one"
        assert body["components"][0]["components"][0]["style"] == 5

    def test_email_template_has_no_widget_placeholders(self, tmp_path):
        # Email stays text (explicit P3 ruling).
        config = load_transformer(tmp_path, "email")
        assert "ui." not in str(config.body)


# ---------------------------------------------------------------------------
# Delivery (real local HTTP sink, no mocks)
# ---------------------------------------------------------------------------


class Sink:
    """Local aiohttp server capturing every request it receives."""

    def __init__(self, status=200):
        self.status = status
        self.requests = []
        self.runner = None
        self.port = None

    async def _handle(self, request: web.Request) -> web.Response:
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "headers": dict(request.headers),
                "body": await request.read(),
            }
        )
        return web.Response(status=self.status)

    async def start(self):
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


def _make_transformer(url, **extra):
    raw = {"name": "sink", "endpoint": {"url": url}, **extra}
    return TransformerConfig.from_dict(raw)


class TestTransformerDelivery:
    async def test_json_delivery_with_bearer_auth_and_context(self):
        sink = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = _make_transformer(
                f"http://127.0.0.1:{sink.port}/postMessage",
                auth={"type": "bearer", "token": "${{ secrets.BOT_TOKEN }}"},
                headers={"Content-Type": "application/json"},
                body={
                    "channel": "${{ context.channel }}",
                    "text": "${{ response.content }}",
                    "user": "${{ request.user_id }}",
                },
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=FakeSecretsManager({"BOT_TOKEN": "xoxb-123"}),
                transformer=transformer,
                response_content="Hello from the agent",
                request_user_id="U777",
                context={"channel": "C42"},
                request_id="req_test_1",
            )
            assert success is True
            assert len(sink.requests) == 1
            received = sink.requests[0]
            assert received["method"] == "POST"
            assert received["path"] == "/postMessage"
            assert received["headers"]["Authorization"] == "Bearer xoxb-123"
            import json

            payload = json.loads(received["body"])
            assert payload == {
                "channel": "C42",
                "text": "Hello from the agent",
                "user": "U777",
            }
        finally:
            await manager.close()
            await sink.stop()

    async def test_form_encoded_delivery_with_basic_auth_and_truncation(self):
        sink = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = _make_transformer(
                f"http://127.0.0.1:{sink.port}/Messages.json",
                auth={
                    "type": "basic",
                    "username": "${{ secrets.SID }}",
                    "password": "${{ secrets.AUTH }}",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body={"To": "+15550001111", "Body": "${{ response.content }}"},
                content_transform={"max_length": 12, "truncation_suffix": "..."},
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=FakeSecretsManager({"SID": "AC1", "AUTH": "tok"}),
                transformer=transformer,
                response_content="This message is far too long for SMS",
                request_id="req_test_2",
            )
            assert success is True
            received = sink.requests[0]
            assert received["headers"]["Authorization"].startswith("Basic ")
            form = parse_qs(received["body"].decode())
            assert form["To"] == ["+15550001111"]
            assert form["Body"] == ["This mess..."]
        finally:
            await manager.close()
            await sink.stop()

    async def test_endpoint_failure_falls_back_to_default_webhook(self):
        failing = await Sink(status=500).start()
        fallback = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = _make_transformer(
                f"http://127.0.0.1:{failing.port}/broken",
                body={"text": "${{ response.content }}"},
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=None,
                transformer=transformer,
                response_content="important result",
                request_id="req_test_3",
                formation_id="formation-x",
                fallback_webhook_url=f"http://127.0.0.1:{fallback.port}/default",
            )
            assert success is False
            assert len(failing.requests) == 1
            assert len(fallback.requests) == 1
            import json

            payload = json.loads(fallback.requests[0]["body"])
            assert payload["request_id"] == "req_test_3"
            assert payload["response"] == [{"type": "text", "text": "important result"}]
            error = payload["transformer_error"]
            assert error["transformer"] == "sink"
            assert error["attempts"] == 1
            assert error["last_error"] == "HTTP 500"
            assert error["timestamp"]
        finally:
            await manager.close()
            await failing.stop()
            await fallback.stop()

    async def test_missing_secret_never_hits_endpoint_and_falls_back(self):
        sink = await Sink().start()
        fallback = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = _make_transformer(
                f"http://127.0.0.1:{sink.port}/postMessage",
                auth={"type": "bearer", "token": "${{ secrets.ABSENT }}"},
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=FakeSecretsManager({}),
                transformer=transformer,
                response_content="hi",
                request_id="req_test_4",
                fallback_webhook_url=f"http://127.0.0.1:{fallback.port}/default",
            )
            assert success is False
            assert sink.requests == []  # endpoint never contacted with bad credentials
            import json

            payload = json.loads(fallback.requests[0]["body"])
            assert "ABSENT" in payload["transformer_error"]["last_error"]
        finally:
            await manager.close()
            await sink.stop()
            await fallback.stop()

    async def test_url_override_wins_over_transformer_endpoint(self):
        own = await Sink().start()
        override = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = _make_transformer(
                f"http://127.0.0.1:{own.port}/own",
                body={"text": "${{ response.content }}"},
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=None,
                transformer=transformer,
                url_override=f"http://127.0.0.1:{override.port}/override",
                response_content="hi",
                request_id="req_test_override_1",
            )
            assert success is True
            assert own.requests == [], "transformer endpoint must not be contacted"
            assert len(override.requests) == 1
            assert override.requests[0]["path"] == "/override"
        finally:
            await manager.close()
            await own.stop()
            await override.stop()

    async def test_url_less_transformer_delivers_to_override(self):
        # The transformer+webhook composition: payload format from the
        # transformer, destination from the trigger/channel.
        sink = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = TransformerConfig.from_dict(
                {
                    "name": "slack-shape",
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "channel": "${{ context.channel }}",
                        "text": "${{ response.content }}",
                    },
                }
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=None,
                transformer=transformer,
                url_override=f"http://127.0.0.1:{sink.port}/bridge",
                response_content="composed",
                context={"channel": "C1"},
                request_id="req_test_override_2",
            )
            assert success is True
            import json

            payload = json.loads(sink.requests[0]["body"])
            assert payload == {"channel": "C1", "text": "composed"}
        finally:
            await manager.close()
            await sink.stop()

    async def test_url_less_transformer_without_override_falls_back(self):
        fallback = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = TransformerConfig.from_dict(
                {"name": "no-url", "body": {"text": "${{ response.content }}"}}
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=None,
                transformer=transformer,
                response_content="orphan",
                request_id="req_test_override_3",
                fallback_webhook_url=f"http://127.0.0.1:{fallback.port}/default",
            )
            assert success is False
            import json

            payload = json.loads(fallback.requests[0]["body"])
            assert "no 'endpoint.url'" in payload["transformer_error"]["last_error"]
        finally:
            await manager.close()
            await fallback.stop()

    async def test_secret_backed_override_url_resolves(self):
        # A channel 'url:' may be a secret-backed template (e.g. a Slack
        # incoming-webhook URL); the override participates in secret scanning.
        sink = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = TransformerConfig.from_dict(
                {"name": "shape", "body": {"text": "${{ response.content }}"}}
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=FakeSecretsManager(
                    {"BRIDGE_URL": f"http://127.0.0.1:{sink.port}/secret-bridge"}
                ),
                transformer=transformer,
                url_override="${{ secrets.BRIDGE_URL }}",
                response_content="hi",
                request_id="req_test_override_4",
            )
            assert success is True
            assert sink.requests[0]["path"] == "/secret-bridge"
        finally:
            await manager.close()
            await sink.stop()

    async def test_header_auth_and_custom_method(self):
        sink = await Sink().start()
        manager = WebhookManager(default_retries=0, default_timeout=5)
        try:
            transformer = TransformerConfig.from_dict(
                {
                    "name": "sink",
                    "endpoint": {"url": f"http://127.0.0.1:{sink.port}/v2", "method": "PUT"},
                    "auth": {
                        "type": "header",
                        "header_name": "X-Api-Key",
                        "header_value": "${{ secrets.KEY }}",
                    },
                    "body": {"text": "${{ response.content }}"},
                }
            )
            success = await deliver_via_transformer(
                webhook_manager=manager,
                secrets_manager=FakeSecretsManager({"KEY": "k-9"}),
                transformer=transformer,
                response_content="hi",
                request_id="req_test_5",
            )
            assert success is True
            received = sink.requests[0]
            assert received["method"] == "PUT"
            assert received["headers"]["X-Api-Key"] == "k-9"
        finally:
            await manager.close()
            await sink.stop()
