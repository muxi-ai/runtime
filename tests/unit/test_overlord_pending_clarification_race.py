"""
Regression tests for pending-clarification write races on hand-off paths.

Background
----------
The overlord stores pending-clarification state in a buffer-memory KV store
keyed by ``session_id``. Two flavours exist:

* ``_set_pending_clarification`` — fire-and-forget (background task)
* ``_set_pending_clarification_sync`` — awaited

When the overlord is about to return a response that *expects an immediate
follow-up message from the user* (workflow approval prompt, ambiguous-
credential selection prompt, etc.), the pending state MUST be persisted
before the response is returned. Otherwise the user's next request can
arrive before the background write lands, ``_get_pending_clarification``
returns ``None``, the corresponding handler branch is skipped, and the
follow-up message is treated as a fresh, contextless request.

These tests pin the contract for the workflow-approval path specifically,
which previously used the fire-and-forget variant and surfaced as
``test_9a3b_with_approval`` getting a clarification reply ("Could you
share more about the plan you're referring to?") instead of a workflow
execution after the user approved.
"""

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.formation.overlord.overlord import Overlord


class _OrderedBufferMemory:
    """Minimal buffer-memory stub that records the order of awaited operations.

    The race we are guarding against is: the workflow approval response
    is returned to the caller BEFORE the kv_set has been awaited. We
    track every await in ``ops`` in arrival order, then assert that the
    workflow-approval kv_set was awaited before the function returned.
    """

    def __init__(self, slow_ms: int = 0) -> None:
        self.store: Dict[Tuple[str, Optional[str]], Any] = {}
        self.ops: List[Tuple[str, str, Optional[str]]] = []
        self._slow_ms = slow_ms

    async def kv_set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        namespace: Optional[str] = None,
    ) -> None:
        # Simulate a non-trivial buffer-memory write: even a single
        # event-loop turn is enough to expose the race against a caller
        # that does not await the write.
        if self._slow_ms:
            await asyncio.sleep(self._slow_ms / 1000.0)
        else:
            await asyncio.sleep(0)
        self.store[(key, namespace)] = value
        self.ops.append(("set", key, namespace))

    async def kv_get(self, key: str, namespace: Optional[str] = None) -> Any:
        await asyncio.sleep(0)
        self.ops.append(("get", key, namespace))
        return self.store.get((key, namespace))

    async def kv_delete(self, key: str, namespace: Optional[str] = None) -> None:
        await asyncio.sleep(0)
        self.store.pop((key, namespace), None)
        self.ops.append(("delete", key, namespace))


def _make_overlord_stub(buffer_memory: _OrderedBufferMemory) -> Overlord:
    """Build a minimally-wired Overlord exposing only what the approval path touches."""
    overlord = Overlord.__new__(Overlord)
    overlord.buffer_memory = buffer_memory
    overlord.pending_clarification_namespace = "pending_clarification"

    # Workflow manager only needs add_pending_approval() in the path under test.
    overlord.workflow_manager = MagicMock()
    overlord.workflow_manager.add_pending_approval = MagicMock()

    # Approval manager returns a deterministic approval message.
    overlord.approval_manager = MagicMock()
    overlord.approval_manager.present_plan_for_approval = AsyncMock(
        return_value="Here's my proposed approach for your request: ..."
    )

    # _validate_workflow_inputs / _validate_workflow_object — neutralise.
    overlord._validate_workflow_inputs = MagicMock()
    overlord._validate_workflow_object = MagicMock()

    return overlord


def _make_workflow() -> SimpleNamespace:
    return SimpleNamespace(id="wf_test_123", tasks={})


@pytest.mark.asyncio
async def test_workflow_approval_pending_is_persisted_before_response_returns() -> None:
    """
    The kv_set for the workflow-approval pending state MUST be awaited
    before _handle_workflow_approval returns.
    """
    buffer = _OrderedBufferMemory(slow_ms=20)
    overlord = _make_overlord_stub(buffer)

    response = await overlord._handle_workflow_approval(
        workflow=_make_workflow(),
        message="Research the latest quantum computing breakthroughs and write a report",
        user_id="test_user",
        session_id="async_test_9a3b_approval",
        request_id="req_init_001",
        use_async=True,
        webhook_url="http://127.0.0.1:8765",
    )

    # Pending must be visible immediately after the function returns.
    assert ("async_test_9a3b_approval", "pending_clarification") in buffer.store, (
        "Workflow approval state was not persisted before _handle_workflow_approval "
        "returned. The kv_set must be awaited (sync variant), not fire-and-forget, "
        "or the user's reply will race past the write."
    )

    pending = buffer.store[("async_test_9a3b_approval", "pending_clarification")]
    assert pending["type"] == "workflow_approval"
    assert pending["workflow_id"] == "wf_test_123"
    assert pending["use_async"] is True
    assert pending["webhook_url"] == "http://127.0.0.1:8765"
    assert pending["original_message"].startswith("Research")

    # Response must carry the approval-required metadata.
    assert response.metadata["approval_required"] is True
    assert response.metadata["requires_user_response"] is True


@pytest.mark.asyncio
async def test_workflow_approval_kv_set_completes_before_kv_get_can_race() -> None:
    """
    Simulate the race window: a follow-up reader (the user's "Yes, proceed"
    message) arrives immediately after the approval response is returned.
    Because we use the sync variant the read MUST see the pending state.
    """
    buffer = _OrderedBufferMemory(slow_ms=30)
    overlord = _make_overlord_stub(buffer)

    response_task = asyncio.create_task(
        overlord._handle_workflow_approval(
            workflow=_make_workflow(),
            message="Build a new feature with comprehensive tests",
            user_id="test_user",
            session_id="race_test_session",
            request_id="req_init_002",
            use_async=False,
            webhook_url=None,
        )
    )

    response = await response_task

    # The follow-up read must observe the write.
    pending = await overlord._get_pending_clarification("race_test_session")
    assert pending is not None, (
        "Follow-up read returned None — kv_set raced past the response, "
        "reproducing the workflow-approval routing bug."
    )
    assert pending["type"] == "workflow_approval"
    assert response.content.startswith("Here's my proposed approach")

    # Op ordering: the kv_set must appear in ops before any subsequent kv_get.
    set_indices = [i for i, op in enumerate(buffer.ops) if op[0] == "set"]
    get_indices = [i for i, op in enumerate(buffer.ops) if op[0] == "get"]
    assert set_indices, "expected a kv_set op for the approval write"
    assert get_indices, "expected a kv_get op for the follow-up read"
    assert set_indices[0] < get_indices[0], (
        f"kv_set must precede kv_get; got ops={buffer.ops}"
    )


@pytest.mark.asyncio
async def test_workflow_approval_without_session_id_is_a_noop() -> None:
    """No session_id → no pending-clarification write is attempted."""
    buffer = _OrderedBufferMemory()
    overlord = _make_overlord_stub(buffer)

    response = await overlord._handle_workflow_approval(
        workflow=_make_workflow(),
        message="Ad-hoc request",
        user_id="test_user",
        session_id=None,
        request_id="req_init_003",
        use_async=False,
        webhook_url=None,
    )

    assert buffer.store == {}
    assert all(op[0] != "set" for op in buffer.ops)
    assert response.metadata["approval_required"] is True
