"""Regression tests for eager KnowledgeHandler initialization at formation startup.

Background
----------
Before this fix, ``Agent._ensure_knowledge_initialized`` was lazy — the
KnowledgeHandler (and the Nomic embedder it transitively loads) wasn't
constructed until the first user message arrived. That deferred ~8s of
chunking+embedding plus the ~12s Nomic cold-start onto the user's first
chat request, producing a visible ~20s "first message is sluggish"
artifact in production traces.

The fix is in ``Overlord._create_agent_from_config``: after the agent is
fully constructed (including MCP server registration), we eagerly call
``await agent._ensure_knowledge_initialized()`` so that the
embedder load and chunk-embed work runs during formation `up` (where
operators expect a brief warmup) rather than during chat.

These tests guard:

1. The eager-init call site exists in ``_create_agent_from_config`` and
   guards on ``agent_config.get("knowledge")`` (no-knowledge agents must
   not pay the cost).
2. The call awaits the same ``_ensure_knowledge_initialized`` entry
   point that the request flow uses, so caching via the
   ``_knowledge_initialized`` flag still short-circuits any later
   first-message call.
3. Failures during eager init propagate (fail-fast at deploy time) and
   emit a SERVICE_UNAVAILABLE observability event so misconfigurations
   surface in formation startup rather than being deferred to whichever
   user happens to land first.
"""

from __future__ import annotations

import inspect

from muxi.runtime.formation.overlord import overlord as overlord_module


def test_create_agent_from_config_eagerly_initializes_knowledge():
    """Static guard: ``_create_agent_from_config`` must contain the
    eager init block. If a refactor drops it, the 8s knowledge-load and
    12s Nomic cold start will silently slide back onto the user's first
    message."""
    src = inspect.getsource(overlord_module.Overlord._create_agent_from_config)
    assert 'agent_config.get("knowledge")' in src, (
        "_create_agent_from_config no longer guards on knowledge config "
        "before eagerly initializing — either the eager-init block was "
        "removed or the gate condition was changed."
    )
    assert "_ensure_knowledge_initialized" in src, (
        "_create_agent_from_config no longer calls "
        "agent._ensure_knowledge_initialized at startup — first-message "
        "latency will regress by ~20s when the Nomic embedder cold-starts."
    )


def test_eager_knowledge_init_is_awaited():
    """The eager init must be awaited; a missing await would silently
    spawn a coroutine that never runs and we'd lose the warmup
    entirely."""
    src = inspect.getsource(overlord_module.Overlord._create_agent_from_config)
    # We can't easily assert "await" lexically without false positives
    # from other awaits in the function, so check the specific pairing.
    assert "await agent._ensure_knowledge_initialized()" in src, (
        "Eager knowledge init is not awaited — the coroutine will never "
        "actually run and the warmup is a no-op."
    )


def test_eager_knowledge_init_reports_failures_via_observability():
    """A failure during eager init must emit a SERVICE_UNAVAILABLE event
    with phase=knowledge_eager_init so operators can distinguish startup
    knowledge failures from runtime ones."""
    src = inspect.getsource(overlord_module.Overlord._create_agent_from_config)
    assert "knowledge_eager_init" in src, (
        "Eager knowledge init failure path no longer tags the "
        "observability event with phase=knowledge_eager_init — operators "
        "lose the ability to distinguish startup vs request-time "
        "knowledge failures."
    )
    assert "SERVICE_UNAVAILABLE" in src or "service_unavailable" in src.lower()


def test_eager_knowledge_init_propagates_errors():
    """Eager init must re-raise on failure so formation up fails fast,
    matching the existing MCP register policy. A swallowed exception
    here would let a broken formation come up in a degraded state where
    the first chat would crash with a confusing knowledge error."""
    src = inspect.getsource(overlord_module.Overlord._create_agent_from_config)
    # Look for the specific re-raise pattern inside the eager-init block.
    eager_block_start = src.find('agent_config.get("knowledge")')
    assert eager_block_start != -1
    eager_block = src[eager_block_start:]
    # The except clause for the eager block must end with `raise`
    # (re-raise), not silently log-and-continue.
    assert (
        "raise" in eager_block.split("description=", 1)[1]
        if "description=" in eager_block
        else "raise" in eager_block
    ), (
        "Eager knowledge init no longer re-raises on failure — formation "
        "will come up in a degraded state and the first chat will crash."
    )
