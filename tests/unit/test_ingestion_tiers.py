"""Unit tests for the ingestion tier-escalation heuristics (maturation).

Covers, per PRD criterion:

  * Tier-0 signal extraction: identities (emails/handles/proper names),
    dates, money, commitment language -- pure regex, deterministic.
  * decide_tier(): per-source pins, priority flags, synthesis-worthy
    categories (personal/work/unknown), ambiguous classification,
    high-signal T3 escalation, and the T1 rest state.
  * TierBudget: per-job caps demote T3 -> T2 -> T1 (never drop).
  * Fail-fast config validation of memory.ingestion (tiers /
    entity_resolution / synthesis / source tier pins), and that the
    formation validator reuses the same parser.
  * Service integration: tier + reason on the item report, escalation
    observability, Tier-1 verbatim store, tier-model resolution for
    T2/T3, and legacy behavior with tiers disabled.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from muxi.runtime.formation.background.request_tracker import RequestTracker
from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.formation.overlord.input_validation import InputLimits, InputValidator
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import MemoryEventService
from muxi.runtime.services.memory.events.models import MemoryEvent, ProjectionCheckpoint
from muxi.runtime.services.memory.ingest import (
    TIER_FRONTIER,
    TIER_LOCAL,
    TIER_STANDARD,
    MemoryIngestionService,
    parse_ingestion_config,
    validate_item,
)
from muxi.runtime.services.memory.ingest.classification import (
    CATEGORY_AUTOMATED,
    CATEGORY_PERSONAL,
    CATEGORY_TRANSACTIONAL,
    CATEGORY_UNKNOWN,
    CATEGORY_WORK,
    INTENT_PREFIX,
)
from muxi.runtime.services.memory.ingest.tiers import (
    TierBudget,
    content_signals,
    decide_tier,
    signal_score,
)

FORMATION_ID = "tiers-test-formation"
EVENT_TABLES = [MemoryEvent.__table__, ProjectionCheckpoint.__table__]

HIGH_SIGNAL_TEXT = (
    "Agreed with Ryan Leveille (ryan@nabo.dev): the contract deadline is "
    "2026-08-01, deliverables due by EOD, budget $12,000."
)


def settings(**overrides):
    config = {"tiers": overrides} if overrides else {}
    return parse_ingestion_config(config).tiers


# ----------------------------------------------------------------------
# Tier 0: signal extraction
# ----------------------------------------------------------------------


class TestContentSignals:
    def test_identity_mentions(self):
        signals = content_signals("Email ryan@nabo.dev or ping @rleveille; ask Ryan Leveille")
        assert signals["identities"] == 3

    def test_dates(self):
        signals = content_signals("Ship on 2026-08-01, review next week, close by end of Q3")
        assert signals["dates"] == 3

    def test_money(self):
        signals = content_signals("Invoice for $1,200.50 plus 300 EUR")
        assert signals["money"] == 2

    def test_commitments(self):
        signals = content_signals("The deadline was agreed; I will deliver the action items")
        assert signals["commitments"] >= 2

    def test_empty_content(self):
        assert signal_score(content_signals("")) == 0

    def test_score_caps_per_signal_class(self):
        text = " ".join(f"user{i}@example.com" for i in range(10))
        assert signal_score(content_signals(text)) == 3  # identities capped at 3

    def test_high_signal_text_crosses_default_threshold(self):
        assert signal_score(content_signals(HIGH_SIGNAL_TEXT)) >= 5


# ----------------------------------------------------------------------
# Escalation decision per criterion
# ----------------------------------------------------------------------


class TestDecideTier:
    def test_synthesis_worthy_categories_escalate_to_t2(self):
        no_signal = content_signals("hello")
        for category in (CATEGORY_PERSONAL, CATEGORY_WORK, CATEGORY_UNKNOWN):
            tier, reason = decide_tier(category, 0.4, no_signal, settings())
            assert tier == TIER_STANDARD, category
            assert reason == f"category:{category}"

    def test_noise_categories_rest_at_t1(self):
        no_signal = content_signals("hello")
        for category in (CATEGORY_AUTOMATED, CATEGORY_TRANSACTIONAL):
            tier, reason = decide_tier(category, 0.4, no_signal, settings())
            assert tier == TIER_LOCAL, category
            assert reason == f"low_signal_category:{category}"

    def test_ambiguous_classification_escalates_to_t2(self):
        tier, reason = decide_tier(CATEGORY_AUTOMATED, 0.01, content_signals("hello"), settings())
        assert tier == TIER_STANDARD
        assert reason.startswith("ambiguous_classification:")

    def test_high_signal_t2_item_escalates_to_t3(self):
        tier, reason = decide_tier(
            CATEGORY_WORK, 0.4, content_signals(HIGH_SIGNAL_TEXT), settings()
        )
        assert tier == TIER_FRONTIER
        assert reason.startswith("high_signal:score=")

    def test_high_signal_noise_stays_t1(self):
        # High-signal escalation applies to synthesis-worthy items only:
        # a promotional blast full of prices is still noise.
        tier, _ = decide_tier(
            CATEGORY_TRANSACTIONAL, 0.4, content_signals(HIGH_SIGNAL_TEXT), settings()
        )
        assert tier == TIER_LOCAL

    def test_priority_flag_escalates_to_t3(self):
        tier, reason = decide_tier(
            CATEGORY_AUTOMATED, 0.4, content_signals("hello"), settings(), priority="HIGH"
        )
        assert tier == TIER_FRONTIER
        assert reason == "priority_flag"

    def test_source_pin_wins(self):
        tier, reason = decide_tier(
            CATEGORY_PERSONAL,
            0.4,
            content_signals(HIGH_SIGNAL_TEXT),
            settings(),
            source_tier=1,
        )
        assert tier == TIER_LOCAL
        assert reason == "source_pin:1"

    def test_t3_signal_score_is_configurable(self):
        strict = settings(t3_signal_score=100)
        tier, _ = decide_tier(CATEGORY_WORK, 0.4, content_signals(HIGH_SIGNAL_TEXT), strict)
        assert tier == TIER_STANDARD

    def test_tiers_disabled_restores_legacy_always_extract(self):
        tier, reason = decide_tier(
            CATEGORY_AUTOMATED, 0.4, content_signals("hello"), settings(enabled=False)
        )
        assert tier == TIER_STANDARD
        assert reason == "tiers_disabled"


# ----------------------------------------------------------------------
# Budget caps
# ----------------------------------------------------------------------


class TestTierBudget:
    def test_t3_budget_demotes_to_t2_then_t1(self):
        budget = TierBudget(t2_remaining=1, t3_remaining=1)
        assert budget.admit(TIER_FRONTIER) == (TIER_FRONTIER, False)
        # T3 exhausted: demote into the T2 budget.
        assert budget.admit(TIER_FRONTIER) == (TIER_STANDARD, True)
        # Both exhausted: rest at T1 (never dropped).
        assert budget.admit(TIER_FRONTIER) == (TIER_LOCAL, True)

    def test_t2_budget_demotes_to_t1(self):
        budget = TierBudget(t2_remaining=1, t3_remaining=0)
        assert budget.admit(TIER_STANDARD) == (TIER_STANDARD, False)
        assert budget.admit(TIER_STANDARD) == (TIER_LOCAL, True)

    def test_t1_is_never_budgeted(self):
        budget = TierBudget(t2_remaining=0, t3_remaining=0)
        for _ in range(5):
            assert budget.admit(TIER_LOCAL) == (TIER_LOCAL, False)


# ----------------------------------------------------------------------
# Fail-fast config validation
# ----------------------------------------------------------------------


class TestConfigValidation:
    def test_defaults_parse(self):
        parsed = parse_ingestion_config(None)
        assert parsed.tiers.enabled is True
        assert parsed.synthesis.hot.interval_seconds == 300.0
        assert parsed.synthesis.cold_cold.interval_seconds == 604800.0
        assert parsed.entity_resolution.auto_merge_threshold == 0.85

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError, match="memory.ingestion must be a dictionary"):
            parse_ingestion_config("yes")

    def test_bad_ambiguity_margin(self):
        with pytest.raises(ValueError, match="tiers.ambiguity_margin"):
            parse_ingestion_config({"tiers": {"ambiguity_margin": 2}})

    def test_bad_budget(self):
        with pytest.raises(ValueError, match="t3_items_per_job"):
            parse_ingestion_config({"tiers": {"budget": {"t3_items_per_job": 0}}})

    def test_bad_source_tier_pin(self):
        with pytest.raises(ValueError, match=r"sources.crm.tier"):
            parse_ingestion_config({"sources": {"crm": {"tier": 4}}})

    def test_flag_threshold_must_not_exceed_merge_threshold(self):
        with pytest.raises(ValueError, match="flag_threshold"):
            parse_ingestion_config(
                {"entity_resolution": {"auto_merge_threshold": 0.5, "flag_threshold": 0.9}}
            )

    def test_bad_cadence_interval(self):
        with pytest.raises(ValueError, match=r"synthesis.warm.interval_seconds"):
            parse_ingestion_config({"synthesis": {"warm": {"interval_seconds": -5}}})

    def test_bad_cadence_enabled_type(self):
        with pytest.raises(ValueError, match=r"synthesis.cold.enabled"):
            parse_ingestion_config({"synthesis": {"cold": {"enabled": "yes"}}})

    def test_formation_validator_reuses_parser(self):
        validator = FormationValidator()
        validator._validate_memory_config({"ingestion": {"tiers": {"t3_signal_score": "many"}}})
        assert any("t3_signal_score" in e for e in validator.result.errors)

    def test_formation_validator_accepts_valid_block(self):
        validator = FormationValidator()
        validator._validate_memory_config(
            {
                "ingestion": {
                    "sources": {"gmail": {"filter": "lenient", "tier": 3}},
                    "tiers": {"models": {"t3": "openai/gpt-5"}},
                    "entity_resolution": {"auto_merge_threshold": 0.9},
                    "synthesis": {"cold_cold": {"enabled": False}},
                }
            }
        )
        assert not [e for e in validator.result.errors if "ingestion" in e]


# ----------------------------------------------------------------------
# Service integration (tier drives the pipeline)
# ----------------------------------------------------------------------


class StubClassifier:
    def __init__(self, margins=None):
        self.margins = margins or {}

    async def register(self, spec):
        pass

    async def classify_binary(self, name, text):
        margin = self.margins.get(name, -0.5)
        return margin > 0, margin


class RecordingLTM:
    def __init__(self):
        self.rows = []

    async def add(self, content, metadata=None, user_id=None, collection=None, scope=None):
        self.rows.append({"content": content, "collection": collection, "scope": scope})
        return f"m{len(self.rows)}"


class RecordingExtractor:
    extraction_interval = 1

    def __init__(self):
        self.calls = []

    async def process_conversation_turn(self, **kwargs):
        self.calls.append(kwargs)


def make_overlord(memory_events, *, classifier_category=CATEGORY_PERSONAL, ingestion_config=None):
    extractor = RecordingExtractor()
    overlord = SimpleNamespace(
        formation_config={"memory": {"ingestion": ingestion_config or {}}},
        formation_id=FORMATION_ID,
        memory_events=memory_events,
        request_tracker=RequestTracker(),
        long_term_memory=RecordingLTM(),
        extractor=extractor,
        knowledge_graph=None,
        default_model=None,
        is_multi_user=False,
        input_validator=InputValidator(InputLimits()),
    )
    classifier = StubClassifier({f"{INTENT_PREFIX}{classifier_category}": 0.4})

    async def _get_local_classifier():
        return classifier

    overlord._get_local_classifier = _get_local_classifier
    return overlord


@pytest.fixture
def memory_events(tmp_path):
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/events.db")
    db_manager.create_tables(Base.metadata, tables=EVENT_TABLES)
    service = MemoryEventService(db_manager, FORMATION_ID, config={"enabled": True})
    yield service
    db_manager.engine.dispose()


def make_item(**overrides):
    payload = {"content": "I moved to London last month", "source": "gmail", "source_id": "m-1"}
    payload.update(overrides)
    item, error = validate_item(payload)
    assert error is None, error
    return item


async def run_one(overlord, item):
    service = MemoryIngestionService(overlord)
    outcome = await service.submit("alice", [(0, item)])
    state = await overlord.request_tracker.get_request(outcome["processing_id"])
    await state.task_ref
    state = await overlord.request_tracker.get_request(outcome["processing_id"])
    return state.result["items"][0]


class TestServiceIntegration:
    async def test_t2_report_and_extractor_default_model(self, memory_events):
        overlord = make_overlord(memory_events)
        report = await run_one(overlord, make_item())
        assert report["tier"] == TIER_STANDARD
        assert report["tier_reason"] == f"category:{CATEGORY_PERSONAL}"
        (call,) = overlord.extractor.calls
        assert call["model"] is None  # default extraction model

    async def test_t1_stores_verbatim_without_extractor(self, memory_events):
        overlord = make_overlord(
            memory_events,
            classifier_category=CATEGORY_TRANSACTIONAL,
            ingestion_config={"sources": {"gmail": {"filter": "off"}}},
        )
        report = await run_one(overlord, make_item(content="Order #4521 shipped, $42 paid"))
        assert report["tier"] == TIER_LOCAL
        assert report["disposition"] == "stored"
        assert overlord.extractor.calls == []
        assert len(overlord.long_term_memory.rows) == 1

    async def test_t3_resolves_configured_frontier_model(self, memory_events):
        overlord = make_overlord(
            memory_events,
            classifier_category=CATEGORY_WORK,
            ingestion_config={"tiers": {"models": {"t3": "openai/gpt-5"}}},
        )
        resolved = []

        async def _get_or_create_model(model_config, cache_scope):
            resolved.append((model_config["model"], cache_scope))
            return f"llm:{model_config['model']}"

        overlord._get_or_create_model = _get_or_create_model
        report = await run_one(overlord, make_item(content=HIGH_SIGNAL_TEXT))
        assert report["tier"] == TIER_FRONTIER
        assert report["tier_reason"].startswith("high_signal:")
        assert resolved == [("openai/gpt-5", "ingestion:t3")]
        (call,) = overlord.extractor.calls
        assert call["model"] == "llm:openai/gpt-5"

    async def test_budget_cap_demotes_and_records_reason(self, memory_events):
        overlord = make_overlord(
            memory_events,
            ingestion_config={"tiers": {"budget": {"t2_items_per_job": 1}}},
        )
        service = MemoryIngestionService(overlord)
        items = [
            (0, make_item(source_id="m-1", content="I love hiking in Wales")),
            (1, make_item(source_id="m-2", content="My sister lives in Boston")),
        ]
        outcome = await service.submit("alice", items)
        state = await overlord.request_tracker.get_request(outcome["processing_id"])
        await state.task_ref
        state = await overlord.request_tracker.get_request(outcome["processing_id"])
        by_index = {r["index"]: r for r in state.result["items"]}
        assert by_index[0]["tier"] == TIER_STANDARD
        assert by_index[1]["tier"] == TIER_LOCAL
        assert "budget_capped_from_t2" in by_index[1]["tier_reason"]
        # Only the admitted item spent LLM extraction.
        assert len(overlord.extractor.calls) == 1

    async def test_budget_resets_per_job(self, memory_events):
        overlord = make_overlord(
            memory_events,
            ingestion_config={"tiers": {"budget": {"t2_items_per_job": 1}}},
        )
        first = await run_one(overlord, make_item(source_id="m-1"))
        second = await run_one(overlord, make_item(source_id="m-2"))
        assert first["tier"] == second["tier"] == TIER_STANDARD

    async def test_source_pin_via_config(self, memory_events):
        overlord = make_overlord(
            memory_events,
            classifier_category=CATEGORY_PERSONAL,
            ingestion_config={"sources": {"gmail": {"tier": 1}}},
        )
        report = await run_one(overlord, make_item())
        assert report["tier"] == TIER_LOCAL
        assert report["tier_reason"] == "source_pin:1"
        assert overlord.extractor.calls == []

    async def test_tiers_disabled_keeps_legacy_pipeline(self, memory_events):
        overlord = make_overlord(
            memory_events,
            classifier_category=CATEGORY_AUTOMATED,
            ingestion_config={
                "tiers": {"enabled": False},
                "sources": {"gmail": {"filter": "off"}},
            },
        )
        report = await run_one(overlord, make_item(content="Build #8841 passed"))
        assert report["tier"] == TIER_STANDARD
        assert report["tier_reason"] == "tiers_disabled"
        assert len(overlord.extractor.calls) == 1
