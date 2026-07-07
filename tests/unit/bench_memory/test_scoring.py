"""Metric correctness tests for the memory benchmark scorer.

These numbers drive published results and tuning decisions, so every
metric is pinned with hand-computed expectations, including edge cases
(duplicates, abstention, errors, k cutoffs, tie-breaking).
"""

import pytest

from bench.memory.scoring import (
    QuestionResult,
    aggregate_results,
    coverage_at_k,
    hit_at_k,
    mrr,
    ranked_unique,
    reciprocal_rank_fusion,
)


class TestRankedUnique:
    def test_preserves_first_seen_order(self):
        assert ranked_unique(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]

    def test_empty(self):
        assert ranked_unique([]) == []

    def test_no_duplicates_passthrough(self):
        assert ranked_unique(["x", "y", "z"]) == ["x", "y", "z"]


class TestHitAtK:
    def test_hit_at_top_rank(self):
        assert hit_at_k(["s1", "s2", "s3"], ["s1"], k=1) is True

    def test_hit_exactly_at_k(self):
        assert hit_at_k(["s1", "s2", "s3"], ["s3"], k=3) is True

    def test_miss_just_below_cutoff(self):
        assert hit_at_k(["s1", "s2", "s3"], ["s3"], k=2) is False

    def test_any_evidence_suffices(self):
        assert hit_at_k(["s1", "s2"], ["s9", "s2"], k=2) is True

    def test_no_evidence_retrieved(self):
        assert hit_at_k(["s1", "s2"], ["s9"], k=5) is False

    def test_empty_retrieval_is_miss(self):
        assert hit_at_k([], ["s1"], k=5) is False

    def test_duplicates_collapse_to_best_rank(self):
        # s2 first appears at rank 2; duplicates must not push it out.
        assert hit_at_k(["s1", "s2", "s1", "s1"], ["s2"], k=2) is True

    def test_k_zero_rejected(self):
        with pytest.raises(ValueError):
            hit_at_k(["s1"], ["s1"], k=0)

    def test_no_evidence_ids_rejected(self):
        with pytest.raises(ValueError):
            hit_at_k(["s1"], [], k=5)


class TestCoverageAtK:
    def test_full_coverage(self):
        assert coverage_at_k(["s1", "s2"], ["s1", "s2"], k=2) == 1.0

    def test_half_coverage(self):
        assert coverage_at_k(["s1", "s3"], ["s1", "s2"], k=2) == 0.5

    def test_zero_coverage(self):
        assert coverage_at_k(["s3", "s4"], ["s1", "s2"], k=2) == 0.0

    def test_cutoff_applies_before_matching(self):
        # s2 is retrieved but at rank 3, beyond k=2.
        assert coverage_at_k(["s9", "s8", "s2"], ["s1", "s2"], k=2) == 0.0

    def test_duplicate_evidence_ids_counted_once(self):
        assert coverage_at_k(["s1"], ["s1", "s1"], k=1) == 1.0

    def test_no_evidence_ids_rejected(self):
        with pytest.raises(ValueError):
            coverage_at_k(["s1"], [], k=1)


class TestMRR:
    def test_first_rank(self):
        assert mrr(["s1", "s2"], ["s1"]) == 1.0

    def test_third_rank(self):
        assert mrr(["a", "b", "s1"], ["s1"]) == pytest.approx(1 / 3)

    def test_first_matching_evidence_wins(self):
        assert mrr(["a", "e2", "e1"], ["e1", "e2"]) == pytest.approx(1 / 2)

    def test_not_retrieved(self):
        assert mrr(["a", "b"], ["s1"]) == 0.0

    def test_duplicates_do_not_shift_rank(self):
        assert mrr(["a", "a", "s1"], ["s1"]) == pytest.approx(1 / 2)

    def test_no_evidence_rejected(self):
        with pytest.raises(ValueError):
            mrr(["a"], [])


class TestReciprocalRankFusion:
    def test_agreement_ranks_first(self):
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "c", "b"]])
        assert fused[0] == "a"

    def test_single_ranking_passthrough_order(self):
        assert reciprocal_rank_fusion([["x", "y", "z"]]) == ["x", "y", "z"]

    def test_exact_scores(self):
        # a: 1/61 + 1/62 ; b: 1/62 + 1/61 -> tie, first-seen order wins (a).
        fused = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
        assert fused == ["a", "b"]

    def test_id_unique_to_one_list_still_ranked(self):
        fused = reciprocal_rank_fusion([["a", "b"], ["c"]])
        assert set(fused) == {"a", "b", "c"}
        # c holds rank 1 in its list (1/61), beating b's rank 2 (1/62).
        assert fused.index("c") < fused.index("b")

    def test_empty_rankings(self):
        assert reciprocal_rank_fusion([[], []]) == []

    def test_invalid_rrf_k(self):
        with pytest.raises(ValueError):
            reciprocal_rank_fusion([["a"]], rrf_k=0)


