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
    cred_a: Optional[str] = None
    cred_b: Optional[str] = None
    foreign_id: Optional[str] = None


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
    authz_cases = [c for c in cases if c.surface == "authz"]
    other_cases = [c for c in cases if c.surface not in ("auth", "authz")]

    for case in auth_cases:
        findings.append(await _run_auth_case(case, cfg))

    for case in authz_cases:
        findings.append(await _run_authz_case(case, cfg))

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


def _expand_authz_template(value: Any, cfg: ScanConfig, run_id: str) -> Any:
    """Expand {cred_a} / {cred_b} / {foreign_id} / {run_id} in string values."""
    if not isinstance(value, str):
        return value
    return (
        value.replace("{cred_a}", cfg.cred_a or "")
        .replace("{cred_b}", cfg.cred_b or "")
        .replace("{foreign_id}", cfg.foreign_id or "")
        .replace("{run_id}", run_id)
    )


async def _run_corroborated_marker_echo(
    client: MCPClient,
    case: TestCase,
    tool: ToolDescriptor,
    all_tools: list[ToolDescriptor],
    cfg: ScanConfig,
) -> Finding:
    """3-call corroboration for a marker_echo probe. Real_1 + real_2 + negative."""
    assert case.matcher is not None and case.matcher.kind == "marker_echo"
    assert case.corroborate is not None

    target = case.payload.tool or tool.name
    real_template = case.matcher.params.get("marker_template", "")
    neg_template = case.corroborate.negative_marker_template

    # Three independent run_ids → three independent markers.
    calls: list[dict[str, Any]] = []
    for label, args_src, marker_template in (
        ("real_1", case.payload.arguments, real_template),
        ("real_2", case.payload.arguments, real_template),
        ("negative", case.corroborate.negative_arguments, neg_template),
    ):
        run_id = _run_id()
        try:
            args = _resolve_arguments(args_src, tool, run_id)
        except _UnresolvedFirstStringArg as exc:
            return Finding(
                test_id=case.id,
                expected_signal=case.expected_signal,
                severity=case.severity,
                surface=case.surface,
                endpoint=cfg.endpoint,
                fired=False,
                outcome="skipped",
                tool_name=target,
                evidence=f"corroborate phase {label}: {exc}",
                owasp=list(case.owasp),
                atlas=list(case.atlas),
            )
        marker = marker_template.replace("{run_id}", run_id)
        call = await client.call_tool(target, args)
        result = run_matcher("marker_echo", {"marker": marker}, call.text, {})
        entry: dict[str, Any] = {
            "label": label,
            "args": args,
            "marker": marker,
            "fired": result.fired,
            "evidence": result.evidence,
            "response": call.text,
            "is_error": call.is_error,
        }
        # matcher_outcome distinguishes vulnerable/echo/pass for the REAL calls
        # (the matcher's shell-syntax check tells us if the response wraps the
        # marker in `$(echo …)`). For the NEGATIVE call the payload has no
        # shell syntax to begin with, so matcher_outcome is uninformative
        # there — we omit it and report a plain `reflected` boolean instead.
        if label == "negative":
            entry["reflected"] = result.fired
        else:
            entry["matcher_outcome"] = result.outcome
        calls.append(entry)

    real_1, real_2, neg = calls[0], calls[1], calls[2]

    # The per-call matcher already classifies vulnerable vs echo by checking
    # whether shell metacharacters appear in the response window around the
    # marker (see matchers._SHELL_ECHO_TELLS). We trust that per-call signal
    # for the real payloads and use the negative for additional context.
    r1, r2 = real_1["matcher_outcome"], real_2["matcher_outcome"]
    neg_reflects = neg["reflected"]  # if the negative marker appears, server reflects raw input

    if r1 == "vulnerable" and r2 == "vulnerable":
        outcome = "vulnerable"
        extra = " (server also reflects raw input)" if neg_reflects else ""
        evidence = (
            f"both real markers reflected without shell-syntax wrapper — expansion confirmed{extra}.\n"
            f"real_1 evidence: {real_1['evidence'][:160]}"
        )
    elif r1 == "echo" and r2 == "echo":
        outcome = "echo"
        evidence = (
            "both real markers reflected alongside the shell-syntax wrapper — "
            "server reflects input, no expansion proven.\n"
            f"real_1 evidence: {real_1['evidence'][:160]}"
        )
    elif r1 == "pass" and r2 == "pass":
        outcome = "pass"
        evidence = "neither real marker reflected"
    elif r1 != r2:
        # The two real calls disagreed — likely intermittent or stateful behavior.
        outcome = "suggestive"
        evidence = (
            f"intermittent: real_1={r1}, real_2={r2}. Rerun to disambiguate "
            "(network, caching, race)."
        )
    else:
        # Defensive: any other combination is unexpected.
        outcome = "suggestive"
        evidence = f"unusual corroboration state: real_1={r1}, real_2={r2}, negative_reflects={neg_reflects}"

    fired = outcome in ("vulnerable", "echo")
    return Finding(
        test_id=case.id,
        expected_signal=case.expected_signal,
        severity=case.severity,
        surface=case.surface,
        endpoint=cfg.endpoint,
        fired=fired,
        outcome=outcome,
        tool_name=target,
        evidence=evidence[:400],
        owasp=list(case.owasp),
        atlas=list(case.atlas),
        payload={
            "tool": target,
            "corroborated": True,
            "calls": [
                # Keep keys that exist (matcher_outcome only on real calls,
                # reflected only on negative).
                {k: c[k] for k in ("label", "args", "marker", "fired", "matcher_outcome", "reflected") if k in c}
                for c in calls
            ],
        },
    )


