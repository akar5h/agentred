"""Eval metrics for comparing scripted vs agentic MUZZLE modes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalMetrics:
    mode: str                          # "scripted" or "agentic"
    surface_coverage: float = 0.0      # unique_surfaces / 7
    budget_efficiency: float = 0.0     # successes per 1k tokens
    turn_efficiency: float = 0.0       # successes per turn
    win_rate: float = 0.0              # successes / specs
    exploration_ratio: float = 0.0     # surfaces_found / (surfaces + specs)
    total_tokens: int = 0
    total_turns: int = 0
    total_specs: int = 0
    total_successes: int = 0
    surfaces_found: list[str] = field(default_factory=list)
    think_step_count: int = 0
    validation_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "surface_coverage": round(self.surface_coverage, 3),
            "budget_efficiency": round(self.budget_efficiency, 4),
            "turn_efficiency": round(self.turn_efficiency, 4),
            "win_rate": round(self.win_rate, 3),
            "exploration_ratio": round(self.exploration_ratio, 3),
            "total_tokens": self.total_tokens,
            "total_turns": self.total_turns,
            "total_specs": self.total_specs,
            "total_successes": self.total_successes,
            "surfaces_found": self.surfaces_found,
            "think_step_count": self.think_step_count,
            "validation_score": round(self.validation_score, 3),
        }


def compute_metrics(
    mode: str,
    cycle_results: list,
    judge_rows: list[dict],
    total_tokens: int,
) -> EvalMetrics:
    """Compute eval metrics from cycle results and judge rows.

    Parameters
    ----------
    mode:
        "scripted" or "agentic".
    cycle_results:
        List of MuzzleCycleResult-like objects with attributes:
        ``surfaces_found``, ``vessels_grafted``, ``judge_results``,
        ``validation``, ``think_steps``.
    judge_rows:
        List of judge result dicts, each with "status" and "turn_count" keys.
    total_tokens:
        Total tokens consumed across the run.
    """
    all_surfaces = sorted(set(s for cr in cycle_results for s in cr.surfaces_found))
    surface_coverage = len(all_surfaces) / 7

    total_specs = sum(cr.vessels_grafted for cr in cycle_results)
    total_successes = sum(1 for r in judge_rows if r.get("status") == "Success")
    total_turns = sum(r.get("turn_count", 0) for r in judge_rows)

    budget_efficiency = (total_successes / max(1, total_tokens)) * 1000
    turn_efficiency = total_successes / max(1, total_turns)
    win_rate = total_successes / max(1, total_specs)
    exploration_ratio = len(all_surfaces) / max(1, len(all_surfaces) + total_specs)

    think_step_count = sum(len(cr.think_steps) for cr in cycle_results)

    # Validation score: mean of quality_score across cycles that have validation
    validation_scores = [
        cr.validation.get("quality_score", 0.0)
        for cr in cycle_results
        if cr.validation
    ]
    validation_score = (
        sum(validation_scores) / len(validation_scores) if validation_scores else 0.0
    )

    return EvalMetrics(
        mode=mode,
        surface_coverage=surface_coverage,
        budget_efficiency=budget_efficiency,
        turn_efficiency=turn_efficiency,
        win_rate=win_rate,
        exploration_ratio=exploration_ratio,
        total_tokens=total_tokens,
        total_turns=total_turns,
        total_specs=total_specs,
        total_successes=total_successes,
        surfaces_found=all_surfaces,
        think_step_count=think_step_count,
        validation_score=validation_score,
    )


def _fmt_pct(value: float) -> str:
    """Format a float as a percentage string like '42.9%'."""
    return f"{value:.1%}"


def _delta_pct(scripted: float, agentic: float) -> str:
    """Format percentage delta like '+12.3%' or '-5.0%'."""
    diff = agentic - scripted
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.1%}"


def _delta_int(scripted: int, agentic: int) -> str:
    """Format integer delta like '+5' or '-3'."""
    diff = agentic - scripted
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff}"


def format_comparison_markdown(
    scripted: EvalMetrics,
    agentic: EvalMetrics,
    engagement_id: str,
) -> str:
    """Generate a markdown report comparing scripted and agentic modes."""
    lines: list[str] = []
    lines.append(f"# MUZZLE Eval Report \u2014 {engagement_id}")
    lines.append("")
    lines.append("## Metrics Comparison")
    lines.append("")
    lines.append("| Metric | Scripted | Agentic | Delta |")
    lines.append("|--------|----------|---------|-------|")
    lines.append(
        f"| Surface Coverage | {_fmt_pct(scripted.surface_coverage)} "
        f"| {_fmt_pct(agentic.surface_coverage)} "
        f"| {_delta_pct(scripted.surface_coverage, agentic.surface_coverage)} |"
    )
    lines.append(
        f"| Win Rate | {_fmt_pct(scripted.win_rate)} "
        f"| {_fmt_pct(agentic.win_rate)} "
        f"| {_delta_pct(scripted.win_rate, agentic.win_rate)} |"
    )
    lines.append(
        f"| Budget Efficiency | {scripted.budget_efficiency:.4f} "
        f"| {agentic.budget_efficiency:.4f} "
        f"| {_delta_pct(scripted.budget_efficiency, agentic.budget_efficiency)} |"
    )
    lines.append(
        f"| Turn Efficiency | {scripted.turn_efficiency:.4f} "
        f"| {agentic.turn_efficiency:.4f} "
        f"| {_delta_pct(scripted.turn_efficiency, agentic.turn_efficiency)} |"
    )
    lines.append(
        f"| Exploration Ratio | {_fmt_pct(scripted.exploration_ratio)} "
        f"| {_fmt_pct(agentic.exploration_ratio)} "
        f"| {_delta_pct(scripted.exploration_ratio, agentic.exploration_ratio)} |"
    )
    lines.append(
        f"| Validation Score | {scripted.validation_score:.3f} "
        f"| {agentic.validation_score:.3f} "
        f"| {_delta_pct(scripted.validation_score, agentic.validation_score)} |"
    )
    lines.append(
        f"| Think Steps | {scripted.think_step_count} "
        f"| {agentic.think_step_count} "
        f"| {_delta_int(scripted.think_step_count, agentic.think_step_count)} |"
    )
    lines.append("")
    lines.append("## Raw Numbers")
    lines.append("")
    lines.append("| Metric | Scripted | Agentic |")
    lines.append("|--------|----------|---------|")
    lines.append(
        f"| Total Tokens | {scripted.total_tokens} | {agentic.total_tokens} |"
    )
    lines.append(
        f"| Total Turns | {scripted.total_turns} | {agentic.total_turns} |"
    )
    lines.append(
        f"| Total Specs | {scripted.total_specs} | {agentic.total_specs} |"
    )
    lines.append(
        f"| Total Successes | {scripted.total_successes} | {agentic.total_successes} |"
    )
    lines.append("")
    lines.append("## Surfaces Found")
    lines.append("")
    lines.append(
        f"- Scripted: {', '.join(scripted.surfaces_found) or 'none'}"
    )
    lines.append(
        f"- Agentic: {', '.join(agentic.surfaces_found) or 'none'}"
    )
    lines.append("")

    return "\n".join(lines)
