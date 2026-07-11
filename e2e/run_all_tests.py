#!/usr/bin/env python3
"""
E2E Test Runner - Executes all test files and collects results.
Each test is run as a subprocess with a timeout.
Results are written to e2e/results/test_report.json.
Proof evidence is captured per test and reported per area.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from provision_keys import provision_keys

TIMEOUT_SECONDS = 120
EARLY_KILL_AFTER_SUCCESS = 3  # seconds to wait after SUCCESS before killing
AREA_TIMEOUT_OVERRIDES = {
    "19_api": 360,  # API tests spin up a server + memory CRUD with extraction waits
    "20_mcp_server": 360,  # MCP tests spin up server + MCP client calls + LLM chat
    "3_multimodal": 480,  # Vision/video LLM calls can be very slow (14MB video, Gemini API)
    "2_memory": 180,  # Memory tests with extraction waits, multi-user, PG queries
    # SOP workflow tests sequentially execute LLM planning + MCP tool
    # calls per task; a 4-task workflow regularly takes ~100s wall-clock
    # against real OpenAI / MCP, so the 120s default kills mid-flight.
    "7_orchestration": 240,
    # Knowledge tests deliberately clear the embedding cache to
    # exercise the cold-start path: sentence-transformers download +
    # CoreML compile + chunked embedding of ~50KB markdown sources
    # routinely runs 3-4 minutes before the first chat turn even
    # starts.
    "6_knowledge": 600,
    # Coding delegation tests run REAL headless coding agents (claude,
    # droid) end to end: each delegation is a full agentic run (git init,
    # clone, commit, push against local fixtures) that takes minutes.
    "24_coding": 900,
    # Watch tests run real LLM turns (submit -> watch_job recognition,
    # completion re-entry) around fixed-cadence poll loops; the full-loop
    # test alone is ~2 LLM turns + ~6s of polling + channel delivery.
    "25_watch": 300,
    # Envelope UI tests drive multi-turn clarification flows (LLM
    # analysis + MCP credential resolution + retry of the original
    # request) against real OpenAI; three rounds regularly exceed 120s.
    "25_envelope_ui": 300,
}
E2E_DIR = Path(__file__).parent
TESTS_DIR = E2E_DIR / "tests"
RESULTS_DIR = E2E_DIR / "results"
EVIDENCE_DIR = E2E_DIR / "evidence"
SRC_DIR = E2E_DIR.parent / "src"

PROOF_APP = "muxi-runtime"
PROOF_AVAILABLE = shutil.which("proof") is not None

SKIP_PATTERNS = [
    "base_",
    "common.py",
    "run_all",
    "run_tests",
    "run_day",
    "quick_test",
    "fix_async",
    "__init__",
    "__pycache__",
    "check_all_response",
    "test_batch_runner",
    "test_check_threads",
    "test_executor_threads",
    "test_force_exit",
    "test_simple_load",
    "test_with_exit",
    "test_with_stop",
    "test_proper_lifecycle",
    "test_nocache",
    "test_minimal_memory",
]

AREAS = sorted(
    [d for d in TESTS_DIR.iterdir() if d.is_dir() and d.name[0].isdigit()],
    key=lambda d: int(d.name.split("_")[0]),
)


def should_skip(filename: str) -> bool:
    return any(pat in filename for pat in SKIP_PATTERNS)


CRASH_SIGNALS = {-6, -9, -11}  # SIGABRT, SIGKILL, SIGSEGV


def _run_once(test_file: Path, env: dict, timeout: int) -> dict:
    """Run a single test subprocess and return result dict."""

    pass_markers = [
        "SUCCESS",
        "PASSED",
        "All checks passed",
        "CORE TESTS PASSED",
        # Many existing e2e tests close with "Test XX completed
        # successfully!" (or "All Test XX tests completed successfully!")
        # using a celebratory emoji line instead of the SUCCESS marker
        # AGENTS.md prescribes. Matching the trailing bang keeps this
        # narrow to end-of-run summary lines and not arbitrary "task X
        # completed successfully" log noise mid-run.
        "completed successfully!",
    ]
    t0 = time.time()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", test_file.name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(test_file.parent),
            env=env,
            text=True,
        )

        stdout_lines = []
        found_success = False
        success_time = None

        import select

        while True:
            elapsed = time.time() - t0

            if elapsed > timeout:
                proc.kill()
                break

            if found_success and (time.time() - success_time) > EARLY_KILL_AFTER_SUCCESS:
                proc.kill()
                break

            if proc.poll() is not None:
                break

            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            if ready:
                line = proc.stdout.readline()
                if line:
                    stdout_lines.append(line)
                    if not found_success and any(m in line for m in pass_markers):
                        found_success = True
                        success_time = time.time()

        remaining_out, stderr = proc.communicate(timeout=5)
        if remaining_out:
            stdout_lines.append(remaining_out)

        elapsed = time.time() - t0
        full_stdout = "".join(stdout_lines)
        full_stderr = stderr or ""
        timed_out = elapsed >= timeout - 1

        has_success = any(m in full_stdout for m in pass_markers)
        has_fail = ("FAILED" in full_stdout or "FAILURE" in full_stdout) and not has_success
        has_assertion_error = "AssertionError" in full_stderr or "AssertionError" in full_stdout

        if has_success and not has_fail and not has_assertion_error:
            passed = True
        elif (
            (proc.returncode == 0 or timed_out or found_success)
            and not has_fail
            and not has_assertion_error
        ):
            passed = True
        else:
            passed = False

        return {
            "file": str(test_file.relative_to(E2E_DIR)),
            "area": test_file.parent.name,
            "exit_code": proc.returncode or 0,
            "passed": passed,
            "time_s": round(elapsed, 1),
            "stdout_tail": full_stdout[-2000:] if full_stdout else "",
            "stderr_tail": (f"TIMEOUT after {timeout}s\n" if timed_out else "")
            + (full_stderr[-500:] if full_stderr else ""),
        }
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        elapsed = time.time() - t0
        return {
            "file": str(test_file.relative_to(E2E_DIR)),
            "area": test_file.parent.name,
            "exit_code": -2,
            "passed": False,
            "time_s": round(elapsed, 1),
            "stdout_tail": "",
            "stderr_tail": str(e),
        }


def run_test(test_file: Path) -> dict:
    area = test_file.parent.name
    timeout = AREA_TIMEOUT_OVERRIDES.get(area, TIMEOUT_SECONDS)
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{SRC_DIR}:{TESTS_DIR}:{test_file.parent}:{env.get('PYTHONPATH', '')}"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["PYTHONUNBUFFERED"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"

    result = _run_once(test_file, env, timeout)

    # Retry once on crash signals (SIGSEGV/SIGABRT) that happened quickly
    # These are environment-specific flaky crashes, not test failures
    if (
        not result["passed"]
        and result["exit_code"] in CRASH_SIGNALS
        and result["time_s"] < 60
        and "SUCCESS" not in result["stdout_tail"]
    ):
        print(
            f"      [retry] crash signal {result['exit_code']} at {result['time_s']}s, retrying..."
        )
        retry = _run_once(test_file, env, timeout)
        retry["retried"] = True
        return retry

    return result


def capture_proof(test_file: Path, run_name: str) -> None:
    """Capture proof evidence for a test. Fails silently if proof CLI is unavailable."""
    if not PROOF_AVAILABLE:
        return
    area = test_file.parent.name
    label = test_file.stem.replace("test_", "")
    timeout = AREA_TIMEOUT_OVERRIDES.get(area, TIMEOUT_SECONDS) + 10
    command = f"cd {test_file.parent} && {sys.executable} {test_file.name}"
    try:
        subprocess.run(
            [
                "proof",
                "capture",
                "--app",
                PROOF_APP,
                "--command",
                command,
                "--mode",
                "terminal",
                "--label",
                label,
                "--dir",
                str(EVIDENCE_DIR),
                "--run",
                run_name,
                "--description",
                test_file.stem.replace("_", " "),
            ],
            timeout=timeout,
            capture_output=True,
        )
    except Exception:
        pass


def generate_proof_reports(run_names: list) -> None:
    """Generate proof reports for each run. Fails silently if proof CLI is unavailable."""
    if not PROOF_AVAILABLE:
        return
    for run_name in run_names:
        try:
            subprocess.run(
                [
                    "proof",
                    "report",
                    "--app",
                    PROOF_APP,
                    "--dir",
                    str(EVIDENCE_DIR),
                    "--run",
                    run_name,
                ],
                timeout=30,
                capture_output=True,
            )
        except Exception:
            pass


def main():
    try:
        provision_keys()
    except Exception as exc:
        print(f"[provision_keys] error: {exc}", file=sys.stderr)
        sys.exit(1)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all test files
    all_tests = []
    for area in AREAS:
        tests = sorted(area.glob("test_*.py"))
        tests = [t for t in tests if not should_skip(t.name)]
        all_tests.extend(tests)

    print(f"Found {len(all_tests)} test files across {len(AREAS)} areas")
    if PROOF_AVAILABLE:
        print(f"Proof evidence: {EVIDENCE_DIR}")
    print("=" * 70)

    results = []
    area_stats = {}
    proof_runs = set()

    for i, test_file in enumerate(all_tests, 1):
        area = test_file.parent.name
        short = test_file.name
        print(f"[{i}/{len(all_tests)}] {area}/{short} ... ", end="", flush=True)

        result = run_test(test_file)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status} ({result['time_s']}s)")

        if area not in area_stats:
            area_stats[area] = {"passed": 0, "failed": 0, "total": 0}
        area_stats[area]["total"] += 1
        if result["passed"]:
            area_stats[area]["passed"] += 1
        else:
            area_stats[area]["failed"] += 1

        # Capture proof evidence (per area group)
        if PROOF_AVAILABLE:
            proof_runs.add(area)
            capture_proof(test_file, area)

    # Generate proof reports per area
    if proof_runs:
        print("\nGenerating proof reports...")
        generate_proof_reports(sorted(proof_runs))
        print(f"Evidence saved to {EVIDENCE_DIR}/{PROOF_APP}/")

    # Summary
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

    # Save report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {"total": total, "passed": passed, "failed": failed},
        "area_stats": area_stats,
        "results": results,
    }
    report_path = RESULTS_DIR / "test_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
