"""Unit tests for Memory Revamp Phase 1: KnowledgeGraphService.

Covers real-time extraction storage round-trips (LLM mocked), failure
isolation (extraction must never raise into the chat turn), config gating,
the periodic deep-extraction scheduling logic, context block rendering, and
path explanation rendering.
"""

from __future__ import annotations

import asyncio

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.service import (
    MAX_PENDING_TURNS_PER_USER,
    KnowledgeGraphService,
    _schedule_to_seconds,
)

FORMATION_ID = "kg-test-formation"

VALID_RESPONSE = (
    "{"
    '"entities": ['
    '{"name": "Automaze", "type": "company", "confidence": 0.95},'
    '{"name": "User", "type": "person", "confidence": 0.95},'
    '{"name": "London", "type": "location", "confidence": 0.8}'
    "],"
    '"relationships": ['
    '{"from": "User", "from_type": "person", "to": "Automaze", "to_type": "company", '
    '"type": "founded", "confidence": 0.95},'
    '{"from": "User", "from_type": "person", "to": "London", "to_type": "location", '
    '"type": "lives_in", "confidence": 0.8}'
    "]"
    "}"
)


class FakeModel:
    def __init__(self, response=VALID_RESPONSE):
        self.response = response
        self.calls = 0

    async def generate_text(self, prompt, caching=True):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/kg.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def service(db_manager):
    return KnowledgeGraphService(db_manager, FORMATION_ID, config={})


class TestConfig:
    def test_defaults_match_prd(self, service):
        assert service.enabled is True
        assert service.realtime_enabled is True
        assert service.realtime_confidence == 0.9
        assert service.periodic_enabled is True
        assert service.periodic_confidence == 0.7
        assert service.periodic_interval_seconds == 3600.0

    def test_config_overrides(self, db_manager):
        service = KnowledgeGraphService(
            db_manager,
            FORMATION_ID,
            config={
                "enabled": True,
                "extraction": {
                    "realtime": False,
                    "realtime_confidence": 0.8,
                    "periodic": False,
                    "periodic_confidence": 0.6,
                    "periodic_schedule": "daily",
                },
            },
        )
        assert service.realtime_enabled is False
        assert service.realtime_confidence == 0.8
        assert service.periodic_enabled is False
        assert service.periodic_confidence == 0.6
        assert service.periodic_interval_seconds == 86400.0

    def test_sqlite_backend_uses_networkx(self, service):
        from muxi.runtime.services.memory.graph.algorithms import NetworkXAlgorithms

        assert service.pgrouting_available is False
        assert isinstance(service.algorithms, NetworkXAlgorithms)

    def test_schedule_to_seconds(self):
        assert _schedule_to_seconds("hourly") == 3600.0
        assert _schedule_to_seconds("daily") == 86400.0
        assert _schedule_to_seconds("HOURLY") == 3600.0
        assert _schedule_to_seconds(120) == 120.0
        assert _schedule_to_seconds(0.5) == 0.5
        # Invalid values fall back to the hourly default
        assert _schedule_to_seconds("weekly") == 3600.0
        assert _schedule_to_seconds(None) == 3600.0
        assert _schedule_to_seconds(-5) == 3600.0
        assert _schedule_to_seconds(True) == 3600.0


