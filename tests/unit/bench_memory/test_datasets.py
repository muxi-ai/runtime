"""Loader tests, driven by the committed fixture samples.

The fixtures are schema-faithful synthetic samples of each published
dataset; these tests pin the exact normalization the runners rely on
(ids, evidence mapping, abstention flags).
"""

import json
from pathlib import Path

import pytest

from bench.memory.datasets import (
    load_convomem,
    load_dataset,
    load_locomo,
    load_longmemeval,
)

FIXTURES = Path(__file__).resolve().parents[3] / "bench" / "memory" / "fixtures"


@pytest.fixture(scope="module")
def longmemeval_dataset():
    return load_longmemeval(FIXTURES / "longmemeval_sample.json")


@pytest.fixture(scope="module")
def locomo_dataset():
    return load_locomo(FIXTURES / "locomo_sample.json")


@pytest.fixture(scope="module")
def convomem_dataset():
    return load_convomem(FIXTURES / "convomem_sample.json")


class TestLongMemEvalLoader:
    @pytest.fixture
    def dataset(self, longmemeval_dataset):
        return longmemeval_dataset

    def test_one_case_per_instance(self, dataset):
        assert len(dataset.cases) == 6
        assert dataset.question_count == 6

    def test_session_ids_preserved(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_ssu_001")
        assert [s.session_id for s in case.sessions] == [
            "fixture_ssu_001_s1",
            "fixture_ssu_001_s2",
            "fixture_ssu_001_s3",
            "fixture_ssu_001_s4",
        ]

    def test_session_dates_attached(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_ssu_001")
        assert case.sessions[0].date == "2023/04/02 (Sun) 09:12"

    def test_evidence_session_ids(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_ms_001")
        question = case.questions[0]
        assert question.evidence_session_ids == (
            "fixture_ms_001_s1",
            "fixture_ms_001_s3",
        )

    def test_evidence_turns_from_has_answer(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_ms_001")
        question = case.questions[0]
        assert question.evidence_turn_ids == (
            "fixture_ms_001_s1:0",
            "fixture_ms_001_s3:0",
        )

    def test_turn_ids_are_session_scoped_indices(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_ssu_001")
        turns = case.sessions[1].turns
        assert turns[0].turn_id == "fixture_ssu_001_s2:0"
        assert turns[3].turn_id == "fixture_ssu_001_s2:3"

    def test_abstention_flagged_by_id_suffix(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_tr_001_abs")
        assert case.questions[0].is_abstention is True
        assert case.questions[0].evidence_session_ids == ()

    def test_non_abstention_not_flagged(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_ku_001")
        assert case.questions[0].is_abstention is False

    def test_question_type_preserved(self, dataset):
        types = {c.questions[0].question_type for c in dataset.cases}
        assert "knowledge-update" in types
        assert "multi-session" in types

    def test_rejects_non_list(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text('{"not": "a list"}')
        with pytest.raises(ValueError, match="JSON list"):
            load_longmemeval(path)

    def test_rejects_mismatched_haystack(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "question_id": "x",
                        "question": "q",
                        "answer": "a",
                        "haystack_sessions": [[]],
                        "haystack_session_ids": ["s1", "s2"],
                        "answer_session_ids": [],
                    }
                ]
            )
        )
        with pytest.raises(ValueError, match="length mismatch"):
            load_longmemeval(path)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_longmemeval(FIXTURES / "does_not_exist.json")


class TestLoCoMoLoader:
    @pytest.fixture
    def dataset(self, locomo_dataset):
        return locomo_dataset

    def test_one_case_per_sample(self, dataset):
        assert len(dataset.cases) == 1
        assert dataset.cases[0].case_id == "fixture_1"

    def test_sessions_ordered_numerically(self, dataset):
        assert [s.session_id for s in dataset.cases[0].sessions] == [
            "session_1",
            "session_2",
            "session_3",
        ]

    def test_session_dates(self, dataset):
        assert dataset.cases[0].sessions[0].date == "1:15 pm on 8 January, 2023"

    def test_turn_ids_are_dia_ids(self, dataset):
        session_1 = dataset.cases[0].sessions[0]
        assert session_1.turns[0].turn_id == "D1:1"
        assert session_1.turns[3].turn_id == "D1:4"

    def test_speaker_kept_as_role(self, dataset):
        session_1 = dataset.cases[0].sessions[0]
        assert session_1.turns[0].role == "Nadia"
        assert session_1.turns[1].role == "Omar"

    def test_evidence_turn_ids(self, dataset):
        questions = dataset.cases[0].questions
        cat1 = next(q for q in questions if q.question_type == "multi-hop")
        assert cat1.evidence_turn_ids == ("D2:2", "D2:4", "D3:1")

    def test_evidence_session_ids_derived_from_dia_ids(self, dataset):
        questions = dataset.cases[0].questions
        cat1 = next(q for q in questions if q.question_type == "multi-hop")
        assert cat1.evidence_session_ids == ("session_2", "session_3")

    def test_category_names(self, dataset):
        types = {q.question_type for q in dataset.cases[0].questions}
        assert {"single-hop", "multi-hop", "temporal", "adversarial"} <= types

    def test_adversarial_is_abstention_with_adversarial_answer(self, dataset):
        adversarial = next(
            q for q in dataset.cases[0].questions if q.question_type == "adversarial"
        )
        assert adversarial.is_abstention is True
        assert adversarial.answer == "Nadia never mentioned owning a car."

    def test_question_ids_unique(self, dataset):
        ids = [q.question_id for q in dataset.cases[0].questions]
        assert len(ids) == len(set(ids))

    def test_rejects_missing_conversation(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps([{"sample_id": "x", "qa": []}]))
        with pytest.raises(ValueError, match="conversation"):
            load_locomo(path)


class TestConvoMemLoader:
    @pytest.fixture
    def dataset(self, convomem_dataset):
        return convomem_dataset

    def test_one_case_per_evidence_item(self, dataset):
        assert len(dataset.cases) == 3

    def test_evidence_conversation_located_by_text_match(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_user_evidence_1")
        question = case.questions[0]
        assert question.evidence_session_ids == ("conv_1",)
        assert question.evidence_turn_ids == ("conv_1:0",)

    def test_assistant_evidence_matched(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_assistant_evidence_1")
        question = case.questions[0]
        assert question.evidence_session_ids == ("conv_0",)
        assert question.evidence_turn_ids == ("conv_0:1",)

    def test_turns_marked_has_answer(self, dataset):
        case = next(c for c in dataset.cases if c.case_id == "fixture_user_evidence_2")
        evidence_turn = case.sessions[0].turns[0]
        assert evidence_turn.has_answer is True
        assert case.sessions[1].turns[0].has_answer is False

    def test_not_abstention_when_evidence_found(self, dataset):
        assert all(not c.questions[0].is_abstention for c in dataset.cases)

    def test_accepts_category_grouped_object(self, tmp_path):
        raw = json.loads((FIXTURES / "convomem_sample.json").read_text())
        grouped = {"user_evidence": raw[:2], "assistant_evidence": raw[2:]}
        path = tmp_path / "grouped.json"
        path.write_text(json.dumps(grouped))
        dataset = load_convomem(path)
        assert len(dataset.cases) == 3

    def test_rejects_empty(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("[]")
        with pytest.raises(ValueError, match="no evidence items"):
            load_convomem(path)


class TestLoadDatasetDispatch:
    def test_dispatch_by_name(self):
        dataset = load_dataset("locomo", FIXTURES / "locomo_sample.json")
        assert dataset.name == "locomo"

    def test_unknown_benchmark(self):
        with pytest.raises(ValueError, match="Unknown benchmark"):
            load_dataset("nope", FIXTURES / "locomo_sample.json")


class TestDatasetProperties:
    def test_counts(self):
        dataset = load_longmemeval(FIXTURES / "longmemeval_sample.json")
        assert dataset.session_count == sum(len(c.sessions) for c in dataset.cases)
        assert dataset.cases[0].turn_count == sum(len(s.turns) for s in dataset.cases[0].sessions)

    def test_iter_questions_order(self):
        dataset = load_locomo(FIXTURES / "locomo_sample.json")
        pairs = list(dataset.iter_questions())
        assert len(pairs) == dataset.question_count
        assert pairs[0][0].case_id == "fixture_1"
