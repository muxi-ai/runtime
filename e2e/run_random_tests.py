#!/usr/bin/env python3
"""
E2E Random Test Runner - Picks N random tests and runs them.
Usage: python run_random_tests.py [N]   (default: 10)
"""

import json
import random
import sys
import time

from provision_keys import provision_keys
from run_all_tests import (
    AREAS,
    EVIDENCE_DIR,
    PROOF_APP,
    PROOF_AVAILABLE,
    RESULTS_DIR,
    capture_proof,
    generate_proof_reports,
    run_test,
    should_skip,
)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run N random e2e tests")
    parser.add_argument("n", nargs="?", type=int, default=10, help="Number of tests to run")
    parser.add_argument(
        "--exclude-file",
        metavar="PATH",
        help="File with test paths (one per line) to exclude from the pool",
    )
    args = parser.parse_args()
    n = args.n

    provision_keys()

    excluded = set()
    if args.exclude_file:
        with open(args.exclude_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    excluded.add(line)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_tests = []
    for area in AREAS:
        tests = sorted(area.glob("test_*.py"))
        tests = [t for t in tests if not should_skip(t.name)]
        all_tests.extend(tests)

    if excluded:
        before = len(all_tests)
        all_tests = [t for t in all_tests if str(t.relative_to(t.parent.parent.parent)) not in excluded]
        print(f"Excluded {before - len(all_tests)} already-passing tests from pool")

    if n > len(all_tests):
        n = len(all_tests)

    selected = random.sample(all_tests, n)
    selected.sort(key=lambda t: (t.parent.name, t.name))

    print(f"Running {n} random tests (from {len(all_tests)} total)")
    if PROOF_AVAILABLE:
        print(f"Proof evidence: {EVIDENCE_DIR}")
    print("=" * 70)

    results = []
    area_stats = {}
    proof_runs = set()

    for i, test_file in enumerate(selected, 1):
        area = test_file.parent.name
        short = test_file.name
        print(f"[{i}/{n}] {area}/{short} ... ", end="", flush=True)

        result = run_test(test_file)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status} ({result['time_s']}s)")

        if not result["passed"]:
            tail = (
                result["stderr_tail"].strip().split("\n")[-1][:120] if result["stderr_tail"] else ""
            )
            if tail:
                print(f"      {tail}")

        if area not in area_stats:
            area_stats[area] = {"passed": 0, "failed": 0, "total": 0}
        area_stats[area]["total"] += 1
        if result["passed"]:
            area_stats[area]["passed"] += 1
        else:
            area_stats[area]["failed"] += 1

        # Capture proof evidence (grouped by area)
        if PROOF_AVAILABLE:
            proof_runs.add(area)
            capture_proof(test_file, area)

    # Generate proof reports per area
    if proof_runs:
        print("\nGenerating proof reports...")
        generate_proof_reports(sorted(proof_runs))
        print(f"Evidence saved to {EVIDENCE_DIR}/{PROOF_APP}/")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    print("\n" + "=" * 70)
    print(f"TOTAL: {passed}/{total} passed, {failed} failed\n")

    print("Per area:")
    for area in sorted(area_stats.keys(), key=lambda a: int(a.split("_")[0])):
        s = area_stats[area]
        status = "ALL PASS" if s["failed"] == 0 else f"{s['failed']} FAILED"
        print(f"  {area}: {s['passed']}/{s['total']} ({status})")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r["passed"]:
                err = r["stderr_tail"].strip().split("\n")[-1][:100] if r["stderr_tail"] else ""
                print(f"  {r['file']} (exit={r['exit_code']}, {r['time_s']}s) {err}")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "random",
        "sample_size": n,
        "pool_size": len(all_tests),
        "summary": {"total": total, "passed": passed, "failed": failed},
        "area_stats": area_stats,
        "results": results,
    }
    report_path = RESULTS_DIR / "random_test_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
