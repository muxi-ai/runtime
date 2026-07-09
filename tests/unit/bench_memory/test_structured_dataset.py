"""Structured-recall dataset loader tests."""

import json
from pathlib import Path

import pytest

from bench.memory.structured_corpus import CATEGORIES, generate_dataset, write_dataset
from bench.memory.structured_dataset import load_structured_recall

FIXTURE = Path(__file__).resolve().parents[3] / (
    "bench/memory/fixtures/structured_recall_sample.json"
)


class TestLoadFixture:
    def test_committed_fixture_loads(self):
        dataset, ground_truth = load_structured_recall(FIXTURE)
        assert dataset.name == "structured_recall"
        assert len(dataset.cases) == 3
        assert dataset.question_count == 30
        assert set(ground_truth) == {case.case_id for case in dataset.cases}

    def test_fixture_covers_all_categories(self):
        dataset, _ = load_structured_recall(FIXTURE)
        categories = {question.question_type for _, question in dataset.iter_questions()}
        assert categories == set(CATEGORIES)

    def test_questions_carry_structured_fields(self):
        dataset, _ = load_structured_recall(FIXTURE)
        questions = [question for _, question in dataset.iter_questions()]
        assert any(question.exact_strings for question in questions)
        assert any(question.date_from for question in questions)
        assert all(question.evidence_session_ids for question in questions)

    def test_ground_truth_manifest_populated(self):
        _, ground_truth = load_structured_recall(FIXTURE)
        for truth in ground_truth.values():
            assert truth.entities
            assert truth.relationships
            assert truth.log_entries
            assert truth.contradictions
            assert truth.session_dates

    def test_turn_ids_align_with_sessions(self):
        dataset, _ = load_structured_recall(FIXTURE)
        for case in dataset.cases:
            for session in case.sessions:
                for index, turn in enumerate(session.turns):
                    assert turn.turn_id == f"{session.session_id}:{index}"


class TestRoundTrip:
    def test_generated_dataset_round_trips(self, tmp_path):
        generated = generate_dataset(sequences=2, sessions_per_sequence=10, seed=5)
        path = write_dataset(generated, tmp_path / "ds.json")
        dataset, ground_truth = load_structured_recall(path)
        assert len(dataset.cases) == 2
        assert dataset.question_count == sum(len(case["questions"]) for case in generated["cases"])
        for raw_case in generated["cases"]:
            truth = ground_truth[raw_case["case_id"]]
            assert len(truth.relationships) == len(raw_case["ground_truth"]["relationships"])


class TestValidation:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_structured_recall(tmp_path / "nope.json")

    def test_wrong_dataset_name_rejected(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"name": "other", "cases": [{}]}))
        with pytest.raises(ValueError, match="Unexpected dataset name"):
            load_structured_recall(path)

    def test_empty_cases_rejected(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"name": "muxi-structured-recall", "cases": []}))
        with pytest.raises(ValueError, match="no cases"):
            load_structured_recall(path)

    def test_unknown_category_rejected(self, tmp_path):
        generated = generate_dataset(sequences=1, sessions_per_sequence=10, seed=5)
        generated["cases"][0]["questions"][0]["category"] = "made_up"
        path = write_dataset(generated, tmp_path / "bad_cat.json")
        with pytest.raises(ValueError, match="unknown category"):
            load_structured_recall(path)
