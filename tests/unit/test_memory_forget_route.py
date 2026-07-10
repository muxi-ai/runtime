"""GDPR forget endpoint job lifecycle tests (substrate admin hardening).

POST /memory/forget soft-deletes inline (the response always carries
``deleted_events``) but runs the projection rebuild as a tracked
background job by default, so large users never block the admin call:
202 + ``job_id`` pollable at GET /memory/forget/{job_id}. Covers the
full job lifecycle (spawn, poll to completion, rebuild report attached,
derived state actually removed), the ``?sync=true`` and ``background:
false`` inline escape hatches, the ``rebuild: false`` posture, unknown
job polling, and the substrate-unavailable 503.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from muxi.runtime.formation.background.request_tracker import RequestStatus, RequestTracker
from muxi.runtime.formation.server.routes.admin.memory import _start_tracked_job, router
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import KnowledgeGraphProjector, MemoryEventService
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService

FORMATION_ID = "forget-route-test"
USER = "u1"


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/forget_route.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def events(db_manager):
    return MemoryEventService(db_manager, FORMATION_ID)


@pytest.fixture
def graph(db_manager, events):
    service = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
    events.register_projector(KnowledgeGraphProjector(service))
    return service


def make_app(memory_events) -> FastAPI:
    """The admin memory router wired the way the runtime serves it."""
    app = FastAPI()
    app.include_router(router)
    overlord = (
        SimpleNamespace(memory_events=memory_events, request_tracker=RequestTracker())
        if memory_events is not None
        else None
    )
    app.state.formation = SimpleNamespace(_overlord=overlord, formation_id=FORMATION_ID)
    return app


def extraction(company):
    return {
        "entities": [{"name": company, "type": "company", "confidence": 0.9}],
        "relationships": [],
    }


async def seed_two_sources(graph):
    """Facts from a chat turn and from an imported source (gmail)."""
    await graph.store_extraction(USER, extraction("Acme"), source="interaction")
    await graph.store_extraction(USER, extraction("MailCorp"), source="gmail")


def poll_until_terminal(client, job_id, deadline_seconds=30.0):
    """Poll the forget job until it leaves 'processing'.

    The job task runs on the TestClient portal loop (a separate thread),
    so sleeping here does not starve it -- it gives the background rebuild
    real wall-time. Sleep-less polling raced the job on loaded CI runners
    and flaked with "never reached a terminal status".
    """
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/memory/forget/{job_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        if data["status"] != "processing":
            return data
        time.sleep(0.05)
    raise AssertionError("forget job never reached a terminal status")


class TestBackgroundForget:
    async def test_background_job_lifecycle(self, events, graph):
        await seed_two_sources(graph)
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is not None

        with TestClient(make_app(events)) as client:
            response = client.post(
                "/memory/forget",
                json={"user_id": USER, "source": "gmail", "reason": "gdpr"},
            )
            assert response.status_code == 202
            data = response.json()["data"]
            # The soft delete ran inline; only the rebuild went background.
            assert data["deleted_events"] == 1
            assert data["status"] == "processing"
            assert data["job_id"].startswith("forget_")
            assert data["status_url"] == f"/memory/forget/{data['job_id']}"
            assert "projections" not in data

            final = poll_until_terminal(client, data["job_id"])
            assert final["status"] == "completed"
            assert final["projections"]["knowledge_graph"]["failed"] == 0

        # Derived state reflects the forgetting.
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is None
        assert await graph.storage.get_entity(USER, "company", "Acme") is not None

    async def test_failed_job_reports_error(self, events, graph, monkeypatch):
        await seed_two_sources(graph)

        async def broken_rebuild(*args, **kwargs):
            raise RuntimeError("rebuild exploded")

        monkeypatch.setattr(events, "rebuild", broken_rebuild)
        with TestClient(make_app(events)) as client:
            response = client.post("/memory/forget", json={"user_id": USER, "source": "gmail"})
            assert response.status_code == 202
            final = poll_until_terminal(client, response.json()["data"]["job_id"])
            assert final["status"] == "failed"
            assert "rebuild exploded" in final["error"]

    def test_unknown_job_returns_404(self, events):
        with TestClient(make_app(events)) as client:
            response = client.get("/memory/forget/forget_nope")
            assert response.status_code == 404


class TestSyncEscapeHatches:
    async def test_sync_query_param_blocks_inline(self, events, graph):
        await seed_two_sources(graph)
        with TestClient(make_app(events)) as client:
            response = client.post(
                "/memory/forget?sync=true",
                json={"user_id": USER, "source": "gmail", "reason": "gdpr"},
            )
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["deleted_events"] == 1
            assert data["projections"]["knowledge_graph"]["failed"] == 0
            assert "job_id" not in data
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is None

    async def test_background_false_body_blocks_inline(self, events, graph):
        await seed_two_sources(graph)
        with TestClient(make_app(events)) as client:
            response = client.post(
                "/memory/forget",
                json={"user_id": USER, "source": "gmail", "background": False},
            )
            assert response.status_code == 200
            assert "projections" in response.json()["data"]

    async def test_rebuild_false_skips_rebuild_entirely(self, events, graph):
        await seed_two_sources(graph)
        with TestClient(make_app(events)) as client:
            response = client.post(
                "/memory/forget",
                json={"user_id": USER, "source": "gmail", "rebuild": False},
            )
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["rebuild_required"] == ["knowledge_graph"]
            assert "job_id" not in data
        # No rebuild ran: the projection still shows the forgotten fact.
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is not None


class TestUnavailableSubstrate:
    def test_missing_substrate_returns_503(self):
        with TestClient(make_app(None)) as client:
            response = client.post("/memory/forget", json={"user_id": USER, "source": "gmail"})
            assert response.status_code == 503


class TestJobCancellation:
    """Graceful-shutdown cancellation marks tracked jobs terminal.

    ``except Exception`` alone would miss asyncio.CancelledError and
    strand the tracker entry at PROCESSING forever; the shared
    ``_start_tracked_job`` helper (rebuild AND forget paths) must mark
    the job CANCELLED and re-raise so the task cancels cleanly.
    """

    async def test_cancelled_job_marked_terminal_and_reraises(self):
        tracker = RequestTracker()
        overlord = SimpleNamespace(request_tracker=tracker)
        started = asyncio.Event()

        async def runner():
            started.set()
            await asyncio.sleep(3600)  # a long rebuild, interrupted by shutdown

        job_id = await _start_tracked_job(overlord, "forget", USER, runner)
        await asyncio.wait_for(started.wait(), timeout=5.0)

        state = await tracker.get_request(job_id)
        assert state.status is RequestStatus.PROCESSING
        state.task_ref.cancel()
        with pytest.raises(asyncio.CancelledError):  # cancellation propagates
            await state.task_ref

        final = await tracker.get_request(job_id)
        assert final.status is RequestStatus.CANCELLED  # terminal, not stuck
        assert final.error == "job cancelled"

    async def test_completed_job_still_reports_completed(self):
        """The cancellation guard does not disturb the happy path."""
        tracker = RequestTracker()
        overlord = SimpleNamespace(request_tracker=tracker)

        async def runner():
            return {"projections": {}}

        job_id = await _start_tracked_job(overlord, "rebuild", USER, runner)
        state = await tracker.get_request(job_id)
        await state.task_ref
        final = await tracker.get_request(job_id)
        assert final.status is RequestStatus.COMPLETED
