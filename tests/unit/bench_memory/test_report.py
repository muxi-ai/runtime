"""Report generation and cost-estimation tests."""

import json

import pytest

from bench.memory.report import (
    build_report,
    estimate_cost_usd,
    relativize,
    render_summary,
    write_report,
)
from bench.memory.scoring import QuestionResult, aggregate_results


def _results():
    return [
        QuestionResult(
            question_id="q2",
            question_type="multi-session",
            is_abstention=False,
            evidence_session_ids=["s1"],
            retrieved_session_ids=["s1", "s2"],
            qa_correct=True,
        ),
        QuestionResult(
            question_id="q1",
            question_type="single-hop",
            is_abstention=False,
            evidence_session_ids=["s3"],
            retrieved_session_ids=["s9"],
            qa_correct=False,
        ),
    ]


def _report(**overrides):
    results = _results()
    defaults = {
        "benchmark": "longmemeval",
        "mode": "combined",
        "k": 5,
        "dataset_path": "bench/memory/fixtures/longmemeval_sample.json",
        "dataset_stats": {"cases": 2, "questions": 2, "sessions": 4, "fixture": True},
        "config": {"text_model": "openai/gpt-4o-mini"},
        "metrics": aggregate_results(results, 5),
        "results": results,
        "usage": {
            "llm_requests": 4,
            "tokens": {"total": 1200, "in": 1000, "out": 200},
            "tokens_by_model": {"openai/gpt-4o-mini": [1200, 1000, 200, 0, 0, 0]},
            "cost": estimate_cost_usd({"openai/gpt-4o-mini": [1200, 1000, 200, 0, 0, 0]}),
        },
        "wall_seconds": 12.345,
    }
    defaults.update(overrides)
    return build_report(**defaults)


class TestEstimateCost:
    def test_known_model_priced(self):
        cost = estimate_cost_usd({"openai/gpt-4o-mini": [0, 1_000_000, 1_000_000, 0, 0, 0]})
        assert cost["estimated_usd"] == pytest.approx(0.15 + 0.60)
        assert cost["per_model_usd"]["openai/gpt-4o-mini"] == pytest.approx(0.75)

    def test_local_model_free(self):
        cost = estimate_cost_usd({"local/nomic-ai/nomic-embed-text-v1.5": [500, 500, 0, 0, 0, 0]})
        assert cost["estimated_usd"] == 0.0
        assert cost["per_model_usd"]["local/nomic-ai/nomic-embed-text-v1.5"] == 0.0
        assert cost["unpriced_models"] == []

    def test_unknown_model_reported_unpriced(self):
        cost = estimate_cost_usd({"mystery/model": [10, 10, 0, 0, 0, 0]})
        assert cost["per_model_usd"]["mystery/model"] is None
        assert cost["unpriced_models"] == ["mystery/model"]

    def test_mixed_models(self):
        cost = estimate_cost_usd(
            {
                "openai/gpt-4o-mini": [0, 2_000_000, 0, 0, 0, 0],
                "mystery/model": [10, 10, 0, 0, 0, 0],
            }
        )
        assert cost["estimated_usd"] == pytest.approx(0.30)
        assert cost["unpriced_models"] == ["mystery/model"]

    def test_empty_breakdown(self):
        cost = estimate_cost_usd({})
        assert cost["per_model_usd"] == {}
        assert cost["unpriced_models"] == []


class TestRelativize:
    def test_inside_repo_root(self, tmp_path):
        target = tmp_path / "bench" / "memory" / "fixtures" / "x.json"
        assert relativize(target, tmp_path) == "bench/memory/fixtures/x.json"

    def test_outside_repo_root_unchanged(self, tmp_path):
        assert relativize("/datasets/full.json", tmp_path) == "/datasets/full.json"

    def test_no_repo_root(self):
        assert relativize("/datasets/full.json", None) == "/datasets/full.json"


class TestBuildReport:
    def test_results_sorted_by_question_id(self):
        report = _report()
        ids = [result["question_id"] for result in report["results"]]
        assert ids == sorted(ids)

    def test_core_fields_present(self):
        report = _report()
        assert report["benchmark"] == "longmemeval"
        assert report["mode"] == "combined"
        assert report["k"] == 5
        assert report["dataset"]["questions"] == 2
        assert report["metrics"]["questions_scored"] == 2
        assert "started_at" in report["run"]
        assert report["run"]["wall_seconds"] == 12.35

    def test_report_is_json_serializable(self):
        json.dumps(_report())


class TestWriteReport:
    def test_writes_sorted_deterministic_json(self, tmp_path):
        report = _report()
        path = write_report(report, tmp_path / "sub" / "report.json")
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["benchmark"] == "longmemeval"
        # Deterministic apart from run metadata: writing the same report
        # twice yields identical bytes.
        second = tmp_path / "again.json"
        write_report(report, second)
        assert path.read_text() == second.read_text()


class TestRenderSummary:
    def test_contains_headline_numbers(self):
        summary = render_summary(_report())
        assert "longmemeval" in summary
        assert "R@5=50.0%" in summary
        assert "QA accuracy" in summary
        assert "50.0%" in summary
        assert "tokens_in=1000" in summary

    def test_handles_missing_qa_block(self):
        results = [
            QuestionResult(
                question_id="q1",
                question_type="single-hop",
                is_abstention=False,
                evidence_session_ids=["s1"],
                retrieved_session_ids=["s1"],
            )
        ]
        report = _report(
            metrics=aggregate_results(results, 5),
            results=results,
        )
        summary = render_summary(report)
        assert "QA accuracy" not in summary

    def test_per_type_breakdown_rendered(self):
        summary = render_summary(_report())
        assert "multi-session" in summary
        assert "single-hop" in summary
