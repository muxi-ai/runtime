"""Longitudinal corpus generator tests (determinism + scenario coverage)."""

import json
from datetime import date, timedelta

import pytest

from bench.memory.longitudinal_corpus import (
    CONFLICTED_NEW_CONFIDENCE,
    CONFLICTED_OLD_CONFIDENCE,
    CROSS_AGENT_AGENTS,
    EARLY_WINDOW_DAYS,
    PRESETS,
    SCENARIO_BUFFER_CYCLE,
    SCENARIO_CONTRADICTION,
    SCENARIO_CROSS_AGENT,
    SCENARIO_ISOLATION,
    SCENARIOS,
    SUPERSEDED_NEW_CONFIDENCE,
    SUPERSEDED_OLD_CONFIDENCE,
    generate_dataset,
)
from bench.memory.structured_corpus import write_dataset

EXCLUSIVE_PREDICATES = {"works_at", "lives_in"}
# graph/models.py: delta above 0.3 supersedes, at/below flags conflicted.
SUPERSEDE_CONFIDENCE_DELTA = 0.3


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(preset="fixture", seed=42)


def _case(dataset, scenario):
    return dataset["scenarios"][scenario]["cases"][0]


def _turn_ids(case):
    return {
        f"{session['session_id']}:{index}"
        for session in case["sessions"]
        for index in range(len(session["turns"]))
    }


