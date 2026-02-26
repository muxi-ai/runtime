#!/usr/bin/env python3
"""
Quick triage: run ONE representative test per area to identify broken areas.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT = 60
E2E_DIR = Path(__file__).parent
TESTS_DIR = E2E_DIR / "tests"
SRC_DIR = E2E_DIR.parent / "src"

SKIP = [
    "base_", "common.py", "run_all", "run_tests", "run_day", "quick_test",
    "fix_async", "__init__", "__pycache__", "check_all", "test_batch",
    "test_check_threads", "test_executor", "test_force_exit", "test_simple_load",
    "test_with_exit", "test_with_stop", "test_proper", "test_nocache", "test_minimal",
]

AREAS = sorted(
    [d for d in TESTS_DIR.iterdir() if d.is_dir() and d.name[0].isdigit()],
    key=lambda d: int(d.name.split("_")[0]),
)


def run_test(test_file):
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{SRC_DIR}:{TESTS_DIR}:{test_file.parent}:{env.get('PYTHONPATH', '')}"
    t0 = time.time()
    try:
        result = subprocess.run(
            ["timeout", str(TIMEOUT), sys.executable, test_file.name],
            capture_output=True, text=True, timeout=TIMEOUT + 10,
            cwd=str(test_file.parent), env=env,
        )
        elapsed = time.time() - t0
        timed_out = result.returncode in (-9, 124, 137)

        full_stdout = result.stdout or ""
        full_stderr = result.stderr or ""
        pass_markers = ["SUCCESS", "PASSED", "All checks passed", "CORE TESTS PASSED"]
        has_success = any(m in full_stdout for m in pass_markers)
        has_explicit_fail = (
            ("FAILED" in full_stdout or "FAILURE" in full_stdout)
            and not has_success
        )
        has_assertion_error = "AssertionError" in full_stderr or "AssertionError" in full_stdout

        if has_success and not has_explicit_fail and not has_assertion_error:
            passed = True
        elif result.returncode == 0 and not has_explicit_fail and not has_assertion_error:
            passed = True
        else:
            passed = False

        return {
            "file": str(test_file.relative_to(E2E_DIR)),
            "exit_code": result.returncode,
            "passed": passed,
            "time_s": round(elapsed, 1),
            "stdout_tail": full_stdout[-2000:] if full_stdout else "",
            "stderr_tail": (
                f"TIMEOUT(killed) after {TIMEOUT}s\n" if timed_out else ""
            ) + (result.stderr[-400:] if result.stderr else ""),
        }
    except subprocess.TimeoutExpired:
        return {
            "file": str(test_file.relative_to(E2E_DIR)),
            "exit_code": -1, "passed": False,
            "time_s": round(time.time() - t0, 1),
            "stdout_tail": "", "stderr_tail": f"TIMEOUT after {TIMEOUT}s",
        }
    except Exception as e:
        return {
            "file": str(test_file.relative_to(E2E_DIR)),
            "exit_code": -2, "passed": False,
            "time_s": round(time.time() - t0, 1),
            "stdout_tail": "", "stderr_tail": str(e),
        }


def main():
    results = []
    for area in AREAS:
        tests = sorted(area.glob("test_*.py"))
        tests = [t for t in tests if not any(s in t.name for s in SKIP)]
        if not tests:
            continue
        # Pick first test as representative
        test_file = tests[0]
        print(f"[{area.name}] {test_file.name} ... ", end="", flush=True)
        r = run_test(test_file)
        results.append({"area": area.name, **r})
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{status} ({r['time_s']}s)")
        if not r["passed"]:
            # Show last error line
            err = r["stderr_tail"].strip().split("\n")[-1][:120] if r["stderr_tail"] else ""
            out = r["stdout_tail"].strip().split("\n")[-1][:120] if r["stdout_tail"] else ""
            if err:
                print(f"  stderr: {err}")
            if out:
                print(f"  stdout: {out}")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*60}")
    print(f"Triage: {passed}/{len(results)} areas have at least 1 passing test")
    for r in results:
        s = "PASS" if r["passed"] else "FAIL"
        print(f"  [{s}] {r['area']}: {r['file']} ({r['time_s']}s)")

    # Save
    report_path = E2E_DIR / "results" / "triage_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {report_path}")


if __name__ == "__main__":
    main()
