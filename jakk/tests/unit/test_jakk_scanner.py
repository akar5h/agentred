"""Tests for scanner-internal helpers (no MCP server required)."""
from __future__ import annotations

import pytest

from jakk.mcp_client import ToolDescriptor
from jakk.scanner import _UnresolvedFirstStringArg, _UnresolvedTargetArg, _resolve_arguments


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


# ---------------------------------------------------------------------------
# __target_arg__ — C+ kind-based resolution
# ---------------------------------------------------------------------------


def _github_like_get_file_contents() -> ToolDescriptor:
    """The canonical multi-string-arg signature where position 0 is the
    wrong place to inject a path payload (it's `owner`, not `path`)."""
    return ToolDescriptor(
        name="get_file_contents",
        input_schema={
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "path": {"type": "string"},
                "ref": {"type": "string"},
            },
            "required": ["owner", "repo", "path"],
        },
    )


def test_target_arg_resolves_to_kind_matched_arg_not_first():
    """The whole point of C+: against a multi-arg tool, __target_arg__ lands
    in the semantically-correct field, not whatever happens to be first."""
    args = {"__target_arg__": "/etc/passwd"}
    out = _resolve_arguments(args, _github_like_get_file_contents(), "abc123", "path")
    assert out == {"path": "/etc/passwd"}
    # Sanity: __first_string_arg__ would have picked the wrong field.
    out2 = _resolve_arguments({"__first_string_arg__": "/etc/passwd"}, _github_like_get_file_contents(), "abc123")
    assert out2 == {"owner": "/etc/passwd"}  # this is exactly the bug C+ fixes


def test_target_arg_with_run_id_template():
    args = {"__target_arg__": "/canary-{run_id}/file"}
    out = _resolve_arguments(args, _github_like_get_file_contents(), "deadbeef", "path")
    assert out == {"path": "/canary-deadbeef/file"}


def test_target_arg_raises_when_kind_not_set():
    """Misconfigured YAML: __target_arg__ used but applies_to.target_arg_kind
    is None. We refuse to guess silently."""
    args = {"__target_arg__": "anything"}
    with pytest.raises(_UnresolvedTargetArg, match="target_arg_kind is not set"):
        _resolve_arguments(args, _github_like_get_file_contents(), "abc123", None)


def test_target_arg_raises_when_no_arg_of_kind():
    """Probe filter SHOULD have excluded this tool at applies_to time. If
    we get here, the scanner refuses to silently degrade."""
    args = {"__target_arg__": "anything"}
    no_path_tool = ToolDescriptor(
        name="get_repo",
        input_schema={"properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}},
    )
    with pytest.raises(_UnresolvedTargetArg, match="no argument matching"):
        _resolve_arguments(args, no_path_tool, "abc123", "path")


def test_target_arg_and_other_keys_coexist():
    """A probe can mix __target_arg__ with explicit args + run_id templates."""
    args = {
        "__target_arg__": "/canary",
        "owner": "test-user",
        "repo": "test-repo",
        "ref": "main-{run_id}",
    }
    out = _resolve_arguments(args, _github_like_get_file_contents(), "xx", "path")
    assert out == {
        "path": "/canary",
        "owner": "test-user",
        "repo": "test-repo",
        "ref": "main-xx",
    }
