"""Local prototype-similarity classifier for binary pre-planning gates.

The classifier embeds the query string with a local ONNX model
(``local/Xenova/multilingual-e5-small`` by default) and computes its
cosine similarity against the centroid of each pre-registered intent's
positive and negative example sets. The label with the larger centroid
similarity wins; the absolute difference is returned as a confidence
margin for diagnostic purposes.

Why prototype similarity, not a trained classifier?
---------------------------------------------------

Trained classifiers (logistic regression, SVM, fine-tuned head) would
edge out prototype similarity on accuracy if we had hundreds of
labelled examples per gate. We don't. We have ~10-25 hand-curated
exemplars per gate. Prototype similarity matches the data we have,
needs no training step, and is trivially extensible — adding a new
gate is just adding an :class:`~.prototypes.IntentSpec`.

Why e5-small, not Nomic?
------------------------

Nomic v1.5 (the runtime's default embedding model) is excellent for
retrieval-style search but is English-strong rather than multilingual.
The e5-small variant ships from Xenova as a 384-dim ONNX model
(~95 MB) explicitly tuned for cross-lingual semantic similarity. The
binary gates need to work for users typing in Spanish, Japanese, etc.,
so the multilingual encoder is the right pick. Both options pass
through OneLLM's local provider and are downloaded lazily on first
use.

Concurrency
-----------

``register`` is idempotent and guarded by an internal asyncio lock so
concurrent first-touch classify calls don't double-embed the prototype
sets. ``classify_binary`` itself is lock-free — embedding the query
and dotting against cached centroids is independent across calls.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Dict, Tuple

from .. import observability
from ..memory.embedding import embed
from .prototypes import ALL_INTENTS, IntentSpec

DEFAULT_CLASSIFIER_MODEL = "local/Xenova/multilingual-e5-small"
"""384-dim multilingual ONNX encoder used as the default classification
backend. Lazily downloaded by OneLLM's local provider on first use and
cached under ``$HF_HOME``. Override via the ``model`` constructor kwarg
on :class:`LocalClassifier` if a deployment ships a different model in
its SIF cache."""


@dataclass
class _Centroids:
    """Per-intent cached centroid vectors after L2-normalization.

    Centroids are unit vectors; cosine similarity reduces to a dot
    product. Storing as plain ``list[float]`` keeps the module free of
    a hard numpy dependency at import time — we only need numpy at
    classify time and the runtime already pulls it in transitively.
    """

    positive: list[float]
    negative: list[float]


def _l2_normalize(vec: list[float]) -> list[float]:
    """Return ``vec`` rescaled to unit length, or a zero vector if it is
    already zero. We do this in pure Python to avoid the numpy import at
    register time; the resulting list is converted to a numpy array
    inside :meth:`LocalClassifier.classify_binary` for the dot product.
    """
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return list(vec)
    return [v / norm for v in vec]


def _centroid(vectors: list[list[float]]) -> list[float]:
    """Mean-pool a batch of vectors and L2-normalize the result.

    The local provider already L2-normalizes per-text outputs, but the
    mean of unit vectors is not itself a unit vector. We renormalize so
    the cosine-similarity reduction at classify time is a clean dot
    product rather than dot / (norm_a * norm_b).
    """
    if not vectors:
        raise ValueError("Cannot compute centroid of an empty vector list")
    dim = len(vectors[0])
    accum = [0.0] * dim
    for vec in vectors:
        if len(vec) != dim:
            raise ValueError(
                f"Vector dimension mismatch in centroid: expected {dim}, " f"got {len(vec)}"
            )
        for i, v in enumerate(vec):
            accum[i] += v
    n = float(len(vectors))
    mean = [v / n for v in accum]
    return _l2_normalize(mean)


class LocalClassifier:
    """Async, lazy-init prototype-similarity classifier.

    Typical lifecycle::

        classifier = LocalClassifier()
        await classifier.warmup()  # optional; first classify_binary auto-warms
        label, margin = await classifier.classify_binary("actionable", text)

    The classifier is safe to share across coroutines once warmed.
    """

    def __init__(self, model: str = DEFAULT_CLASSIFIER_MODEL) -> None:
        self.model = model
        self._centroids: Dict[str, _Centroids] = {}
        self._specs: Dict[str, IntentSpec] = {}
        self._register_lock = asyncio.Lock()
        self._warmed = False

    @property
    def is_warmed(self) -> bool:
        """``True`` once :meth:`warmup` has finished registering all
        built-in intents. Useful for diagnostics and tests."""
        return self._warmed

    async def warmup(self) -> None:
        """Eagerly register every intent from
        :data:`~.prototypes.ALL_INTENTS`. Safe to call multiple times;
        re-registration is a no-op once an intent's centroid is cached.

        The first call to ``warmup`` (or to :meth:`classify_binary` on a
        cold classifier) downloads ``self.model`` from HuggingFace if it
        isn't already cached on disk — typically ~95 MB for e5-small.
        Subsequent process starts read from the HF cache.
        """
        for spec in ALL_INTENTS:
            await self.register(spec)
        self._warmed = True

    async def register(self, spec: IntentSpec) -> None:
        """Embed ``spec``'s positive and negative example sets and cache
        their centroids under ``spec.name``.

        Idempotent: a second register call for the same name is a
        no-op. Uses an asyncio lock so concurrent first-touch
        :meth:`classify_binary` calls on the same intent don't both pay
        the embed cost.
        """
        if spec.name in self._centroids:
            return

        async with self._register_lock:
            # Re-check inside the lock — another waiter may have
            # registered while we were blocked.
            if spec.name in self._centroids:
                return

            if not spec.positive or not spec.negative:
                raise ValueError(
                    f"IntentSpec {spec.name!r} must have at least one "
                    f"positive and one negative example"
                )

            # The e5 family is trained with prefix conventions:
            # "query: ..." for retrieval queries and "passage: ..." for
            # the indexed corpus. For symmetric semantic-similarity use
            # like ours the official guidance is to use "query: " on
            # both sides — the prefix is a fixed instruction, not a
            # role tag. Other local models (Nomic, BGE) ignore unknown
            # prefixes gracefully so this is safe across backends.
            positive_inputs = [f"query: {t}" for t in spec.positive]
            negative_inputs = [f"query: {t}" for t in spec.negative]

            try:
                pos_vecs = await embed(self.model, positive_inputs)
                neg_vecs = await embed(self.model, negative_inputs)
            except Exception as exc:
                observability.observe(
                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "intent": spec.name,
                        "model": self.model,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "phase": "classifier_register",
                    },
                    description=(
                        f"Local classifier prototype embedding failed for "
                        f"intent {spec.name!r}: {exc}"
                    ),
                )
                raise

            self._centroids[spec.name] = _Centroids(
                positive=_centroid(pos_vecs),
                negative=_centroid(neg_vecs),
            )
            self._specs[spec.name] = spec

    async def classify_binary(self, name: str, text: str) -> Tuple[bool, float]:
        """Classify ``text`` against the registered intent ``name``.

        Returns
        -------
        tuple[bool, float]
            ``(label, margin)`` where ``label`` is ``True`` when the
            query is closer to the positive centroid than the negative
            centroid, and ``margin`` is ``cos_sim(query, positive) -
            cos_sim(query, negative)`` clamped to ``[-1.0, 1.0]``.

            A ``margin`` near zero indicates the prototypes don't
            disambiguate the query well — useful for diagnostic logs
            but not used by the gate itself, since gates have safe
            defaults already and we don't fall back to LLM in Phase 1.

        Raises
        ------
        KeyError
            If ``name`` was never registered (call :meth:`warmup` or
            :meth:`register` first). Stricter than silently defaulting
            so wiring bugs surface immediately in tests.
        """
        if not text or not text.strip():
            # Empty input is a wiring bug, not user data. Embedding it
            # would raise inside ``embed()``; we surface a clearer error.
            raise ValueError(f"classify_binary({name!r}) called with empty text")

        # Auto-register on first use if a built-in intent was requested
        # but warmup wasn't called explicitly. Keeps the call sites in
        # overlord/clarification simple.
        if name not in self._centroids:
            spec = next((s for s in ALL_INTENTS if s.name == name), None)
            if spec is None:
                raise KeyError(
                    f"Unknown classification intent {name!r}. "
                    f"Registered: {sorted(self._centroids)}"
                )
            await self.register(spec)

        centroids = self._centroids[name]
        query_vec = (await embed(self.model, [f"query: {text}"]))[0]
        query_unit = _l2_normalize(query_vec)

        sim_pos = sum(a * b for a, b in zip(query_unit, centroids.positive))
        sim_neg = sum(a * b for a, b in zip(query_unit, centroids.negative))
        margin = max(-1.0, min(1.0, sim_pos - sim_neg))

        return sim_pos > sim_neg, margin

    async def pairwise_similarity(self, text_a: str, text_b: str) -> float:
        """Cosine similarity between two texts using the embedding model.

        Direct replacement for any LLM call that asks "how similar are
        these two texts?" — semantic similarity scoring, prompt-change
        detection, fusion-quality assessment. No prototype centroid is
        involved; we just embed both inputs and dot the L2-normalized
        vectors.

        Returns
        -------
        float
            Cosine similarity in ``[-1.0, 1.0]``. For natural-language
            text the practical range is ``[0.0, 1.0]``: identical or
            paraphrased text approaches 1.0; unrelated topics drop
            toward 0.0; only adversarial pairs go negative.

        Notes
        -----
        Symmetric: ``pairwise_similarity(a, b) == pairwise_similarity(b, a)``
        within floating-point noise. Embeds both texts in a single
        OneLLM call so latency is one round-trip, not two.

        The e5 family's ``query: `` prefix is applied to both inputs to
        match the convention used elsewhere in this module — it
        improves cross-language similarity calibration.
        """
        if not text_a or not text_a.strip():
            raise ValueError("pairwise_similarity: text_a must be non-empty")
        if not text_b or not text_b.strip():
            raise ValueError("pairwise_similarity: text_b must be non-empty")

        vecs = await embed(self.model, [f"query: {text_a}", f"query: {text_b}"])
        a_unit = _l2_normalize(vecs[0])
        b_unit = _l2_normalize(vecs[1])
        sim = sum(x * y for x, y in zip(a_unit, b_unit))
        return max(-1.0, min(1.0, sim))

    def diagnostic_snapshot(self) -> Dict[str, dict]:
        """Return a dict describing every registered intent — useful
        for ``/health`` endpoints and tests. Does not include the
        centroid vectors themselves to keep the payload small.
        """
        return {
            name: {
                "description": self._specs[name].description,
                "positive_examples": len(self._specs[name].positive),
                "negative_examples": len(self._specs[name].negative),
                "centroid_dim": len(self._centroids[name].positive),
            }
            for name in self._centroids
        }
