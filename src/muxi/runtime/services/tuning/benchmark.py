# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Benchmark Observation - The Meta-Agent's Measuring Stick
# Description:  Runs the shipped memory benchmarks as a tuning observation
# Role:         Deterministic metric source for the tuning loop (Phase 3)
# Usage:        Driven by TuningService.run_once between digest and tune
# Author:       Muxi Framework Team
#
# Self-Improving Formation PRD, Phase 3 (meta-agent). The same tuning
# loop, with the shipped benchmark tiers as an additional observation
# source: fixture-scale suites (LongMemEval sample + structured recall)
# run with QA against a real formation, steered by the live MUXI.md.
# Their scores become lower-is-better metrics next to the spool rates,
# so learnings can watch "benchmark:longmemeval.qa_error" exactly like
# "error_rate" -- cold-start formations get evidence before their first
# user, and MUXI.md regressions show up against a consistent baseline.
#
# The harness lives in the repo's ``bench/`` tree, not the installed
# package, and every runner owns its own asyncio loop and OneLLM
# singleton -- so suites run as subprocesses of a harness checkout,
# opted in via $MUXI_BENCH_ROOT (benchmark runs cost tokens; nothing
# should spend them by surprise). Everything here fails soft: no
# harness, a failed run, or a timeout degrades to the previous scores
# (carried forward so watch windows keep evaluating) and never breaks
# the tuning pass.
# =============================================================================

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...utils.user_dirs import get_observability_dir
from .. import observability

BENCHMARKS_FILE = "benchmarks.json"

# Explicit pointer to the directory containing the ``bench`` package
# (the repo checkout root, or wherever a deployment ships the harness).
# The observation is opt-in via this variable: auto-discovering a repo
# checkout would make every dev formation and e2e run silently spend
# tokens on benchmark subprocesses.
BENCH_ROOT_ENV = "MUXI_BENCH_ROOT"

# The fixture-scale suites the loop observes: committed samples, QA on,
# default combined retrieval -- cheap (cents), bounded (minutes), and
# deterministic in shape.
SUITES = (
    {"name": "longmemeval", "module": "bench.memory.longmemeval_runner"},
    {"name": "structured_recall", "module": "bench.memory.structured_recall_runner"},
)

# One attempt (successful or not) per suite per interval: a broken
# environment must not burn minutes on every pass, and scores fresher
# than a day carry no new signal for a daily loop.
DEFAULT_MIN_INTERVAL_HOURS = 24.0
DEFAULT_SUITE_TIMEOUT_SECONDS = 600.0

# Tail of subprocess output kept for diagnostics in the sidecar/event.
MAX_ERROR_CHARS = 500


def _default_base_dir() -> str:
    """Sidecar home: the tuner directory (sibling of experiments.json)."""
    return str(Path(get_observability_dir()) / "tuner")


def discover_bench_root() -> Optional[Path]:
    """The directory containing the ``bench`` harness package, or None.

    Resolved from ``$MUXI_BENCH_ROOT`` only -- unset, empty, or a
    directory without the harness means the observation skips.
    """
    env = os.environ.get(BENCH_ROOT_ENV)
    if not env:
        return None
    root = Path(env)
    return root if root.joinpath("bench", "memory", "runner.py").is_file() else None


def parse_report(payload: Any) -> Optional[Dict[str, float]]:
    """Extract the loop's scores from one benchmark report; None = unusable.

    A partial report is unusable (its rates cover an arbitrary subset of
    questions), and so is one with errored questions: an environment
    blip deflating a score must never masquerade as a capability
    regression.
    """
    if not isinstance(payload, dict) or payload.get("partial"):
        return None
    k = payload.get("k")
    metrics = payload.get("metrics")
    if not isinstance(k, int) or not isinstance(metrics, dict):
        return None
    if metrics.get("questions_errored"):
        return None
    try:
        recall = metrics["retrieval"]["session_level"]["overall"][f"recall@{k}"]
        accuracy = metrics["qa"]["overall"]["accuracy"]
    except (KeyError, TypeError):
        return None
    if not isinstance(recall, (int, float)) or not isinstance(accuracy, (int, float)):
        return None
    scores = {"k": float(k), "recall_at_k": float(recall), "qa_accuracy": float(accuracy)}
    usage = payload.get("usage")
    if isinstance(usage, dict):
        cost = (usage.get("cost") or {}).get("estimated_usd")
        if isinstance(cost, (int, float)):
            scores["estimated_usd"] = float(cost)
    return scores


