"""Determinism and correctness tests for the dev/holdout split."""

from pathlib import Path

import pytest

from bench.memory.datasets import load_locomo, load_longmemeval
from bench.memory.split import select_split, split_dataset, split_question_keys

FIXTURES = Path(__file__).resolve().parents[3] / "bench" / "memory" / "fixtures"


@pytest.fixture(scope="module")
def longmemeval():
    return load_longmemeval(FIXTURES / "longmemeval_sample.json")


@pytest.fixture(scope="module")
def locomo():
    return load_locomo(FIXTURES / "locomo_sample.json")


class TestSplitQuestionKeys:
    def test_deterministic_for_same_seed(self, longmemeval):
        first = split_question_keys(longmemeval, dev_size=3, seed=42)
        second = split_question_keys(longmemeval, dev_size=3, seed=42)
        assert first == second

    def test_different_seed_changes_assignment(self, longmemeval):
        dev_a, _ = split_question_keys(longmemeval, dev_size=3, seed=1)
        dev_b, _ = split_question_keys(longmemeval, dev_size=3, seed=2)
        assert dev_a != dev_b

    def test_partition_is_complete_and_disjoint(self, longmemeval):
        dev, holdout = split_question_keys(longmemeval, dev_size=3, seed=42)
        assert len(dev) == 3
        assert len(dev) + len(holdout) == longmemeval.question_count
        assert not set(dev) & set(holdout)

    def test_dev_size_larger_than_dataset(self, longmemeval):
        dev, holdout = split_question_keys(longmemeval, dev_size=100, seed=42)
        assert len(dev) == longmemeval.question_count
        assert holdout == []

    def test_negative_dev_size_rejected(self, longmemeval):
        with pytest.raises(ValueError):
            split_question_keys(longmemeval, dev_size=-1)


class TestSplitDataset:
    def test_questions_partitioned(self, longmemeval):
        dev, holdout = split_dataset(longmemeval, dev_size=2, seed=42)
        assert dev.question_count == 2
        assert holdout.question_count == longmemeval.question_count - 2

    def test_cases_without_questions_dropped(self, longmemeval):
        # LongMemEval has one question per case, so the dev split must
        # contain exactly dev_size cases.
        dev, _ = split_dataset(longmemeval, dev_size=2, seed=42)
        assert len(dev.cases) == 2

    def test_shared_case_kept_in_both_splits(self, locomo):
        # LoCoMo has one case with many questions; both splits keep the
        # case (with its full haystack) but different question subsets.
        dev, holdout = split_dataset(locomo, dev_size=2, seed=42)
        assert len(dev.cases) == 1
        assert len(holdout.cases) == 1
        assert dev.cases[0].sessions == holdout.cases[0].sessions
        dev_ids = {q.question_id for q in dev.cases[0].questions}
        holdout_ids = {q.question_id for q in holdout.cases[0].questions}
        assert not dev_ids & holdout_ids

    def test_sessions_preserved_in_split(self, longmemeval):
        dev, _ = split_dataset(longmemeval, dev_size=2, seed=42)
        original = {case.case_id: case for case in longmemeval.cases}
        for case in dev.cases:
            assert case.sessions == original[case.case_id].sessions


class TestSelectSplit:
    def test_all_returns_original(self, longmemeval):
        assert select_split(longmemeval, "all") is longmemeval

    def test_dev_and_holdout_partition(self, longmemeval):
        dev = select_split(longmemeval, "dev", dev_size=3, seed=42)
        holdout = select_split(longmemeval, "holdout", dev_size=3, seed=42)
        assert dev.question_count == 3
        assert dev.question_count + holdout.question_count == longmemeval.question_count

    def test_unknown_split_rejected(self, longmemeval):
        with pytest.raises(ValueError, match="Unknown split"):
            select_split(longmemeval, "test")