def _result(
    question_id="q1",
    question_type="single-session-user",
    is_abstention=False,
    evidence_session_ids=("s1",),
    evidence_turn_ids=(),
    retrieved_session_ids=("s1", "s2"),
    retrieved_turn_ids=(),
    qa_correct=None,
    error=None,
):
    return QuestionResult(
        question_id=question_id,
        question_type=question_type,
        is_abstention=is_abstention,
        evidence_session_ids=list(evidence_session_ids),
        evidence_turn_ids=list(evidence_turn_ids),
        retrieved_session_ids=list(retrieved_session_ids),
        retrieved_turn_ids=list(retrieved_turn_ids),
        qa_correct=qa_correct,
        error=error,
    )


class TestQuestionResultMetrics:
    def test_session_metrics_values(self):
        result = _result(retrieved_session_ids=["s9", "s1"], evidence_session_ids=["s1"])
        metrics = result.session_metrics(k=5)
        assert metrics["hit@5"] == 1.0
        assert metrics["coverage@5"] == 1.0
        assert metrics["mrr"] == pytest.approx(1 / 2)

    def test_abstention_returns_none(self):
        assert _result(is_abstention=True).session_metrics(k=5) is None

    def test_error_returns_none(self):
        assert _result(error="boom").session_metrics(k=5) is None

    def test_turn_metrics_absent_without_turn_evidence(self):
        assert _result(evidence_turn_ids=()).turn_metrics(k=5) is None

    def test_turn_metrics_values(self):
        result = _result(
            evidence_turn_ids=["t1", "t2"],
            retrieved_turn_ids=["t2", "x", "t1"],
        )
        metrics = result.turn_metrics(k=2)
        assert metrics["hit@2"] == 1.0
        assert metrics["coverage@2"] == 0.5  # t1 is at rank 3
        assert metrics["mrr"] == 1.0


class TestAggregateResults:
    def test_overall_recall_is_mean_of_hits(self):
        results = [
            _result(question_id="q1", retrieved_session_ids=["s1"]),  # hit
            _result(question_id="q2", retrieved_session_ids=["s9"]),  # miss
        ]
        agg = aggregate_results(results, k=5)
        overall = agg["retrieval"]["session_level"]["overall"]
        assert overall["questions"] == 2
        assert overall["recall@5"] == 0.5

    def test_by_question_type_breakdown(self):
        results = [
            _result(question_id="q1", question_type="multi-session"),
            _result(
                question_id="q2",
                question_type="temporal-reasoning",
                retrieved_session_ids=["nope"],
            ),
        ]
        by_type = aggregate_results(results, k=5)["retrieval"]["session_level"]["by_question_type"]
        assert by_type["multi-session"]["recall@5"] == 1.0
        assert by_type["temporal-reasoning"]["recall@5"] == 0.0

    def test_abstention_and_errors_excluded_and_counted(self):
        results = [
            _result(question_id="q1"),
            _result(question_id="q2", is_abstention=True, evidence_session_ids=()),
            _result(question_id="q3", error="ValueError: x"),
        ]
        agg = aggregate_results(results, k=5)
        assert agg["questions_total"] == 3
        assert agg["questions_scored"] == 1
        assert agg["questions_abstention"] == 1
        assert agg["questions_errored"] == 1
        assert agg["retrieval"]["session_level"]["overall"]["questions"] == 1

    def test_turn_level_none_when_no_turn_evidence(self):
        agg = aggregate_results([_result()], k=5)
        assert agg["retrieval"]["turn_level"] is None

    def test_qa_accuracy(self):
        results = [
            _result(question_id="q1", qa_correct=True),
            _result(question_id="q2", qa_correct=False),
            _result(question_id="q3", qa_correct=True),
            _result(question_id="q4"),  # QA not run
        ]
        qa = aggregate_results(results, k=5)["qa"]
        assert qa["overall"]["questions"] == 3
        assert qa["overall"]["accuracy"] == pytest.approx(2 / 3)

    def test_qa_block_absent_when_not_run(self):
        assert aggregate_results([_result()], k=5)["qa"] is None

    def test_all_abstention_gives_no_session_block(self):
        results = [_result(is_abstention=True, evidence_session_ids=())]
        assert aggregate_results(results, k=5)["retrieval"]["session_level"] is None

    def test_k_recorded(self):
        assert aggregate_results([_result()], k=7)["k"] == 7
