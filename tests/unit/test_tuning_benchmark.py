"""Unit tests for the benchmark observation (Self-Improving Formation, Phase 3).

Pins the BenchmarkStep contract against a fake harness (a real
subprocess with the real CLI surface, no LLM): explicit opt-in
discovery, the once-per-interval run policy, score parsing and
lower-is-better inversion, carry-forward across failed/skipped passes,
MUXI.md plumbing, timeout kill, and the report block's delta rendering.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from muxi.runtime.services.tuning.benchmark import (
    BENCH_ROOT_ENV,
    SUITES,
    BenchmarkStep,
    discover_bench_root,
    parse_report,
)

GOOD_REPORT = {
    "k": 5,
    "metrics": {
        "retrieval": {"session_level": {"overall": {"recall@5": 0.8}}},
        "qa": {"overall": {"accuracy": 0.75}},
    },
    "usage": {"cost": {"estimated_usd": 0.003}},
}

# A fake runner speaking the real CLI surface: writes a canned report
# to --output (echoing --muxi-md so tests can assert the plumbing).
FAKE_RUNNER = f"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--fixture", action="store_true")
parser.add_argument("--qa", action="store_true")
parser.add_argument("--output", required=True)
parser.add_argument("--muxi-md", default=None)
args = parser.parse_args()
report = json.loads({json.dumps(json.dumps(GOOD_REPORT))})
if args.muxi_md:
    report["config"] = {{"muxi_md": args.muxi_md}}
with open(args.output, "w") as handle:
    json.dump(report, handle)
"""

FAILING_RUNNER = """
import sys
print("embedding model unavailable", file=sys.stderr)
sys.exit(1)
"""

# Writes a complete report, then dies -- the native-teardown segfault
# shape observed on macOS. The report is the verdict, not the exit code.
CRASH_AFTER_REPORT_RUNNER = FAKE_RUNNER + """
sys.exit(11)
"""

SLEEPING_RUNNER = """
import time
time.sleep(60)
"""


def build_harness(root: Path, runner_source: str = FAKE_RUNNER) -> Path:
    """Lay down a fake ``bench`` package satisfying discovery and -m runs."""
    memory = root / "bench" / "memory"
    memory.mkdir(parents=True, exist_ok=True)
    (root / "bench" / "__init__.py").write_text("")
    (memory / "__init__.py").write_text("")
    (memory / "runner.py").write_text("")  # the discovery marker
    for suite in SUITES:
        module_file = suite["module"].rsplit(".", 1)[-1] + ".py"
        (memory / module_file).write_text(runner_source)
    return root


@pytest.fixture
def step(tmp_path):
    step = BenchmarkStep(base_dir=str(tmp_path / "tuner"))
    step.suite_timeout_seconds = 30.0
    return step


class TestDiscovery:
    def test_unset_env_means_no_harness(self, monkeypatch):
        monkeypatch.delenv(BENCH_ROOT_ENV, raising=False)
        assert discover_bench_root() is None

    def test_empty_env_means_no_harness(self, monkeypatch):
        monkeypatch.setenv(BENCH_ROOT_ENV, "")
        assert discover_bench_root() is None

    def test_root_without_harness_means_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path))
        assert discover_bench_root() is None

    def test_valid_root_resolves(self, tmp_path, monkeypatch):
        build_harness(tmp_path)
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path))
        assert discover_bench_root() == tmp_path


class TestParseReport:
    def test_scores_extracted(self):
        scores = parse_report(GOOD_REPORT)
        assert scores == {
            "k": 5.0,
            "recall_at_k": 0.8,
            "qa_accuracy": 0.75,
            "estimated_usd": 0.003,
        }

    def test_partial_report_is_unusable(self):
        assert parse_report({**GOOD_REPORT, "partial": True}) is None

    def test_errored_questions_make_the_report_unusable(self):
        payload = json.loads(json.dumps(GOOD_REPORT))
        payload["metrics"]["questions_errored"] = 2
        assert parse_report(payload) is None

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            [],
            {},
            {"k": 5, "metrics": {}},
            {"k": 5, "metrics": {"retrieval": {}, "qa": {}}},
            {"k": "5", "metrics": GOOD_REPORT["metrics"]},
        ],
    )
    def test_malformed_reports_are_unusable(self, payload):
        assert parse_report(payload) is None


