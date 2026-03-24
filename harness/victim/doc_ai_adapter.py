"""VictimAdapter for the Document AI (deepagent) target.

API surface:
  POST /upload          — upload file (multipart, returns doc_id + conversation_id)
  POST /chat            — chat with session_id (returns response + trace + history)
  POST /chat/stream     — SSE variant (status, message, guard_stop, done events)
  GET  /docs            — list documents (optional ?session_id=)
  GET  /docs/{doc_id}   — document detail with full content
  GET  /tool-calls      — tool call audit log (?session_id=, ?tool_name=, ?limit=)
  GET  /debug/{session}  — agent state + memory + documents
  GET  /memories         — memory inspection (?user_id=)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from harness.core.exceptions import InfraError
from harness.victim.base import VictimAdapter

logger = logging.getLogger("harness.victim.doc_ai")


class DocAiAdapter(VictimAdapter):
    """Adapter for the Document AI / RAG target.

    Unlike HrApiAdapter, this target uses caller-provided session_ids directly
    (no server-side session creation needed). The upload endpoint accepts an
    optional ``session_id`` form field to attach documents to a conversation.
    """

    def __init__(
        self,
        base_url: str,
        tenant_id: str = "default",
        user_id: str = "default",
        *,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._client = client
        self._upload_log: list[dict] = []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 300.0,
        **kwargs: Any,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("x-tenant-id", self.tenant_id)
        headers.setdefault("x-user-id", self.user_id)
        kwargs["headers"] = headers

        if self._client:
            return await self._client.request(method, url, timeout=timeout, **kwargs)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, url, **kwargs)

    # ------------------------------------------------------------------
    # VictimAdapter interface
    # ------------------------------------------------------------------

    async def send_turn(
        self,
        session_id: str,
        message: str,
        *,
        mode: str = "chat",
        timeout: float = 300.0,
    ) -> dict:
        started = time.monotonic()
        try:
            resp = await self._request(
                "POST",
                "/chat",
                timeout=timeout,
                json={"message": message, "session_id": session_id},
            )
        except Exception as exc:
            raise InfraError(f"send_turn failed: {exc}") from exc

        duration_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code >= 400:
            raise InfraError(f"send_turn failed: {resp.status_code} {resp.text}")

        payload = resp.json() if resp.content else {}
        return {
            "response": str(payload.get("response", "")),
            "history": payload.get("history", []),
            "trace": payload.get("trace", []),
            "usage": payload.get("usage", {}),
            "duration_ms": duration_ms,
            "tool_calls": payload.get("trace", []),
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
        try:
            resp = await self._request(
                "POST",
                "/upload",
                timeout=timeout,
                files={"file": (filename, content, content_type)},
                data={"session_id": session_id},
            )
        except Exception as exc:
            raise InfraError(f"upload_file failed: {exc}") from exc

        if resp.status_code >= 400:
            raise InfraError(f"upload_file failed: {resp.status_code} {resp.text}")

        result = resp.json() if resp.content else {}
        self._upload_log.append({
            "filename": filename,
            "session_id": session_id,
            "doc_id": result.get("doc_id"),
            "conversation_id": result.get("conversation_id"),
        })
        return result

    async def list_docs(
        self,
        session_id: str,
        *,
        timeout: float = 30.0,
    ) -> list[dict]:
        try:
            resp = await self._request(
                "GET",
                f"/docs?session_id={session_id}",
                timeout=timeout,
            )
        except Exception as exc:
            logger.debug("list_docs failed: %s", exc)
            return []

        if resp.status_code >= 400:
            logger.debug("list_docs returned %s", resp.status_code)
            return []

        payload = resp.json() if resp.content else []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return payload.get("documents", payload.get("entries", []))
        return []

    async def reset_session(self, session_id: str, *, timeout: float = 10.0) -> None:
        # Doc AI has no explicit session reset — we just use a fresh session_id.
        # Clear local state for the old session.
        self._upload_log = [u for u in self._upload_log if u.get("session_id") != session_id]

    # ------------------------------------------------------------------
    # Extended methods (used by Explorer / Oracle for richer telemetry)
    # ------------------------------------------------------------------

    async def get_doc_detail(self, session_id: str, doc_id: int) -> dict:
        try:
            resp = await self._request("GET", f"/docs/{doc_id}", timeout=30.0)
            if resp.status_code >= 400:
                return {}
            return resp.json() if resp.content else {}
        except Exception as exc:
            logger.debug("get_doc_detail failed: %s", exc)
            return {}

    async def get_tool_calls(self, session_id: str) -> list[dict]:
        try:
            resp = await self._request(
                "GET",
                f"/tool-calls?session_id={session_id}&limit=50",
                timeout=30.0,
            )
            if resp.status_code >= 400:
                return []
            payload = resp.json() if resp.content else []
            return payload if isinstance(payload, list) else []
        except Exception as exc:
            logger.debug("get_tool_calls failed: %s", exc)
            return []

    async def get_memories(self, user_id: str | None = None) -> list[dict]:
        uid = user_id or self.user_id
        try:
            resp = await self._request(
                "GET",
                f"/memories?user_id={uid}",
                timeout=30.0,
            )
            if resp.status_code >= 400:
                return []
            payload = resp.json() if resp.content else []
            return payload if isinstance(payload, list) else []
        except Exception as exc:
            logger.debug("get_memories failed: %s", exc)
            return []

    async def get_debug_state(self, session_id: str) -> dict:
        try:
            resp = await self._request(
                "GET",
                f"/debug/{session_id}",
                timeout=30.0,
            )
            if resp.status_code >= 400:
                return {}
            return resp.json() if resp.content else {}
        except Exception as exc:
            logger.debug("get_debug_state failed: %s", exc)
            return {}

    async def health(self) -> dict:
        try:
            resp = await self._request("GET", "/", timeout=10.0)
            return resp.json() if resp.content else {}
        except Exception:
            return {"ok": False}
