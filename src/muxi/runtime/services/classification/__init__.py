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

from .local_classifier import LocalClassifier
from .prototypes import (
    ACTIONABILITY,
    CLARIFICATION_CONTEXT_SWITCH,
    CLARIFICATION_STOP_INTENT,
    RECALL_QUESTION,
    SIMPLE_QUESTION,
    WORKFLOW_ELIGIBILITY,
    IntentSpec,
)

__all__ = [
    "LocalClassifier",
    "IntentSpec",
    "ACTIONABILITY",
    "WORKFLOW_ELIGIBILITY",
    "SIMPLE_QUESTION",
    "CLARIFICATION_CONTEXT_SWITCH",
    "CLARIFICATION_STOP_INTENT",
    "RECALL_QUESTION",
]
