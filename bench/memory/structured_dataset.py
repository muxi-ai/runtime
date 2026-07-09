"""Loader for the Tier 2 structured-recall dataset.

The dataset file is produced by :mod:`bench.memory.structured_corpus`
(committed fixture sample or a full generated run). Loading yields two
things:

- A :class:`~bench.memory.datasets.BenchmarkDataset` in the exact
  Tier 1 shape (cases -> sessions -> turns, questions with evidence
  ids), so the shared adapter/scoring/report machinery applies
  unchanged. Question categories map onto ``question_type``.
- A :class:`StructuredGroundTruth` per case: the manifest of
  entities, relationships (with turn-level provenance), Captain's-Log
  entries, and injected contradictions that the ``structured``
  retrieval mode ingests into the real KG + Captain's-Log services.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from .datasets import BenchmarkCase, BenchmarkDataset, Question, Session, Turn
from .structured_corpus import CATEGORIES, DATASET_NAME

BENCHMARK_NAME = "structured_recall"


@dataclass(frozen=True)
class StructuredGroundTruth:
    """The per-case manifest consumed by the structured retrieval mode."""

    case_id: str
    scenario: str
    entities: Tuple[Dict[str, Any], ...] = ()
    relationships: Tuple[Dict[str, Any], ...] = ()
    log_entries: Tuple[Dict[str, Any], ...] = ()
    contradictions: Tuple[Dict[str, Any], ...] = ()
    # session_id -> date, for mapping log entries back to sessions.
    session_dates: Dict[str, str] = field(default_factory=dict)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_structured_recall(
    path: Union[str, Path],
) -> Tuple[BenchmarkDataset, Dict[str, StructuredGroundTruth]]:
    """Load a structured-recall dataset file.

    Returns ``(dataset, ground_truth_by_case_id)``.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    _require(isinstance(data, dict), "Structured recall file must be a JSON object")
    _require(
        data.get("name") == DATASET_NAME,
        f"Unexpected dataset name: {data.get('name')!r} (expected {DATASET_NAME!r})",
    )
    raw_cases = data.get("cases")
    _require(isinstance(raw_cases, list) and bool(raw_cases), "Dataset contains no cases")

    cases: List[BenchmarkCase] = []
    ground_truth: Dict[str, StructuredGroundTruth] = {}
    for raw_case in raw_cases:
        case_id = str(raw_case["case_id"])

        sessions: List[Session] = []
        session_dates: Dict[str, str] = {}
        for raw_session in raw_case.get("sessions") or []:
            session_id = str(raw_session["session_id"])
            date = raw_session.get("date")
            if date:
                session_dates[session_id] = str(date)
            turns = tuple(
                Turn(
                    turn_id=f"{session_id}:{turn_index}",
                    role=str(raw_turn.get("role", "user")),
                    content=str(raw_turn.get("content", "")),
                )
                for turn_index, raw_turn in enumerate(raw_session.get("turns") or [])
            )
            sessions.append(
                Session(
                    session_id=session_id,
                    turns=turns,
                    date=str(date) if date is not None else None,
                )
            )

        questions: List[Question] = []
        for raw_question in raw_case.get("questions") or []:
            category = str(raw_question.get("category", "unknown"))
            _require(
                category in CATEGORIES,
                f"Question {raw_question.get('question_id')}: unknown category {category!r}",
            )
            questions.append(
                Question(
                    question_id=str(raw_question["question_id"]),
                    question=str(raw_question.get("question", "")),
                    answer=(
                        str(raw_question["answer"])
                        if raw_question.get("answer") is not None
                        else None
                    ),
                    question_type=category,
                    evidence_session_ids=tuple(
                        str(s) for s in (raw_question.get("evidence_session_ids") or [])
                    ),
                    evidence_turn_ids=tuple(
                        str(t) for t in (raw_question.get("evidence_turn_ids") or [])
                    ),
                    exact_strings=tuple(str(s) for s in (raw_question.get("exact_strings") or [])),
                    date_from=(
                        str(raw_question["date_from"]) if raw_question.get("date_from") else None
                    ),
                    date_to=(str(raw_question["date_to"]) if raw_question.get("date_to") else None),
                )
            )

        raw_truth = raw_case.get("ground_truth") or {}
        ground_truth[case_id] = StructuredGroundTruth(
            case_id=case_id,
            scenario=str(raw_case.get("scenario", "unknown")),
            entities=tuple(raw_truth.get("entities") or ()),
            relationships=tuple(raw_truth.get("relationships") or ()),
            log_entries=tuple(raw_truth.get("log_entries") or ()),
            contradictions=tuple(raw_truth.get("contradictions") or ()),
            session_dates=session_dates,
        )
        cases.append(
            BenchmarkCase(
                case_id=case_id,
                sessions=tuple(sessions),
                questions=tuple(questions),
            )
        )

    return BenchmarkDataset(name=BENCHMARK_NAME, cases=tuple(cases)), ground_truth
