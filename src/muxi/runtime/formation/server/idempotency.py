"""
In-memory idempotency-key support for Formation API endpoints.

Clients send an ``Idempotency-Key`` header on mutating requests; retries with
the same key within the TTL replay the original JSON response instead of
processing the request again. Keys are scoped per endpoint and user so
different callers (or different endpoints) can reuse the same key safely.

Semantics:
  - Only successful (2xx) JSON responses are cached; errors are retryable.
  - Streaming (SSE) responses pass through untouched: a token stream cannot
    be replayed from a response cache, and duplicate sync chats are harmless.
  - Concurrent requests with the same key are single-flighted: the second
    caller waits for the first to finish, then receives the cached response.
  - Storage is in-process with a TTL, mirroring the RequestTracker precedent;
    like async request state, cached responses do not survive a restart.
"""

import asyncio
import functools
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse

from ...services import observability
from ...utils.fastjson import json
from .responses import APIResponse
from .utils import get_header_case_insensitive

IDEMPOTENCY_HEADER = "Idempotency-Key"
DEFAULT_TTL_SECONDS = 24 * 60 * 60
MAX_CACHE_ENTRIES = 10_000


class IdempotencyCache:
    """In-memory idempotency response cache with TTL and single-flight locks."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        # scoped_key -> (expires_at, response_body, status_code)
        self._responses: Dict[str, Tuple[float, Dict[str, Any], int]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    @staticmethod
    def scoped_key(endpoint: str, user_id: str, key: str) -> str:
        return f"{endpoint}:{user_id}:{key}"

    def lock_for(self, scoped_key: str) -> asyncio.Lock:
        """Get (or create) the single-flight lock for a scoped key."""
        lock = self._locks.get(scoped_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[scoped_key] = lock
        return lock

    def get(self, scoped_key: str) -> Optional[Tuple[Dict[str, Any], int]]:
        """Return the cached (body, status_code) if present and not expired."""
        entry = self._responses.get(scoped_key)
        if entry is None:
            return None
        expires_at, body, status_code = entry
        if expires_at <= time.time():
            self._responses.pop(scoped_key, None)
            self._locks.pop(scoped_key, None)
            return None
        return body, status_code

    def store(self, scoped_key: str, body: Dict[str, Any], status_code: int) -> None:
        self._prune()
        self._responses[scoped_key] = (time.time() + self.ttl_seconds, body, status_code)

    def _prune(self) -> None:
        if len(self._responses) < MAX_CACHE_ENTRIES:
            return
        now = time.time()
        self._responses = {key: entry for key, entry in self._responses.items() if entry[0] > now}
        self._locks = {
            key: lock
            for key, lock in self._locks.items()
            if lock.locked() or key in self._responses
        }
        overflow = len(self._responses) - MAX_CACHE_ENTRIES + 1
        if overflow > 0:
            # Still full after dropping expired entries: evict the oldest
            for key, _ in sorted(self._responses.items(), key=lambda item: item[1][0])[:overflow]:
                self._responses.pop(key, None)


def get_idempotency_cache(app) -> IdempotencyCache:
    """Get (or lazily create) the app-scoped idempotency cache."""
    cache = getattr(app.state, "idempotency_cache", None)
    if cache is None:
        cache = IdempotencyCache()
        app.state.idempotency_cache = cache
    return cache


def _find_request(args, kwargs) -> Optional[Request]:
    for value in list(args) + list(kwargs.values()):
        if isinstance(value, Request):
            return value
    return None


def _echo_key(body: Dict[str, Any], key: str) -> None:
    """Echo the idempotency key into the response envelope, if present."""
    request_info = body.get("request")
    if isinstance(request_info, dict):
        request_info["idempotency_key"] = key


def _extract_cacheable_body(response: Any) -> Optional[Tuple[Dict[str, Any], int]]:
    """Extract a JSON body + status from a handler result, if it is cacheable."""
    if isinstance(response, APIResponse):
        return response.model_dump(), 200
    if isinstance(response, JSONResponse):
        try:
            body = json.loads(response.body)
        except (ValueError, TypeError):
            return None
        if isinstance(body, dict):
            return body, response.status_code
    return None


def idempotent(endpoint: str):
    """Wrap a route handler with Idempotency-Key replay support.

    Requests without the header run unchanged. FastAPI resolves dependencies
    against the wrapped handler's signature (functools.wraps preserves it).
    """

    def decorator(handler):
        @functools.wraps(handler)
        async def wrapper(*args, **kwargs):
            request = _find_request(args, kwargs)
            key = (
                get_header_case_insensitive(request.headers, IDEMPOTENCY_HEADER)
                if request is not None
                else None
            )
            if not key:
                return await handler(*args, **kwargs)

            user_id = get_header_case_insensitive(request.headers, "X-Muxi-User-Id") or "0"
            cache = get_idempotency_cache(request.app)
            # Scope by the concrete path so path parameters (e.g. trigger
            # names) get independent key namespaces
            scoped = cache.scoped_key(f"{request.method} {request.url.path}", user_id, key)

            async with cache.lock_for(scoped):
                cached = cache.get(scoped)
                if cached is not None:
                    body, status_code = cached
                    observability.observe(
                        event_type=observability.ConversationEvents.REQUEST_COMPLETED,
                        level=observability.EventLevel.INFO,
                        data={
                            "service": "formation_api_server",
                            "endpoint": endpoint,
                            "user_id": user_id,
                            "idempotency_replay": True,
                        },
                        description=(f"Replayed cached response for idempotency key on {endpoint}"),
                    )
                    return JSONResponse(content=body, status_code=status_code)

                response = await handler(*args, **kwargs)

                extracted = _extract_cacheable_body(response)
                if extracted is not None:
                    body, status_code = extracted
                    if 200 <= status_code < 300:
                        _echo_key(body, key)
                        cache.store(scoped, body, status_code)
                        return JSONResponse(content=body, status_code=status_code)
                return response

        return wrapper

    return decorator
