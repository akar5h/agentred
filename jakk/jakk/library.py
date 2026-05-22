"""Attack-library loader.

A jakk library is a directory of YAML files, one per test. Each file
parses into a :class:`TestCase`. Loaders are deliberately strict — a
malformed file fails fast with the file path in the error.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class AppliesTo(BaseModel):
    """Selector that decides which tools on a server the test fires against."""

    tool_name: Optional[str] = None
    """Exact tool name. Mutually compatible with tool_name_regex (both must match)."""

    tool_name_regex: Optional[str] = None
    """Python regex matched against tool name (re.search). Compiled at load time."""

    min_string_args: int = 0
    """Only fire if the tool's input schema has at least N string-typed args."""

    require_no_required_args: bool = False
    """If True, only match tools whose ``inputSchema.required`` is empty/absent.

    Useful for probes that intentionally call with empty arguments (the
    ``response.*`` family). Without this filter, those probes match
    args-required tools by name and then fail with ``isError=True``,
    producing noisy ``error`` outcomes that aren't a vulnerability signal.
    """

    none: bool = False
    """If True, do not call any tool — test inspects schema/listing only."""

    @field_validator("tool_name_regex")
    @classmethod
    def _validate_regex(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"invalid tool_name_regex {v!r}: {exc}") from exc
        return v


class Payload(BaseModel):
    """What to send to the tool. Templates like ``{run_id}`` are expanded at scan time."""

    tool: Optional[str] = None
    """Explicit tool name. If absent, scanner uses the matched tool from applies_to."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    """Argument map. String values may use ``{run_id}`` and ``{first_string_arg}`` markers.

    Special key ``__first_string_arg__`` means: assign the value to whatever
    the first string-typed parameter of the matched tool is. Useful when the
    same payload applies to tools with different argument names.
    """


class Matcher(BaseModel):
    """How to decide if the probe fired."""

    kind: Literal[
        "substring",
        "regex",
        "marker_echo",
        "secret_pattern",
        "directive_passthrough",
        "schema_field",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class TestCase(BaseModel):
    """One probe in the jakk attack library."""

    # Prevent pytest from trying to collect this Pydantic model as a test class.
    __test__ = False

    id: str
    """Dotted identifier, e.g. ``mcp.command.shell_marker``."""

    surface: Literal["tool_call", "tool_list", "resource_list", "prompt_list"]
    """Which MCP surface the test exercises."""

    description: str

    owasp: list[str] = Field(default_factory=list)
    """OWASP-for-MCP codes (e.g. MCP05). Free-form strings, not validated against a fixed enum."""

    atlas: list[str] = Field(default_factory=list)
    """MITRE ATLAS technique IDs (e.g. AML.T0051)."""

    severity: Literal["info", "low", "medium", "high", "critical"] = "medium"

    expected_signal: str
    """Stable class label emitted on the finding (e.g. ``input.command_injection``)."""

    applies_to: AppliesTo = Field(default_factory=AppliesTo)
    payload: Payload = Field(default_factory=Payload)
    matcher: Matcher

    @field_validator("id")
    @classmethod
    def _id_must_be_dotted(cls, v: str) -> str:
        if not v or " " in v or "/" in v:
            raise ValueError("id must be a dotted slug with no spaces or slashes")
        return v


def load_library(path: Path | str) -> list[TestCase]:
    """Load every ``*.yaml`` file in ``path`` into a list of :class:`TestCase`.

    Raises :class:`ValueError` with the offending file path if any document
    fails schema validation. Duplicate ids across files are an error.
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"library directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"library path is not a directory: {root}")

    cases: list[TestCase] = []
    seen: dict[str, Path] = {}
    for yaml_path in sorted(root.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text())
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML parse error in {yaml_path}: {exc}") from exc
        if data is None:
            raise ValueError(f"empty YAML document: {yaml_path}")
        try:
            case = TestCase(**data)
        except ValidationError as exc:
            raise ValueError(f"schema error in {yaml_path}: {exc}") from exc
        if case.id in seen:
            raise ValueError(
                f"duplicate test id {case.id!r}: {seen[case.id]} and {yaml_path}"
            )
        seen[case.id] = yaml_path
        cases.append(case)
    return cases


def filter_cases(
    cases: Iterable[TestCase],
    select: Optional[str] = None,
    owasp: Optional[str] = None,
) -> list[TestCase]:
    """Filter by ``--select`` (exact id) and ``--owasp`` (membership in owasp list)."""
    out = list(cases)
    if select:
        out = [c for c in out if c.id == select]
    if owasp:
        owasp_upper = owasp.upper()
        out = [c for c in out if any(o.upper() == owasp_upper for o in c.owasp)]
    return out
