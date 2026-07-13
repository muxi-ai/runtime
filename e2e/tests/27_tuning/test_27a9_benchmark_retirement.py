#!/usr/bin/env python3
"""
Test 27A9: benchmark carry-forward + deterministic retirement (Phase 3).

The regression-guard half of the meta-agent, provable without paying
for a real benchmark run: a planted sidecar score is carried forward
into the watch windows even when the harness is broken (a failing fake
harness records its error and never breaks the pass), and a planted
expired learning watching a benchmark metric that did not move is
deterministically retired. Metric absence must NEVER false-validate a
learning -- that is exactly what carry-forward exists to prevent.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from tuning_common import (
    build_formation,
    experiments_path_for,
    load_formation,
    run_tuning_pass,
    teardown,
    tuner_dir_for,
    unique_formation_id,
)

FAILING_RUNNER = "import sys\nprint('planted harness failure', file=sys.stderr)\nsys.exit(1)\n"


def build_failing_harness(root: Path) -> Path:
    """A fake bench checkout whose runners always fail (no LLM, no cost)."""
    memory = root / "bench" / "memory"
    memory.mkdir(parents=True)
    (root / "bench" / "__init__.py").write_text("")
    (memory / "__init__.py").write_text("")
    (memory / "runner.py").write_text("")  # the discovery marker
    for module in ("longmemeval_runner.py", "structured_recall_runner.py"):
        (memory / module).write_text(FAILING_RUNNER)
    return root


def plant_benchmark_scores(formation_id: str) -> None:
    """A fresh longmemeval score in the sidecar: qa_error = 0.25."""
    tuner_dir = tuner_dir_for(formation_id)
    tuner_dir.mkdir(parents=True, exist_ok=True)
    (tuner_dir / "benchmarks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "suites": {
                    "longmemeval": {
                        "attempted_at": time.time(),  # fresh: never rerun today
                        "succeeded": True,
                        "scores": {"k": 5.0, "recall_at_k": 0.8, "qa_accuracy": 0.75},
                        "previous_scores": None,
                        "error": None,
                        "duration_seconds": 60.0,
                    }
                },
            }
        )
    )


def plant_expired_benchmark_learning(formation_id: str) -> None:
    """An active learning whose expired window watched a flat benchmark metric."""
    path = experiments_path_for(formation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "experiments": [
                    {
                        "content_hash": "planted-benchmark-retirement",
                        "status": "active",
                        "learning": "Planted learning that never moved the benchmark.",
                        "evidence": "planted",
                        "metric_key": "benchmark:longmemeval.qa_error",
                        "baseline": 0.25,
                        "watch": {
                            "opened_at": time.time() - 8 * 24 * 3600,
                            "window_hours": 168,
                        },
                        "created_at": time.time(),
                        "updated_at": time.time(),
                    }
                ],
            }
        )
    )


async def main():
    print("MUXI Runtime - Test 27A9: benchmark carry-forward + retirement")
    print("=" * 60)

    formation = None
    formation_id = unique_formation_id("benchretire")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a9-"))
    try:
        # 1. Plant the state BEFORE the pass: a fresh longmemeval score
        #    (qa_error 0.25), an expired learning watching that exact
        #    metric, and a harness whose every runner fails.
        plant_benchmark_scores(formation_id)
        plant_expired_benchmark_learning(formation_id)
        os.environ["MUXI_BENCH_ROOT"] = str(build_failing_harness(tmp / "harness"))

        formation_dir = build_formation(tmp, formation_id)
        formation, formation_overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation_id}")

        # 2. One pass: the stale structured_recall suite is attempted
        #    against the broken harness (fails, recorded, fail-soft),
        #    the fresh longmemeval score is reused, and its carried
        #    metric feeds the watch windows -- retiring the planted
        #    no-movement learning.
        result = await run_tuning_pass(formation_overlord)
        print(f"Tuning pass: {result}")
        assert result["spool_committed"] is True
        assert result["benchmark_suites_run"] == [
            "structured_recall"
        ], f"only the stale suite should have been attempted: {result}"
        assert result["learnings_retired"] >= 1, f"no learning was retired: {result}"
        assert "tuner_error" not in result, f"the pass broke on the benchmark step: {result}"

        # 3. The broken harness was recorded, not fatal -- and the
        #    planted longmemeval score survived it untouched.
        sidecar = json.loads((tuner_dir_for(formation_id) / "benchmarks.json").read_text())
        structured = sidecar["suites"]["structured_recall"]
        assert structured["succeeded"] is False
        assert "planted harness failure" in structured["error"], f"error lost: {structured}"
        assert sidecar["suites"]["longmemeval"]["scores"]["qa_accuracy"] == 0.75
        print("Broken harness recorded per-suite; planted scores carried forward")

        # 4. The retirement is the carried metric's doing: final == the
        #    planted 0.25 (had the metric been absent, 0.0 would have
        #    false-validated the learning as 'moved').
        experiments = json.loads(experiments_path_for(formation_id).read_text())["experiments"]
        planted = next(
            record
            for record in experiments
            if record["content_hash"] == "planted-benchmark-retirement"
        )
        assert planted["status"] == "retired", f"planted learning was not retired: {planted}"
        assert planted["outcome"]["moved"] is False
        assert (
            planted["outcome"]["final"] == 0.25
        ), f"the carried benchmark metric did not feed the window: {planted['outcome']}"
        print("No-movement benchmark learning deterministically retired (final=0.25)")

        # 5. Fail-soft without any harness: unset the root and the next
        #    pass skips the observation cleanly.
        os.environ.pop("MUXI_BENCH_ROOT", None)
        again = await run_tuning_pass(formation_overlord)
        print(f"Pass without harness: {again}")
        assert again["spool_committed"] is True
        assert again["benchmark_suites_run"] == []
        assert "MUXI_BENCH_ROOT" in (again["benchmark_skipped"] or "")
        print("Missing harness skips the observation without breaking the pass")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: benchmark carry-forward and retirement work end-to-end")
        print("  - a failing harness was recorded per-suite and never broke the pass")
        print("  - fresh planted scores were reused, not rerun")
        print("  - the carried metric fed the watch windows (no false validation)")
        print("  - the planted no-movement learning was deterministically retired")
        print("  - an unset $MUXI_BENCH_ROOT skips the observation cleanly")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\n(none -- this test drives the tuning loop directly, without traffic)")

        print("\nTest 27A9 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        os.environ.pop("MUXI_BENCH_ROOT", None)
        if formation is not None:
            await teardown(formation, formation_id)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
