"""Synthetic corpus + ground-truth Q&A generator for Tier 2 (Structured Recall).

No public dataset tests KG relationship recall, temporal validity,
narrative recall, cross-agent knowledge, or contradiction detection —
so MUXI builds one (memory-benchmarking PRD, Tier 2). This module
generates it:

- A **conversation corpus**: seeded, deterministic multi-session
  sequences over five realistic formation scenarios (software team,
  sales ops, personal assistant, financial analysis, customer
  support). Facts, decisions, artifacts, and contradictions are
  embedded in rendered conversation turns.
- A **ground-truth manifest** per sequence: every entity,
  relationship (with provenance to the exact turn), Captain's-Log
  entry, and injected contradiction — machine-usable by the
  structured retrieval mode and by dataset consumers.
- A **Q&A dataset**: template-generated questions across the five PRD
  categories, each with a gold answer and evidence session/turn ids.
  Questions whose answers are exact strings (emails, ticket codes,
  invoice ids) carry ``exact_strings`` so runs can measure
  exact-string recall — the metric that decides whether hybrid/BM25
  search (memory-revamp Phase 6) gets built.

Determinism: everything derives from ``random.Random`` seeded per
sequence with ``f"{seed}:{index}"``. The same (seed, size) inputs
produce byte-identical dataset files. No LLM is involved; the PRD's
"automated generation layer" (LLM-expanded questions validated by
human review) can extend this corpus later without replacing it.

Tier 3 seam: the longitudinal benchmark (30-90 day corpora, buffer
cycling, multi-user isolation) builds on the same event-scheduling
skeleton — sessions here already carry real dates and per-agent
attribution — but requires the memory-substrate rebuild to land
first. See bench/memory/README.md ("Tier 3").

CLI
---
::

    # Regenerate the committed CI fixture (3 sequences, 30 questions)
    uv run python -m bench.memory.structured_corpus --preset fixture \
        --output bench/memory/fixtures/structured_recall_sample.json

    # Full dataset (50 sequences, 500 questions, PRD scale)
    uv run python -m bench.memory.structured_corpus --preset full \
        --output ~/datasets/membench/structured_recall_full.json
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DATASET_NAME = "muxi-structured-recall"
DATASET_SCHEMA_VERSION = "1.0"

DEFAULT_SEED = 42

# The five PRD question categories.
CATEGORY_KG = "kg_relationship"
CATEGORY_TEMPORAL = "temporal_validity"
CATEGORY_NARRATIVE = "narrative_recall"
CATEGORY_CROSS_AGENT = "cross_agent"
CATEGORY_CONTRADICTION = "contradiction_detection"
CATEGORIES = (
    CATEGORY_KG,
    CATEGORY_TEMPORAL,
    CATEGORY_NARRATIVE,
    CATEGORY_CROSS_AGENT,
    CATEGORY_CONTRADICTION,
)

# Presets: fixture = committed CI sample; full = PRD scale (50 sequences,
# 2 questions per category per sequence = 500 questions).
PRESETS = {
    "fixture": {"sequences": 3, "sessions_per_sequence": 12, "questions_per_category": 2},
    "full": {"sequences": 50, "sessions_per_sequence": None, "questions_per_category": 2},
}

# ---------------------------------------------------------------------------
# Ground-truth dataclasses (serialized into each case's manifest)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GTEntity:
    """A ground-truth entity with provenance to the turn that states it."""

    name: str
    type: str
    attributes: Dict[str, Any]
    session_id: str
    turn_id: str


@dataclass(frozen=True)
class GTRelationship:
    """A ground-truth relationship with provenance."""

    from_name: str
    from_type: str
    type: str
    to_name: str
    to_type: str
    attributes: Dict[str, Any]
    confidence: float
    session_id: str
    turn_id: str


@dataclass(frozen=True)
class GTLogEntry:
    """A ground-truth Captain's-Log entry for one day."""

    date: str
    summary: str
    decisions: List[str]
    projects: List[str]
    source_session_ids: List[str]


@dataclass(frozen=True)
class GTContradiction:
    """An injected contradiction between two turns."""

    subject: str
    predicate: str
    old_object: str
    new_object: str
    old_turn_id: str
    new_turn_id: str


@dataclass
class GTQuestion:
    """A generated question with gold answer and evidence."""

    question_id: str
    category: str
    question: str
    answer: str
    evidence_session_ids: List[str]
    evidence_turn_ids: List[str]
    exact_strings: List[str] = field(default_factory=list)
    date_from: Optional[str] = None
    date_to: Optional[str] = None


