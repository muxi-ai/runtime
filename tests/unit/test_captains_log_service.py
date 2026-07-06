"""Unit tests for Memory Revamp Phase 2: CaptainsLogService.

Covers config gating and cadence resolution, turn queueing, the digest run
(LLM mocked) producing entries + source lineage + lessons + knowledge graph
rows, failure isolation (a digest failure must never raise into the loop),
the background-loop lifecycle, session-stable lesson injection, the
record_lesson write path, lesson maintenance (decay + consolidation), the
/history query surface, and the captains_log_sources DAG registration.
"""

from __future__ import annotations

import asyncio

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.log import service as service_module
from muxi.runtime.services.memory.log.service import (
    CAPTAINS_LOG_DAG,
    DEFAULT_ARCHIVE_THRESHOLD,
    DEFAULT_CONFIDENCE_DECAY_PER_30D,
    DEFAULT_INCLUDE_IN_CONTEXT,
    DEFAULT_INJECT_TOP_N,
    DEFAULT_MAX_PER_AGENT,
    LESSONS_BLOCK_HEADER,
    MAX_PENDING_TURNS_PER_USER,
    CaptainsLogService,
)

FORMATION_ID = "log-test-formation"

DIGEST_RESPONSE = (
    "{"
    '"summary": "The user finalized the memory PRD and founded Automaze.",'
    '"decisions": ["Knowledge graph over flat facts"],'
    '"projects": ["MUXI"],'
    '"context": "Focused on the launch.",'
    '"lessons": [{"rule": "Prefer reportlab over fpdf", "context": "PDF generation"}],'
    '"entities": ['
    '{"name": "User", "type": "person", "confidence": 0.95},'
    '{"name": "Automaze", "type": "company", "confidence": 0.9}'
    "],"
    '"relationships": ['
    '{"from": "User", "from_type": "person", "to": "Automaze", "to_type": "company", '
    '"type": "founded", "confidence": 0.9}'
    "]"
    "}"
)


class FakeModel:
    def __init__(self, response=DIGEST_RESPONSE):
        self.response = response
        self.calls = 0
        self.prompts = []

    async def generate_text(self, prompt, caching=True):
        self.calls += 1
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/log.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def service(db_manager):
    return CaptainsLogService(db_manager, FORMATION_ID)


@pytest.fixture
def service_with_graph(db_manager):
    graph = KnowledgeGraphService(db_manager, FORMATION_ID)
    return CaptainsLogService(db_manager, FORMATION_ID, knowledge_graph=graph)


class TestConfig:
    def test_defaults_match_prd(self, service):
        assert service.enabled is True
        assert service.interval_seconds == 86400  # "daily"
        assert service.include_in_context == DEFAULT_INCLUDE_IN_CONTEXT
        assert service.lessons_enabled is True
        assert service.extract_lessons_during_digest is True
        assert service.lessons_inject_top_n == DEFAULT_INJECT_TOP_N
        assert service.lessons_max_per_agent == DEFAULT_MAX_PER_AGENT
        assert service.lessons_decay_per_30d == DEFAULT_CONFIDENCE_DECAY_PER_30D
        assert service.lessons_archive_threshold == DEFAULT_ARCHIVE_THRESHOLD

    def test_config_overrides(self, db_manager):
        service = CaptainsLogService(
            db_manager,
            FORMATION_ID,
            config={"schedule": "hourly", "include_in_context": 3},
            lessons_config={
                "enabled": False,
                "inject_top_n": 5,
                "max_per_agent": 10,
                "confidence_decay_per_30d": 0.1,
                "archive_threshold": 0.3,
            },
        )
        assert service.interval_seconds == 3600
        assert service.include_in_context == 3
        assert service.lessons_enabled is False
        assert service.lessons_inject_top_n == 5
        assert service.lessons_max_per_agent == 10
        assert service.lessons_decay_per_30d == 0.1
        assert service.lessons_archive_threshold == 0.3

    def test_numeric_schedule_for_deterministic_tests(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"schedule": 2})
        assert service.interval_seconds == 2.0

    def test_dag_registered_on_graph_algorithms(self, service_with_graph):
        algorithms = service_with_graph.knowledge_graph.algorithms
        assert CAPTAINS_LOG_DAG in algorithms._dag_edge_providers


