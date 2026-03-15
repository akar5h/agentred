from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from harness.victim.hr_api_adapter import HrApiAdapter


def _mock_response(status_code: int = 200, json_data=None, content: bytes = b"x") -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = content
    resp.text = str(json_data) if json_data else ""
    resp.json.return_value = json_data
    return resp


def _make_adapter() -> HrApiAdapter:
    client = AsyncMock(spec=httpx.AsyncClient)
    adapter = HrApiAdapter("http://fake-hr", client=client)
    return adapter


# ---------------------------------------------------------------------------
# get_memories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_memories_returns_query_history() -> None:
    """get_memories should return entries from /history/queries."""
    adapter = _make_adapter()
    adapter._request = AsyncMock(return_value=_mock_response(
        json_data={"entries": [{"query": "hello", "ts": 1}]},
    ))

    result = await adapter.get_memories()
    assert result == [{"query": "hello", "ts": 1}]
    adapter._request.assert_awaited_once_with("GET", "/history/queries", timeout=30.0)


@pytest.mark.asyncio
async def test_get_memories_returns_empty_on_error() -> None:
    """get_memories should return [] when the endpoint returns an error."""
    adapter = _make_adapter()
    adapter._request = AsyncMock(return_value=_mock_response(status_code=500))

    result = await adapter.get_memories()
    assert result == []


@pytest.mark.asyncio
async def test_get_memories_handles_list_response() -> None:
    """get_memories should handle a bare list response."""
    adapter = _make_adapter()
    adapter._request = AsyncMock(return_value=_mock_response(
        json_data=[{"q": "a"}, {"q": "b"}],
    ))

    result = await adapter.get_memories()
    assert result == [{"q": "a"}, {"q": "b"}]


@pytest.mark.asyncio
async def test_get_memories_respects_limit() -> None:
    """get_memories should cap returned entries at the limit."""
    adapter = _make_adapter()
    adapter._request = AsyncMock(return_value=_mock_response(
        json_data={"entries": [{"i": i} for i in range(50)]},
    ))

    result = await adapter.get_memories(limit=5)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_get_memories_uses_queries_key() -> None:
    """get_memories should fall back to 'queries' key if 'entries' missing."""
    adapter = _make_adapter()
    adapter._request = AsyncMock(return_value=_mock_response(
        json_data={"queries": [{"q": "x"}]},
    ))

    result = await adapter.get_memories()
    assert result == [{"q": "x"}]


# ---------------------------------------------------------------------------
# get_debug_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_debug_state_returns_payload() -> None:
    """get_debug_state should return the JSON payload when endpoint exists."""
    adapter = _make_adapter()
    adapter._session_map["sess-1"] = "server-1"
    adapter._request = AsyncMock(return_value=_mock_response(
        json_data={"agents": ["a1"], "tools": ["t1"]},
    ))

    result = await adapter.get_debug_state("sess-1")
    assert result == {"agents": ["a1"], "tools": ["t1"]}
    adapter._request.assert_awaited_once_with("GET", "/debug/server-1", timeout=30.0)


@pytest.mark.asyncio
async def test_get_debug_state_caches_404() -> None:
    """get_debug_state should cache 404 and skip future calls."""
    adapter = _make_adapter()
    adapter._session_map["sess-1"] = "server-1"
    adapter._request = AsyncMock(return_value=_mock_response(status_code=404))

    # First call — hits endpoint, gets 404
    result1 = await adapter.get_debug_state("sess-1")
    assert result1 == {}
    assert adapter._debug_unavailable is True

    # Second call — should not hit endpoint at all (cached)
    adapter._request.reset_mock()
    result2 = await adapter.get_debug_state("sess-1")
    assert result2 == {}
    adapter._request.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_debug_state_caches_infra_error() -> None:
    """get_debug_state should cache InfraError (connection refused etc.)."""
    from harness.core.exceptions import InfraError

    adapter = _make_adapter()
    adapter._session_map["sess-1"] = "server-1"
    adapter._request = AsyncMock(side_effect=InfraError("connection refused"))

    result = await adapter.get_debug_state("sess-1")
    assert result == {}
    assert adapter._debug_unavailable is True


@pytest.mark.asyncio
async def test_get_debug_state_returns_empty_on_500() -> None:
    """get_debug_state should return {} on 500 but NOT cache (transient error)."""
    adapter = _make_adapter()
    adapter._session_map["sess-1"] = "server-1"
    adapter._request = AsyncMock(return_value=_mock_response(status_code=500))

    result = await adapter.get_debug_state("sess-1")
    assert result == {}
    # Should NOT cache — 500 is transient
    assert adapter._debug_unavailable is False
