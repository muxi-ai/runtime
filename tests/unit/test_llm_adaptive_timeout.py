"""Regression tests for the adaptive-timeout sizing fix.

Background
----------
Before this fix, every chat / chat_with_tools call passed
``messages=None`` to ``calculate_adaptive_timeout`` (see the now-removed
"Known limitation" comment in ``services.llm.llm._execute_with_resilience``).
That meant the timeout always equaled the bare base (default 30s), even
when the planning prompt fed the LLM 15K+ tokens of tool definitions and
context. Sonnet 4.6 needs ~30-40s to plan that input, so the first attempt
timed out at 30s and the resilience layer retried with a 1.5x escalation
(45s budget). Net cost: 30 wasted seconds per complex planning call,
visible in production traces as ``error.internal.error`` followed
~750ms later by ``resource.allocated`` with the 45s recalc.

These tests guard:

1. The internal kwargs ``_adaptive_messages`` / ``_adaptive_files`` are
   threaded through ``_execute_with_resilience`` to
   ``calculate_adaptive_timeout`` (so the timeout actually scales with
   payload size).
2. The internal kwargs are stripped before reaching the wrapped chat
   coroutine — they must NOT leak through to provider clients that
   would reject unknown kwargs.
3. Backward compatibility: calls without these kwargs (embedding,
   transcription, legacy callers) still work and produce the same
   bare-base timeout as before.
"""

from __future__ import annotations

import inspect

from muxi.runtime.services.llm import llm as llm_module
from muxi.runtime.services.llm.llm import calculate_adaptive_timeout


def test_calculate_adaptive_timeout_scales_with_message_size():
    """A 15K-token planning prompt should produce a timeout well above the
    30s bare base. The previous bug was passing messages=None which capped
    every call at 30s regardless of context."""
    base = 30.0
    # ~60K chars ~= 15K tokens (4 chars per token heuristic the helper uses)
    big_prompt = "x" * 60_000
    messages = [
        {"role": "system", "content": big_prompt},
        {"role": "user", "content": "plan this"},
    ]
    timeout = calculate_adaptive_timeout(
        base_timeout=base,
        messages=messages,
        operation_type="chat",
        max_timeout=120.0,
    )
    # 30 base + 15 (15K tokens / 1000) * 1.0 chat modifier = 45s
    assert timeout > base, (
        f"Adaptive timeout did not scale with context size: got {timeout}s "
        f"for a 15K-token prompt, expected > {base}s base"
    )
    # Sanity-cap: must not exceed max_timeout
    assert timeout <= 120.0


def test_calculate_adaptive_timeout_messages_none_keeps_base():
    """Backward-compatibility: callers that don't yet thread messages
    (embedding, transcription) get the same bare-base behavior as before."""
    base = 30.0
    timeout = calculate_adaptive_timeout(
        base_timeout=base,
        messages=None,
        operation_type="chat",
        max_timeout=120.0,
    )
    assert timeout == base, f"Expected base timeout when messages=None, got {timeout}s"


def test_calculate_adaptive_timeout_scales_with_max_tokens():
    """A planning call asks for ``max_tokens=16384`` because it's emitting
    a structured plan over many tools. The output-size signal must add
    real budget — without it the first attempt times out at 30s + a
    handful of input-token seconds (~37s) and Sonnet 4.6 retries at the
    1.5x escalation, wasting ~30s per planning call.

    Budget: 2s per 1000 max output tokens (16384 / 500 ≈ 32.8s)."""
    base = 30.0
    # Small input, big requested output — the planning shape.
    messages = [{"role": "user", "content": "plan this"}]
    timeout_no_max = calculate_adaptive_timeout(
        base_timeout=base, messages=messages, operation_type="chat"
    )
    timeout_with_max = calculate_adaptive_timeout(
        base_timeout=base,
        messages=messages,
        operation_type="chat",
        max_tokens=16384,
    )
    # max_tokens=16384 should add ~32.8s of headroom on top of input scaling.
    assert timeout_with_max > timeout_no_max + 30.0, (
        f"max_tokens did not produce meaningful headroom: "
        f"no-max={timeout_no_max}s, with-max={timeout_with_max}s. "
        f"Expected with-max >= no-max + 30s for max_tokens=16384."
    )
    # Sanity: still capped at max_timeout.
    assert timeout_with_max <= 120.0


def test_calculate_adaptive_timeout_max_tokens_none_keeps_input_scaling():
    """Backward-compatibility: calls without ``max_tokens`` (e.g. response
    synthesis where the LLM defaults the cap) get the same input-only
    scaling as before, no change in behavior."""
    base = 30.0
    messages = [{"role": "user", "content": "x" * 4000}]  # ~1K tokens
    t = calculate_adaptive_timeout(
        base_timeout=base, messages=messages, max_tokens=None, operation_type="chat"
    )
    # 30 + 1.0 (1K tokens / 1000) * 1.0 chat modifier = 31s
    assert abs(t - 31.0) < 0.5, f"Expected ~31s for 1K input + max_tokens=None, got {t}s"


