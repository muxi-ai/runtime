#!/usr/bin/env python3
"""
Test 27A8: benchmark observation (Self-Improving Formation, Phase 3).

The meta-agent's cold start against the real harness: a formation with
ZERO traffic (no users, empty spool) runs one tuning pass with
$MUXI_BENCH_ROOT pointing at this checkout -> both fixture suites run
as real subprocesses (real formation, real embeddings, real QA + judge)
with the live MUXI.md riding the QA prompt -> the scores land in the
tuner sidecar and give the tune step enough evidence to run without a
single event -> a second pass reuses the fresh scores instead of paying
for a rerun.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from tuning_common import (
    REPO_ROOT,
    build_formation,
    load_formation,
    run_tuning_pass,
    teardown,
    tuner_dir_for,
    unique_formation_id,
)

MUXI_MD = (
    "# Learnings\n\n"
    "- Answer strictly from the retrieved conversation excerpts; when they "
    "lack the answer, say you do not know.\n"
)

SUITE_NAMES = ("longmemeval", "structured_recall")


async def main():
    print("MUXI Runtime - Test 27A8: benchmark observation (meta-agent cold start)")
    print("=" * 60)

    formation = None
    formation_id = unique_formation_id("bench")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a8-"))
    try:
        os.environ["MUXI_BENCH_ROOT"] = str(REPO_ROOT)
        formation_dir = build_formation(tmp, formation_id, muxi_md=MUXI_MD)
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation_id} (no traffic -- cold start)")

        # 1. One pass on a formation nobody has ever talked to (the
        #    spool holds only the formation's own startup events): the
        #    benchmark suites are the evidence that makes tuning possible.
        print("Running tuning pass with real benchmark suites (takes minutes)...")
        result = await run_tuning_pass(overlord)
        print(f"Tuning pass: {result}")
        assert result["spool_committed"] is True
        assert sorted(result["benchmark_suites_run"]) == sorted(
            SUITE_NAMES
        ), f"both fixture suites should have run: {result}"
        assert (
            "learnings_recorded" in result or "tuner_skipped" in result
        ), f"the tune step did not run: {result}"
        print("Tuning pass completed with benchmark evidence (no user traffic)")

        # 2. Real scores in the sidecar, from complete (non-partial) runs.
        sidecar = json.loads((tuner_dir_for(formation_id) / "benchmarks.json").read_text())
        for name in SUITE_NAMES:
            record = sidecar["suites"][name]
            assert record["succeeded"] is True, f"suite {name} failed: {record}"
            scores = record["scores"]
            assert 0.0 <= scores["recall_at_k"] <= 1.0, f"bad recall for {name}: {scores}"
            assert 0.0 <= scores["qa_accuracy"] <= 1.0, f"bad accuracy for {name}: {scores}"
            print(
                f"  {name}: recall@{scores['k']:.0f}={scores['recall_at_k']:.3f}, "
                f"qa_accuracy={scores['qa_accuracy']:.3f}, "
                f"cost=${scores.get('estimated_usd', 0.0):.4f}, "
                f"duration={record['duration_seconds']:.0f}s"
            )

        # 3. The live MUXI.md steered the QA runs: the benchmark reports
        #    echo the exact file the runner was pointed at.
        live_path = overlord.muxi_md.resolve_path()
        assert live_path, "the formation's MUXI.md went missing"
        for name in SUITE_NAMES:
            report = json.loads((tuner_dir_for(formation_id) / f"bench-{name}.json").read_text())
            assert (
                report["config"]["muxi_md"] == live_path
            ), f"suite {name} did not receive the live MUXI.md: {report['config']}"
        print(f"Both suites ran with the live MUXI.md: {live_path}")

        # 4. Fresh scores are reused, not repurchased: a second pass
        #    skips every suite and the attempt timestamps do not move.
        attempted = {name: sidecar["suites"][name]["attempted_at"] for name in SUITE_NAMES}
        again = await run_tuning_pass(overlord)
        print(f"Second pass: {again}")
        assert again["benchmark_suites_run"] == [], f"fresh suites were rerun: {again}"
        assert again["benchmark_skipped"] == "all suites fresh"
        sidecar = json.loads((tuner_dir_for(formation_id) / "benchmarks.json").read_text())
        for name in SUITE_NAMES:
            assert sidecar["suites"][name]["attempted_at"] == attempted[name]
        print("Second pass reused the fresh scores (no rerun)")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: the benchmark observation works end-to-end")
        print("  - a zero-traffic formation ran both fixture suites in one tuning pass")
        print("  - real recall/QA scores landed in the tuner sidecar")
        print("  - the live MUXI.md rode every QA prompt")
        print("  - the tune step ran on benchmark evidence alone (cold start)")
        print("  - a second pass reused the fresh scores instead of rerunning")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\n(none -- the point of this test is a formation with zero traffic)")

        print("\nTest 27A8 PASSED")
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
