"""Structured-recall scoring tests (exact strings + contradictions)."""

import pytest

from bench.memory.structured_scoring import (
    ContradictionCaseResult,
    StructuredQuestionResult,
    aggregate_contradictions,
    aggregate_exact_strings,
    aggregate_structured_results,
    exact_string_rank,
    render_structured_summary_extras,
)


class TestExactStringRank:
    def test_found_at_first_rank(self):
        assert exact_string_rank(["contact kai@x.example.com now"], ["kai@x.example.com"]) == 1

    def test_case_insensitive(self):
        assert exact_string_rank(["Reference INV-1234-AB filed"], ["inv-1234-ab"]) == 1

    def test_rank_is_where_last_string_completes(self):
        texts = ["first has code-a", "second has CODE-B"]
        assert exact_string_rank(texts, ["code-a", "code-b"]) == 2

    def test_missing_string_returns_none(self):
        assert exact_string_rank(["nothing relevant"], ["INV-1"]) is None

    def test_empty_texts_returns_none(self):
        assert exact_string_rank([], ["INV-1"]) is None

    def test_no_strings_raises(self):
        with pytest.raises(ValueError):
            exact_string_rank(["text"], [])


def _result(question_id, category, rank, error=None):
    return StructuredQuestionResult(
        question_id=question_id,
        question_type=category,
        is_abstention=False,
        category=category,
        exact_strings=["X-1"],
        exact_string_rank=rank,
        error=error,
    )


class TestAggregateExactStrings:
    def test_recall_at_k_counts_top_k_only(self):
        results = [
            _result("q1", "kg_relationship", 1),
            _result("q2", "kg_relationship", 9),
            _result("q3", "cross_agent", None),
        ]
        block = aggregate_exact_strings(results, k=5)
        assert block["overall"]["questions"] == 3
        assert block["overall"]["recall@5"] == pytest.approx(1 / 3)
        assert block["overall"]["recall@fetch"] == pytest.approx(2 / 3)
        assert block["overall"]["missed_question_ids"] == ["q2", "q3"]

    def test_by_category_breakdown(self):
        results = [
            _result("q1", "kg_relationship", 1),
            _result("q2", "cross_agent", None),
        ]
        block = aggregate_exact_strings(results, k=5)
        assert block["by_category"]["kg_relationship"]["recall@5"] == 1.0
        assert block["by_category"]["cross_agent"]["recall@5"] == 0.0

    def test_errored_and_untagged_excluded(self):
        results = [
            _result("q1", "kg_relationship", 1, error="boom"),
            StructuredQuestionResult(
                question_id="q2",
                question_type="narrative_recall",
                is_abstention=False,
                category="narrative_recall",
            ),
        ]
        assert aggregate_exact_strings(results, k=5) is None


class TestAggregateContradictions:
    def test_precision_and_recall(self):
        cases = [
            ContradictionCaseResult(case_id="c1", expected=2, detected=2, true_positives=2),
            ContradictionCaseResult(case_id="c2", expected=2, detected=4, true_positives=1),
        ]
        block = aggregate_contradictions(cases)
        assert block["expected"] == 4
        assert block["detected"] == 6
        assert block["precision"] == pytest.approx(3 / 6)
        assert block["recall"] == pytest.approx(3 / 4)
        assert set(block["by_case"]) == {"c1", "c2"}

    def test_zero_detected_has_null_precision(self):
        block = aggregate_contradictions(
            [ContradictionCaseResult(case_id="c1", expected=2, detected=0, true_positives=0)]
        )
        assert block["precision"] is None
        assert block["recall"] == 0.0

    def test_no_cases_returns_none(self):
        assert aggregate_contradictions([]) is None


class TestAggregateStructuredResults:
    def test_extends_tier1_metrics(self):
        results = [
            StructuredQuestionResult(
                question_id="q1",
                question_type="kg_relationship",
                is_abstention=False,
                category="kg_relationship",
                evidence_session_ids=["s1"],
                retrieved_session_ids=["s1"],
                exact_strings=["X-1"],
                exact_string_rank=1,
            )
        ]
        cases = [ContradictionCaseResult(case_id="c1", expected=1, detected=1, true_positives=1)]
        metrics = aggregate_structured_results(results, 5, cases)
        assert metrics["questions_scored"] == 1
        assert metrics["retrieval"]["session_level"]["overall"]["recall@5"] == 1.0
        assert metrics["exact_strings"]["overall"]["recall@5"] == 1.0
        assert metrics["contradiction_detection"]["precision"] == 1.0

    def test_summary_extras_render_missed_questions(self):
        results = [_result("q_missed", "kg_relationship", None)]
        metrics = aggregate_structured_results(results, 5, [])
        extras = render_structured_summary_extras(metrics, 5)
        assert "EXACT-STRING RECALL" in extras
        assert "q_missed" in extras

    def test_summary_extras_render_contradictions(self):
        cases = [ContradictionCaseResult(case_id="c1", expected=4, detected=5, true_positives=4)]
        metrics = aggregate_structured_results([], 5, cases)
        extras = render_structured_summary_extras(metrics, 5)
        assert "Contradiction detection" in extras
        assert "80.0%" in extras  # precision 4/5
        assert "100.0%" in extras  # recall 4/4
