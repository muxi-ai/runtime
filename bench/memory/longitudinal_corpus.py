"""Longitudinal corpus generator for Tier 3 (Multi-Session Longitudinal).

The Tier 3 benchmark simulates 30-90 days of realistic usage across
multiple users and agents (memory-benchmarking PRD, Tier 3). This is
the PRD's "MemBench Generator": seeded and fully deterministic, no
LLM calls — the same (seed, preset) inputs produce byte-identical
dataset files. It extends the Tier 2 generator's dated, agent-
attributed session skeleton (``structured_corpus.py``) to longitudinal
multi-session corpora, one per PRD scenario:

- ``buffer_cycle`` (Scenario A) — one user, a conversation-heavy
  workload whose turns overflow a small working-memory budget. Facts
  and decisions are concentrated in the first days ("day 1-5") and
  questioned at the end of the window ("day 30"), after their source
  turns have been FIFO-evicted. A ``recent_recall`` control group
  (facts from the last days, still buffer-resident) separates
  "the persisted layers compensate" from "retrieval is broken".
- ``cross_agent`` (Scenario B) — one user, four agents (research,
  finance, marketing, engineering per the PRD). Each agent produces
  artifacts and KG facts in its own sessions; every question is asked
  "via" a different agent than the one whose session carries the
  evidence (``question_meta`` records the pair). The artifact manifest
  backs the zero-orphan audit.
- ``isolation`` (Scenario C) — N users, 7 days each, one case per
  user. Every user's facts follow IDENTICAL templates (same fact
  wording, same probe questions) differing only in values, so if
  isolation ever broke, another user's turn would be the nearest
  neighbor. Each user carries unique ``CANARY-{user}-...`` tokens;
  a canary from user A in user B's retrieval is an unambiguous leak.
- ``contradiction`` (Scenario D) — one user, contradictions injected
  across sessions with day gaps: conflicted pairs (confidence delta
  within SUPERSEDE_CONFIDENCE_DELTA, expect ``conflicted``),
  supersession pairs (delta above it, expect ``superseded``), plus
  precision distractors (duplicate re-assertions and non-exclusive
  predicate changes that must NOT be flagged). Relationships carry
  per-fact confidence and turn provenance so the runner can replay
  them per-session, in corpus order, through the real
  ``store_extraction`` write path (which records the substrate's
  ``fact.contradicted`` events from the event-substrate PRD).

CLI
---
::

    # Regenerate the committed CI fixture
    uv run python -m bench.memory.longitudinal_corpus --preset fixture \
        --output bench/memory/fixtures/longitudinal_sample.json

    # Full dataset (PRD scale: 30-day corpora, 100 isolation users,
    # 10,000 isolation retrieval ops)
    uv run python -m bench.memory.longitudinal_corpus --preset full \
        --output ~/datasets/membench/longitudinal_full.json
"""

from __future__ import annotations

import argparse
import random
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .structured_corpus import (
    CITIES,
    COMPANIES,
    DISTRACTOR_EXCHANGES,
    FIRST_NAMES,
    LAST_NAMES,
    ROLES,
    TECHNOLOGIES,
    GTEntity,
    GTLogEntry,
    GTQuestion,
    GTRelationship,
    _code,
    _email_for,
    _iso,
    write_dataset,
)

DATASET_NAME = "muxi-longitudinal"
DATASET_SCHEMA_VERSION = "1.0"

DEFAULT_SEED = 42

# The four PRD Tier 3 scenarios.
SCENARIO_BUFFER_CYCLE = "buffer_cycle"
SCENARIO_CROSS_AGENT = "cross_agent"
SCENARIO_ISOLATION = "isolation"
SCENARIO_CONTRADICTION = "contradiction"
SCENARIOS = (
    SCENARIO_BUFFER_CYCLE,
    SCENARIO_CROSS_AGENT,
    SCENARIO_ISOLATION,
    SCENARIO_CONTRADICTION,
)

# Question categories (mapped onto question_type by the loader).
CATEGORY_EVICTED = "evicted_recall"
CATEGORY_RECENT = "recent_recall"
CATEGORY_PROPAGATION = "cross_agent_propagation"
CATEGORY_ISOLATION_PROBE = "isolation_probe"
CATEGORIES = (
    CATEGORY_EVICTED,
    CATEGORY_RECENT,
    CATEGORY_PROPAGATION,
    CATEGORY_ISOLATION_PROBE,
)

# The PRD's Scenario A window: questions target facts from days 1-5,
# asked after the full span has been ingested ("at day 30").
EARLY_WINDOW_DAYS = 5

