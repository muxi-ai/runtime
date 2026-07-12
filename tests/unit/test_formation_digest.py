"""Unit tests for the formation captain's log digest (Self-Improving Formation).

Covers the FormationLogSummarizer prompt/parse contract, the sentence-level
privacy lint (drops the offending sentence, never the digest; operational
content like tool names and time windows survives), the sentinel-scoped
digest write with its formation-scope memory event, same-date merging, the
consumed-flag semantics the tuning loop's checkpointing relies on, the
formation context block read side, and the memory lint's sentinel exclusion.
"""

from __future__ import annotations

import asyncio

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events.models import EVENT_LOG_ENTRY
from muxi.runtime.services.memory.events.service import MemoryEventService
from muxi.runtime.services.memory.log.formation import (
    FORMATION_LOG_USER_ID,
    FormationLogSummarizer,
    lint_formation_digest,
)
from muxi.runtime.services.memory.log.service import CaptainsLogService

FORMATION_ID = "formation-digest-test"

DIGEST_RESPONSE = (
    "{"
    '"summary": "Traffic doubled around midday. The jira MCP tool failed repeatedly '
    'between 14:00 and 16:00 UTC.",'
    '"context": "Most requests were FAQ-class."'
    "}"
)

ACTIVITY_REPORT = (
    "Window: 120 events spanning 2026-07-12 08:00 to 2026-07-12 18:00 (UTC); "
    "2 distinct user(s), 5 session(s), 12 tracked request(s).\n"
    "Warning/error clusters:\n- mcp.tool.failed: 9"
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


class TestSummarizer:
    def test_prompt_carries_report_and_privacy_rule(self):
        summarizer = FormationLogSummarizer()
        prompt = summarizer.build_prompt(ACTIVITY_REPORT, entry_date="2026-07-12")
        assert ACTIVITY_REPORT in prompt
        assert "NEVER include user identifiers" in prompt
        assert "2026-07-12" in prompt

    def test_prompt_merges_previous_entry(self):
        summarizer = FormationLogSummarizer()
        prompt = summarizer.build_prompt(
            ACTIVITY_REPORT,
            entry_date="2026-07-12",
            previous_entry={"summary": "Morning was quiet.", "context": ""},
        )
        assert "already exists" in prompt
        assert "Morning was quiet." in prompt

    def test_parse_valid_response(self):
        digest = FormationLogSummarizer().parse_response(DIGEST_RESPONSE)
        assert digest["summary"].startswith("Traffic doubled")
        assert digest["context"] == "Most requests were FAQ-class."

    def test_parse_tolerates_fenced_block(self):
        fenced = f"```json\n{DIGEST_RESPONSE}\n```"
        assert FormationLogSummarizer().parse_response(fenced) is not None

    def test_parse_failures_return_none(self):
        summarizer = FormationLogSummarizer()
        assert summarizer.parse_response("not json") is None
        assert summarizer.parse_response("[1, 2]") is None
        assert summarizer.parse_response('{"context": "no summary"}') is None
        assert summarizer.parse_response("") is None


class TestPrivacyLint:
    def test_user_id_sentence_dropped(self):
        text = "Traffic was heavy. User alice-99 hit rate limits. Tools were stable."
        cleaned, dropped = lint_formation_digest(text, ["alice-99"])
        assert dropped == 1
        assert "alice-99" not in cleaned
        assert "Traffic was heavy." in cleaned
        assert "Tools were stable." in cleaned

    def test_email_and_ssn_sentences_dropped(self):
        text = (
            "Load was normal. Contact bob@example.com asked twice. "
            "A value 123-45-6789 appeared. All good otherwise."
        )
        cleaned, dropped = lint_formation_digest(text, [])
        assert dropped == 2
        assert "bob@example.com" not in cleaned
        assert "123-45-6789" not in cleaned
        assert "All good otherwise." in cleaned

    def test_sensitive_keyword_sentence_dropped(self):
        text = "A password was pasted into chat. Routing stayed nominal."
        cleaned, dropped = lint_formation_digest(text, [])
        assert dropped == 1
        assert cleaned == "Routing stayed nominal."

    def test_card_length_digit_run_dropped(self):
        text = "Someone typed 4111111111111111 in a message. Latency was fine."
        cleaned, dropped = lint_formation_digest(text, [])
        assert dropped == 1
        assert cleaned == "Latency was fine."

    def test_separator_formatted_card_dropped(self):
        for card in ("4111 1111 1111 1111", "4111-1111-1111-1111"):
            text = f"A value {card} was pasted. Throughput held steady."
            cleaned, dropped = lint_formation_digest(text, [])
            assert dropped == 1, f"missed separator-formatted digits: {card}"
            assert cleaned == "Throughput held steady."

    def test_detector_failure_fails_closed(self, monkeypatch):
        from muxi.runtime.services.memory.log import formation as formation_module

        class ExplodingDetector:
            def detect(self, sentence):
                raise RuntimeError("model unavailable")

        monkeypatch.setattr(formation_module, "get_entity_detector", lambda: ExplodingDetector())
        cleaned, dropped = lint_formation_digest("Traffic was heavy today.", [])
        assert cleaned is None
        assert dropped == 1

    def test_operational_content_survives(self):
        text = (
            "The jira MCP tool rate-limited between 14:00 and 16:00 UTC. "
            "FAQ-class requests spiked 3x. gpt-4o-mini handled 80% of turns."
        )
        cleaned, dropped = lint_formation_digest(text, ["user-abc"])
        assert dropped == 0
        assert cleaned == text

    def test_short_user_ids_do_not_wipe_everything(self):
        # "0" is the single-user-mode id; substring-matching it would drop
        # every sentence containing a zero.
        text = "Around 10:00 traffic rose."
        cleaned, dropped = lint_formation_digest(text, ["0"])
        assert dropped == 0
        assert cleaned == text

    def test_empty_and_none_pass_through(self):
        assert lint_formation_digest(None, []) == (None, 0)
        assert lint_formation_digest("", []) == ("", 0)

    def test_all_sentences_dropped_returns_none(self):
        cleaned, dropped = lint_formation_digest("User alice-99 did a thing.", ["alice-99"])
        assert cleaned is None
        assert dropped == 1


class TestDigestFormation:
    def test_writes_sentinel_entry(self, service):
        model = FakeModel()
        result = asyncio.run(service.digest_formation(ACTIVITY_REPORT, model))
        assert result == {"entries": 1, "dropped_sentences": 0, "consumed": True}
        assert model.calls == 1
        assert ACTIVITY_REPORT in model.prompts[0]

        block = asyncio.run(service.get_formation_context_block())
        assert "Traffic doubled" in block

    def test_same_date_entry_is_merged_not_duplicated(self, service):
        model = FakeModel()
        asyncio.run(service.digest_formation(ACTIVITY_REPORT, model))
        asyncio.run(service.digest_formation(ACTIVITY_REPORT, model))
        assert "already exists" in model.prompts[1]
        entries = asyncio.run(service.storage.list_entries(FORMATION_LOG_USER_ID, limit=10))
        assert len(entries) == 1

    def test_lint_drops_user_identifying_sentence(self, service):
        leaky = '{"summary": "Load was fine. User alice-99 spammed the API.", ' '"context": ""}'
        result = asyncio.run(
            service.digest_formation(ACTIVITY_REPORT, FakeModel(leaky), known_user_ids=["alice-99"])
        )
        assert result["entries"] == 1
        assert result["dropped_sentences"] == 1
        block = asyncio.run(service.get_formation_context_block())
        assert "alice-99" not in block
        assert "Load was fine." in block

    def test_fully_linted_summary_skips_write_but_consumes(self, service):
        leaky = '{"summary": "User alice-99 spammed the API.", "context": ""}'
        result = asyncio.run(
            service.digest_formation(ACTIVITY_REPORT, FakeModel(leaky), known_user_ids=["alice-99"])
        )
        assert result == {"entries": 0, "dropped_sentences": 1, "consumed": True}
        assert asyncio.run(service.get_formation_context_block()) == ""

    def test_transient_failures_do_not_consume(self, service):
        no_model = asyncio.run(service.digest_formation(ACTIVITY_REPORT, None))
        assert no_model["consumed"] is False
        bad_parse = asyncio.run(service.digest_formation(ACTIVITY_REPORT, FakeModel("not json")))
        assert bad_parse["consumed"] is False

    def test_empty_report_consumes_without_llm_call(self, service):
        model = FakeModel()
        result = asyncio.run(service.digest_formation("", model))
        assert result == {"entries": 0, "dropped_sentences": 0, "consumed": True}
        assert model.calls == 0

    def test_disabled_service_consumes_without_writing(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        result = asyncio.run(service.digest_formation(ACTIVITY_REPORT, FakeModel()))
        assert result == {"entries": 0, "dropped_sentences": 0, "consumed": True}

    def test_records_formation_scope_memory_event(self, db_manager):
        event_log = MemoryEventService(db_manager, FORMATION_ID, config={"enabled": True})
        service = CaptainsLogService(db_manager, FORMATION_ID, event_log=event_log)
        asyncio.run(service.digest_formation(ACTIVITY_REPORT, FakeModel()))

        events = asyncio.run(event_log.storage.list_events(user_id=FORMATION_LOG_USER_ID))
        assert len(events) == 1
        assert events[0]["event_type"] == EVENT_LOG_ENTRY
        assert events[0]["scope_type"] == "formation"
        assert events[0]["scope_id"] == FORMATION_ID


class TestReadSide:
    def test_formation_block_empty_without_entries(self, service):
        assert asyncio.run(service.get_formation_context_block()) == ""

    def test_formation_entries_do_not_leak_into_user_block(self, service):
        asyncio.run(service.digest_formation(ACTIVITY_REPORT, FakeModel()))
        user_block = asyncio.run(service.get_context_block("real-user"))
        assert user_block == ""


class TestMemoryLintExclusion:
    def test_sentinel_excluded_from_user_enumeration(self, db_manager):
        from muxi.runtime.services.memory.lint import MemoryLintService

        service = CaptainsLogService(db_manager, FORMATION_ID)
        asyncio.run(service.digest_formation(ACTIVITY_REPORT, FakeModel()))
        asyncio.run(
            service.apply_log_entry_event(
                "real-user", {"date": "2026-07-12", "summary": "User day."}
            )
        )

        lint = MemoryLintService(
            db_manager,
            FORMATION_ID,
            config={"enabled": True},
            knowledge_graph=None,
            captains_log=service,
            artifact_memory=None,
            index=None,
        )
        users = asyncio.run(lint._list_user_ids())
        assert FORMATION_LOG_USER_ID not in users
        assert "real-user" in users