async def _run_authz_case(case: TestCase, cfg: ScanConfig) -> Finding:
    """Two-credential cross-tenant probe."""
    # Skip cleanly if the operator didn't supply the required identities.
    missing: list[str] = []
    if not cfg.cred_a:
        missing.append("--cred-a")
    if not cfg.cred_b:
        missing.append("--cred-b")
    if not cfg.foreign_id:
        missing.append("--foreign-id")
    if missing:
        return Finding(
            test_id=case.id,
            expected_signal=case.expected_signal,
            severity=case.severity,
            surface=case.surface,
            endpoint=cfg.endpoint,
            fired=False,
            outcome="skipped",
            evidence=f"authz probe requires {' / '.join(missing)}",
            owasp=list(case.owasp),
            atlas=list(case.atlas),
        )

    run_id = _run_id()
    phase_a = case.phase_a
    phase_b = case.phase_b
    assert phase_a is not None and phase_b is not None  # validated at load time
    a_args = {k: _expand_authz_template(v, cfg, run_id) for k, v in phase_a.arguments.items()}
    b_args = {k: _expand_authz_template(v, cfg, run_id) for k, v in phase_b.arguments.items()}

    async with MCPClient(
        cfg.endpoint,
        timeout_s=cfg.timeout_s,
        bearer=cfg.bearer,
        headers=cfg.headers,
    ) as client:
        call_a = await client.call_tool(phase_a.tool, a_args)
        # Sanity check: A should be able to read its own object. If not, the
        # foreign_id is wrong or A's credential is invalid — emit error rather
        # than misclassify a probe-config bug as "not vulnerable".
        if call_a.is_error:
            return Finding(
                test_id=case.id,
                expected_signal=case.expected_signal,
                severity=case.severity,
                surface=case.surface,
                endpoint=cfg.endpoint,
                fired=False,
                outcome="error",
                tool_name=phase_a.tool,
                evidence=f"phase_a (identity A) failed — check --cred-a and --foreign-id: {call_a.text[:200]}",
                owasp=list(case.owasp),
                atlas=list(case.atlas),
                payload={"phase_a": {"tool": phase_a.tool, "arguments": a_args}},
            )

        call_b = await client.call_tool(phase_b.tool, b_args)

    # Run the matcher against B's response. The matcher's params may reference
    # ``{run_id}`` and template tokens; expand those.
    assert case.matcher is not None
    params = {k: _expand_authz_template(v, cfg, run_id) for k, v in case.matcher.params.items()}
    result = run_matcher(case.matcher.kind, params, call_b.text, {})

    return Finding(
        test_id=case.id,
        expected_signal=case.expected_signal,
        severity=case.severity,
        surface=case.surface,
        endpoint=cfg.endpoint,
        fired=result.fired,
        outcome=result.outcome,
        tool_name=phase_b.tool,
        evidence=(result.evidence or f"phase_b response: {call_b.text[:200]}"),
        owasp=list(case.owasp),
        atlas=list(case.atlas),
        payload={
            "phase_a": {"tool": phase_a.tool, "arguments": a_args},
            "phase_b": {"tool": phase_b.tool, "arguments": b_args},
        },
    )


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
        # Corroborated marker_echo: run 3 calls and aggregate.
        if (
            case.corroborate is not None
            and case.matcher is not None
            and case.matcher.kind == "marker_echo"
        ):
            findings.append(await _run_corroborated_marker_echo(client, case, tool, tools, cfg))
            continue

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
