"""Tests for final-response token streaming (``content`` delta events).

Feature contract
----------------
During a streaming chat turn the FINAL response LLM call (the persona
pass in ``Overlord._apply_persona``) may stream its output as
incremental ``type: "content"`` events so clients can render text as it
generates. The feature is strictly additive:

- the terminal ``completed`` event still carries the full final text;
- deltas are emitted only when the persona output IS the final text --
  call sites that post-process the output (json wrapping, html
  prettify, credential-option formatting) never stream;
- ``overlord.config.response.stream_tokens: false`` disables deltas;
- delta chunking is passed through as the provider yields it (clients
  coalesce); ordering is guaranteed by synchronous emission.
"""

import asyncio

import pytest

from muxi.runtime.datatypes.observability import RequestContext
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.services.observability.context import set_request_context
from muxi.runtime.services.streaming import streaming_manager

REQUEST_ID = "req_stream_deltas_test"
USER_ID = "user_1"
SESSION_ID = "sess_1"

CHUNKS = ["Hel", "lo ", "wor", "ld!"]


class _FakeStreamingLLM:
    """Persona model stub with both streaming and non-streaming APIs."""

    def __init__(self, chunks=None, stream_error_after=None):
        self.chunks = chunks if chunks is not None else list(CHUNKS)
        self.stream_error_after = stream_error_after
        self.chat_called = False
        self.chat_stream_called = False

    async def chat_stream(self, messages, **kwargs):
        self.chat_stream_called = True
        for i, chunk in enumerate(self.chunks):
            if self.stream_error_after is not None and i >= self.stream_error_after:
                raise RuntimeError("provider stream broke")
            yield chunk

    async def chat(self, messages, **kwargs):
        self.chat_called = True

        class _Response:
            content = "".join(CHUNKS)

        return _Response()


class _NoCancelTracker:
    """Request tracker stub: nothing is ever cancelled."""

    def is_cancelled(self, request_id):
        return False

    async def clear_cancelled(self, request_id):
        pass


def _make_overlord(llm, stream_tokens=True, response_format="markdown"):
    overlord = Overlord.__new__(Overlord)
    overlord.routing_model = llm
    overlord._default_persona = "You are a helpful assistant."
    overlord.request_tracker = _NoCancelTracker()
    overlord.stream_tokens = stream_tokens
    overlord.response_format = response_format
    return overlord


@pytest.fixture(autouse=True)
def _reset_request_context():
    """Never leak the request-context ContextVar into other tests."""
    yield
    set_request_context(None)


@pytest.fixture()
def streaming_request():
    """Set a request context and enable streaming for it; clean up after."""
    set_request_context(RequestContext(id=REQUEST_ID, user_id=USER_ID, session_id=SESSION_ID))
    streaming_manager.enable_streaming(REQUEST_ID, USER_ID, SESSION_ID)
    yield REQUEST_ID
    streaming_manager.disable_streaming(REQUEST_ID)


def _recorded_events(request_id=REQUEST_ID):
    with streaming_manager._lock:
        stream_data = streaming_manager.event_streams.get(request_id)
        return list(stream_data["events"]) if stream_data else []


def _content_events(request_id=REQUEST_ID):
    return [e for e in _recorded_events(request_id) if e["type"] == "content"]


def test_deltas_emitted_in_order_and_returned_text_matches(streaming_request):
    """Streaming persona call emits one content event per chunk, in order."""
    llm = _FakeStreamingLLM()
    overlord = _make_overlord(llm)

    result = asyncio.run(
        overlord._apply_persona("agent says hi", "hello there", stream_deltas=True)
    )

    assert llm.chat_stream_called, "persona call should use the streaming API"
    assert not llm.chat_called, "non-streaming fallback should not fire"

    deltas = [e["content"] for e in _content_events()]
    assert deltas == CHUNKS, "deltas must pass through as chunked, in order"
    # The returned (final) text is the concatenation of the deltas --
    # the terminal completed event downstream carries exactly this text.
    assert result == "".join(CHUNKS)


def test_content_events_carry_standard_envelope(streaming_request):
    """content events ride the standard envelope (ids + timestamp)."""
    overlord = _make_overlord(_FakeStreamingLLM())
    asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    events = _content_events()
    assert events, "expected at least one content event"
    for event in events:
        assert event["request_id"] == REQUEST_ID
        assert event["user_id"] == USER_ID
        assert event["session_id"] == SESSION_ID
        assert "timestamp" in event
        assert event["stage"] == "response_generation"


def test_config_off_no_deltas(streaming_request):
    """stream_tokens: false disables deltas; non-streaming call is used."""
    llm = _FakeStreamingLLM()
    overlord = _make_overlord(llm, stream_tokens=False)

    result = asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert not llm.chat_stream_called
    assert llm.chat_called
    assert _content_events() == []
    assert result == "".join(CHUNKS)


@pytest.mark.parametrize("response_format", ["json", "html"])
def test_rewrite_step_present_no_deltas(streaming_request, response_format):
    """Formats post-processed AFTER persona (json wrap, html prettify) never
    stream: the generated text is not the text the user receives."""
    llm = _FakeStreamingLLM()
    overlord = _make_overlord(llm, response_format=response_format)

    asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert not llm.chat_stream_called
    assert llm.chat_called
    assert _content_events() == []


def test_no_opt_in_no_deltas(streaming_request):
    """Call sites that don't opt in (error paths, credential formatting)
    keep today's behavior even when all runtime gates would allow it."""
    llm = _FakeStreamingLLM()
    overlord = _make_overlord(llm)

    asyncio.run(overlord._apply_persona("raw", "msg"))

    assert not llm.chat_stream_called
    assert llm.chat_called
    assert _content_events() == []


