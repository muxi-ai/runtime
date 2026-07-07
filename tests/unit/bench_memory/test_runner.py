"""Runner lifecycle tests (stubbed adapter; no formation boot).

Pins two guarantees:
- every exit path — including a failure inside ``adapter.start()`` and
  per-case ingestion failures — reaches ``adapter.stop()``, so temp run
  dirs and partially-initialized formations never leak;
- a report is written on EVERY exit path: complete runs, runs with
  failed cases, early-stopped failure storms, and aborts all leave a
  report with whatever finished (marked ``partial`` when cut short).
"""

import json

import pytest

from bench.memory import runner as runner_module
from bench.memory.runner import (
    MAX_CONSECUTIVE_CASE_FAILURES,
    build_arg_parser,
    run_benchmark,
)


class _StubAdapter:
    """Records lifecycle calls; failure points are class-configurable."""

    instances = []

    fail_on_start = False
    fail_ingest_case_ids = frozenset()
    fail_all_ingest = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.start_called = False
        self.stop_called = 0
        type(self).instances.append(self)

    async def start(self):
        self.start_called = True
        if self.fail_on_start:
            raise RuntimeError("boom: formation load failed")

    async def stop(self):
        self.stop_called += 1

    def clear_case(self):
        pass

    async def ingest_session(self, user_id, session):
        case_id = user_id.split("-", 2)[-1]
        if self.fail_all_ingest or case_id in self.fail_ingest_case_ids:
            raise OSError("embedding model unavailable")

    async def search(self, user_id, query, fetch_limit):
        return []

    @staticmethod
    def ranked_session_ids(items):
        return []

    @staticmethod
    def ranked_turn_ids(items):
        return []

    def usage_snapshot(self):
        return {"llm_requests": 0, "tokens": {}, "tokens_by_model": {}, "cost": {}}

    def config_snapshot(self):
        return {"mode": self.kwargs.get("mode", "?")}


@pytest.fixture(autouse=True)
def _stub_adapter(monkeypatch):
    _StubAdapter.instances = []
    _StubAdapter.fail_on_start = False
    _StubAdapter.fail_ingest_case_ids = frozenset()
    _StubAdapter.fail_all_ingest = False
    monkeypatch.setattr(runner_module, "MuxiMemoryAdapter", _StubAdapter)


def _args(*extra):
    parser = build_arg_parser("longmemeval", default_k=5)
    return parser.parse_args(["--fixture", *extra])


def _read_report(path):
    return json.loads(path.read_text())


class TestRunnerLifecycle:
    async def test_start_failure_calls_stop_and_writes_partial_report(self, tmp_path):
        _StubAdapter.fail_on_start = True
        output = tmp_path / "report.json"
        with pytest.raises(RuntimeError, match="boom"):
            await run_benchmark("longmemeval", _args("--output", str(output)))
        (adapter,) = _StubAdapter.instances
        assert adapter.start_called
        assert adapter.stop_called == 1
        # The report still exists, marked partial with the abort reason.
        report = _read_report(output)
        assert report["partial"] is True
        assert "boom: formation load failed" in report["run"]["abort_reason"]
        assert report["run"]["cases"] == {"completed": 0, "failed": 0, "skipped": 6}
        assert report["results"] == []

    async def test_successful_run_calls_stop_once(self, tmp_path):
        exit_code = await run_benchmark(
            "longmemeval", _args("--output", str(tmp_path / "report.json"))
        )
        (adapter,) = _StubAdapter.instances
        assert adapter.stop_called == 1
        assert exit_code == 0
        assert (tmp_path / "report.json").exists()

    async def test_happy_path_report_has_no_partial_flag(self, tmp_path):
        output = tmp_path / "report.json"
        await run_benchmark("longmemeval", _args("--output", str(output)))
        report = _read_report(output)
        assert "partial" not in report
        assert "abort_reason" not in report["run"]
        assert report["run"]["cases"] == {"completed": 6, "failed": 0, "skipped": 0}

    async def test_keep_run_dir_flag_forwarded(self, tmp_path):
        await run_benchmark(
            "longmemeval",
            _args("--keep-run-dir", "--output", str(tmp_path / "report.json")),
        )
        (adapter,) = _StubAdapter.instances
        assert adapter.kwargs["keep_run_dir"] is True

    async def test_keep_run_dir_defaults_false(self, tmp_path):
        await run_benchmark("longmemeval", _args("--output", str(tmp_path / "report.json")))
        (adapter,) = _StubAdapter.instances
        assert adapter.kwargs["keep_run_dir"] is False


