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
    bearer: Optional[str] = None
    headers: Optional[dict[str, str]] = None


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

    # Auth probes don't use the shared client (they need overridden credentials);
    # run them first against fresh per-probe connections.
    auth_cases = [c for c in cases if c.surface == "auth"]
    other_cases = [c for c in cases if c.surface != "auth"]

    for case in auth_cases:
        findings.append(await _run_auth_case(case, cfg))

    if other_cases:
        async with MCPClient(
            cfg.endpoint,
            timeout_s=cfg.timeout_s,
            bearer=cfg.bearer,
            headers=cfg.headers,
        ) as client:
            tools = await client.list_tools()
            tools_ctx = [t.to_dict() for t in tools]
            for case in other_cases:
                findings.extend(await _run_case(client, case, tools, tools_ctx, cfg))
    return findings


async def _run_auth_case(case: TestCase, cfg: ScanConfig) -> Finding:
    """Run a single auth-misconfig probe with overridden credentials."""
    override = case.auth_override
    if override is None:
        return Finding(
            test_id=case.id,
            expected_signal=case.expected_signal,
            severity=case.severity,
            surface=case.surface,
            endpoint=cfg.endpoint,
            fired=False,
            outcome="error",
            evidence="surface=auth requires auth_override field; none provided",
            owasp=list(case.owasp),
            atlas=list(case.atlas),
        )

    # wrong_prefix requires a bearer to mutate; skip cleanly when absent.
    if override.mode == "wrong_prefix" and not cfg.bearer:
        return Finding(
            test_id=case.id,
            expected_signal=case.expected_signal,
            severity=case.severity,
            surface=case.surface,
            endpoint=cfg.endpoint,
            fired=False,
            outcome="skipped",
            evidence="auth_override=wrong_prefix requires --bearer to mutate; none provided",
            owasp=list(case.owasp),
            atlas=list(case.atlas),
        )

    try:
        async with MCPClient(
            cfg.endpoint,
            timeout_s=cfg.timeout_s,
            bearer=cfg.bearer,
            headers=cfg.headers,
            auth_override=override.mode,
        ) as client:
            tools = await client.list_tools()
            # Handshake + list_tools succeeded with intentionally-bad auth.
            outcome = override.expect_success
            evidence = (
                f"server accepted auth_override={override.mode}; "
                f"list_tools returned {len(tools)} tool(s)"
            )
            fired = (outcome == "vulnerable")
    except Exception as exc:
        outcome = "pass"
        evidence = f"server rejected auth_override={override.mode}: {type(exc).__name__}: {exc}"
        fired = False

    return Finding(
        test_id=case.id,
        expected_signal=case.expected_signal,
        severity=case.severity,
        surface=case.surface,
        endpoint=cfg.endpoint,
        fired=fired,
        outcome=outcome,
        evidence=evidence[:300],
        owasp=list(case.owasp),
        atlas=list(case.atlas),
        payload={"auth_override": override.mode},
    )


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
