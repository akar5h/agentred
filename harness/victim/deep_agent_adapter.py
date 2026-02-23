from __future__ import annotations

from typing import Optional

import httpx

from harness.victim.api_adapter import RestApiAdapter


class DeepAgentAdapter(RestApiAdapter):
    """Thin adapter for the deepagent-doc-pipeline target.

    Differences from RestApiAdapter:
    - Injects X-Tenant-Id / X-User-Id headers on every request
    - reset_session() is a no-op (no /reset endpoint; use a fresh session_id instead)
    """

    def __init__(
        self,
        base_url: str,
        mode: str = "chat",
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(base_url, mode, client=client)
        self._extra_headers: dict[str, str] = {
            "X-Tenant-Id": tenant_id,
            "X-User-Id": user_id,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        **kwargs,
    ) -> httpx.Response:
        existing: dict = kwargs.pop("headers", {}) or {}
        kwargs["headers"] = {**self._extra_headers, **existing}
        return await super()._request(method, path, timeout=timeout, **kwargs)

    async def reset_session(self, session_id: str, *, timeout: float = 10.0) -> None:
        """No-op: deepagent-doc-pipeline has no /reset endpoint.

        Callers should pass a fresh session_id UUID to start a new conversation.
        """

    async def get_debug_state(self, session_id: str, *, timeout: float = 30.0) -> dict:
        """GET /debug/{session_id} — returns full agent state (messages, memory, tool calls)."""
        from harness.core.exceptions import InfraError  # local to avoid circular import
        resp = await self._request("GET", f"/debug/{session_id}", timeout=timeout)
        if resp.status_code >= 400:
            raise InfraError(f"get_debug_state failed with status {resp.status_code}: {resp.text}")
        payload = resp.json() if resp.content else {}
        return payload if isinstance(payload, dict) else {}

    async def get_memories(self, *, limit: int = 20, timeout: float = 30.0) -> list[dict]:
        """GET /memories?limit=N — returns stored memory entries for the current user."""
        from harness.core.exceptions import InfraError  # local to avoid circular import
        resp = await self._request("GET", "/memories", timeout=timeout, params={"limit": limit})
        if resp.status_code >= 400:
            raise InfraError(f"get_memories failed with status {resp.status_code}: {resp.text}")
        payload = resp.json() if resp.content else []
        return payload if isinstance(payload, list) else []

    async def get_tool_calls(
        self, session_id: str, *, limit: int = 50, timeout: float = 30.0
    ) -> list[dict]:
        """GET /tool-calls?session_id=&limit=N — returns tool call log for a session."""
        from harness.core.exceptions import InfraError  # local to avoid circular import
        resp = await self._request(
            "GET", "/tool-calls", timeout=timeout,
            params={"session_id": session_id, "limit": limit},
        )
        if resp.status_code >= 400:
            raise InfraError(f"get_tool_calls failed with status {resp.status_code}: {resp.text}")
        payload = resp.json() if resp.content else []
        return payload if isinstance(payload, list) else []
