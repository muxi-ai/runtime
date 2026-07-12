"""
Unit tests for the proactive notification router.

Covers routing precedence (explicit > preferred > default > webhook),
the reserved 'last'/'preferred'/'webhook' targets, multi-channel arrays,
fallback behavior for unknown/stale channels, and real HTTP delivery
through the trigger-transformer machinery (local aiohttp sink server,
no mocks).
"""

import json

import pytest
from aiohttp import web

from muxi.runtime.formation.background.webhook_manager import WebhookManager
from muxi.runtime.formation.proactive import (
    NotificationRouter,
    UserChannelStore,
    parse_proactive_config,
)


class FakeSecretsManager:
    """Minimal async secrets source for rendering tests."""

    def __init__(self, secrets=None):
        self._secrets = secrets or {}

    async def get_secret(self, name):
        return self._secrets.get(name)


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


def _write_transformer(formation_dir, name, url):
    transformers_dir = formation_dir / "transformers"
    transformers_dir.mkdir(exist_ok=True)
    (transformers_dir / f"{name}.yaml").write_text(
        f"name: {name}\n"
        f"endpoint:\n"
        f"  url: {url}\n"
        f"body:\n"
        f'  text: "${{{{ response.content }}}}"\n'
        f'  room: "${{{{ context.room }}}}"\n'
        f'  user: "${{{{ request.user_id }}}}"\n'
    )


def _router(formation_dir, raw_config, store=None, async_webhook_url=None):
    config = parse_proactive_config(raw_config)
    store = store or UserChannelStore(formation_id="test-formation")
    router = NotificationRouter(
        config=config,
        formation_dir=str(formation_dir),
        formation_id="test-formation",
        channel_store=store,
        webhook_manager=WebhookManager(default_retries=0, default_timeout=5),
        secrets_manager=FakeSecretsManager(),
        async_webhook_url=async_webhook_url,
        agent_name="test-agent",
    )
    return router, store


