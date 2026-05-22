"""Scan orchestration."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Optional

from .applies import select_tools
from .findings import Finding
from .library import TestCase
from .matchers import run_matcher
from .mcp_client import MCPClient, ToolDescriptor


@dataclass
class ScanConfig:
    endpoint: str
    timeout_s: float = 15.0


def _run_id() -> str:
    return secrets.token_hex(4)


class _UnresolvedFirstStringArg(Exception):
    """Raised when a payload uses ``__first_string_arg__`` but the matched tool exposes no string-typed arg."""


def _resolve_arguments(
    arguments: dict[str, Any],
    tool: Optional[ToolDescriptor],
    run_id: str,
) -> dict[str, Any]:
    """Expand template strings and the ``__first_string_arg__`` key.

    Raises :class:`_UnresolvedFirstStringArg` if the payload requested
    substitution into the first string arg but the tool has none — the
    scanner converts this into an explicit ``skipped`` finding rather
    than silently sending the tool an empty argument map.
    """
    resolved: dict[str, Any] = {}
    first_arg = tool.first_string_arg() if tool else None
    for key, value in arguments.items():
        if key == "__first_string_arg__":
            if first_arg is None:
                raise _UnresolvedFirstStringArg(
                    f"tool {tool.name if tool else '<none>'} has no string-typed argument"
                )
            key = first_arg
        if isinstance(value, str):
            value = value.replace("{run_id}", run_id)
        resolved[key] = value
    return resolved


def _resolve_matcher_params(params: dict[str, Any], run_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, str):
            v = v.replace("{run_id}", run_id)
        out[k] = v
    # Convenience: if a marker_template is provided, expose it as ``marker`` resolved.
    if "marker_template" in out and "marker" not in out:
        out["marker"] = str(out["marker_template"]).replace("{run_id}", run_id)
    return out


async def run_scan(cases: list[TestCase], cfg: ScanConfig) -> list[Finding]:
    findings: list[Finding] = []
    async with MCPClient(cfg.endpoint, timeout_s=cfg.timeout_s) as client:
        tools = await client.list_tools()
        tools_ctx = [t.to_dict() for t in tools]
        for case in cases:
            findings.extend(await _run_case(client, case, tools, tools_ctx, cfg))
    return findings


async def _run_case(
    client: MCPClient,
    case: TestCase,
    tools: list[ToolDescriptor],
    tools_ctx: list[dict[str, Any]],
    cfg: ScanConfig,
) -> list[Finding]:
    if case.surface in ("tool_list", "resource_list", "prompt_list") or case.applies_to.none:
        # Schema-only / listing-only tests: no tool call.
        run_id = _run_id()
        params = _resolve_matcher_params(case.matcher.params, run_id)
        result = run_matcher(case.matcher.kind, params, "", {"tools": tools_ctx})
        return [
            Finding(
                test_id=case.id,
                expected_signal=case.expected_signal,
                severity=case.severity,
                surface=case.surface,
                endpoint=cfg.endpoint,
                fired=result.fired,
                outcome=result.outcome,
                tool_name=None,
                evidence=result.evidence,
                owasp=list(case.owasp),
                atlas=list(case.atlas),
                payload={"matcher": case.matcher.kind, "params": params},
            )
        ]

    matched_tools = select_tools(case, tools)
    if not matched_tools:
        return [
            Finding(
                test_id=case.id,
                expected_signal=case.expected_signal,
                severity=case.severity,
                surface=case.surface,
                endpoint=cfg.endpoint,
                fired=False,
                outcome="skipped",
                tool_name=None,
                evidence="no compatible tool exposed by server",
                owasp=list(case.owasp),
                atlas=list(case.atlas),
            )
        ]

    findings: list[Finding] = []
    for tool in matched_tools:
        run_id = _run_id()
        target = case.payload.tool or tool.name
        try:
            arguments = _resolve_arguments(case.payload.arguments, tool, run_id)
        except _UnresolvedFirstStringArg as exc:
            findings.append(
                Finding(
                    test_id=case.id,
                    expected_signal=case.expected_signal,
                    severity=case.severity,
                    surface=case.surface,
                    endpoint=cfg.endpoint,
                    fired=False,
                    outcome="skipped",
                    tool_name=target,
                    evidence=f"payload requires __first_string_arg__ but {exc}",
                    owasp=list(case.owasp),
                    atlas=list(case.atlas),
                )
            )
            continue
        params = _resolve_matcher_params(case.matcher.params, run_id)
        call = await client.call_tool(target, arguments)
        result = run_matcher(
            case.matcher.kind,
            params,
            call.text,
            {"tools": [t.to_dict() for t in tools]},
        )
        outcome = result.outcome
        if call.is_error and not result.fired:
            outcome = "error"
        findings.append(
            Finding(
                test_id=case.id,
                expected_signal=case.expected_signal,
                severity=case.severity,
                surface=case.surface,
                endpoint=cfg.endpoint,
                fired=result.fired,
                outcome=outcome,
                tool_name=target,
                evidence=result.evidence,
                owasp=list(case.owasp),
                atlas=list(case.atlas),
                payload={"tool": target, "arguments": arguments},
                error=("call returned isError=True" if call.is_error and not result.fired else None),
            )
        )
    return findings
