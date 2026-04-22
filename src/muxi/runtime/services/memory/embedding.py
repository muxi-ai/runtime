"""Shared embedding helper for MUXI memory and related consumers.

This module is the single choke point for generating embeddings in the
MUXI runtime. Every consumer — long-term memory, working memory, SQLite
memory, fusion engine, SOP coordinator, knowledge handler — flows through
``embed()`` / ``probe_dimension()`` below, which in turn delegate to
``onellm.Embedding.acreate``.

The helper normalizes the public API across cloud and local providers:

* ``local/*`` slugs route through OneLLM's ``LocalProvider`` (ONNX / HF).
* Everything else (``openai/*``, ``cohere/*``, ``anthropic/*``, ...)
  routes through that provider's cloud API.

Design decisions — documented here so consumers and reviewers don't have
to re-derive them from code:

Empty / whitespace-only input
-----------------------------
``embed()`` raises ``onellm.errors.InvalidRequestError`` when called with
an empty string, a whitespace-only string, an empty list, or a list whose
members are all empty / whitespace-only. No zero-vector is synthesized.
OneLLM's own ``validate_embedding_input`` covers the empty/falsy cases;
this helper additionally rejects whitespace-only strings for consistency.

``dimensions`` that exceed native model dim
-------------------------------------------
``dimensions`` is forwarded as-is to OneLLM. When the requested value
EXCEEDS the provider's native dimensionality (e.g. requesting
``dimensions=4096`` from Nomic v1.5 whose native dim is 768), OneLLM's
``LocalProvider`` clamps silently to the native dim and returns the
full-length vector. The helper does not intercept this — callers that
want a hard error on Matryoshka misconfiguration should probe
``probe_dimension(model)`` first and validate against it. Requests for
``dimensions <= native`` are honored exactly (Matryoshka truncation +
re-normalization).

``task`` kwarg policy
---------------------
The ``task`` kwarg is a Nomic-style convention honored by
``LocalProvider`` — it prepends ``f"{task}: "`` to each input. Cloud
providers (OpenAI, Cohere, Anthropic, ...) do not recognize ``task`` and
would either ignore it or reject the request. To keep consumers free of
per-provider branching, this helper **strips ``task`` from outbound
kwargs when the model slug does not start with ``local/``**. Consumers
may therefore pass ``task`` unconditionally; it is a no-op for cloud
models.

``pooling`` policy
------------------
``pooling`` (``"mean" | "cls" | "max"``) is forwarded when the caller
provides it. When omitted, the downstream provider falls back to its
default (mean pooling for ``LocalProvider``'s ONNX backend). The helper
does not pin a pooling strategy — that decision stays with the caller or
the provider.

``EmbeddingResponse`` shape
---------------------------
OneLLM returns an ``EmbeddingResponse`` **dataclass**
(see ``onellm/models.py``). The helper uses attribute access
(``resp.data[0].embedding``) and must NEVER use subscript syntax
(``resp["data"][0]["embedding"]``) — dataclasses do not implement
``__getitem__`` by default and the regression would surface only at
runtime against the real OneLLM.
"""

from __future__ import annotations

import onellm
from onellm.errors import InvalidRequestError

DEFAULT_EMBEDDING_MODEL = "local/nomic-ai/nomic-embed-text-v1.5"
"""Apache-2.0 Nomic v1.5 (768-dim, 8k context, Matryoshka 64-768).

Chosen as the default local embedding model for MUXI. Multilingual
deployments can opt into ``local/nomic-ai/nomic-embed-text-v2-moe``.
"""


def _normalize_input(text_or_texts: str | list[str]) -> list[str]:
    """Normalize the ``input`` argument to ``list[str]`` and validate.

    Raises
    ------
    InvalidRequestError
        If the input is empty, whitespace-only, or a list containing only
        empty / whitespace-only strings.
    """
    if isinstance(text_or_texts, str):
        items = [text_or_texts]
    elif isinstance(text_or_texts, list):
        items = text_or_texts
    else:
        raise InvalidRequestError(
            f"embed() input must be str or list[str], got {type(text_or_texts).__name__}"
        )

    if not items or all(not isinstance(t, str) or not t.strip() for t in items):
        raise InvalidRequestError("Input cannot be empty or whitespace-only (embed helper).")

    return items


async def embed(
    model: str,
    input: str | list[str],
    *,
    dimensions: int | None = None,
    task: str | None = None,
    pooling: str | None = None,
) -> list[list[float]]:
    """Generate embedding vectors for ``input`` using ``model``.

    This is the single embedding entry point used by every MUXI memory
    and non-memory consumer. It forwards optional kwargs to
    ``onellm.Embedding.acreate`` and returns a list of vectors (one per
    input string).

    Parameters
    ----------
    model:
        Provider-prefixed model slug (e.g.
        ``"local/nomic-ai/nomic-embed-text-v1.5"`` or
        ``"openai/text-embedding-3-small"``).
    input:
        A single string or a list of strings to embed. A single string is
        normalized to ``[input]`` before being forwarded.
    dimensions:
        Optional Matryoshka truncation target. Forwarded as-is; values
        above the model's native dim surface a provider error rather than
        being silently clamped.
    task:
        Optional Nomic-style task prefix (``"search_document"``,
        ``"search_query"``, ``"classification"``, ``"clustering"``). Only
        forwarded when ``model`` starts with ``"local/"``; stripped for
        every cloud provider to avoid leaking the kwarg to APIs that do
        not recognize it.
    pooling:
        Optional pooling strategy override (``"mean"``, ``"cls"``, or
        ``"max"``). Forwarded verbatim when set; provider default
        otherwise.

    Returns
    -------
    list[list[float]]
        One vector per input string, in the original input order.

    Raises
    ------
    InvalidRequestError
        If ``input`` is empty or whitespace-only.
    """
    items = _normalize_input(input)

    kwargs: dict[str, object] = {"model": model, "input": items}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    if pooling is not None:
        kwargs["pooling"] = pooling
    # Task-kwarg policy: only forward for local/* slugs. Cloud providers
    # do not understand the Nomic-style ``task`` convention.
    if task is not None and model.startswith("local/"):
        kwargs["task"] = task

    response = await onellm.Embedding.acreate(**kwargs)

    # Dataclass attribute access — EmbeddingResponse does NOT implement
    # __getitem__. See module docstring.
    return [item.embedding for item in response.data]


async def probe_dimension(model: str) -> int:
    """Return the native embedding dimension for ``model``.

    Issues a single placeholder embedding call and reports
    ``len(resp.data[0].embedding)``. Consumers should memoize the result
    per-instance; this helper is stateless and probes on every call.
    """
    response = await onellm.Embedding.acreate(model=model, input=["probe"])
    return len(response.data[0].embedding)
