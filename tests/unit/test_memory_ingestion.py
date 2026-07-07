"""Unit tests for Memory Ingestion Phase 3a: /v1/memories contract + pipeline.

Covers the ingestion surface at the unit level:

  * Contract validation: content/source/source_id/timestamp/subject/
    metadata rules with precise error messages, including the
    input_limits.max_memory_entry_size gate.
  * Idempotency: a duplicate (source, source_id) POST returns the
    original event (duplicate status + derived events), never an error
    and never a second processing run; batches with duplicate mixes get
    per-item statuses in order.
  * Async lifecycle: accept returns a processing_id; the tracked job
    moves queued -> processing -> completed with per-stage outcomes and
    token-usage cost attribution.
  * Classifier triage: prototype-similarity arg-max mapping and the
    per-source noise-gate levels (strict default, lenient, off, unknown
    values falling back to strict).
  * Filter dispositions recorded as ingestion.filtered events with
    caused_by provenance (raw memory.ingested event keeps the content).
  * Pipeline feeds the EXISTING extraction path: the extractor is called
    with caused_by_event_id + event_source; without an extractor the
    content is stored as an event-sourced fact.
  * Scope + grant behavior identical to #215: ingestion with shared
    scopes runs through _resolve_write_scope (403 without a grant) and
    shared items are written event-first with their true scope.
  * In-flight cap: the per-user job counter rejects with 429 semantics.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from muxi.runtime.formation.background.request_tracker import RequestStatus, RequestTracker
from muxi.runtime.formation.overlord.input_validation import InputLimits, InputValidator
from muxi.runtime.formation.server.routes.client.memory import (
    MemoryCreate,
    MemoryIngestBatch,
    _handle_ingestion,
    ingest_memories_batch,
)
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import MemoryEventService
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    EVENT_INGESTION_FILTERED,
    EVENT_MEMORY_INGESTED,
    MemoryEvent,
    ProjectionCheckpoint,
)
from muxi.runtime.services.memory.events.projectors import FACT_EVENT_METADATA_KEY
from muxi.runtime.services.memory.ingest import (
    STATUS_ACCEPTED,
    STATUS_DUPLICATE,
    STATUS_INVALID,
    IngestionBusyError,
    IngestionUnavailableError,
    MemoryIngestionService,
    validate_item,
)
from muxi.runtime.services.memory.ingest.classification import (
    CATEGORY_AUTOMATED,
    CATEGORY_PERSONAL,
    CATEGORY_PROMOTIONAL,
    CATEGORY_TRANSACTIONAL,
    CATEGORY_WORK,
    DEFAULT_FILTER_LEVEL,
    INTENT_PREFIX,
    classify_content,
    is_filtered,
)
from muxi.runtime.services.memory.ingest.service import (
    DISPOSITION_FAILED,
    DISPOSITION_FILTERED,
    DISPOSITION_STORED,
)

FORMATION_ID = "ingestion-test-formation"

EVENT_TABLES = [MemoryEvent.__table__, ProjectionCheckpoint.__table__]


# ----------------------------------------------------------------------
# Test doubles
# ----------------------------------------------------------------------


class StubClassifier:
    """Deterministic classifier: fixed margin per registered intent."""

    def __init__(self, margins=None, fail=False):
        self.margins = margins or {}
        self.fail = fail
        self.registered = []
        self.registered_specs = []

    async def register(self, spec):
        self.registered.append(spec.name)
        self.registered_specs.append(spec)

    async def classify_binary(self, name, text):
        if self.fail:
            raise RuntimeError("embedding backend unavailable")
        margin = self.margins.get(name, -0.5)
        return margin > 0, margin


def margins_for(category: str) -> dict:
    """Margins that make `category` the arg-max triage label."""
    return {f"{INTENT_PREFIX}{category}": 0.4}


class RecordingLTM:
    """Minimal long-term-memory double recording add() calls."""

    def __init__(self):
        self.rows = []

    async def add(self, content, metadata=None, user_id=None, collection=None, scope=None):
        self.rows.append(
            {
                "content": content,
                "metadata": dict(metadata or {}),
                "user_id": user_id,
                "collection": collection,
                "scope": scope,
            }
        )
        return f"m{len(self.rows)}"


class StubExtractor:
    """Extractor double that mimics the dual-write (fact.extracted) path."""

    extraction_interval = 1

    def __init__(self, memory_events=None, facts=("User likes green tea",), block_event=None):
        self.memory_events = memory_events
        self.facts = facts
        self.block_event = block_event
        self.calls = []

    async def process_conversation_turn(self, **kwargs):
        self.calls.append(kwargs)
        if self.block_event is not None:
            await self.block_event.wait()
        if self.memory_events is None:
            return
        for fact in self.facts:
            await self.memory_events.record(
                user_id=str(kwargs["user_id"]),
                event_type=EVENT_FACT_EXTRACTED,
                payload={"memory": fact, "collection": "context"},
                source=kwargs.get("event_source") or "interaction",
                caused_by=kwargs.get("caused_by_event_id"),
            )


class FailingExtractor:
    extraction_interval = 1

    async def process_conversation_turn(self, **kwargs):
        raise RuntimeError("extraction model exploded")


def make_overlord(
    memory_events,
    *,
    classifier=None,
    extractor=None,
    long_term_memory=None,
    ingestion_config=None,
):
    """Build the minimal overlord surface the ingestion service uses."""
    overlord = SimpleNamespace(
        formation_config={"memory": {"ingestion": ingestion_config or {}}},
        formation_id=FORMATION_ID,
        memory_events=memory_events,
        request_tracker=RequestTracker(),
        long_term_memory=long_term_memory or RecordingLTM(),
        extractor=extractor,
        knowledge_graph=None,
        default_model=None,
        is_multi_user=False,
        input_validator=InputValidator(InputLimits()),
    )
    classifier = classifier or StubClassifier(margins_for(CATEGORY_PERSONAL))

    async def _get_local_classifier():
        return classifier

    overlord._get_local_classifier = _get_local_classifier
    # The routes resolve the service from the overlord, exactly like the
    # real wiring in Overlord.__init__.
    overlord.memory_ingestion = MemoryIngestionService(overlord)
    return overlord


@pytest.fixture
def memory_events(tmp_path):
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/events.db")
    db_manager.create_tables(Base.metadata, tables=EVENT_TABLES)
    service = MemoryEventService(db_manager, FORMATION_ID, config={"enabled": True})
    yield service
    db_manager.engine.dispose()


def make_item(service_or_none=None, **overrides):
    payload = {
        "content": "I moved to London last month and I love hiking",
        "source": "gmail",
        "source_id": "msg-1",
    }
    payload.update(overrides)
    item, error = validate_item(payload)
    assert error is None, error
    return item


async def finish_job(overlord, processing_id):
    """Await the background processing task and return the tracker state."""
    state = await overlord.request_tracker.get_request(processing_id)
    assert state is not None
    await state.task_ref
    return await overlord.request_tracker.get_request(processing_id)


# ----------------------------------------------------------------------
# Contract validation
# ----------------------------------------------------------------------


class TestContractValidation:
    def test_source_required(self):
        item, error = validate_item({"content": "hello"})
        assert item is None
        assert "'source' is required" in error

    def test_source_length_capped(self):
        item, error = validate_item({"content": "x", "source": "s" * 51})
        assert item is None
        assert "at most 50 characters" in error

    def test_content_required(self):
        item, error = validate_item({"source": "gmail"})
        assert item is None
        assert "'content' is required" in error

    def test_content_must_not_be_blank(self):
        item, error = validate_item({"content": "   ", "source": "gmail"})
        assert item is None
        assert "must not be empty" in error

    def test_content_type_checked(self):
        item, error = validate_item({"content": 42, "source": "gmail"})
        assert item is None
        assert "string or a structured object" in error

    def test_structured_content_serialized_for_pipeline(self):
        item, error = validate_item(
            {"content": {"subject": "Re: launch", "body": "ship it"}, "source": "gmail"}
        )
        assert error is None
        assert item.content == {"subject": "Re: launch", "body": "ship it"}
        assert "ship it" in item.content_text

    def test_memory_entry_size_limit_enforced(self):
        validator = InputValidator(InputLimits(max_memory_entry_size=10))
        item, error = validate_item(
            {"content": "much longer than ten characters", "source": "gmail"},
            input_validator=validator,
        )
        assert item is None
        assert "Memory entry too large" in error

    def test_timestamp_parsing_and_rejection(self):
        item, error = validate_item(
            {"content": "x", "source": "gmail", "timestamp": "2026-07-01T12:00:00Z"}
        )
        assert error is None
        assert item.occurred_at is not None
        assert item.occurred_at.tzinfo is None  # substrate's naive-UTC shape
        assert item.occurred_at.hour == 12

        item, error = validate_item(
            {"content": "x", "source": "gmail", "timestamp": "yesterday-ish"}
        )
        assert item is None
        assert "not valid ISO 8601" in error

    def test_source_id_and_subject_rules(self):
        item, error = validate_item({"content": "x", "source": "gmail", "source_id": "  "})
        assert item is None and "'source_id'" in error

        item, error = validate_item({"content": "x", "source": "gmail", "subject": "s" * 256})
        assert item is None and "'subject'" in error

    def test_metadata_must_be_object(self):
        item, error = validate_item({"content": "x", "source": "gmail", "metadata": "nope"})
        assert item is None
        assert "'metadata' must be an object" in error


# ----------------------------------------------------------------------
# Classifier triage + noise gate
# ----------------------------------------------------------------------


class TestTriage:
    async def test_argmax_category_wins(self):
        classifier = StubClassifier(
            {
                f"{INTENT_PREFIX}{CATEGORY_PERSONAL}": 0.10,
                f"{INTENT_PREFIX}{CATEGORY_WORK}": 0.35,
                f"{INTENT_PREFIX}{CATEGORY_AUTOMATED}": -0.2,
            }
        )
        category, margin = await classify_content(classifier, "standup notes")
        assert category == CATEGORY_WORK
        assert margin == pytest.approx(0.35)
        # All five category intents were registered on the classifier.
        assert len({n for n in classifier.registered if n.startswith(INTENT_PREFIX)}) == 5

    def test_filter_levels(self):
        assert is_filtered(CATEGORY_PROMOTIONAL, "strict")
        assert is_filtered(CATEGORY_AUTOMATED, "strict")
        assert is_filtered(CATEGORY_TRANSACTIONAL, "strict")
        assert not is_filtered(CATEGORY_PERSONAL, "strict")
        assert not is_filtered(CATEGORY_WORK, "strict")

        assert is_filtered(CATEGORY_PROMOTIONAL, "lenient")
        assert not is_filtered(CATEGORY_AUTOMATED, "lenient")

        assert not is_filtered(CATEGORY_PROMOTIONAL, "off")

        # Unknown-category items are always kept (fail-open triage).
        assert not is_filtered("unknown", "strict")

    async def test_repeated_classify_reuses_module_constant_specs(self):
        # The category specs are pure constants: repeated classify calls
        # (and independent classifier instances) must register the exact
        # same spec objects, never per-call rebuilds.
        from muxi.runtime.services.memory.ingest.classification import CATEGORY_SPECS

        first = StubClassifier(margins_for(CATEGORY_PERSONAL))
        second = StubClassifier(margins_for(CATEGORY_PERSONAL))
        await classify_content(first, "note one")
        await classify_content(first, "note two")
        await classify_content(second, "note three")

        constant_ids = {id(spec) for spec in CATEGORY_SPECS.values()}
        assert {id(spec) for spec in first.registered_specs} == constant_ids
        assert {id(spec) for spec in second.registered_specs} == constant_ids
        # Two calls on the same classifier registered the same objects twice.
        assert len(first.registered_specs) == 2 * len(CATEGORY_SPECS)
        for a, b in zip(
            first.registered_specs[: len(CATEGORY_SPECS)],
            first.registered_specs[len(CATEGORY_SPECS) :],
        ):
            assert a is b

    def test_per_source_filter_config(self, memory_events):
        overlord = make_overlord(
            memory_events,
            ingestion_config={
                "sources": {
                    "gmail": {"filter": "lenient"},
                    "desktop": {"filter": "OFF"},
                    "weird": {"filter": "everything"},
                }
            },
        )
        service = MemoryIngestionService(overlord)
        assert service.filter_level("gmail") == "lenient"
        assert service.filter_level("desktop") == "off"
        # Unknown value and unconfigured source both fall back to strict.
        assert service.filter_level("weird") == DEFAULT_FILTER_LEVEL == "strict"
        assert service.filter_level("never-configured") == "strict"


# ----------------------------------------------------------------------
# Accept path: idempotency + async lifecycle
# ----------------------------------------------------------------------


class TestAcceptAndIdempotency:
    async def test_accept_records_raw_event_and_completes(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(memory_events, extractor=extractor)
        service = MemoryIngestionService(overlord)

        outcome = await service.submit("alice", [(0, make_item())])
        assert outcome["processing_id"] is not None
        assert outcome["results"][0]["status"] == STATUS_ACCEPTED

        # The raw event landed BEFORE processing, with the idempotency key.
        events = await memory_events.list_events("alice", event_types=[EVENT_MEMORY_INGESTED])
        assert len(events) == 1
        assert events[0]["source"] == "gmail"
        assert events[0]["source_id"] == "msg-1"

        state = await finish_job(overlord, outcome["processing_id"])
        assert state.status == RequestStatus.COMPLETED
        report = state.result
        assert report["counts"][DISPOSITION_STORED] == 1
        assert report["items"][0]["disposition"] == DISPOSITION_STORED
        assert report["items"][0]["classification"]["category"] == CATEGORY_PERSONAL
        assert report["items"][0]["facts_extracted"] == 1
        # Cost attribution is present (zero here: no real LLM ran).
        assert "usage" in report and "total" in report["usage"]

        # The extractor was fed with provenance + true source.
        assert extractor.calls[0]["caused_by_event_id"] == events[0]["id"]
        assert extractor.calls[0]["event_source"] == "gmail"

        # In-flight slot released after completion.
        assert service.in_flight("alice") == 0

    async def test_duplicate_submit_returns_original(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(memory_events, extractor=extractor)
        service = MemoryIngestionService(overlord)

        first = await service.submit("alice", [(0, make_item())])
        await finish_job(overlord, first["processing_id"])

        second = await service.submit("alice", [(0, make_item())])
        result = second["results"][0]
        assert second["processing_id"] is None  # no reprocessing
        assert result["status"] == STATUS_DUPLICATE
        assert result["event_id"] == first["results"][0]["event_id"]
        # The original processing result travels with the duplicate:
        # the fact derived from the first ingestion.
        derived_types = {d["event_type"] for d in result["derived_events"]}
        assert EVENT_FACT_EXTRACTED in derived_types

        # Still exactly one raw event and one extraction call.
        events = await memory_events.list_events("alice", event_types=[EVENT_MEMORY_INGESTED])
        assert len(events) == 1
        assert len(extractor.calls) == 1

    async def test_batch_with_duplicate_mix_keeps_order(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(memory_events, extractor=extractor)
        service = MemoryIngestionService(overlord)

        first = await service.submit("alice", [(0, make_item(source_id="msg-1"))])
        await finish_job(overlord, first["processing_id"])

        batch = [
            (0, make_item(source_id="msg-2", content="New note about my cat")),
            (1, make_item(source_id="msg-1")),  # duplicate of the first submit
            (2, make_item(source_id="msg-3", content="Another note about work")),
        ]
        outcome = await service.submit("alice", batch)
        assert outcome["results"][0]["status"] == STATUS_ACCEPTED
        assert outcome["results"][1]["status"] == STATUS_DUPLICATE
        assert outcome["results"][2]["status"] == STATUS_ACCEPTED

        state = await finish_job(overlord, outcome["processing_id"])
        # Only the two new items were processed; indexes preserved.
        assert [item["index"] for item in state.result["items"]] == [0, 2]

    async def test_substrate_required(self):
        overlord = make_overlord(None)
        service = MemoryIngestionService(overlord)
        with pytest.raises(IngestionUnavailableError):
            await service.submit("alice", [(0, make_item())])

    async def test_items_without_source_id_are_never_duplicates(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(memory_events, extractor=extractor)
        service = MemoryIngestionService(overlord)

        item = make_item(source_id=None)
        one = await service.submit("alice", [(0, item)])
        await finish_job(overlord, one["processing_id"])
        two = await service.submit("alice", [(0, make_item(source_id=None))])
        assert two["results"][0]["status"] == STATUS_ACCEPTED
        await finish_job(overlord, two["processing_id"])


# ----------------------------------------------------------------------
# Pipeline stages
# ----------------------------------------------------------------------


class TestPipeline:
    async def test_filtered_disposition_recorded_as_event(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(
            memory_events,
            extractor=extractor,
            classifier=StubClassifier(margins_for(CATEGORY_AUTOMATED)),
        )
        service = MemoryIngestionService(overlord)

        outcome = await service.submit(
            "alice", [(0, make_item(content="Build #8841 passed on main"))]
        )
        state = await finish_job(overlord, outcome["processing_id"])

        report = state.result["items"][0]
        assert report["disposition"] == DISPOSITION_FILTERED
        assert report["classification"]["category"] == CATEGORY_AUTOMATED
        assert report["filter_level"] == "strict"
        # Filtering never reaches extraction.
        assert extractor.calls == []

        # Raw event kept (replayable) + filtered disposition event linked.
        raw = await memory_events.list_events("alice", event_types=[EVENT_MEMORY_INGESTED])
        filtered = await memory_events.list_events("alice", event_types=[EVENT_INGESTION_FILTERED])
        assert len(raw) == 1 and len(filtered) == 1
        assert filtered[0]["caused_by"] == raw[0]["id"]
        assert filtered[0]["payload"]["category"] == CATEGORY_AUTOMATED
        assert filtered[0]["payload"]["filter_level"] == "strict"
        assert filtered[0]["source"] == "gmail"

    async def test_filter_off_keeps_noise(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(
            memory_events,
            extractor=extractor,
            classifier=StubClassifier(margins_for(CATEGORY_AUTOMATED)),
            ingestion_config={"sources": {"gmail": {"filter": "off"}}},
        )
        service = MemoryIngestionService(overlord)
        outcome = await service.submit("alice", [(0, make_item())])
        state = await finish_job(overlord, outcome["processing_id"])
        assert state.result["items"][0]["disposition"] == DISPOSITION_STORED
        assert len(extractor.calls) == 1

    async def test_classifier_failure_fails_open(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(
            memory_events, extractor=extractor, classifier=StubClassifier(fail=True)
        )
        service = MemoryIngestionService(overlord)
        outcome = await service.submit("alice", [(0, make_item())])
        state = await finish_job(overlord, outcome["processing_id"])
        report = state.result["items"][0]
        # Triage failure keeps the item (never lose developer data).
        assert report["classification"]["category"] == "unknown"
        assert report["disposition"] == DISPOSITION_STORED
        assert "classify_error" in report

    async def test_no_extractor_stores_verbatim_fact(self, memory_events):
        ltm = RecordingLTM()
        overlord = make_overlord(memory_events, extractor=None, long_term_memory=ltm)
        service = MemoryIngestionService(overlord)

        outcome = await service.submit("alice", [(0, make_item())])
        state = await finish_job(overlord, outcome["processing_id"])
        assert state.result["items"][0]["disposition"] == DISPOSITION_STORED

        (row,) = ltm.rows
        assert row["scope"] is None  # user scope
        assert row["metadata"]["source"] == "gmail"
        assert FACT_EVENT_METADATA_KEY in row["metadata"]  # replayable provenance

        facts = await memory_events.list_events("alice", event_types=[EVENT_FACT_EXTRACTED])
        raw = await memory_events.list_events("alice", event_types=[EVENT_MEMORY_INGESTED])
        assert len(facts) == 1
        assert facts[0]["caused_by"] == raw[0]["id"]
        assert facts[0]["source"] == "gmail"

    async def test_shared_scope_written_event_first_with_true_scope(self, memory_events):
        ltm = RecordingLTM()
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(memory_events, extractor=extractor, long_term_memory=ltm)
        service = MemoryIngestionService(overlord)

        item = make_item(content="Team A ships on Fridays")
        item.scope = ("group", "team-a")
        outcome = await service.submit("alice", [(0, item)])
        state = await finish_job(overlord, outcome["processing_id"])
        assert state.result["items"][0]["disposition"] == DISPOSITION_STORED

        # Shared-scope ingestion stores the content itself (grant-checked
        # shared write, #215 semantics); the user-scope extractor is not
        # used for shared items.
        assert extractor.calls == []
        (row,) = ltm.rows
        assert row["scope"] == ("group", "team-a")

        facts = await memory_events.list_events("alice", event_types=[EVENT_FACT_EXTRACTED])
        assert facts[0]["scope_type"] == "group"
        assert facts[0]["scope_id"] == "team-a"
        raw = await memory_events.list_events("alice", event_types=[EVENT_MEMORY_INGESTED])
        assert raw[0]["scope_type"] == "group"
        assert facts[0]["caused_by"] == raw[0]["id"]

    async def test_per_item_failure_contained(self, memory_events):
        overlord = make_overlord(memory_events, extractor=FailingExtractor())
        service = MemoryIngestionService(overlord)
        outcome = await service.submit("alice", [(0, make_item())])
        state = await finish_job(overlord, outcome["processing_id"])
        # The job completes; the item reports its failure.
        assert state.status == RequestStatus.COMPLETED
        report = state.result["items"][0]
        assert report["disposition"] == DISPOSITION_FAILED
        assert "extraction model exploded" in report["error"]
        assert service.in_flight("alice") == 0


# ----------------------------------------------------------------------
# In-flight cap
# ----------------------------------------------------------------------


class TestInFlightCap:
    async def test_cap_rejects_and_recovers(self, memory_events):
        gate = asyncio.Event()
        extractor = StubExtractor(memory_events, block_event=gate)
        overlord = make_overlord(
            memory_events, extractor=extractor, ingestion_config={"max_in_flight_per_user": 1}
        )
        service = MemoryIngestionService(overlord)

        first = await service.submit("alice", [(0, make_item(source_id="msg-1"))])
        assert service.in_flight("alice") == 1

        with pytest.raises(IngestionBusyError) as excinfo:
            await service.submit("alice", [(0, make_item(source_id="msg-2"))])
        assert "max 1" in str(excinfo.value)

        # A rejected request appended nothing: msg-2's key is not burned.
        events = await memory_events.list_events("alice", event_types=[EVENT_MEMORY_INGESTED])
        assert {e["source_id"] for e in events} == {"msg-1"}

        # Other users are unaffected.
        other = await service.submit("bob", [(0, make_item(source_id="msg-9"))])
        assert other["results"][0]["status"] == STATUS_ACCEPTED

        gate.set()
        await finish_job(overlord, first["processing_id"])
        assert service.in_flight("alice") == 0
        retry = await service.submit("alice", [(0, make_item(source_id="msg-2"))])
        assert retry["results"][0]["status"] == STATUS_ACCEPTED

        gate.set()
        for pid in (other["processing_id"], retry["processing_id"]):
            state = await overlord.request_tracker.get_request(pid)
            await state.task_ref


# ----------------------------------------------------------------------
# Slot ownership transfer (accept-path failures must never leak slots)
# ----------------------------------------------------------------------


class BrokenTracker:
    """Tracker double whose registration always fails."""

    async def track_request(self, *args, **kwargs):
        raise RuntimeError("tracker down")


class TestSlotOwnershipTransfer:
    async def test_tracker_failure_releases_slot(self, memory_events):
        overlord = make_overlord(
            memory_events,
            extractor=StubExtractor(memory_events),
            ingestion_config={"max_in_flight_per_user": 1},
        )
        service = overlord.memory_ingestion
        good_tracker = overlord.request_tracker

        overlord.request_tracker = BrokenTracker()
        with pytest.raises(RuntimeError, match="tracker down"):
            await service.submit("alice", [(0, make_item(source_id="m-1"))])
        assert service.in_flight("alice") == 0

        # The slot was returned, not leaked: with the tracker healthy
        # again, the next submit is accepted instead of 429'd forever.
        overlord.request_tracker = good_tracker
        outcome = await service.submit("alice", [(0, make_item(source_id="m-2"))])
        assert outcome["results"][0]["status"] == STATUS_ACCEPTED
        await finish_job(overlord, outcome["processing_id"])
        assert service.in_flight("alice") == 0

    async def test_task_creation_failure_releases_slot_and_untracks(self, memory_events):
        overlord = make_overlord(
            memory_events,
            extractor=StubExtractor(memory_events),
            ingestion_config={"max_in_flight_per_user": 1},
        )
        service = overlord.memory_ingestion

        def boom(*args, **kwargs):
            raise RuntimeError("task creation failed")

        original_process_job = service._process_job
        service._process_job = boom
        with pytest.raises(RuntimeError, match="task creation failed"):
            await service.submit("alice", [(0, make_item(source_id="m-1"))])
        assert service.in_flight("alice") == 0
        # No orphaned queued entry that would never run.
        assert await overlord.request_tracker.get_all_requests() == {}

        service._process_job = original_process_job
        outcome = await service.submit("alice", [(0, make_item(source_id="m-2"))])
        assert outcome["results"][0]["status"] == STATUS_ACCEPTED
        await finish_job(overlord, outcome["processing_id"])

    async def test_happy_path_releases_slot_exactly_once(self, memory_events):
        overlord = make_overlord(memory_events, extractor=StubExtractor(memory_events))
        service = overlord.memory_ingestion

        releases = []
        original_release = service._release_slot

        async def counting_release(user_id):
            releases.append(user_id)
            await original_release(user_id)

        service._release_slot = counting_release

        outcome = await service.submit("alice", [(0, make_item(source_id="m-1"))])
        state = await finish_job(overlord, outcome["processing_id"])
        assert state.status == RequestStatus.COMPLETED
        assert releases == ["alice"], "slot must be released exactly once (by the job)"
        assert service.in_flight("alice") == 0

        # Duplicate-only submits (no job) also release exactly once.
        releases.clear()
        duplicate = await service.submit("alice", [(0, make_item(source_id="m-1"))])
        assert duplicate["processing_id"] is None
        assert releases == ["alice"]
        assert service.in_flight("alice") == 0

    async def test_route_maps_accept_failure_to_formatted_500(self, memory_events):
        overlord = make_overlord(memory_events, extractor=StubExtractor(memory_events))
        formation = make_formation(overlord)
        overlord.request_tracker = BrokenTracker()

        response = await _handle_ingestion(
            formation,
            overlord,
            "alice",
            MemoryCreate(content="x", source="s", source_id="m-1"),
            "req-1",
        )
        assert response.status_code == 500
        body = response_data(response)
        assert body["success"] is False
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert "Failed to accept memory" in body["error"]["message"]
        # The failed accept did not consume the user's in-flight budget.
        assert overlord.memory_ingestion.in_flight("alice") == 0


# ----------------------------------------------------------------------
# Route behavior (single + batch + grant preservation)
# ----------------------------------------------------------------------


def make_formation(overlord, resolver=None):
    return SimpleNamespace(
        formation_id=FORMATION_ID,
        permission_resolver=resolver,
        _overlord=overlord,
        has_persistent_memory=lambda: True,
    )


def make_request(formation):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(formation=formation)),
        state=SimpleNamespace(request_id="req-1"),
    )


def response_data(response):
    from muxi.runtime.utils.fastjson import json

    return json.loads(response.body)


class TestRoutes:
    async def test_single_ingestion_returns_202_then_duplicate_200(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(memory_events, extractor=extractor)
        formation = make_formation(overlord)

        memory = MemoryCreate(content="I adopted a dog", source="gmail", source_id="m-1")
        response = await _handle_ingestion(formation, overlord, "alice", memory, "req-1")
        assert response.status_code == 202
        body = response_data(response)
        assert body["success"] is True
        assert body["data"]["status"] == STATUS_ACCEPTED
        assert body["data"]["duplicate"] is False
        processing_id = body["data"]["processing_id"]
        assert body["data"]["status_url"].endswith(processing_id)

        await finish_job(overlord, processing_id)

        replay = await _handle_ingestion(formation, overlord, "alice", memory, "req-2")
        assert replay.status_code == 200
        body = response_data(replay)
        assert body["data"]["duplicate"] is True
        assert body["data"]["event_id"]
        assert "processing_id" not in body["data"]

    async def test_single_ingestion_validation_422(self, memory_events):
        overlord = make_overlord(memory_events)
        formation = make_formation(overlord)
        memory = MemoryCreate(content="", source="gmail")
        response = await _handle_ingestion(formation, overlord, "alice", memory, "req-1")
        assert response.status_code == 422
        assert "'content'" in response_data(response)["error"]["message"]

    async def test_ingestion_scope_grant_behavior_unchanged(self, memory_events):
        # No permission resolver -> shared-scope ingestion is denied with
        # the same generic 403 as the direct write path (#215).
        overlord = make_overlord(memory_events, extractor=StubExtractor(memory_events))
        formation = make_formation(overlord)
        memory = MemoryCreate(
            content="team fact", source="gmail", source_id="m-2", scope="formation"
        )
        response = await _handle_ingestion(formation, overlord, "alice", memory, "req-1")
        assert response.status_code == 403
        # Denied requests never burn the idempotency key.
        events = await memory_events.list_events("alice", event_types=[EVENT_MEMORY_INGESTED])
        assert events == []

    async def test_ingestion_busy_maps_to_429(self, memory_events):
        gate = asyncio.Event()
        extractor = StubExtractor(memory_events, block_event=gate)
        overlord = make_overlord(
            memory_events, extractor=extractor, ingestion_config={"max_in_flight_per_user": 1}
        )
        formation = make_formation(overlord)

        first = await _handle_ingestion(
            formation,
            overlord,
            "alice",
            MemoryCreate(content="one", source="s", source_id="1"),
            "req-1",
        )
        assert first.status_code == 202

        second = await _handle_ingestion(
            formation,
            overlord,
            "alice",
            MemoryCreate(content="two", source="s", source_id="2"),
            "req-2",
        )
        assert second.status_code == 429
        body = response_data(second)
        assert body["error"]["code"] == "RATE_LIMITED"
        assert "ingestion jobs in flight" in body["error"]["message"]

        gate.set()
        await finish_job(overlord, response_data(first)["data"]["processing_id"])

    async def test_ingestion_unavailable_maps_to_503(self):
        overlord = make_overlord(None)
        formation = make_formation(overlord)
        memory = MemoryCreate(content="x", source="gmail")
        response = await _handle_ingestion(formation, overlord, "alice", memory, "req-1")
        assert response.status_code == 503
        assert "event substrate" in response_data(response)["error"]["message"]

    async def test_batch_route_per_item_statuses_in_order(self, memory_events):
        extractor = StubExtractor(memory_events)
        overlord = make_overlord(memory_events, extractor=extractor)
        formation = make_formation(overlord)
        request = make_request(formation)

        # Seed one item so the batch contains a duplicate.
        seeded = await _handle_ingestion(
            formation,
            overlord,
            "alice",
            MemoryCreate(content="seed", source="gmail", source_id="dup-1"),
            "req-0",
        )
        await finish_job(overlord, response_data(seeded)["data"]["processing_id"])

        batch = MemoryIngestBatch(
            items=[
                MemoryCreate(content="fresh item", source="gmail", source_id="new-1"),
                MemoryCreate(content="seed", source="gmail", source_id="dup-1"),
                MemoryCreate(content="no source at all"),
                MemoryCreate(content="needs grant", source="crm", scope="formation"),
            ]
        )
        response = await ingest_memories_batch(request, batch, x_user_id="alice")
        assert response.status_code == 200
        data = response_data(response)["data"]

        statuses = [item["status"] for item in data["items"]]
        assert statuses == [STATUS_ACCEPTED, STATUS_DUPLICATE, STATUS_INVALID, STATUS_INVALID]
        assert [item["index"] for item in data["items"]] == [0, 1, 2, 3]
        assert data["counts"] == {"accepted": 1, "duplicate": 1, "invalid": 2}
        assert "'source' is required" in data["items"][2]["error"]
        assert "permission" in data["items"][3]["error"].lower()

        await finish_job(overlord, data["processing_id"])

    async def test_batch_route_enforces_max_batch_items(self, memory_events):
        overlord = make_overlord(memory_events)
        overlord.input_validator = InputValidator(InputLimits(max_batch_items=2))
        formation = make_formation(overlord)
        request = make_request(formation)

        batch = MemoryIngestBatch(
            items=[
                MemoryCreate(content=f"item {i}", source="gmail", source_id=f"m-{i}")
                for i in range(3)
            ]
        )
        response = await ingest_memories_batch(request, batch, x_user_id="alice")
        assert response.status_code == 422
        assert "Batch too large" in response_data(response)["error"]["message"]

    async def test_batch_route_rejects_empty_items(self, memory_events):
        overlord = make_overlord(memory_events)
        formation = make_formation(overlord)
        request = make_request(formation)
        response = await ingest_memories_batch(
            request, MemoryIngestBatch(items=[]), x_user_id="alice"
        )
        assert response.status_code == 422

    async def test_batch_route_requires_user_header(self, memory_events):
        overlord = make_overlord(memory_events)
        formation = make_formation(overlord)
        request = make_request(formation)
        response = await ingest_memories_batch(
            request,
            MemoryIngestBatch(items=[MemoryCreate(content="x", source="s")]),
            x_user_id=None,
        )
        assert response.status_code == 400


# ----------------------------------------------------------------------
# Direct write path unchanged (regression pins)
# ----------------------------------------------------------------------


class TestDirectPathUnchanged:
    def test_requests_without_source_stay_on_direct_path(self):
        # The switch is the presence of `source`; the legacy fields
        # continue to build a plain content string.
        memory = MemoryCreate(content="User prefers Python")
        assert memory.source is None
        assert memory.get_content_string() == "User prefers Python"

    def test_structured_content_requires_ingestion_contract(self):
        memory = MemoryCreate(content={"k": "v"})
        with pytest.raises(ValueError, match="ingestion contract"):
            memory.get_content_string()
