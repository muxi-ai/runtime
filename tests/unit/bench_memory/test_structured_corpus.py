"""Structured-recall corpus generator tests (determinism + integrity)."""

import json

import pytest

from bench.memory.structured_corpus import (
    CATEGORIES,
    PRESETS,
    SCENARIOS,
    generate_dataset,
    write_dataset,
)

EXCLUSIVE_PREDICATES = {"works_at", "lives_in"}


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(
        sequences=5, sessions_per_sequence=12, questions_per_category=2, seed=42
    )


class TestDeterminism:
    def test_same_seed_identical(self):
        a = generate_dataset(sequences=2, sessions_per_sequence=10, seed=7)
        b = generate_dataset(sequences=2, sessions_per_sequence=10, seed=7)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_different_seed_differs(self):
        a = generate_dataset(sequences=2, sessions_per_sequence=10, seed=7)
        b = generate_dataset(sequences=2, sessions_per_sequence=10, seed=8)
        assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)

    def test_written_file_bytes_stable(self, tmp_path):
        dataset = generate_dataset(sequences=1, sessions_per_sequence=10, seed=3)
        first = write_dataset(dataset, tmp_path / "a.json")
        second = write_dataset(dataset, tmp_path / "b.json")
        assert first.read_text() == second.read_text()

    def test_unsized_sequences_deterministic(self):
        a = generate_dataset(sequences=2, sessions_per_sequence=None, seed=11)
        b = generate_dataset(sequences=2, sessions_per_sequence=None, seed=11)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class TestCategoryCoverage:
    def test_every_category_present_per_case(self, dataset):
        for case in dataset["cases"]:
            categories = {question["category"] for question in case["questions"]}
            assert categories == set(CATEGORIES), case["case_id"]

    def test_questions_per_category_honored(self, dataset):
        for case in dataset["cases"]:
            per_category = {}
            for question in case["questions"]:
                per_category[question["category"]] = per_category.get(question["category"], 0) + 1
            assert all(count == 2 for count in per_category.values()), case["case_id"]

    def test_all_scenarios_cycle(self, dataset):
        scenarios = [case["scenario"] for case in dataset["cases"]]
        assert scenarios == list(SCENARIOS)

    def test_exact_string_questions_present(self, dataset):
        for case in dataset["cases"]:
            tagged = [q for q in case["questions"] if q["exact_strings"]]
            assert tagged, f"{case['case_id']} has no exact-string questions"

    def test_full_preset_reaches_prd_scale(self):
        spec = PRESETS["full"]
        # 50 sequences x 5 categories x 2 questions = 500 (PRD target).
        assert spec["sequences"] * len(CATEGORIES) * spec["questions_per_category"] == 500


class TestEvidenceIntegrity:
    def test_evidence_ids_exist_in_corpus(self, dataset):
        for case in dataset["cases"]:
            session_ids = {session["session_id"] for session in case["sessions"]}
            turn_ids = {
                f"{session['session_id']}:{index}"
                for session in case["sessions"]
                for index in range(len(session["turns"]))
            }
            for question in case["questions"]:
                assert question["evidence_session_ids"], question["question_id"]
                for session_id in question["evidence_session_ids"]:
                    assert session_id in session_ids
                for turn_id in question["evidence_turn_ids"]:
                    assert turn_id in turn_ids

    def test_exact_strings_appear_in_evidence_turns(self, dataset):
        for case in dataset["cases"]:
            texts_by_turn = {
                f"{session['session_id']}:{index}": turn["content"]
                for session in case["sessions"]
                for index, turn in enumerate(session["turns"])
            }
            for question in case["questions"]:
                for exact in question["exact_strings"]:
                    evidence_texts = [
                        texts_by_turn[turn_id] for turn_id in question["evidence_turn_ids"]
                    ]
                    assert any(exact.lower() in text.lower() for text in evidence_texts), (
                        question["question_id"],
                        exact,
                    )

    def test_relationship_provenance_points_at_real_turns(self, dataset):
        for case in dataset["cases"]:
            turn_ids = {
                f"{session['session_id']}:{index}"
                for session in case["sessions"]
                for index in range(len(session["turns"]))
            }
            for rel in case["ground_truth"]["relationships"]:
                assert rel["turn_id"] in turn_ids, rel

    def test_contradictions_use_exclusive_predicates(self, dataset):
        for case in dataset["cases"]:
            contradictions = case["ground_truth"]["contradictions"]
            assert contradictions, case["case_id"]
            for contradiction in contradictions:
                assert contradiction["predicate"] in EXCLUSIVE_PREDICATES
                assert contradiction["old_turn_id"]
                assert contradiction["new_turn_id"]

    def test_log_entries_map_to_session_dates(self, dataset):
        for case in dataset["cases"]:
            dates = {session["session_id"]: session["date"] for session in case["sessions"]}
            for entry in case["ground_truth"]["log_entries"]:
                for session_id in entry["source_session_ids"]:
                    assert dates[session_id] == entry["date"]

    def test_narrative_questions_carry_date_window(self, dataset):
        for case in dataset["cases"]:
            for question in case["questions"]:
                if question["category"] == "narrative_recall":
                    assert question["date_from"] and question["date_to"]
