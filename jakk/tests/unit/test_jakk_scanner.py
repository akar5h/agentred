"""Tests for scanner-internal helpers (no MCP server required)."""
from __future__ import annotations

import pytest

from jakk.mcp_client import ToolDescriptor
from jakk.scanner import _UnresolvedFirstStringArg, _resolve_arguments


def _tool_with_first_string(arg_name: str = "repo_name") -> ToolDescriptor:
    return ToolDescriptor(
        name="t",
        input_schema={"properties": {arg_name: {"type": "string"}}, "required": [arg_name]},
    )


def _tool_no_string_args() -> ToolDescriptor:
    return ToolDescriptor(
        name="t",
        input_schema={"properties": {"count": {"type": "integer"}}, "required": []},
    )


def test_resolve_arguments_substitutes_first_string_arg():
    args = {"__first_string_arg__": "value-{run_id}"}
    out = _resolve_arguments(args, _tool_with_first_string("name"), "abc123")
    assert out == {"name": "value-abc123"}


def test_resolve_arguments_run_id_substitution_works_for_explicit_keys():
    args = {"q": "marker-{run_id}"}
    out = _resolve_arguments(args, _tool_with_first_string(), "abc123")
    assert out == {"q": "marker-abc123"}


def test_resolve_arguments_raises_when_no_string_arg_available():
    """Bug B: previously this silently dropped the key. Now it raises so the
    scanner can emit an explicit skipped finding instead of calling the tool
    with empty arguments."""
    args = {"__first_string_arg__": "anything"}
    with pytest.raises(_UnresolvedFirstStringArg):
        _resolve_arguments(args, _tool_no_string_args(), "abc123")


def test_resolve_arguments_with_no_tool_passes_through_literal_keys():
    # When there's no tool context (e.g. schema-only test), __first_string_arg__
    # cannot resolve. Literal keys still resolve their {run_id}.
    args = {"q": "marker-{run_id}", "other": 42}
    out = _resolve_arguments(args, None, "deadbeef")
    assert out == {"q": "marker-deadbeef", "other": 42}


def test_resolve_arguments_non_string_values_passthrough():
    args = {"count": 5, "items": ["a", "b"], "flag": True}
    out = _resolve_arguments(args, _tool_with_first_string(), "xx")
    assert out == {"count": 5, "items": ["a", "b"], "flag": True}
