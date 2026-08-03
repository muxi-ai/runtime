"""
Unit tests for the built-in slash commands (Proactiveness Phase 3).

Covers, per command, the happy path plus the "formation cannot back this"
edges (no scheduler for /jobs, no proactive block for /channels and
/preferences, no database for /identity, no session for /reset), the
overlord interception gate (no ``commands:`` block means no interception
at all -- pinned), formation-SOP shadowing through the chat gate, the
deterministic /setup flow, and handler failure isolation.

All commands are deterministic: no LLM is involved anywhere in this file.
Database-backed /identity link/unlink runs against in-memory SQLite;
everything else uses the real in-memory UserChannelStore plus small fakes
for the scheduler and buffer memory.
"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.formation.builtin_commands import (
    BuiltinCommandContext,
    execute_builtin,
    handle_setup_answer,
)
from muxi.runtime.formation.commands import (
    BUILTIN_COMMANDS,
    BuiltinCommand,
    CommandsConfig,
    ParsedCommand,
    parse_commands_config,
)
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.formation.proactive import UserChannelStore, parse_proactive_config
from muxi.runtime.services.db import Base
from muxi.runtime.services.memory.long_term import User, UserIdentifier

# ===================================================================
# Test doubles
# ===================================================================


class FakeScheduler:
    """Deterministic stand-in for SchedulerService job management."""

    def __init__(self, jobs: Optional[List[Dict[str, Any]]] = None):
        self.jobs = jobs or []
        self.actions: List[tuple] = []
        self.job_manager = SimpleNamespace(get_job_audit_trail=self._audit_trail)

    async def list_user_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        return list(self.jobs)

    async def pause_job(self, job_id: str, user_id: str = "0") -> bool:
        self.actions.append(("pause", job_id, user_id))
        job = next((j for j in self.jobs if j["id"] == job_id), None)
        if job is None or job["status"] != "ACTIVE":
            return False
        job["status"] = "PAUSED"
        return True

    async def resume_job(self, job_id: str, user_id: str = "0") -> bool:
        self.actions.append(("resume", job_id, user_id))
        job = next((j for j in self.jobs if j["id"] == job_id), None)
        if job is None or job["status"] != "PAUSED":
            return False
        job["status"] = "ACTIVE"
        return True

    async def delete_job(self, job_id: str, user_id: str = "0") -> bool:
        self.actions.append(("cancel", job_id, user_id))
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j["id"] != job_id]
        return len(self.jobs) < before

    async def _audit_trail(self, job_id: str) -> List[Dict[str, Any]]:
        return [{"timestamp": "2026-07-08T09:00:00", "action": "created"}]


class FakeDelegation:
    """Deterministic stand-in for the coding DelegationService surface."""

    def __init__(self, jobs: Optional[List[Dict[str, Any]]] = None):
        self.jobs = jobs or []
        self.actions: List[tuple] = []

    async def list_user_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        return [j for j in self.jobs if j.get("user_id", user_id) == user_id]

    async def cancel_job(self, job_id: str, user_id: str = "0") -> bool:
        self.actions.append(("cancel", job_id, user_id))
        job = next((j for j in self.jobs if j["id"] == job_id), None)
        if job is None or job["status"] != "running":
            return False
        job["status"] = "cancelled"
        return True

    async def get_job_trail(self, job_id: str, user_id: str = "0"):
        return [
            {"timestamp": "2026-07-10T09:00:00", "action": "started"},
            {"timestamp": "2026-07-10T09:05:00", "action": "completed"},
        ]


def coding_job(job_id="cdg_abc123", status="running", user_id="0", **extra):
    return {
        "id": job_id,
        "kind": "coding",
        "title": "Fix the login bug",
        "status": status,
        "adapter": "claude-code",
        "user_id": user_id,
        **extra,
    }


class FakeWatch:
    """Deterministic stand-in for the WatchService surface."""

    def __init__(self, jobs: Optional[List[Dict[str, Any]]] = None):
        self.jobs = jobs or []
        self.actions: List[tuple] = []

    async def list_user_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        return [j for j in self.jobs if j.get("user_id", user_id) == user_id]

    async def cancel_job(self, job_id: str, user_id: str = "0") -> bool:
        self.actions.append(("cancel", job_id, user_id))
        job = next((j for j in self.jobs if j["id"] == job_id), None)
        if job is None or job["status"] != "watching":
            return False
        job["status"] = "cancelled"
        return True

    async def get_job_trail(self, job_id: str, user_id: str = "0"):
        return [
            {"timestamp": "2026-07-11T09:00:00", "action": "started"},
            {"timestamp": "2026-07-11T09:05:00", "action": "poll_failed (1 consecutive)"},
        ]


def watch_job(job_id="wch_abc123", status="watching", user_id="0", **extra):
    return {
        "id": job_id,
        "kind": "watch",
        "title": "logo render",
        "status": status,
        "tool": "image-gen.check_status",
        "polls": 4,
        "user_id": user_id,
        **extra,
    }


class FakeBuffer:
    """Buffer memory double exposing only remove_by_metadata."""

    def __init__(self, items: Optional[List[Dict[str, Any]]] = None):
        self.items = items or []

    def remove_by_metadata(self, metadata_filter: Dict[str, Any], namespace: str = None) -> int:
        kept = []
        removed = 0
        for item in self.items:
            metadata = item.get("metadata", {})
            if all(metadata.get(k) == v for k, v in metadata_filter.items()):
                removed += 1
            else:
                kept.append(item)
        self.items = kept
        return removed


class FakeRouter:
    def __init__(self, delivered: bool = True):
        self.delivered = delivered
        self.calls: List[Dict[str, Any]] = []

    async def notify(self, *, user_id, message, channels=None, request_id=None, source=None):
        self.calls.append({"user_id": user_id, "message": message, "channels": channels})
        if self.delivered:
            return {"delivered": list(channels or []), "failed": [], "channels": channels}
        return {"delivered": [], "failed": list(channels or []), "channels": channels}


PROACTIVE_RAW = {
    "channels": {
        "chan-a": {"transformer": "sink-a"},
        "chan-b": {"transformer": "sink-b"},
    },
    "default_channel": "chan-a",
}


def make_overlord(
    *,
    commands_config: Optional[CommandsConfig] = "default",
    sops: Optional[Dict[str, Dict[str, Any]]] = None,
    multi_user: bool = False,
    with_proactive: bool = True,
    scheduler: Any = None,
    buffer: Any = None,
    router: Any = None,
    db_manager: Any = None,
    delegation: Any = None,
    watch: Any = None,
) -> Overlord:
    """Bare Overlord carrying only what the command path touches."""
    overlord = Overlord.__new__(Overlord)
    overlord._commands_config = (
        CommandsConfig() if commands_config == "default" else commands_config
    )
    overlord.sop_system = SimpleNamespace(sops=sops or {})
    overlord._ensure_sop_system = lambda: True
    overlord.formation_id = "test-formation"
    overlord.is_multi_user = multi_user
    overlord._proactive_config = parse_proactive_config(PROACTIVE_RAW) if with_proactive else None
    overlord.user_channel_store = (
        UserChannelStore(formation_id="test-formation") if with_proactive else None
    )
    overlord.notification_router = router
    overlord.heartbeat_service = None
    overlord.scheduler_service = scheduler
    overlord.delegation_service = delegation
    overlord.watch_service = watch
    overlord.buffer_memory = buffer
    overlord.db_manager = db_manager
    overlord.long_term_memory = None
    overlord._setup_flows = {}
    return overlord


async def run_command(overlord: Overlord, message: str, user_id="0", session_id="sess-1"):
    return await overlord._process_slash_command(message, user_id, session_id)


# ===================================================================
# Interception gate (inert-when-unconfigured, pinned)
# ===================================================================


class TestInterceptionGate:
    async def test_no_commands_block_means_no_interception(self):
        overlord = make_overlord(commands_config=parse_commands_config(None))
        assert overlord._commands_config is None
        assert await run_command(overlord, "/help") is None
        assert await run_command(overlord, "/setup") is None

    async def test_disabled_commands_block_means_no_interception(self):
        overlord = make_overlord(commands_config=parse_commands_config({"enabled": False}))
        assert await run_command(overlord, "/help") is None

    async def test_non_command_message_flows_through(self):
        overlord = make_overlord()
        assert await run_command(overlord, "hello there") is None
        assert await run_command(overlord, "/usr/bin/env") is None

    async def test_unknown_command_short_circuits_with_builtins_listed(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/nope")
        assert isinstance(response, MuxiResponse)
        assert "Unknown command: /nope" in response.content
        assert "/help" in response.content
        assert response.metadata["command_status"] == "unknown"

    async def test_sop_shadows_builtin_through_gate(self):
        sops = {"help": {"content": "Custom help.", "description": "Formation help"}}
        overlord = make_overlord(sops=sops)
        result = await run_command(overlord, "/help")
        # SOP resolution continues through the chat flow (not a MuxiResponse)
        assert not isinstance(result, MuxiResponse)
        assert result.message == 'Execute the "help" SOP.'

    async def test_disabled_builtin_reports_unknown(self):
        overlord = make_overlord(
            commands_config=parse_commands_config({"builtin": {"reset": False}})
        )
        response = await run_command(overlord, "/reset")
        assert isinstance(response, MuxiResponse)
        assert "Unknown command: /reset" in response.content


# ===================================================================
# Failure isolation
# ===================================================================


class TestFailureIsolation:
    async def test_handler_exception_becomes_friendly_reply(self):
        async def broken(ctx):
            raise RuntimeError("boom")

        overlord = make_overlord()
        response = await execute_builtin(
            overlord,
            BuiltinCommand(name="broken", description="x", usage="/broken", handler=broken),
            ParsedCommand(name="broken"),
            CommandsConfig(),
            {},
            "0",
            "sess-1",
        )
        assert isinstance(response, MuxiResponse)
        assert "unexpected error" in response.content
        assert response.metadata["command_status"] == "error"


# ===================================================================
# /help
# ===================================================================


class TestHelp:
    async def test_lists_builtins_sops_and_aliases(self):
        sops = {"ping": {"content": "x", "description": "Ping the agent"}}
        config = parse_commands_config({"aliases": {"tasks": "jobs"}})
        overlord = make_overlord(commands_config=config, sops=sops)
        response = await run_command(overlord, "/help")
        assert isinstance(response, MuxiResponse)
        for name in ("setup", "help", "status", "jobs", "identity", "channels", "preferences"):
            assert f"/{name}" in response.content
        assert "/ping - Ping the agent" in response.content
        assert "/tasks -> /jobs" in response.content
        assert response.metadata["command_status"] == "ok"

    async def test_disabled_builtin_hidden_from_help(self):
        overlord = make_overlord(
            commands_config=parse_commands_config({"builtin": {"jobs": False}})
        )
        response = await run_command(overlord, "/help")
        assert "/jobs" not in response.content

    async def test_shadowed_builtin_listed_as_formation_command(self):
        sops = {"status": {"content": "x", "description": "Custom status"}}
        overlord = make_overlord()
        ctx = BuiltinCommandContext(
            overlord=overlord,
            user_id="0",
            session_id=None,
            args="",
            config=CommandsConfig(),
            sops=sops,
        )
        reply = await BUILTIN_COMMANDS["help"].handler(ctx)
        assert "/status - Custom status" in reply
        # Not duplicated in the built-in section
        assert reply.count("/status") == 1


# ===================================================================
# /status
# ===================================================================


class TestStatus:
    async def test_overview_with_services(self):
        scheduler = FakeScheduler(
            jobs=[
                {"id": "job_1", "title": "A", "status": "ACTIVE", "is_recurring": True},
                {"id": "job_2", "title": "B", "status": "PAUSED", "is_recurring": True},
            ]
        )
        overlord = make_overlord(scheduler=scheduler)
        await overlord.user_channel_store.set_preferences(
            "0", preferred_channel="chan-a", timezone="Europe/London"
        )
        response = await run_command(overlord, "/status")
        assert "Formation: test-formation" in response.content
        assert "Preferred channel: chan-a" in response.content
        assert "Timezone: Europe/London" in response.content
        assert "chan-a, chan-b" in response.content
        assert "1 active, 1 paused" in response.content

    async def test_overview_without_services(self):
        overlord = make_overlord(with_proactive=False)
        response = await run_command(overlord, "/status")
        assert "Notifications: not configured" in response.content
        assert "scheduler not enabled" in response.content


# ===================================================================
# /jobs
# ===================================================================


def _job(job_id: str, title: str, status: str = "ACTIVE") -> Dict[str, Any]:
    return {
        "id": job_id,
        "title": title,
        "status": status,
        "is_recurring": True,
        "cron_expression": "0 9 * * *",
        "last_run_at": None,
        "total_runs": 0,
        "total_failures": 0,
    }


class TestJobs:
    async def test_no_scheduler_is_friendly(self):
        overlord = make_overlord(scheduler=None)
        response = await run_command(overlord, "/jobs")
        assert "scheduler is not enabled" in response.content
        assert response.metadata["command_status"] == "ok"

    async def test_empty_listing(self):
        overlord = make_overlord(scheduler=FakeScheduler())
        response = await run_command(overlord, "/jobs")
        assert "no scheduled tasks" in response.content

    async def test_listing_shows_jobs(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email"), _job("job_b", "Report")])
        overlord = make_overlord(scheduler=scheduler)
        response = await run_command(overlord, "/jobs")
        assert "1. Check email [job_a]" in response.content
        assert "2. Report [job_b]" in response.content
        assert "0 9 * * *" in response.content

    async def test_pause_by_index_and_resume_by_id(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        overlord = make_overlord(scheduler=scheduler)

        response = await run_command(overlord, "/jobs pause 1")
        assert 'Paused "Check email"' in response.content
        assert ("pause", "job_a", "0") in scheduler.actions

        response = await run_command(overlord, "/jobs resume job_a")
        assert 'Resumed "Check email"' in response.content

    async def test_cancel(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        overlord = make_overlord(scheduler=scheduler)
        response = await run_command(overlord, "/jobs cancel job_a")
        assert 'Cancelled "Check email"' in response.content
        assert scheduler.jobs == []

    async def test_unknown_job_id(self):
        overlord = make_overlord(scheduler=FakeScheduler(jobs=[_job("job_a", "A")]))
        response = await run_command(overlord, "/jobs pause job_of_someone_else")
        assert "found among your tasks" in response.content

    async def test_logs(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        overlord = make_overlord(scheduler=scheduler)
        response = await run_command(overlord, "/jobs logs 1")
        assert 'History for "Check email"' in response.content
        assert "created" in response.content

    async def test_usage_on_bad_args(self):
        overlord = make_overlord(scheduler=FakeScheduler())
        response = await run_command(overlord, "/jobs frobnicate")
        assert "Usage: /jobs" in response.content


# ===================================================================
# /jobs x coding delegations (coding-agent delegation)
# ===================================================================


class TestJobsCoding:
    async def test_coding_only_formation_lists_coding_tasks(self):
        # No scheduler, but a delegation service: /jobs still works.
        delegation = FakeDelegation(jobs=[coding_job()])
        overlord = make_overlord(scheduler=None, delegation=delegation)
        response = await run_command(overlord, "/jobs")
        assert "1 coding task(s)" in response.content
        assert "Fix the login bug [cdg_abc123]" in response.content
        assert "claude-code" in response.content

    async def test_coding_only_empty_listing(self):
        overlord = make_overlord(scheduler=None, delegation=FakeDelegation())
        response = await run_command(overlord, "/jobs")
        assert "no background tasks" in response.content

    async def test_combined_listing_continuous_index(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        delegation = FakeDelegation(jobs=[coding_job()])
        overlord = make_overlord(scheduler=scheduler, delegation=delegation)
        response = await run_command(overlord, "/jobs")
        assert "1. Check email [job_a]" in response.content
        # The coding section continues the index (2, not 1).
        assert "2. Fix the login bug [cdg_abc123]" in response.content

    async def test_cancel_coding_task_by_continuous_index(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        delegation = FakeDelegation(jobs=[coding_job()])
        overlord = make_overlord(scheduler=scheduler, delegation=delegation)
        response = await run_command(overlord, "/jobs cancel 2")
        assert "Cancelled coding task" in response.content
        assert "resumed" in response.content  # session retained
        assert ("cancel", "cdg_abc123", "0") in delegation.actions

    async def test_cancel_non_running_coding_task(self):
        delegation = FakeDelegation(jobs=[coding_job(status="completed")])
        overlord = make_overlord(scheduler=None, delegation=delegation)
        response = await run_command(overlord, "/jobs cancel cdg_abc123")
        assert "Could not cancel" in response.content

    async def test_pause_and_resume_unsupported_for_coding(self):
        delegation = FakeDelegation(jobs=[coding_job()])
        overlord = make_overlord(scheduler=None, delegation=delegation)
        for action in ("pause", "resume"):
            response = await run_command(overlord, f"/jobs {action} cdg_abc123")
            assert "not supported for coding tasks" in response.content

    async def test_logs_for_coding_task(self):
        delegation = FakeDelegation(jobs=[coding_job(status="completed")])
        overlord = make_overlord(scheduler=None, delegation=delegation)
        response = await run_command(overlord, "/jobs logs cdg_abc123")
        assert 'History for coding task "Fix the login bug"' in response.content
        assert "started" in response.content
        assert "completed" in response.content

    async def test_scheduler_actions_untouched_by_coding_presence(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        delegation = FakeDelegation(jobs=[coding_job()])
        overlord = make_overlord(scheduler=scheduler, delegation=delegation)
        response = await run_command(overlord, "/jobs pause job_a")
        assert 'Paused "Check email"' in response.content
        assert delegation.actions == []

    async def test_neither_service_stays_friendly(self):
        overlord = make_overlord(scheduler=None, delegation=None)
        response = await run_command(overlord, "/jobs")
        assert "scheduler is not enabled" in response.content


# ===================================================================
# /jobs x watch jobs (remote async tools)
# ===================================================================


class TestJobsWatch:
    async def test_watch_only_formation_lists_watches(self):
        # No scheduler, no delegation, but a watch service: /jobs works.
        watch = FakeWatch(jobs=[watch_job()])
        overlord = make_overlord(scheduler=None, watch=watch)
        response = await run_command(overlord, "/jobs")
        assert "1 watched job(s)" in response.content
        assert "logo render [wch_abc123]" in response.content
        assert "image-gen.check_status" in response.content
        assert "Polls: 4" in response.content

    async def test_combined_listing_continuous_index(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        delegation = FakeDelegation(jobs=[coding_job()])
        watch = FakeWatch(jobs=[watch_job()])
        overlord = make_overlord(scheduler=scheduler, delegation=delegation, watch=watch)
        response = await run_command(overlord, "/jobs")
        assert "1. Check email [job_a]" in response.content
        assert "2. Fix the login bug [cdg_abc123]" in response.content
        # The watch section continues the index (3, not 1).
        assert "3. logo render [wch_abc123]" in response.content

    async def test_cancel_watch_by_continuous_index(self):
        scheduler = FakeScheduler(jobs=[_job("job_a", "Check email")])
        watch = FakeWatch(jobs=[watch_job()])
        overlord = make_overlord(scheduler=scheduler, watch=watch)
        response = await run_command(overlord, "/jobs cancel 2")
        assert "Stopped watching" in response.content
        assert ("cancel", "wch_abc123", "0") in watch.actions
        assert scheduler.jobs, "the scheduled job must not be touched"

    async def test_cancel_non_active_watch(self):
        watch = FakeWatch(jobs=[watch_job(status="completed")])
        overlord = make_overlord(scheduler=None, watch=watch)
        response = await run_command(overlord, "/jobs cancel wch_abc123")
        assert "Could not cancel" in response.content

    async def test_pause_and_resume_unsupported_for_watches(self):
        watch = FakeWatch(jobs=[watch_job()])
        overlord = make_overlord(scheduler=None, watch=watch)
        for action in ("pause", "resume"):
            response = await run_command(overlord, f"/jobs {action} wch_abc123")
            assert "not supported for watched jobs" in response.content
        assert watch.actions == []

    async def test_logs_for_watch(self):
        watch = FakeWatch(jobs=[watch_job()])
        overlord = make_overlord(scheduler=None, watch=watch)
        response = await run_command(overlord, "/jobs logs wch_abc123")
        assert 'History for watch "logo render"' in response.content
        assert "Polls: 4" in response.content
        assert "poll_failed" in response.content


# ===================================================================
# /channels
# ===================================================================


class TestChannels:
    async def test_no_proactive_block_is_friendly(self):
        overlord = make_overlord(with_proactive=False)
        response = await run_command(overlord, "/channels")
        assert "no notification channels" in response.content

    async def test_proactive_block_with_zero_channels_is_friendly(self):
        # A 'proactive' block can exist with no declared channels: the store
        # is live but there is nothing to list, default, or test.
        overlord = make_overlord()
        overlord._proactive_config = parse_proactive_config({"channels": {}})
        assert overlord.user_channel_store is not None
        for command in ("/channels", "/channels default chan-a", "/channels test chan-a"):
            response = await run_command(overlord, command)
            assert "no notification channels" in response.content, command
            assert "Commands:" not in response.content, command

    async def test_listing_marks_default_and_last(self):
        overlord = make_overlord()
        await overlord.user_channel_store.set_preferences("0", preferred_channel="chan-b")
        await overlord.user_channel_store.record_inbound("0", "chan-a")
        response = await run_command(overlord, "/channels")
        assert "- chan-a (last used)" in response.content
        assert "- chan-b (default)" in response.content

    async def test_default_sets_preference(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/channels default chan-b")
        assert "set to chan-b" in response.content
        state = await overlord.user_channel_store.get_state("0")
        assert state["preferred_channel"] == "chan-b"

    async def test_default_rejects_undeclared_channel(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/channels default nope")
        assert "Unknown channel 'nope'" in response.content
        state = await overlord.user_channel_store.get_state("0")
        assert state["preferred_channel"] is None

    async def test_test_subcommand_routes_through_router(self):
        router = FakeRouter(delivered=True)
        overlord = make_overlord(router=router)
        response = await run_command(overlord, "/channels test chan-a")
        assert "Sent a test notification to chan-a" in response.content
        assert router.calls[0]["channels"] == ["chan-a"]

    async def test_test_subcommand_reports_failure(self):
        overlord = make_overlord(router=FakeRouter(delivered=False))
        response = await run_command(overlord, "/channels test chan-a")
        assert "could not be delivered" in response.content


# ===================================================================
# /preferences
# ===================================================================


class TestPreferences:
    async def test_no_proactive_block_is_friendly(self):
        overlord = make_overlord(with_proactive=False)
        response = await run_command(overlord, "/preferences")
        assert "no notification channels" in response.content

    async def test_show_defaults(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/preferences")
        assert "Notification channel: not set" in response.content
        assert "Timezone: not set" in response.content

    async def test_set_and_read_back_timezone(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/preferences timezone Europe/London")
        assert "Timezone set to Europe/London" in response.content
        response = await run_command(overlord, "/preferences")
        assert "Timezone: Europe/London" in response.content

    async def test_invalid_timezone_rejected(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/preferences timezone Mars/Olympus")
        assert "Unknown timezone" in response.content

    async def test_clear_timezone(self):
        overlord = make_overlord()
        await run_command(overlord, "/preferences timezone UTC")
        response = await run_command(overlord, "/preferences timezone clear")
        assert "Timezone cleared" in response.content
        state = await overlord.user_channel_store.get_state("0")
        assert state["timezone"] is None

    async def test_channel_subcommand(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/preferences channel chan-a")
        assert "set to chan-a" in response.content
        state = await overlord.user_channel_store.get_state("0")
        assert state["preferred_channel"] == "chan-a"

    async def test_usage_on_bad_args(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/preferences style brief")
        assert "Usage: /preferences" in response.content


# ===================================================================
# /reset
# ===================================================================


class TestReset:
    async def test_clears_current_session_only(self):
        buffer = FakeBuffer(
            items=[
                {"metadata": {"user_id": "0", "session_id": "sess-1", "role": "user"}},
                {"metadata": {"user_id": "0", "session_id": "sess-1", "role": "assistant"}},
                {"metadata": {"user_id": "0", "session_id": "sess-2", "role": "user"}},
                {"metadata": {"user_id": "other", "session_id": "sess-1", "role": "user"}},
            ]
        )
        overlord = make_overlord(buffer=buffer)
        response = await run_command(overlord, "/reset", user_id="0", session_id="sess-1")
        assert "2 message(s)" in response.content
        assert len(buffer.items) == 2  # other session and other user untouched

    async def test_no_session_is_friendly(self):
        overlord = make_overlord(buffer=FakeBuffer())
        response = await run_command(overlord, "/reset", session_id=None)
        assert "no active session" in response.content.lower()

    async def test_no_buffer_is_friendly(self):
        overlord = make_overlord(buffer=None)
        response = await run_command(overlord, "/reset")
        assert "not available" in response.content

    async def test_empty_session_reports_nothing_to_clear(self):
        overlord = make_overlord(buffer=FakeBuffer())
        response = await run_command(overlord, "/reset")
        assert "no conversation history" in response.content


# ===================================================================
# /identity
# ===================================================================


class _SqliteDBManager:
    """Minimal async db_manager double backed by in-memory SQLite."""

    def __init__(self, session_maker):
        self._session_maker = session_maker

    def get_async_session(self):
        return self._session_maker()


@pytest.fixture
async def sqlite_db_manager():
    # Disposed on teardown: each pooled aiosqlite connection owns a worker
    # thread that outlives the test's event loop otherwise.
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=[User.__table__, UserIdentifier.__table__]
            )
        )
    yield _SqliteDBManager(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


class TestIdentity:
    async def test_single_user_mode_is_friendly(self):
        overlord = make_overlord(multi_user=False)
        response = await run_command(overlord, "/identity")
        assert "single-user mode" in response.content

    async def test_no_database_is_friendly(self):
        overlord = make_overlord(multi_user=True, db_manager=None)
        response = await run_command(overlord, "/identity")
        assert "requires persistent memory" in response.content

    async def test_link_list_unlink_roundtrip(self, sqlite_db_manager):
        overlord = make_overlord(multi_user=True, db_manager=sqlite_db_manager)

        response = await run_command(overlord, "/identity", user_id="ran@example.com")
        assert "No other identifiers are linked yet" in response.content

        response = await run_command(
            overlord, "/identity link U12345 slack", user_id="ran@example.com"
        )
        assert "Linked u12345 (slack)" in response.content

        response = await run_command(overlord, "/identity", user_id="ran@example.com")
        assert "ran@example.com (current)" in response.content
        assert "u12345 (slack)" in response.content

        response = await run_command(overlord, "/identity unlink U12345", user_id="ran@example.com")
        assert "Unlinked u12345" in response.content

        response = await run_command(overlord, "/identity", user_id="ran@example.com")
        assert "u12345" not in response.content

    async def test_link_normalizes_mixed_case_type(self, sqlite_db_manager):
        overlord = make_overlord(multi_user=True, db_manager=sqlite_db_manager)
        response = await run_command(
            overlord, "/identity link tg-1 Telegram", user_id="ran@example.com"
        )
        assert "Linked tg-1 (telegram)" in response.content
        response = await run_command(overlord, "/identity", user_id="ran@example.com")
        assert "tg-1 (telegram)" in response.content
        assert "Telegram" not in response.content

    async def test_link_conflict_with_other_user(self, sqlite_db_manager):
        overlord = make_overlord(multi_user=True, db_manager=sqlite_db_manager)

        # bob links an identifier to his own account first
        await run_command(overlord, "/identity link shared-handle", user_id="bob@example.com")
        response = await run_command(
            overlord, "/identity link shared-handle", user_id="alice@example.com"
        )
        assert "already linked to a different user" in response.content

    async def test_cannot_unlink_current_identity(self, sqlite_db_manager):
        overlord = make_overlord(multi_user=True, db_manager=sqlite_db_manager)
        response = await run_command(
            overlord, "/identity unlink ran@example.com", user_id="ran@example.com"
        )
        assert "cannot unlink" in response.content.lower()

    async def test_usage_on_bad_args(self, sqlite_db_manager):
        overlord = make_overlord(multi_user=True, db_manager=sqlite_db_manager)
        response = await run_command(overlord, "/identity frobnicate", user_id="ran@example.com")
        assert "Usage: /identity" in response.content


# ===================================================================
# /setup (deterministic multi-step flow)
# ===================================================================


class TestSetupFlow:
    async def test_no_proactive_block_is_friendly(self):
        overlord = make_overlord(with_proactive=False)
        response = await run_command(overlord, "/setup")
        assert "Nothing to set up" in response.content
        assert overlord._setup_flows == {}

    async def test_full_flow_sets_channel_and_timezone(self):
        overlord = make_overlord()
        response = await run_command(overlord, "/setup")
        assert "Available channels: chan-a, chan-b" in response.content
        assert "0" in overlord._setup_flows

        # Plain replies are intercepted while the flow is active
        response = await run_command(overlord, "chan-b")
        assert "Notifications will go to chan-b" in response.content
        assert "timezone" in response.content.lower()

        response = await run_command(overlord, "Europe/London")
        assert "You're all set" in response.content
        assert "chan-b" in response.content
        assert "Europe/London" in response.content
        assert overlord._setup_flows == {}

        state = await overlord.user_channel_store.get_state("0")
        assert state["preferred_channel"] == "chan-b"
        assert state["timezone"] == "Europe/London"

    async def test_invalid_answers_reask_without_advancing(self):
        overlord = make_overlord()
        await run_command(overlord, "/setup")
        response = await run_command(overlord, "carrier-pigeon")
        assert "don't recognize that channel" in response.content
        response = await run_command(overlord, "chan-a")
        assert "Notifications will go to chan-a" in response.content
        response = await run_command(overlord, "Not/AZone")
        assert "don't recognize" in response.content
        response = await run_command(overlord, "UTC")
        assert "You're all set" in response.content

    async def test_skip_leaves_state_untouched(self):
        overlord = make_overlord()
        await run_command(overlord, "/setup")
        await run_command(overlord, "skip")
        response = await run_command(overlord, "skip")
        assert "You're all set" in response.content
        state = await overlord.user_channel_store.get_state("0")
        assert state["preferred_channel"] is None
        assert state["timezone"] is None

    async def test_cancel_stops_the_flow(self):
        overlord = make_overlord()
        await run_command(overlord, "/setup")
        response = await run_command(overlord, "cancel")
        assert "Setup cancelled" in response.content
        # Next plain message flows through to the LLM path
        assert await run_command(overlord, "chan-a") is None

    async def test_other_command_cancels_the_flow(self):
        overlord = make_overlord()
        await run_command(overlord, "/setup")
        await run_command(overlord, "/help")
        assert overlord._setup_flows == {}
        assert await run_command(overlord, "chan-a") is None

    async def test_expired_flow_replies_with_expiry_message(self):
        overlord = make_overlord()
        await run_command(overlord, "/setup")
        overlord._setup_flows["0"].updated_at -= 10_000
        response = await run_command(overlord, "chan-a")
        # The pending answer must NOT fall through to the LLM unexplained
        assert response is not None
        assert "Setup session expired" in response.content
        assert overlord._setup_flows == {}
        # Subsequent plain messages flow through normally again
        assert await run_command(overlord, "chan-a") is None

    async def test_flow_error_is_isolated(self):
        overlord = make_overlord()
        await run_command(overlord, "/setup")

        # Break the store so the flow answer handler raises internally
        async def broken_set_preferences(*args, **kwargs):
            raise RuntimeError("store exploded")

        overlord.user_channel_store.set_preferences = broken_set_preferences
        reply = await handle_setup_answer(overlord, "0", "sess-1", "chan-a", CommandsConfig())
        assert "unexpected error" in reply
        assert overlord._setup_flows == {}

    async def test_flows_are_per_user(self):
        overlord = make_overlord(multi_user=True)
        await run_command(overlord, "/setup", user_id="alice")
        assert await run_command(overlord, "chan-a", user_id="bob") is None
        response = await run_command(overlord, "chan-a", user_id="alice")
        assert "Notifications will go to chan-a" in response.content
