"""Dataset loaders for the Tier 1 memory benchmarks.

Every benchmark is normalized into the same shape so a single runner
can score all of them:

- ``BenchmarkDataset``  — a named collection of independent cases.
- ``BenchmarkCase``     — one isolated haystack (sessions) plus the
  questions asked against it. Cases never share memory: the runner
  ingests each case under its own user id and clears working memory
  between cases.
- ``Session`` / ``Turn`` — the conversation history, with stable ids
  so retrieval results can be mapped back to evidence.

Loaders are schema-faithful to the published datasets:

- LongMemEval (``longmemeval_s*.json``): one case per question
  instance; each instance carries its own haystack of sessions.
- LoCoMo (``locomo10.json``): one case per sample; all QA pairs in a
  sample share the sample's multi-session conversation.
- ConvoMem (Salesforce/ConvoMem evidence files): one case per
  evidence item; evidence conversations are located by matching the
  ``message_evidences`` texts inside the item's conversations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# LoCoMo question categories, per the paper (snap-research/locomo).
LOCOMO_CATEGORIES = {
    1: "multi-hop",
    2: "temporal",
    3: "open-domain",
    4: "single-hop",
    5: "adversarial",
}


@dataclass(frozen=True)
class Turn:
    """A single conversation turn."""

    turn_id: str
    role: str
    content: str
    has_answer: bool = False


@dataclass(frozen=True)
class Session:
    """A conversation session: an ordered list of turns."""

    session_id: str
    turns: Tuple[Turn, ...]
    date: Optional[str] = None


@dataclass(frozen=True)
class Question:
    """A benchmark question with its ground-truth evidence.

    The trailing optional fields are used by the Tier 2 structured
    recall dataset: ``exact_strings`` (verbatim tokens - emails, codes,
    ids - whose presence in retrieved context is scored separately) and
    ``date_from``/``date_to`` (the date window for narrative questions,
    used by the structured retrieval mode's Captain's-Log lookup).
    Tier 1 loaders leave them at their defaults.
    """

    question_id: str
    question: str
    answer: Optional[str]
    question_type: str
    evidence_session_ids: Tuple[str, ...] = ()
    evidence_turn_ids: Tuple[str, ...] = ()
    question_date: Optional[str] = None
    is_abstention: bool = False
    exact_strings: Tuple[str, ...] = ()
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@dataclass(frozen=True)
class BenchmarkCase:
    """One isolated haystack plus the questions asked against it."""

    case_id: str
    sessions: Tuple[Session, ...]
    questions: Tuple[Question, ...]

    @property
    def turn_count(self) -> int:
        return sum(len(session.turns) for session in self.sessions)


@dataclass(frozen=True)
class BenchmarkDataset:
    """A named collection of independent benchmark cases."""

    name: str
    cases: Tuple[BenchmarkCase, ...] = field(default_factory=tuple)

    @property
    def question_count(self) -> int:
        return sum(len(case.questions) for case in self.cases)

    @property
    def session_count(self) -> int:
        return sum(len(case.sessions) for case in self.cases)

    def iter_questions(self):
        """Yield ``(case, question)`` pairs in dataset order."""
        for case in self.cases:
            for question in case.questions:
                yield case, question


def _read_json(path: Union[str, Path]) -> Any:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


# ---------------------------------------------------------------------------
# LongMemEval
# ---------------------------------------------------------------------------


def load_longmemeval(path: Union[str, Path]) -> BenchmarkDataset:
    """Load a LongMemEval file (``longmemeval_s.json`` or the cleaned variant).

    Each instance becomes one :class:`BenchmarkCase` (per-question
    haystack). Abstention questions (ids ending in ``_abs``) carry no
    evidence sessions and are excluded from retrieval aggregates by
    the scorer.
    """
    data = _read_json(path)
    _require(isinstance(data, list), "LongMemEval file must be a JSON list of instances")

    cases: List[BenchmarkCase] = []
    for idx, instance in enumerate(data):
        _require(isinstance(instance, dict), f"LongMemEval instance {idx} is not an object")
        question_id = str(instance.get("question_id", idx))
        haystack_sessions = instance.get("haystack_sessions")
        haystack_session_ids = instance.get("haystack_session_ids")
        _require(
            isinstance(haystack_sessions, list) and isinstance(haystack_session_ids, list),
            f"LongMemEval instance {question_id}: missing haystack sessions/ids",
        )
        _require(
            len(haystack_sessions) == len(haystack_session_ids),
            f"LongMemEval instance {question_id}: haystack sessions/ids length mismatch",
        )
        haystack_dates = instance.get("haystack_dates") or [None] * len(haystack_sessions)

        sessions: List[Session] = []
        evidence_turn_ids: List[str] = []
        answer_session_ids = {str(sid) for sid in (instance.get("answer_session_ids") or [])}
        for session_id, session_turns, date in zip(
            haystack_session_ids, haystack_sessions, haystack_dates
        ):
            session_id = str(session_id)
            turns: List[Turn] = []
            for turn_idx, raw_turn in enumerate(session_turns or []):
                turn_id = f"{session_id}:{turn_idx}"
                has_answer = bool(raw_turn.get("has_answer", False))
                if has_answer:
                    evidence_turn_ids.append(turn_id)
                turns.append(
                    Turn(
                        turn_id=turn_id,
                        role=str(raw_turn.get("role", "user")),
                        content=str(raw_turn.get("content", "")),
                        has_answer=has_answer,
                    )
                )
            sessions.append(
                Session(
                    session_id=session_id,
                    turns=tuple(turns),
                    date=str(date) if date is not None else None,
                )
            )

        is_abstention = question_id.endswith("_abs") or not answer_session_ids
        question = Question(
            question_id=question_id,
            question=str(instance.get("question", "")),
            answer=(str(instance["answer"]) if instance.get("answer") is not None else None),
            question_type=str(instance.get("question_type", "unknown")),
            evidence_session_ids=tuple(sorted(answer_session_ids)),
            evidence_turn_ids=tuple(evidence_turn_ids),
            question_date=(
                str(instance["question_date"]) if instance.get("question_date") else None
            ),
            is_abstention=is_abstention,
        )
        cases.append(
            BenchmarkCase(
                case_id=question_id,
                sessions=tuple(sessions),
                questions=(question,),
            )
        )

    return BenchmarkDataset(name="longmemeval", cases=tuple(cases))


# ---------------------------------------------------------------------------
# LoCoMo
# ---------------------------------------------------------------------------


def _locomo_session_id_from_dia(dia_id: str) -> Optional[str]:
    """Map a LoCoMo dialog id (``D1:3``) to its session id (``session_1``)."""
    dia_id = str(dia_id).strip()
    if not dia_id.startswith("D"):
        return None
    head = dia_id[1:].split(":", 1)[0]
    if not head.isdigit():
        return None
    return f"session_{head}"


def load_locomo(path: Union[str, Path]) -> BenchmarkDataset:
    """Load a LoCoMo file (``locomo10.json``).

    One case per sample. Evidence is turn-level (dialog ids like
    ``D1:3``); session-level evidence is derived from the dialog ids.
    Adversarial questions (category 5) are unanswerable by design and
    marked as abstention questions.
    """
    data = _read_json(path)
    _require(isinstance(data, list), "LoCoMo file must be a JSON list of samples")

    cases: List[BenchmarkCase] = []
    for idx, sample in enumerate(data):
        _require(isinstance(sample, dict), f"LoCoMo sample {idx} is not an object")
        sample_id = str(sample.get("sample_id", idx))
        conversation = sample.get("conversation")
        _require(
            isinstance(conversation, dict),
            f"LoCoMo sample {sample_id}: missing conversation object",
        )

        sessions: List[Session] = []
        session_numbers = []
        for key in conversation:
            if key.startswith("session_") and not key.endswith("_date_time"):
                suffix = key.removeprefix("session_")
                if suffix.isdigit() and isinstance(conversation[key], list):
                    session_numbers.append(int(suffix))
        for number in sorted(session_numbers):
            key = f"session_{number}"
            date = conversation.get(f"{key}_date_time")
            turns: List[Turn] = []
            for turn_idx, raw_turn in enumerate(conversation[key]):
                dia_id = str(raw_turn.get("dia_id", f"D{number}:{turn_idx}"))
                speaker = str(raw_turn.get("speaker", "speaker"))
                text = str(raw_turn.get("text", ""))
                turns.append(
                    Turn(
                        turn_id=dia_id,
                        role=speaker,
                        content=text,
                    )
                )
            sessions.append(
                Session(
                    session_id=key,
                    turns=tuple(turns),
                    date=str(date) if date is not None else None,
                )
            )

        questions: List[Question] = []
        for q_idx, qa in enumerate(sample.get("qa") or []):
            category = qa.get("category")
            category_name = LOCOMO_CATEGORIES.get(category, str(category))
            evidence_dia_ids = [str(e) for e in (qa.get("evidence") or [])]
            evidence_session_ids = sorted(
                {
                    session_id
                    for session_id in (
                        _locomo_session_id_from_dia(dia_id) for dia_id in evidence_dia_ids
                    )
                    if session_id is not None
                }
            )
            answer = qa.get("answer")
            if answer is None:
                answer = qa.get("adversarial_answer")
            is_adversarial = category_name == "adversarial"
            questions.append(
                Question(
                    question_id=f"{sample_id}:q{q_idx}",
                    question=str(qa.get("question", "")),
                    answer=(str(answer) if answer is not None else None),
                    question_type=category_name,
                    evidence_session_ids=tuple(evidence_session_ids),
                    evidence_turn_ids=tuple(evidence_dia_ids),
                    is_abstention=is_adversarial or not evidence_dia_ids,
                )
            )

        cases.append(
            BenchmarkCase(
                case_id=sample_id,
                sessions=tuple(sessions),
                questions=tuple(questions),
            )
        )

    return BenchmarkDataset(name="locomo", cases=tuple(cases))


# ---------------------------------------------------------------------------
# ConvoMem
# ---------------------------------------------------------------------------


def _convomem_items(data: Any) -> List[Dict[str, Any]]:
    """Normalize a ConvoMem file into a flat list of evidence items.

    Accepts either a bare list of evidence items or an object whose
    values are lists of evidence items (the published dataset groups
    items by evidence category).
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items: List[Dict[str, Any]] = []
        for value in data.values():
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        return items
    raise ValueError("ConvoMem file must be a JSON list or an object of lists")


