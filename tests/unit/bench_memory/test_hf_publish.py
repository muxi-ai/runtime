"""HuggingFace publication rendering tests."""

import pytest

from bench.memory.hf_publish import flatten_questions, flatten_sessions, render
from bench.memory.structured_corpus import generate_dataset, write_dataset


def _dataset_path(tmp_path, mutate=None):
    dataset = generate_dataset(sequences=1, sessions_per_sequence=10, seed=5)
    if mutate:
        mutate(dataset)
    return write_dataset(dataset, tmp_path / "ds.json")


class TestRender:
    def test_renders_card_and_data_files(self, tmp_path):
        output = render(_dataset_path(tmp_path), tmp_path / "hf")
        assert (output / "README.md").exists()
        assert (output / "structured_recall.json").exists()
        assert (output / "data" / "sessions.jsonl").exists()
        assert (output / "data" / "questions.jsonl").exists()
        card = (output / "README.md").read_text()
        assert "license: mit" in card

    def test_rejects_wrong_dataset_name(self, tmp_path):
        def mutate(dataset):
            dataset["name"] = "other"

        with pytest.raises(ValueError, match="Not a structured-recall dataset"):
            render(_dataset_path(tmp_path, mutate), tmp_path / "hf")

    def test_rejects_schema_version_mismatch(self, tmp_path):
        def mutate(dataset):
            dataset["schema_version"] = "0.9"

        with pytest.raises(ValueError, match="schema_version"):
            render(_dataset_path(tmp_path, mutate), tmp_path / "hf")

    def test_rejects_category_set_mismatch(self, tmp_path):
        def mutate(dataset):
            dataset["generator"]["categories"] = ["kg_relationship"]

        with pytest.raises(ValueError, match="categories do not match"):
            render(_dataset_path(tmp_path, mutate), tmp_path / "hf")


class TestFlattening:
    def test_flat_rows_carry_case_id(self, tmp_path):
        dataset = generate_dataset(sequences=2, sessions_per_sequence=10, seed=5)
        sessions = flatten_sessions(dataset)
        questions = flatten_questions(dataset)
        assert len(sessions) == sum(len(case["sessions"]) for case in dataset["cases"])
        assert len(questions) == sum(len(case["questions"]) for case in dataset["cases"])
        case_ids = {case["case_id"] for case in dataset["cases"]}
        assert {row["case_id"] for row in sessions} == case_ids
        assert {row["case_id"] for row in questions} == case_ids
