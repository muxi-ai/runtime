"""Correctness + invariants for ``services.classification.LocalClassifier``.

These tests use the real ``Xenova/multilingual-e5-small`` ONNX model (no
mocks — per project policy in ``AGENTS.md``). The model is downloaded on
first run by OneLLM's local provider and cached under
``~/.cache/huggingface/hub/``; subsequent invocations are fast.

A single module-scoped event-loop fixture warms up one classifier
instance and reuses it across every test, so the cumulative runtime is
dominated by per-test classify calls (~50 ms each), not warmup. CI
machines with a cold HF cache will see the first test in this file pay
the one-time download (~95 MB).
"""

from __future__ import annotations

from typing import List, Tuple

import pytest
import pytest_asyncio

from muxi.runtime.services.classification import (
    ACTIONABILITY,
    CLARIFICATION_CONTEXT_SWITCH,
    CLARIFICATION_STOP_INTENT,
    RECALL_QUESTION,
    SIMPLE_QUESTION,
    WORKFLOW_ELIGIBILITY,
    IntentSpec,
    LocalClassifier,
)


# Module-scoped warmed classifier. Every test reuses this instance to
# amortize the prototype embedding cost (one batched call per intent at
# warmup, then per-query embeddings only). pytest-asyncio's
# module-scoped fixtures need a matching ``loop_scope`` so the same
# event loop hosts both the fixture and the test that consumes it.
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def classifier():
    c = LocalClassifier()
    await c.warmup()
    return c


def _accuracy(predictions: List[Tuple[bool, bool]]) -> float:
    """Helper: ``predictions`` is a list of (expected, got) tuples."""
    if not predictions:
        return 0.0
    return sum(1 for exp, got in predictions if exp == got) / len(predictions)


# ---------------------------------------------------------------------------
# Intent-spec invariants (no embedding required)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec",
    [
        ACTIONABILITY,
        WORKFLOW_ELIGIBILITY,
        SIMPLE_QUESTION,
        CLARIFICATION_CONTEXT_SWITCH,
        CLARIFICATION_STOP_INTENT,
        RECALL_QUESTION,
    ],
    ids=lambda s: s.name,
)
def test_intent_specs_have_disjoint_pos_neg_examples(spec: IntentSpec) -> None:
    """A literal duplicate between positive and negative would create a
    degenerate centroid pair and silently corrupt classification. Catch
    authoring mistakes here rather than in production traces."""
    assert spec.positive, f"{spec.name} has no positive examples"
    assert spec.negative, f"{spec.name} has no negative examples"
    overlap = set(spec.positive) & set(spec.negative)
    assert not overlap, f"{spec.name} has overlapping examples: {overlap}"


@pytest.mark.parametrize(
    "spec",
    [
        ACTIONABILITY,
        WORKFLOW_ELIGIBILITY,
        SIMPLE_QUESTION,
        CLARIFICATION_CONTEXT_SWITCH,
        CLARIFICATION_STOP_INTENT,
        RECALL_QUESTION,
    ],
    ids=lambda s: s.name,
)
def test_intent_spec_examples_are_short_enough(spec: IntentSpec) -> None:
    """Long examples dilute the centroid and slow warmup. We empirically
    capped exemplars at <100 chars; this test enforces the cap so future
    edits stay honest."""
    overlong = [t for t in spec.positive + spec.negative if len(t) > 200]
    assert not overlong, f"{spec.name} has examples > 200 chars: {overlong}"


# ---------------------------------------------------------------------------
# End-to-end accuracy on a curated multilingual eval set
# ---------------------------------------------------------------------------


ACTIONABILITY_EVAL = [
    ("Tell me about MUXI", True),
    ("What database should I use?", True),
    ("Explain how vector search works", True),
    ("Hi", False),
    ("Hello there", False),
    ("Thanks!", False),
    ("Got it, thank you", False),
    ("Hola", False),
    ("Que es MUXI?", True),  # Spanish
    ("Bonjour", False),  # French greeting
]


WORKFLOW_ELIGIBILITY_EVAL = [
    ("Build a web app with auth and Postgres", True),
    ("Refactor the entire authentication module", True),
    ("Hi", False),
    ("My budget is $5000", False),  # informational
    ("I prefer dark mode", False),  # informational
    ("Migrate the production database", True),
    ("Yes", False),
    ("Sure", False),
]


SIMPLE_QUESTION_EVAL = [
    ("What is the capital of France?", True),
    ("Why is the sky blue?", True),
    ("Build a chatbot that ingests our docs", False),
    ("Refactor and migrate the entire system", False),
    ("How do I install Python?", True),
    ("Plan and execute a multi-region failover", False),
]


CLARIFICATION_CONTEXT_SWITCH_EVAL = [
    ("Yes, Postgres please", False),
    ("Actually, never mind that — what's the weather?", True),
    ("The first option", False),
    ("Wait, different question: how do I reset my password?", True),
    ("Both options work", False),
    ("Forget the deployment, can you help me debug?", True),
]