def test_not_streaming_request_no_deltas():
    """Without a streaming subscriber the persona call stays non-streaming."""
    set_request_context(
        RequestContext(id="req_not_streaming", user_id=USER_ID, session_id=SESSION_ID)
    )
    llm = _FakeStreamingLLM()
    overlord = _make_overlord(llm)

    asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert not llm.chat_stream_called
    assert llm.chat_called


def test_stream_failure_falls_back_to_non_streaming(streaming_request):
    """A broken provider stream falls back to the regular call so the turn
    still produces a full response (completed stays authoritative)."""
    llm = _FakeStreamingLLM(stream_error_after=2)
    overlord = _make_overlord(llm)

    result = asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert llm.chat_stream_called
    assert llm.chat_called, "must fall back after the stream errors"
    assert result == "".join(CHUNKS), "fallback must return the full text"


def test_empty_stream_falls_back_to_non_streaming(streaming_request):
    """Zero yielded deltas (empty stream) must not produce an empty reply."""
    llm = _FakeStreamingLLM(chunks=[])
    overlord = _make_overlord(llm)

    result = asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert llm.chat_called
    assert result == "".join(CHUNKS)


def _emit_completed(content, request_id=REQUEST_ID):
    """Emit a terminal completed event the way the overlord does and
    return it (content events are synchronous; completed rides the same
    emit_event path, called directly here for determinism)."""
    streaming_manager.emit_event(request_id, "completed", content, status="success")
    events = _recorded_events(request_id)
    assert events and events[-1]["type"] == "completed"
    return events[-1]


def test_mid_stream_failure_flags_discontinuity_on_completed(streaming_request):
    """Fallback regeneration AFTER published deltas: completed must carry
    stream_discontinuity: true (deltas belong to the abandoned generation)
    while still carrying the full authoritative text."""
    llm = _FakeStreamingLLM(stream_error_after=2)
    overlord = _make_overlord(llm)

    result = asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert len(_content_events()) == 2, "two deltas published before the failure"

    completed = _emit_completed(result)
    assert completed["stream_discontinuity"] is True
    assert completed["content"] == "".join(CHUNKS), "full text stays authoritative"


def test_failure_before_first_delta_no_discontinuity_flag(streaming_request):
    """Zero deltas published before the failure: nothing to invalidate, so
    the completed event carries no flag (absent, not false)."""
    llm = _FakeStreamingLLM(stream_error_after=0)
    overlord = _make_overlord(llm)

    result = asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert llm.chat_called, "must fall back after the stream errors"
    assert _content_events() == []

    completed = _emit_completed(result)
    assert "stream_discontinuity" not in completed


def test_empty_stream_fallback_no_discontinuity_flag(streaming_request):
    """The empty-stream fallback (no error, no deltas) is not a
    discontinuity either."""
    llm = _FakeStreamingLLM(chunks=[])
    overlord = _make_overlord(llm)

    result = asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    completed = _emit_completed(result)
    assert "stream_discontinuity" not in completed


def test_normal_path_no_discontinuity_flag(streaming_request):
    """A clean streamed generation never flags: additive, absent-when-false."""
    llm = _FakeStreamingLLM()
    overlord = _make_overlord(llm)

    result = asyncio.run(overlord._apply_persona("raw", "msg", stream_deltas=True))

    assert [e["content"] for e in _content_events()] == CHUNKS
    completed = _emit_completed(result)
    assert "stream_discontinuity" not in completed


def test_content_events_emitted_synchronously():
    """content events bypass the background emitter thread: they must be
    visible in the event list immediately after stream() returns, or thread
    scheduling could reorder deltas."""
    from muxi.runtime.services import streaming

    request_id = "req_sync_emit"
    set_request_context(RequestContext(id=request_id, user_id=USER_ID, session_id=SESSION_ID))
    streaming_manager.enable_streaming(request_id, USER_ID, SESSION_ID)
    try:
        for i in range(50):
            streaming.stream("content", f"delta-{i}", stage="response_generation")
        deltas = [e["content"] for e in _content_events(request_id)]
        assert deltas == [f"delta-{i}" for i in range(50)]
    finally:
        streaming_manager.disable_streaming(request_id)


def test_llm_chat_stream_passes_provider_chunks_through(monkeypatch):
    """LLM.chat_stream yields provider deltas verbatim -- no coalescing,
    empty chunks skipped."""
    from muxi.runtime.services.llm import llm as llm_module

    class _Delta:
        def __init__(self, content):
            self.content = content

    class _Choice:
        def __init__(self, content):
            self.delta = _Delta(content)

    class _Chunk:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    async def _fake_acreate(**params):
        assert params["stream"] is True

        async def _gen():
            for text in ["a", "", None, "bc", "d"]:
                yield _Chunk(text)

        return _gen()

    monkeypatch.setattr(llm_module.ChatCompletion, "acreate", staticmethod(_fake_acreate))

    llm = llm_module.LLM.__new__(llm_module.LLM)
    llm.model_name = "openai/gpt-test"
    llm._provider = "openai"
    llm._model = "gpt-test"
    llm.temperature = 0.7
    llm.max_tokens = None
    llm.additional_params = {}

    async def _collect():
        return [
            d
            async for d in llm.chat_stream(
                [{"role": "user", "content": "hi"}], max_tokens=100, caching=False
            )
        ]

    assert asyncio.run(_collect()) == ["a", "bc", "d"]
