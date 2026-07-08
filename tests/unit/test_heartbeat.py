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
    load_default_heartbeat_sop,
    parse_proactive_config,
)
from muxi.runtime.formation.proactive.heartbeat import BUILTIN_HEARTBEAT_SOP_PATH

# Fixed reference times (UTC)
TUESDAY_NOON = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
TUESDAY_NIGHT = datetime(2026, 7, 7, 23, 0, tzinfo=timezone.utc)
SATURDAY_NOON = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


class FakeSecretsManager:
    def __init__(self, secrets=None):
        self._secrets = secrets or {}

    async def get_secret(self, name):
        return self._secrets.get(name)


class StubSopSystem:
    def __init__(self, sops):
        self.sops = {name: {"content": content} for name, content in sops.items()}


class StubOverlord:
    """Canned-response overlord: heartbeat unit tests must not need an LLM."""

    def __init__(self, reply, sops=None):
        self.reply = reply
        self.calls = []
        self._sops = sops or {}
        self.sop_system = StubSopSystem(self._sops)

    async def chat(self, **kwargs):
        self.calls.append(kwargs)

        class _Response:
            content = self.reply

        return _Response()

    def _ensure_sop_system(self):
        return bool(self._sops)


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


def _heartbeat(tmp_path, raw_proactive, reply="HEARTBEAT_OK", sink_url=None, sops=None):
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
    overlord = StubOverlord(reply, sops=sops)
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

    async def test_wrapped_heartbeat_ok_is_not_delivered(self, tmp_path):
        # Agent pipelines (persona formatting, workflow synthesis) wrap the
        # raw sentinel in prose; a response mentioning HEARTBEAT_OK is
        # protocol chatter about the check, never a user notification.
        sink = await Sink().start()
        try:
            service, store, overlord = _heartbeat(
                tmp_path,
                _proactive(),
                reply="The check was fine, the agent replied with **HEARTBEAT_OK**.",
                sink_url=f"http://127.0.0.1:{sink.port}/notify",
            )
            await store.record_inbound("ran", "chan-a")
            notified = await service.run_once()
            assert notified == []
            assert sink.requests == []
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
            # The heartbeat conversation is user-scoped and fresh per run
            assert overlord.calls[0]["session_id"].startswith("heartbeat_ran_")
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


class TestSessionScoping:
    async def test_each_run_uses_a_fresh_session(self, tmp_path):
        """
        Fixed per-user session ids would accumulate conversation history
        (and session-scoped buffer memory) without bound across ticks:
        every run must get a fresh, user-scoped, request-correlated session.
        """
        service, store, overlord = _heartbeat(tmp_path, _proactive())
        await store.record_inbound("ran", "chan-a")

        await service.run_once()
        await service.run_once()

        assert len(overlord.calls) == 2
        first, second = overlord.calls
        assert first["session_id"].startswith("heartbeat_ran_")
        assert second["session_id"].startswith("heartbeat_ran_")
        assert first["session_id"] != second["session_id"]
        # Session stays correlated with the run's request id
        assert first["session_id"] == f"heartbeat_ran_{first['request_id']}"


class TestPromptResolution:
    """
    Default-SOP fallback and override precedence (Proactiveness Phase 4):
    formation `sop:` > bundled default heartbeat SOP > minimal built-in
    prompt (broken install only); `instruction:` appends in every case.
    """

    def test_bundled_sop_ships_with_the_runtime(self):
        assert BUILTIN_HEARTBEAT_SOP_PATH.is_file(), "bundled heartbeat SOP missing from package"
        content = load_default_heartbeat_sop()
        assert "## Your Task" in content
        assert "HEARTBEAT_OK" in content

    def test_no_sop_configured_uses_bundled_default(self, tmp_path):
        service, _, _ = _heartbeat(tmp_path, _proactive())
        assert service._build_prompt() == load_default_heartbeat_sop()

    def test_formation_sop_overrides_bundled_default(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path,
            _proactive(sop="my-heartbeat"),
            sops={"my-heartbeat": "CUSTOM HEARTBEAT PROMPT"},
        )
        prompt = service._build_prompt()
        assert prompt == "CUSTOM HEARTBEAT PROMPT"
        assert "## Your Task" not in prompt

    def test_missing_formation_sop_falls_back_to_bundled_default(self, tmp_path):
        # `sop:` names an SOP the formation does not define: fall back to
        # the bundled default instead of an empty or minimal prompt
        service, _, _ = _heartbeat(
            tmp_path,
            _proactive(sop="does-not-exist"),
            sops={"some-other-sop": "irrelevant"},
        )
        assert service._build_prompt() == load_default_heartbeat_sop()

    def test_instruction_appends_to_bundled_default(self, tmp_path):
        service, _, _ = _heartbeat(tmp_path, _proactive(instruction="Meetings only."))
        prompt = service._build_prompt()
        assert prompt.startswith(load_default_heartbeat_sop())
        assert prompt.endswith("## Additional Instructions\nMeetings only.")

    def test_instruction_appends_to_formation_sop(self, tmp_path):
        service, _, _ = _heartbeat(
            tmp_path,
            _proactive(sop="my-heartbeat", instruction="Meetings only."),
            sops={"my-heartbeat": "CUSTOM HEARTBEAT PROMPT"},
        )
        prompt = service._build_prompt()
        assert prompt.startswith("CUSTOM HEARTBEAT PROMPT")
        assert prompt.endswith("## Additional Instructions\nMeetings only.")
