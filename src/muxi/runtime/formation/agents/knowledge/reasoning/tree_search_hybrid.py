# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Tree Search Hybrid - Parallel A+B with Sufficiency Evaluator
# Description:  Runs Method A (LLM tree navigation) and Method B (value
#               scoring) in parallel, dedup-merges by node_id, and loops a
#               small agentic sufficiency evaluator to decide whether to
#               fetch more nodes
# Role:         Retrieval-side component of reasoning-based RAG (hybrid mode)
# Usage:        Invoked by KnowledgeHandler.search for ``retrieval: hybrid``
#               sources
# Author:       Muxi Framework Team
#
# Flow per query:
#
#   A (LLM nav)  --+
#                  +--> dedup queue (node_id) --> fetch raw --> sufficiency
#   B (scoring)  --+                                   ^            |
#                                                      |   gaps -> expand
#                                                      +------------+
#
# The sufficiency evaluator is a dedicated single LLM call with structured
# output ({"enough_info": bool, "gaps": [...], "reasoning": "..."}) using
# the terminator model (``knowledge.tree.terminator_model``, resolved
# through the model hierarchy; defaults to the tree model). It is NOT the
# formation's main agent and is NOT routed through the workflow planner.
#
# Loop bounds (runaway-cost guards):
#   * max_sufficiency_rounds (default 3)
#   * max_fetched_nodes_pct  (default 50% of the tree's nodes)
#   * evaluator failure -> return the current fetched set, warning event
#
# Cost note: every LLM call here passes ``caching=False`` - evaluation
# prompts over the same tree differ only by the (short) query/content, so
# the semantic response cache would replay verdicts from unrelated queries
# (the same class of bug as Method A navigation; see mental-model.md).
# Token accounting flows through the standard LLM events tagged with the
# ``component`` metadata below; the retrieval results additionally carry a
# ``cost`` metadata block (llm_calls / evaluator_rounds) per the PRD.
# =============================================================================

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .....services import observability
from .scoring_service import ScoringService
from .tree_builder import extract_json_object
from .tree_search_a import TreeSearchA
from .tree_search_b import TreeSearchB
from .types import (
    DEFAULT_TREE_SETTINGS,
    RetrievalResult,
    TreeIndex,
    TreeNavigationError,
)

# Cap on raw content characters per fetched node (same guard as A and B).
_MAX_NODE_CONTENT_CHARS = 6000

# Cap on fetched-content characters shown to the sufficiency evaluator.
# Keeps the evaluator prompt inside cheap-model context windows.
_MAX_EVALUATOR_CONTEXT_CHARS = 24000

_EVALUATOR_SYSTEM_PROMPT = (
    "You judge whether retrieved document content is sufficient to answer a "
    "user query. Given the query and the content fetched so far, decide if "
    "enough information has been gathered. If not, list the specific topics "
    "that are still missing (short noun phrases, not questions). Respond ONLY "
    'with a JSON object of the form {"enough_info": true|false, '
    '"gaps": ["<topic>", ...], "reasoning": "<brief>"}. No markdown, no '
    "extra keys."
)


@dataclass
class SufficiencyVerdict:
    """Structured output of one sufficiency evaluator call."""

    enough_info: bool
    gaps: List[str] = field(default_factory=list)
    reasoning: str = ""


class SufficiencyEvaluator:
    """
    Dedicated single-call LLM evaluator for hybrid retrieval sufficiency.

    Args:
        llm: Object exposing ``async chat(messages, **kwargs) -> str`` (the
            runtime ``LLM`` class) - the resolved terminator model.
    """

    def __init__(self, llm: Any):
        self.llm = llm

    async def evaluate(self, query: str, fetched_contents: List[str]) -> SufficiencyVerdict:
        """
        Evaluate whether ``fetched_contents`` suffices to answer ``query``.

        Raises:
            TreeNavigationError: On LLM failure or unusable structured
                output (the hybrid runner treats this as "stop expanding").
        """
        combined = "\n\n---\n\n".join(c for c in fetched_contents if c)
        combined = combined[:_MAX_EVALUATOR_CONTEXT_CHARS]
        messages = [
            {"role": "system", "content": _EVALUATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Query: {query}\n\nFetched content:\n{combined}",
            },
        ]
        try:
            # caching=False + temperature 0.1: see module frontmatter (the
            # semantic cache replays verdicts across unrelated queries, and
            # LLM.chat coerces falsy temperatures to the instance default).
            # Explicit max_tokens decouples the structured verdict from any
            # formation-level chat cap.
            response = await self.llm.chat(
                messages=messages,
                temperature=0.1,
                max_tokens=400,
                caching=False,
                metadata={"component": "knowledge_tree_sufficiency"},
            )
            parsed = extract_json_object(response)
        except Exception as e:
            raise TreeNavigationError(f"Sufficiency evaluation failed: {e}") from e

        if not isinstance(parsed.get("enough_info"), bool):
            raise TreeNavigationError("Sufficiency evaluator returned no 'enough_info' bool")
        gaps_raw = parsed.get("gaps") or []
        gaps = (
            [str(g).strip() for g in gaps_raw if str(g).strip()]
            if isinstance(gaps_raw, list)
            else []
        )
        return SufficiencyVerdict(
            enough_info=parsed["enough_info"],
            gaps=gaps,
            reasoning=str(parsed.get("reasoning", "")),
        )


