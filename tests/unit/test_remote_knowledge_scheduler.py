"""Unit tests for the remote knowledge sync scheduler (Phase 3).

Covers cron schedule resolution, due-time gating, per-source lock
contention (no overlapping syncs), retry with exponential backoff, manual
sync triggers, and the incremental re-embed hook. The SyncManager is
stubbed so no network or filesystem sync happens.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Dict, List
from unittest import mock

import pytest

from muxi.runtime.formation.agents.knowledge.remote.scheduler import (
    KnowledgeSyncService,
    RetryPolicy,
    resolve_cron_expression,
)
from muxi.runtime.formation.agents.knowledge.remote.sync import SyncResult

NOW = datetime(2026, 7, 9, 10, 0, 0, tzinfo=timezone.utc)

SCHEDULED_SOURCE = {
    "url": "stub://source",
    "id": "scheduled-source",
    "description": "scheduled stub source",
    "schedule": "*/15 * * * *",
}

MANUAL_SOURCE = {
    "url": "stub://manual",
    "id": "manual-source",
    "description": "manual-only stub source",
}


class StubSyncManager:
    """Records sync calls and returns scripted results."""

    instances: List["StubSyncManager"] = []
    script: Dict[str, SyncResult] = {}
    delay: float = 0.0

    def __init__(self, agent_id: str, formation_id: str = "default-formation", root_dir=None):
        self.agent_id = agent_id
        self.formation_id = formation_id
        self.sync_calls: List[Dict] = []
        StubSyncManager.instances.append(self)

    async def sync_source(self, raw_source, trigger="startup"):
        self.sync_calls.append({"source": raw_source, "trigger": trigger})
        if StubSyncManager.delay:
            await asyncio.sleep(StubSyncManager.delay)
        source_id = raw_source.get("id", "")
        result = StubSyncManager.script.get(source_id)
        if result is None:
            result = SyncResult(
                source_id=source_id,
                url=raw_source.get("url", ""),
                status="success",
                content_dir=f"/mirror/{source_id}/content",
            )
        return result

    def synthetic_local_source(self, config, result):
        return {
            "path": result.content_dir,
            "name": config.source_id,
            "description": config.description,
        }


@pytest.fixture(autouse=True)
def stub_sync_manager():
    StubSyncManager.instances = []
    StubSyncManager.script = {}
    StubSyncManager.delay = 0.0
    with mock.patch(
        "muxi.runtime.formation.agents.knowledge.remote.scheduler.SyncManager",
        StubSyncManager,
    ):
        yield


def make_overlord(handler=None):
    agent = SimpleNamespace(knowledge_handler=handler)
    return SimpleNamespace(agents={"agent-x": agent})


def make_service(sources=None, handler=None, agent_id="agent-x"):
    return KnowledgeSyncService(
        overlord=make_overlord(handler),
        agent_sources={agent_id: sources or [dict(SCHEDULED_SOURCE)]},
    )


def scripted_result(source_id, status="success", changed=None, deleted=None):
    result = SyncResult(
        source_id=source_id,
        url="stub://source",
        status=status,
        content_dir=f"/mirror/{source_id}/content",
        error="boom" if status == "failed" else "",
    )
    result.changed_paths = list(changed or [])
    result.deleted_paths = list(deleted or [])
    return result


class TestCronResolution:
    def test_aliases_resolve_to_cron(self):
        assert resolve_cron_expression("@hourly") == "0 * * * *"
        assert resolve_cron_expression("@daily") == "0 0 * * *"
        assert resolve_cron_expression("@weekly") == "0 0 * * 0"

    def test_startup_and_missing_are_not_periodic(self):
        assert resolve_cron_expression("@startup") is None
        assert resolve_cron_expression(None) is None
        assert resolve_cron_expression("") is None

    def test_raw_cron_passes_through(self):
        assert resolve_cron_expression("*/15 * * * *") == "*/15 * * * *"


class TestRetryPolicy:
    def test_defaults(self):
        policy = RetryPolicy.from_dict({})
        assert policy.max_attempts == 3
        assert policy.initial_delay == 5.0
        assert policy.max_delay == 300.0
        assert policy.exponential_base == 2.0

    def test_backoff_progression_and_cap(self):
        policy = RetryPolicy(initial_delay=5, max_delay=30, exponential_base=2)
        assert policy.delay_for_attempt(1) == 5
        assert policy.delay_for_attempt(2) == 10
        assert policy.delay_for_attempt(3) == 20
        assert policy.delay_for_attempt(4) == 30  # capped
        assert policy.delay_for_attempt(10) == 30


class TestScheduling:
    def test_scheduled_sources_get_next_fire(self):
        service = make_service([dict(SCHEDULED_SOURCE), dict(MANUAL_SOURCE)])
        entries = {e.source_id: e for e in service.sources_for_agent("agent-x")}
        assert entries["scheduled-source"].next_fire is not None
        assert entries["manual-source"].next_fire is None
        assert service.has_scheduled_sources
        assert service.scheduled_source_count == 1

    def test_manual_only_service_has_no_scheduled_sources(self):
        service = make_service([dict(MANUAL_SOURCE)])
        assert not service.has_scheduled_sources

    async def test_tick_before_due_does_not_sync(self):
        service = make_service()
        entry = service.sources_for_agent("agent-x")[0]
        await service.tick(now=entry.next_fire - timedelta(seconds=1))
        assert StubSyncManager.instances == []

    async def test_tick_at_due_time_syncs_and_reschedules(self):
        service = make_service()
        entry = service.sources_for_agent("agent-x")[0]
        due = entry.next_fire
        await service.tick(now=due)
        assert len(StubSyncManager.instances) == 1
        assert StubSyncManager.instances[0].sync_calls[0]["trigger"] == "scheduled"
        # Rescheduled to the next cron slot after the sync
        assert entry.next_fire > due

    async def test_tick_isolated_from_sync_crash(self):
        service = make_service()
        entry = service.sources_for_agent("agent-x")[0]
        with mock.patch.object(StubSyncManager, "sync_source", side_effect=RuntimeError("explode")):
            await service.tick(now=entry.next_fire)  # must not raise


class TestRetryBackoff:
    async def test_failure_schedules_exponential_retries_then_cron(self):
        source = {**SCHEDULED_SOURCE, "retry": {"initial_delay": 5, "exponential_base": 2}}
        service = make_service([source])
        entry = service.sources_for_agent("agent-x")[0]
        StubSyncManager.script["scheduled-source"] = scripted_result(
            "scheduled-source", status="failed"
        )

        first_due = entry.next_fire
        await service.tick(now=first_due)
        assert entry.failed_attempts == 1
        assert entry.next_fire == first_due + timedelta(seconds=5)

        second_due = entry.next_fire
        await service.tick(now=second_due)
        assert entry.failed_attempts == 2
        assert entry.next_fire == second_due + timedelta(seconds=10)

        # Third failure exhausts max_attempts (default 3): back to cron
        third_due = entry.next_fire
        await service.tick(now=third_due)
        assert entry.failed_attempts == 0
        assert entry.next_fire.minute % 15 == 0
        assert entry.next_fire > third_due

    async def test_success_resets_failed_attempts(self):
        service = make_service()
        entry = service.sources_for_agent("agent-x")[0]
        StubSyncManager.script["scheduled-source"] = scripted_result(
            "scheduled-source", status="failed"
        )
        await service.tick(now=entry.next_fire)
        assert entry.failed_attempts == 1

        StubSyncManager.script["scheduled-source"] = scripted_result("scheduled-source")
        await service.tick(now=entry.next_fire)
        assert entry.failed_attempts == 0

    async def test_backoff_delay_capped_at_max_delay(self):
        source = {
            **SCHEDULED_SOURCE,
            "retry": {"initial_delay": 100, "max_delay": 120, "max_attempts": 5},
        }
        service = make_service([source])
        entry = service.sources_for_agent("agent-x")[0]
        StubSyncManager.script["scheduled-source"] = scripted_result(
            "scheduled-source", status="failed"
        )
        due = entry.next_fire
        await service.tick(now=due)
        assert entry.next_fire == due + timedelta(seconds=100)
        due = entry.next_fire
        await service.tick(now=due)
        assert entry.next_fire == due + timedelta(seconds=120)  # capped, not 200


class TestLockContention:
    async def test_concurrent_syncs_of_same_source_skip(self):
        StubSyncManager.delay = 0.2
        service = make_service([dict(MANUAL_SOURCE)])

        first, second = await asyncio.gather(
            service.sync_now("agent-x"),
            service.sync_now("agent-x"),
        )
        statuses = sorted([first[0]["status"], second[0]["status"]])
        assert statuses == ["skipped", "success"]
        # Only one sync actually ran
        total_calls = sum(len(i.sync_calls) for i in StubSyncManager.instances)
        assert total_calls == 1

    async def test_scheduled_tick_skips_while_manual_sync_running(self):
        StubSyncManager.delay = 0.2
        service = make_service()
        entry = service.sources_for_agent("agent-x")[0]
        due = entry.next_fire

        manual = asyncio.create_task(service.sync_now("agent-x", "scheduled-source"))
        await asyncio.sleep(0.05)
        await service.tick(now=due)
        results = await manual

        assert results[0]["status"] == "success"
        # The scheduled slot was skipped, next_fire untouched
        assert entry.next_fire == due
        total_calls = sum(len(i.sync_calls) for i in StubSyncManager.instances)
        assert total_calls == 1

    async def test_different_sources_do_not_contend(self):
        StubSyncManager.delay = 0.1
        service = make_service([dict(SCHEDULED_SOURCE), dict(MANUAL_SOURCE)])
        results = await asyncio.gather(
            service.sync_now("agent-x", "scheduled-source"),
            service.sync_now("agent-x", "manual-source"),
        )
        assert [r[0]["status"] for r in results] == ["success", "success"]


class TestManualTrigger:
    async def test_sync_now_all_sources(self):
        service = make_service([dict(SCHEDULED_SOURCE), dict(MANUAL_SOURCE)])
        results = await service.sync_now("agent-x")
        assert {r["source_id"] for r in results} == {"scheduled-source", "manual-source"}
        assert all(r["status"] == "success" for r in results)
        triggers = [call["trigger"] for i in StubSyncManager.instances for call in i.sync_calls]
        assert triggers == ["manual", "manual"]

    async def test_sync_now_single_source(self):
        service = make_service([dict(SCHEDULED_SOURCE), dict(MANUAL_SOURCE)])
        results = await service.sync_now("agent-x", source_id="manual-source")
        assert len(results) == 1
        assert results[0]["source_id"] == "manual-source"

    async def test_sync_now_unknown_agent_raises(self):
        service = make_service()
        with pytest.raises(KeyError):
            await service.sync_now("nope")

    async def test_sync_now_unknown_source_raises(self):
        service = make_service()
        with pytest.raises(KeyError):
            await service.sync_now("agent-x", source_id="nope")


class TestReembedding:
    def make_handler(self):
        handler = mock.MagicMock()
        handler.refresh_remote_source = mock.AsyncMock(return_value=3)
        return handler

    async def test_changed_files_trigger_incremental_reembed(self):
        handler = self.make_handler()
        service = make_service([dict(MANUAL_SOURCE)], handler=handler)
        StubSyncManager.script["manual-source"] = scripted_result(
            "manual-source", changed=["a.md", "docs/b.md"], deleted=["old.md"]
        )
        await service.sync_now("agent-x")

        handler.refresh_remote_source.assert_awaited_once()
        source_config, changed, deleted = handler.refresh_remote_source.await_args.args
        assert source_config["path"] == "/mirror/manual-source/content"
        assert changed == [
            "/mirror/manual-source/content/a.md",
            "/mirror/manual-source/content/docs/b.md",
        ]
        assert deleted == ["/mirror/manual-source/content/old.md"]

    async def test_no_changes_skip_reembed(self):
        handler = self.make_handler()
        service = make_service([dict(MANUAL_SOURCE)], handler=handler)
        await service.sync_now("agent-x")
        handler.refresh_remote_source.assert_not_awaited()

    async def test_failed_sync_skips_reembed(self):
        handler = self.make_handler()
        service = make_service([dict(MANUAL_SOURCE)], handler=handler)
        StubSyncManager.script["manual-source"] = scripted_result(
            "manual-source", status="failed", changed=["a.md"]
        )
        await service.sync_now("agent-x")
        handler.refresh_remote_source.assert_not_awaited()

    async def test_missing_knowledge_handler_tolerated(self):
        service = make_service([dict(MANUAL_SOURCE)], handler=None)
        StubSyncManager.script["manual-source"] = scripted_result("manual-source", changed=["a.md"])
        results = await service.sync_now("agent-x")
        assert results[0]["status"] == "success"

    async def test_reembed_failure_is_isolated(self):
        handler = self.make_handler()
        handler.refresh_remote_source.side_effect = RuntimeError("embed exploded")
        service = make_service([dict(MANUAL_SOURCE)], handler=handler)
        StubSyncManager.script["manual-source"] = scripted_result("manual-source", changed=["a.md"])
        results = await service.sync_now("agent-x")  # must not raise
        assert results[0]["status"] == "success"
