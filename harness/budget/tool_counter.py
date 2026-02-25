"""Tool-call depth budget for MUZZLE agents."""
from __future__ import annotations

from enum import Enum


class ToolBudgetStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    EXHAUSTED = "EXHAUSTED"


class ToolCallCounter:
    """Tracks per-agent tool-call counts and enforces limits."""

    def __init__(self, limits: dict[str, int] | None = None):
        self._limits: dict[str, int] = dict(limits or {})
        self._counts: dict[str, int] = {}

    def increment(self, agent_name: str) -> ToolBudgetStatus:
        if agent_name not in self._limits:
            raise KeyError(f"Unknown agent: {agent_name!r}")
        self._counts[agent_name] = self._counts.get(agent_name, 0) + 1
        return self.check(agent_name)

    def check(self, agent_name: str) -> ToolBudgetStatus:
        if agent_name not in self._limits:
            raise KeyError(f"Unknown agent: {agent_name!r}")
        limit = self._limits[agent_name]
        count = self._counts.get(agent_name, 0)
        if count >= limit:
            return ToolBudgetStatus.EXHAUSTED
        if count >= limit * 0.8:
            return ToolBudgetStatus.WARNING
        return ToolBudgetStatus.OK

    def remaining(self, agent_name: str) -> int:
        if agent_name not in self._limits:
            raise KeyError(f"Unknown agent: {agent_name!r}")
        return max(0, self._limits[agent_name] - self._counts.get(agent_name, 0))

    def reset(self) -> None:
        self._counts.clear()

    def warning_message(self, agent_name: str) -> str:
        r = self.remaining(agent_name)
        status = self.check(agent_name)
        if status == ToolBudgetStatus.EXHAUSTED:
            return "BUDGET_EXHAUSTED \u2014 return your results NOW."
        if status == ToolBudgetStatus.WARNING:
            return f"You have {r} tool calls remaining, wrap up."
        return ""
