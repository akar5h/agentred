"""Compatibility filter — decide which discovered tools a test fires against."""
from __future__ import annotations

import re
from typing import Iterable

from .library import AppliesTo, TestCase
from .mcp_client import ToolDescriptor


def matches(applies_to: AppliesTo, tool: ToolDescriptor) -> bool:
    if applies_to.none:
        return False
    if applies_to.tool_name and tool.name != applies_to.tool_name:
        return False
    if applies_to.tool_name_regex and not re.search(applies_to.tool_name_regex, tool.name):
        return False
    if applies_to.min_string_args and tool.string_arg_count() < applies_to.min_string_args:
        return False
    if applies_to.require_no_required_args:
        required = (tool.input_schema or {}).get("required") or []
        if required:
            return False
    return True


def select_tools(case: TestCase, tools: Iterable[ToolDescriptor]) -> list[ToolDescriptor]:
    """Return the subset of ``tools`` that ``case.applies_to`` matches."""
    if case.applies_to.none:
        return []
    return [t for t in tools if matches(case.applies_to, t)]
