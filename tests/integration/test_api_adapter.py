from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from grafted.victim.api_adapter import RestApiAdapter
from grafted.victim.mock.app import app


@pytest.mark.asyncio
async def test_send_turn_chat_mode() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adapter = RestApiAdapter(base_url="http://test", mode="chat", client=client)
        out = await adapter.send_turn("s1", "hello")
    assert "response" in out
    assert isinstance(out["duration_ms"], int)


@pytest.mark.asyncio
async def test_send_turn_stream_mode() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adapter = RestApiAdapter(base_url="http://test", mode="stream", client=client)
        out = await adapter.send_turn("s1", "hello", mode="stream")
    assert "response" in out


@pytest.mark.asyncio
async def test_upload_file() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adapter = RestApiAdapter(base_url="http://test", client=client)
        out = await adapter.upload_file("s1", "a.md", b"hello", "text/markdown")
    assert "id" in out


@pytest.mark.asyncio
async def test_list_docs() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adapter = RestApiAdapter(base_url="http://test", client=client)
        await adapter.upload_file("s-list", "a.md", b"hello", "text/markdown")
        docs = await adapter.list_docs("s-list")
    assert isinstance(docs, list)
    assert len(docs) >= 1


@pytest.mark.asyncio
async def test_reset_session() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adapter = RestApiAdapter(base_url="http://test", client=client)
        await adapter.upload_file("s-reset-adapter", "a.md", b"hello", "text/markdown")
        before = await adapter.list_docs("s-reset-adapter")
        assert len(before) >= 1
        await adapter.reset_session("s-reset-adapter")
        after = await adapter.list_docs("s-reset-adapter")
    assert after == []
