"""Cross-cycle strategic memory — persisted to JSON between cycles."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger("grafted.memory.strategic")

# Per-surface cap on retained winning_turns. The attacker LLM sees these as
# exemplars during synthesis (via FindingMemory → _build_winning_turns_block).
# Empirically tested at N=10 on banking and it HURT ASR by ~18pp (more
# exemplars caused the attacker to over-anchor on the same style instead
# of innovating). Reverted to 3 — the original conservative default.
WINNING_TURNS_CAP = 3

if TYPE_CHECKING:
    from grafted.core.schemas import JudgeResult, TestSpec
    from grafted.memory.working import WorkingMemory


@dataclass
class SurfaceStats:
    attempts: int = 0
    successes: int = 0
    partials: int = 0
    last_cycle: int = -1


@dataclass
class WinningTurn:
    turn_text: str
    cycle: int
    technique: str = ""


@dataclass
class TechniqueStats:
    attempts: int = 0
    successes: int = 0
    last_cycle: int = -1


@dataclass
class RationaleStats:
    attempts: int = 0
    confirmed: int = 0


@dataclass
class StrategicMemory:
    engagement_id: str = ""
    surface_stats: dict[str, SurfaceStats] = field(default_factory=dict)
    technique_stats: dict[str, TechniqueStats] = field(default_factory=dict)
    behavioral_patterns: list[str] = field(default_factory=list)
    winning_turns: dict[str, list[WinningTurn]] = field(default_factory=dict)
    cycle_summaries: list[str] = field(default_factory=list)
    rationale_stats: dict[str, RationaleStats] = field(default_factory=dict)
    failed_attacks: dict[str, list[str]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Update helpers
    # ------------------------------------------------------------------

    def update_from_result(self, result: "JudgeResult", spec: "TestSpec", cycle: int) -> None:
        surface = spec.attack_surface.value if spec.attack_surface else "unknown"
        technique = spec.technique_family or "unknown"
        status_val = result.status.value if hasattr(result.status, "value") else str(result.status)

        # Surface stats
        ss = self.surface_stats.setdefault(surface, SurfaceStats())
        ss.attempts += 1
        ss.last_cycle = cycle
        if status_val in ("Success", "Injection"):
            ss.successes += 1
        elif status_val == "Partial":
            ss.partials += 1

        # Technique stats
        ts = self.technique_stats.setdefault(technique, TechniqueStats())
        ts.attempts += 1
        ts.last_cycle = cycle
        if status_val in ("Success", "Injection"):
            ts.successes += 1

        logger.info("strategic surface=%s technique=%s status=%s -> win_rate=%.3f",
                    surface, technique, status_val, self.surface_win_rate(surface))

        # Rationale accuracy tracking
        if hasattr(result, "rationale_confirmed") and result.rationale_confirmed is not None:
            rs = self.rationale_stats.setdefault(surface, RationaleStats())
            rs.attempts += 1
            if result.rationale_confirmed:
                rs.confirmed += 1

        # Failed attack memory — record blocked turns to avoid repetition
        if status_val == "Blocked" and spec.turns:
            self.record_failed_attack(surface, spec.turns[-1])

        # Winning turns
        if status_val in ("Success", "Injection") and spec.turns:
            wt_list = self.winning_turns.setdefault(surface, [])
            wt_list.append(WinningTurn(
                turn_text=spec.turns[-1][:500],
                cycle=cycle,
                technique=technique,
            ))
            # Keep top-N by recency. Bumped from 3 → 10 after the banking
            # ablation showed 0pp memory effect on a non-saturated baseline;
            # 3 exemplars is a thin signal, especially when injection_tasks
            # span multiple action categories (banking has 9 distinct types).
            self.winning_turns[surface] = wt_list[-WINNING_TURNS_CAP:]

    def record_behavioral_pattern(self, pattern: str) -> None:
        if pattern and pattern not in self.behavioral_patterns:
            self.behavioral_patterns.append(pattern)

    def record_failed_attack(self, surface: str, turn_text: str) -> None:
        bucket = self.failed_attacks.setdefault(surface, [])
        fingerprint = turn_text.strip()[:200]
        if fingerprint and fingerprint not in bucket:
            bucket.append(fingerprint)
        self.failed_attacks[surface] = bucket[-10:]

    def rationale_accuracy(self, surface: str) -> float:
        rs = self.rationale_stats.get(surface)
        if rs is None or rs.attempts == 0:
            return 0.0
        return rs.confirmed / rs.attempts

    def ingest_working_memory(self, wm: "WorkingMemory") -> None:
        summary = wm.summarize_for_carry_forward()
        if summary:
            self.cycle_summaries.append(summary)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def surface_win_rate(self, surface: str) -> float:
        ss = self.surface_stats.get(surface)
        if ss is None or ss.attempts == 0:
            return 0.0
        return ss.successes / ss.attempts

    def technique_effectiveness(self, technique: str) -> float:
        ts = self.technique_stats.get(technique)
        if ts is None or ts.attempts == 0:
            return 0.0
        return ts.successes / ts.attempts

    def top_winning_turns(self, surface: str, k: int = 3) -> list[str]:
        wt_list = self.winning_turns.get(surface, [])
        return [wt.turn_text for wt in wt_list[-k:]]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, engagement_id: str) -> None:
        path = Path("reports") / engagement_id / "memory" / "strategic.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, engagement_id: str) -> "StrategicMemory":
        path = Path("reports") / engagement_id / "memory" / "strategic.json"
        if not path.exists():
            return cls(engagement_id=engagement_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls._from_dict(data, engagement_id)
        except Exception as exc:
            logger.warning("Failed to load strategic memory for %s: %s", engagement_id, exc)
            return cls(engagement_id=engagement_id)

    def _to_dict(self) -> dict:
        return {
            "engagement_id": self.engagement_id,
            "surface_stats": {
                k: {"attempts": v.attempts, "successes": v.successes, "partials": v.partials, "last_cycle": v.last_cycle}
                for k, v in self.surface_stats.items()
            },
            "technique_stats": {
                k: {"attempts": v.attempts, "successes": v.successes, "last_cycle": v.last_cycle}
                for k, v in self.technique_stats.items()
            },
            "behavioral_patterns": self.behavioral_patterns,
            "winning_turns": {
                k: [{"turn_text": wt.turn_text, "cycle": wt.cycle, "technique": wt.technique} for wt in v]
                for k, v in self.winning_turns.items()
            },
            "cycle_summaries": self.cycle_summaries,
            "rationale_stats": {
                k: {"attempts": v.attempts, "confirmed": v.confirmed}
                for k, v in self.rationale_stats.items()
            },
            "failed_attacks": self.failed_attacks,
        }

    @classmethod
    def _from_dict(cls, data: dict, engagement_id: str) -> "StrategicMemory":
        sm = cls(engagement_id=engagement_id)
        for k, v in data.get("surface_stats", {}).items():
            sm.surface_stats[k] = SurfaceStats(**v)
        for k, v in data.get("technique_stats", {}).items():
            sm.technique_stats[k] = TechniqueStats(**v)
        sm.behavioral_patterns = list(data.get("behavioral_patterns", []))
        for k, turns in data.get("winning_turns", {}).items():
            sm.winning_turns[k] = [WinningTurn(**wt) for wt in turns]
        sm.cycle_summaries = list(data.get("cycle_summaries", []))
        for k, v in data.get("rationale_stats", {}).items():
            sm.rationale_stats[k] = RationaleStats(**v)
        sm.failed_attacks = {k: list(v) for k, v in data.get("failed_attacks", {}).items()}
        return sm
