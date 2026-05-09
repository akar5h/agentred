from __future__ import annotations

import json
import time
from typing import Optional

import httpx

from grafted.core.exceptions import InfraError, VictimResetError
from grafted.victim.base import VictimAdapter


def _parse_sse_done_body(body: str) -> dict:
    current_event = "message"
    data_lines: list[str] = []
    done_payload: dict = {}

    def flush() -> None:
        nonlocal current_event, data_lines, done_payload
        if not data_lines:
            return
        raw = "".join(data_lines)
        data_lines.clear()
        if current_event != "done":
            current_event = "message"
            return
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                done_payload = payload.get("result", payload)
        except json.JSONDecodeError:
            done_payload = {"response": "", "usage": {}}
        current_event = "message"

    for line in body.splitlines():
        if line == "":
            flush()
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())

    flush()
    return done_payload


class RestApiAdapter(VictimAdapter):
    def __init__(
        self,
        base_url: str,
        mode: str = "chat",
        *,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.mode = mode
        self._client = client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        **kwargs,
    ) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.request(method, path, timeout=timeout, **kwargs)
            async with httpx.AsyncClient(base_url=self.base_url) as client:
                return await client.request(method, path, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise InfraError(f"{type(exc).__name__}: {exc!r}") from exc

    async def send_turn(
        self,
        session_id: str,
        message: str,
        *,
        mode: Optional[str] = None,
        timeout: float = 120.0,
    ) -> dict:
        chosen_mode = mode or self.mode
        started = time.monotonic()
        endpoint = "/chat" if chosen_mode == "chat" else "/chat/stream"
        resp = await self._request(
            "POST",
            endpoint,
            timeout=timeout,
            json={"session_id": session_id, "message": message},
        )
        if resp.status_code >= 400:
            raise InfraError(f"send_turn failed with status {resp.status_code}: {resp.text}")

        if chosen_mode == "stream":
            parsed = _parse_sse_done_body(resp.text)
            response_text = str(parsed.get("response", ""))
            usage = parsed.get("usage", {})
            system_prompts = parsed.get("system_prompts", {})
        else:
            payload = resp.json() if resp.content else {}
            response_text = str(payload.get("response", ""))
            usage = payload.get("usage", {})
            system_prompts = payload.get("system_prompts", {})

        return {
            "response": response_text,
            "usage": usage if isinstance(usage, dict) else {},
            "duration_ms": int((time.monotonic() - started) * 1000),
            "system_prompts": system_prompts if isinstance(system_prompts, dict) else {},
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
        resp = await self._request(
            "POST",
            "/upload",
            timeout=timeout,
            data={"session_id": session_id},
            files={"file": (filename, content, content_type)},
        )
        if resp.status_code >= 400:
            raise InfraError(f"upload_file failed with status {resp.status_code}: {resp.text}")
        return resp.json() if resp.content else {}

    async def list_docs(
        self,
        session_id: str,
        *,
        timeout: float = 30.0,
    ) -> list[dict]:
        resp = await self._request(
            "GET",
            "/docs",
            timeout=timeout,
            params={"session_id": session_id},
        )
        if resp.status_code >= 400:
            raise InfraError(f"list_docs failed with status {resp.status_code}: {resp.text}")
        payload = resp.json() if resp.content else []
        return payload if isinstance(payload, list) else []

    async def get_doc_detail(self, session_id: str, doc_id: int, *, timeout: float = 30.0) -> dict:
        resp = await self._request(
            "GET",
            f"/docs/{doc_id}",
            timeout=timeout,
            params={"session_id": session_id},
        )
        if resp.status_code >= 400:
            raise InfraError(f"get_doc_detail failed with status {resp.status_code}: {resp.text}")
        payload = resp.json() if resp.content else {}
        return payload if isinstance(payload, dict) else {}

    async def reset_session(
        self,
        session_id: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        try:
            resp = await self._request(
                "POST",
                "/reset",
                timeout=timeout,
                json={"session_id": session_id},
            )
        except InfraError as exc:
            raise VictimResetError(str(exc)) from exc
        if resp.status_code >= 400:
            raise VictimResetError(f"reset_session failed with status {resp.status_code}: {resp.text}")
