"""Unit tests for hybrid tree retrieval (reasoning-RAG Phase 3).

Pins the Phase 3 conventions:

  * Parallel A+B with node dedup by node_id (A's picks lead).
  * Sufficiency evaluator loop bounds: ``max_sufficiency_rounds`` and
    ``max_fetched_nodes_pct`` cap expansion; evaluator failure serves the
    current fetched set; enough_info terminates early.
  * Semantic-cache bypass: EVERY reasoning LLM call (navigation, summary,
    sufficiency) passes ``caching=False`` - the Method A lesson.
  * Degradation: one method failing serves the other's results; both
    failing raises (handler then falls back to vector).
  * Cost metadata (llm_calls / evaluator_rounds) on every result.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from muxi.runtime.formation.agents.knowledge.reasoning import (
    ScoringService,
    SufficiencyEvaluator,
    TreeBuilder,
    TreeNavigationError,
    TreeSearchHybrid,
    build_node_chunk_embeddings,
)
from muxi.runtime.utils.fastjson import json

STRUCTURED_DOC = "\n".join(
    [
        "# Device Manual",
        "General overview of the device. " * 30,
        "## Installation",
        "To install, run the bootstrap installer. " * 30,
        "### Requirements",
        "Requires FIRMWARE-X9 and a powered hub. " * 30,
        "## Troubleshooting",
        "If the light blinks, apply RESET-CODE-77. " * 30,
        "## Warranty",
        "Coverage lasts 24 months from purchase. " * 30,
    ]
)

KEYWORDS = ("install", "firmware", "reset", "overview", "warranty")


async def keyword_embeddings_fn(texts):
    vecs = []
    for text in texts:
        lowered = text.lower()
        vecs.append([float(lowered.count(k)) for k in KEYWORDS] + [0.001])
    return vecs


class FakeLLM:
    """Deterministic LLM covering summary, navigation, and sufficiency prompts.

    Records every call's kwargs so tests can assert the semantic-cache
    bypass (caching=False) on each reasoning call.
    """

    def __init__(self, node_list=None, verdicts=None, fail_navigation=False):
        self.calls = []
        self.node_list = node_list if node_list is not None else ["0004"]
        # One verdict dict per sufficiency round; the last repeats.
        self.verdicts = verdicts or [{"enough_info": True, "gaps": []}]
        self.fail_navigation = fail_navigation
        self.sufficiency_calls = 0
        self.navigation_calls = 0

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        content = messages[-1]["content"]
        system = messages[0]["content"]
        node_ids = re.findall(r"node_id: (\d{4})", content)
        if node_ids:  # tree-builder summary pass
            return json.dumps({"summaries": {i: f"Covers topic {i}" for i in node_ids}})
        if "sufficient" in system or "enough information" in system:
            index = min(self.sufficiency_calls, len(self.verdicts) - 1)
            self.sufficiency_calls += 1
            verdict = dict(self.verdicts[index])
            verdict.setdefault("reasoning", "test verdict")
            return json.dumps(verdict)
        # Method A navigation
        self.navigation_calls += 1
        if self.fail_navigation:
            raise RuntimeError("simulated navigation outage")
        return json.dumps({"thinking": "picked", "node_list": self.node_list})


def build_tree(llm=None):
    llm = llm or FakeLLM()
    builder = TreeBuilder(llm=llm, settings={"max_tokens_per_node": 2000})
    tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))
    scoring = ScoringService(keyword_embeddings_fn)
    asyncio.run(build_node_chunk_embeddings(tree, scoring))
    return tree


def make_hybrid(llm, settings=None, scoring=None, terminator_llm=None):
    return TreeSearchHybrid(
        llm=llm,
        scoring_service=scoring or ScoringService(keyword_embeddings_fn),
        terminator_llm=terminator_llm,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


class TestDedup:
    def test_overlapping_a_and_b_results_dedupe_by_node_id(self):
        tree = build_tree()
        # Find the node B will rank first for the reset query, then make A
        # select the same node - the union must contain it exactly once.
        from muxi.runtime.formation.agents.knowledge.reasoning import TreeSearchB

        b_results = asyncio.run(
            TreeSearchB(ScoringService(keyword_embeddings_fn)).search(
                "reset blinking light", tree, max_nodes=1
            )
        )
        overlap_id = b_results[0].metadata["node_id"]

        llm = FakeLLM(node_list=[overlap_id])
        hybrid = make_hybrid(llm)
        results = asyncio.run(hybrid.search("reset blinking light", tree, max_nodes=2))

        node_ids = [r.metadata["node_id"] for r in results]
        assert len(node_ids) == len(set(node_ids)), "results must be unique per node"
        assert node_ids.count(overlap_id) == 1

    def test_union_of_disjoint_selections(self):
        tree = build_tree()
        nodes = [n.node_id for n in tree.walk() if tree.fetch_raw(n.node_id)]
        a_pick = nodes[0]
        llm = FakeLLM(node_list=[a_pick])
        hybrid = make_hybrid(llm)

        results = asyncio.run(hybrid.search("install firmware", tree, max_nodes=2))
        node_ids = {r.metadata["node_id"] for r in results}
        assert a_pick in node_ids, "Method A's pick must be in the union"
        assert len(node_ids) >= 2, "Method B extends the queue"


# ---------------------------------------------------------------------------
# Sufficiency loop bounds
# ---------------------------------------------------------------------------


class TestSufficiencyLoop:
    def test_terminates_early_when_sufficient(self):
        tree = build_tree()
        llm = FakeLLM(verdicts=[{"enough_info": True, "gaps": []}])
        hybrid = make_hybrid(llm, settings={"max_sufficiency_rounds": 3})

        results = asyncio.run(hybrid.search("reset", tree, max_nodes=1))

        assert llm.sufficiency_calls == 1, "sufficient verdict must stop the loop"
        assert results
        assert results[0].metadata["cost"]["evaluator_rounds"] == 1

    def test_loop_stops_at_max_sufficiency_rounds(self):
        tree = build_tree()
        llm = FakeLLM(verdicts=[{"enough_info": False, "gaps": ["warranty coverage"]}])
        hybrid = make_hybrid(llm, settings={"max_sufficiency_rounds": 2})

        asyncio.run(hybrid.search("reset", tree, max_nodes=1))

        assert llm.sufficiency_calls <= 2, "loop must respect max_sufficiency_rounds"

    def test_zero_rounds_disables_the_evaluator(self):
        tree = build_tree()
        llm = FakeLLM()
        hybrid = make_hybrid(llm, settings={"max_sufficiency_rounds": 0})

        results = asyncio.run(hybrid.search("reset", tree, max_nodes=1))

        assert llm.sufficiency_calls == 0
        assert results, "A+B union is still served"

    def test_gap_expansion_fetches_new_nodes(self):
        tree = build_tree()
        llm = FakeLLM(
            verdicts=[
                {"enough_info": False, "gaps": ["warranty coverage period"]},
                {"enough_info": True, "gaps": []},
            ]
        )
        hybrid = make_hybrid(llm, settings={"max_sufficiency_rounds": 3})

        results = asyncio.run(hybrid.search("reset the device", tree, max_nodes=1))

        expanded = [r for r in results if r.metadata.get("gap_topic")]
        assert expanded, "gap expansion should add a node for the gap topic"
        assert any("24 months" in r.content for r in expanded), "warranty node expected"

    def test_fetched_nodes_cap_stops_expansion(self):
        tree = build_tree()
        llm = FakeLLM(verdicts=[{"enough_info": False, "gaps": ["warranty", "install"]}])
        # 1% of a small tree floors to a cap of 1 fetched node
        hybrid = make_hybrid(
            llm, settings={"max_sufficiency_rounds": 5, "max_fetched_nodes_pct": 1}
        )

        results = asyncio.run(hybrid.search("reset", tree, max_nodes=1))

        assert len(results) <= 2, "cap must bound the fetched set"
        assert llm.sufficiency_calls <= 1

    def test_evaluator_failure_serves_current_set(self):
        tree = build_tree()

        class FailingEvaluatorLLM(FakeLLM):
            async def chat(self, messages, **kwargs):
                system = messages[0]["content"]
                if "enough information" in system or "sufficient" in system:
                    raise RuntimeError("evaluator outage")
                return await super().chat(messages, **kwargs)

        llm = FailingEvaluatorLLM()
        hybrid = make_hybrid(llm, settings={"max_sufficiency_rounds": 3})

        results = asyncio.run(hybrid.search("reset", tree, max_nodes=1))
        assert results, "evaluator failure must not drop the A+B union"

    def test_malformed_verdict_raises_navigation_error(self):
        evaluator = SufficiencyEvaluator(FakeLLM(verdicts=[{"gaps": []}]))
        with pytest.raises(TreeNavigationError):
            asyncio.run(evaluator.evaluate("q", ["content"]))


# ---------------------------------------------------------------------------
# Degradation and failure isolation
# ---------------------------------------------------------------------------


class TestDegradation:
    def test_method_a_failure_serves_method_b_results(self):
        tree = build_tree()
        llm = FakeLLM(fail_navigation=True)
        hybrid = make_hybrid(llm)

        results = asyncio.run(hybrid.search("reset blinking light", tree, max_nodes=2))

        assert results, "Method B results must survive an A outage"
        assert all(r.metadata["retrieval_method"] != "tree_a" for r in results)

    def test_method_b_failure_serves_method_a_results(self):
        tree = build_tree()
        nodes = [n.node_id for n in tree.walk() if tree.fetch_raw(n.node_id)]
        llm = FakeLLM(node_list=[nodes[0]])

        async def broken(texts):
            raise RuntimeError("embedding provider down")

        hybrid = make_hybrid(llm, scoring=ScoringService(broken))
        results = asyncio.run(hybrid.search("reset", tree, max_nodes=2))

        assert results
        assert {r.metadata["node_id"] for r in results} == {nodes[0]}

    def test_both_methods_failing_raises(self):
        tree = build_tree()
        llm = FakeLLM(fail_navigation=True)

        async def broken(texts):
            raise RuntimeError("embedding provider down")

        hybrid = make_hybrid(llm, scoring=ScoringService(broken))
        with pytest.raises(TreeNavigationError):
            asyncio.run(hybrid.search("reset", tree, max_nodes=2))


# ---------------------------------------------------------------------------
# Semantic-cache bypass + terminator model + cost metadata
# ---------------------------------------------------------------------------


class TestCallHygiene:
    def test_every_reasoning_llm_call_bypasses_the_semantic_cache(self):
        """Navigation, summary, and sufficiency calls all pass caching=False.

        The Method A lesson: prompts over the same tree differ only by the
        short query, so the semantic response cache would replay selections
        and verdicts from unrelated queries.
        """
        llm = FakeLLM(
            verdicts=[
                {"enough_info": False, "gaps": ["warranty"]},
                {"enough_info": True, "gaps": []},
            ]
        )
        tree = build_tree(llm=llm)  # summary calls also land on this llm
        hybrid = make_hybrid(llm)
        asyncio.run(hybrid.search("reset", tree, max_nodes=1))

        assert llm.calls, "expected LLM traffic"
        for call in llm.calls:
            assert call["kwargs"].get("caching") is False, (
                "reasoning call must bypass the semantic response cache: "
                f"{call['messages'][0]['content'][:60]}"
            )
            assert call["kwargs"].get("temperature") not in (None, 0.0)

    def test_terminator_llm_receives_the_sufficiency_calls(self):
        tree = build_tree()
        navigator = FakeLLM()
        terminator = FakeLLM(verdicts=[{"enough_info": True, "gaps": []}])
        hybrid = make_hybrid(navigator, terminator_llm=terminator)

        asyncio.run(hybrid.search("reset", tree, max_nodes=1))

        assert terminator.sufficiency_calls == 1
        assert navigator.sufficiency_calls == 0

    def test_results_carry_cost_metadata(self):
        tree = build_tree()
        llm = FakeLLM(verdicts=[{"enough_info": True, "gaps": []}])
        hybrid = make_hybrid(llm)

        results = asyncio.run(hybrid.search("reset", tree, max_nodes=2))

        for result in results:
            cost = result.metadata["cost"]
            assert cost["llm_calls"] == 2  # 1 navigation + 1 evaluator
            assert cost["evaluator_rounds"] == 1
            assert result.metadata["hybrid"] is True
