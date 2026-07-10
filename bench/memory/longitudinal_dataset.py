"""Loader for the Tier 3 longitudinal dataset.

The dataset file is produced by :mod:`bench.memory.longitudinal_corpus`
(committed fixture sample or a full generated run). Loading yields one
:class:`LongitudinalScenario` per PRD scenario:

- A :class:`~bench.memory.datasets.BenchmarkDataset` in the exact
  Tier 1/2 shape (cases -> sessions -> turns, questions with evidence
  ids), so the shared adapter/scoring/report machinery applies
  unchanged. Question categories map onto ``question_type``.
- A :class:`LongitudinalGroundTruth` per case: the Tier 2 manifest
  (entities, relationships with per-fact confidence and turn-level
  provenance, Captain's-Log entries, contradictions) plus the Tier 3
  extras — decisions (zero-lost-decisions audit), artifacts
  (zero-orphan audit), canaries (isolation leak detection),
  ``question_meta`` (asking/evidence agent pairs), and expected
  contradiction detection kinds.
- The scenario's generator ``config`` (isolation user count, target
  retrieval-op count, corpus spans) for the runner.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from .datasets import BenchmarkCase, BenchmarkDataset, Question, Session, Turn
from .longitudinal_corpus import CATEGORIES, DATASET_NAME, SCENARIOS

BENCHMARK_NAME = "longitudinal"


@dataclass(frozen=True)
class LongitudinalGroundTruth:
    """Per-case manifest consumed by the longitudinal runner."""

    case_id: str
    scenario: str
    entities: Tuple[Dict[str, Any], ...] = ()
    relationships: Tuple[Dict[str, Any], ...] = ()
    log_entries: Tuple[Dict[str, Any], ...] = ()
    contradictions: Tuple[Dict[str, Any], ...] = ()
    distractors: Tuple[Dict[str, Any], ...] = ()
    decisions: Tuple[Dict[str, Any], ...] = ()
    artifacts: Tuple[Dict[str, Any], ...] = ()
    canaries: Tuple[str, ...] = ()
    question_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # session_id -> date, for mapping log entries back to sessions.
    session_dates: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LongitudinalScenario:
    """One PRD scenario: dataset + ground truth + generator config."""

    key: str
    config: Dict[str, Any]
    dataset: BenchmarkDataset
    ground_truth: Dict[str, LongitudinalGroundTruth]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_case(raw_case: Dict[str, Any]) -> Tuple[BenchmarkCase, LongitudinalGroundTruth]:
    case_id = str(raw_case["case_id"])

    sessions: List[Session] = []
    session_dates: Dict[str, str] = {}
    for raw_session in raw_case.get("sessions") or []:
        session_id = str(raw_session["session_id"])
        session_date = raw_session.get("date")
        if session_date:
            session_dates[session_id] = str(session_date)
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
                date=str(session_date) if session_date is not None else None,
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
                    str(raw_question["answer"]) if raw_question.get("answer") is not None else None
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
    truth = LongitudinalGroundTruth(
        case_id=case_id,
        scenario=str(raw_case.get("scenario", "unknown")),
        entities=tuple(raw_truth.get("entities") or ()),
        relationships=tuple(raw_truth.get("relationships") or ()),
        log_entries=tuple(raw_truth.get("log_entries") or ()),
        contradictions=tuple(raw_truth.get("contradictions") or ()),
        distractors=tuple(raw_truth.get("distractors") or ()),
        decisions=tuple(raw_truth.get("decisions") or ()),
        artifacts=tuple(raw_truth.get("artifacts") or ()),
        canaries=tuple(str(c) for c in (raw_truth.get("canaries") or ())),
        question_meta=dict(raw_truth.get("question_meta") or {}),
        session_dates=session_dates,
    )
    case = BenchmarkCase(
        case_id=case_id,
        sessions=tuple(sessions),
        questions=tuple(questions),
    )
    return case, truth


def load_longitudinal(path: Union[str, Path]) -> Dict[str, LongitudinalScenario]:
    """Load a longitudinal dataset file.

    Returns ``{scenario_key: LongitudinalScenario}`` for every scenario
    present in the file (all four for generator output).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    _require(isinstance(data, dict), "Longitudinal dataset file must be a JSON object")
    _require(
        data.get("name") == DATASET_NAME,
        f"Unexpected dataset name: {data.get('name')!r} (expected {DATASET_NAME!r})",
    )
    raw_scenarios = data.get("scenarios")
    _require(
        isinstance(raw_scenarios, dict) and bool(raw_scenarios),
        "Dataset contains no scenarios",
    )

    scenarios: Dict[str, LongitudinalScenario] = {}
    for key, raw_scenario in raw_scenarios.items():
        _require(key in SCENARIOS, f"Unknown scenario {key!r} (expected one of {SCENARIOS})")
        raw_cases = raw_scenario.get("cases")
        _require(
            isinstance(raw_cases, list) and bool(raw_cases),
            f"Scenario {key!r} contains no cases",
        )
        cases: List[BenchmarkCase] = []
        ground_truth: Dict[str, LongitudinalGroundTruth] = {}
        for raw_case in raw_cases:
            case, truth = _load_case(raw_case)
            cases.append(case)
            ground_truth[case.case_id] = truth
        scenarios[key] = LongitudinalScenario(
            key=key,
            config=dict(raw_scenario.get("config") or {}),
            dataset=BenchmarkDataset(name=f"{BENCHMARK_NAME}_{key}", cases=tuple(cases)),
            ground_truth=ground_truth,
        )
    return scenarios
