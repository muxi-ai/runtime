"""Scoring extensions for the Tier 3 longitudinal benchmark.

Adds the four scenario-specific measurement blocks on top of the
Tier 1/2 machinery (memory-benchmarking PRD, Tier 3):

- **Buffer cycle compensation (A)** — retrieval over the persisted
  layers (KG + Captain's Log) vs the working-memory baseline, split by
  ``evicted_recall`` / ``recent_recall``; eviction and pre-compaction
  flush statistics; the zero-lost-decisions audit. PRD targets:
  day-1 recall at day-30 >= 0.85, zero lost decisions.
- **Cross-agent propagation (B)** — recall over questions whose
  evidence was produced in a different agent's sessions, plus the
  zero-artifact-orphans audit. PRD targets: R@5 >= 0.80, zero orphans.
- **Multi-user isolation (C)** — leak detection over retrieval
  operations: a leak is a foreign user's canary token in retrieved
  text, or a retrieved item attributed to another user's sessions.
  Pass/fail per the PRD: zero leaks.
- **Contradiction detection over time (D)** — precision/recall of the
  KG's conflict/supersede flags against injected pairs, detection-kind
  accuracy (conflicted vs superseded), the substrate's
  ``fact.contradicted`` event tally, and a rebuild consistency check
  (the same audit after an event-log projection rebuild). PRD
  targets: precision >= 0.90, recall >= 0.80.

All functions are pure and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .scoring import aggregate_results
from .structured_scoring import StructuredQuestionResult, aggregate_structured_results

# PRD Tier 3 targets (Success Criteria table).
TARGET_BUFFER_CYCLE_RECALL = 0.85
TARGET_CROSS_AGENT_RECALL = 0.80
TARGET_CONTRADICTION_PRECISION = 0.90
TARGET_CONTRADICTION_RECALL = 0.80

# Retrieval layers measured in Scenario A.
LAYER_STRUCTURED = "structured"
LAYER_WORKING = "working"

# Cap on leak details embedded in a report (a systematic leak would
# otherwise bloat the JSON with thousands of identical entries).
MAX_LEAK_DETAILS = 50


@dataclass
class LongitudinalQuestionResult(StructuredQuestionResult):
    """Tier 2 result plus the Tier 3 measurements."""

    # Which retrieval layer produced this result (Scenario A runs every
    # question against both the persisted layers and the buffer).
    layer: str = LAYER_STRUCTURED
    # Scenario A: were ALL evidence turns already evicted from the
    # working-memory buffer when the question was asked?
    evidence_evicted: Optional[bool] = None


# ---------------------------------------------------------------------------
# Scenario A: buffer cycle compensation
# ---------------------------------------------------------------------------


@dataclass
class DecisionAuditItem:
    """One ground-truth decision checked against the Captain's Log."""

    decision: str
    date: str
    found: bool


def aggregate_decisions(items: Sequence[DecisionAuditItem]) -> Dict[str, Any]:
    """The PRD's "zero lost decisions" audit block."""
    lost = [item for item in items if not item.found]
    return {
        "expected": len(items),
        "found": len(items) - len(lost),
        "lost": len(lost),
        "lost_decisions": sorted(f"[{item.date}] {item.decision}" for item in lost),
        "zero_lost_met": not lost,
    }


def _category_recall(metrics: Dict[str, Any], category: str, k: int) -> Optional[float]:
    """Session-level recall@k for one question category, if measured."""
    level = (metrics.get("retrieval") or {}).get("session_level") or {}
    stats = (level.get("by_question_type") or {}).get(category)
    if not stats:
        return None
    return stats.get(f"recall@{k}")


