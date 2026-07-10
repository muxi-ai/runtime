"""Unit tests for the memory synthesis cadences (Memory Ingestion maturation).

Covers:

  * Overlord wiring: inert when memory.ingestion is unconfigured (pin),
    service created + registered as a scheduler periodic task when
    configured, degradation without a scheduler, and the master
    synthesis.enabled switch.
  * tick() interval gating per cadence, individually disableable.
  * Hot cadence: entity resolution for users with new events; the
    durable per-user cursor gates re-processing.
  * Warm/cold cadences: deterministic pattern extraction (preferences,
    domain expertise, schedule) written event-first with per-(kind,
    ISO week) idempotency keys and decaying decay_rate.
  * Cold-cold: per-user rebuild from the event log (the substrate's
    replay machinery), deterministic across replays, failure-isolated
    per user.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import MemoryEventService
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    EVENT_INTERACTION_TURN,
    EVENT_MEMORY_INGESTED,
    SOURCE_INTERACTION,
    SOURCE_SYNTHESIS,
)
from muxi.runtime.services.memory.events.projectors import KnowledgeGraphProjector
from muxi.runtime.services.memory.graph.models import STATUS_MERGED
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.ingest.config import parse_ingestion_config
from muxi.runtime.services.memory.synthesis import (
    CADENCE_COLD,
    CADENCE_COLD_COLD,
    CADENCE_HOT,
    CADENCE_WARM,
    CADENCES,
    MemorySynthesisService,
)

FORMATION_ID = "synthesis-test-formation"
USER = "u1"

NOW = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)  # a Wednesday


class RecordingLTM:
    def __init__(self):
        self.rows = []

    async def add(self, content, metadata=None, user_id=None, collection=None, scope=None):
        self.rows.append(
            {"content": content, "metadata": dict(metadata or {}), "collection": collection}
        )
        return f"m{len(self.rows)}"


def make_settings(**synthesis_overrides):
    return parse_ingestion_config({"synthesis": synthesis_overrides})


@pytest.fixture
def env(tmp_path):
    """Real substrate + graph + a minimal overlord namespace."""
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/synthesis.db")
    db_manager.create_tables(Base.metadata)
    events = MemoryEventService(db_manager, FORMATION_ID, config={"enabled": True})
    graph = KnowledgeGraphService(db_manager, FORMATION_ID, config={}, event_log=events)
    events.register_projector(KnowledgeGraphProjector(graph))
    overlord = SimpleNamespace(
        memory_events=events,
        knowledge_graph=graph,
        long_term_memory=RecordingLTM(),
    )
    yield overlord, events, graph
    db_manager.engine.dispose()


def make_service(overlord, *, baseline=None, **synthesis_overrides):
    parsed = make_settings(**synthesis_overrides)
    service = MemorySynthesisService(overlord, parsed.synthesis, parsed.entity_resolution)
    if baseline is not None:
        # Freeze the startup baseline for deterministic gating tests
        # (construction stamps the real clock).
        service._last_run = {cadence: baseline for cadence in CADENCES}
    return service


async def seed_ingestion_event(events, source_id="m-1"):
    return await events.record(
        user_id=USER,
        event_type=EVENT_MEMORY_INGESTED,
        payload={"content": "hello"},
        source="gmail",
        source_id=source_id,
    )


async def seed_duplicate_identities(graph):
    full = await graph.storage.upsert_entity(
        USER, "person", "Ryan Leveille", attributes={"email": "ryan@nabo.dev"}, confidence=0.9
    )
    await graph.storage.upsert_entity(
        USER, "person", "Ryan", attributes={"email": "ryan@nabo.dev"}, confidence=0.8
    )
    return full


# ----------------------------------------------------------------------
# Overlord wiring (inertness pin + registration)
# ----------------------------------------------------------------------


class FakeScheduler:
    def __init__(self):
        self.periodic_tasks = []

    def register_periodic_task(self, task):
        self.periodic_tasks.append(task)


def overlord_stub(memory_config, *, scheduler=True, memory_events=None):
    ingestion_config = (memory_config or {}).get("ingestion")
    settings = (
        parse_ingestion_config(ingestion_config)
        if isinstance(ingestion_config, dict)
        else parse_ingestion_config(None)
    )
    return SimpleNamespace(
        formation_config={"memory": memory_config or {}},
        memory_ingestion=SimpleNamespace(settings=settings),
        memory_synthesis=None,
        memory_events=memory_events or SimpleNamespace(enabled=True),
        knowledge_graph=None,
        scheduler_service=FakeScheduler() if scheduler else None,
    )


class TestOverlordWiring:
    def test_inert_when_ingestion_unconfigured(self):
        stub = overlord_stub({})
        Overlord._initialize_memory_synthesis(stub)
        assert stub.memory_synthesis is None
        assert stub.scheduler_service.periodic_tasks == []

    def test_registered_when_ingestion_configured(self):
        stub = overlord_stub({"ingestion": {"sources": {"gmail": {"filter": "lenient"}}}})
        Overlord._initialize_memory_synthesis(stub)
        assert stub.memory_synthesis is not None
        assert stub.scheduler_service.periodic_tasks == [stub.memory_synthesis]

    def test_synthesis_master_switch_disables(self):
        stub = overlord_stub({"ingestion": {"synthesis": {"enabled": False}}})
        Overlord._initialize_memory_synthesis(stub)
        assert stub.memory_synthesis is None

    def test_all_cadences_disabled_registers_nothing(self):
        stub = overlord_stub(
            {
                "ingestion": {
                    "synthesis": {
                        "hot": {"enabled": False},
                        "warm": {"enabled": False},
                        "cold": {"enabled": False},
                        "cold_cold": {"enabled": False},
                    }
                }
            }
        )
        Overlord._initialize_memory_synthesis(stub)
        # Service exists for manual passes, but no periodic task fires.
        assert stub.memory_synthesis is not None
        assert stub.scheduler_service.periodic_tasks == []

    def test_no_scheduler_degrades_to_manual(self, capsys):
        stub = overlord_stub({"ingestion": {}}, scheduler=False)
        stub.formation_config = {"memory": {"ingestion": {"tiers": {}}}}
        stub.memory_ingestion = SimpleNamespace(settings=parse_ingestion_config({"tiers": {}}))
        Overlord._initialize_memory_synthesis(stub)
        assert stub.memory_synthesis is not None
        assert "require the scheduler" in capsys.readouterr().out

    def test_requires_event_substrate(self):
        stub = overlord_stub(
            {"ingestion": {"tiers": {}}},
            memory_events=SimpleNamespace(enabled=False),
        )
        Overlord._initialize_memory_synthesis(stub)
        assert stub.memory_synthesis is None


# ----------------------------------------------------------------------
# tick() interval gating
# ----------------------------------------------------------------------


class TestTickGating:
    async def test_cadence_fires_only_after_interval(self, env):
        overlord, events, _ = env
        service = make_service(overlord, baseline=NOW)
        ran = []

        async def record_cadence(cadence, now=None):
            ran.append(cadence)
            return {}

        service.run_cadence = record_cadence

        await service.tick(NOW + timedelta(seconds=60))
        assert ran == []  # nothing due yet (first fire is one interval in)

        await service.tick(NOW + timedelta(seconds=301))
        assert ran == [CADENCE_HOT]

        await service.tick(NOW + timedelta(seconds=3901))
        assert CADENCE_WARM in ran and ran.count(CADENCE_HOT) == 2

    async def test_disabled_cadence_never_fires(self, env):
        overlord, _, _ = env
        service = make_service(overlord, baseline=NOW, hot={"enabled": False})
        ran = []

        async def record_cadence(cadence, now=None):
            ran.append(cadence)
            return {}

        service.run_cadence = record_cadence
        await service.tick(NOW + timedelta(days=30))
        assert CADENCE_HOT not in ran
        assert {CADENCE_WARM, CADENCE_COLD, CADENCE_COLD_COLD} <= set(ran)

    async def test_custom_interval_respected(self, env):
        overlord, _, _ = env
        service = make_service(overlord, baseline=NOW, hot={"interval_seconds": 10})
        ran = []

        async def record_cadence(cadence, now=None):
            ran.append(cadence)
            return {}

        service.run_cadence = record_cadence
        await service.tick(NOW + timedelta(seconds=11))
        assert ran == [CADENCE_HOT]

    async def test_tick_never_raises(self, env):
        overlord, _, _ = env
        service = make_service(overlord, baseline=NOW)

        async def boom(cadence, now=None):
            raise RuntimeError("pass exploded")

        service.run_cadence = boom
        await service.tick(NOW + timedelta(days=1))  # must not raise


# ----------------------------------------------------------------------
# Hot cadence: resolution + durable cursors
# ----------------------------------------------------------------------


class TestHotCadence:
    async def test_hot_resolves_users_with_new_events(self, env):
        overlord, events, graph = env
        await seed_duplicate_identities(graph)
        await seed_ingestion_event(events)
        service = make_service(overlord)

        report = await service.run_cadence(CADENCE_HOT)
        assert report["users"] == 1
        assert report["merged"] == 1

        merged = await graph.storage.get_entity(USER, "person", "Ryan")
        assert merged["status"] == STATUS_MERGED

    async def test_hot_cursor_skips_settled_users(self, env):
        overlord, events, graph = env
        await seed_duplicate_identities(graph)
        await seed_ingestion_event(events)
        service = make_service(overlord)

        first = await service.run_cadence(CADENCE_HOT)
        assert first["users"] == 1
        # No new events since the cursor advanced: the user is skipped.
        second = await service.run_cadence(CADENCE_HOT)
        assert second["users"] == 0

        # A new ingestion event makes the user eligible again.
        await seed_ingestion_event(events, source_id="m-2")
        third = await service.run_cadence(CADENCE_HOT)
        assert third["users"] == 1

    async def test_inert_without_substrate(self):
        overlord = SimpleNamespace(memory_events=None, knowledge_graph=None, long_term_memory=None)
        service = make_service(overlord)
        report = await service.run_cadence(CADENCE_HOT)
        assert report["users"] == 0


# ----------------------------------------------------------------------
# Warm/cold cadences: pattern extraction
# ----------------------------------------------------------------------


async def seed_graph_preferences(graph):
    user = await graph.storage.upsert_entity(USER, "person", "User", confidence=0.95)
    tea = await graph.storage.upsert_entity(USER, "preference", "Earl Grey tea", confidence=0.9)
    bouldering = await graph.storage.upsert_entity(USER, "topic", "bouldering", confidence=0.9)
    python = await graph.storage.upsert_entity(USER, "topic", "Python", confidence=0.8)
    await graph.storage.upsert_relationship(USER, user["id"], tea["id"], "prefers", confidence=0.9)
    await graph.storage.upsert_relationship(
        USER, user["id"], bouldering["id"], "interested_in", confidence=0.9
    )
    return python


async def seed_turns(events, count, start=NOW):
    for i in range(count):
        occurred = (start + timedelta(days=i % 2, hours=(i % 3) - 1)).replace(tzinfo=None)
        await events.record(
            user_id=USER,
            event_type=EVENT_INTERACTION_TURN,
            payload={"user_message": f"turn {i}"},
            source=SOURCE_INTERACTION,
            occurred_at=occurred,
        )


class TestPatternExtraction:
    async def test_warm_writes_preference_and_expertise_patterns(self, env):
        overlord, events, graph = env
        await seed_graph_preferences(graph)
        await seed_ingestion_event(events)
        service = make_service(overlord)

        report = await service.run_cadence(CADENCE_WARM, now=NOW)
        assert report["patterns"] == 2

        facts = await events.list_events(USER, event_types=[EVENT_FACT_EXTRACTED])
        by_kind = {e["payload"]["metadata"]["pattern"]: e for e in facts}
        assert set(by_kind) == {"preferences", "expertise"}
        assert "Earl Grey tea" in by_kind["preferences"]["payload"]["memory"]
        assert by_kind["preferences"]["payload"]["collection"] == "preferences"
        assert by_kind["preferences"]["source"] == SOURCE_SYNTHESIS
        assert by_kind["preferences"]["decay_rate"] == "decaying"
        assert by_kind["preferences"]["source_id"] == "pattern/preferences/2026-W28"

        # The flat-fact projection received the pattern rows.
        contents = [row["content"] for row in overlord.long_term_memory.rows]
        assert any("Earl Grey tea" in content for content in contents)

    async def test_patterns_idempotent_within_period(self, env):
        overlord, events, graph = env
        await seed_graph_preferences(graph)
        await seed_ingestion_event(events)
        service = make_service(overlord)

        assert (await service.run_cadence(CADENCE_WARM, now=NOW))["patterns"] == 2
        await seed_ingestion_event(events, source_id="m-2")  # re-arm the cursor
        assert (await service.run_cadence(CADENCE_WARM, now=NOW))["patterns"] == 0
        assert len(overlord.long_term_memory.rows) == 2

        # A new period re-derives.
        await seed_ingestion_event(events, source_id="m-3")
        next_week = NOW + timedelta(days=7)
        assert (await service.run_cadence(CADENCE_WARM, now=next_week))["patterns"] == 2

    async def test_cold_writes_schedule_pattern(self, env):
        overlord, events, graph = env
        await seed_turns(events, 24)
        service = make_service(overlord)

        report = await service.run_cadence(CADENCE_COLD, now=NOW)
        assert report["patterns"] == 1
        facts = await events.list_events(USER, event_types=[EVENT_FACT_EXTRACTED])
        (schedule,) = facts
        assert schedule["payload"]["metadata"]["pattern"] == "schedule"
        assert schedule["payload"]["collection"] == "activities"
        assert "Typically active around" in schedule["payload"]["memory"]
        assert "Wednesday" in schedule["payload"]["memory"]

    async def test_schedule_needs_min_events(self, env):
        overlord, events, _ = env
        await seed_turns(events, 5)  # below the default min_events=20
        service = make_service(overlord)
        report = await service.run_cadence(CADENCE_COLD, now=NOW)
        assert report["patterns"] == 0

    async def test_min_events_configurable(self, env):
        overlord, events, _ = env
        await seed_turns(events, 5)
        service = make_service(overlord, patterns={"min_events": 3})
        report = await service.run_cadence(CADENCE_COLD, now=NOW)
        assert report["patterns"] == 1

    async def test_patterns_disableable(self, env):
        overlord, events, graph = env
        await seed_graph_preferences(graph)
        await seed_ingestion_event(events)
        service = make_service(overlord, patterns={"enabled": False})
        report = await service.run_cadence(CADENCE_WARM, now=NOW)
        assert report["patterns"] == 0


# ----------------------------------------------------------------------
# Cold-cold: weekly re-synthesis from the event log
# ----------------------------------------------------------------------


class TestColdCold:
    async def test_cold_cold_rebuilds_then_synthesizes(self, env):
        overlord, events, graph = env

        # History lives in the event log (dual-write), so the rebuild's
        # wipe-and-replay recreates it; the duplicate pair merges after.
        await graph.store_extraction(
            USER,
            {
                "entities": [
                    {
                        "name": "Ryan Leveille",
                        "type": "person",
                        "attributes": {"email": "ryan@nabo.dev"},
                        "confidence": 0.9,
                    },
                    {
                        "name": "Ryan",
                        "type": "person",
                        "attributes": {"email": "ryan@nabo.dev"},
                        "confidence": 0.8,
                    },
                ],
                "relationships": [],
            },
        )
        service = make_service(overlord)
        report = await service.run_cadence(CADENCE_COLD_COLD, now=NOW)
        assert report["rebuilt"] == 1
        assert report["merged"] == 1

        merged = await graph.storage.get_entity(USER, "person", "Ryan")
        assert merged["status"] == STATUS_MERGED

        # Replay determinism: a second full re-synthesis converges to the
        # same merged graph and derives nothing new.
        second = await service.run_cadence(CADENCE_COLD_COLD, now=NOW)
        assert second["rebuilt"] == 1
        assert second["merged"] == 0
        merged = await graph.storage.get_entity(USER, "person", "Ryan")
        assert merged["status"] == STATUS_MERGED
        names = {e["name"] for e in await graph.storage.list_entities(USER, entity_type="person")}
        assert names == {"Ryan Leveille"}

    async def test_rebuild_failure_is_isolated(self, env):
        overlord, events, graph = env
        await seed_ingestion_event(events)
        await events.record(
            user_id="u2",
            event_type=EVENT_MEMORY_INGESTED,
            payload={"content": "other user"},
            source="gmail",
            source_id="m-9",
        )
        service = make_service(overlord)

        original_rebuild = events.rebuild
        calls = []

        async def flaky_rebuild(user_id, *args, **kwargs):
            calls.append(str(user_id))
            if str(user_id) == USER:
                raise RuntimeError("replay exploded")
            return await original_rebuild(user_id, *args, **kwargs)

        events.rebuild = flaky_rebuild
        report = await service.run_cadence(CADENCE_COLD_COLD, now=NOW)
        # The failing user is isolated; the other user still rebuilt.
        assert sorted(calls) == [USER, "u2"]
        assert report["failed"] == 1
        assert report["rebuilt"] == 1