class TestDeterminism:
    def test_same_seed_identical(self):
        a = generate_dataset(preset="fixture", seed=7)
        b = generate_dataset(preset="fixture", seed=7)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_different_seed_differs(self):
        a = generate_dataset(preset="fixture", seed=7)
        b = generate_dataset(preset="fixture", seed=8)
        assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)

    def test_written_file_bytes_stable(self, tmp_path):
        dataset = generate_dataset(preset="fixture", seed=3)
        first = write_dataset(dataset, tmp_path / "a.json")
        second = write_dataset(dataset, tmp_path / "b.json")
        assert first.read_text() == second.read_text()

    def test_unknown_preset_rejected(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            generate_dataset(preset="nope")


class TestStructure:
    def test_all_scenarios_present(self, dataset):
        assert set(dataset["scenarios"]) == set(SCENARIOS)

    def test_every_scenario_has_cases_and_sessions(self, dataset):
        for scenario in SCENARIOS:
            cases = dataset["scenarios"][scenario]["cases"]
            assert cases, scenario
            for case in cases:
                assert case["sessions"], case["case_id"]
                for session in case["sessions"]:
                    assert session["date"]
                    assert session["turns"]

    def test_evidence_ids_exist_in_corpus(self, dataset):
        for scenario in SCENARIOS:
            for case in dataset["scenarios"][scenario]["cases"]:
                session_ids = {session["session_id"] for session in case["sessions"]}
                turn_ids = _turn_ids(case)
                for question in case["questions"]:
                    assert question["evidence_session_ids"], question["question_id"]
                    for session_id in question["evidence_session_ids"]:
                        assert session_id in session_ids
                    for turn_id in question["evidence_turn_ids"]:
                        assert turn_id in turn_ids

    def test_exact_strings_appear_in_evidence_turns(self, dataset):
        for scenario in SCENARIOS:
            for case in dataset["scenarios"][scenario]["cases"]:
                texts_by_turn = {
                    f"{session['session_id']}:{index}": turn["content"]
                    for session in case["sessions"]
                    for index, turn in enumerate(session["turns"])
                }
                for question in case["questions"]:
                    if not question["exact_strings"] or not question["evidence_turn_ids"]:
                        continue
                    evidence_texts = [
                        texts_by_turn[turn_id] for turn_id in question["evidence_turn_ids"]
                    ]
                    for exact in question["exact_strings"]:
                        assert any(exact.lower() in text.lower() for text in evidence_texts), (
                            question["question_id"],
                            exact,
                        )

    def test_relationship_provenance_points_at_real_turns(self, dataset):
        for scenario in SCENARIOS:
            for case in dataset["scenarios"][scenario]["cases"]:
                turn_ids = _turn_ids(case)
                for rel in case["ground_truth"]["relationships"]:
                    assert rel["turn_id"] in turn_ids, rel


class TestBufferCycleScenario:
    def test_evicted_questions_target_early_window(self, dataset):
        case = _case(dataset, SCENARIO_BUFFER_CYCLE)
        dates = {session["session_id"]: session["date"] for session in case["sessions"]}
        window = case["ground_truth"]["early_window"]
        for question in case["questions"]:
            if question["category"] != "evicted_recall":
                continue
            for session_id in question["evidence_session_ids"]:
                assert window["date_from"] <= dates[session_id] <= window["date_to"], question

    def test_recent_questions_target_late_window(self, dataset):
        case = _case(dataset, SCENARIO_BUFFER_CYCLE)
        params = PRESETS["fixture"][SCENARIO_BUFFER_CYCLE]
        dates = {session["session_id"]: session["date"] for session in case["sessions"]}
        start = date.fromisoformat(case["ground_truth"]["early_window"]["date_from"])
        recent_cutoff = (
            start + timedelta(days=params["span_days"] - EARLY_WINDOW_DAYS)
        ).isoformat()
        for question in case["questions"]:
            if question["category"] != "recent_recall":
                continue
            for session_id in question["evidence_session_ids"]:
                assert dates[session_id] >= recent_cutoff, question

    def test_both_categories_present(self, dataset):
        case = _case(dataset, SCENARIO_BUFFER_CYCLE)
        categories = {question["category"] for question in case["questions"]}
        assert categories == {"evicted_recall", "recent_recall"}

    def test_corpus_spans_the_configured_window(self, dataset):
        case = _case(dataset, SCENARIO_BUFFER_CYCLE)
        params = PRESETS["fixture"][SCENARIO_BUFFER_CYCLE]
        dates = sorted(session["date"] for session in case["sessions"])
        first = date.fromisoformat(dates[0])
        last = date.fromisoformat(dates[-1])
        assert (last - first).days == params["span_days"] - 1

    def test_decisions_match_log_entries(self, dataset):
        case = _case(dataset, SCENARIO_BUFFER_CYCLE)
        truth = case["ground_truth"]
        assert truth["decisions"]
        logged = {decision for entry in truth["log_entries"] for decision in entry["decisions"]}
        for item in truth["decisions"]:
            assert item["decision"] in logged


class TestCrossAgentScenario:
    def test_four_prd_agents(self, dataset):
        case = _case(dataset, SCENARIO_CROSS_AGENT)
        agents = {session["agent_id"] for session in case["sessions"]}
        assert agents == set(CROSS_AGENT_AGENTS)

    def test_every_question_crosses_agents(self, dataset):
        case = _case(dataset, SCENARIO_CROSS_AGENT)
        meta = case["ground_truth"]["question_meta"]
        assert case["questions"]
        for question in case["questions"]:
            pair = meta[question["question_id"]]
            assert pair["asking_agent"] != pair["evidence_agent"], question["question_id"]
            assert pair["asking_agent"] in CROSS_AGENT_AGENTS

    def test_evidence_sessions_belong_to_evidence_agent(self, dataset):
        case = _case(dataset, SCENARIO_CROSS_AGENT)
        meta = case["ground_truth"]["question_meta"]
        agents = {session["session_id"]: session["agent_id"] for session in case["sessions"]}
        for question in case["questions"]:
            expected = meta[question["question_id"]]["evidence_agent"]
            for session_id in question["evidence_session_ids"]:
                assert agents[session_id] == expected

    def test_question_texts_unambiguous(self, dataset):
        # Every "who recommended X for Y" must have exactly one answer:
        # duplicate question texts would make the gold answer ambiguous.
        case = _case(dataset, SCENARIO_CROSS_AGENT)
        texts = [question["question"] for question in case["questions"]]
        assert len(texts) == len(set(texts))

    def test_artifacts_unique_with_provenance(self, dataset):
        case = _case(dataset, SCENARIO_CROSS_AGENT)
        artifacts = case["ground_truth"]["artifacts"]
        assert artifacts
        names = [artifact["name"] for artifact in artifacts]
        assert len(names) == len(set(names))
        turn_ids = _turn_ids(case)
        for artifact in artifacts:
            assert artifact["turn_id"] in turn_ids
            assert artifact["agent"] in CROSS_AGENT_AGENTS


class TestIsolationScenario:
    def test_one_case_per_user(self, dataset):
        cases = dataset["scenarios"][SCENARIO_ISOLATION]["cases"]
        assert len(cases) == PRESETS["fixture"][SCENARIO_ISOLATION]["users"]
        assert len({case["case_id"] for case in cases}) == len(cases)

    def test_canaries_globally_unique(self, dataset):
        cases = dataset["scenarios"][SCENARIO_ISOLATION]["cases"]
        all_canaries = [canary for case in cases for canary in case["ground_truth"]["canaries"]]
        assert all_canaries
        assert len(all_canaries) == len(set(all_canaries))

    def test_canaries_never_leak_into_other_users_corpora(self, dataset):
        cases = dataset["scenarios"][SCENARIO_ISOLATION]["cases"]
        corpora = {
            case["case_id"]: " ".join(
                turn["content"] for session in case["sessions"] for turn in session["turns"]
            ).lower()
            for case in cases
        }
        for case in cases:
            for canary in case["ground_truth"]["canaries"]:
                for other_id, text in corpora.items():
                    if other_id == case["case_id"]:
                        assert canary.lower() in text
                    else:
                        assert canary.lower() not in text, (case["case_id"], other_id, canary)

    def test_probe_questions_carry_exact_strings(self, dataset):
        for case in dataset["scenarios"][SCENARIO_ISOLATION]["cases"]:
            tagged = [q for q in case["questions"] if q["exact_strings"]]
            assert tagged, case["case_id"]

    def test_identical_probe_templates_across_users(self, dataset):
        # The isolation stressor: every user asks the same questions, so
        # a scoping bug would surface another user's near-identical turn.
        cases = dataset["scenarios"][SCENARIO_ISOLATION]["cases"]
        reference = [q["question"] for q in cases[0]["questions"]]
        for case in cases[1:]:
            assert [q["question"] for q in case["questions"]] == reference

    def test_full_preset_matches_prd_scale(self):
        params = PRESETS["full"][SCENARIO_ISOLATION]
        assert params["users"] == 100
        assert params["span_days"] == 7
        assert params["target_ops"] == 10000


class TestContradictionScenario:
    def test_both_detection_kinds_injected(self, dataset):
        case = _case(dataset, SCENARIO_CONTRADICTION)
        kinds = {c["expected_detection"] for c in case["ground_truth"]["contradictions"]}
        assert kinds == {"conflicted", "superseded"}

    def test_contradictions_use_exclusive_predicates(self, dataset):
        case = _case(dataset, SCENARIO_CONTRADICTION)
        contradictions = case["ground_truth"]["contradictions"]
        assert len(contradictions) == (
            PRESETS["fixture"][SCENARIO_CONTRADICTION]["conflicted"]
            + PRESETS["fixture"][SCENARIO_CONTRADICTION]["superseded"]
        )
        for contradiction in contradictions:
            assert contradiction["predicate"] in EXCLUSIVE_PREDICATES
            assert contradiction["old_turn_id"]
            assert contradiction["new_turn_id"]

    def test_confidences_drive_the_expected_detection(self, dataset):
        # The storage layer supersedes above SUPERSEDE_CONFIDENCE_DELTA
        # and flags conflicted otherwise; the corpus encodes that rule.
        assert SUPERSEDED_NEW_CONFIDENCE - SUPERSEDED_OLD_CONFIDENCE > SUPERSEDE_CONFIDENCE_DELTA
        assert CONFLICTED_NEW_CONFIDENCE - CONFLICTED_OLD_CONFIDENCE <= SUPERSEDE_CONFIDENCE_DELTA
        case = _case(dataset, SCENARIO_CONTRADICTION)
        by_key = {
            (rel["from_name"], rel["type"], rel["to_name"]): rel["confidence"]
            for rel in case["ground_truth"]["relationships"]
        }
        for contradiction in case["ground_truth"]["contradictions"]:
            old_conf = by_key[
                (contradiction["subject"], contradiction["predicate"], contradiction["old_object"])
            ]
            new_conf = by_key[
                (contradiction["subject"], contradiction["predicate"], contradiction["new_object"])
            ]
            if contradiction["expected_detection"] == "superseded":
                assert new_conf - old_conf > SUPERSEDE_CONFIDENCE_DELTA
            else:
                assert new_conf - old_conf <= SUPERSEDE_CONFIDENCE_DELTA

    def test_new_fact_stated_after_old_fact(self, dataset):
        case = _case(dataset, SCENARIO_CONTRADICTION)
        for contradiction in case["ground_truth"]["contradictions"]:
            old_session = contradiction["old_turn_id"].rsplit(":", 1)[0]
            new_session = contradiction["new_turn_id"].rsplit(":", 1)[0]
            assert old_session < new_session, contradiction

    def test_precision_distractors_present(self, dataset):
        case = _case(dataset, SCENARIO_CONTRADICTION)
        kinds = {d["kind"] for d in case["ground_truth"]["distractors"]}
        assert kinds == {"duplicate_fact", "non_exclusive_change"}

    def test_distractor_subjects_do_not_overlap_contradictions(self, dataset):
        case = _case(dataset, SCENARIO_CONTRADICTION)
        contradiction_subjects = {c["subject"] for c in case["ground_truth"]["contradictions"]}
        for distractor in case["ground_truth"]["distractors"]:
            assert distractor["subject"] not in contradiction_subjects
