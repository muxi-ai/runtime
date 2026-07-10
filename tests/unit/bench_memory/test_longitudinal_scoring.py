"""Longitudinal scoring tests (scenario aggregates + leak detection)."""

from bench.memory.longitudinal_scoring import (
    LAYER_STRUCTURED,
    LAYER_WORKING,
    ArtifactAuditItem,
    ContradictionPairAudit,
    DecisionAuditItem,
    IsolationOpResult,
    LongitudinalQuestionResult,
    aggregate_buffer_cycle,
    aggregate_contradiction,
    aggregate_cross_agent,
    aggregate_decisions,
    aggregate_isolation,
    find_leaks,
    render_longitudinal_extras,
    summarize_contradiction_audit,
)


def _result(
    question_id: str,
    category: str,
    layer: str = LAYER_STRUCTURED,
    retrieved=("s1",),
    evidence=("s1",),
    evidence_evicted=None,
):
    return LongitudinalQuestionResult(
        question_id=question_id,
        question_type=category,
        is_abstention=False,
        evidence_session_ids=list(evidence),
        evidence_turn_ids=[],
        retrieved_session_ids=list(retrieved),
        category=category,
        layer=layer,
        evidence_evicted=evidence_evicted,
    )


class TestBufferCycleAggregate:
    def test_layers_split_and_compensation_computed(self):
        results = [
            # Structured layer answers the evicted question...
            _result("q1", "evicted_recall", LAYER_STRUCTURED, evidence_evicted=True),
            # ...the working baseline misses it (evidence evicted).
            _result(
                "q1#working",
                "evicted_recall",
                LAYER_WORKING,
                retrieved=("s9",),
                evidence_evicted=True,
            ),
            # Both layers answer the recent control question.
            _result("q2", "recent_recall", LAYER_STRUCTURED, evidence_evicted=False),
            _result("q2#working", "recent_recall", LAYER_WORKING, evidence_evicted=False),
        ]
        metrics = aggregate_buffer_cycle(
            results,
            k=5,
            eviction={"ingested_turns": 100, "resident_turns": 40, "evicted_turns": 60},
            flush={"hand_offs": 3, "items_handed": 45, "digest_enabled": False},
            decision_items=[DecisionAuditItem("Adopt X", "2026-01-05", True)],
        )
        compensation = metrics["compensation"]
        assert compensation["evicted_recall_structured"] == 1.0
        assert compensation["evicted_recall_working"] == 0.0
        assert compensation["recent_recall_structured"] == 1.0
        assert compensation["recent_recall_working"] == 1.0
        assert compensation["evidence_evicted_fraction"] == 1.0
        assert compensation["target_met"] is True
        # The headline retrieval block covers the structured layer only.
        assert metrics["retrieval"]["session_level"]["overall"]["questions"] == 2
        assert (
            metrics["working_baseline"]["retrieval"]["session_level"]["overall"]["recall@5"] == 0.5
        )
        assert metrics["decisions"]["zero_lost_met"] is True

    def test_target_not_met_below_threshold(self):
        results = [
            _result("q1", "evicted_recall", retrieved=("s9",), evidence_evicted=True),
            _result("q2", "evicted_recall", retrieved=("s1",), evidence_evicted=True),
        ]
        metrics = aggregate_buffer_cycle(results, 5, {}, {}, [])
        assert metrics["compensation"]["evicted_recall_structured"] == 0.5
        assert metrics["compensation"]["target_met"] is False

    def test_partial_eviction_fraction_flags_weak_workload(self):
        results = [
            _result("q1", "evicted_recall", evidence_evicted=True),
            _result("q2", "evicted_recall", evidence_evicted=False),
        ]
        metrics = aggregate_buffer_cycle(results, 5, {}, {}, [])
        assert metrics["compensation"]["evidence_evicted_fraction"] == 0.5