# Contradiction-detection confidences (graph/models.py:
# SUPERSEDE_CONFIDENCE_DELTA = 0.3 — a delta above it supersedes, at
# or below it both facts are flagged conflicted).
CONFLICTED_OLD_CONFIDENCE = 0.6
CONFLICTED_NEW_CONFIDENCE = 0.6
SUPERSEDED_OLD_CONFIDENCE = 0.55
SUPERSEDED_NEW_CONFIDENCE = 0.95
DEFAULT_FACT_CONFIDENCE = 0.85

# Scenario B agents, per the PRD ("research, finance, marketing,
# engineering").
CROSS_AGENT_AGENTS = (
    "research-agent",
    "finance-agent",
    "marketing-agent",
    "engineering-agent",
)

# Artifact pool for Scenario B: one per (set, agent); names stay unique
# so the zero-orphan audit can key on them. 3 sets x 4 agents = 12.
CROSS_AGENT_ARTIFACTS = (
    "market sizing memo",
    "Q3 revenue forecast",
    "campaign performance report",
    "load test report",
    "competitor teardown",
    "budget variance report",
    "brand refresh brief",
    "API design document",
    "user interview digest",
    "pricing comparison sheet",
    "onboarding funnel analysis",
    "capacity plan",
)

# Presets: fixture = committed CI sample (small, minutes to run);
# full = the PRD's documented scale (30-day corpora, 100 isolation
# users, 10,000 isolation retrieval operations).
PRESETS = {
    "fixture": {
        SCENARIO_BUFFER_CYCLE: {
            "span_days": 30,
            "sessions": 18,
            "filler_exchanges": 6,
            "fact_sets": 1,
        },
        SCENARIO_CROSS_AGENT: {
            "span_days": 30,
            "sessions": 16,
            "filler_exchanges": 2,
            "artifact_sets": 2,
        },
        SCENARIO_ISOLATION: {
            "users": 6,
            "span_days": 7,
            "sessions_per_user": 7,
            "target_ops": 600,
        },
        SCENARIO_CONTRADICTION: {
            "span_days": 45,
            "sessions": 12,
            "conflicted": 3,
            "superseded": 3,
        },
    },
    "full": {
        SCENARIO_BUFFER_CYCLE: {
            "span_days": 30,
            "sessions": 60,
            "filler_exchanges": 10,
            "fact_sets": 3,
        },
        SCENARIO_CROSS_AGENT: {
            "span_days": 30,
            "sessions": 60,
            "filler_exchanges": 4,
            "artifact_sets": 3,
        },
        SCENARIO_ISOLATION: {
            "users": 100,
            "span_days": 7,
            "sessions_per_user": 7,
            "target_ops": 10000,
        },
        SCENARIO_CONTRADICTION: {
            "span_days": 90,
            "sessions": 45,
            "conflicted": 10,
            "superseded": 10,
        },
    },
}


def _rng(seed: int, *scope: Any) -> random.Random:
    return random.Random(":".join(str(part) for part in (seed, "longitudinal", *scope)))


