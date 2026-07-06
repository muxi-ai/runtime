"""Regression tests for the overlord model cache key.

Background
----------
``Overlord.get_model_for_capability`` used to cache model instances under
``f"{agent_id or 'default'}:{capability}"``. Two call sites requesting the
same capability with different effective settings (temperature, timeout,
etc.) therefore shared a single cached instance: whichever caller ran first
locked in its settings, and the second caller silently received a model
configured for someone else.

The fix appends a stable sha256 digest of the effective settings (global
settings merged with model-specific overrides) to the cache key, so:

- same capability + different settings -> distinct cache entries
- same capability + identical settings -> cache hit (single instance)
- missing/None settings are handled (digest of the empty dict)
"""

from unittest.mock import patch

import pytest

from muxi.runtime.formation.overlord import overlord as overlord_module
from muxi.runtime.formation.overlord.overlord import Overlord


class FakeLLM:
    """Stands in for LLM so no provider client is constructed."""

    def __init__(self, model=None, api_key=None, **settings):
        self.model = model
        self.api_key = api_key
        self.settings = settings


def make_overlord(capability_models, global_llm_settings=None):
    """Build a minimally-initialized Overlord for cache-key testing."""
    ov = Overlord.__new__(Overlord)
    ov._model_cache = {}
    ov._capability_models = capability_models
    ov._global_llm_settings = global_llm_settings or {}
    ov._global_api_keys = {"openai": "test-key"}
    return ov


@pytest.mark.asyncio
async def test_different_settings_produce_different_cache_entries():
    """Same capability with different effective settings must not share
    one cached instance."""
    ov = make_overlord(
        {"text": {"model": "openai/gpt-4o", "settings": {"temperature": 0.2, "timeout": 30}}}
    )

    with patch.object(overlord_module, "LLM", FakeLLM):
        first = await ov.get_model_for_capability("text")

        # A second call site resolves the same capability with different
        # settings (e.g. reconfigured formation defaults).
        ov._capability_models["text"]["settings"] = {"temperature": 0.9, "timeout": 5}
        second = await ov.get_model_for_capability("text")

    assert first is not second
    assert len(ov._model_cache) == 2
    assert first.settings == {"temperature": 0.2, "timeout": 30}
    assert second.settings == {"temperature": 0.9, "timeout": 5}


@pytest.mark.asyncio
async def test_identical_settings_hit_cache():
    """Same capability + identical settings must return the cached instance."""
    ov = make_overlord({"text": {"model": "openai/gpt-4o", "settings": {"temperature": 0.2}}})

    with patch.object(overlord_module, "LLM", FakeLLM):
        first = await ov.get_model_for_capability("text")
        second = await ov.get_model_for_capability("text")

    assert first is second
    assert len(ov._model_cache) == 1


@pytest.mark.asyncio
async def test_missing_settings_are_handled():
    """A model config without a settings block must still cache cleanly."""
    ov = make_overlord({"text": {"model": "openai/gpt-4o"}})

    with patch.object(overlord_module, "LLM", FakeLLM):
        first = await ov.get_model_for_capability("text")
        second = await ov.get_model_for_capability("text")

    assert first is second
    assert len(ov._model_cache) == 1


@pytest.mark.asyncio
async def test_cache_key_includes_settings_digest():
    """Cache keys keep the agent/capability prefix and gain a hex digest."""
    ov = make_overlord({"text": {"model": "openai/gpt-4o", "settings": {"temperature": 0.2}}})

    with patch.object(overlord_module, "LLM", FakeLLM):
        await ov.get_model_for_capability("text")

    (cache_key,) = ov._model_cache.keys()
    prefix, capability, digest = cache_key.split(":")
    assert prefix == "default"
    assert capability == "text"
    assert len(digest) == 12
    int(digest, 16)  # digest must be hex