def aggregate_buffer_cycle(
    results: Sequence[LongitudinalQuestionResult],
    k: int,
    eviction: Dict[str, Any],
    flush: Dict[str, Any],
    decision_items: Sequence[DecisionAuditItem],
) -> Dict[str, Any]:
    """Scenario A metrics: structured headline + working baseline + audits."""
    structured = [result for result in results if result.layer == LAYER_STRUCTURED]
    working = [result for result in results if result.layer == LAYER_WORKING]

    metrics = aggregate_structured_results(structured, k)
    metrics["working_baseline"] = aggregate_results(working, k)
    metrics["eviction"] = dict(eviction)
    metrics["flush"] = dict(flush)
    metrics["decisions"] = aggregate_decisions(decision_items)

    evicted_flags = [
        result.evidence_evicted
        for result in structured
        if result.question_type == "evicted_recall" and result.evidence_evicted is not None
    ]
    evicted_recall = _category_recall(metrics, "evicted_recall", k)
    metrics["compensation"] = {
        "evicted_recall_structured": evicted_recall,
        "evicted_recall_working": _category_recall(
            metrics["working_baseline"], "evicted_recall", k
        ),
        "recent_recall_structured": _category_recall(metrics, "recent_recall", k),
        "recent_recall_working": _category_recall(metrics["working_baseline"], "recent_recall", k),
        # Fraction of evicted-category questions whose evidence turns
        # were actually gone from the buffer (must be 1.0 for the
        # scenario to prove anything; below that the workload/budget
        # did not cycle the buffer far enough).
        "evidence_evicted_fraction": (
            sum(float(flag) for flag in evicted_flags) / len(evicted_flags)
            if evicted_flags
            else None
        ),
        "target": TARGET_BUFFER_CYCLE_RECALL,
        "target_met": (evicted_recall is not None and evicted_recall >= TARGET_BUFFER_CYCLE_RECALL),
    }
    return metrics


# ---------------------------------------------------------------------------
# Scenario B: cross-agent knowledge propagation
# ---------------------------------------------------------------------------


@dataclass
class ArtifactAuditItem:
    """One ground-truth artifact checked for KG reachability."""

    name: str
    agent: str
    entity_found: bool
    produced_link_found: bool

    @property
    def reachable(self) -> bool:
        return self.entity_found and self.produced_link_found


def aggregate_cross_agent(
    results: Sequence[LongitudinalQuestionResult],
    k: int,
    artifact_items: Sequence[ArtifactAuditItem],
) -> Dict[str, Any]:
    """Scenario B metrics: propagation recall + zero-orphan audit."""
    metrics = aggregate_structured_results(results, k)

    orphans = [item for item in artifact_items if not item.reachable]
    metrics["artifacts"] = {
        "expected": len(artifact_items),
        "reachable": len(artifact_items) - len(orphans),
        "orphans": len(orphans),
        "orphan_names": sorted(f"{item.name} ({item.agent})" for item in orphans),
        "zero_orphans_met": not orphans,
    }

    recall = _category_recall(metrics, "cross_agent_propagation", k)
    metrics["propagation"] = {
        f"recall@{k}": recall,
        "target": TARGET_CROSS_AGENT_RECALL,
        "target_met": recall is not None and recall >= TARGET_CROSS_AGENT_RECALL,
    }
    return metrics


# ---------------------------------------------------------------------------
# Scenario C: multi-user isolation
# ---------------------------------------------------------------------------


@dataclass
class IsolationOpResult:
    """One retrieval operation checked for cross-user leaks."""

    case_id: str
    op_kind: str  # vector_search | graph | log
    query: str
    leaks: List[Dict[str, str]] = field(default_factory=list)
    error: Optional[str] = None


def find_leaks(
    texts: Sequence[str],
    session_ids: Sequence[str],
    own_case_id: str,
    canary_owners: Dict[str, str],
) -> List[Dict[str, str]]:
    """Detect cross-user leaks in one operation's retrieved items.

    ``canary_owners`` maps every canary token (all users) to its owner
    case id. A leak is (a) a canary owned by another case appearing in
    retrieved text, or (b) a retrieved item attributed to another
    case's session id.
    """
    leaks: List[Dict[str, str]] = []
    for text in texts:
        haystack = str(text).lower()
        for canary, owner in canary_owners.items():
            if owner != own_case_id and canary.lower() in haystack:
                leaks.append(
                    {
                        "kind": "foreign_canary",
                        "canary_owner": owner,
                        "detail": canary,
                    }
                )
    for session_id in session_ids:
        if session_id and not str(session_id).startswith(own_case_id):
            leaks.append(
                {
                    "kind": "foreign_session",
                    "canary_owner": "",
                    "detail": str(session_id),
                }
            )
    return leaks


def aggregate_isolation(
    ops: Sequence[IsolationOpResult], users: int, target_ops: int
) -> Dict[str, Any]:
    """Scenario C metrics: pass/fail leak audit over retrieval ops."""
    errored = [op for op in ops if op.error]
    leaks: List[Dict[str, str]] = []
    by_kind: Dict[str, Dict[str, int]] = {}
    for op in ops:
        stats = by_kind.setdefault(op.op_kind, {"operations": 0, "leaks": 0, "errors": 0})
        stats["operations"] += 1
        if op.error:
            stats["errors"] += 1
            continue
        stats["leaks"] += len(op.leaks)
        for leak in op.leaks:
            leaks.append({**leak, "case_id": op.case_id, "op_kind": op.op_kind})

    return {
        "users": users,
        "operations": len(ops),
        "target_operations": target_ops,
        "operations_errored": len(errored),
        "leaks": len(leaks),
        "leak_details": sorted(
            (leaks[:MAX_LEAK_DETAILS]),
            key=lambda leak: (leak["case_id"], leak["kind"], leak["detail"]),
        ),
        "by_op_kind": {kind: stats for kind, stats in sorted(by_kind.items())},
        # Pass/fail per the PRD: zero leaks across every completed
        # operation. Errored operations do not count as leak-free.
        "passed": not leaks and not errored and len(ops) > 0,
    }


