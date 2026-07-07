"""Real-formation adapter for the memory benchmarks.

The harness never mocks the memory stack: every run boots an actual
:class:`muxi.runtime.formation.Formation` (SQLite persistent memory,
FAISS working memory, local ONNX embeddings by default) and drives it
through the same public APIs the runtime uses in production.

Isolation model
---------------
- Each benchmark case is ingested under its own ``user_id``
  (``bench-{benchmark}-{case_id}``), so persistent-memory rows from
  one case can never surface in another case's retrieval.
- Working memory is cleared between cases (``WorkingMemory.clear()``)
  because its FIFO capacity is global; per-case ingestion + clearing
  keeps every haystack fully resident during its questions.
- Each run gets a fresh run directory (temp dir by default) holding a
  rendered ``formation.yaml`` with a run-local SQLite path, so runs
  never see each other's databases.

Retrieval modes
---------------
- ``working``      — FAISS working-memory search only.
- ``persistent``   — SQLite (sqlite-vec) persistent-memory search only.
- ``combined``     — both backends, merged with Reciprocal Rank Fusion
  (scores are on different scales across backends; RRF is scale-free).

The "combined + KG routing" mode from the PRD's mode table is out of
scope for Tier 1 (it depends on per-turn KG extraction; see README).
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from .datasets import Question, Session
from .scoring import ranked_unique, reciprocal_rank_fusion

MODES = ("working", "persistent", "combined")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORMATION_YAML = Path(__file__).resolve().parent / "formation" / "formation.yaml"
DEFAULT_SECRETS_DIR = REPO_ROOT / "e2e" / "assets"

# Local embedding inputs are capped defensively; the default local
# model (nomic v1.5) has an 8k-token context. Truncations are counted
# and reported so silent clipping never skews published numbers.
DEFAULT_MAX_EMBED_CHARS = 6000

_ANSWER_SYSTEM_PROMPT = (
    "You answer questions about a user's past conversations. Base your "
    "answer ONLY on the provided conversation excerpts. If the question "
    "asks for advice, a plan, or a recommendation, give one that honors "
    "what the excerpts say about the user (preferences, restrictions, "
    "facts). If the excerpts lack the information needed, say you do not "
    "know. Answer concisely."
)

_JUDGE_PROMPT = """You are grading a memory system's answer against the ground truth.

Question: {question}
Ground-truth answer: {gold}
System answer: {predicted}

