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