class BenchmarkStep:
    """Runs the shipped benchmark suites and turns scores into metrics."""

    def __init__(self, base_dir: Optional[str] = None):
        """
        Args:
            base_dir: Overrides the sidecar location (tests only; None
                means the formation's observability tuner directory).
        """
        self._base_dir_override = base_dir
        self.min_interval_hours = DEFAULT_MIN_INTERVAL_HOURS
        self.suite_timeout_seconds = DEFAULT_SUITE_TIMEOUT_SECONDS

    def _base_dir(self) -> Path:
        return Path(self._base_dir_override or _default_base_dir())

    def _sidecar_path(self) -> Path:
        return self._base_dir() / BENCHMARKS_FILE

    # ------------------------------------------------------------------
    # Sidecar persistence (experiment-store idiom: tmp write + replace)
    # ------------------------------------------------------------------

    def _load_sidecar(self) -> Dict[str, Any]:
        try:
            payload = json.loads(self._sidecar_path().read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "suites": {}}
        suites = payload.get("suites") if isinstance(payload, dict) else None
        return {"version": 1, "suites": suites if isinstance(suites, dict) else {}}

    def _save_sidecar(self, sidecar: Dict[str, Any]) -> None:
        path = self._sidecar_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(sidecar, indent=1), encoding="utf-8")
            os.replace(tmp_path, path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # The observation: run due suites, carry scores forward, report
    # ------------------------------------------------------------------

    async def observe(self, muxi_md_path: Optional[str] = None) -> Dict[str, Any]:
        """Run due suites and return the benchmark observation. Never raises.

        Returns ``{"metrics": {...}, "report_block": str, "suites_run":
        [...], "skipped": reason-or-None}``. Metrics carry the latest
        successful scores of every suite (this pass's or an earlier
        one's), inverted to lower-is-better so watch windows evaluate
        them like spool rates.
        """
        sidecar = self._load_sidecar()
        bench_root = discover_bench_root()
        suites_run: List[str] = []
        skipped: Optional[str] = None

        if bench_root is None:
            skipped = f"bench harness not configured (${BENCH_ROOT_ENV})"
        else:
            now = time.time()
            for suite in SUITES:
                record = sidecar["suites"].get(suite["name"]) or {}
                attempted_at = record.get("attempted_at")
                if (
                    isinstance(attempted_at, (int, float))
                    and now - attempted_at < self.min_interval_hours * 3600.0
                ):
                    continue
                sidecar["suites"][suite["name"]] = await self._run_suite(
                    suite, bench_root, muxi_md_path, previous=record
                )
                suites_run.append(suite["name"])
                # Persist per attempt: a pass cancelled between suites
                # must not lose (and later re-buy) a completed result.
                self._save_sidecar(sidecar)
            if not suites_run:
                skipped = "all suites fresh"

        return {
            "metrics": self._metrics(sidecar),
            "report_block": self._render_block(sidecar),
            "suites_run": suites_run,
            "skipped": skipped,
        }

    async def _run_suite(
        self,
        suite: Dict[str, str],
        bench_root: Path,
        muxi_md_path: Optional[str],
        previous: Dict[str, Any],
    ) -> Dict[str, Any]:
        """One subprocess attempt; the returned record replaces the old one.

        The previous scores are kept on the record (as ``scores`` after a
        failure, as ``previous_scores`` after a success) so metrics carry
        forward and the tuner sees deltas.
        """
        started = time.monotonic()
        output_path = self._base_dir() / f"bench-{suite['name']}.json"
        command = [
            sys.executable,
            "-m",
            suite["module"],
            "--fixture",
            "--qa",
            "--output",
            str(output_path),
        ]
        if muxi_md_path:
            command.extend(["--muxi-md", muxi_md_path])

        record: Dict[str, Any] = {
            "attempted_at": time.time(),
            "succeeded": False,
            "scores": previous.get("scores"),
            "previous_scores": previous.get("previous_scores"),
            "error": None,
        }
        # The child's import path is explicit, never an accident of cwd:
        # ``-m bench...`` only resolves through the interpreter's
        # implicit-cwd sys.path entry, which safe-path environments
        # (PYTHONSAFEPATH, seen on CI runners) and any deployment
        # launching from elsewhere do not provide. The bench root goes
        # on PYTHONPATH explicitly, merged in front of any existing
        # entries. A harness checkout carries the runtime under src/;
        # putting it first lets the benchmark measure that checkout's
        # code and keeps the subprocess importable when muxi is not
        # installed into the interpreter.
        env = os.environ.copy()
        path_entries = [str(bench_root)]
        src_dir = bench_root / "src"
        if src_dir.is_dir():
            path_entries.insert(0, str(src_dir))
        existing = env.get("PYTHONPATH", "")
        if existing:
            path_entries.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(path_entries)

        process = None
        try:
            self._base_dir().mkdir(parents=True, exist_ok=True)
            # Never trust a stale report: only a file this attempt wrote
            # may become this attempt's evidence.
            output_path.unlink(missing_ok=True)
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(bench_root),
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.suite_timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                # Drain the stderr pipe (not just wait()) so the killed
                # child's transport closes cleanly.
                try:
                    await process.communicate()
                except Exception:
                    await process.wait()
                record["error"] = f"timed out after {self.suite_timeout_seconds:.0f}s"
                return self._finish_attempt(suite, record, started)

            scores = None
            try:
                scores = parse_report(json.loads(output_path.read_text(encoding="utf-8")))
            except Exception:
                pass
            record["exit_code"] = process.returncode
            # The report is the verdict, not the exit code: runners have
            # been seen segfaulting in native-library teardown AFTER
            # writing a complete report, and parse_report already rejects
            # partial or errored runs.
            if scores is not None:
                record["succeeded"] = True
                record["previous_scores"] = previous.get("scores")
                record["scores"] = scores
            else:
                tail = (stderr or b"").decode("utf-8", errors="replace").strip()
                record["error"] = (
                    f"no usable report (exit {process.returncode}"
                    + (f": {tail[-MAX_ERROR_CHARS:]}" if tail else "")
                    + ")"
                )
        except BaseException as e:
            # No orphans: a crash here -- or the loop's own cancellation
            # at shutdown -- must not leave a benchmark subprocess (and
            # its formation) running.
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            if not isinstance(e, Exception):
                raise
            record["error"] = f"{type(e).__name__}: {e}"
        return self._finish_attempt(suite, record, started)

    def _finish_attempt(
        self, suite: Dict[str, str], record: Dict[str, Any], started: float
    ) -> Dict[str, Any]:
        record["duration_seconds"] = round(time.monotonic() - started, 1)
        scores = record.get("scores") if record["succeeded"] else None
        observability.observe(
            event_type=observability.SystemEvents.TUNING_BENCHMARK,
            level=(
                observability.EventLevel.INFO
                if record["succeeded"]
                else observability.EventLevel.WARNING
            ),
            data={
                "suite": suite["name"],
                "succeeded": record["succeeded"],
                "duration_seconds": record["duration_seconds"],
                "scores": scores,
                "error": record.get("error"),
            },
            description=(
                f"Benchmark suite {suite['name']} "
                + (
                    f"scored recall@{scores['k']:.0f}={scores['recall_at_k']:.3f}, "
                    f"qa_accuracy={scores['qa_accuracy']:.3f}"
                    if scores
                    else f"failed: {record.get('error')}"
                )
            ),
        )
        return record

    # ------------------------------------------------------------------
    # Scores -> metrics/prose
    # ------------------------------------------------------------------

    def _metrics(self, sidecar: Dict[str, Any]) -> Dict[str, float]:
        """Lower-is-better metrics from the latest scores of every suite.

        Inverted (gap/error, not recall/accuracy) to satisfy the watch
        windows' "improvement is a drop" contract, and always carried
        forward from the sidecar so a skipped or failed pass never
        false-validates a learning through metric absence.
        """
        metrics: Dict[str, float] = {}
        for name, record in (sidecar.get("suites") or {}).items():
            scores = record.get("scores") if isinstance(record, dict) else None
            if not isinstance(scores, dict):
                continue
            recall = scores.get("recall_at_k")
            accuracy = scores.get("qa_accuracy")
            if isinstance(recall, (int, float)):
                metrics[f"benchmark:{name}.recall_gap"] = round(1.0 - float(recall), 6)
            if isinstance(accuracy, (int, float)):
                metrics[f"benchmark:{name}.qa_error"] = round(1.0 - float(accuracy), 6)
        return metrics

    def _render_block(self, sidecar: Dict[str, Any]) -> str:
        """Prose benchmark results for the tuner prompt ('' = nothing)."""
        lines: List[str] = []
        for suite in SUITES:
            record = sidecar.get("suites", {}).get(suite["name"])
            if not isinstance(record, dict):
                continue
            scores = record.get("scores")
            if isinstance(scores, dict):
                line = (
                    f"- {suite['name']} (fixture, QA): "
                    f"recall@{scores.get('k', 0):.0f} {scores.get('recall_at_k', 0.0):.1%}, "
                    f"QA accuracy {scores.get('qa_accuracy', 0.0):.1%}"
                )
                previous = record.get("previous_scores")
                if isinstance(previous, dict):
                    line += (
                        f" (previous run: recall {previous.get('recall_at_k', 0.0):.1%}, "
                        f"QA {previous.get('qa_accuracy', 0.0):.1%})"
                    )
                if not record.get("succeeded"):
                    line += f" [stale: latest attempt failed: {record.get('error')}]"
                lines.append(line)
            elif record.get("error"):
                lines.append(f"- {suite['name']}: no scores yet ({record['error']})")
        return "\n".join(lines)


__all__ = ["BenchmarkStep", "discover_bench_root", "parse_report"]