class TestTurnQueueing:
    def test_turns_queue_per_user_with_cap(self, service):
        for index in range(MAX_PENDING_TURNS_PER_USER + 10):
            service.queue_turn(f"message {index}", "response", user_id="u1")
        service.queue_turn("other", "response", user_id="u2")

        assert len(service._pending_turns["u1"]) == MAX_PENDING_TURNS_PER_USER
        assert len(service._pending_turns["u2"]) == 1

    def test_turn_carries_timestamp_source_key(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        timestamp_key, text = service._pending_turns["u1"][0]
        float(timestamp_key)  # buffer timestamp key: parseable epoch seconds
        assert text == "User: hello\nAssistant: hi"

    def test_disabled_service_does_not_queue(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        service.queue_turn("hello", "hi", user_id="u1")
        assert service._pending_turns == {}


class TestPeriodicSummarization:
    async def test_digest_produces_entry_sources_and_lessons(self, service):
        service.queue_turn("I founded Automaze", "Congrats!", user_id="u1")
        service.queue_turn("We ship MUXI next month", "Exciting!", user_id="u1")

        totals = await service.run_periodic_summarization(FakeModel())
        assert totals == {"entries": 1, "sources": 2, "lessons": 1}

        entries = await service.storage.list_entries("u1")
        assert len(entries) == 1
        assert entries[0]["summary"].startswith("The user finalized")
        assert entries[0]["decisions"] == ["Knowledge graph over flat facts"]

        sources = await service.storage.get_sources(entries[0]["id"])
        assert len(sources) == 2
        assert all(source["source_type"] == "buffer_item" for source in sources)

        lessons = await service.lessons.list_active("u1")
        assert [lesson["rule"] for lesson in lessons] == ["Prefer reportlab over fpdf"]
        assert lessons[0]["source_log_id"] == entries[0]["id"]

    async def test_digest_feeds_knowledge_graph(self, service_with_graph):
        service_with_graph.queue_turn("I founded Automaze", "Congrats!", user_id="u1")
        await service_with_graph.run_periodic_summarization(FakeModel())

        graph = service_with_graph.knowledge_graph
        entities = await graph.storage.list_entities("u1")
        assert {entity["name"] for entity in entities} == {"User", "Automaze"}
        relationships = await graph.storage.list_relationships("u1")
        assert [rel["type"] for rel in relationships] == ["founded"]

    async def test_second_run_merges_same_date_entry(self, service):
        model = FakeModel()
        service.queue_turn("first", "ok", user_id="u1")
        await service.run_periodic_summarization(model)
        service.queue_turn("second", "ok", user_id="u1")
        await service.run_periodic_summarization(model)

        # Second digest prompt folds the existing entry in for merging.
        assert "already exists" in model.prompts[1]
        entries = await service.storage.list_entries("u1")
        assert len(entries) == 1
        # Sources accumulate across runs.
        assert len(await service.storage.get_sources(entries[0]["id"])) == 2

    async def test_pending_turns_cleared_after_run(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        await service.run_periodic_summarization(FakeModel())
        assert service._pending_turns == {}

    async def test_no_model_keeps_pending_turns(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        totals = await service.run_periodic_summarization(None)
        assert totals == {"entries": 0, "sources": 0, "lessons": 0}
        assert "u1" in service._pending_turns

    async def test_model_failure_never_raises(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        totals = await service.run_periodic_summarization(FakeModel(RuntimeError("LLM down")))
        assert totals == {"entries": 0, "sources": 0, "lessons": 0}

    async def test_malformed_response_stores_nothing(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        totals = await service.run_periodic_summarization(FakeModel("not json"))
        assert totals == {"entries": 0, "sources": 0, "lessons": 0}
        assert await service.storage.list_entries("u1") == []

    async def test_one_user_failure_does_not_block_others(self, service, monkeypatch):
        service.queue_turn("mine", "ok", user_id="u1")
        service.queue_turn("theirs", "ok", user_id="u2")

        original = service._digest_user

        async def flaky(user_id, turns, model):
            if user_id == "u1":
                raise RuntimeError("boom")
            return await original(user_id, turns, model)

        monkeypatch.setattr(service, "_digest_user", flaky)
        totals = await service.run_periodic_summarization(FakeModel())
        assert totals["entries"] == 1

    async def test_graph_failure_keeps_entry(self, service_with_graph, monkeypatch):
        async def broken(*args, **kwargs):
            raise RuntimeError("graph down")

        monkeypatch.setattr(service_with_graph.knowledge_graph, "store_extraction", broken)
        service_with_graph.queue_turn("hello", "hi", user_id="u1")
        totals = await service_with_graph.run_periodic_summarization(FakeModel())
        assert totals["entries"] == 1
        assert len(await service_with_graph.storage.list_entries("u1")) == 1

    async def test_lessons_disabled_skips_extraction(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, lessons_config={"enabled": False})
        model = FakeModel()
        service.queue_turn("hello", "hi", user_id="u1")
        totals = await service.run_periodic_summarization(model)
        assert totals["lessons"] == 0
        assert "LESSONS LEARNED" not in model.prompts[0]
        assert await service.lessons.list_active("u1") == []


class TestLoopLifecycle:
    async def test_loop_runs_and_stops(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"schedule": 0.05})
        model = FakeModel()
        service.queue_turn("hello", "hi", user_id="u1")

        service.start(lambda: model)
        assert service._task is not None
        await asyncio.sleep(0.2)
        await service.stop()
        assert service._task is None
        assert model.calls >= 1
        assert len(await service.storage.list_entries("u1")) == 1

    async def test_loop_survives_model_failures(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"schedule": 0.05})
        model = FakeModel(RuntimeError("LLM down"))

        service.start(lambda: model)
        await asyncio.sleep(0.2)
        assert not service._task.done()  # loop backed off and kept running
        await service.stop()

    async def test_disabled_service_does_not_start(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        service.start(lambda: FakeModel())
        assert service._task is None

    async def test_start_twice_keeps_single_task(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"schedule": 60})
        service.start(lambda: None)
        first_task = service._task
        service.start(lambda: None)
        assert service._task is first_task
        await service.stop()

    async def test_stop_without_start_is_safe(self, service):
        await service.stop()


class TestRecordLesson:
    async def test_record_and_confirm(self, service):
        first = await service.record_lesson("u1", "assistant", "Prefer X", context="when Y")
        assert first["hits"] == 1
        second = await service.record_lesson("u1", "assistant", "prefer x")
        assert second["id"] == first["id"]
        assert second["hits"] == 2

    async def test_empty_rule_rejected(self, service):
        with pytest.raises(ValueError):
            await service.record_lesson("u1", "assistant", "   ")

    async def test_disabled_lessons_rejected(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, lessons_config={"enabled": False})
        with pytest.raises(ValueError):
            await service.record_lesson("u1", "assistant", "Rule")


class TestLessonInjection:
    async def test_block_renders_top_lessons(self, service):
        await service.record_lesson("u1", "assistant", "Prefer X", context="PDFs")
        block = await service.get_lessons_prompt_block("u1", "assistant", "s1")
        assert block.startswith(LESSONS_BLOCK_HEADER)
        assert "- Prefer X (when: PDFs)" in block

    async def test_block_marks_lessons_applied(self, service):
        await service.record_lesson("u1", "assistant", "Prefer X")
        await service.get_lessons_prompt_block("u1", "assistant", "s1")
        listed = await service.lessons.list_active("u1")
        assert listed[0]["last_applied_at"] is not None

    async def test_block_stable_within_session(self, service):
        await service.record_lesson("u1", "assistant", "Prefer X")
        first = await service.get_lessons_prompt_block("u1", "assistant", "s1")
        # A lesson recorded mid-session must not change the session's block.
        await service.record_lesson("u1", "assistant", "Prefer Z")
        second = await service.get_lessons_prompt_block("u1", "assistant", "s1")
        assert second == first
        assert "Prefer Z" not in second

    async def test_new_session_sees_new_lessons(self, service):
        await service.record_lesson("u1", "assistant", "Prefer X")
        await service.get_lessons_prompt_block("u1", "assistant", "s1")
        await service.record_lesson("u1", "assistant", "Prefer Z")
        block = await service.get_lessons_prompt_block("u1", "assistant", "s2")
        assert "Prefer Z" in block

    async def test_empty_when_no_lessons(self, service):
        assert await service.get_lessons_prompt_block("u1", "assistant", "s1") == ""

    async def test_empty_when_disabled(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, lessons_config={"enabled": False})
        assert await service.get_lessons_prompt_block("u1", "assistant", "s1") == ""

    async def test_top_n_limit_respected(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, lessons_config={"inject_top_n": 1})
        await service.record_lesson("u1", "assistant", "Low rule")
        high = await service.record_lesson("u1", "assistant", "High rule")
        await service.record_lesson("u1", "assistant", "High rule")  # confirm: bumps confidence
        block = await service.get_lessons_prompt_block("u1", "assistant", "s1")
        assert "High rule" in block
        assert "Low rule" not in block
        assert high["id"] is not None

    async def test_storage_error_returns_empty(self, service, monkeypatch):
        async def broken(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(service.lessons, "list_active", broken)
        assert await service.get_lessons_prompt_block("u1", "assistant", "s1") == ""


class TestLessonMaintenance:
    async def test_consolidation_merges_similar_lessons(self, db_manager, monkeypatch):
        service = CaptainsLogService(db_manager, FORMATION_ID, lessons_config={"max_per_agent": 2})
        await service.record_lesson("u1", "assistant", "Use reportlab for PDFs")
        await service.record_lesson("u1", "assistant", "reportlab beats fpdf for PDFs")
        await service.record_lesson("u1", "assistant", "Always answer briefly")

        async def fake_embed(model, texts, **kwargs):
            # The two PDF rules are identical vectors; the brevity rule is
            # orthogonal, so greedy clustering pairs the first two.
            vectors = {
                "Use reportlab for PDFs": [1.0, 0.0],
                "reportlab beats fpdf for PDFs": [1.0, 0.0],
                "Always answer briefly": [0.0, 1.0],
            }
            return [vectors[text] for text in texts]

        monkeypatch.setattr(service_module, "embed", fake_embed)
        model = FakeModel("When generating PDFs, use reportlab (never fpdf).")

        consolidated = await service.run_lesson_consolidation(model)
        assert consolidated == 1

        active = await service.lessons.list_active("u1")
        rules = {lesson["rule"] for lesson in active}
        assert "When generating PDFs, use reportlab (never fpdf)." in rules
        assert "Always answer briefly" in rules
        assert len(active) == 2  # originals archived, hits carried over
        merged = next(lesson for lesson in active if "reportlab" in lesson["rule"])
        assert merged["hits"] == 2

    async def test_consolidation_noop_under_cap(self, service):
        await service.record_lesson("u1", "assistant", "Only rule")
        assert await service.run_lesson_consolidation(FakeModel()) == 0

    async def test_maintenance_failure_isolated(self, service, monkeypatch):
        async def broken(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(service.lessons, "run_decay", broken)
        monkeypatch.setattr(service.lessons, "scopes_over_cap", broken)
        totals = await service.run_lesson_maintenance(FakeModel())
        assert totals == {"decayed": 0, "archived": 0, "consolidated": 0}


class TestQuerySurface:
    async def test_context_block_renders_recent_entries(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        await service.run_periodic_summarization(FakeModel())

        block = await service.get_context_block("u1")
        assert "The user finalized the memory PRD" in block
        assert "Decisions: Knowledge graph over flat facts" in block
        assert "Projects: MUXI" in block

    async def test_context_block_empty_log(self, service):
        assert await service.get_context_block("u1") == ""

    async def test_context_block_disabled(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        assert await service.get_context_block("u1") == ""

    async def test_context_block_survives_storage_errors(self, service, monkeypatch):
        async def broken(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(service.storage, "list_entries", broken)
        assert await service.get_context_block("u1") == ""

    async def test_history_exposes_public_ids_and_sources(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        await service.run_periodic_summarization(FakeModel())

        history = await service.get_history("u1", include_sources=True)
        assert len(history) == 1
        entry = history[0]
        assert len(entry["id"]) == 21  # public_id, never the integer PK
        assert entry["summary"].startswith("The user finalized")
        assert len(entry["sources"]) == 1
        assert entry["sources"][0]["source_type"] == "buffer_item"

    async def test_history_without_sources(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        await service.run_periodic_summarization(FakeModel())
        history = await service.get_history("u1")
        assert "sources" not in history[0]

    async def test_topological_sort_over_log_dag(self, service_with_graph):
        storage = service_with_graph.storage
        from datetime import date

        old = await storage.upsert_entry("u1", date(2026, 7, 5), summary="Old")
        new = await storage.upsert_entry("u1", date(2026, 7, 6), summary="New")
        await storage.add_sources(
            "u1", new["id"], [{"source_type": "log_entry", "source_id": str(old["id"])}]
        )

        algorithms = service_with_graph.knowledge_graph.algorithms
        order = await algorithms.topological_sort(user_id="u1", dag=CAPTAINS_LOG_DAG)
        assert order == [old["id"], new["id"]]