def test_calculate_adaptive_timeout_files_add_per_file_overhead():
    """Each file should add 3s of processing overhead so multimodal
    requests don't time out before the provider can ingest them."""
    base = 30.0
    timeout = calculate_adaptive_timeout(
        base_timeout=base,
        messages=None,
        files=["a.png", "b.png", "c.pdf"],
        operation_type="chat",
        max_timeout=120.0,
    )
    # 30 + 3 files * 3s = 39s
    assert timeout >= base + 9.0


def test_calculate_adaptive_timeout_retry_escalates():
    """Retry attempts should compound the timeout (1.5x per retry)
    so a transient timeout on attempt 0 doesn't immediately retry
    with the same too-short budget."""
    base = 30.0
    t0 = calculate_adaptive_timeout(
        base_timeout=base, messages=None, operation_type="chat", retry_attempt=0
    )
    t1 = calculate_adaptive_timeout(
        base_timeout=base, messages=None, operation_type="chat", retry_attempt=1
    )
    assert t1 > t0
    assert abs(t1 - t0 * 1.5) < 0.01


def test_execute_with_resilience_threads_adaptive_kwargs_through():
    """Static guard: the source of ``_execute_with_resilience`` must pop
    both ``_adaptive_messages`` and ``_adaptive_files`` from kwargs and
    pass them to ``calculate_adaptive_timeout``. If a future refactor
    drops the threading we'll silently regress to the bare 30s timeout
    and complex planning prompts will start timing out again."""
    src = inspect.getsource(llm_module.LLM._execute_with_resilience)
    assert "_adaptive_messages" in src, (
        "_execute_with_resilience no longer pops _adaptive_messages from "
        "kwargs — adaptive timeout will fall back to the bare base and "
        "complex planning calls will start timing out again."
    )
    assert "_adaptive_files" in src
    assert "_adaptive_max_tokens" in src, (
        "_execute_with_resilience no longer pops _adaptive_max_tokens — "
        "planning calls (max_tokens=16384) will lose the strongest output-"
        "size signal and the first-attempt timeout will be too tight."
    )
    assert "messages=adaptive_messages" in src or "messages = adaptive_messages" in src, (
        "_execute_with_resilience pops _adaptive_messages but no longer "
        "forwards it to calculate_adaptive_timeout — the timeout will not "
        "scale with payload size."
    )
    assert "files=adaptive_files" in src or "files = adaptive_files" in src
    assert "max_tokens=adaptive_max_tokens" in src or "max_tokens = adaptive_max_tokens" in src, (
        "_execute_with_resilience pops _adaptive_max_tokens but no longer "
        "forwards it to calculate_adaptive_timeout — output-size scaling "
        "will be a no-op."
    )


def test_execute_with_resilience_does_not_leak_internal_kwargs():
    """Static guard: the internal sizing kwargs must be popped (not merely
    read) so they don't leak through to the wrapped provider call where
    they'd be rejected as unknown kwargs."""
    src = inspect.getsource(llm_module.LLM._execute_with_resilience)
    # ``kwargs.pop("_adaptive_messages", None)`` is the contract; ``.get``
    # would leak the kwarg downstream.
    assert 'kwargs.pop("_adaptive_messages"' in src
    assert 'kwargs.pop("_adaptive_files"' in src
    assert 'kwargs.pop("_adaptive_max_tokens"' in src


def test_basic_chat_call_site_forwards_messages_and_files():
    """Static guard on the call site for the text-only chat path.

    ``LLM.chat`` routes through ``_text_chat`` to ``_basic_chat_with_files``,
    which is where the ``_execute_with_resilience`` call actually lives
    (the public ``chat()`` only dispatches by fusion mode and file
    presence). The ``_basic_chat_with_files`` closure must forward the
    original ``messages`` and ``files`` as the internal sizing kwargs so
    the adaptive timeout sees the actual payload.

    If this regresses (e.g. someone passes ``_adaptive_messages=None`` on
    cleanup), the adaptive timeout becomes a no-op for chat calls and
    long planning prompts start timing out at 30s again."""
    src = inspect.getsource(llm_module.LLM._basic_chat_with_files)
    assert "_adaptive_messages=messages" in src, (
        "_basic_chat_with_files no longer forwards messages to "
        "_execute_with_resilience as _adaptive_messages — the adaptive "
        "timeout fix is broken for the text-only chat path (which is the "
        "path planning calls take)."
    )
    assert "_adaptive_files=files" in src
    assert '_adaptive_max_tokens=kwargs.get("max_tokens")' in src, (
        "_basic_chat_with_files no longer forwards max_tokens to the "
        "adaptive timeout — planning calls will lose the output-size "
        "signal and start timing out at ~37s again."
    )


def test_chat_with_tools_call_site_forwards_messages_and_files():
    """Same guard as test_chat_call_site_forwards_messages_and_files but
    for the tool-calling path (which sees the same large planning prompts)."""
    src = inspect.getsource(llm_module.LLM.chat_with_tools)
    assert "_adaptive_messages=messages" in src
    assert "_adaptive_files=files" in src
    assert "_adaptive_max_tokens=max_tokens" in src, (
        "chat_with_tools no longer forwards max_tokens to the adaptive "
        "timeout — agent.chat_with_tools planning calls will lose the "
        "output-size signal and start timing out again."
    )