# ---------------------------------------------------------------------------
# Name/content pools (deterministically sampled per sequence)
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Kai",
    "Mara",
    "Jonas",
    "Priya",
    "Tomas",
    "Lena",
    "Ravi",
    "Sofia",
    "Dario",
    "Ingrid",
    "Malik",
    "Noor",
    "Petra",
    "Owen",
    "Yuki",
    "Amara",
]
LAST_NAMES = [
    "Nakamura",
    "Silva",
    "Bergstrom",
    "Rao",
    "Kovacs",
    "Fischer",
    "Mensah",
    "Alvarez",
    "Okafor",
    "Lindqvist",
    "Haddad",
    "Petrov",
    "Tanaka",
    "Moreau",
]
COMPANIES = [
    "Vertex Labs",
    "Northwind Analytics",
    "Helios Systems",
    "Cobalt Works",
    "Aster Dynamics",
    "Quill Software",
    "Bluepeak Media",
    "Sundial Health",
]
CITIES = [
    "Berlin",
    "Lisbon",
    "Austin",
    "Toronto",
    "Singapore",
    "Amsterdam",
    "Stockholm",
    "Melbourne",
]
ROLES = [
    "backend engineer",
    "engineering lead",
    "product manager",
    "data analyst",
    "account executive",
    "support specialist",
    "finance controller",
    "marketing strategist",
]
TECHNOLOGIES = [
    "PostgreSQL",
    "Clerk",
    "Stripe",
    "Kafka",
    "Terraform",
    "Snowflake",
    "Redis",
    "Temporal",
]

SCENARIOS = {
    "software_team": {
        "agents": ["research-agent", "engineering-agent", "reviewer-agent"],
        "projects": ["checkout service", "payments integration", "auth migration", "search revamp"],
        "artifacts": [
            "API design document",
            "load test report",
            "migration runbook",
            "incident postmortem",
        ],
    },
    "sales_ops": {
        "agents": ["sales-agent", "marketing-agent", "finance-agent"],
        "projects": [
            "enterprise pipeline",
            "pricing revamp",
            "renewal campaign",
            "partner program",
        ],
        "artifacts": [
            "Q3 revenue forecast",
            "pricing comparison sheet",
            "renewal playbook",
            "pipeline health report",
        ],
    },
    "personal_assistant": {
        "agents": ["planner-agent", "travel-agent", "inbox-agent"],
        "projects": ["home renovation", "conference trip", "tax filing", "family reunion"],
        "artifacts": [
            "travel itinerary",
            "renovation budget",
            "packing checklist",
            "vendor shortlist",
        ],
    },
    "financial_analysis": {
        "agents": ["finance-agent", "research-agent", "compliance-agent"],
        "projects": [
            "portfolio rebalance",
            "expense audit",
            "budget planning",
            "vendor consolidation",
        ],
        "artifacts": [
            "quarterly budget model",
            "expense anomaly report",
            "vendor spend breakdown",
            "cash flow projection",
        ],
    },
    "customer_support": {
        "agents": ["support-agent", "triage-agent", "escalation-agent"],
        "projects": [
            "ticket backlog cleanup",
            "helpdesk migration",
            "SLA revamp",
            "knowledge base refresh",
        ],
        "artifacts": [
            "escalation summary",
            "SLA compliance report",
            "macro response templates",
            "root cause analysis",
        ],
    },
}
SCENARIO_ORDER = list(SCENARIOS)

DISTRACTOR_EXCHANGES = [
    (
        "Can you suggest a quick lunch spot near the office?",
        "The noodle bar on the corner is fast, and the salad place next door has a lunch deal.",
    ),
    (
        "What's the weather looking like for the weekend?",
        "Mostly sunny with a chance of showers on Sunday afternoon.",
    ),
    (
        "Remind me how to write a good standup update.",
        "Cover what you finished, what you're doing next, and anything blocking you.",
    ),
    (
        "Any tips for staying focused during long meetings?",
        "Take brief notes by hand and ask one clarifying question early to stay engaged.",
    ),
    (
        "What's a good book on negotiation?",
        "Never Split the Difference is a practical starting point.",
    ),
    (
        "How do I make cold brew at home?",
        "Steep coarse grounds in cold water for 16 hours, then strain twice.",
    ),
    (
        "Can you recommend a stretch for wrist pain?",
        "Gentle wrist extensor stretches, ten seconds each side, a few times a day.",
    ),
    (
        "What time zone is our Thursday sync in?",
        "It is pinned to 15:00 UTC, which shifts locally with daylight saving.",
    ),
]


def _rng_for_sequence(seed: int, index: int) -> random.Random:
    return random.Random(f"{seed}:{index}")


def _email_for(name: str, company: str) -> str:
    user = name.lower().replace(" ", ".")
    domain = company.lower().replace(" ", "") + ".example.com"
    return f"{user}@{domain}"


