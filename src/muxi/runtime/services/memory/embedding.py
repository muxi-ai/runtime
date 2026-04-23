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

Model slug revision pinning
---------------------------
``local/*`` slugs support a ``:<revision>`` suffix for pinning the
HuggingFace git revision: ``local/nomic-ai/nomic-embed-text-v1.5:abc123``.
``<revision>`` may be a commit SHA, tag, or branch name; it is forwarded
verbatim to OneLLM's ``LocalProvider`` which passes it through to
``huggingface_hub`` (``snapshot_download``, ``hf_hub_download``,
``SentenceTransformer``, ``AutoTokenizer``, ``AutoConfig``). A slug
without ``:<revision>`` resolves to ``main`` (back-compat).

Cloud provider slugs are NOT parsed for revisions because model names
legitimately contain ``:`` in some providers (e.g. ``ollama/llama2:7b``).
They pass through to OneLLM untouched.
"""

from __future__ import annotations

import onellm
from onellm.errors import InvalidRequestError

DEFAULT_EMBEDDING_MODEL = "local/nomic-ai/nomic-embed-text-v1.5"
"""Apache-2.0 Nomic v1.5 (768-dim, 8k context, Matryoshka 64-768).

Chosen as the default local embedding model for MUXI. Multilingual
deployments can opt into ``local/nomic-ai/nomic-embed-text-v2-moe``.
"""

DEFAULT_EMBEDDING_MODEL_NATIVE_DIM = 768
"""Native (pre-Matryoshka-truncation) output dimension of
``DEFAULT_EMBEDDING_MODEL``. Exported so downstream modules
(e.g. ``services.multimodal.fusion_engine``) that need to produce
shape-compatible fallback vectors can depend on a single source of
truth instead of copy-pasting the magic number. Update *together*
with ``DEFAULT_EMBEDDING_MODEL`` when swapping defaults."""


def _parse_model_slug(slug: str) -> tuple[str, str | None]:
    """Split ``local/<repo>:<revision>`` notation into ``(model, revision)``.

    Only ``local/*`` slugs are parsed — cloud providers may legitimately
    use ``:`` in model names (e.g. ``ollama/llama2:7b``) and pass through
    unchanged. A ``local/*`` slug without ``:`` also passes through with
    ``revision=None`` (resolves to ``main`` downstream).

    Parameters
    ----------
    slug:
        Provider-prefixed model slug, optionally with ``:<revision>``
        suffix for ``local/*`` slugs.

    Returns
    -------
    tuple[str, str | None]
        ``(model, revision)``. ``revision`` is ``None`` when no suffix
        was present; otherwise it is the non-empty string after the
        first ``:``.

    Raises
    ------
    InvalidRequestError
        If ``slug`` is not a non-empty string, or if a ``local/*`` slug
        has a trailing ``:`` with no revision (e.g. ``"local/foo:"``).
        Trailing ``:`` is rejected up front so operators get a clear
        error instead of HuggingFace resolving the revision to ``main``
        silently.
    """
    if not isinstance(slug, str) or not slug:
        raise InvalidRequestError(f"Embedding model slug must be a non-empty string, got {slug!r}")
    if not slug.startswith("local/"):
        return slug, None
    if ":" not in slug:
        return slug, None
    model, _, revision = slug.partition(":")
    if not revision:
        raise InvalidRequestError(
            f"Embedding model slug {slug!r} has a trailing ':' with no "
            f"revision. Use 'local/<repo>:<revision>' (revision required) "
            f"or 'local/<repo>' (defaults to 'main')."
        )
    return model, revision


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
    texts: str | list[str],
    *,
    dimensions: int | None = None,
    task: str | None = None,
    pooling: str | None = None,
) -> list[list[float]]:
    """Generate embedding vectors for ``texts`` using ``model``.

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
    texts:
        A single string or a list of strings to embed. A single string is
        normalized to ``[texts]`` before being forwarded. Named ``texts``
        rather than ``input`` to avoid shadowing the Python builtin.
    dimensions:
        Optional Matryoshka truncation target. Forwarded as-is to
        OneLLM. Values ``<= native`` are honored exactly (Matryoshka
        truncation + re-normalization). Values that EXCEED the model's
        native dim are **silently clamped** by OneLLM's ``LocalProvider``
        and return a full native-length vector, NOT a provider error.
        Callers that want a hard failure on over-sized requests must
        probe ``probe_dimension(model)`` first and guard on the result
        themselves. See the module-level "``dimensions`` that exceed
        native model dim" section for the full rationale.
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
        If ``texts`` is empty or whitespace-only.
    """
    items = _normalize_input(texts)

    # Support ``local/<repo>:<revision>`` slug notation transparently.
    # Consumers continue to pass a single slug; the parser extracts the
    # revision for the ``revision=`` kwarg that OneLLM's LocalProvider
    # forwards to HuggingFace.
    parsed_model, revision = _parse_model_slug(model)

    kwargs: dict[str, object] = {"model": parsed_model, "input": items}
    if dimensions is not None:
        kwargs["dimensions"] = dimensions
    if pooling is not None:
        kwargs["pooling"] = pooling
    # Task-kwarg policy: only forward for local/* slugs. Cloud providers
    # do not understand the Nomic-style ``task`` convention.
    if task is not None and parsed_model.startswith("local/"):
        kwargs["task"] = task
    # Forward a pinned revision to OneLLM only when the slug embedded one.
    # ``None`` means "follow main" — omit the kwarg rather than sending
    # ``revision=None`` so OneLLM's default path is taken.
    if revision is not None:
        kwargs["revision"] = revision

    response = await onellm.Embedding.acreate(**kwargs)

    # Dataclass attribute access — EmbeddingResponse does NOT implement
    # __getitem__. See module docstring.
    return [item.embedding for item in response.data]


async def probe_dimension(model: str) -> int:
    """Return the native embedding dimension for ``model``.

    Issues a single placeholder embedding call and reports
    ``len(resp.data[0].embedding)``. Consumers should memoize the result
    per-instance; this helper is stateless and probes on every call.

    ``local/<repo>:<revision>`` slug notation is honored — the probe
    fetches the exact revision the consumer will use for real embeds, so
    dimension mismatches across revisions surface here rather than
    silently when the first real embed runs.
    """
    parsed_model, revision = _parse_model_slug(model)
    kwargs: dict[str, object] = {"model": parsed_model, "input": ["probe"]}
    if revision is not None:
        kwargs["revision"] = revision
    response = await onellm.Embedding.acreate(**kwargs)
    return len(response.data[0].embedding)