class TestDecisionsAudit:
    def test_lost_decisions_listed(self):
        block = aggregate_decisions(
            [
                DecisionAuditItem("Adopt Kafka", "2026-01-05", True),
                DecisionAuditItem("Drop Neo4j", "2026-01-07", False),
            ]
        )
        assert block == {
            "expected": 2,
            "found": 1,
            "lost": 1,
            "lost_decisions": ["[2026-01-07] Drop Neo4j"],
            "zero_lost_met": False,
        }

    def test_empty_audit_passes(self):
        assert aggregate_decisions([])["zero_lost_met"] is True


class TestCrossAgentAggregate:
    def test_orphans_and_target(self):
        results = [
            _result("q1", "cross_agent_propagation"),
            _result("q2", "cross_agent_propagation", retrieved=("s9",)),
        ]
        artifacts = [
            ArtifactAuditItem("report", "finance-agent", True, True),
            ArtifactAuditItem("memo", "research-agent", True, False),
        ]
        metrics = aggregate_cross_agent(results, 5, artifacts)
        assert metrics["propagation"]["recall@5"] == 0.5
        assert metrics["propagation"]["target_met"] is False
        assert metrics["artifacts"]["orphans"] == 1
        assert metrics["artifacts"]["orphan_names"] == ["memo (research-agent)"]
        assert metrics["artifacts"]["zero_orphans_met"] is False

    def test_full_recall_meets_target(self):
        results = [_result("q1", "cross_agent_propagation")]
        metrics = aggregate_cross_agent(
            results, 5, [ArtifactAuditItem("report", "finance-agent", True, True)]
        )
        assert metrics["propagation"]["target_met"] is True
        assert metrics["artifacts"]["zero_orphans_met"] is True


class TestFindLeaks:
    CANARIES = {
        "CANARY-000-1111AA": "seq_isolation_000",
        "CANARY-001-2222BB": "seq_isolation_001",
    }

    def test_own_canary_is_not_a_leak(self):
        leaks = find_leaks(
            ["your locker code is CANARY-000-1111AA"],
            ["seq_isolation_000_s001"],
            "seq_isolation_000",
            self.CANARIES,
        )
        assert leaks == []

    def test_foreign_canary_is_a_leak(self):
        leaks = find_leaks(
            ["the code is canary-001-2222bb"],  # case-insensitive
            [],
            "seq_isolation_000",
            self.CANARIES,
        )
        assert len(leaks) == 1
        assert leaks[0]["kind"] == "foreign_canary"
        assert leaks[0]["canary_owner"] == "seq_isolation_001"

    def test_foreign_session_is_a_leak(self):
        leaks = find_leaks(
            [],
            ["seq_isolation_001_s003"],
            "seq_isolation_000",
            self.CANARIES,
        )
        assert len(leaks) == 1
        assert leaks[0]["kind"] == "foreign_session"


class TestIsolationAggregate:
    def test_clean_run_passes(self):
        ops = [
            IsolationOpResult("seq_isolation_000", "vector_search", "q"),
            IsolationOpResult("seq_isolation_001", "graph", ""),
        ]
        metrics = aggregate_isolation(ops, users=2, target_ops=2)
        assert metrics["passed"] is True
        assert metrics["leaks"] == 0
        assert metrics["by_op_kind"]["graph"]["operations"] == 1

    def test_any_leak_fails(self):
        ops = [
            IsolationOpResult(
                "seq_isolation_000",
                "vector_search",
                "q",
                leaks=[{"kind": "foreign_canary", "canary_owner": "x", "detail": "C"}],
            )
        ]
        metrics = aggregate_isolation(ops, users=1, target_ops=1)
        assert metrics["passed"] is False
        assert metrics["leaks"] == 1
        assert metrics["leak_details"][0]["case_id"] == "seq_isolation_000"

    def test_errored_ops_fail_the_audit(self):
        ops = [IsolationOpResult("seq_isolation_000", "log", "", error="boom")]
        metrics = aggregate_isolation(ops, users=1, target_ops=1)
        assert metrics["passed"] is False
        assert metrics["operations_errored"] == 1

    def test_zero_ops_never_passes(self):
        assert aggregate_isolation([], users=0, target_ops=0)["passed"] is False


