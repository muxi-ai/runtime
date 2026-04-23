"""Integration tests for the shared embedding helper against real models.

Exercises ``services.memory.embedding`` against the real OneLLM
``LocalProvider`` (Nomic v1.5). Marked ``slow`` + ``integration`` so they
are excluded from the fast unit pass.

Covers:
  * VAL-HELPER-007: ``probe_dimension`` returns 768 for Nomic v1.5.
  * VAL-HELPER-010: ``dimensions`` exceeding the native dim has a
    documented outcome (the helper does not silently clamp).
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.memory.embedding import (
    DEFAULT_EMBEDDING_MODEL,
    embed,
    probe_dimension,
)

pytestmark = [pytest.mark.slow, pytest.mark.integration]


@pytest.mark.asyncio
async def test_probe_dimension_nomic_v15():
    """VAL-HELPER-007: Nomic v1.5 native dim is 768."""
    dim = await probe_dimension("local/nomic-ai/nomic-embed-text-v1.5")
    assert dim == 768


@pytest.mark.asyncio
async def test_probe_dimension_matches_default_model():
    """The default model slug probes to 768."""
    dim = await probe_dimension(DEFAULT_EMBEDDING_MODEL)
    assert dim == 768


@pytest.mark.asyncio
async def test_embed_dimensions_exceeds_native():
    """VAL-HELPER-010: documented behavior when dimensions > native.

    OneLLM's ``LocalProvider`` silently clamps ``dimensions`` to the
    model's native dim when the request exceeds it. The helper
    documents this in its module docstring and forwards the kwarg
    verbatim. Asserting the clamp is the documented-behavior
    contract.
    """
    vectors = await embed("local/nomic-ai/nomic-embed-text-v1.5", "x", dimensions=4096)
    # Clamped to the native Nomic v1.5 dim, not silently truncated to
    # some weird partial state.
    assert len(vectors) == 1
    assert len(vectors[0]) == 768


@pytest.mark.asyncio
async def test_embed_dimensions_within_native_is_honored():
    """Matryoshka truncation works when ``dimensions <= native``."""
    vectors = await embed("local/nomic-ai/nomic-embed-text-v1.5", "x", dimensions=256)
    assert len(vectors) == 1
    assert len(vectors[0]) == 256