# ---------------------------------------------------------------------------
# Scenario D: contradiction detection over time
# ---------------------------------------------------------------------------


@dataclass
class ContradictionPairAudit:
    """One injected contradiction pair checked against the KG flags."""

    subject: str
    predicate: str
    old_object: str
    new_object: str
    expected_detection: str  # conflicted | superseded
    detected: bool = False
    detected_kind: Optional[str] = None


def summarize_contradiction_audit(
    pairs: Sequence[ContradictionPairAudit],
    false_positive_pairs: Sequence[Sequence[str]],
) -> Dict[str, Any]:
    """Precision/recall/kind-accuracy for one audit pass."""
    expected = len(pairs)
    detected_expected = [pair for pair in pairs if pair.detected]
    true_positives = len(detected_expected)
    detected_total = true_positives + len(false_positive_pairs)
    kind_correct = [
        pair for pair in detected_expected if pair.detected_kind == pair.expected_detection
    ]
    precision = (true_positives / detected_total) if detected_total else None
    recall = (true_positives / expected) if expected else None
    return {
        "expected": expected,
        "detected": detected_total,
        "true_positives": true_positives,
        "false_positives": len(false_positive_pairs),
        "false_positive_pairs": sorted(list(pair) for pair in false_positive_pairs),
        "missed_pairs": sorted(
            f"{pair.subject} {pair.predicate} {pair.old_object} -> {pair.new_object}"
            for pair in pairs
            if not pair.detected
        ),
        "precision": precision,
        "recall": recall,
        "detection_kind_accuracy": (len(kind_correct) / true_positives if true_positives else None),
        "kind_mismatches": sorted(
            f"{pair.subject} {pair.predicate}: expected {pair.expected_detection}, "
            f"detected {pair.detected_kind}"
            for pair in detected_expected
            if pair.detected_kind != pair.expected_detection
        ),
    }


