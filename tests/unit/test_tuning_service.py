"""Unit tests for the tuning loop (Self-Improving Formation, Phase 1).

Pins one loop pass end-to-end against a real spool and a real
CaptainsLogService (LLM mocked): spool aggregation into the bounded
activity report, digest into the formation log, checkpoint semantics
(delete vs keep, retry on transient failure), lifecycle start/stop, and
the MuxiMdFile read/write/cache contract.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.log.service import CaptainsLogService
from muxi.runtime.services.observability import spool as spool_module
from muxi.runtime.services.observability.spool import reset_event_spool
from muxi.runtime.services.tuning import MuxiMdFile, TuningConfig, TuningService
from muxi.runtime.services.tuning.benchmark import BENCH_ROOT_ENV, BenchmarkStep
from muxi.runtime.services.tuning.experiments import ExperimentStore
from muxi.runtime.services.tuning.service import (
    MAX_REPORT_CHARS,
    _aggregate_segments,
    _SpoolStats,
)

FORMATION_ID = "tuning-test-formation"

DIGEST_RESPONSE = (
    '{"summary": "The formation handled a small spike; one tool warned twice.", '
    '"context": "Mostly FAQ traffic."}'
)


class FakeModel:
    def __init__(self, response=DIGEST_RESPONSE):
        self.response = response
        self.calls = 0

    async def generate_text(self, prompt, caching=True):
        self.calls += 1
        return self.response


class FakeOverlord:
    def __init__(self, captains_log):
        self.captains_log = captains_log


def spool_event(
    name="agent.processing",
    level="info",
    timestamp=1783862400000,
    user_id=None,
    session_id=None,
    request=None,
    data=None,
):
    event = {"event": name, "level": level, "timestamp": timestamp}
    if session_id:
        event["session_id"] = session_id
    if request:
        event["request"] = request
    payload = dict(data or {})
    if user_id:
        payload["user_id"] = user_id
    if payload:
        event["data"] = payload
    return event


@pytest.fixture(autouse=True)
def no_bench_harness(tmp_path, monkeypatch):
    """Keep every pass's benchmark observation inert and hermetic."""
    monkeypatch.delenv(BENCH_ROOT_ENV, raising=False)
    yield


@pytest.fixture
def isolated_spool(tmp_path, monkeypatch):
    monkeypatch.setattr(spool_module, "_spool_dir", lambda: str(tmp_path / "spool"))
    reset_event_spool()
    yield spool_module.get_event_spool()
    reset_event_spool()


