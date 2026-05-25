"""Thin async wrapper over fastmcp.Client.

The scanner only needs three operations: initialize, list_tools, and
call_tool. This module isolates the fastmcp dependency so the rest of jakk
stays import-clean even when fastmcp is not installed (e.g. during unit
tests that exercise only library + matchers).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolDescriptor:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def first_string_arg(self) -> Optional[str]:
        """Return the name of the first string-typed argument in the input schema, if any."""
        props = (self.input_schema or {}).get("properties") or {}
        for key, spec in props.items():
            spec_type = spec.get("type") if isinstance(spec, dict) else None
            if spec_type == "string":
                return key
            if isinstance(spec_type, list) and "string" in spec_type:
                return key
        return None

    def string_arg_count(self) -> int:
        props = (self.input_schema or {}).get("properties") or {}
        count = 0
        for spec in props.values():
            if not isinstance(spec, dict):
                continue
            t = spec.get("type")
            if t == "string" or (isinstance(t, list) and "string" in t):
                count += 1
        return count

    def required_args(self) -> list[str]:
        """Names the tool's inputSchema marks as required (empty if none)."""
        req = (self.input_schema or {}).get("required") or []
        return [r for r in req if isinstance(r, str)]

    def has_arg(self, name: str) -> bool:
        """True if the tool declares an argument with this name."""
        props = (self.input_schema or {}).get("properties") or {}
        return name in props

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class CallResult:
    text: str
    is_error: bool = False
    raw: Any = None


class MCPClient:
    """Async context-manager wrapper around fastmcp.Client.

    Usage::

        async with MCPClient(endpoint) as c:
            tools = await c.list_tools()
            result = await c.call_tool(name, {"x": 1})

    Auth + headers:

        async with MCPClient(endpoint, bearer="abc123") as c: ...
        async with MCPClient(endpoint, headers={"X-Api-Key": "..."}) as c: ...

    The bearer shortcut is equivalent to ``auth="abc123"`` which fastmcp
    translates into ``Authorization: Bearer abc123``. Custom headers go
    through the streamable-HTTP transport directly.
    """

    def __init__(
        self,
        endpoint: str,
        timeout_s: float = 15.0,
        bearer: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        auth_override: Optional[str] = None,
    ) -> None:
        """
        :param bearer: bearer token; sent as ``Authorization: Bearer <token>``.
        :param headers: additional headers merged into every request.
        :param auth_override: special-case for auth-misconfig probes. Accepted
            values:
              - ``"none"``      — strip all auth (bearer + Authorization header)
              - ``"garbage"``   — send ``Authorization: Bearer garbage-<rand>``
              - ``"wrong_prefix"`` — send the bearer token without the ``Bearer ``
                prefix (i.e. raw token in the Authorization header).
            When set, takes precedence over ``bearer`` and any Authorization
            entry in ``headers``.
        """
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.bearer = bearer
        self.headers = dict(headers or {})
        self.auth_override = auth_override
        self._client = None
        self._ctx = None

    def _resolve_transport_kwargs(self) -> dict[str, Any]:
        """Compute (headers, auth) for the underlying transport, honouring auth_override."""
        headers = dict(self.headers)
        auth: Optional[str] = self.bearer

        if self.auth_override is None:
            return {"headers": headers or None, "auth": auth}

        # Strip any existing auth state before applying the override.
        headers.pop("Authorization", None)
        headers.pop("authorization", None)
        if self.auth_override == "none":
            return {"headers": headers or None, "auth": None}
        if self.auth_override == "garbage":
            import secrets as _secrets
            headers["Authorization"] = f"Bearer garbage-{_secrets.token_hex(8)}"
            return {"headers": headers, "auth": None}
        if self.auth_override == "wrong_prefix":
            if not self.bearer:
                raise ValueError(
                    "auth_override='wrong_prefix' requires a bearer token to mutate"
                )
            headers["Authorization"] = self.bearer  # raw token, no 'Bearer ' prefix
            return {"headers": headers, "auth": None}
        raise ValueError(f"unknown auth_override: {self.auth_override!r}")

    async def __aenter__(self) -> "MCPClient":
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport

        kw = self._resolve_transport_kwargs()
        transport = StreamableHttpTransport(self.endpoint, headers=kw["headers"], auth=kw["auth"])
        self._client = Client(transport, timeout=self.timeout_s)
        self._ctx = await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, tb)
        self._client = None
        self._ctx = None

    async def list_tools(self) -> list[ToolDescriptor]:
        assert self._client is not None, "MCPClient not entered"
        tools_raw = await self._client.list_tools()
        out: list[ToolDescriptor] = []
        for t in tools_raw:
            # fastmcp returns Tool objects with .name / .description / .inputSchema.
            name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else "")
            description = getattr(t, "description", "") or (
                t.get("description", "") if isinstance(t, dict) else ""
            )
            schema = getattr(t, "inputSchema", None)
            if schema is None and isinstance(t, dict):
                schema = t.get("inputSchema") or t.get("input_schema") or {}
            out.append(ToolDescriptor(name=name, description=description or "", input_schema=schema or {}))
        return out

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallResult:
        assert self._client is not None, "MCPClient not entered"
        try:
            result = await self._client.call_tool(name, arguments)
        except Exception as exc:
            return CallResult(text=f"<call_tool error: {type(exc).__name__}: {exc}>", is_error=True, raw=exc)
        return CallResult(text=_flatten_content(result), is_error=_is_error(result), raw=result)


def _flatten_content(result: Any) -> str:
    """Flatten a CallToolResult into a single string for matcher consumption."""
    if result is None:
        return ""
    # fastmcp result types: .content (list of content blocks) or .data (structured output).
    parts: list[str] = []
    content = getattr(result, "content", None)
    if content:
        for block in content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
                continue
            data = getattr(block, "data", None)
            if data is not None:
                parts.append(str(data))
    data = getattr(result, "data", None)
    if data is not None:
        parts.append(str(data))
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if structured is not None:
        parts.append(str(structured))
    if not parts:
        parts.append(str(result))
    return "\n".join(parts)


def _is_error(result: Any) -> bool:
    val = getattr(result, "isError", None)
    if val is None:
        val = getattr(result, "is_error", None)
    return bool(val)
