import asyncio
import json

import pytest

from muxi.runtime.formation.server.routes.client import chat as chat_routes


async def _collect_chunks(response_awaitable):
    return [chunk async for chunk in chat_routes._stream_with_keepalive(response_awaitable)]


class TestChatSSEKeepalive:
    @pytest.mark.asyncio
    async def test_emits_keepalive_while_waiting_for_stream_setup(self, monkeypatch):
        monkeypatch.setattr(chat_routes, "SSE_KEEPALIVE_INTERVAL_SECONDS", 0.01)

        async def build_response():
            await asyncio.sleep(0.03)

            async def _stream():
                yield {"content": "ready"}

            return _stream()

        chunks = await _collect_chunks(build_response())

        assert chunks[0] == chat_routes.SSE_KEEPALIVE_COMMENT
        assert chunks.count(chat_routes.SSE_KEEPALIVE_COMMENT) >= 2

        payloads = [json.loads(chunk[6:]) for chunk in chunks if chunk.startswith("data: ")]
        assert payloads == [{"token": {"content": "ready"}}]
        assert chunks[-1].startswith("event: done")

    @pytest.mark.asyncio
    async def test_emits_keepalive_during_long_gap_between_tokens(self, monkeypatch):
        monkeypatch.setattr(chat_routes, "SSE_KEEPALIVE_INTERVAL_SECONDS", 0.01)

        async def build_response():
            async def _stream():
                yield {"content": "first"}
                await asyncio.sleep(0.03)
                yield {"content": "second"}

            return _stream()

        chunks = await _collect_chunks(build_response())

        data_indices = [index for index, chunk in enumerate(chunks) if chunk.startswith("data: ")]
        payloads = [json.loads(chunks[index][6:]) for index in data_indices]

        assert payloads == [
            {"token": {"content": "first"}},
            {"token": {"content": "second"}},
        ]
        assert any(
            chunk == chat_routes.SSE_KEEPALIVE_COMMENT
            for chunk in chunks[data_indices[0] + 1 : data_indices[1]]
        )