def aggregate_contradiction(
    live_pairs: Sequence[ContradictionPairAudit],
    live_false_positives: Sequence[Sequence[str]],
    events: Dict[str, Any],
    rebuild_pairs: Optional[Sequence[ContradictionPairAudit]] = None,
    rebuild_false_positives: Sequence[Sequence[str]] = (),
    rebuild_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Scenario D metrics: live audit + substrate events + rebuild check."""
    live = summarize_contradiction_audit(live_pairs, live_false_positives)
    metrics: Dict[str, Any] = {
        "contradiction_detection": live,
        "substrate_events": dict(events),
        "targets": {
            "precision_target": TARGET_CONTRADICTION_PRECISION,
            "recall_target": TARGET_CONTRADICTION_RECALL,
            "precision_met": (
                live["precision"] is not None
                and live["precision"] >= TARGET_CONTRADICTION_PRECISION
            ),
            "recall_met": (
                live["recall"] is not None and live["recall"] >= TARGET_CONTRADICTION_RECALL
            ),
        },
    }
    if rebuild_pairs is not None:
        rebuilt = summarize_contradiction_audit(rebuild_pairs, rebuild_false_positives)
        metrics["rebuild"] = {
            "audit": rebuilt,
            "projection_report": dict(rebuild_report or {}),
            "consistent_with_live": (
                rebuilt["true_positives"] == live["true_positives"]
                and rebuilt["false_positives"] == live["false_positives"]
                and rebuilt["detection_kind_accuracy"] == live["detection_kind_accuracy"]
            ),
        }
    return metrics


# ---------------------------------------------------------------------------
# Stdout rendering
# ---------------------------------------------------------------------------


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def render_longitudinal_extras(scenario: str, metrics: Dict[str, Any], k: int) -> str:
    """Scenario-specific stdout lines appended to the shared summary."""
    lines: List[str] = []

    if scenario == "buffer_cycle":
        compensation = metrics.get("compensation") or {}
        eviction = metrics.get("eviction") or {}
        flush = metrics.get("flush") or {}
        decisions = metrics.get("decisions") or {}
        lines.append("")
        lines.append("BUFFER CYCLE COMPENSATION (evicted day-1 facts at day-30):")
        lines.append(
            f"  evicted_recall: structured R@{k}="
            f"{_pct(compensation.get('evicted_recall_structured'))}  "
            f"working-baseline R@{k}={_pct(compensation.get('evicted_recall_working'))}  "
            f"(target >= {_pct(compensation.get('target'))}: "
            f"{'MET' if compensation.get('target_met') else 'NOT MET'})"
        )
        lines.append(
            f"  recent_recall:  structured R@{k}="
            f"{_pct(compensation.get('recent_recall_structured'))}  "
            f"working-baseline R@{k}={_pct(compensation.get('recent_recall_working'))}"
        )
        lines.append(
            f"  eviction: {eviction.get('evicted_turns', 0)}/"
            f"{eviction.get('ingested_turns', 0)} turns evicted "
            f"(budget {eviction.get('max_memory_mb')}MB, cycles="
            f"{eviction.get('cleanup_passes', 0)}), evidence evicted for "
            f"{_pct(compensation.get('evidence_evicted_fraction'))} of evicted questions"
        )
        lines.append(
            f"  pre-compaction flush: {flush.get('hand_offs', 0)} hand-offs / "
            f"{flush.get('items_handed', 0)} items "
            f"(digest {'ON' if flush.get('digest_enabled') else 'off - counting only'})"
        )
        lines.append(
            f"  decisions: {decisions.get('found', 0)}/{decisions.get('expected', 0)} "
            f"findable via Captain's Log "
            f"(zero lost: {'MET' if decisions.get('zero_lost_met') else 'NOT MET'})"
        )
        lost = decisions.get("lost_decisions") or []
        if lost:
            lines.append(f"  LOST: {'; '.join(lost)}")

    elif scenario == "cross_agent":
        propagation = metrics.get("propagation") or {}
        artifacts = metrics.get("artifacts") or {}
        lines.append("")
        lines.append(
            f"Cross-agent propagation: R@{k}={_pct(propagation.get(f'recall@{k}'))} "
            f"(target >= {_pct(propagation.get('target'))}: "
            f"{'MET' if propagation.get('target_met') else 'NOT MET'})"
        )
        lines.append(
            f"Artifact orphans: {artifacts.get('orphans', 0)}/{artifacts.get('expected', 0)} "
            f"(zero orphans: {'MET' if artifacts.get('zero_orphans_met') else 'NOT MET'})"
        )
        orphan_names = artifacts.get("orphan_names") or []
        if orphan_names:
            lines.append(f"  ORPHANS: {', '.join(orphan_names)}")

    elif scenario == "isolation":
        lines.append("")
        lines.append(
            f"Multi-user isolation: {metrics.get('leaks', 0)} leaks across "
            f"{metrics.get('operations', 0)} retrieval operations / "
            f"{metrics.get('users', 0)} users -> "
            f"{'PASSED' if metrics.get('passed') else 'FAILED'}"
        )
        for kind, stats in (metrics.get("by_op_kind") or {}).items():
            lines.append(
                f"  {kind:<16} operations={stats['operations']:<6} "
                f"leaks={stats['leaks']}  errors={stats['errors']}"
            )

    elif scenario == "contradiction":
        detection = metrics.get("contradiction_detection") or {}
        targets = metrics.get("targets") or {}
        events = metrics.get("substrate_events") or {}
        lines.append("")
        lines.append(
            f"Contradiction detection: precision={_pct(detection.get('precision'))} "
            f"(target >= {_pct(targets.get('precision_target'))}: "
            f"{'MET' if targets.get('precision_met') else 'NOT MET'})  "
            f"recall={_pct(detection.get('recall'))} "
            f"(target >= {_pct(targets.get('recall_target'))}: "
            f"{'MET' if targets.get('recall_met') else 'NOT MET'})"
        )
        lines.append(
            f"  detection kind accuracy (conflicted vs superseded): "
            f"{_pct(detection.get('detection_kind_accuracy'))}  "
            f"(expected={detection.get('expected')}, detected={detection.get('detected')}, "
            f"false_positives={detection.get('false_positives')})"
        )
        lines.append(
            f"  substrate fact.contradicted events: {events.get('events', 0)} "
            f"(matches detections: {events.get('matches_detections')})"
        )
        rebuild = metrics.get("rebuild")
        if rebuild:
            lines.append(
                f"  rebuild consistency (event-log replay): "
                f"{'CONSISTENT' if rebuild.get('consistent_with_live') else 'DIVERGED'}"
            )

    return "\n".join(lines)
