"""
Unit tests for the proactive heartbeat service.

Covers active-hours gating (same-day windows, overnight wrap, weekends,
fixed and per-user timezones), interval gating in tick(), HEARTBEAT_OK
suppression, and end-to-end routing of a heartbeat message to the user's
last channel through a real local HTTP sink (no mocks; the overlord is a
minimal stub because a real one requires live LLM credentials).
"""

import json
from datetime import datetime, timedelta, timezone

from aiohttp import web

from muxi.runtime.formation.background.webhook_manager import WebhookManager
from muxi.runtime.formation.proactive import (
    HeartbeatService,
    NotificationRouter,
    UserChannelStore,
    parse_proactive_config,
)

# Fixed reference times (UTC)
TUESDAY_NOON = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
TUESDAY_NIGHT = datetime(2026, 7, 7, 23, 0, tzinfo=timezone.utc)
SATURDAY_NOON = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


class FakeSecretsManager:
    def __init__(self, secrets=None):
        self._secrets = secrets or {}

    async def get_secret(self, name):
        return self._secrets.get(name)


class StubOverlord:
    """Canned-response overlord: heartbeat unit tests must not need an LLM."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)

        class _Response:
            content = self.reply

        return _Response()

    def _ensure_sop_system(self):
        return False


class Sink:
    def __init__(self, status=200):
        self.status = status
        self.requests = []
        self.runner = None
        self.port = None

    async def _handle(self, request: web.Request) -> web.Response:
        self.requests.append({"path": request.path, "body": await request.read()})
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
        f"name: {name}\nendpoint:\n  url: {url}\nbody:\n" f'  text: "${{{{ response.content }}}}"\n'
    )


def _heartbeat(tmp_path, raw_proactive, reply="HEARTBEAT_OK", sink_url=None):
    """Build a HeartbeatService wired to a stub overlord and a real router."""
    _write_transformer(tmp_path, "t-a", sink_url or "http://127.0.0.1:1/never")
    config = parse_proactive_config(raw_proactive)
    store = UserChannelStore(formation_id="test-formation")
    router = NotificationRouter(
        config=config,
        formation_dir=str(tmp_path),
        formation_id="test-formation",
        channel_store=store,
        webhook_manager=WebhookManager(default_retries=0, default_timeout=5),
        secrets_manager=FakeSecretsManager(),
    )
    overlord = StubOverlord(reply)
    service = HeartbeatService(
        config=config.heartbeat,
        overlord=overlord,
        router=router,
        channel_store=store,
    )
    return service, store, overlord


def _proactive(**heartbeat):
    return {
        "channels": {"chan-a": {"transformer": "t-a"}},
        "heartbeat": heartbeat,
    }


class TestActiveHours:
    def test_no_active_hours_always_active(self, tmp_path):
        service, _, _ = _heartbeat(tmp_path, _proactive())
        assert service.is_within_active_hours(TUESDAY_NIGHT) is True

    def test_inside_window(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path, _proactive(active_hours={"start": "09:00", "end": "18:00"})
        )
        assert service.is_within_active_hours(TUESDAY_NOON) is True

    def test_outside_window(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path, _proactive(active_hours={"start": "09:00", "end": "18:00"})
        )
        assert service.is_within_active_hours(TUESDAY_NIGHT) is False

    def test_boundaries_inclusive(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path, _proactive(active_hours={"start": "12:00", "end": "18:00"})
        )
        assert service.is_within_active_hours(TUESDAY_NOON) is True

    def test_overnight_window_wraps_midnight(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path, _proactive(active_hours={"start": "22:00", "end": "06:00"})
        )
        assert service.is_within_active_hours(TUESDAY_NIGHT) is True
        assert service.is_within_active_hours(TUESDAY_NOON) is False

    def test_weekends_suppressed(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path,
            _proactive(active_hours={"start": "09:00", "end": "18:00", "weekends": False}),
        )
        assert service.is_within_active_hours(SATURDAY_NOON) is False
        assert service.is_within_active_hours(TUESDAY_NOON) is True

    def test_fixed_timezone_shifts_window(self, tmp_path):
        # 12:00 UTC is 21:00 in Tokyo: outside a 09:00-18:00 Tokyo window
        service, _, _ = _heartbeat(
            tmp_path,
            _proactive(active_hours={"start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"}),
        )
        assert service.is_within_active_hours(TUESDAY_NOON) is False

    def test_user_timezone_applied(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path,
            _proactive(active_hours={"start": "09:00", "end": "18:00", "timezone": "user"}),
        )
        # 12:00 UTC: within window for a UTC user, outside for a Tokyo user
        assert service.is_within_active_hours(TUESDAY_NOON, user_timezone=None) is True
        assert service.is_within_active_hours(TUESDAY_NOON, user_timezone="Asia/Tokyo") is False


class TestIntervalGating:
    async def test_tick_before_interval_does_nothing(self, tmp_path):
        service, store, overlord = _heartbeat(tmp_path, _proactive(interval="30m"))
        await store.record_inbound("ran", "chan-a")
        start = datetime.now(timezone.utc)
        await service.tick(start + timedelta(minutes=10))
        assert overlord.calls == []

    async def test_tick_after_interval_runs(self, tmp_path):
        service, store, overlord = _heartbeat(tmp_path, _proactive(interval="30m"))
        await store.record_inbound("ran", "chan-a")
        start = datetime.now(timezone.utc)
        await service.tick(start + timedelta(minutes=31))
        assert len(overlord.calls) == 1
        # Interval resets: an immediate second tick is a no-op
        await service.tick(start + timedelta(minutes=32))
        assert len(overlord.calls) == 1

    async def test_no_known_users_is_silent(self, tmp_path):
        service, _, overlord = _heartbeat(tmp_path, _proactive(interval="30m"))
        await service.run_once()
        assert overlord.calls == []


class TestSuppression:
    async def test_heartbeat_ok_is_not_delivered(self, tmp_path):
        sink = await Sink().start()
        try:
            service, store, overlord = _heartbeat(
                tmp_path,
                _proactive(),
                reply="HEARTBEAT_OK",
                sink_url=f"http://127.0.0.1:{sink.port}/notify",
            )
            await store.record_inbound("ran", "chan-a")
            notified = await service.run_once()
            assert notified == []
            assert len(overlord.calls) == 1  # Agent woke up...
            assert sink.requests == []  # ...but stayed silent
        finally:
            await sink.stop()

    async def test_outside_active_hours_skips_llm_entirely(self, tmp_path):
        service, store, overlord = _heartbeat(
            tmp_path,
            _proactive(active_hours={"start": "09:00", "end": "18:00"}),
            reply="should never run",
        )
        await store.record_inbound("ran", "chan-a")
        await service.run_once(TUESDAY_NIGHT)
        assert overlord.calls == []


class TestDelivery:
    async def test_report_routes_to_last_channel(self, tmp_path):
        sink = await Sink().start()
        try:
            service, store, overlord = _heartbeat(
                tmp_path,
                _proactive(target="last"),
                reply="Your 2pm meeting conflicts with the standup.",
                sink_url=f"http://127.0.0.1:{sink.port}/notify",
            )
            await store.record_inbound("ran", "chan-a")
            notified = await service.run_once()
            assert notified == ["ran"]
            payload = json.loads(sink.requests[0]["body"])
            assert payload["text"] == "Your 2pm meeting conflicts with the standup."
            # The heartbeat conversation is scoped per user
            assert overlord.calls[0]["session_id"] == "heartbeat_ran"
            assert overlord.calls[0]["is_scheduled_execution"] is True
        finally:
            await sink.stop()

    async def test_instruction_appended_to_prompt(self, tmp_path):
        service, store, overlord = _heartbeat(
            tmp_path, _proactive(instruction="Only meeting prep matters.")
        )
        await store.record_inbound("ran", "chan-a")
        await service.run_once()
        prompt = overlord.calls[0]["message"]
        assert "HEARTBEAT_OK" in prompt
        assert "Only meeting prep matters." in prompt

    async def test_user_failure_is_isolated(self, tmp_path):
        sink = await Sink().start()
        try:
            service, store, overlord = _heartbeat(
                tmp_path,
                _proactive(),
                reply="report",
                sink_url=f"http://127.0.0.1:{sink.port}/notify",
            )

            async def failing_chat(**kwargs):
                if kwargs["user_id"] == "alice":
                    raise RuntimeError("boom")
                return await StubOverlord("report").chat(**kwargs)

            overlord.chat = failing_chat
            await store.record_inbound("alice", "chan-a")
            await store.record_inbound("bob", "chan-a")

            notified = await service.run_once()

            # Alice's failure never blocks Bob's heartbeat
            assert notified == ["bob"]
        finally:
            await sink.stop()
