#!/usr/bin/env python3
"""
Phase 0 baseline harness for feature/local-classification.

Measures wall-time and classification-LLM-call counts for two workloads:

1. **heavy** — the canonical hello-muxi PDF prompt
   ("create a one-page PDF about MUXI"). Regression check; classifications
   are <2% of latency on this workload.
2. **light** — a 10-prompt micro-suite that does NOT trigger heavy
   planning; the pre-planning pipeline (RequestAnalyzer, AgentRouter,
   Clarification, Actionability) dominates wall time. This is where
   local classifiers should show the win.

Usage
-----
Assumes the runtime is running on ``http://127.0.0.1:8000`` against the
hello-muxi formation, with ``FORMATION_CLIENT_API_KEY`` set in the
environment (decrypt from ``hello-muxi/secrets.enc`` separately).

::

    # In one shell, with env vars set:
    python -m muxi.runtime.utils.run_formation \
        /Users/ran/Projects/muxi/code/example-formations/hello-muxi/formation.afs \
        --port 8000 > /tmp/runtime-baseline.log 2>&1 &

    # In another shell:
    python bench/run_baseline.py --runs 3 \
        --log-file /tmp/runtime-baseline.log \
        --output bench/local_classification_baseline.json

Output
------
A JSON file with per-prompt timings, per-run totals, and the count of
classification-shaped LLM calls per prompt parsed from the runtime log.
A human-readable summary is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

import urllib.error
import urllib.request

# Local import — we run this from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from light_workload_microsuite import LightPrompt, all_prompts  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_API_KEY_ENV = "FORMATION_CLIENT_API_KEY"

HEAVY_PROMPT = "create a one-page PDF about MUXI"

# Empirical calibration (probed against running hello-muxi runtime):
# the runtime emits ``model.request.started`` once per outbound LLM call,
# carrying a ``data.max_tokens`` field that disambiguates the call shape
# more reliably than guessing event names. Buckets:
#
#   classification : max_tokens <=    64  (yes/no, label, small JSON)
#   synthesis      : max_tokens <= 4000  (response text, summaries)
#   planning       : max_tokens  > 4000  (decomposition + tool plans)
#
# This is the cleanest available proxy for "which LLM calls would a
# local classifier replace?" without invasive instrumentation.
LLM_CALL_EVENT = "model.request.started"
CLASSIFICATION_TOKEN_THRESHOLD = 64
SYNTHESIS_TOKEN_THRESHOLD = 4000


def _bucket_for_max_tokens(max_tokens: Optional[int]) -> str:
    if max_tokens is None:
        return "unknown"
    if max_tokens <= CLASSIFICATION_TOKEN_THRESHOLD:
        return "classification"
    if max_tokens <= SYNTHESIS_TOKEN_THRESHOLD:
        return "synthesis"
    return "planning"


def _post_chat(
    base_url: str,
    api_key: Optional[str],
    message: str,
    session_id: str,
    timeout_s: float = 180.0,
) -> Tuple[float, int, str]:
    """
    POST to /v1/chat with stream=false (so we can time end-to-end cleanly)
    and return (wall_time_seconds, http_status, response_body_excerpt).
    """
    url = f"{base_url}/v1/chat"
    payload = json.dumps(
        {
            "message": message,
            "session_id": session_id,
            "stream": False,
        }
    ).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        # Runtime expects the client key in this custom header.
        headers["X-Muxi-Client-Key"] = api_key

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    t0 = time.perf_counter()
    body = ""
    status = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
    except urllib.error.URLError as e:
        status = -1
        body = f"URLError: {e}"
    except Exception as e:  # pylint: disable=broad-except
        status = -1
        body = f"Exception: {type(e).__name__}: {e}"
    t1 = time.perf_counter()

    excerpt = body[:200].replace("\n", " ")
    return t1 - t0, status, excerpt


def _read_log_jsonl(log_path: Path) -> List[Dict[str, Any]]:
    """Read jsonl-style runtime log and return parsed event records."""
    if not log_path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Logs may interleave with stdout banner lines; only parse JSON.
            if not line.startswith("{"):
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _classify_events_in_window(
    events: List[Dict[str, Any]],
    started_ms: int,
    ended_ms: int,
) -> Dict[str, Any]:
    """
    Count outbound LLM calls within a request's wall-time window, bucketed
    by ``max_tokens``. Returns:

        {
          "classification": int,
          "synthesis": int,
          "planning": int,
          "unknown": int,
          "calls": [{"max_tokens": int, "temperature": float, "rel_s": float}, ...],
        }
    """
    counts = {"classification": 0, "synthesis": 0, "planning": 0, "unknown": 0}
    calls: List[Dict[str, Any]] = []
    for ev in events:
        ts = ev.get("timestamp")
        evname = ev.get("event")
        if not isinstance(ts, (int, float)) or evname != LLM_CALL_EVENT:
            continue
        if ts < started_ms or ts > ended_ms:
            continue
        d = ev.get("data") or {}
        mt = d.get("max_tokens")
        bucket = _bucket_for_max_tokens(mt if isinstance(mt, int) else None)
        counts[bucket] += 1
        calls.append(
            {
                "max_tokens": mt,
                "temperature": d.get("temperature"),
                "model": d.get("model"),
                "rel_s": round((ts - started_ms) / 1000.0, 3),
            }
        )
    return {**counts, "calls": calls}


def _run_single(
    base_url: str,
    api_key: Optional[str],
    prompt_label: str,
    prompt_text: str,
    session_id: str,
    log_path: Optional[Path],
) -> Dict[str, Any]:
    """Run one prompt, capture timing, then post-hoc count classification events."""
    started_ms = int(time.time() * 1000)
    wall_s, status, excerpt = _post_chat(base_url, api_key, prompt_text, session_id)
    ended_ms = int(time.time() * 1000)

    events_in_window: Dict[str, Any] = {}
    if log_path:
        # Small sleep so the runtime has flushed its log before we read.
        time.sleep(0.75)
        events = _read_log_jsonl(log_path)
        # Pad the read window slightly on both ends to absorb log-flush
        # jitter while keeping requests well-separated (sessions are
        # serial in this harness).
        events_in_window = _classify_events_in_window(
            events, started_ms - 250, ended_ms + 1000
        )

    return {
        "label": prompt_label,
        "prompt": prompt_text,
        "wall_seconds": round(wall_s, 3),
        "http_status": status,
        "response_excerpt": excerpt,
        "session_id": session_id,
        "started_ms": started_ms,
        "ended_ms": ended_ms,
        "classification_events": events_in_window,
    }


def run_heavy(
    base_url: str,
    api_key: Optional[str],
    runs: int,
    log_path: Optional[Path],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for i in range(runs):
        # Each run gets a fresh session so buffer doesn't accumulate.
        session_id = f"bench_heavy_run{i + 1}"
        print(f"  [heavy/run{i + 1}] {HEAVY_PROMPT!r}")
        r = _run_single(base_url, api_key, "heavy_pdf", HEAVY_PROMPT, session_id, log_path)
        print(f"    → {r['wall_seconds']}s (status {r['http_status']})")
        results.append(r)
    return results


def run_light(
    base_url: str,
    api_key: Optional[str],
    runs: int,
    log_path: Optional[Path],
) -> List[Dict[str, Any]]:
    """Run the 10-prompt micro-suite ``runs`` times. Each run = fresh session."""
    results: List[Dict[str, Any]] = []
    prompts = all_prompts()
    for i in range(runs):
        session_id = f"bench_light_run{i + 1}"
        print(f"  [light/run{i + 1}] {len(prompts)} prompts in session {session_id}")
        for p in prompts:
            r = _run_single(base_url, api_key, p.label, p.text, session_id, log_path)
            print(f"    → {p.label:18s} {r['wall_seconds']:6.3f}s status={r['http_status']}")
            r["run"] = i + 1
            results.append(r)
    return results


def _summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"count": 0}
    walls = [r["wall_seconds"] for r in results if r["http_status"] in (200, 201)]
    if not walls:
        return {"count": len(results), "successful": 0}
    return {
        "count": len(results),
        "successful": len(walls),
        "min_s": round(min(walls), 3),
        "median_s": round(median(walls), 3),
        "max_s": round(max(walls), 3),
        "total_s": round(sum(walls), 3),
    }


def _summarize_classifications(results: List[Dict[str, Any]]) -> Dict[str, int]:
    totals: Dict[str, int] = {
        "classification": 0,
        "synthesis": 0,
        "planning": 0,
        "unknown": 0,
    }
    for r in results:
        ev = r.get("classification_events") or {}
        for k in totals:
            totals[k] += int(ev.get(k, 0))
    return totals


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 0 baseline harness for local-classification.")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENV,
        help="Env var holding the formation client API key.",
    )
    p.add_argument("--runs", type=int, default=3, help="Runs per workload (default 3).")
    p.add_argument("--log-file", default=None, help="Path to runtime log for event parsing.")
    p.add_argument(
        "--workloads",
        default="heavy,light",
        help="Comma-separated subset of {heavy,light}.",
    )
    p.add_argument(
        "--output",
        default="bench/local_classification_baseline.json",
        help="Where to write the JSON report.",
    )
    args = p.parse_args()

    api_key = os.environ.get(args.api_key_env, "") or None
    if not api_key:
        print(
            f"[warn] {args.api_key_env} not set in env; requests will be sent unauthenticated."
        )

    log_path: Optional[Path] = None
    if args.log_file:
        log_path = Path(args.log_file)
        if not log_path.exists():
            print(f"[warn] log file not found yet at {log_path}; will retry per-request")

    workloads = {w.strip() for w in args.workloads.split(",") if w.strip()}

    report: Dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": args.base_url,
        "runs": args.runs,
        "workloads_requested": sorted(workloads),
    }

    if "heavy" in workloads:
        print("== heavy workload ==")
        h = run_heavy(args.base_url, api_key, args.runs, log_path)
        report["heavy"] = {
            "results": h,
            "summary": _summarize(h),
            "classification_event_totals": _summarize_classifications(h),
        }

    if "light" in workloads:
        print("== light workload ==")
        light = run_light(args.base_url, api_key, args.runs, log_path)
        report["light"] = {
            "results": light,
            "summary": _summarize(light),
            "classification_event_totals": _summarize_classifications(light),
        }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print("== summary ==")
    if "heavy" in workloads:
        print(f"  heavy : {report['heavy']['summary']}")
    if "light" in workloads:
        print(f"  light : {report['light']['summary']}")
    print(f"\nWrote report to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