def _code(rng: random.Random, prefix: str) -> str:
    letters = "".join(rng.choice("ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(2))
    return f"{prefix}-{rng.randint(1000, 9999)}-{letters}"


def _iso(day: date) -> str:
    return day.isoformat()


# ---------------------------------------------------------------------------
# Event model: each event renders turns into a session and emits ground truth
# ---------------------------------------------------------------------------


@dataclass
class _Event:
    """One fact-bearing exchange scheduled into a session."""

    kind: str
    turns: List[Tuple[str, str]]  # (role, content); first turn carries the fact
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    decision: Optional[str] = None
    project: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


class _SequenceBuilder:
    """Builds one corpus sequence (sessions + ground truth + questions)."""

    def __init__(
        self,
        index: int,
        seed: int,
        sessions_per_sequence: Optional[int],
        questions_per_category: int,
    ):
        self.rng = _rng_for_sequence(seed, index)
        self.scenario = SCENARIO_ORDER[index % len(SCENARIO_ORDER)]
        self.case_id = f"seq_{self.scenario}_{index:03d}"
        spec = SCENARIOS[self.scenario]
        self.agents = list(spec["agents"])
        self.n_sessions = sessions_per_sequence or self.rng.randint(10, 30)
        self.questions_per_category = questions_per_category

        # Cast (unique, deterministic).
        firsts = self.rng.sample(FIRST_NAMES, 5)
        lasts = self.rng.sample(LAST_NAMES, 5)
        self.people = [f"{f} {last}" for f, last in zip(firsts, lasts)]
        self.companies = self.rng.sample(COMPANIES, 2)
        self.cities = self.rng.sample(CITIES, 3)
        self.projects = self.rng.sample(spec["projects"], 3)
        self.artifacts = self.rng.sample(spec["artifacts"], 3)
        self.technologies = self.rng.sample(TECHNOLOGIES, 3)

        # Timeline: business-day-ish spacing starting from a seeded day.
        start = date(2026, 1, 5) + timedelta(days=self.rng.randint(0, 60))
        self.session_dates = [start + timedelta(days=2 * i) for i in range(self.n_sessions)]

        # Filled during build().
        self.events: List[Tuple[int, _Event]] = []  # (session_index, event)
        self.sessions: List[Dict[str, Any]] = []
        self.entities: List[GTEntity] = []
        self.relationships: List[GTRelationship] = []
        self.log_entries: List[GTLogEntry] = []
        self.contradictions: List[GTContradiction] = []
        self.questions: List[GTQuestion] = []
        self._question_counter = 0

    # -- event construction --------------------------------------------------

    def _schedule(self, session_index: int, event: _Event) -> None:
        self.events.append((session_index, event))

    def _spread(self, count: int, lo_frac: float = 0.0, hi_frac: float = 1.0) -> List[int]:
        """Deterministic distinct-ish session indexes inside a window."""
        lo = int(lo_frac * (self.n_sessions - 1))
        hi = max(lo, int(hi_frac * (self.n_sessions - 1)))
        return [
            lo + ((hi - lo) * i) // max(1, count - 1) if count > 1 else lo for i in range(count)
        ]

    def _build_events(self) -> None:
        rng = self.rng
        people, company = self.people, self.companies[0]

        # Employment facts (KG recall + exact-string emails).
        for i, slot in enumerate(self._spread(3, 0.0, 0.3)):
            person = people[i]
            role = ROLES[(rng.randrange(len(ROLES)) + i) % len(ROLES)]
            email = _email_for(person, company)
            self._schedule(
                slot,
                _Event(
                    kind="employment",
                    turns=[
                        (
                            "user",
                            f"For the record: {person} is our {role} at {company}. "
                            f"You can reach them at {email}.",
                        ),
                        (
                            "assistant",
                            f"Noted. {person} ({role}, {company}) with contact {email}.",
                        ),
                    ],
                    entities=[
                        {
                            "name": person,
                            "type": "person",
                            "attributes": {"role": role, "email": email},
                        },
                        {"name": company, "type": "company", "attributes": {}},
                    ],
                    relationships=[
                        {
                            "from": person,
                            "from_type": "person",
                            "type": "works_at",
                            "to": company,
                            "to_type": "company",
                            "attributes": {"role": role},
                            "confidence": 0.85,
                        }
                    ],
                    payload={"person": person, "role": role, "company": company, "email": email},
                ),
            )

        # Recommendation decisions (KG recall + narrative decisions).
        for i, slot in enumerate(self._spread(3, 0.1, 0.6)):
            person = people[(i + 1) % len(people)]
            tech = self.technologies[i % len(self.technologies)]
            project = self.projects[i % len(self.projects)]
            reason = rng.choice(
                [
                    "it removes an entire class of operational work",
                    "the team already knows it well",
                    "it was the cheapest option that met the latency budget",
                    "the migration path from the current stack is simplest",
                ]
            )
            decision = f"Adopt {tech} for the {project} ({person}'s recommendation)"
            self._schedule(
                slot,
                _Event(
                    kind="recommendation",
                    turns=[
                        (
                            "user",
                            f"{person} recommended switching to {tech} for the {project} "
                            f"because {reason}. Let's go with that.",
                        ),
                        (
                            "assistant",
                            f"Decision recorded: {tech} for the {project}, recommended by "
                            f"{person}. Rationale: {reason}.",
                        ),
                    ],
                    entities=[
                        {"name": person, "type": "person", "attributes": {}},
                        {"name": tech, "type": "topic", "attributes": {}},
                        {"name": project, "type": "project", "attributes": {}},
                    ],
                    relationships=[
                        {
                            "from": person,
                            "from_type": "person",
                            "type": "recommended",
                            "to": tech,
                            "to_type": "topic",
                            "attributes": {"project": project},
                            "confidence": 0.85,
                        },
                        {
                            "from": project,
                            "from_type": "project",
                            "type": "uses",
                            "to": tech,
                            "to_type": "topic",
                            "attributes": {},
                            "confidence": 0.85,
                        },
                    ],
                    decision=decision,
                    project=project,
                    payload={"person": person, "tech": tech, "project": project, "reason": reason},
                ),
            )

        # Cross-agent artifacts.
        for i, slot in enumerate(self._spread(3, 0.2, 0.9)):
            agent = self.agents[i % len(self.agents)]
            artifact = self.artifacts[i % len(self.artifacts)]
            code = _code(rng, "DOC")
            self._schedule(
                slot,
                _Event(
                    kind="artifact",
                    turns=[
                        (
                            "user",
                            f"For the record: the {agent} produced the {artifact} today "
                            f"and filed it under reference {code}.",
                        ),
                        (
                            "assistant",
                            f"Logged - {artifact} delivered by the {agent}, " f"reference {code}.",
                        ),
                    ],
                    entities=[
                        {"name": agent, "type": "agent", "attributes": {}},
                        {"name": artifact, "type": "artifact", "attributes": {"reference": code}},
                    ],
                    relationships=[
                        {
                            "from": agent,
                            "from_type": "agent",
                            "type": "produced",
                            "to": artifact,
                            "to_type": "artifact",
                            "attributes": {"reference": code},
                            "confidence": 0.85,
                        }
                    ],
                    payload={"agent": agent, "artifact": artifact, "code": code},
                ),
            )

        # Exact-string business codes (invoice / ticket ids).
        for i, slot in enumerate(self._spread(2, 0.3, 0.8)):
            person = people[(i + 2) % len(people)]
            kind, prefix = [("invoice", "INV"), ("support ticket", "TKT")][i % 2]
            code = _code(rng, prefix)
            project = self.projects[(i + 1) % len(self.projects)]
            self._schedule(
                slot,
                _Event(
                    kind="code_fact",
                    turns=[
                        (
                            "user",
                            f"{person} opened {kind} {code} for the {project}. "
                            f"Keep that reference handy.",
                        ),
                        (
                            "assistant",
                            f"Saved: {kind} {code} ({project}, opened by {person}).",
                        ),
                    ],
                    entities=[
                        {"name": person, "type": "person", "attributes": {}},
                        {
                            "name": code,
                            "type": "reference",
                            "attributes": {"kind": kind, "project": project},
                        },
                    ],
                    relationships=[
                        {
                            "from": person,
                            "from_type": "person",
                            "type": "opened",
                            "to": code,
                            "to_type": "reference",
                            "attributes": {"kind": kind, "project": project},
                            "confidence": 0.85,
                        }
                    ],
                    payload={"person": person, "kind": kind, "code": code, "project": project},
                ),
            )

        # Temporal validity: a role change for one person (same employer).
        person = people[0]
        old_role_event = next(
            e for _, e in self.events if e.kind == "employment" and e.payload["person"] == person
        )
        old_role = old_role_event.payload["role"]
        new_role = next(r for r in ROLES if r != old_role)
        change_slot = self._spread(1, 0.55, 0.7)[0]
        self._schedule(
            change_slot,
            _Event(
                kind="role_change",
                turns=[
                    (
                        "user",
                        f"Heads up: {person} moved from {old_role} to {new_role} at "
                        f"{company} this week.",
                    ),
                    (
                        "assistant",
                        f"Updated. {person} is now {new_role} at {company}; previously "
                        f"{old_role}.",
                    ),
                ],
                entities=[{"name": person, "type": "person", "attributes": {"role": new_role}}],
                relationships=[
                    {
                        "from": person,
                        "from_type": "person",
                        "type": "works_at",
                        "to": company,
                        "to_type": "company",
                        "attributes": {"role": new_role},
                        "confidence": 0.9,
                    }
                ],
                payload={
                    "person": person,
                    "old_role": old_role,
                    "new_role": new_role,
                    "company": company,
                },
            ),
        )

        # Contradiction 1: conflicting employer (exclusive works_at).
        person_c = people[1]
        other_company = self.companies[1]
        contra_slot = self._spread(1, 0.7, 0.85)[0]
        self._schedule(
            contra_slot,
            _Event(
                kind="contradiction_works_at",
                turns=[
                    (
                        "user",
                        f"Wait - I heard {person_c} actually works at {other_company}, "
                        f"not {company}.",
                    ),
                    (
                        "assistant",
                        f"That conflicts with my earlier record of {person_c} at {company}; "
                        f"flagging both until confirmed.",
                    ),
                ],
                entities=[{"name": other_company, "type": "company", "attributes": {}}],
                relationships=[
                    {
                        "from": person_c,
                        "from_type": "person",
                        "type": "works_at",
                        "to": other_company,
                        "to_type": "company",
                        "attributes": {},
                        "confidence": 0.85,
                    }
                ],
                payload={
                    "person": person_c,
                    "old_object": company,
                    "new_object": other_company,
                    "predicate": "works_at",
                },
            ),
        )

        # Contradiction 2: conflicting home city (exclusive lives_in).
        person_l = people[2]
        city_a, city_b = self.cities[0], self.cities[1]
        base_slot = self._spread(1, 0.05, 0.2)[0]
        self._schedule(
            base_slot,
            _Event(
                kind="residence",
                turns=[
                    (
                        "user",
                        f"{person_l} is based in {city_a}, so schedule calls in their " f"morning.",
                    ),
                    ("assistant", f"Got it - {person_l} lives in {city_a}."),
                ],
                entities=[
                    {"name": person_l, "type": "person", "attributes": {}},
                    {"name": city_a, "type": "location", "attributes": {}},
                ],
                relationships=[
                    {
                        "from": person_l,
                        "from_type": "person",
                        "type": "lives_in",
                        "to": city_a,
                        "to_type": "location",
                        "attributes": {},
                        "confidence": 0.85,
                    }
                ],
                payload={"person": person_l, "city": city_a},
            ),
        )
        contra_slot_2 = self._spread(1, 0.8, 0.95)[0]
        self._schedule(
            contra_slot_2,
            _Event(
                kind="contradiction_lives_in",
                turns=[
                    ("user", f"Correction from HR: {person_l} lives in {city_b}."),
                    (
                        "assistant",
                        f"That contradicts the earlier note that {person_l} is "
                        f"based in {city_a}; flagging the conflict.",
                    ),
                ],
                entities=[{"name": city_b, "type": "location", "attributes": {}}],
                relationships=[
                    {
                        "from": person_l,
                        "from_type": "person",
                        "type": "lives_in",
                        "to": city_b,
                        "to_type": "location",
                        "attributes": {},
                        "confidence": 0.85,
                    }
                ],
                payload={
                    "person": person_l,
                    "old_object": city_a,
                    "new_object": city_b,
                    "predicate": "lives_in",
                },
            ),
        )

        # Precision distractor: a duplicate re-assertion that must NOT be
        # flagged as a contradiction (same subject, predicate, and object).
        dup_slot = self._spread(1, 0.85, 1.0)[0]
        dup_person = people[0]
        self._schedule(
            dup_slot,
            _Event(
                kind="duplicate_fact",
                turns=[
                    (
                        "user",
                        f"Just double-checking: {dup_person} is still at {company}, " f"right?",
                    ),
                    ("assistant", f"Correct, {dup_person} works at {company}."),
                ],
                relationships=[
                    {
                        "from": dup_person,
                        "from_type": "person",
                        "type": "works_at",
                        "to": company,
                        "to_type": "company",
                        "attributes": {},
                        "confidence": 0.85,
                    }
                ],
                payload={"person": dup_person, "company": company},
            ),
        )

    # -- session rendering ----------------------------------------------------

    def _render_sessions(self) -> None:
        by_session: Dict[int, List[_Event]] = {}
        for slot, event in self.events:
            by_session.setdefault(slot, []).append(event)

        for index in range(self.n_sessions):
            session_id = f"{self.case_id}_s{index + 1:02d}"
            session_date = _iso(self.session_dates[index])
            agent_id = self.agents[index % len(self.agents)]
            turns: List[Dict[str, str]] = []

            def _add_turn(role: str, content: str) -> str:
                turn_id = f"{session_id}:{len(turns)}"
                turns.append({"role": role, "content": content})
                return turn_id

            # Opening distractor exchange keeps fact turns from always
            # sitting at index 0.
            opener = DISTRACTOR_EXCHANGES[(index + len(self.case_id)) % len(DISTRACTOR_EXCHANGES)]
            _add_turn("user", opener[0])
            _add_turn("assistant", opener[1])

            for event in by_session.get(index, []):
                fact_turn_id: Optional[str] = None
                for turn_index, (role, content) in enumerate(event.turns):
                    turn_id = _add_turn(role, content)
                    if turn_index == 0:
                        fact_turn_id = turn_id
                assert fact_turn_id is not None
                self._emit_ground_truth(event, session_id, fact_turn_id, session_date)

            # Closing distractor on longer sessions.
            if index % 2 == 0:
                closer = DISTRACTOR_EXCHANGES[
                    (index + 3 + len(self.case_id)) % len(DISTRACTOR_EXCHANGES)
                ]
                _add_turn("user", closer[0])
                _add_turn("assistant", closer[1])

            self.sessions.append(
                {
                    "session_id": session_id,
                    "date": session_date,
                    "agent_id": agent_id,
                    "turns": turns,
                }
            )

        self._emit_log_entries(by_session)

    def _emit_ground_truth(
        self, event: _Event, session_id: str, turn_id: str, session_date: str
    ) -> None:
        for entity in event.entities:
            self.entities.append(
                GTEntity(
                    name=entity["name"],
                    type=entity["type"],
                    attributes=dict(entity.get("attributes") or {}),
                    session_id=session_id,
                    turn_id=turn_id,
                )
            )
        for rel in event.relationships:
            attributes = dict(rel.get("attributes") or {})
            attributes.setdefault("stated_on", session_date)
            if event.kind == "employment":
                attributes.setdefault("valid_from", session_date)
            if event.kind == "role_change":
                attributes.setdefault("valid_from", session_date)
            self.relationships.append(
                GTRelationship(
                    from_name=rel["from"],
                    from_type=rel["from_type"],
                    type=rel["type"],
                    to_name=rel["to"],
                    to_type=rel["to_type"],
                    attributes=attributes,
                    confidence=rel["confidence"],
                    session_id=session_id,
                    turn_id=turn_id,
                )
            )
        if event.kind.startswith("contradiction"):
            payload = event.payload
            old_turn = self._find_assertion_turn(
                payload["person"], payload["predicate"], payload["old_object"]
            )
            self.contradictions.append(
                GTContradiction(
                    subject=payload["person"],
                    predicate=payload["predicate"],
                    old_object=payload["old_object"],
                    new_object=payload["new_object"],
                    old_turn_id=old_turn or "",
                    new_turn_id=turn_id,
                )
            )
        if event.kind == "role_change":
            # Close the previous employment window in the manifest (the
            # temporal ground truth; the KG merge path has no temporal
            # model yet - that gap is what this category measures).
            payload = event.payload
            for i, rel in enumerate(self.relationships):
                if (
                    rel.from_name == payload["person"]
                    and rel.type == "works_at"
                    and rel.attributes.get("role") == payload["old_role"]
                ):
                    closed = dict(rel.attributes)
                    closed["valid_to"] = session_date
                    self.relationships[i] = GTRelationship(
                        from_name=rel.from_name,
                        from_type=rel.from_type,
                        type=rel.type,
                        to_name=rel.to_name,
                        to_type=rel.to_type,
                        attributes=closed,
                        confidence=rel.confidence,
                        session_id=rel.session_id,
                        turn_id=rel.turn_id,
                    )

    def _find_assertion_turn(self, subject: str, predicate: str, obj: str) -> Optional[str]:
        for rel in self.relationships:
            if rel.from_name == subject and rel.type == predicate and rel.to_name == obj:
                return rel.turn_id
        return None

    def _emit_log_entries(self, by_session: Dict[int, List[_Event]]) -> None:
        """One Captain's-Log entry per day that carried at least one event."""
        for index in sorted(by_session):
            events = by_session[index]
            session_id = f"{self.case_id}_s{index + 1:02d}"
            session_date = _iso(self.session_dates[index])
            decisions = [e.decision for e in events if e.decision]
            projects = sorted({e.project for e in events if e.project})
            highlights = []
            for event in events:
                if event.kind == "artifact":
                    highlights.append(
                        f"the {event.payload['agent']} delivered the "
                        f"{event.payload['artifact']}"
                    )
                elif event.kind == "recommendation":
                    highlights.append(
                        f"{event.payload['person']} recommended {event.payload['tech']} "
                        f"for the {event.payload['project']}"
                    )
                elif event.kind == "role_change":
                    highlights.append(
                        f"{event.payload['person']} moved to {event.payload['new_role']}"
                    )
            summary = (
                f"Work on {session_date}: " + "; ".join(highlights)
                if highlights
                else f"Routine coordination on {session_date}."
            )
            self.log_entries.append(
                GTLogEntry(
                    date=session_date,
                    summary=summary,
                    decisions=decisions,
                    projects=projects,
                    source_session_ids=[session_id],
                )
            )

    # -- question generation --------------------------------------------------

    def _next_question_id(self, category: str) -> str:
        self._question_counter += 1
        return f"{self.case_id}_q{self._question_counter:03d}_{category}"

    def _events_of(self, kind: str) -> List[Tuple[int, _Event]]:
        return [(slot, e) for slot, e in self.events if e.kind == kind]

    def _session_id_for(self, slot: int) -> str:
        return f"{self.case_id}_s{slot + 1:02d}"

    def _turn_for_event(self, slot: int, event: _Event) -> Tuple[str, str]:
        """Locate (session_id, turn_id) of an event's fact turn via ground truth."""
        session_id = self._session_id_for(slot)
        for rel in self.relationships:
            if rel.session_id == session_id and rel.from_name == (
                event.relationships[0]["from"] if event.relationships else None
            ):
                if rel.type == event.relationships[0]["type"]:
                    return session_id, rel.turn_id
        # Entity-only events.
        for ent in self.entities:
            if ent.session_id == session_id:
                return session_id, ent.turn_id
        raise LookupError(f"No ground truth found for event in {session_id}")

    def _build_questions(self) -> None:
        n = self.questions_per_category

        # kg_relationship: employment / recommendation / exact-string lookups.
        kg_pool: List[GTQuestion] = []
        for slot, event in self._events_of("recommendation"):
            p = event.payload
            session_id, turn_id = self._turn_for_event(slot, event)
            kg_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_KG,
                    question=f"Who recommended using {p['tech']} for the {p['project']}?",
                    answer=p["person"],
                    evidence_session_ids=[session_id],
                    evidence_turn_ids=[turn_id],
                )
            )
        for slot, event in self._events_of("employment"):
            p = event.payload
            session_id, turn_id = self._turn_for_event(slot, event)
            kg_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_KG,
                    question=f"What is {p['person']}'s email address?",
                    answer=p["email"],
                    evidence_session_ids=[session_id],
                    evidence_turn_ids=[turn_id],
                    exact_strings=[p["email"]],
                )
            )
        for slot, event in self._events_of("code_fact"):
            p = event.payload
            session_id, turn_id = self._turn_for_event(slot, event)
            kg_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_KG,
                    question=(
                        f"What was the reference number of the {p['kind']} {p['person']} "
                        f"opened for the {p['project']}?"
                    ),
                    answer=p["code"],
                    evidence_session_ids=[session_id],
                    evidence_turn_ids=[turn_id],
                    exact_strings=[p["code"]],
                )
            )

        # temporal_validity: role before/after the change.
        temporal_pool: List[GTQuestion] = []
        for slot, event in self._events_of("role_change"):
            p = event.payload
            change_session, change_turn = self._turn_for_event(slot, event)
            original = next(
                e for _, e in self._events_of("employment") if e.payload["person"] == p["person"]
            )
            original_slot = next(s for s, e in self._events_of("employment") if e is original)
            orig_session, orig_turn = self._turn_for_event(original_slot, original)
            before_date = _iso(self.session_dates[original_slot])
            temporal_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_TEMPORAL,
                    question=(
                        f"What was {p['person']}'s role at {p['company']} on "
                        f"{before_date}, before any later changes?"
                    ),
                    answer=p["old_role"],
                    evidence_session_ids=[orig_session],
                    evidence_turn_ids=[orig_turn],
                    date_from=before_date,
                    date_to=before_date,
                )
            )
            temporal_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_TEMPORAL,
                    question=f"What is {p['person']}'s current role at {p['company']}?",
                    answer=p["new_role"],
                    evidence_session_ids=[change_session],
                    evidence_turn_ids=[change_turn],
                )
            )

        # narrative_recall: decisions of a given day (Captain's Log).
        narrative_pool: List[GTQuestion] = []
        for entry in self.log_entries:
            if not entry.decisions:
                continue
            narrative_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_NARRATIVE,
                    question=f"What were the main decisions made on {entry.date}?",
                    answer="; ".join(entry.decisions),
                    evidence_session_ids=list(entry.source_session_ids),
                    evidence_turn_ids=[],
                    date_from=entry.date,
                    date_to=entry.date,
                )
            )
        for entry in self.log_entries:
            if entry.projects:
                narrative_pool.append(
                    GTQuestion(
                        question_id="",
                        category=CATEGORY_NARRATIVE,
                        question=(f"Which projects saw activity on {entry.date}?"),
                        answer=", ".join(entry.projects),
                        evidence_session_ids=list(entry.source_session_ids),
                        evidence_turn_ids=[],
                        date_from=entry.date,
                        date_to=entry.date,
                    )
                )

        # cross_agent: artifact attribution + exact-string references.
        cross_pool: List[GTQuestion] = []
        for slot, event in self._events_of("artifact"):
            p = event.payload
            session_id, turn_id = self._turn_for_event(slot, event)
            cross_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_CROSS_AGENT,
                    question=f"Which agent produced the {p['artifact']}?",
                    answer=p["agent"],
                    evidence_session_ids=[session_id],
                    evidence_turn_ids=[turn_id],
                )
            )
            cross_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_CROSS_AGENT,
                    question=(
                        f"Under what reference number did the {p['agent']} file the "
                        f"{p['artifact']}?"
                    ),
                    answer=p["code"],
                    evidence_session_ids=[session_id],
                    evidence_turn_ids=[turn_id],
                    exact_strings=[p["code"]],
                )
            )

        # contradiction_detection: surface the conflict.
        contradiction_pool: List[GTQuestion] = []
        for contradiction in self.contradictions:
            evidence_turns = [
                t for t in (contradiction.old_turn_id, contradiction.new_turn_id) if t
            ]
            evidence_sessions = sorted({t.split(":")[0] for t in evidence_turns})
            subject = contradiction.subject
            if contradiction.predicate == "works_at":
                question = f"Which company does {subject} work at?"
            else:
                question = f"Which city does {subject} live in?"
            contradiction_pool.append(
                GTQuestion(
                    question_id="",
                    category=CATEGORY_CONTRADICTION,
                    question=question,
                    answer=(
                        f"Conflicting information: {contradiction.old_object} and "
                        f"{contradiction.new_object} were both stated; the conflict is "
                        f"unresolved."
                    ),
                    evidence_session_ids=evidence_sessions,
                    evidence_turn_ids=evidence_turns,
                )
            )

        for pool in (kg_pool, temporal_pool, narrative_pool, cross_pool, contradiction_pool):
            self.rng.shuffle(pool)
            # Exact-string recall is the Phase 6 (hybrid/BM25) decision
            # metric: guarantee at least one exact-string question per
            # category that has any, then fill from the shuffled rest.
            exact = [q for q in pool if q.exact_strings]
            rest = [q for q in pool if not q.exact_strings]
            chosen = (exact[:1] + rest + exact[1:])[:n]
            for question in sorted(chosen, key=pool.index):
                question.question_id = self._next_question_id(question.category)
                self.questions.append(question)

    # -- output ---------------------------------------------------------------

    def build(self) -> Dict[str, Any]:
        self._build_events()
        self._render_sessions()
        self._build_questions()
        return {
            "case_id": self.case_id,
            "scenario": self.scenario,
            "sessions": self.sessions,
            "questions": [asdict(question) for question in self.questions],
            "ground_truth": {
                "entities": [asdict(entity) for entity in self.entities],
                "relationships": [asdict(rel) for rel in self.relationships],
                "log_entries": [asdict(entry) for entry in self.log_entries],
                "contradictions": [asdict(c) for c in self.contradictions],
            },
        }


