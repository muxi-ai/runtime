"""Regression tests for LLM response cache key generation.

Background
----------
``services.llm.llm._get_cache_key`` previously built keys with
``str(sorted(kwargs.items()))``. For batch embedding calls the input
texts are a list-valued kwarg, and any normalization that ignores list
order can map ``["A", "B", "C"]`` and ``["C", "B", "A"]`` to the same
key, returning cached vectors misaligned with the requested texts.

The fix serializes kwargs with ``json.dumps(kwargs, sort_keys=True,
default=str)``: stable across dict-key ordering, but sensitive to the
element order of list-valued inputs.

These tests guard:

1. Same batch texts in a different order produce DIFFERENT keys.
2. Identical calls (including different kwarg insertion order) produce
   the SAME key.
3. Different operations or parameter values never share a key.
"""

from __future__ import annotations

from muxi.runtime.services.llm.llm import _get_cache_key


class TestGetCacheKeyOrderSensitivity:
    """List-valued inputs must keep their order in the cache key."""

    def test_batch_texts_in_different_order_produce_different_keys(self):
        key_abc = _get_cache_key("embed_batch", model="m", input=["A", "B", "C"])
        key_cba = _get_cache_key("embed_batch", model="m", input=["C", "B", "A"])
        assert key_abc != key_cba

    def test_two_element_swap_produces_different_keys(self):
        key_ab = _get_cache_key("embed_batch", model="m", input=["A", "B"])
        key_ba = _get_cache_key("embed_batch", model="m", input=["B", "A"])
        assert key_ab != key_ba


class TestGetCacheKeyDeterminism:
    """Identical calls must always hit the same cache entry."""

    def test_identical_calls_produce_same_key(self):
        key_first = _get_cache_key("embed_batch", model="m", input=["A", "B", "C"])
        key_second = _get_cache_key("embed_batch", model="m", input=["A", "B", "C"])
        assert key_first == key_second

    def test_kwarg_insertion_order_does_not_change_key(self):
        key_model_first = _get_cache_key("embed", model="m", input="hello")
        key_input_first = _get_cache_key("embed", input="hello", model="m")
        assert key_model_first == key_input_first


class TestGetCacheKeyIsolation:
    """Distinct requests must never collide."""

    def test_different_operations_produce_different_keys(self):
        key_embed = _get_cache_key("embed", model="m", input="hello")
        key_chat = _get_cache_key("chat", model="m", input="hello")
        assert key_embed != key_chat

    def test_non_json_values_are_stringified_not_dropped(self):
        from pathlib import Path

        # default=str handles values orjson cannot serialize natively
        key_file_a = _get_cache_key("chat", model="m", file=Path("/tmp/a.wav"))
        key_file_b = _get_cache_key("chat", model="m", file=Path("/tmp/b.wav"))
        assert key_file_a != key_file_b
