"""DELETE /requests/{request_id} reports cancellation honestly.

Cancellation has two mechanisms. ``RequestTracker.mark_cancelled`` sets a
cooperative flag that processing checkpoints honour (they raise
``RequestCancelledException`` at the next safe point), and
``Overlord.cancel_request`` cancels the asyncio task directly. Only
background workflow executions carry a ``task_ref``, so hard task
cancellation is unavailable for an ordinary chat turn.

The route used to key its status code off the hard-cancellation result
alone, so cancelling a normal chat turn returned 400 OPERATION_FAILED even
though the turn did abort at its next checkpoint. These tests pin the
corrected contract: 2xx whenever the cancellation flag was set, with a
``cancellation`` field distinguishing ``cooperative`` from ``immediate``,
404 for unknown ids, and a genuine failure only when the request already
finished.
"""

from __future__ import annotations

import asyncio
import time
from types import MethodType, SimpleNamespace
from typing import Any, Optional

import httpx
import pytest
from fastapi import FastAPI

from muxi.runtime.formation.background.request_tracker import (
    RequestState,
    RequestStatus,
    RequestTracker,
)
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.formation.server.routes.client.requests import router

CLIENT_KEY = "client-key-for-tests"
USER = "user123"


class StubBufferMemory:
    """Only ``kv_set`` is reached, and only on the hard-cancellation path."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, Any]] = []

    async def kv_set(self, key: str, value: Any, ttl: int, namespace: str) -> None:
        self.writes.append((key, value))


def make_overlord() -> SimpleNamespace:
    """An overlord stub carrying the real ``cancel_request`` implementation.

    Binding the real method (rather than faking its return value) is the
    point of these tests: the no-``task_ref`` branch returning
    ``success: False`` is exactly the behaviour the route has to stop
    treating as an error.
    """
    overlord = SimpleNamespace(
        request_tracker=RequestTracker(),
        buffer_memory=StubBufferMemory(),
        is_multi_user=False,
    )
    overlord.cancel_request = MethodType(Overlord.cancel_request, overlord)
    return overlord


def make_app(overlord: Optional[SimpleNamespace]) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.formation = SimpleNamespace(
        _overlord=overlord,
        _api_keys={"client": CLIENT_KEY, "admin": "admin-key-for-tests"},
    )
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Muxi-Client-Key": CLIENT_KEY, "X-Muxi-User-ID": USER},
    )


async def track(
    overlord: SimpleNamespace,
    request_id: str,
    status: RequestStatus = RequestStatus.PROCESSING,
    task_ref: Optional[asyncio.Task] = None,
) -> RequestState:
    """Track a request owned by the single-user id the route normalizes to."""
    state = RequestState(
        id=request_id,
        status=status,
        start_time=time.time(),
        user_id="0",  # single-user mode: the route normalizes X-Muxi-User-ID to "0"
        task_ref=task_ref,
    )
    await overlord.request_tracker.track_request(request_id, state)
    return state


async def test_cancel_in_flight_chat_turn_reports_cooperative_cancellation() -> None:
    """A normal chat turn has no task_ref: 200 + cooperative, flag actually set."""
    overlord = make_overlord()
    await track(overlord, "req-chat")

    async with client_for(make_app(overlord)) as client:
        response = await client.delete("/requests/req-chat")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["request_id"] == "req-chat"
    assert body["data"]["status"] == "cancelled"
    assert body["data"]["cancellation"] == "cooperative"

    # The guarantee the 2xx is claiming: checkpoints will see the flag.
    assert overlord.request_tracker.is_cancelled("req-chat")


async def test_cancel_unknown_request_returns_404() -> None:
    overlord = make_overlord()

    async with client_for(make_app(overlord)) as client:
        response = await client.delete("/requests/req-missing")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert not overlord.request_tracker.is_cancelled("req-missing")


async def test_cancel_background_workflow_reports_immediate_cancellation() -> None:
    """A tracked task_ref still gets hard-cancelled, and says so."""
    overlord = make_overlord()

    started = asyncio.Event()

    async def never_finishes() -> None:
        started.set()
        await asyncio.sleep(3600)

    task = asyncio.create_task(never_finishes())
    await started.wait()
    await track(overlord, "req-workflow", status=RequestStatus.RUNNING, task_ref=task)

    async with client_for(make_app(overlord)) as client:
        response = await client.delete("/requests/req-workflow")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["cancellation"] == "immediate"
    assert overlord.request_tracker.is_cancelled("req-workflow")

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


@pytest.mark.parametrize("status", [RequestStatus.COMPLETED, RequestStatus.FAILED])
async def test_cancel_finished_request_still_fails(status: RequestStatus) -> None:
    """Neither mechanism applies once the request is done -- keep the error."""
    overlord = make_overlord()
    await track(overlord, "req-done", status=status)

    async with client_for(make_app(overlord)) as client:
        response = await client.delete("/requests/req-done")

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "OPERATION_FAILED"
    assert status.value in body["error"]["message"]

    # A finished request must not be left carrying a cancellation flag.
    assert not overlord.request_tracker.is_cancelled("req-done")


async def test_cancelling_twice_is_idempotent() -> None:
    """Documented behaviour: re-cancelling is safe, not an error."""
    overlord = make_overlord()
    await track(overlord, "req-twice")

    async with client_for(make_app(overlord)) as client:
        first = await client.delete("/requests/req-twice")
        second = await client.delete("/requests/req-twice")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["cancellation"] == "cooperative"