def generate_dataset(
    sequences: int = 3,
    sessions_per_sequence: Optional[int] = 12,
    questions_per_category: int = 2,
    seed: int = DEFAULT_SEED,
) -> Dict[str, Any]:
    """Generate the structured-recall dataset as a plain dict.

    Deterministic: identical arguments produce an identical dict (and,
    through :func:`write_dataset`, byte-identical files).
    """
    cases = [
        _SequenceBuilder(
            index=i,
            seed=seed,
            sessions_per_sequence=sessions_per_sequence,
            questions_per_category=questions_per_category,
        ).build()
        for i in range(sequences)
    ]
    return {
        "name": DATASET_NAME,
        "schema_version": DATASET_SCHEMA_VERSION,
        "generator": {
            "seed": seed,
            "sequences": sequences,
            "sessions_per_sequence": sessions_per_sequence,
            "questions_per_category": questions_per_category,
            "categories": list(CATEGORIES),
        },
        "cases": cases,
    }


def write_dataset(dataset: Dict[str, Any], path: Path) -> Path:
    """Write a dataset dict as deterministic, sorted-key JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(dataset, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the Tier 2 structured-recall corpus + Q&A dataset "
            "(deterministic, seeded; no LLM calls)."
        )
    )
    parser.add_argument("--preset", choices=sorted(PRESETS), default=None)
    parser.add_argument("--sequences", type=int, default=3)
    parser.add_argument(
        "--sessions-per-sequence",
        type=int,
        default=12,
        help="Sessions per sequence; 0 samples 10-30 per sequence (PRD full-scale).",
    )
    parser.add_argument("--questions-per-category", type=int, default=2)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args(argv)

    kwargs: Dict[str, Any] = {
        "sequences": args.sequences,
        "sessions_per_sequence": args.sessions_per_sequence or None,
        "questions_per_category": args.questions_per_category,
        "seed": args.seed,
    }
    if args.preset:
        kwargs.update(PRESETS[args.preset])
        kwargs["seed"] = args.seed

    dataset = generate_dataset(**kwargs)
    path = write_dataset(dataset, Path(args.output))
    questions = sum(len(case["questions"]) for case in dataset["cases"])
    sessions = sum(len(case["sessions"]) for case in dataset["cases"])
    print(
        f"Wrote {path}: {len(dataset['cases'])} sequences, {sessions} sessions, "
        f"{questions} questions (seed={kwargs['seed']})"
    )
    return 0


if __name__ == "__main__":
    import sys

    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(main())