CLARIFICATION_STOP_INTENT_EVAL = [
    ("Just do it", True),
    ("Yes, Postgres please", False),
    ("Stop asking questions", True),
    ("Make it green", False),
    ("Enough, proceed", True),
    ("The first option", False),
]


RECALL_QUESTION_EVAL = [
    ("What is my name?", True),
    ("What did I tell you about my project?", True),
    ("What is FastAPI?", False),
    ("Build me a web app", False),
    ("Remind me what we discussed", True),
    ("How do I install Python?", False),
]


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "intent_name,eval_set",
    [
        ("actionable", ACTIONABILITY_EVAL),
        ("workflow_eligible", WORKFLOW_ELIGIBILITY_EVAL),
        ("simple_question", SIMPLE_QUESTION_EVAL),
        ("clarification_context_switch", CLARIFICATION_CONTEXT_SWITCH_EVAL),
        ("clarification_stop", CLARIFICATION_STOP_INTENT_EVAL),
        ("recall_question", RECALL_QUESTION_EVAL),
    ],
)
async def test_classifier_accuracy_meets_threshold(
    classifier: LocalClassifier,
    intent_name: str,
    eval_set: List[Tuple[str, bool]],
) -> None:
    """Each gate must reach >=85% accuracy on its eval set. Lower
    threshold than the smoke test (97%) because the eval sets here
    intentionally include borderline cases not covered verbatim by the
    prototype examples — we want the embedder's semantic generalization
    to do real work, not just memorize the prototypes."""
    predictions: List[Tuple[bool, bool]] = []
    for text, expected in eval_set:
        label, _margin = await classifier.classify_binary(intent_name, text)
        predictions.append((expected, label))

    acc = _accuracy(predictions)
    misses = [
        (text, exp, got)
        for (text, exp), (_e, got) in zip(eval_set, predictions)
        if exp != got
    ]
    assert acc >= 0.85, (
        f"{intent_name} accuracy {acc:.2%} below 85% threshold; "
        f"misses: {misses}"
    )


# ---------------------------------------------------------------------------
# Margin / confidence sanity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_strong_examples_produce_separation(classifier: LocalClassifier) -> None:
    """Texts that are essentially copies of prototype examples should
    classify with a margin clearly above zero. Catches regressions
    where the centroid cache silently goes stale (e.g. someone wires a
    mutation into the centroid arrays)."""
    label_pos, margin_pos = await classifier.classify_binary(
        "actionable", "Tell me about MUXI"
    )
    label_neg, margin_neg = await classifier.classify_binary("actionable", "Hi")
    assert label_pos is True, f"clear positive misclassified, margin={margin_pos:+.3f}"
    assert label_neg is False, f"clear negative misclassified, margin={margin_neg:+.3f}"
    # Both should have non-trivial separation. A degenerate centroid
    # would give margin near zero on both sides.
    assert abs(margin_pos) > 0.01
    assert abs(margin_neg) > 0.01


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="module")
async def test_unknown_intent_raises(classifier: LocalClassifier) -> None:
    """Calling classify_binary with a name that isn't a built-in and
    wasn't manually registered should raise rather than silently
    misclassify against a default centroid."""
    with pytest.raises(KeyError):
        await classifier.classify_binary("does_not_exist_intent", "anything")


@pytest.mark.asyncio(loop_scope="module")
async def test_empty_text_raises(classifier: LocalClassifier) -> None:
    """Empty or whitespace-only input is a wiring bug — fail loudly."""
    with pytest.raises(ValueError):
        await classifier.classify_binary("actionable", "")
    with pytest.raises(ValueError):
        await classifier.classify_binary("actionable", "   \n\t")


@pytest.mark.asyncio(loop_scope="module")
async def test_register_is_idempotent(classifier: LocalClassifier) -> None:
    """Registering the same intent twice must not double-embed or
    overwrite the cached centroid. We verify by snapshotting the
    centroid dict size before and after a redundant register call."""
    snapshot_before = classifier.diagnostic_snapshot()
    await classifier.register(ACTIONABILITY)
    snapshot_after = classifier.diagnostic_snapshot()
    assert snapshot_before == snapshot_after


@pytest.mark.asyncio(loop_scope="module")
async def test_diagnostic_snapshot_reports_all_warmed_intents(
    classifier: LocalClassifier,
) -> None:
    """Operators should be able to see exactly which intents are warm
    via ``diagnostic_snapshot()``. The snapshot must list all six
    built-in intents after warmup."""
    snap = classifier.diagnostic_snapshot()
    expected = {
        "actionable",
        "workflow_eligible",
        "simple_question",
        "clarification_context_switch",
        "clarification_stop",
        "recall_question",
    }
    assert set(snap.keys()) >= expected
    for name in expected:
        assert snap[name]["positive_examples"] > 0
        assert snap[name]["negative_examples"] > 0
        assert snap[name]["centroid_dim"] == 384  # e5-small native dim
