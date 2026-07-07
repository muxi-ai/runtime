"""Runner lifecycle tests (stubbed adapter; no formation boot).

Pins the guarantee that every exit path — including a failure inside
``adapter.start()`` — reaches ``adapter.stop()``, so temp run dirs and
partially-initialized formations never leak.
"""

import pytest

from bench.memory import runner as runner_module
from bench.memory.runner import build_arg_parser, run_benchmark


class _StubAdapter:
    """Records lifecycle calls; start() raises when configured to."""

    instances = []

    fail_on_start = False

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
        pass

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
    monkeypatch.setattr(runner_module, "MuxiMemoryAdapter", _StubAdapter)


def _args(*extra):
    parser = build_arg_parser("longmemeval", default_k=5)
    return parser.parse_args(["--fixture", *extra])


class TestRunnerLifecycle:
    async def test_start_failure_still_calls_stop(self):
        _StubAdapter.fail_on_start = True
        with pytest.raises(RuntimeError, match="boom"):
            await run_benchmark("longmemeval", _args())
        (adapter,) = _StubAdapter.instances
        assert adapter.start_called
        assert adapter.stop_called == 1

    async def test_successful_run_calls_stop_once(self, tmp_path):
        exit_code = await run_benchmark(
            "longmemeval", _args("--output", str(tmp_path / "report.json"))
        )
        (adapter,) = _StubAdapter.instances
        assert adapter.stop_called == 1
        assert exit_code == 0
        assert (tmp_path / "report.json").exists()

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
