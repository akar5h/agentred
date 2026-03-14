"""Token / context budget tracker for MUZZLE agents."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BudgetStatus(str, Enum):
    OK = "OK"
    WARNING_80_PCT = "WARNING_80_PCT"
    EXHAUSTED = "EXHAUSTED"


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_tokens: int, output_tokens: int, est_cost: float = 0.0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.est_cost += est_cost


class BudgetTracker:
    """Tracks per-cycle and campaign-wide token budgets."""

    def __init__(
        self,
        explorer_ceiling: int = 50_000,
        attacker_ceiling: int = 80_000,
        campaign_budget: int = 500_000,
    ):
        self.explorer_ceiling = max(1, explorer_ceiling)
        self.attacker_ceiling = max(1, attacker_ceiling)
        self.campaign_budget = max(1, campaign_budget)

        self._ceilings: dict[str, int] = {
            "explorer": self.explorer_ceiling,
            "attacker": self.attacker_ceiling,
        }
        self._cycle_usage: dict[str, TokenUsage] = {}
        self._campaign_usage = TokenUsage()

    def record(
        self,
        agent_name: str,
        input_tokens: int,
        output_tokens: int,
        est_cost: float = 0.0,
    ) -> None:
        if agent_name not in self._cycle_usage:
            self._cycle_usage[agent_name] = TokenUsage()
        self._cycle_usage[agent_name].add(input_tokens, output_tokens, est_cost)
        self._campaign_usage.add(input_tokens, output_tokens, est_cost)

    def check(self, agent_name: str) -> BudgetStatus:
        usage = self._cycle_usage.get(agent_name)
        if usage is None:
            return BudgetStatus.OK

        ceiling = self._ceilings.get(agent_name)
        if ceiling is None:
            return BudgetStatus.OK

        used = usage.total_tokens
        if used >= ceiling:
            return BudgetStatus.EXHAUSTED
        if used >= ceiling * 0.8:
            return BudgetStatus.WARNING_80_PCT
        return BudgetStatus.OK

    def reset_cycle(self) -> None:
        self._cycle_usage.clear()

    def is_campaign_exhausted(self) -> bool:
        return self._campaign_usage.total_tokens >= self.campaign_budget

    def cycle_usage(self, agent_name: str) -> TokenUsage:
        return self._cycle_usage.get(agent_name, TokenUsage())

    @property
    def campaign_usage(self) -> TokenUsage:
        return self._campaign_usage

    def to_telemetry_dict(self) -> dict:
        cycle = {
            name: {
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "total_tokens": u.total_tokens,
                "est_cost": u.est_cost,
            }
            for name, u in self._cycle_usage.items()
        }
        return {
            "cycle_usage": cycle,
            "campaign_total_tokens": self._campaign_usage.total_tokens,
            "campaign_est_cost": self._campaign_usage.est_cost,
            "campaign_exhausted": self.is_campaign_exhausted(),
        }
