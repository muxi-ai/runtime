"""Unit tests for Memory Revamp Phase 2: the captain's log digest summarizer.

Covers digest prompt construction (merge of an existing entry, the lessons
toggle, the graph-extraction section) and response parsing (valid payloads,
fenced code blocks, malformed input, and item-level validation).
"""

from __future__ import annotations

from muxi.runtime.services.memory.log.summarizer import CaptainsLogSummarizer

ENTRY_DATE = "2026-07-06"

VALID_RESPONSE = (
    "{"
    '"summary": "Finalized the memory system PRD.",'
    '"decisions": ["Knowledge graph over flat facts", ""],'
    '"projects": ["MUXI"],'
    '"context": "No infrastructure gaps remain.",'
    '"lessons": ['
    '{"rule": "Prefer reportlab over fpdf", "context": "PDF generation"},'
    '{"rule": "  ", "context": "dropped: empty rule"},'
    '{"rule": "Keep summaries under 100 words"}'
    "],"
    '"entities": [{"name": "MUXI", "type": "project", "confidence": 0.9}],'
    '"relationships": []'
    "}"
)


class TestPromptConstruction:
    def test_prompt_includes_date_and_conversation(self):
        prompt = CaptainsLogSummarizer().build_prompt(
            "User: hello\nAssistant: hi", entry_date=ENTRY_DATE
        )
        assert ENTRY_DATE in prompt
        assert "User: hello\nAssistant: hi" in prompt
        assert '"summary"' in prompt
        assert '"decisions"' in prompt

    def test_prompt_asks_for_lessons_by_default(self):
        prompt = CaptainsLogSummarizer().build_prompt("text", entry_date=ENTRY_DATE)
        assert "LESSONS LEARNED" in prompt
        assert '"lessons"' in prompt

    def test_prompt_omits_lessons_when_disabled(self):
        prompt = CaptainsLogSummarizer().build_prompt(
            "text", entry_date=ENTRY_DATE, extract_lessons=False
        )
        assert "LESSONS LEARNED" not in prompt
        assert '"lessons"' not in prompt

    def test_prompt_merges_previous_entry(self):
        prompt = CaptainsLogSummarizer().build_prompt(
            "text",
            entry_date=ENTRY_DATE,
            previous_entry={
                "summary": "Morning: reviewed the PRD",
                "decisions": ["Ship Phase 1 first"],
                "projects": [],
                "context": None,
            },
        )
        assert "already exists" in prompt
        assert "Morning: reviewed the PRD" in prompt
        assert "Ship Phase 1 first" in prompt

    def test_prompt_requests_graph_extraction(self):
        prompt = CaptainsLogSummarizer().build_prompt("text", entry_date=ENTRY_DATE)
        assert '"entities"' in prompt
        assert '"relationships"' in prompt

    def test_prompt_forbids_sensitive_data(self):
        prompt = CaptainsLogSummarizer().build_prompt("text", entry_date=ENTRY_DATE)
        assert "sensitive" in prompt.lower()


class TestResponseParsing:
    def test_valid_response(self):
        digest = CaptainsLogSummarizer().parse_response(VALID_RESPONSE)
        assert digest["summary"] == "Finalized the memory system PRD."
        assert digest["decisions"] == ["Knowledge graph over flat facts"]
        assert digest["projects"] == ["MUXI"]
        assert digest["context"] == "No infrastructure gaps remain."
        assert digest["lessons"] == [
            {"rule": "Prefer reportlab over fpdf", "context": "PDF generation"},
            {"rule": "Keep summaries under 100 words", "context": None},
        ]

    def test_fenced_code_block(self):
        fenced = f"```json\n{VALID_RESPONSE}\n```"
        digest = CaptainsLogSummarizer().parse_response(fenced)
        assert digest is not None
        assert digest["summary"] == "Finalized the memory system PRD."

    def test_malformed_json_returns_none(self):
        assert CaptainsLogSummarizer().parse_response("not json at all") is None

    def test_non_dict_payload_returns_none(self):
        assert CaptainsLogSummarizer().parse_response("[1, 2, 3]") is None

    def test_empty_and_non_string_returns_none(self):
        summarizer = CaptainsLogSummarizer()
        assert summarizer.parse_response("") is None
        assert summarizer.parse_response(None) is None

    def test_missing_sections_default_empty(self):
        digest = CaptainsLogSummarizer().parse_response("{}")
        assert digest == {
            "summary": None,
            "decisions": [],
            "projects": [],
            "context": None,
            "lessons": [],
        }

    def test_wrong_section_types_dropped(self):
        digest = CaptainsLogSummarizer().parse_response(
            '{"summary": 42, "decisions": "not a list", "projects": [1, 2],'
            ' "context": ["nope"], "lessons": [{"context": "no rule"}, "junk"]}'
        )
        assert digest == {
            "summary": None,
            "decisions": [],
            "projects": [],
            "context": None,
            "lessons": [],
        }
