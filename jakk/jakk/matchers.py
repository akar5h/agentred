"""Matchers — decide whether a probe response indicates the test fired.

Each matcher consumes:
- the probe payload that was sent (so it can resolve ``{run_id}``/marker expansions),
- the response text (a single flattened string of the tool result), and
- an optional context dict (e.g. tool schema for schema_field).

Each returns a :class:`MatcherResult` with ``fired: bool`` and a short
``evidence`` snippet that lands in the finding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional


Outcome = str  # "vulnerable" | "echo" | "pass" | "skipped" | "error"


@dataclass
class MatcherResult:
    fired: bool
    evidence: str = ""
    outcome: Outcome = "pass"
    """Refined verdict beyond fired/not-fired:
       - ``vulnerable``: probe produced evidence that exceeds simple input reflection
         (file contents, expanded shell substitution, schema directives, ...).
       - ``echo``: marker appears in response but the surrounding payload syntax was
         reflected unchanged — server echoed input but did not interpret it.
       - ``pass``: no signal.
       - ``skipped``: not applicable to this server.
       - ``error``: probe could not be evaluated (transport error, etc.).
    """


MatcherFn = Callable[[dict[str, Any], str, dict[str, Any]], MatcherResult]


_REGISTRY: dict[str, MatcherFn] = {}


def register(kind: str) -> Callable[[MatcherFn], MatcherFn]:
    def deco(fn: MatcherFn) -> MatcherFn:
        _REGISTRY[kind] = fn
        return fn
    return deco


def get_matcher(kind: str) -> MatcherFn:
    if kind not in _REGISTRY:
        raise KeyError(f"no matcher registered for kind={kind!r}")
    return _REGISTRY[kind]


def _snippet(text: str, needle: str, radius: int = 60) -> str:
    idx = text.find(needle)
    if idx < 0:
        return text[: 2 * radius]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    return text[start:end]


# ---------------------------------------------------------------------------
# Built-in matchers
# ---------------------------------------------------------------------------


@register("substring")
def _substring(params: dict[str, Any], response: str, ctx: dict[str, Any]) -> MatcherResult:
    needle = params.get("needle", "")
    if not needle:
        return MatcherResult(False, "substring matcher: empty needle", "error")
    fired = needle in response
    return MatcherResult(
        fired,
        _snippet(response, needle) if fired else "",
        "vulnerable" if fired else "pass",
    )


@register("regex")
def _regex(params: dict[str, Any], response: str, ctx: dict[str, Any]) -> MatcherResult:
    pattern = params.get("pattern", "")
    if not pattern:
        return MatcherResult(False, "regex matcher: empty pattern", "error")
    flags = re.IGNORECASE if params.get("ignore_case", False) else 0
    m = re.search(pattern, response, flags)
    if not m:
        return MatcherResult(False, "", "pass")
    return MatcherResult(True, _snippet(response, m.group(0)), "vulnerable")


# Shell metacharacter literals that, if echoed back alongside the marker,
# indicate the server reflected the raw payload rather than interpreting it.
_SHELL_ECHO_TELLS: tuple[str, ...] = ("$(", "${", "`echo", "; cat", "&& cat", "| cat")


@register("marker_echo")
def _marker_echo(params: dict[str, Any], response: str, ctx: dict[str, Any]) -> MatcherResult:
    """Decide if a unique per-run marker appears in the response, and classify the outcome.

    Outcome rules:

    - ``pass``     — marker absent.
    - ``echo``     — marker present AND payload-shaped shell metacharacters (e.g.
      ``$(echo ...)``) also present near the marker. The server reflected the raw
      input but did not interpret it. NOT a command-injection finding by itself;
      may indicate a separate output-reflection issue.
    - ``vulnerable`` — marker present without the surrounding payload syntax.
      Implies shell expansion happened: the substituted command ran and its
      output was used by the host command.
    """
    marker: str = params.get("marker", "")
    if not marker:
        return MatcherResult(False, "marker_echo: no marker resolved", "error")
    if marker not in response:
        return MatcherResult(False, "", "pass")

    # Look at a window around the marker for echo-tells.
    window = _snippet(response, marker, radius=80)
    tell_hit = next((t for t in _SHELL_ECHO_TELLS if t in window), None)
    if tell_hit is not None:
        return MatcherResult(True, f"[echo-only] {window}", "echo")
    return MatcherResult(True, _snippet(response, marker), "vulnerable")


_DEFAULT_SECRET_PATTERNS: tuple[str, ...] = (
    # File contents that should never appear in a normal tool response.
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"root:x:0:0:",                          # /etc/passwd first line
    r"\bFLAG\{[^}]+\}",                       # CTF flag style (ch08 canary)
    # Token-shaped strings near a key=value assignment.
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
    r"AKIA[0-9A-Z]{16}",                      # AWS access-key id
    r"ghp_[A-Za-z0-9]{30,}",                  # GitHub PAT
    r"sk-[A-Za-z0-9]{20,}",                   # OpenAI-style key
)


@register("secret_pattern")
def _secret_pattern(params: dict[str, Any], response: str, ctx: dict[str, Any]) -> MatcherResult:
    extra = tuple(params.get("patterns", ()))
    for pat in (*_DEFAULT_SECRET_PATTERNS, *extra):
        m = re.search(pat, response)
        if m:
            return MatcherResult(True, _snippet(response, m.group(0)), "vulnerable")
    return MatcherResult(False, "", "pass")


_DIRECTIVE_PATTERNS: tuple[str, ...] = (
    r"(?im)^\s*system\s*[:>]",
    r"(?im)ignore (all )?previous (instructions|messages|prompts)",
    r"(?im)disregard (the )?(above|prior|previous)",
    r"(?im)^\s*<\s*system\s*>",
    r"(?im)you are now (a|an|the) ",
    r"(?im)forget (everything|all) (you|previous)",
    r"(?im)new instructions?\s*[:>]",
)


@register("directive_passthrough")
def _directive_passthrough(
    params: dict[str, Any], response: str, ctx: dict[str, Any]
) -> MatcherResult:
    extra = tuple(params.get("patterns", ()))
    for pat in (*_DIRECTIVE_PATTERNS, *extra):
        m = re.search(pat, response)
        if m:
            return MatcherResult(True, _snippet(response, m.group(0)), "vulnerable")
    return MatcherResult(False, "", "pass")


@register("schema_field")
def _schema_field(params: dict[str, Any], response: str, ctx: dict[str, Any]) -> MatcherResult:
    """Inspect tool schemas/descriptions (passed via ctx['tools']) for hidden content.

    Looks for directive-style language in tool descriptions or in JSON-schema
    ``description`` fields — the canonical 'tool poisoning via description'
    pattern from the Invariant Labs writeup.
    """
    tools = ctx.get("tools") or []
    patterns: list[str] = list(params.get("patterns", []))
    if not patterns:
        patterns = list(_DIRECTIVE_PATTERNS)
    for tool in tools:
        haystack_parts: list[str] = []
        for key in ("description", "instructions"):
            val = tool.get(key)
            if isinstance(val, str):
                haystack_parts.append(val)
        schema = tool.get("inputSchema") or tool.get("input_schema") or {}
        # Walk schema for description fields.
        for _key, val in _walk_strings(schema):
            haystack_parts.append(val)
        haystack = "\n".join(haystack_parts)
        for pat in patterns:
            m = re.search(pat, haystack)
            if m:
                name = tool.get("name", "<anonymous>")
                return MatcherResult(
                    True,
                    f"tool={name} :: {_snippet(haystack, m.group(0))}",
                    "vulnerable",
                )
    return MatcherResult(False, "", "pass")


def _walk_strings(obj: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                out.append((k, v))
            else:
                out.extend(_walk_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_walk_strings(item))
    return out


def run_matcher(
    kind: str,
    params: dict[str, Any],
    response: str,
    ctx: Optional[dict[str, Any]] = None,
) -> MatcherResult:
    return get_matcher(kind)(params or {}, response or "", ctx or {})
