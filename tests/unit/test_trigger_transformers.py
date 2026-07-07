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

from muxi.runtime.formation.background.transformers import (
    ContentTransform,
    TransformerConfig,
    apply_content_transform,
    build_transformer_variables,
    collect_secret_names,
    deliver_via_transformer,
    extract_parse_values,
    extract_path,
    extract_response_files,
    load_transformer,
    parse_trigger_frontmatter,
    render_template_string,
    render_template_value,
    resolve_secrets,
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

    def test_webhook_and_transformer_are_mutually_exclusive(self):
        content = "---\nwebhook: https://x.test/h\ntransformer: slack\n---\nbody"
        with pytest.raises(ValueError, match="mutually exclusive"):
            parse_trigger_frontmatter(content)

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
        assert result == {"message": None, "user_id": None, "files": None, "context": {}}

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

    def test_missing_endpoint_rejected(self):
        with pytest.raises(ValueError, match="'endpoint'"):
            TransformerConfig.from_dict({"name": "t"})

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

    def test_truncation_never_exceeds_max_length(self):
        transform = ContentTransform.from_dict({"max_length": 10, "truncation_suffix": "..."})
        result = apply_content_transform("a" * 50, transform)
        assert result == "a" * 7 + "..."
        assert len(result) == 10

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
