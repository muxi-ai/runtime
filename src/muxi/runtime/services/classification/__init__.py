"""Local prototype-similarity classification for binary pre-planning gates.

This module provides a lightweight, deterministic, multilingual replacement
for the cloud-LLM binary gate calls that fire before the planner — things
like "is this message actionable?", "is this a simple question?", "is the
user trying to switch context out of a clarification flow?".

These gates have well-defined positive/negative label sets and don't
require reasoning, so prototype-similarity classification using a local
ONNX embedding model (``local/Xenova/multilingual-e5-small`` by default)
is both faster (~5-30 ms vs 200-2000 ms cloud RTT) and free of cloud
spend / rate limits / non-determinism.

Public API
----------

* :class:`LocalClassifier` — async, lazy-init classifier with one method
  worth calling: ``classify_binary(name, text) -> (label, margin)``.
  Prototypes are registered once per process and cached on the instance.

* :mod:`prototypes` — curated ``IntentSpec`` definitions for each binary
  gate the runtime currently uses. Centralized here so prompt-equivalent
  example sentences live next to the classifier rather than scattered
  across overlord and clarification modules.
"""

import asyncio
from typing import Optional

from .local_classifier import LocalClassifier
from .prototypes import (
    ACTIONABILITY,
    CLARIFICATION_CONTEXT_SWITCH,
    CLARIFICATION_NEEDED,
    CLARIFICATION_NEEDS_MORE,
    CLARIFICATION_STOP_INTENT,
    CREDENTIAL_CANCELLATION,
    CREDENTIAL_HELP_REQUEST,
    CREDENTIAL_REQUEST,
    RECALL_QUESTION,
    SIMPLE_QUESTION,
    WORKFLOW_ELIGIBILITY,
    IntentSpec,
)

# Process-level singleton: the classifier is stateless after warmup
# (model weights + cached prototype centroids), so a single instance
# is safe to share across overlords / services / formations. Consumers
# that don't have an overlord reference (scheduler JobManager, fusion
# engine) call ``get_classifier()`` to obtain the warmed singleton.
_singleton: Optional[LocalClassifier] = None
_singleton_lock = asyncio.Lock()


async def get_classifier() -> LocalClassifier:
    """Return the warmed process-wide LocalClassifier singleton.

    Lazily constructs and warms the classifier on first call. Lock-
    protected so concurrent first-touch callers don't both pay the
    warmup cost. Subsequent calls return the cached instance
    immediately.

    The first overlord to come up will normally trigger warmup via its
    own observability-instrumented ``_get_local_classifier()``; this
    helper exists for non-overlord consumers (scheduler, fusion engine,
    other services) that need the same shared instance without taking
    a runtime dependency on the overlord.
    """
    global _singleton
    if _singleton is not None and _singleton.is_warmed:
        return _singleton
    async with _singleton_lock:
        if _singleton is None:
            _singleton = LocalClassifier()
        if not _singleton.is_warmed:
            await _singleton.warmup()
    return _singleton


__all__ = [
    "LocalClassifier",
    "IntentSpec",
    "get_classifier",
    "ACTIONABILITY",
    "WORKFLOW_ELIGIBILITY",
    "SIMPLE_QUESTION",
    "CLARIFICATION_CONTEXT_SWITCH",
    "CLARIFICATION_STOP_INTENT",
    "CLARIFICATION_NEEDED",
    "CLARIFICATION_NEEDS_MORE",
    "CREDENTIAL_CANCELLATION",
    "CREDENTIAL_HELP_REQUEST",
    "CREDENTIAL_REQUEST",
    "RECALL_QUESTION",
]
