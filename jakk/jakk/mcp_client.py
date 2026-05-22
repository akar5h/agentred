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
    """

    def __init__(self, endpoint: str, timeout_s: float = 15.0) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self._client = None
        self._ctx = None

    async def __aenter__(self) -> "MCPClient":
        from fastmcp import Client  # local import: heavy dep
        self._client = Client(self.endpoint, timeout=self.timeout_s)
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