class TestRoutingPrecedence:
    async def test_no_preference_resolves_to_webhook(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        router, _ = _router(tmp_path, {"channels": {"chan-a": {"transformer": "t-a"}}})
        assert await router.resolve_channels("ran") == ["webhook"]

    async def test_preferred_channel_wins_over_default(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        _write_transformer(tmp_path, "t-b", "http://127.0.0.1:1/never")
        router, store = _router(
            tmp_path,
            {
                "channels": {
                    "chan-a": {"transformer": "t-a"},
                    "chan-b": {"transformer": "t-b"},
                },
                "default_channel": "chan-b",
            },
        )
        await store.set_preferences("ran", preferred_channel="chan-a")
        assert await router.resolve_channels("ran") == ["chan-a"]

    async def test_default_channel_used_without_preference(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        router, _ = _router(
            tmp_path,
            {"channels": {"chan-a": {"transformer": "t-a"}}, "default_channel": "chan-a"},
        )
        assert await router.resolve_channels("ran") == ["chan-a"]

    async def test_explicit_channel_overrides_preference(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        _write_transformer(tmp_path, "t-b", "http://127.0.0.1:1/never")
        router, store = _router(
            tmp_path,
            {
                "channels": {
                    "chan-a": {"transformer": "t-a"},
                    "chan-b": {"transformer": "t-b"},
                }
            },
        )
        await store.set_preferences("ran", preferred_channel="chan-a")
        assert await router.resolve_channels("ran", ["chan-b"]) == ["chan-b"]

    async def test_last_target_resolves_to_last_channel(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        _write_transformer(tmp_path, "t-b", "http://127.0.0.1:1/never")
        router, store = _router(
            tmp_path,
            {
                "channels": {
                    "chan-a": {"transformer": "t-a"},
                    "chan-b": {"transformer": "t-b"},
                }
            },
        )
        await store.set_preferences("ran", preferred_channel="chan-a")
        await store.record_inbound("ran", "chan-b")
        assert await router.resolve_channels("ran", ["last"]) == ["chan-b"]

    async def test_last_falls_back_to_preferred_then_default(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        router, store = _router(
            tmp_path,
            {"channels": {"chan-a": {"transformer": "t-a"}}, "default_channel": "chan-a"},
        )
        # No last channel, no preference -> default
        assert await router.resolve_channels("ran", ["last"]) == ["chan-a"]
        await store.set_preferences("ran", preferred_channel="chan-a")
        assert await router.resolve_channels("ran", ["last"]) == ["chan-a"]

    async def test_multi_channel_array_deduplicated(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        _write_transformer(tmp_path, "t-b", "http://127.0.0.1:1/never")
        router, store = _router(
            tmp_path,
            {
                "channels": {
                    "chan-a": {"transformer": "t-a"},
                    "chan-b": {"transformer": "t-b"},
                }
            },
        )
        await store.set_preferences("ran", preferred_channel="chan-a")
        resolved = await router.resolve_channels("ran", ["chan-a", "chan-b", "preferred"])
        assert resolved == ["chan-a", "chan-b"]

    async def test_stale_preference_falls_back_to_webhook(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        router, store = _router(tmp_path, {"channels": {"chan-a": {"transformer": "t-a"}}})
        await store.set_preferences("ran", preferred_channel="webhook")
        assert await router.resolve_channels("ran") == ["webhook"]


def _write_url_less_transformer(formation_dir, name):
    transformers_dir = formation_dir / "transformers"
    transformers_dir.mkdir(exist_ok=True)
    (transformers_dir / f"{name}.yaml").write_text(
        f"name: {name}\n"
        f"body:\n"
        f'  text: "${{{{ response.content }}}}"\n'
        f'  room: "${{{{ context.room }}}}"\n'
        f'  user: "${{{{ request.user_id }}}}"\n'
    )


class TestConstruction:
    def test_missing_transformer_fails_fast(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            _router(tmp_path, {"channels": {"chan-a": {"transformer": "missing"}}})

    def test_url_less_transformer_without_channel_url_fails_fast(self, tmp_path):
        # URL resolution is a startup error, not a delivery-time surprise
        _write_url_less_transformer(tmp_path, "shape-only")
        with pytest.raises(ValueError, match="no 'endpoint.url'"):
            _router(tmp_path, {"channels": {"chan-a": {"transformer": "shape-only"}}})

    def test_channel_url_satisfies_url_less_transformer(self, tmp_path):
        _write_url_less_transformer(tmp_path, "shape-only")
        router, _ = _router(
            tmp_path,
            {"channels": {"chan-a": {"transformer": "shape-only", "url": "https://bridge.test/a"}}},
        )
        assert router.config.channels["chan-a"].url == "https://bridge.test/a"

    def test_bundled_template_with_channel_url_constructs(self, tmp_path):
        # A bundled dormant template (no formation-local file at all)
        # activates by reference when the channel supplies the URL.
        router, _ = _router(
            tmp_path,
            {"channels": {"slack": {"transformer": "slack", "url": "https://bridge.test/s"}}},
        )
        assert router.config.channels["slack"].transformer == "slack"


class TestUiWidgets:
    async def test_channel_delivery_renders_ui_variables(self, tmp_path):
        from muxi.runtime.datatypes.ui import build_options_widget

        sink = await Sink().start()
        try:
            transformers_dir = tmp_path / "transformers"
            transformers_dir.mkdir(exist_ok=True)
            (transformers_dir / "t-ui.yaml").write_text(
                "name: t-ui\n"
                "endpoint:\n"
                f"  url: http://127.0.0.1:{sink.port}/notify\n"
                "body:\n"
                '  text: "${{ response.content }}"\n'
                '  reply_markup: "${{ ui.telegram.reply_markup }}"\n'
            )
            router, store = _router(tmp_path, {"channels": {"chan-u": {"transformer": "t-ui"}}})
            await store.set_preferences("ran", preferred_channel="chan-u")

            widget = build_options_widget(
                "Apply?", [{"value": "apply", "label": "Apply"}, {"value": "dismiss"}]
            )
            result = await router.notify(user_id="ran", message="report", ui=[widget])

            assert result["delivered"] == ["chan-u"]
            payload = json.loads(sink.requests[0]["body"])
            assert payload["text"] == "report"
            buttons = payload["reply_markup"]["inline_keyboard"]
            callbacks = [button["callback_data"] for row in buttons for button in row]
            assert callbacks == [f"{widget['id']}#0", f"{widget['id']}#1"]
        finally:
            await sink.stop()

    async def test_webhook_payload_carries_ui(self, tmp_path):
        from muxi.runtime.datatypes.ui import build_options_widget

        sink = await Sink().start()
        try:
            router, _ = _router(
                tmp_path,
                {"channels": {}},
                async_webhook_url=f"http://127.0.0.1:{sink.port}/hook",
            )
            widget = build_options_widget("Apply?", [{"value": "apply"}])
            result = await router.notify(user_id="ran", message="report", ui=[widget])

            assert result["delivered"] == ["webhook"]
            payload = json.loads(sink.requests[0]["body"])
            assert payload["response"] == [{"type": "text", "text": "report"}]
            assert payload["ui"][0]["id"] == widget["id"]
        finally:
            await sink.stop()

    async def test_text_only_notification_is_unchanged(self, tmp_path):
        sink = await Sink().start()
        try:
            router, _ = _router(
                tmp_path,
                {"channels": {}},
                async_webhook_url=f"http://127.0.0.1:{sink.port}/hook",
            )
            await router.notify(user_id="ran", message="plain")
            payload = json.loads(sink.requests[0]["body"])
            assert "ui" not in payload
        finally:
            await sink.stop()


class TestDelivery:
    async def test_delivers_to_channel_with_user_context(self, tmp_path):
        sink = await Sink().start()
        try:
            _write_transformer(tmp_path, "t-a", f"http://127.0.0.1:{sink.port}/notify")
            router, store = _router(tmp_path, {"channels": {"chan-a": {"transformer": "t-a"}}})
            await store.set_preferences(
                "ran", preferred_channel="chan-a", channels={"chan-a": {"room": "R42"}}
            )

            result = await router.notify(user_id="ran", message="hello there")

            assert result["delivered"] == ["chan-a"]
            assert result["failed"] == []
            assert len(sink.requests) == 1
            payload = json.loads(sink.requests[0]["body"])
            assert payload["text"] == "hello there"
            assert payload["room"] == "R42"
            assert payload["user"] == "ran"
        finally:
            await sink.stop()

    async def test_channel_url_override_wins_over_transformer_url(self, tmp_path):
        own = await Sink().start()
        override = await Sink().start()
        try:
            _write_transformer(tmp_path, "t-a", f"http://127.0.0.1:{own.port}/own")
            router, store = _router(
                tmp_path,
                {
                    "channels": {
                        "chan-a": {
                            "transformer": "t-a",
                            "url": f"http://127.0.0.1:{override.port}/override",
                        }
                    }
                },
            )
            await store.set_preferences("ran", preferred_channel="chan-a")

            result = await router.notify(user_id="ran", message="ping")

            assert result["delivered"] == ["chan-a"]
            assert own.requests == []
            assert len(override.requests) == 1
            assert override.requests[0]["path"] == "/override"
        finally:
            await own.stop()
            await override.stop()

    async def test_url_less_transformer_delivers_to_channel_url(self, tmp_path):
        sink = await Sink().start()
        try:
            _write_url_less_transformer(tmp_path, "shape-only")
            router, store = _router(
                tmp_path,
                {
                    "channels": {
                        "chan-a": {
                            "transformer": "shape-only",
                            "url": f"http://127.0.0.1:{sink.port}/bridge",
                        }
                    }
                },
            )
            await store.set_preferences(
                "ran", preferred_channel="chan-a", channels={"chan-a": {"room": "R7"}}
            )

            result = await router.notify(user_id="ran", message="composed")

            assert result["delivered"] == ["chan-a"]
            payload = json.loads(sink.requests[0]["body"])
            assert payload == {"text": "composed", "room": "R7", "user": "ran"}
        finally:
            await sink.stop()

    async def test_multi_channel_delivery(self, tmp_path):
        sink = await Sink().start()
        try:
            _write_transformer(tmp_path, "t-a", f"http://127.0.0.1:{sink.port}/a")
            _write_transformer(tmp_path, "t-b", f"http://127.0.0.1:{sink.port}/b")
            router, _ = _router(
                tmp_path,
                {
                    "channels": {
                        "chan-a": {"transformer": "t-a"},
                        "chan-b": {"transformer": "t-b"},
                    }
                },
            )

            result = await router.notify(
                user_id="ran", message="fan out", channels=["chan-a", "chan-b"]
            )

            assert result["delivered"] == ["chan-a", "chan-b"]
            assert sorted(r["path"] for r in sink.requests) == ["/a", "/b"]
        finally:
            await sink.stop()

    async def test_webhook_target_posts_notification_payload(self, tmp_path):
        sink = await Sink().start()
        try:
            _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
            router, _ = _router(
                tmp_path,
                {"channels": {"chan-a": {"transformer": "t-a"}}},
                async_webhook_url=f"http://127.0.0.1:{sink.port}/hook",
            )

            result = await router.notify(user_id="ran", message="to webhook")

            assert result["delivered"] == ["webhook"]
            payload = json.loads(sink.requests[0]["body"])
            assert payload["type"] == "notification"
            assert payload["user_id"] == "ran"
            assert payload["response"] == [{"type": "text", "text": "to webhook"}]
        finally:
            await sink.stop()

    async def test_failed_channel_falls_back_to_webhook(self, tmp_path):
        sink = await Sink().start()
        try:
            # Channel transformer points at a dead port; webhook is live
            _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/dead")
            router, store = _router(
                tmp_path,
                {"channels": {"chan-a": {"transformer": "t-a"}}},
                async_webhook_url=f"http://127.0.0.1:{sink.port}/hook",
            )
            await store.set_preferences("ran", preferred_channel="chan-a")

            result = await router.notify(user_id="ran", message="rescue me")

            assert result["failed"] == ["chan-a"]
            assert result["delivered"] == ["webhook"]
            payload = json.loads(sink.requests[0]["body"])
            assert payload["failed_channels"] == ["chan-a"]
        finally:
            await sink.stop()

    async def test_no_webhook_url_drops_gracefully(self, tmp_path):
        _write_transformer(tmp_path, "t-a", "http://127.0.0.1:1/never")
        router, _ = _router(tmp_path, {"channels": {"chan-a": {"transformer": "t-a"}}})
        result = await router.notify(user_id="ran", message="nowhere to go")
        assert result["delivered"] == []
        assert result["failed"] == ["webhook"]
