from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from harness.core.exceptions import InfraError, VictimResetError
from harness.victim.base import VictimAdapter

logger = logging.getLogger("harness.victim.hr_api")


class HrApiAdapter(VictimAdapter):
    """Adapter for the HR AI target at localhost:8000.

    The HR AI generates its own session UUIDs via ``POST /sessions``.
    The harness passes arbitrary session_ids (e.g. ``explore-task1-abc``).
    This adapter maintains ``_session_map`` to translate between the two.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str = "client-techcorp",
        *,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self._client = client
        self._session_map: dict[str, str] = {}
        self._upload_log: list[dict] = []
        self._debug_unavailable: bool = False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 30.0,
        **kwargs,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            if self._client is not None:
                return await self._client.request(method, url, timeout=timeout, **kwargs)
            async with httpx.AsyncClient() as client:
                return await client.request(method, url, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise InfraError(f"{type(exc).__name__}: {exc!r}") from exc

    # ------------------------------------------------------------------
    # Internal: server-side session management
    # ------------------------------------------------------------------

    async def _create_server_session(self, *, timeout: float = 10.0) -> str:
        resp = await self._request(
            "POST", "/sessions",
            timeout=timeout,
            json={"client_id": self.client_id},
        )
        if resp.status_code >= 400:
            raise InfraError(f"POST /sessions failed: {resp.status_code} {resp.text}")
        payload = resp.json() if resp.content else {}
        server_id = payload.get("session_id", "")
        if not server_id:
            raise InfraError("POST /sessions returned no session_id")
        return server_id

    async def _delete_server_session(self, server_id: str, *, timeout: float = 10.0) -> None:
        try:
            resp = await self._request("DELETE", f"/sessions/{server_id}", timeout=timeout)
            if resp.status_code >= 400 and resp.status_code != 404:
                logger.debug("DELETE /sessions/%s returned %s", server_id, resp.status_code)
        except InfraError:
            pass  # best-effort cleanup

    async def _resolve_session(self, session_id: str, *, timeout: float = 10.0) -> str:
        """Resolve harness session_id → server session_id, lazy-creating if needed."""
        if session_id not in self._session_map:
            server_id = await self._create_server_session(timeout=timeout)
            self._session_map[session_id] = server_id
        return self._session_map[session_id]

    # ------------------------------------------------------------------
    # VictimAdapter ABC
    # ------------------------------------------------------------------

    async def reset_session(
        self,
        session_id: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        old_server_id = self._session_map.pop(session_id, None)
        if old_server_id:
            await self._delete_server_session(old_server_id, timeout=timeout)
        # Clear upload log entries for this session
        self._upload_log = [
            entry for entry in self._upload_log
            if entry.get("session_id") != session_id
        ]
        try:
            new_server_id = await self._create_server_session(timeout=timeout)
        except InfraError as exc:
            raise VictimResetError(str(exc)) from exc
        self._session_map[session_id] = new_server_id

    async def send_turn(
        self,
        session_id: str,
        message: str,
        *,
        mode: str = "chat",
        timeout: float = 120.0,
    ) -> dict:
        server_id = await self._resolve_session(session_id, timeout=timeout)
        started = time.monotonic()
        resp = await self._request(
            "POST",
            f"/sessions/{server_id}/chat",
            timeout=timeout,
            json={"message": message, "client_id": self.client_id},
        )
        # Session expired on the server — recreate and retry once
        if resp.status_code == 404:
            logger.debug("Session %s expired (404), recreating", server_id)
            new_server_id = await self._create_server_session(timeout=timeout)
            self._session_map[session_id] = new_server_id
            started = time.monotonic()
            resp = await self._request(
                "POST",
                f"/sessions/{new_server_id}/chat",
                timeout=timeout,
                json={"message": message, "client_id": self.client_id},
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code >= 400:
            raise InfraError(f"send_turn failed: {resp.status_code} {resp.text}")
        payload = resp.json() if resp.content else {}
        return {
            "response": str(payload.get("response", "")),
            "usage": payload.get("usage", {}),
            "duration_ms": duration_ms,
            "tool_calls": payload.get("tool_calls", []),
        }

    async def upload_file(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        timeout: float = 120.0,
    ) -> dict:
        # Ensure session exists before uploading
        await self._resolve_session(session_id, timeout=timeout)
        resp = await self._request(
            "POST",
            "/upload",
            timeout=timeout,
            files={"file": (filename, content, content_type)},
        )
        if resp.status_code >= 400:
            raise InfraError(f"upload_file failed: {resp.status_code} {resp.text}")
        result = resp.json() if resp.content else {}
        # Track upload locally so list_docs() can see it
        self._upload_log.append({
            "filename": filename,
            "session_id": session_id,
            "source": "upload_file",
        })
        return result

    async def list_docs(
        self,
        session_id: str,
        *,
        timeout: float = 30.0,
    ) -> list[dict]:
        resp = await self._request("GET", "/history/uploads", timeout=timeout)
        if resp.status_code >= 400:
            raise InfraError(f"list_docs failed: {resp.status_code} {resp.text}")
        payload = resp.json() if resp.content else {}
        # Response is {"total": N, "entries": [...]}
        if isinstance(payload, dict):
            entries = payload.get("entries", [])
        elif isinstance(payload, list):
            entries = payload
        else:
            entries = []

        # Merge locally-tracked uploads (dedupe by filename)
        seen_filenames = {
            e.get("filename") for e in entries
            if isinstance(e, dict) and e.get("filename")
        }
        for upload in self._upload_log:
            if upload["filename"] not in seen_filenames:
                entries.append({"filename": upload["filename"], "source": "upload_file"})
                seen_filenames.add(upload["filename"])
        return entries

    # ------------------------------------------------------------------
    # Extra methods (beyond VictimAdapter ABC)
    # ------------------------------------------------------------------

    async def health(self, *, timeout: float = 5.0) -> dict:
        resp = await self._request("GET", "/health", timeout=timeout)
        if resp.status_code >= 400:
            raise InfraError(f"health check failed: {resp.status_code}")
        return resp.json() if resp.content else {}

    async def list_sessions(self, *, timeout: float = 10.0) -> dict:
        resp = await self._request("GET", "/sessions", timeout=timeout)
        if resp.status_code >= 400:
            raise InfraError(f"list_sessions failed: {resp.status_code}")
        return resp.json() if resp.content else {}

    async def evaluate(
        self,
        session_id: str,
        resume_path: str,
        linkedin_url: str = "",
        website_url: str = "",
        position: str = "",
        *,
        timeout: float = 120.0,
    ) -> dict:
        server_id = await self._resolve_session(session_id, timeout=timeout)
        body: dict = {"resume_path": resume_path}
        if linkedin_url:
            body["linkedin_url"] = linkedin_url
        if website_url:
            body["website_url"] = website_url
        if position:
            body["position"] = position
        resp = await self._request(
            "POST",
            f"/sessions/{server_id}/evaluate",
            timeout=timeout,
            json=body,
        )
        if resp.status_code >= 400:
            raise InfraError(f"evaluate failed: {resp.status_code} {resp.text}")
        return resp.json() if resp.content else {}

    async def list_positions(self, client_id: str | None = None, *, timeout: float = 10.0) -> dict:
        cid = client_id or self.client_id
        resp = await self._request("GET", "/positions", timeout=timeout, params={"client_id": cid})
        if resp.status_code >= 400:
            raise InfraError(f"list_positions failed: {resp.status_code}")
        return resp.json() if resp.content else {}

    async def get_memories(self, *, limit: int = 20, timeout: float = 30.0) -> list[dict]:
        """Use /history/queries as a memory/state proxy.

        New query history entries appearing after a turn = structural evidence
        of state persistence, which feeds the Summarizer's memory_write check.
        """
        resp = await self._request("GET", "/history/queries", timeout=timeout)
        if resp.status_code >= 400:
            return []
        payload = resp.json() if resp.content else {}
        if isinstance(payload, dict):
            return payload.get("entries", payload.get("queries", []))[:limit]
        if isinstance(payload, list):
            return payload[:limit]
        return []

    async def get_debug_state(self, session_id: str, *, timeout: float = 30.0) -> dict:
        """Attempt GET /debug/{session_id} — returns {} if endpoint doesn't exist.

        Caches 404/405 results to avoid repeated failed requests.
        """
        if self._debug_unavailable:
            return {}
        server_id = self._session_map.get(session_id, session_id)
        try:
            resp = await self._request("GET", f"/debug/{server_id}", timeout=timeout)
        except InfraError:
            self._debug_unavailable = True
            return {}
        if resp.status_code in (404, 405):
            self._debug_unavailable = True
            return {}
        if resp.status_code >= 400:
            return {}
        payload = resp.json() if resp.content else {}
        return payload if isinstance(payload, dict) else {}

    async def get_query_history(self, *, timeout: float = 10.0) -> dict:
        resp = await self._request("GET", "/history/queries", timeout=timeout)
        if resp.status_code >= 400:
            raise InfraError(f"get_query_history failed: {resp.status_code}")
        return resp.json() if resp.content else {}
