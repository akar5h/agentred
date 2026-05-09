"""Post-cycle quality validator for MUZZLE campaigns.

Runs a battery of heuristic checks on each cycle's outputs and produces
a ``ValidationReport`` with warnings and a quality score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationWarning:
    check: str  # e.g. "surface_coverage", "blocked_loop", "budget_waste"
    severity: str  # "info", "warning", "error"
    message: str
    metric_value: float = 0.0


@dataclass
class ValidationReport:
    cycle: int
    quality_score: float  # 0.0-1.0
    warnings: list[ValidationWarning] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "cycle": self.cycle,
            "quality_score": self.quality_score,
            "warnings": [
                {
                    "check": w.check,
                    "severity": w.severity,
                    "message": w.message,
                    "metric_value": w.metric_value,
                }
                for w in self.warnings
            ],
            "metrics": self.metrics,
        }


class AgentValidator:
    """Validates a single MUZZLE cycle and returns a quality report."""

    TOTAL_SURFACES = 7  # The 7 MUZZLE attack surfaces

    def validate(
        self,
        cycle: int,
        surfaces_explored: list[str],
        surface_stats: dict[str, Any],
        total_attempts: int,
        total_successes: int,
        surfaces_discovered: int,
        specs_count: int,
        think_step_count: int,
    ) -> ValidationReport:
        warnings: list[ValidationWarning] = []

        # --- 1. Surface coverage ---
        coverage = len(surfaces_explored) / self.TOTAL_SURFACES
        if cycle >= 1 and coverage < 0.3:
            warnings.append(
                ValidationWarning(
                    check="surface_coverage",
                    severity="warning",
                    message=(
                        f"Low surface coverage ({coverage:.0%}) after cycle {cycle}. "
                        f"Only {len(surfaces_explored)}/{self.TOTAL_SURFACES} surfaces explored."
                    ),
                    metric_value=coverage,
                )
            )

        # --- 2. Blocked surface loop ---
        for surface_name, stats in surface_stats.items():
            attempts = stats.get("attempts", 0) if isinstance(stats, dict) else getattr(stats, "attempts", 0)
            successes = stats.get("successes", 0) if isinstance(stats, dict) else getattr(stats, "successes", 0)
            if attempts >= 3 and successes == 0:
                warnings.append(
                    ValidationWarning(
                        check="blocked_loop",
                        severity="error",
                        message=(
                            f"Surface '{surface_name}' has {attempts} attempts with 0 successes. "
                            f"Consider deprioritising or changing technique."
                        ),
                        metric_value=float(attempts),
                    )
                )

        # --- 3. Budget waste ratio ---
        waste_ratio = 0.0
        if total_attempts >= 5:
            waste_ratio = 1.0 - (total_successes / total_attempts)
            if waste_ratio > 0.9:
                warnings.append(
                    ValidationWarning(
                        check="budget_waste",
                        severity="warning",
                        message=(
                            f"High budget waste ratio ({waste_ratio:.0%}): "
                            f"{total_successes}/{total_attempts} successes."
                        ),
                        metric_value=waste_ratio,
                    )
                )

        # --- 4. Exploration / exploitation balance ---
        exploration_ratio = surfaces_discovered / max(1, surfaces_discovered + specs_count)
        if cycle == 0 and exploration_ratio < 0.2:
            warnings.append(
                ValidationWarning(
                    check="exploration_ratio",
                    severity="warning",
                    message=(
                        f"Low exploration ratio ({exploration_ratio:.0%}) on cycle 0. "
                        f"Consider exploring more surfaces before exploiting."
                    ),
                    metric_value=exploration_ratio,
                )
            )

        # --- 5. Think step count ---
        if think_step_count < 2:
            warnings.append(
                ValidationWarning(
                    check="think_steps",
                    severity="info",
                    message=(
                        f"Only {think_step_count} think() calls recorded. "
                        f"Structured reasoning improves cycle quality."
                    ),
                    metric_value=float(think_step_count),
                )
            )

        # --- Quality score ---
        score = 1.0
        for w in warnings:
            if w.severity == "error":
                score -= 0.2
            elif w.severity == "warning":
                score -= 0.1
            # "info" does not deduct
        score += 0.2 * coverage
        if think_step_count >= 2:
            score += 0.1
        score = max(0.0, min(1.0, score))

        return ValidationReport(
            cycle=cycle,
            quality_score=round(score, 4),
            warnings=warnings,
            metrics={
                "coverage": round(coverage, 4),
                "waste_ratio": round(waste_ratio, 4),
                "exploration_ratio": round(exploration_ratio, 4),
                "think_steps": think_step_count,
            },
        )