class TestRealtimeExtraction:
    async def test_turn_produces_graph_rows(self, service):
        await service.process_conversation_turn(
            "I founded Automaze and live in London", "Nice!", "u1", FakeModel()
        )
        entities = await service.storage.list_entities("u1")
        # Threshold 0.9 keeps User and Automaze; London (0.8) is dropped
        assert {e["name"] for e in entities} == {"User", "Automaze"}

        relationships = await service.storage.list_relationships("u1")
        assert [r["type"] for r in relationships] == ["founded"]

    async def test_relationship_endpoints_auto_created(self, db_manager):
        response = (
            '{"entities": [], "relationships": [{"from": "User", "from_type": "person", '
            '"to": "Acme", "to_type": "company", "type": "works_at", "confidence": 0.95}]}'
        )
        service = KnowledgeGraphService(db_manager, FORMATION_ID, config={})
        await service.process_conversation_turn("I work at Acme", "", "u1", FakeModel(response))
        assert await service.storage.get_entity("u1", "company", "Acme") is not None
        assert len(await service.storage.list_relationships("u1")) == 1

    async def test_untyped_unknown_endpoint_skipped(self, db_manager):
        response = (
            '{"entities": [], "relationships": [{"from": "User", '
            '"to": "Mystery", "type": "knows", "confidence": 0.95}]}'
        )
        service = KnowledgeGraphService(db_manager, FORMATION_ID, config={})
        await service.process_conversation_turn("hi", "", "u1", FakeModel(response))
        assert await service.storage.list_relationships("u1") == []

    async def test_self_loop_skipped(self, db_manager):
        response = (
            '{"entities": [{"name": "User", "type": "person", "confidence": 0.95}], '
            '"relationships": [{"from": "User", "from_type": "person", "to": "User", '
            '"to_type": "person", "type": "knows", "confidence": 0.95}]}'
        )
        service = KnowledgeGraphService(db_manager, FORMATION_ID, config={})
        await service.process_conversation_turn("hi", "", "u1", FakeModel(response))
        assert await service.storage.list_relationships("u1") == []

    async def test_model_failure_never_raises(self, service):
        await service.process_conversation_turn(
            "hello", "hi", "u1", FakeModel(RuntimeError("model down"))
        )
        assert await service.storage.list_entities("u1") == []

    async def test_malformed_response_stores_nothing(self, service):
        await service.process_conversation_turn("hello", "hi", "u1", FakeModel("not json {"))
        assert await service.storage.list_entities("u1") == []

    async def test_no_model_is_noop(self, service):
        await service.process_conversation_turn("hello", "hi", "u1", None)
        assert await service.storage.list_entities("u1") == []

    async def test_disabled_service_is_noop(self, db_manager):
        service = KnowledgeGraphService(db_manager, FORMATION_ID, config={"enabled": False})
        model = FakeModel()
        await service.process_conversation_turn("hello", "hi", "u1", model)
        assert model.calls == 0
        assert await service.storage.list_entities("u1") == []

    async def test_realtime_disabled_still_queues_for_periodic(self, db_manager):
        service = KnowledgeGraphService(
            db_manager, FORMATION_ID, config={"extraction": {"realtime": False}}
        )
        model = FakeModel()
        await service.process_conversation_turn("hello", "hi", "u1", model)
        assert model.calls == 0
        assert len(service._pending_turns["u1"]) == 1