Reply with exactly one word: CORRECT if the system answer conveys the same
information as the ground truth (wording may differ), otherwise INCORRECT.
If the ground truth states a requirement or preference the answer must
respect (for example a dietary restriction), the system answer is CORRECT
when it satisfies that requirement. If the ground truth indicates the
question is unanswerable or that there is no information, the system answer
is CORRECT only if it also declines or states the information is
unavailable."""


@dataclass
class RetrievedItem:
    """One retrieval result mapped back to benchmark ids."""

    turn_id: str
    session_id: str
    text: str
    score: float
    source: str


class MuxiMemoryAdapter:
    """Drives a real MUXI formation through ingest / search / QA."""

    def __init__(
        self,
        mode: str,
        formation_yaml: Optional[Path] = None,
        run_dir: Optional[Path] = None,
        secrets_dir: Optional[Path] = None,
        max_embed_chars: int = DEFAULT_MAX_EMBED_CHARS,
    ):
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode} (expected one of {MODES})")
        self.mode = mode
        self.formation_yaml = Path(formation_yaml or DEFAULT_FORMATION_YAML)
        self.run_dir = Path(run_dir) if run_dir else None
        self.secrets_dir = Path(secrets_dir or DEFAULT_SECRETS_DIR)
        self.max_embed_chars = max_embed_chars

        self.formation = None
        self.overlord = None
        self._token_context = None
        self.llm_requests = 0
        self.ingested_turns = 0
        self.truncated_turns = 0
        self.searches = 0

    # -- lifecycle ---------------------------------------------------------

    def _prepare_run_dir(self) -> Path:
        """Render the benchmark formation into an isolated run directory."""
        if self.run_dir is None:
            import tempfile

            self.run_dir = Path(tempfile.mkdtemp(prefix="muxi-membench-"))
        self.run_dir.mkdir(parents=True, exist_ok=True)

        with open(self.formation_yaml, "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)

        # Run-local SQLite database so concurrent/consecutive runs never
        # share state.
        persistent = config.setdefault("memory", {}).setdefault("persistent", {})
        persistent["connection_string"] = str(self.run_dir / "membench.db")

        # Run-local conversation event log (keeps stdout readable and
        # leaves an auditable JSONL trail per run).
        streams = config.get("logging", {}).get("conversation", {}).get("streams", [])
        for stream in streams:
            if stream.get("transport") == "file":
                stream["destination"] = str(self.run_dir / "membench-events.jsonl")

        rendered = self.run_dir / "formation.yaml"
        with open(rendered, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)

        # Secrets: same symlink strategy as the e2e suite (the .key file
        # is gitignored; secrets.enc is committed under e2e/assets).
        for name in (".key", "secrets.enc"):
            source = self.secrets_dir / name
            target = self.run_dir / name
            if target.exists() or target.is_symlink():
                continue
            if source.exists():
                try:
                    target.symlink_to(source)
                except OSError:
                    shutil.copy2(source, target)
        return rendered

    async def start(self) -> None:
        """Load the formation, boot the overlord, and arm token tracking."""
        from muxi.runtime.datatypes.observability import RequestContext
        from muxi.runtime.formation import Formation
        from muxi.runtime.services.observability.context import set_request_context

        rendered = self._prepare_run_dir()
        self.formation = Formation()
        await self.formation.load(str(rendered))
        self.overlord = await self.formation.start_overlord()

        # In server mode this is called after startup; the harness runs
        # the formation bare, so activate the configured file stream
        # here. Conversation events (model.request.*, memory.*) then go
        # to the run-local JSONL instead of stdout.
        from muxi.runtime.formation.initialization import enable_conversation_logging

        enable_conversation_logging(self.formation)

        if self.mode in ("working", "combined") and self.overlord.buffer_memory is None:
            raise RuntimeError("Working memory is not configured on the benchmark formation")
        if self.mode in ("persistent", "combined") and self.overlord.long_term_memory is None:
            raise RuntimeError("Persistent memory is not configured on the benchmark formation")

        # Cumulative token tally: every LLM call made by this task
        # (QA answers, judging, cloud embeddings if configured) lands in
        # this context's TokenUsage.
        self._token_context = RequestContext(id=f"membench-{uuid.uuid4().hex[:12]}")
        set_request_context(self._token_context)

    async def stop(self) -> None:
        if self.formation is not None:
            await self.formation.stop_overlord()

    # -- ingestion ---------------------------------------------------------

    def _render_turn_text(self, session: Session, turn) -> str:
        prefix = f"[{session.date}] " if session.date else ""
        text = f"{prefix}{turn.role}: {turn.content}"
        if len(text) > self.max_embed_chars:
            self.truncated_turns += 1
            text = text[: self.max_embed_chars]
        return text

    async def ingest_session(self, user_id: str, session: Session) -> None:
        """Ingest one session turn-by-turn into the mode's backends."""
        for turn in session.turns:
            text = self._render_turn_text(session, turn)
            if not text.strip():
                continue
            metadata = {
                "user_id": user_id,
                "bench_session_id": session.session_id,
                "bench_turn_id": turn.turn_id,
                "role": turn.role,
            }
            if self.mode in ("working", "combined"):
                await self.overlord.buffer_memory.add(text, metadata=dict(metadata))
            if self.mode in ("persistent", "combined"):
                await self.overlord.long_term_memory.add(
                    content=text,
                    metadata=dict(metadata),
                    user_id=user_id,
                    collection="conversations",
                )
            self.ingested_turns += 1

    def clear_case(self) -> None:
        """Reset working memory between cases (FIFO capacity is global)."""
        if self.overlord is not None and self.overlord.buffer_memory is not None:
            self.overlord.buffer_memory.clear()

    # -- retrieval ---------------------------------------------------------

    @staticmethod
    def _items_from_working(results: Sequence[Dict[str, Any]]) -> List[RetrievedItem]:
        items = []
        for result in results:
            metadata = result.get("metadata") or {}
            turn_id = metadata.get("bench_turn_id")
            session_id = metadata.get("bench_session_id")
            if not turn_id or not session_id:
                continue
            items.append(
                RetrievedItem(
                    turn_id=str(turn_id),
                    session_id=str(session_id),
                    text=str(result.get("text", "")),
                    score=float(result.get("score", 0.0)),
                    source="working",
                )
            )
        return items

    @staticmethod
    def _items_from_persistent(results: Sequence[Dict[str, Any]]) -> List[RetrievedItem]:
        items = []
        for result in results:
            metadata = result.get("metadata") or {}
            turn_id = metadata.get("bench_turn_id")
            session_id = metadata.get("bench_session_id")
            if not turn_id or not session_id:
                continue
            items.append(
                RetrievedItem(
                    turn_id=str(turn_id),
                    session_id=str(session_id),
                    text=str(result.get("text", "")),
                    score=float(result.get("score", 0.0)),
                    source="persistent",
                )
            )
        return items

    async def search(self, user_id: str, query: str, fetch_limit: int) -> List[RetrievedItem]:
        """Turn-level retrieval, ranked best-first, for one question."""
        self.searches += 1
        working_items: List[RetrievedItem] = []
        persistent_items: List[RetrievedItem] = []

        if self.mode in ("working", "combined"):
            raw = await self.overlord.buffer_memory.search(
                query,
                limit=fetch_limit,
                filter_metadata={"user_id": user_id},
                recency_bias=0.0,
                namespace="buffer",
            )
            working_items = self._items_from_working(raw)

        if self.mode in ("persistent", "combined"):
            raw = await self.overlord.long_term_memory.search(
                query,
                limit=fetch_limit,
                user_id=user_id,
                scopes=["user"],
            )
            persistent_items = self._items_from_persistent(raw)

        if self.mode == "working":
            return working_items
        if self.mode == "persistent":
            return persistent_items

        # Combined: scale-free rank fusion over turn ids, then map the
        # fused ranking back to items (working copy preferred for text).
        by_turn: Dict[str, RetrievedItem] = {}
        for item in persistent_items + working_items:
            by_turn[item.turn_id] = item
        fused = reciprocal_rank_fusion(
            [
                [item.turn_id for item in working_items],
                [item.turn_id for item in persistent_items],
            ]
        )
        return [by_turn[turn_id] for turn_id in fused[:fetch_limit]]

    @staticmethod
    def ranked_session_ids(items: Sequence[RetrievedItem]) -> List[str]:
        """Session ranking derived from the turn ranking (best turn wins)."""
        return ranked_unique(item.session_id for item in items)

    @staticmethod
    def ranked_turn_ids(items: Sequence[RetrievedItem]) -> List[str]:
        return ranked_unique(item.turn_id for item in items)

    # -- QA (end-to-end answer accuracy) ------------------------------------

    async def answer_question(
        self, question: Question, items: Sequence[RetrievedItem], context_limit: int
    ) -> str:
        """Answer ``question`` from the top retrieved excerpts."""
        model = await self.overlord.get_model_for_capability("text")
        context = "\n".join(f"- {item.text}" for item in items[:context_limit] if item.text.strip())
        if not context:
            context = "(no relevant excerpts were retrieved)"
        user_message = (
            f"Conversation excerpts (most relevant first):\n{context}\n\n"
            f"Question: {question.question}"
        )
        self.llm_requests += 1
        response = await model.chat(
            messages=[
                {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
        )
        return str(response).strip()

    async def judge_answer(self, question: Question, predicted: str) -> bool:
        """LLM-as-judge: does ``predicted`` match the gold answer?"""
        model = await self.overlord.get_model_for_capability("text")
        prompt = _JUDGE_PROMPT.format(
            question=question.question,
            gold=question.answer if question.answer is not None else "(unanswerable)",
            predicted=predicted,
        )
        self.llm_requests += 1
        response = await model.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=8,
        )
        return str(response).strip().upper().startswith("CORRECT")

    # -- usage reporting -----------------------------------------------------

    def usage_snapshot(self) -> Dict[str, Any]:
        """Token/cost usage for the run (from the request-context tally)."""
        from .report import estimate_cost_usd

        tokens = {"total": 0, "in": 0, "out": 0}
        breakdown: Dict[str, List[int]] = {}
        if self._token_context is not None:
            usage = self._token_context.tokens
            tokens = {
                "total": usage.total[0],
                "in": usage.total[1],
                "out": usage.total[2],
                "total_cached": usage.total[3],
            }
            breakdown = {model: list(fields) for model, fields in usage.breakdown.items()}
        return {
            "llm_requests": self.llm_requests,
            "tokens": tokens,
            "tokens_by_model": breakdown,
            "cost": estimate_cost_usd(breakdown),
            "ingested_turns": self.ingested_turns,
            "truncated_turns": self.truncated_turns,
            "searches": self.searches,
        }

    def config_snapshot(self) -> Dict[str, Any]:
        """Echo the effective configuration into the report."""
        from .report import relativize

        config: Dict[str, Any] = {
            "mode": self.mode,
            "formation_yaml": relativize(self.formation_yaml, REPO_ROOT),
            "max_embed_chars": self.max_embed_chars,
        }
        if self.overlord is not None and self.overlord.buffer_memory is not None:
            config["working_embedding_model"] = self.overlord.buffer_memory.embedding_model_name
        capability_models = getattr(self.formation, "_capability_models", None) or {}
        text_model = capability_models.get("text") or {}
        if isinstance(text_model, dict) and text_model.get("model"):
            config["text_model"] = text_model["model"]
        return config