class TestObserve:
    def test_no_harness_skips_with_empty_metrics(self, step, monkeypatch):
        monkeypatch.delenv(BENCH_ROOT_ENV, raising=False)
        result = asyncio.run(step.observe())
        assert BENCH_ROOT_ENV in result["skipped"]
        assert result["metrics"] == {}
        assert result["report_block"] == ""
        assert result["suites_run"] == []

    def test_run_inverts_scores_and_persists(self, step, tmp_path, monkeypatch):
        build_harness(tmp_path / "harness")
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path / "harness"))
        result = asyncio.run(step.observe())

        assert sorted(result["suites_run"]) == sorted(s["name"] for s in SUITES)
        assert result["skipped"] is None
        for suite in SUITES:
            name = suite["name"]
            assert result["metrics"][f"benchmark:{name}.recall_gap"] == pytest.approx(0.2)
            assert result["metrics"][f"benchmark:{name}.qa_error"] == pytest.approx(0.25)
            assert f"{name} (fixture, QA): recall@5 80.0%, QA accuracy 75.0%" in (
                result["report_block"]
            )

        sidecar = json.loads((tmp_path / "tuner" / "benchmarks.json").read_text())
        for suite in SUITES:
            record = sidecar["suites"][suite["name"]]
            assert record["succeeded"] is True
            assert record["scores"]["recall_at_k"] == 0.8
            assert record["previous_scores"] is None

    def test_fresh_scores_are_reused_not_rerun(self, step, tmp_path, monkeypatch):
        build_harness(tmp_path / "harness")
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path / "harness"))
        asyncio.run(step.observe())
        again = asyncio.run(step.observe())

        assert again["suites_run"] == []
        assert again["skipped"] == "all suites fresh"
        # Carried forward: metrics never vanish between runs.
        for suite in SUITES:
            assert f"benchmark:{suite['name']}.qa_error" in again["metrics"]

    def test_stale_scores_rerun_and_keep_previous(self, step, tmp_path, monkeypatch):
        build_harness(tmp_path / "harness")
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path / "harness"))
        step.min_interval_hours = 0.0
        asyncio.run(step.observe())
        again = asyncio.run(step.observe())

        assert sorted(again["suites_run"]) == sorted(s["name"] for s in SUITES)
        assert "previous run: recall 80.0%, QA 75.0%" in again["report_block"]
        sidecar = json.loads((tmp_path / "tuner" / "benchmarks.json").read_text())
        for suite in SUITES:
            assert sidecar["suites"][suite["name"]]["previous_scores"]["qa_accuracy"] == 0.75

    def test_failed_run_carries_scores_forward(self, step, tmp_path, monkeypatch):
        harness = tmp_path / "harness"
        build_harness(harness)
        monkeypatch.setenv(BENCH_ROOT_ENV, str(harness))
        step.min_interval_hours = 0.0
        asyncio.run(step.observe())

        build_harness(harness, runner_source=FAILING_RUNNER)
        result = asyncio.run(step.observe())

        # The attempt failed, but the previous scores still feed the
        # watch windows -- absence would false-validate learnings.
        for suite in SUITES:
            assert result["metrics"][f"benchmark:{suite['name']}.qa_error"] == pytest.approx(0.25)
        assert "stale: latest attempt failed" in result["report_block"]
        assert "embedding model unavailable" in result["report_block"]
        sidecar = json.loads((tmp_path / "tuner" / "benchmarks.json").read_text())
        for suite in SUITES:
            record = sidecar["suites"][suite["name"]]
            assert record["succeeded"] is False
            assert record["scores"]["qa_accuracy"] == 0.75

    def test_complete_report_beats_a_crashed_exit_code(self, step, tmp_path, monkeypatch):
        build_harness(tmp_path / "harness", runner_source=CRASH_AFTER_REPORT_RUNNER)
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path / "harness"))
        result = asyncio.run(step.observe())

        for suite in SUITES:
            assert result["metrics"][f"benchmark:{suite['name']}.qa_error"] == pytest.approx(0.25)
        sidecar = json.loads((tmp_path / "tuner" / "benchmarks.json").read_text())
        for suite in SUITES:
            record = sidecar["suites"][suite["name"]]
            assert record["succeeded"] is True
            assert record["exit_code"] == 11
            assert record["error"] is None

    def test_failure_before_any_success_yields_no_metrics(self, step, tmp_path, monkeypatch):
        build_harness(tmp_path / "harness", runner_source=FAILING_RUNNER)
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path / "harness"))
        result = asyncio.run(step.observe())

        assert result["metrics"] == {}
        assert "no scores yet" in result["report_block"]

    def test_muxi_md_path_reaches_the_runner(self, step, tmp_path, monkeypatch):
        build_harness(tmp_path / "harness")
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path / "harness"))
        muxi_md = tmp_path / "MUXI.md"
        muxi_md.write_text("- Prefer terse answers.")
        asyncio.run(step.observe(str(muxi_md)))

        for suite in SUITES:
            report = json.loads((tmp_path / "tuner" / f"bench-{suite['name']}.json").read_text())
            assert report["config"]["muxi_md"] == str(muxi_md)

    def test_timeout_kills_the_suite(self, step, tmp_path, monkeypatch):
        build_harness(tmp_path / "harness", runner_source=SLEEPING_RUNNER)
        monkeypatch.setenv(BENCH_ROOT_ENV, str(tmp_path / "harness"))
        step.suite_timeout_seconds = 1.0
        result = asyncio.run(step.observe())

        assert result["metrics"] == {}
        sidecar = json.loads((tmp_path / "tuner" / "benchmarks.json").read_text())
        for suite in SUITES:
            assert "timed out" in sidecar["suites"][suite["name"]]["error"]

    def test_corrupt_sidecar_starts_fresh(self, step, tmp_path, monkeypatch):
        monkeypatch.delenv(BENCH_ROOT_ENV, raising=False)
        (tmp_path / "tuner").mkdir(parents=True)
        (tmp_path / "tuner" / "benchmarks.json").write_text("{not json")
        result = asyncio.run(step.observe())
        assert result["metrics"] == {}