class TreeSearchHybrid:
    """
    Hybrid retriever: parallel A+B, node dedup, sufficiency-gated expansion.

    Args:
        llm: Tree navigation model (Method A).
        scoring_service: Shared scoring service (Method B + gap expansion).
        terminator_llm: Model for the sufficiency evaluator. Defaults to
            ``llm`` when not provided (resolution through the model
            hierarchy happens in the agent wiring, not here).
        settings: The effective ``knowledge.tree`` settings dict (missing
            keys take :data:`DEFAULT_TREE_SETTINGS` defaults).
    """

    def __init__(
        self,
        llm: Any,
        scoring_service: ScoringService,
        terminator_llm: Optional[Any] = None,
        settings: Optional[Dict[str, Any]] = None,
    ):
        merged = dict(DEFAULT_TREE_SETTINGS)
        merged.update(settings or {})
        self.search_a = TreeSearchA(llm)
        self.search_b = TreeSearchB(scoring_service)
        self.scoring = scoring_service
        self.evaluator = SufficiencyEvaluator(terminator_llm or llm)
        self.max_sufficiency_rounds = max(0, int(merged["max_sufficiency_rounds"]))
        self.max_fetched_nodes_pct = min(100, max(1, int(merged["max_fetched_nodes_pct"])))

    async def search(
        self, query: str, tree: TreeIndex, max_nodes: int = 3
    ) -> List[RetrievalResult]:
        """
        Run hybrid retrieval over ``tree`` for ``query``.

        Raises:
            TreeNavigationError: Only when BOTH Method A and Method B fail
                (the caller then falls back to vector results). A single
                method failing degrades to the other's results.
        """
        a_task = asyncio.create_task(self.search_a.search(query, tree, max_nodes=max_nodes))
        b_task = asyncio.create_task(self.search_b.search(query, tree, max_nodes=max_nodes))
        a_out, b_out = await asyncio.gather(a_task, b_task, return_exceptions=True)

        a_results = a_out if isinstance(a_out, list) else []
        b_results = b_out if isinstance(b_out, list) else []
        errors = [out for out in (a_out, b_out) if isinstance(out, BaseException)]
        if len(errors) == 2:
            raise TreeNavigationError(
                f"Hybrid retrieval failed for '{tree.document}': "
                f"method A: {errors[0]}; method B: {errors[1]}"
            )

        # Dedup queue keyed on node_id, order-preserving (A first: its
        # selections are reasoning-backed; B refines and extends).
        fetched: Dict[str, RetrievalResult] = {}
        for result in a_results + b_results:
            node_id = result.metadata.get("node_id")
            if node_id and node_id not in fetched:
                fetched[node_id] = result

        observability.observe(
            event_type=observability.SystemEvents.KNOWLEDGE_TREE_HYBRID_QUEUED,
            level=observability.EventLevel.DEBUG,
            description="Hybrid A+B results dedup-merged",
            data={
                "document": tree.document,
                "queue_size": len(fetched),
                "method_a_count": len(a_results),
                "method_b_count": len(b_results),
                "method_a_failed": isinstance(a_out, BaseException),
                "method_b_failed": isinstance(b_out, BaseException),
            },
        )

        # LLM-call accounting for the cost metadata block: Method A is one
        # call when it succeeded; each evaluator round adds one.
        llm_calls = 0 if isinstance(a_out, BaseException) else 1
        evaluator_rounds = 0

        max_fetched_nodes = max(1, (tree.node_count * self.max_fetched_nodes_pct) // 100)

        for _ in range(self.max_sufficiency_rounds):
            if not fetched:
                break
            if len(fetched) >= max_fetched_nodes:
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_TREE_HYBRID_LOOP_CAPPED,
                    level=observability.EventLevel.WARNING,
                    description="Hybrid fetched-node cap reached before sufficiency",
                    data={
                        "document": tree.document,
                        "fetched_nodes": len(fetched),
                        "max_fetched_nodes": max_fetched_nodes,
                        "cap": "max_fetched_nodes_pct",
                    },
                )
                break

            try:
                verdict = await self.evaluator.evaluate(
                    query, [r.content for r in fetched.values()]
                )
            except TreeNavigationError as e:
                # Evaluator failure -> serve what we have (PRD loop bound 3).
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_TREE_SUFFICIENCY_EVALUATED,
                    level=observability.EventLevel.WARNING,
                    description="Sufficiency evaluator failed - serving fetched set",
                    data={"document": tree.document, "error": str(e), "failed": True},
                )
                break
            evaluator_rounds += 1
            llm_calls += 1

            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_TREE_SUFFICIENCY_EVALUATED,
                level=observability.EventLevel.DEBUG,
                description="Sufficiency evaluator verdict",
                data={
                    "document": tree.document,
                    "round": evaluator_rounds,
                    "enough_info": verdict.enough_info,
                    "gaps": verdict.gaps[:5],
                    "fetched_nodes": len(fetched),
                },
            )

            if verdict.enough_info:
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_TREE_HYBRID_TERMINATED_EARLY,
                    level=observability.EventLevel.DEBUG,
                    description="Hybrid retrieval terminated early (sufficient)",
                    data={
                        "document": tree.document,
                        "rounds_used": evaluator_rounds,
                        "max_rounds": self.max_sufficiency_rounds,
                        "fetched_nodes": len(fetched),
                    },
                )
                break

            more = await self._fetch_for_gaps(
                tree, verdict.gaps, exclude=set(fetched), budget=max_fetched_nodes - len(fetched)
            )
            if not more:
                break  # nothing new to fetch - avoid an infinite loop
            for result in more:
                fetched[result.metadata["node_id"]] = result
        else:
            if self.max_sufficiency_rounds:
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_TREE_HYBRID_LOOP_CAPPED,
                    level=observability.EventLevel.WARNING,
                    description="Hybrid sufficiency loop reached max rounds",
                    data={
                        "document": tree.document,
                        "rounds_used": evaluator_rounds,
                        "max_rounds": self.max_sufficiency_rounds,
                        "fetched_nodes": len(fetched),
                        "cap": "max_sufficiency_rounds",
                    },
                )

        cost = {
            "llm_calls": llm_calls,
            "evaluator_rounds": evaluator_rounds,
            "embedding_lookups": 0 if isinstance(b_out, BaseException) else 1,
        }
        results = list(fetched.values())
        for result in results:
            result.metadata.setdefault("retrieval_method", "hybrid")
            result.metadata["hybrid"] = True
            result.metadata["cost"] = cost
        return results

    async def _fetch_for_gaps(
        self,
        tree: TreeIndex,
        gaps: List[str],
        exclude: set,
        budget: int,
    ) -> List[RetrievalResult]:
        """
        Expand the fetched set: score each gap topic against unfetched nodes.

        Uses Method B scoring (embeddings are always present in hybrid mode
        at build time; when they are missing - e.g. the embedding pass
        failed at ingestion - expansion is skipped and the loop terminates).
        """
        if budget <= 0 or not gaps or not tree.chunk_embeddings:
            return []
        added: List[RetrievalResult] = []
        source_type = "agent_tree" if tree.scope == "agent" else "tree"
        for gap in gaps[:budget]:
            try:
                candidates = await self.search_b.search(gap, tree, max_nodes=budget + len(exclude))
            except TreeNavigationError:
                continue
            for candidate in candidates:
                node_id = candidate.metadata.get("node_id")
                if not node_id or node_id in exclude:
                    continue
                candidate.source_type = source_type
                candidate.metadata["gap_topic"] = gap
                candidate.metadata["retrieval_method"] = "hybrid_gap_expansion"
                added.append(candidate)
                exclude.add(node_id)
                break  # one best new node per gap topic
            if len(added) >= budget:
                break
        return added