def _spread_dates(rng: random.Random, span_days: int, sessions: int) -> List[date]:
    """Session dates covering ``span_days`` (first day 0, last day span-1)."""
    start = date(2026, 2, 2) + timedelta(days=rng.randint(0, 45))
    if sessions == 1:
        return [start]
    return [
        start + timedelta(days=(i * (span_days - 1)) // (sessions - 1)) for i in range(sessions)
    ]


class _SessionWriter:
    """Accumulates one session's turns, handing back stable turn ids."""

    def __init__(self, case_id: str, index: int, session_date: date, agent_id: str):
        self.session_id = f"{case_id}_s{index + 1:03d}"
        self.date = _iso(session_date)
        self.agent_id = agent_id
        self.turns: List[Dict[str, str]] = []

    def add(self, role: str, content: str) -> str:
        turn_id = f"{self.session_id}:{len(self.turns)}"
        self.turns.append({"role": role, "content": content})
        return turn_id

    def add_filler(self, count: int, salt: int) -> None:
        """Deterministic small-talk exchanges padding the buffer workload.

        Each exchange carries a distinct note number so no two filler
        turns embed identically (a buffer full of duplicate vectors
        would make the eviction workload unrealistically compressible).
        """
        for exchange_index in range(count):
            question, answer = DISTRACTOR_EXCHANGES[
                (salt + exchange_index) % len(DISTRACTOR_EXCHANGES)
            ]
            note = salt * 17 + exchange_index
            self.add("user", f"{question} (note {note:04d})")
            self.add("assistant", f"{answer} (ref {note:04d})")

    def render(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "date": self.date,
            "agent_id": self.agent_id,
            "turns": self.turns,
        }


class _CaseBuilder:
    """Shared ground-truth bookkeeping for one longitudinal case."""

    def __init__(self, case_id: str, scenario: str):
        self.case_id = case_id
        self.scenario = scenario
        self.writers: List[_SessionWriter] = []
        self.entities: List[GTEntity] = []
        self.relationships: List[GTRelationship] = []
        self.log_entries: List[GTLogEntry] = []
        self.contradictions: List[Dict[str, Any]] = []
        self.distractors: List[Dict[str, Any]] = []
        self.decisions: List[Dict[str, Any]] = []
        self.artifacts: List[Dict[str, Any]] = []
        self.canaries: List[str] = []
        self.questions: List[GTQuestion] = []
        self.question_meta: Dict[str, Dict[str, Any]] = {}
        self._question_counter = 0
        # Per-date log accumulation: date -> (summary parts, decisions,
        # projects, session ids).
        self._log_days: Dict[str, Dict[str, Any]] = {}

    # -- ground truth ---------------------------------------------------------

    def entity(
        self,
        writer: _SessionWriter,
        turn_id: str,
        name: str,
        entity_type: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.entities.append(
            GTEntity(
                name=name,
                type=entity_type,
                attributes=dict(attributes or {}),
                session_id=writer.session_id,
                turn_id=turn_id,
            )
        )

    def relationship(
        self,
        writer: _SessionWriter,
        turn_id: str,
        from_name: str,
        from_type: str,
        rel_type: str,
        to_name: str,
        to_type: str,
        attributes: Optional[Dict[str, Any]] = None,
        confidence: float = DEFAULT_FACT_CONFIDENCE,
    ) -> None:
        attrs = dict(attributes or {})
        attrs.setdefault("stated_on", writer.date)
        self.relationships.append(
            GTRelationship(
                from_name=from_name,
                from_type=from_type,
                type=rel_type,
                to_name=to_name,
                to_type=to_type,
                attributes=attrs,
                confidence=confidence,
                session_id=writer.session_id,
                turn_id=turn_id,
            )
        )

    def log_day(
        self,
        writer: _SessionWriter,
        highlight: str,
        decision: Optional[str] = None,
        project: Optional[str] = None,
    ) -> None:
        day = self._log_days.setdefault(
            writer.date,
            {"highlights": [], "decisions": [], "projects": [], "session_ids": []},
        )
        day["highlights"].append(highlight)
        if decision:
            day["decisions"].append(decision)
            self.decisions.append(
                {"decision": decision, "date": writer.date, "session_id": writer.session_id}
            )
        if project and project not in day["projects"]:
            day["projects"].append(project)
        if writer.session_id not in day["session_ids"]:
            day["session_ids"].append(writer.session_id)

    def question(
        self,
        category: str,
        question: str,
        answer: str,
        evidence: Sequence[Tuple[str, str]],
        exact_strings: Sequence[str] = (),
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._question_counter += 1
        question_id = f"{self.case_id}_q{self._question_counter:03d}_{category}"
        self.questions.append(
            GTQuestion(
                question_id=question_id,
                category=category,
                question=question,
                answer=answer,
                evidence_session_ids=sorted({session_id for session_id, _ in evidence}),
                evidence_turn_ids=[turn_id for _, turn_id in evidence if turn_id],
                exact_strings=list(exact_strings),
                date_from=date_from,
                date_to=date_to,
            )
        )
        if meta:
            self.question_meta[question_id] = dict(meta)

    # -- output ---------------------------------------------------------------

    def build(self, extra_ground_truth: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        for day in sorted(self._log_days):
            info = self._log_days[day]
            summary = f"Work on {day}: " + "; ".join(info["highlights"])
            self.log_entries.append(
                GTLogEntry(
                    date=day,
                    summary=summary,
                    decisions=list(info["decisions"]),
                    projects=list(info["projects"]),
                    source_session_ids=list(info["session_ids"]),
                )
            )
        ground_truth: Dict[str, Any] = {
            "entities": [asdict(entity) for entity in self.entities],
            "relationships": [asdict(rel) for rel in self.relationships],
            "log_entries": [asdict(entry) for entry in self.log_entries],
            "contradictions": list(self.contradictions),
            "distractors": list(self.distractors),
            "decisions": list(self.decisions),
            "artifacts": list(self.artifacts),
            "canaries": list(self.canaries),
            "question_meta": dict(self.question_meta),
        }
        ground_truth.update(extra_ground_truth or {})
        return {
            "case_id": self.case_id,
            "scenario": self.scenario,
            "sessions": [writer.render() for writer in self.writers],
            "questions": [asdict(question) for question in self.questions],
            "ground_truth": ground_truth,
        }


# ---------------------------------------------------------------------------
# Scenario A: buffer cycle compensation
# ---------------------------------------------------------------------------


def _build_buffer_cycle(seed: int, params: Dict[str, Any]) -> Dict[str, Any]:
    rng = _rng(seed, SCENARIO_BUFFER_CYCLE)
    case = _CaseBuilder("seq_buffer_cycle_000", SCENARIO_BUFFER_CYCLE)
    span_days = params["span_days"]
    sessions = params["sessions"]
    fact_sets = params["fact_sets"]

    dates = _spread_dates(rng, span_days, sessions)
    start = dates[0]
    early_indices = [i for i, d in enumerate(dates) if (d - start).days < EARLY_WINDOW_DAYS]
    recent_indices = [
        i for i, d in enumerate(dates) if (d - start).days >= span_days - EARLY_WINDOW_DAYS
    ]

    company = rng.choice(COMPANIES)
    firsts = rng.sample(FIRST_NAMES, min(len(FIRST_NAMES), 4 * fact_sets + 2))
    lasts = rng.sample(LAST_NAMES, min(len(LAST_NAMES), 4 * fact_sets + 2))
    people = [f"{first} {last}" for first, last in zip(firsts, lasts)]
    technologies = list(TECHNOLOGIES)
    projects = ["checkout service", "payments integration", "auth migration", "search revamp"]

    writers = [
        _SessionWriter(case.case_id, index, dates[index], "membench-agent")
        for index in range(sessions)
    ]
    case.writers = writers

    # Opening filler so fact turns never sit at turn index 0.
    for index, writer in enumerate(writers):
        writer.add_filler(1, salt=index * 2)

    person_cursor = 0
    code_cursor = 0

    def _employment(writer: _SessionWriter, category: str) -> None:
        nonlocal person_cursor
        person = people[person_cursor % len(people)]
        person_cursor += 1
        role = ROLES[person_cursor % len(ROLES)]
        email = _email_for(person, company)
        turn_id = writer.add(
            "user",
            f"For the record: {person} is our {role} at {company}. "
            f"You can reach them at {email}.",
        )
        writer.add("assistant", f"Noted. {person} ({role}, {company}) with contact {email}.")
        case.entity(writer, turn_id, person, "person", {"role": role, "email": email})
        case.entity(writer, turn_id, company, "company")
        case.relationship(
            writer, turn_id, person, "person", "works_at", company, "company", {"role": role}
        )
        case.log_day(writer, f"logged {person} as {role}")
        case.question(
            category,
            f"What is {person}'s email address?",
            email,
            [(writer.session_id, turn_id)],
            exact_strings=[email],
        )

    def _recommendation(writer: _SessionWriter, category: str) -> None:
        nonlocal person_cursor
        person = people[person_cursor % len(people)]
        person_cursor += 1
        tech = technologies[person_cursor % len(technologies)]
        project = projects[person_cursor % len(projects)]
        decision = f"Adopt {tech} for the {project} ({person}'s recommendation)"
        turn_id = writer.add(
            "user",
            f"{person} recommended switching to {tech} for the {project}. Let's go with that.",
        )
        writer.add(
            "assistant",
            f"Decision recorded: {tech} for the {project}, recommended by {person}.",
        )
        case.entity(writer, turn_id, person, "person")
        case.entity(writer, turn_id, tech, "topic")
        case.entity(writer, turn_id, project, "project")
        case.relationship(
            writer, turn_id, person, "person", "recommended", tech, "topic", {"project": project}
        )
        case.log_day(
            writer,
            f"{person} recommended {tech} for the {project}",
            decision=decision,
            project=project,
        )
        case.question(
            category,
            f"Who recommended using {tech} for the {project}?",
            person,
            [(writer.session_id, turn_id)],
        )

    def _code_fact(writer: _SessionWriter, category: str) -> None:
        nonlocal person_cursor, code_cursor
        person = people[person_cursor % len(people)]
        person_cursor += 1
        kind, prefix = [("invoice", "INV"), ("support ticket", "TKT")][code_cursor % 2]
        code_cursor += 1
        code = _code(rng, prefix)
        project = projects[code_cursor % len(projects)]
        turn_id = writer.add(
            "user",
            f"{person} opened {kind} {code} for the {project}. Keep that reference handy.",
        )
        writer.add("assistant", f"Saved: {kind} {code} ({project}, opened by {person}).")
        case.entity(writer, turn_id, person, "person")
        case.entity(writer, turn_id, code, "reference", {"kind": kind, "project": project})
        case.relationship(
            writer,
            turn_id,
            person,
            "person",
            "opened",
            code,
            "reference",
            {"kind": kind, "project": project},
        )
        case.log_day(writer, f"{person} opened {kind} {code}")
        case.question(
            category,
            f"What was the reference number of the {kind} {person} opened for the {project}?",
            code,
            [(writer.session_id, turn_id)],
            exact_strings=[code],
        )

    # Early-window facts (Scenario A's subject: asked at "day 30" after
    # their source turns have been evicted).
    early_events = (
        [_employment] * (2 * fact_sets) + [_recommendation] * fact_sets + [_code_fact] * fact_sets
    )
    for event_index, event in enumerate(early_events):
        writer = writers[early_indices[event_index % len(early_indices)]]
        event(writer, CATEGORY_EVICTED)

    # Recent-window control facts (still buffer-resident at question time).
    recent_events = [_employment, _code_fact] * fact_sets
    for event_index, event in enumerate(recent_events):
        writer = writers[recent_indices[event_index % len(recent_indices)]]
        event(writer, CATEGORY_RECENT)

    # Narrative questions: the decisions of each decision-bearing day
    # (Captain's-Log recall; answers list every decision of the date).
    decisions_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for decision in case.decisions:
        decisions_by_date.setdefault(decision["date"], []).append(decision)
    early_cutoff = _iso(dates[0] + timedelta(days=EARLY_WINDOW_DAYS - 1))
    recent_cutoff = _iso(dates[0] + timedelta(days=span_days - EARLY_WINDOW_DAYS))
    for day in sorted(decisions_by_date):
        if day <= early_cutoff:
            category = CATEGORY_EVICTED
        elif day >= recent_cutoff:
            category = CATEGORY_RECENT
        else:
            continue
        day_decisions = decisions_by_date[day]
        case.question(
            category,
            f"What were the main decisions made on {day}?",
            "; ".join(item["decision"] for item in day_decisions),
            [(item["session_id"], None) for item in day_decisions],
            date_from=day,
            date_to=day,
        )

    # Filler workload: the conversation-heavy noise that cycles the buffer.
    for index, writer in enumerate(writers):
        writer.add_filler(max(0, params["filler_exchanges"] - 1), salt=index * 2 + 1)

    return case.build(
        extra_ground_truth={
            "early_window": {
                "date_from": _iso(dates[0]),
                "date_to": _iso(dates[0] + timedelta(days=EARLY_WINDOW_DAYS - 1)),
            }
        }
    )


# ---------------------------------------------------------------------------
# Scenario B: cross-agent knowledge propagation
# ---------------------------------------------------------------------------


def _build_cross_agent(seed: int, params: Dict[str, Any]) -> Dict[str, Any]:
    rng = _rng(seed, SCENARIO_CROSS_AGENT)
    case = _CaseBuilder("seq_cross_agent_000", SCENARIO_CROSS_AGENT)
    sessions = params["sessions"]
    dates = _spread_dates(rng, params["span_days"], sessions)

    agents = list(CROSS_AGENT_AGENTS)
    writers = [
        _SessionWriter(case.case_id, index, dates[index], agents[index % len(agents)])
        for index in range(sessions)
    ]
    case.writers = writers
    writers_by_agent: Dict[str, List[_SessionWriter]] = {}
    for writer in writers:
        writers_by_agent.setdefault(writer.agent_id, []).append(writer)

    firsts = rng.sample(FIRST_NAMES, 6)
    lasts = rng.sample(LAST_NAMES, 6)
    people = [f"{first} {last}" for first, last in zip(firsts, lasts)]
    technologies = list(TECHNOLOGIES)
    projects = ["pricing revamp", "enterprise pipeline", "search revamp", "partner program"]

    artifact_names = list(CROSS_AGENT_ARTIFACTS)
    artifact_cursor = 0
    fact_cursor = 0

    for set_index in range(params["artifact_sets"]):
        for agent_index, agent in enumerate(agents):
            asking_agent = agents[(agent_index + 1) % len(agents)]
            own_writers = writers_by_agent[agent]
            writer = own_writers[set_index % len(own_writers)]

            # The agent produces an artifact in its own session.
            artifact = artifact_names[artifact_cursor % len(artifact_names)]
            artifact_cursor += 1
            reference = _code(rng, "DOC")
            turn_id = writer.add(
                "user",
                f"For the record: the {agent} produced the {artifact} today "
                f"and filed it under reference {reference}.",
            )
            writer.add("assistant", f"Logged - {artifact} delivered by the {agent}.")
            case.entity(writer, turn_id, agent, "agent")
            case.entity(writer, turn_id, artifact, "artifact", {"reference": reference})
            case.relationship(
                writer,
                turn_id,
                agent,
                "agent",
                "produced",
                artifact,
                "artifact",
                {"reference": reference},
            )
            case.log_day(writer, f"the {agent} delivered the {artifact}")
            case.artifacts.append(
                {
                    "name": artifact,
                    "agent": agent,
                    "reference": reference,
                    "session_id": writer.session_id,
                    "turn_id": turn_id,
                }
            )
            meta = {"evidence_agent": agent, "asking_agent": asking_agent}
            case.question(
                CATEGORY_PROPAGATION,
                f"Which agent produced the {artifact}?",
                agent,
                [(writer.session_id, turn_id)],
                meta=meta,
            )
            case.question(
                CATEGORY_PROPAGATION,
                f"Under what reference number was the {artifact} filed?",
                reference,
                [(writer.session_id, turn_id)],
                exact_strings=[reference],
                meta=meta,
            )

            # The agent also logs a KG fact another agent must recall.
            # (tech, project) pairs stay unique across the corpus so
            # "who recommended X for Y" always has exactly one answer.
            person = people[fact_cursor % len(people)]
            tech = technologies[fact_cursor % len(technologies)]
            project = projects[(fact_cursor + fact_cursor // len(technologies)) % len(projects)]
            fact_cursor += 1
            fact_turn = writer.add(
                "user",
                f"{person} recommended {tech} for the {project}; the {agent} "
                f"confirmed it in review.",
            )
            writer.add("assistant", f"Recorded: {tech} for the {project}, per {person}.")
            case.entity(writer, fact_turn, person, "person")
            case.entity(writer, fact_turn, tech, "topic")
            case.entity(writer, fact_turn, project, "project")
            case.relationship(
                writer,
                fact_turn,
                person,
                "person",
                "recommended",
                tech,
                "topic",
                {"project": project},
            )
            case.log_day(
                writer,
                f"{person} recommended {tech} for the {project}",
                decision=f"Adopt {tech} for the {project} ({person}'s recommendation)",
                project=project,
            )
            case.question(
                CATEGORY_PROPAGATION,
                f"Who recommended {tech} for the {project}?",
                person,
                [(writer.session_id, fact_turn)],
                meta=meta,
            )

    for index, writer in enumerate(writers):
        writer.add_filler(params["filler_exchanges"], salt=index)

    return case.build(extra_ground_truth={"agents": agents})


# ---------------------------------------------------------------------------
# Scenario C: multi-user isolation
# ---------------------------------------------------------------------------


def _canary(rng: random.Random, user_index: int) -> str:
    letters = "".join(rng.choice("ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(2))
    return f"CANARY-{user_index:03d}-{rng.randint(1000, 9999)}{letters}"


def _build_isolation_user(seed: int, user_index: int, params: Dict[str, Any]) -> Dict[str, Any]:
    rng = _rng(seed, SCENARIO_ISOLATION, user_index)
    case = _CaseBuilder(f"seq_isolation_{user_index:03d}", SCENARIO_ISOLATION)
    sessions = params["sessions_per_user"]
    dates = _spread_dates(rng, params["span_days"], sessions)

    writers = [
        _SessionWriter(case.case_id, index, dates[index], "membench-agent")
        for index in range(sessions)
    ]
    case.writers = writers

    # Identical fact templates across users — only the values differ.
    # If isolation broke, another user's near-identical turn would be
    # the nearest neighbor for these probes.
    person = (
        f"{FIRST_NAMES[user_index % len(FIRST_NAMES)]} "
        f"{LAST_NAMES[user_index % len(LAST_NAMES)]}"
    )
    company = COMPANIES[user_index % len(COMPANIES)]
    city = CITIES[user_index % len(CITIES)]
    email = _email_for(person, company)
    locker_canary = _canary(rng, user_index)
    ticket_canary = _canary(rng, user_index)
    case.canaries = [locker_canary, ticket_canary, email]

    writer = writers[0]
    turn_id = writer.add(
        "user",
        f"Please remember: my private locker code is {locker_canary}.",
    )
    writer.add("assistant", f"Stored your private locker code {locker_canary}.")
    case.entity(writer, turn_id, locker_canary, "reference", {"kind": "locker code"})
    case.log_day(writer, f"stored private locker code {locker_canary}")
    case.question(
        CATEGORY_ISOLATION_PROBE,
        "What is my private locker code?",
        locker_canary,
        [(writer.session_id, turn_id)],
        exact_strings=[locker_canary],
    )

    writer = writers[1 % sessions]
    turn_id = writer.add(
        "user",
        f"My main contact is {person} at {company}; email {email}.",
    )
    writer.add("assistant", f"Noted. {person} ({company}), contact {email}.")
    case.entity(writer, turn_id, person, "person", {"email": email})
    case.entity(writer, turn_id, company, "company")
    case.relationship(writer, turn_id, person, "person", "works_at", company, "company")
    case.log_day(writer, f"logged {person} ({company}) as main contact")
    case.question(
        CATEGORY_ISOLATION_PROBE,
        "What is my main contact's email address?",
        email,
        [(writer.session_id, turn_id)],
        exact_strings=[email],
    )

    writer = writers[2 % sessions]
    turn_id = writer.add(
        "user",
        f"I filed my expense ticket under {ticket_canary}; {person} is based in {city}.",
    )
    writer.add("assistant", f"Saved ticket {ticket_canary}; {person} is based in {city}.")
    case.entity(writer, turn_id, ticket_canary, "reference", {"kind": "expense ticket"})
    case.entity(writer, turn_id, city, "location")
    case.relationship(writer, turn_id, person, "person", "lives_in", city, "location")
    case.log_day(writer, f"filed expense ticket {ticket_canary}")
    case.question(
        CATEGORY_ISOLATION_PROBE,
        "Under what reference did I file my expense ticket?",
        ticket_canary,
        [(writer.session_id, turn_id)],
        exact_strings=[ticket_canary],
    )
    case.question(
        CATEGORY_ISOLATION_PROBE,
        "Which city is my main contact based in?",
        city,
        [(writer.session_id, turn_id)],
    )

    for index, writer in enumerate(writers):
        writer.add_filler(2, salt=user_index * 31 + index)

    return case.build()


# ---------------------------------------------------------------------------
# Scenario D: contradiction detection over time
# ---------------------------------------------------------------------------


def _build_contradiction(seed: int, params: Dict[str, Any]) -> Dict[str, Any]:
    rng = _rng(seed, SCENARIO_CONTRADICTION)
    case = _CaseBuilder("seq_contradiction_000", SCENARIO_CONTRADICTION)
    sessions = params["sessions"]
    dates = _spread_dates(rng, params["span_days"], sessions)
    writers = [
        _SessionWriter(case.case_id, index, dates[index], "membench-agent")
        for index in range(sessions)
    ]
    case.writers = writers

    conflicted = params["conflicted"]
    superseded = params["superseded"]
    needed_people = conflicted + superseded + 2  # + distractor subjects
    firsts = [FIRST_NAMES[i % len(FIRST_NAMES)] for i in range(needed_people)]
    lasts = [LAST_NAMES[(i * 3 + 1) % len(LAST_NAMES)] for i in range(needed_people)]
    people = [f"{first} {last}" for first, last in zip(firsts, lasts)]

    def _assert_fact(
        writer: _SessionWriter,
        person: str,
        predicate: str,
        obj: str,
        obj_type: str,
        confidence: float,
        phrasing: str,
    ) -> str:
        turn_id = writer.add("user", phrasing)
        writer.add("assistant", f"Recorded: {person} {predicate.replace('_', ' ')} {obj}.")
        case.entity(writer, turn_id, person, "person")
        case.entity(writer, turn_id, obj, obj_type)
        case.relationship(
            writer,
            turn_id,
            person,
            "person",
            predicate,
            obj,
            obj_type,
            confidence=confidence,
        )
        case.log_day(writer, f"noted {person} {predicate.replace('_', ' ')} {obj}")
        return turn_id

    # Alternate exclusive predicates across pairs; spread old/new facts
    # across the timeline with a session gap between assertion and
    # contradiction (the "over time" in the PRD's Scenario D).
    pair_specs = [("conflicted", i) for i in range(conflicted)] + [
        ("superseded", i) for i in range(superseded)
    ]
    gap = max(2, sessions // 3)
    for pair_index, (kind, _) in enumerate(pair_specs):
        person = people[pair_index]
        predicate = ("works_at", "lives_in")[pair_index % 2]
        if predicate == "works_at":
            pool = COMPANIES
            obj_type = "company"
        else:
            pool = CITIES
            obj_type = "location"
        old_obj = pool[(pair_index * 2) % len(pool)]
        new_obj = pool[(pair_index * 2 + 1) % len(pool)]
        old_slot = pair_index % max(1, sessions - gap)
        new_slot = min(sessions - 1, old_slot + gap)

        if kind == "conflicted":
            old_confidence = CONFLICTED_OLD_CONFIDENCE
            new_confidence = CONFLICTED_NEW_CONFIDENCE
            new_phrasing = (
                f"Wait - I heard {person} actually "
                f"{'works at' if predicate == 'works_at' else 'lives in'} {new_obj}, "
                f"not {old_obj}."
            )
        else:
            old_confidence = SUPERSEDED_OLD_CONFIDENCE
            new_confidence = SUPERSEDED_NEW_CONFIDENCE
            new_phrasing = (
                f"Confirmed by HR: {person} now "
                f"{'works at' if predicate == 'works_at' else 'lives in'} {new_obj}."
            )

        old_turn = _assert_fact(
            writers[old_slot],
            person,
            predicate,
            old_obj,
            obj_type,
            old_confidence,
            f"{person} {'works at' if predicate == 'works_at' else 'lives in'} {old_obj}.",
        )
        new_turn = _assert_fact(
            writers[new_slot], person, predicate, new_obj, obj_type, new_confidence, new_phrasing
        )
        case.contradictions.append(
            {
                "subject": person,
                "predicate": predicate,
                "old_object": old_obj,
                "new_object": new_obj,
                "old_turn_id": old_turn,
                "new_turn_id": new_turn,
                "expected_detection": kind,
            }
        )

    # Precision distractors: must NOT be flagged.
    # 1. Duplicate re-assertion (same subject, predicate, AND object).
    dup_person = people[len(pair_specs)]
    dup_company = COMPANIES[3 % len(COMPANIES)]
    first_turn = _assert_fact(
        writers[0],
        dup_person,
        "works_at",
        dup_company,
        "company",
        DEFAULT_FACT_CONFIDENCE,
        f"{dup_person} works at {dup_company}.",
    )
    dup_turn = _assert_fact(
        writers[-1],
        dup_person,
        "works_at",
        dup_company,
        "company",
        DEFAULT_FACT_CONFIDENCE,
        f"Just double-checking: {dup_person} still works at {dup_company}, right?",
    )
    case.distractors.append(
        {
            "kind": "duplicate_fact",
            "subject": dup_person,
            "predicate": "works_at",
            "object": dup_company,
            "turn_ids": [first_turn, dup_turn],
        }
    )

    # 2. Non-exclusive predicate change (a person may recommend many
    #    technologies; a changed object is an addition, not a conflict).
    rec_person = people[len(pair_specs) + 1]
    tech_a, tech_b = TECHNOLOGIES[0], TECHNOLOGIES[1]
    rec_turn_a = writers[1].add(
        "user", f"{rec_person} recommended {tech_a} for the checkout service."
    )
    writers[1].add("assistant", f"Recorded {rec_person}'s recommendation of {tech_a}.")
    case.entity(writers[1], rec_turn_a, rec_person, "person")
    case.entity(writers[1], rec_turn_a, tech_a, "topic")
    case.relationship(writers[1], rec_turn_a, rec_person, "person", "recommended", tech_a, "topic")
    rec_turn_b = writers[min(sessions - 1, 1 + gap)].add(
        "user", f"{rec_person} now also recommends {tech_b} for the checkout service."
    )
    writers[min(sessions - 1, 1 + gap)].add(
        "assistant", f"Recorded {rec_person}'s recommendation of {tech_b}."
    )
    case.entity(writers[min(sessions - 1, 1 + gap)], rec_turn_b, tech_b, "topic")
    case.relationship(
        writers[min(sessions - 1, 1 + gap)],
        rec_turn_b,
        rec_person,
        "person",
        "recommended",
        tech_b,
        "topic",
    )
    case.distractors.append(
        {
            "kind": "non_exclusive_change",
            "subject": rec_person,
            "predicate": "recommended",
            "objects": [tech_a, tech_b],
            "turn_ids": [rec_turn_a, rec_turn_b],
        }
    )

    for index, writer in enumerate(writers):
        writer.add_filler(2, salt=index)

    return case.build()


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------


def generate_dataset(preset: str = "fixture", seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    """Generate the Tier 3 longitudinal dataset as a plain dict.

    Deterministic: identical ``(preset, seed)`` produce an identical
    dict (and, through :func:`write_dataset`, byte-identical files).
    """
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r} (expected one of {sorted(PRESETS)})")
    params = PRESETS[preset]

    scenarios: Dict[str, Any] = {
        SCENARIO_BUFFER_CYCLE: {
            "config": dict(params[SCENARIO_BUFFER_CYCLE]),
            "cases": [_build_buffer_cycle(seed, params[SCENARIO_BUFFER_CYCLE])],
        },
        SCENARIO_CROSS_AGENT: {
            "config": dict(params[SCENARIO_CROSS_AGENT]),
            "cases": [_build_cross_agent(seed, params[SCENARIO_CROSS_AGENT])],
        },
        SCENARIO_ISOLATION: {
            "config": dict(params[SCENARIO_ISOLATION]),
            "cases": [
                _build_isolation_user(seed, user_index, params[SCENARIO_ISOLATION])
                for user_index in range(params[SCENARIO_ISOLATION]["users"])
            ],
        },
        SCENARIO_CONTRADICTION: {
            "config": dict(params[SCENARIO_CONTRADICTION]),
            "cases": [_build_contradiction(seed, params[SCENARIO_CONTRADICTION])],
        },
    }
    return {
        "name": DATASET_NAME,
        "schema_version": DATASET_SCHEMA_VERSION,
        "generator": {"preset": preset, "seed": seed, "scenarios": list(SCENARIOS)},
        "scenarios": scenarios,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the Tier 3 longitudinal corpus (four PRD scenarios; "
            "deterministic, seeded, no LLM calls)."
        )
    )
    parser.add_argument("--preset", choices=sorted(PRESETS), default="fixture")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args(argv)

    dataset = generate_dataset(preset=args.preset, seed=args.seed)
    path = write_dataset(dataset, Path(args.output))
    for key, scenario in dataset["scenarios"].items():
        cases = scenario["cases"]
        sessions = sum(len(case["sessions"]) for case in cases)
        turns = sum(len(s["turns"]) for case in cases for s in case["sessions"])
        questions = sum(len(case["questions"]) for case in cases)
        print(
            f"  {key:<16} cases={len(cases):<4} sessions={sessions:<5} "
            f"turns={turns:<6} questions={questions}"
        )
    print(f"Wrote {path} (preset={args.preset}, seed={args.seed})")
    return 0


if __name__ == "__main__":
    import sys

    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(main())
