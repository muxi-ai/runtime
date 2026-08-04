"""Unit tests for Idempotency-Key support on Formation API endpoints.

Covers:
  - IdempotencyCache: TTL expiry, scoping, prune behavior
  - The @idempotent decorator through a real FastAPI app: replay of cached
    responses, envelope echo of the key, per-user, per-path and per-response-
    mode scoping, error responses staying retryable, streaming passthrough,
    and single-flight coalescing of concurrent duplicates
"""

import asyncio
import time

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from muxi.runtime.datatypes.api import APIEventType, APIObjectType
from muxi.runtime.formation.server.idempotency import (
    IdempotencyCache,
    get_idempotency_cache,
    idempotent,
)
from muxi.runtime.formation.server.responses import create_success_response

# ---------------------------------------------------------------------------
# IdempotencyCache primitives
# ---------------------------------------------------------------------------


def test_cache_get_returns_stored_body():
    cache = IdempotencyCache()
    cache.store("k1", {"data": 1}, 200)
    assert cache.get("k1") == ({"data": 1}, 200)


def test_cache_miss_returns_none():
    cache = IdempotencyCache()
    assert cache.get("missing") is None


def test_cache_entry_expires_after_ttl():
    cache = IdempotencyCache(ttl_seconds=1)
    cache.store("k1", {"data": 1}, 200)
    cache._responses["k1"] = (time.time() - 1, {"data": 1}, 200)
    assert cache.get("k1") is None


def test_scoped_key_separates_endpoint_and_user():
    assert IdempotencyCache.scoped_key("POST /chat", "u1", "abc") != IdempotencyCache.scoped_key(
        "POST /chat", "u2", "abc"
    )
    assert IdempotencyCache.scoped_key("POST /chat", "u1", "abc") != IdempotencyCache.scoped_key(
        "POST /triggers/t1", "u1", "abc"
    )


def test_scoped_key_separates_response_mode():
    assert IdempotencyCache.scoped_key(
        "POST /chat", "u1", "abc", "json"
    ) != IdempotencyCache.scoped_key("POST /chat", "u1", "abc", "stream")


def test_scoped_key_is_unambiguous_for_colon_containing_components():
    # Colon-joining would make these distinct tuples collide:
    #   ("alice", "stream", "json:k") vs ("alice:stream", "json", "k")
    ambiguous_pairs = [
        (("POST /chat", "alice", "json:k", "stream"), ("POST /chat", "alice:stream", "k", "json")),
        (("POST /chat", "alice", "k", "json"), ("POST /chat:alice", "k", "json", "json")),
        (("POST /chat", "u1", "k:json", "json"), ("POST /chat", "u1:k", "json", "json")),
    ]
    for (e1, u1, k1, m1), (e2, u2, k2, m2) in ambiguous_pairs:
        key_a = IdempotencyCache.scoped_key(e1, u1, k1, m1)
        key_b = IdempotencyCache.scoped_key(e2, u2, k2, m2)
        assert key_a != key_b

        # Distinct scope keys must not share cache entries...
        cache = IdempotencyCache()
        cache.store(key_a, {"owner": "a"}, 200)
        assert cache.get(key_b) is None
        assert cache.get(key_a) == ({"owner": "a"}, 200)

        # ...nor single-flight locks
        assert cache.lock_for(key_a) is not cache.lock_for(key_b)


def test_prune_evicts_expired_entries_when_full():
    cache = IdempotencyCache()
    from muxi.runtime.formation.server import idempotency as idem_module

    for i in range(idem_module.MAX_CACHE_ENTRIES):
        cache._responses[f"k{i}"] = (time.time() - 1, {}, 200)
    cache.store("fresh", {"data": 1}, 200)
    assert cache.get("fresh") == ({"data": 1}, 200)
    assert len(cache._responses) == 1


# ---------------------------------------------------------------------------
# @idempotent decorator through a real FastAPI app
# ---------------------------------------------------------------------------


class _ChatBody(BaseModel):
    """Minimal stand-in for ChatRequest: streaming is the default."""

    message: str
    stream: bool = True


@pytest.fixture
def app_and_calls():
    app = FastAPI()
    calls = {"count": 0}

    @app.post("/v1/jobs")
    @idempotent("jobs_create")
    async def create_job(request: Request) -> JSONResponse:
        calls["count"] += 1
        envelope = create_success_response(
            APIObjectType.REQUEST,
            APIEventType.REQUEST_COMPLETED,
            {"job_id": f"job-{calls['count']}"},
        )
        return JSONResponse(content=envelope.model_dump(), status_code=200)

    @app.post("/v1/failing")
    @idempotent("failing")
    async def failing(request: Request) -> JSONResponse:
        calls["count"] += 1
        return JSONResponse(content={"error": "boom"}, status_code=500)

    @app.post("/v1/stream")
    @idempotent("stream")
    async def stream(request: Request):
        calls["count"] += 1

        async def gen():
            yield "data: x\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    # Mirrors the real /v1/chat contract: one endpoint, two response shapes
    # selected by the body's `stream` flag
    @app.post("/v1/chat")
    @idempotent("chat")
    async def chat(request: Request, chat_request: _ChatBody):
        calls["count"] += 1
        if chat_request.stream is False:
            envelope = create_success_response(
                APIObjectType.REQUEST,
                APIEventType.REQUEST_COMPLETED,
                {"reply": f"reply-{calls['count']}"},
            )
            return JSONResponse(content=envelope.model_dump(), status_code=200)

        async def gen():
            yield "data: token\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app, calls