@pytest.fixture
def captains_log(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/log.db")
    manager.create_tables(Base.metadata)
    yield CaptainsLogService(manager, FORMATION_ID)
    manager.engine.dispose()


@pytest.fixture
def tuning(captains_log, tmp_path):
    service = TuningService(TuningConfig(), FakeOverlord(captains_log))
    service.benchmark = BenchmarkStep(base_dir=str(tmp_path / "tuner"))
    return service


class TestAggregation:
    def test_empty_segments_render_empty_report(self, isolated_spool):
        report, user_ids, count, metrics = _aggregate_segments(isolated_spool, [])
        assert report == ""
        assert user_ids == []
        assert count == 0
        assert metrics == {}

    def test_report_captures_operational_shape(self, isolated_spool):
        events = [
            spool_event(name="request.received", user_id="alice", session_id="s1"),
            spool_event(
                name="mcp.tool.failed",
                level="warning",
                data={"description": "jira MCP timed out"},
            ),
            spool_event(
                name="request.completed",
                request={
                    "id": "req-1",
                    "user_id": "bob",
                    "tokens": {
                        "total": [120, 0.001],
                        "breakdown": {"openai/gpt-4o-mini": [120, 0.001]},
                    },
                },
            ),
        ]
        isolated_spool.write_lines([json.dumps(event) for event in events])
        segments, _ = isolated_spool.read_for_digest()
        report, user_ids, count, metrics = _aggregate_segments(isolated_spool, segments)

        assert count == 3
        assert metrics["problem:mcp.tool.failed"] == pytest.approx(1 / 3)
        assert metrics["warning_rate"] == pytest.approx(1 / 3)
        assert metrics["error_rate"] == 0.0
        assert user_ids == ["alice", "bob"]
        assert "Window: 3 events" in report
        assert "2 distinct user(s), 1 session(s), 1 tracked request(s)" in report
        assert "- mcp.tool.failed: 1" in report
        assert "e.g. jira MCP timed out" in report
        assert "Total tokens across tracked requests: 120." in report
        assert "- openai/gpt-4o-mini: 120" in report
        # Raw identifiers stay out of the LLM-facing report.
        assert "alice" not in report
        assert "bob" not in report

    def test_report_is_bounded(self):
        stats = _SpoolStats()
        for index in range(500):
            stats.add(
                spool_event(
                    name=f"event.type.{index}",
                    level="warning",
                    data={"description": "d" * 200},
                )
            )
        assert len(stats.render()) <= MAX_REPORT_CHARS

    def test_last_token_snapshot_wins_per_request(self):
        stats = _SpoolStats()
        for total in (50, 120):
            stats.add(
                spool_event(
                    request={"id": "req-1", "user_id": "u", "tokens": {"total": [total, 0.0]}}
                )
            )
        total, _ = stats._token_totals()
        assert total == 120


class TestRunOnce:
    def test_digest_pass_writes_entry_and_deletes_segments(
        self, isolated_spool, captains_log, tuning
    ):
        isolated_spool.write_lines([json.dumps(spool_event(user_id="alice"))])
        result = asyncio.run(tuning.run_once(FakeModel()))

        assert result["events_read"] == 1
        assert result["segments_read"] == 1
        assert result["entries_written"] == 1
        assert result["spool_committed"] is True
        assert result["spool_segments_kept"] is False
        assert isolated_spool._list_segments() == []
        assert "small spike" in asyncio.run(captains_log.get_formation_context_block())
        assert tuning.last_run == result

    def test_keep_spool_segments_preserves_files(self, isolated_spool, captains_log, tmp_path):
        tuning = TuningService(TuningConfig(), FakeOverlord(captains_log), keep_spool_segments=True)
        tuning.benchmark = BenchmarkStep(base_dir=str(tmp_path / "tuner"))
        isolated_spool.write_lines([json.dumps(spool_event())])
        result = asyncio.run(tuning.run_once(FakeModel()))

        assert result["spool_committed"] is True
        assert result["spool_segments_kept"] is True
        assert len(isolated_spool._list_segments()) == 1
        # But the checkpoint advanced: nothing is digested twice.
        again = asyncio.run(tuning.run_once(FakeModel()))
        assert again["events_read"] == 0

    def test_transient_failure_keeps_segments_for_retry(self, isolated_spool, captains_log, tuning):
        isolated_spool.write_lines([json.dumps(spool_event())])
        failed = asyncio.run(tuning.run_once(None))  # no model yet
        assert failed["spool_committed"] is False
        assert failed["entries_written"] == 0
        assert len(isolated_spool._list_segments()) == 1

        retried = asyncio.run(tuning.run_once(FakeModel()))
        assert retried["events_read"] == 1
        assert retried["spool_committed"] is True

    def test_empty_spool_pass_is_clean(self, isolated_spool, tuning):
        model = FakeModel()
        result = asyncio.run(tuning.run_once(model))
        assert result["events_read"] == 0
        assert result["entries_written"] == 0
        assert result["spool_committed"] is True
        assert model.calls == 0

    def test_missing_captains_log_still_consumes(self, isolated_spool, tmp_path):
        tuning = TuningService(TuningConfig(), FakeOverlord(captains_log=None))
        tuning.benchmark = BenchmarkStep(base_dir=str(tmp_path / "tuner"))
        isolated_spool.write_lines([json.dumps(spool_event())])
        result = asyncio.run(tuning.run_once(FakeModel()))
        assert result["spool_committed"] is True
        assert result["entries_written"] == 0
        assert isolated_spool._list_segments() == []


class TestLifecycle:
    def test_inactive_config_never_starts(self, captains_log):
        async def scenario():
            tuning = TuningService(TuningConfig(active=False), FakeOverlord(captains_log))
            tuning.start(lambda: FakeModel())
            assert tuning._task is None
            await tuning.stop()

        asyncio.run(scenario())

    def test_start_and_stop(self, captains_log):
        async def scenario():
            tuning = TuningService(TuningConfig(), FakeOverlord(captains_log))
            tuning.start(lambda: FakeModel())
            assert tuning._task is not None and not tuning._task.done()
            await tuning.stop()
            assert tuning._task is None

        asyncio.run(scenario())


class TestMuxiMdFile:
    def test_absent_file_reads_none(self, tmp_path):
        assert MuxiMdFile(str(tmp_path)).read() is None
        assert MuxiMdFile(None).read() is None

    def test_read_write_roundtrip(self, tmp_path):
        muxi_md = MuxiMdFile(str(tmp_path))
        path = muxi_md.write("# Learnings\n\n- Prefer reportlab over fpdf.")
        assert path.endswith("MUXI.md")
        assert muxi_md.read() == "# Learnings\n\n- Prefer reportlab over fpdf."

    def test_lowercase_variant_resolved_and_reused_on_write(self, tmp_path):
        (tmp_path / "muxi.md").write_text("hand-written")
        muxi_md = MuxiMdFile(str(tmp_path))
        assert muxi_md.read() == "hand-written"
        muxi_md.write("curated")
        assert (tmp_path / "muxi.md").read_text() == "curated"
        # One file either way (case-insensitive filesystems collapse them).
        assert len(list(tmp_path.iterdir())) == 1

    def test_hand_edit_invalidates_cache(self, tmp_path):
        import os

        muxi_md = MuxiMdFile(str(tmp_path))
        muxi_md.write("v1")
        assert muxi_md.read() == "v1"
        target = tmp_path / "MUXI.md"
        target.write_text("v2")
        os.utime(target, (0, 0))  # force an mtime change either direction
        assert muxi_md.read() == "v2"

    def test_deleted_file_reads_none_again(self, tmp_path):
        muxi_md = MuxiMdFile(str(tmp_path))
        muxi_md.write("v1")
        (tmp_path / "MUXI.md").unlink()
        assert muxi_md.read() is None

    def test_write_without_directory_raises(self):
        with pytest.raises(ValueError, match="no directory"):
            MuxiMdFile(None).write("content")

    def test_empty_file_reads_none(self, tmp_path):
        (tmp_path / "MUXI.md").write_text("   \n")
        assert MuxiMdFile(str(tmp_path)).read() is None


TUNER_RESPONSE = json.dumps(
    {
        "muxi_md": "- Ground every QA answer in the retrieved excerpts.",
        "learnings": [
            {
                "learning": "Ground every QA answer in the retrieved excerpts.",
                "evidence": "benchmark qa_error at 0.25",
                "metric_key": "benchmark:longmemeval.qa_error",
            }
        ],
        "recommendations": [],
    }
)


class TunerModel:
    """FakeModel variant matching the tune step's generate_text signature."""

    def __init__(self, response=TUNER_RESPONSE):
        self.response = response
        self.prompts = []

    async def generate_text(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.response


class StubBenchmark:
    """Canned benchmark observation (or a raising one)."""

    def __init__(self, metrics=None, block="", error=None):
        self.metrics = metrics or {}
        self.block = block
        self.error = error
        self.observed_with = "never-called"

    async def observe(self, muxi_md_path=None):
        self.observed_with = muxi_md_path
        if self.error is not None:
            raise self.error
        return {
            "metrics": self.metrics,
            "report_block": self.block,
            "suites_run": sorted({key.split(":")[1].split(".")[0] for key in self.metrics}),
            "skipped": None,
        }


class TestBenchmarkWiring:
    """The meta-agent seam: benchmark scores feeding the tune step."""

    @pytest.fixture
    def cold_start_tuning(self, captains_log, tmp_path):
        overlord = FakeOverlord(captains_log)
        (tmp_path / "formation").mkdir()
        overlord.muxi_md = MuxiMdFile(str(tmp_path / "formation"))
        service = TuningService(TuningConfig(), overlord)
        service.experiments_dir = str(tmp_path / "experiments")
        return service

    def test_benchmark_evidence_tunes_without_traffic(self, isolated_spool, cold_start_tuning):
        """Cold start: no users, no events -- benchmarks still drive a tune."""
        tuning = cold_start_tuning
        tuning.benchmark = StubBenchmark(
            metrics={"benchmark:longmemeval.qa_error": 0.25},
            block="- longmemeval (fixture, QA): recall@5 80.0%, QA accuracy 75.0%",
        )
        model = TunerModel()
        result = asyncio.run(tuning.run_once(model))

        assert result["events_read"] == 0
        assert result["benchmark_suites_run"] == ["longmemeval"]
        assert result["learnings_recorded"] == 1
        assert result["muxi_md_applied"] is True
        assert "retrieved excerpts" in tuning.overlord.muxi_md.read()
        assert "Latest benchmark results" in model.prompts[0]
        assert "QA accuracy 75.0%" in model.prompts[0]
        assert "benchmark:longmemeval.qa_error" in model.prompts[0]
        # The watched benchmark metric froze its baseline at proposal time.
        record = ExperimentStore(tuning.experiments_dir).records[0]
        assert record["metric_key"] == "benchmark:longmemeval.qa_error"
        assert record["baseline"] == pytest.approx(0.25)

    def test_live_muxi_md_path_reaches_the_observation(self, isolated_spool, cold_start_tuning):
        tuning = cold_start_tuning
        tuning.overlord.muxi_md.write("- Existing learning.")
        stub = StubBenchmark()
        tuning.benchmark = stub
        asyncio.run(tuning.run_once(TunerModel()))
        assert stub.observed_with == tuning.overlord.muxi_md.resolve_path()

    def test_benchmark_failure_never_breaks_the_pass(self, isolated_spool, cold_start_tuning):
        tuning = cold_start_tuning
        tuning.benchmark = StubBenchmark(error=RuntimeError("harness exploded"))
        isolated_spool.write_lines([json.dumps(spool_event(user_id="alice"))])
        model = TunerModel(DIGEST_RESPONSE)
        result = asyncio.run(tuning.run_once(model))

        assert result["spool_committed"] is True
        assert "harness exploded" in result["benchmark_skipped"]
        assert result["benchmark_suites_run"] == []

    def test_no_evidence_at_all_skips_the_tuner(self, isolated_spool, cold_start_tuning):
        tuning = cold_start_tuning
        tuning.benchmark = StubBenchmark()  # harness skipped, no scores yet
        model = TunerModel()
        result = asyncio.run(tuning.run_once(model))

        assert result["events_read"] == 0
        assert model.prompts == []
        assert "learnings_recorded" not in result