class TestIngestionFailureIsolation:
    async def test_single_case_failure_run_continues(self, tmp_path):
        _StubAdapter.fail_ingest_case_ids = frozenset({"fixture_ms_001"})
        output = tmp_path / "report.json"
        exit_code = await run_benchmark("longmemeval", _args("--output", str(output)))
        assert exit_code == 1  # errored questions surface in the exit code
        report = _read_report(output)
        # Run completed: not partial, all six cases attempted.
        assert "partial" not in report
        assert report["run"]["cases"] == {"completed": 5, "failed": 1, "skipped": 0}
        # The failed case's question carries the ingestion error; the
        # other five questions completed normally.
        by_id = {result["question_id"]: result for result in report["results"]}
        assert len(by_id) == 6
        assert "case ingestion failed: OSError" in by_id["fixture_ms_001"]["error"]
        clean = [r for r in report["results"] if r["error"] is None]
        assert len(clean) == 5
        assert report["metrics"]["questions_errored"] == 1
        # Cleanup still happened exactly once.
        (adapter,) = _StubAdapter.instances
        assert adapter.stop_called == 1

    async def test_consecutive_failure_counter_resets_after_success(self, tmp_path):
        # Two isolated failures with successes between them must NOT
        # trip the early stop (the threshold is CONSECUTIVE failures).
        _StubAdapter.fail_ingest_case_ids = frozenset({"fixture_ssu_001", "fixture_ms_001"})
        output = tmp_path / "report.json"
        await run_benchmark("longmemeval", _args("--output", str(output)))
        report = _read_report(output)
        assert "partial" not in report
        assert report["run"]["cases"] == {"completed": 4, "failed": 2, "skipped": 0}

    async def test_failure_storm_stops_early_with_partial_report(self, tmp_path):
        _StubAdapter.fail_all_ingest = True
        output = tmp_path / "report.json"
        exit_code = await run_benchmark("longmemeval", _args("--output", str(output)))
        assert exit_code == 1
        report = _read_report(output)
        assert report["partial"] is True
        assert "consecutive case ingestion failures" in report["run"]["abort_reason"]
        assert "embedding model unavailable" in report["run"]["abort_reason"]
        cases = report["run"]["cases"]
        assert cases["completed"] == 0
        assert cases["failed"] == MAX_CONSECUTIVE_CASE_FAILURES
        assert cases["skipped"] == 6 - MAX_CONSECUTIVE_CASE_FAILURES
        # Only the attempted cases' questions are recorded, all errored.
        assert len(report["results"]) == MAX_CONSECUTIVE_CASE_FAILURES
        assert all(result["error"] for result in report["results"])
        # Cleanup still ran.
        (adapter,) = _StubAdapter.instances
        assert adapter.stop_called == 1


class TestReportWriteFailureExitCode:
    """A run whose report cannot be written must not exit 0 (review P1)."""

    async def test_report_write_failure_returns_nonzero(self, monkeypatch, tmp_path):
        import bench.memory.runner as runner_mod

        def exploding_write(report, output):
            raise OSError("disk full")

        monkeypatch.setattr(runner_mod, "write_report", exploding_write)
        exit_code = await run_benchmark(
            "longmemeval", _args("--output", str(tmp_path / "report.json"))
        )
        assert exit_code != 0