def _pair(detected=True, kind="conflicted", expected="conflicted", subject="Kai"):
    return ContradictionPairAudit(
        subject=subject,
        predicate="works_at",
        old_object="A",
        new_object="B",
        expected_detection=expected,
        detected=detected,
        detected_kind=kind if detected else None,
    )


class TestContradictionAggregate:
    def test_precision_recall_and_kind_accuracy(self):
        pairs = [
            _pair(detected=True, kind="conflicted", expected="conflicted", subject="Kai"),
            _pair(detected=True, kind="conflicted", expected="superseded", subject="Mara"),
            _pair(detected=False, expected="conflicted", subject="Ravi"),
        ]
        false_positives = [("noor", "works_at", "a", "b")]
        summary = summarize_contradiction_audit(pairs, false_positives)
        assert summary["expected"] == 3
        assert summary["true_positives"] == 2
        assert summary["detected"] == 3
        assert summary["precision"] == 2 / 3
        assert summary["recall"] == 2 / 3
        assert summary["detection_kind_accuracy"] == 0.5
        assert summary["missed_pairs"] == ["Ravi works_at A -> B"]
        assert len(summary["kind_mismatches"]) == 1

    def test_targets_and_rebuild_consistency(self):
        pairs = [_pair(subject=name) for name in ("Kai", "Mara", "Ravi")]
        metrics = aggregate_contradiction(
            pairs,
            [],
            events={"available": True, "events": 3, "matches_detections": True},
            rebuild_pairs=pairs,
            rebuild_false_positives=[],
            rebuild_report={"events": 5, "applied": 5, "failed": 0},
        )
        assert metrics["targets"]["precision_met"] is True
        assert metrics["targets"]["recall_met"] is True
        assert metrics["rebuild"]["consistent_with_live"] is True

    def test_rebuild_divergence_detected(self):
        live = [_pair(subject=name) for name in ("Kai", "Mara")]
        rebuilt = [
            _pair(subject="Kai"),
            _pair(detected=False, expected="conflicted", subject="Mara"),
        ]
        metrics = aggregate_contradiction(
            live,
            [],
            events={"available": True, "events": 2, "matches_detections": True},
            rebuild_pairs=rebuilt,
        )
        assert metrics["rebuild"]["consistent_with_live"] is False

    def test_no_rebuild_block_when_unavailable(self):
        metrics = aggregate_contradiction([_pair()], [], events={"available": False, "events": 0})
        assert "rebuild" not in metrics


class TestRendering:
    def test_every_scenario_renders(self):
        # Rendering must never crash on the aggregates it is fed.
        buffer_metrics = aggregate_buffer_cycle(
            [_result("q1", "evicted_recall", evidence_evicted=True)],
            5,
            {"ingested_turns": 10, "evicted_turns": 4, "max_memory_mb": 0.4},
            {"hand_offs": 1, "items_handed": 5, "digest_enabled": False},
            [DecisionAuditItem("d", "2026-01-01", True)],
        )
        cross_metrics = aggregate_cross_agent(
            [_result("q1", "cross_agent_propagation")],
            5,
            [ArtifactAuditItem("report", "finance-agent", True, True)],
        )
        isolation_metrics = aggregate_isolation(
            [IsolationOpResult("c", "graph", "")], users=1, target_ops=1
        )
        contradiction_metrics = aggregate_contradiction(
            [_pair()],
            [],
            events={"available": True, "events": 1, "matches_detections": True},
            rebuild_pairs=[_pair()],
        )
        for scenario, metrics in (
            ("buffer_cycle", buffer_metrics),
            ("cross_agent", cross_metrics),
            ("isolation", isolation_metrics),
            ("contradiction", contradiction_metrics),
        ):
            rendered = render_longitudinal_extras(scenario, metrics, 5)
            assert rendered.strip(), scenario