def load_convomem(path: Union[str, Path]) -> BenchmarkDataset:
    """Load a ConvoMem evidence file (Salesforce/ConvoMem).

    One case per evidence item. Evidence conversations/messages are
    located by exact text match of ``message_evidences`` entries
    inside the item's conversations.
    """
    data = _read_json(path)
    items = _convomem_items(data)
    _require(bool(items), "ConvoMem file contains no evidence items")

    cases: List[BenchmarkCase] = []
    for item_idx, item in enumerate(items):
        case_id = str(item.get("id", item_idx))
        conversations = item.get("conversations")
        _require(
            isinstance(conversations, list) and conversations,
            f"ConvoMem item {case_id}: missing conversations",
        )
        evidences = item.get("message_evidences") or []
        evidence_keys = {
            (str(ev.get("speaker", "")).lower(), str(ev.get("text", "")))
            for ev in evidences
            if isinstance(ev, dict)
        }

        sessions: List[Session] = []
        evidence_session_ids: List[str] = []
        evidence_turn_ids: List[str] = []
        for conv_idx, conversation in enumerate(conversations):
            session_id = f"conv_{conv_idx}"
            messages = conversation.get("messages", []) if isinstance(conversation, dict) else []
            turns: List[Turn] = []
            session_has_evidence = False
            for msg_idx, message in enumerate(messages):
                if not isinstance(message, dict):
                    continue
                speaker = str(message.get("speaker", "user"))
                text = str(message.get("text", ""))
                turn_id = f"{session_id}:{msg_idx}"
                has_answer = (speaker.lower(), text) in evidence_keys
                if has_answer:
                    session_has_evidence = True
                    evidence_turn_ids.append(turn_id)
                turns.append(
                    Turn(
                        turn_id=turn_id,
                        role=speaker,
                        content=text,
                        has_answer=has_answer,
                    )
                )
            if session_has_evidence:
                evidence_session_ids.append(session_id)
            sessions.append(Session(session_id=session_id, turns=tuple(turns)))

        question = Question(
            question_id=case_id,
            question=str(item.get("question", "")),
            answer=(str(item["answer"]) if item.get("answer") is not None else None),
            question_type=str(item.get("category", "convomem")),
            evidence_session_ids=tuple(evidence_session_ids),
            evidence_turn_ids=tuple(evidence_turn_ids),
            is_abstention=not evidence_turn_ids,
        )
        cases.append(
            BenchmarkCase(
                case_id=case_id,
                sessions=tuple(sessions),
                questions=(question,),
            )
        )

    return BenchmarkDataset(name="convomem", cases=tuple(cases))


LOADERS = {
    "longmemeval": load_longmemeval,
    "locomo": load_locomo,
    "convomem": load_convomem,
}


def load_dataset(benchmark: str, path: Union[str, Path]) -> BenchmarkDataset:
    """Load ``path`` with the loader registered for ``benchmark``."""
    loader = LOADERS.get(benchmark)
    if loader is None:
        raise ValueError(f"Unknown benchmark: {benchmark} (expected one of {sorted(LOADERS)})")
    return loader(path)