class TestPeriodicScheduling:
    async def test_turns_queue_per_user_with_cap(self, service):
        model = FakeModel('{"entities": [], "relationships": []}')
        for index in range(MAX_PENDING_TURNS_PER_USER + 10):
            await service.process_conversation_turn(f"message {index}", "", "u1", model)
        await service.process_conversation_turn("other user", "", "u2", model)

        assert len(service._pending_turns["u1"]) == MAX_PENDING_TURNS_PER_USER
        assert len(service._pending_turns["u2"]) == 1
        # FIFO cap keeps the newest turns
        assert "message 59" in service._pending_turns["u1"][-1]

    async def test_periodic_run_processes_batches_and_clears(self, db_manager):
        service = KnowledgeGraphService(
            db_manager, FORMATION_ID, config={"extraction": {"realtime": False}}
        )
        await service.process_conversation_turn("I founded Automaze", "", "u1", FakeModel())
        await service.process_conversation_turn("and live in London", "", "u1", FakeModel())

        model = FakeModel()
        totals = await service.run_periodic_extraction(model)

        assert model.calls == 1  # one batch per user, full context
        assert totals["entities"] == 3  # 0.7 threshold keeps London too
        assert totals["relationships"] == 2
        assert service._pending_turns == {}

        entities = await service.storage.list_entities("u1")
        assert {e["name"] for e in entities} == {"User", "Automaze", "London"}

    async def test_periodic_run_without_model_keeps_nothing_running(self, service):
        await service.process_conversation_turn(
            "hello", "", "u1", FakeModel('{"entities": [], "relationships": []}')
        )
        totals = await service.run_periodic_extraction(None)
        assert totals == {"entities": 0, "relationships": 0}

    async def test_periodic_failure_for_one_user_does_not_raise(self, db_manager):
        service = KnowledgeGraphService(
            db_manager, FORMATION_ID, config={"extraction": {"realtime": False}}
        )
        await service.process_conversation_turn("hello", "", "u1", FakeModel())
        totals = await service.run_periodic_extraction(FakeModel(RuntimeError("down")))
        assert totals == {"entities": 0, "relationships": 0}

    async def test_periodic_loop_lifecycle(self, db_manager):
        service = KnowledgeGraphService(
            db_manager,
            FORMATION_ID,
            config={"extraction": {"realtime": False, "periodic_schedule": 0.05}},
        )
        model = FakeModel()
        await service.process_conversation_turn("I founded Automaze", "", "u1", model)

        service.start_periodic_extraction(lambda: model)
        assert service._periodic_task is not None
        # Starting twice must not spawn a second task
        first_task = service._periodic_task
        service.start_periodic_extraction(lambda: model)
        assert service._periodic_task is first_task

        await asyncio.sleep(0.2)
        await service.stop()
        assert service._periodic_task is None
        assert model.calls >= 1  # the loop ran at least one extraction pass

    async def test_periodic_disabled_does_not_start(self, db_manager):
        service = KnowledgeGraphService(
            db_manager, FORMATION_ID, config={"extraction": {"periodic": False}}
        )
        service.start_periodic_extraction(lambda: FakeModel())
        assert service._periodic_task is None

    async def test_stop_without_start_is_safe(self, service):
        await service.stop()


class TestQuerySurface:
    async def _seed(self, service):
        storage = service.storage
        user = await storage.upsert_entity("u1", "person", "User", confidence=0.95)
        acme = await storage.upsert_entity("u1", "company", "Acme", confidence=0.95)
        muxi = await storage.upsert_entity("u1", "project", "MUXI", confidence=0.9)
        await storage.upsert_relationship("u1", user["id"], acme["id"], "founded", confidence=0.95)
        await storage.upsert_relationship("u1", acme["id"], muxi["id"], "building", confidence=0.9)
        return user, acme, muxi

    async def test_context_block_renders_one_hop_facts(self, service):
        await self._seed(service)
        block = await service.get_context_block("u1")
        assert "User -[founded]-> Acme" in block
        assert "Acme -[building]-> MUXI" in block

    async def test_context_block_multi_hop_on_topic_match(self, service):
        await self._seed(service)
        block = await service.get_context_block("u1", query_text="tell me about Acme")
        assert "Related to Acme:" in block
        assert "MUXI" in block

    async def test_context_block_empty_graph(self, service):
        assert await service.get_context_block("u1") == ""

    async def test_context_block_disabled(self, db_manager):
        service = KnowledgeGraphService(db_manager, FORMATION_ID, config={"enabled": False})
        assert await service.get_context_block("u1") == ""

    async def test_context_block_survives_storage_errors(self, service, monkeypatch):
        async def broken(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(service.storage, "list_relationships", broken)
        assert await service.get_context_block("u1") == ""

    async def test_explain_path_renders_edge_chain(self, service):
        await self._seed(service)
        rendered = await service.explain_path("u1", "User", "MUXI")
        assert rendered == "User -[founded]-> Acme -[building]-> MUXI"

    async def test_explain_path_case_insensitive_names(self, service):
        await self._seed(service)
        rendered = await service.explain_path("u1", "user", "muxi")
        assert rendered.endswith("MUXI")

    async def test_explain_path_unknown_entity(self, service):
        await self._seed(service)
        assert await service.explain_path("u1", "User", "Nowhere") == ""