def test_requests_without_key_are_not_deduplicated(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    client.post("/v1/jobs")
    client.post("/v1/jobs")
    assert calls["count"] == 2


def test_duplicate_key_replays_cached_response(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)

    first = client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "abc"})
    second = client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "abc"})

    assert calls["count"] == 1
    assert first.json()["data"]["job_id"] == "job-1"
    assert second.json() == first.json()


def test_key_echoed_in_response_envelope(app_and_calls):
    app, _ = app_and_calls
    client = TestClient(app)
    response = client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "echo-me"})
    assert response.json()["request"]["idempotency_key"] == "echo-me"


def test_different_keys_process_independently(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "k1"})
    client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "k2"})
    assert calls["count"] == 2


def test_same_key_different_users_process_independently(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "k1", "X-Muxi-User-Id": "alice"})
    client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "k1", "X-Muxi-User-Id": "bob"})
    assert calls["count"] == 2


def test_header_is_case_insensitive(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    client.post("/v1/jobs", headers={"x-muxi-idempotency-key": "k1"})
    client.post("/v1/jobs", headers={"X-MUXI-IDEMPOTENCY-KEY": "k1"})
    assert calls["count"] == 1


def test_error_responses_are_not_cached(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    first = client.post("/v1/failing", headers={"X-Muxi-Idempotency-Key": "k1"})
    second = client.post("/v1/failing", headers={"X-Muxi-Idempotency-Key": "k1"})
    assert first.status_code == 500
    assert second.status_code == 500
    assert calls["count"] == 2


def test_streaming_responses_pass_through_uncached(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    first = client.post("/v1/stream", headers={"X-Muxi-Idempotency-Key": "k1"})
    second = client.post("/v1/stream", headers={"X-Muxi-Idempotency-Key": "k1"})
    assert first.headers["content-type"].startswith("text/event-stream")
    assert second.headers["content-type"].startswith("text/event-stream")
    assert calls["count"] == 2


def test_stream_retry_does_not_replay_cached_json(app_and_calls):
    """A stream:true retry of a cached stream:false key must not get JSON."""
    app, calls = app_and_calls
    client = TestClient(app)
    headers = {"X-Muxi-Idempotency-Key": "k1"}

    first = client.post("/v1/chat", json={"message": "hi", "stream": False}, headers=headers)
    second = client.post("/v1/chat", json={"message": "hi", "stream": True}, headers=headers)

    assert first.headers["content-type"].startswith("application/json")
    assert second.headers["content-type"].startswith("text/event-stream")
    assert second.text == "data: token\n\n"
    assert calls["count"] == 2


def test_json_retry_still_replays_within_same_mode(app_and_calls):
    app, calls = app_and_calls
    client = TestClient(app)
    headers = {"X-Muxi-Idempotency-Key": "k1"}
    body = {"message": "hi", "stream": False}

    first = client.post("/v1/chat", json=body, headers=headers)
    second = client.post("/v1/chat", json=body, headers=headers)

    assert calls["count"] == 1
    assert second.json() == first.json()


def test_json_retry_after_stream_is_not_served_from_stream_scope(app_and_calls):
    """The reverse order: streaming is never cached, so the JSON call runs."""
    app, calls = app_and_calls
    client = TestClient(app)
    headers = {"X-Muxi-Idempotency-Key": "k1"}

    client.post("/v1/chat", json={"message": "hi", "stream": True}, headers=headers)
    second = client.post("/v1/chat", json={"message": "hi", "stream": False}, headers=headers)

    assert second.headers["content-type"].startswith("application/json")
    assert second.json()["data"]["reply"] == "reply-2"
    assert calls["count"] == 2


def test_cache_is_app_scoped(app_and_calls):
    app, _ = app_and_calls
    client = TestClient(app)
    client.post("/v1/jobs", headers={"X-Muxi-Idempotency-Key": "k1"})
    cache = get_idempotency_cache(app)
    assert isinstance(cache, IdempotencyCache)
    assert len(cache._responses) == 1


async def test_concurrent_duplicates_are_single_flighted():
    app = FastAPI()
    calls = {"count": 0}
    release = asyncio.Event()

    @app.post("/v1/slow")
    @idempotent("slow")
    async def slow(request: Request) -> JSONResponse:
        calls["count"] += 1
        await release.wait()
        envelope = create_success_response(
            APIObjectType.REQUEST,
            APIEventType.REQUEST_COMPLETED,
            {"result": calls["count"]},
        )
        return JSONResponse(content=envelope.model_dump(), status_code=200)

    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        task1 = asyncio.create_task(
            client.post("/v1/slow", headers={"X-Muxi-Idempotency-Key": "k1"})
        )
        task2 = asyncio.create_task(
            client.post("/v1/slow", headers={"X-Muxi-Idempotency-Key": "k1"})
        )
        await asyncio.sleep(0.1)
        release.set()
        first, second = await asyncio.gather(task1, task2)

    assert calls["count"] == 1
    assert first.json()["data"] == {"result": 1}
    assert second.json() == first.json()
