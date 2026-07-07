"""Deterministic dev/holdout split for the memory benchmarks.

The PRD calls for a 50-question dev split (for tuning) and a held-out
remainder (for published numbers) so configuration changes are never
overfit to the full question set. The split is seeded and stable:
questions are keyed by ``(case_id, question_id)``, sorted, then
shuffled with ``random.Random(seed)``.
"""

from __future__ import annotations

import random
from typing import List, Tuple

from .datasets import BenchmarkCase, BenchmarkDataset

DEFAULT_DEV_SIZE = 50
DEFAULT_SEED = 42


def split_question_keys(
    dataset: BenchmarkDataset, dev_size: int = DEFAULT_DEV_SIZE, seed: int = DEFAULT_SEED
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Return ``(dev_keys, holdout_keys)`` of ``(case_id, question_id)``.

    Deterministic for a given ``(dataset, dev_size, seed)``. When the
    dataset holds fewer questions than ``dev_size``, every question
    lands in the dev split and the holdout is empty.
    """
    if dev_size < 0:
        raise ValueError(f"dev_size must be >= 0, got {dev_size}")
    keys = sorted(
        (case.case_id, question.question_id) for case, question in dataset.iter_questions()
    )
    rng = random.Random(seed)
    rng.shuffle(keys)
    return keys[:dev_size], keys[dev_size:]


def _filter_dataset(dataset: BenchmarkDataset, keys: set) -> BenchmarkDataset:
    cases: List[BenchmarkCase] = []
    for case in dataset.cases:
        questions = tuple(
            question for question in case.questions if (case.case_id, question.question_id) in keys
        )
        if questions:
            cases.append(
                BenchmarkCase(case_id=case.case_id, sessions=case.sessions, questions=questions)
            )
    return BenchmarkDataset(name=dataset.name, cases=tuple(cases))


def split_dataset(
    dataset: BenchmarkDataset, dev_size: int = DEFAULT_DEV_SIZE, seed: int = DEFAULT_SEED
) -> Tuple[BenchmarkDataset, BenchmarkDataset]:
    """Split ``dataset`` into ``(dev, holdout)`` datasets.

    Cases whose questions land entirely in the other split are dropped
    from a split, so each split only ingests the haystacks it needs.
    """
    dev_keys, holdout_keys = split_question_keys(dataset, dev_size=dev_size, seed=seed)
    return (
        _filter_dataset(dataset, set(dev_keys)),
        _filter_dataset(dataset, set(holdout_keys)),
    )


def select_split(
    dataset: BenchmarkDataset,
    split: str,
    dev_size: int = DEFAULT_DEV_SIZE,
    seed: int = DEFAULT_SEED,
) -> BenchmarkDataset:
    """Return the requested split: ``dev``, ``holdout``, or ``all``."""
    if split == "all":
        return dataset
    dev, holdout = split_dataset(dataset, dev_size=dev_size, seed=seed)
    if split == "dev":
        return dev
    if split == "holdout":
        return holdout
    raise ValueError(f"Unknown split: {split} (expected dev, holdout, or all)")
