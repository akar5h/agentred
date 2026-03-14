"""Per-cycle working memory (scratchpad that resets each cycle)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VesselOutcome:
    vessel_kind: str
    technique: str
    status: str
    oracle_codes: list[str] = field(default_factory=list)
    turn_count: int = 0


@dataclass
class WorkingMemory:
    cycle: int = 0
    surfaces_discovered: list[str] = field(default_factory=list)
    vessels_tried: list[VesselOutcome] = field(default_factory=list)
    current_hypothesis: str = ""
    notes: list[str] = field(default_factory=list)

    def record_surface(self, surface: str) -> None:
        if surface and surface not in self.surfaces_discovered:
            self.surfaces_discovered.append(surface)

    def record_vessel_outcome(
        self,
        vessel_kind: str,
        technique: str,
        status: str,
        oracle_codes: list[str] | None = None,
        turn_count: int = 0,
    ) -> None:
        self.vessels_tried.append(
            VesselOutcome(
                vessel_kind=vessel_kind,
                technique=technique,
                status=status,
                oracle_codes=list(oracle_codes or []),
                turn_count=turn_count,
            )
        )

    def set_hypothesis(self, hypothesis: str) -> None:
        self.current_hypothesis = hypothesis

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    def summarize_for_carry_forward(self) -> str:
        parts: list[str] = [f"Cycle {self.cycle}:"]
        if self.surfaces_discovered:
            parts.append(f"  Surfaces: {', '.join(self.surfaces_discovered)}")
        successes = [v for v in self.vessels_tried if v.status in ("Success", "Injection")]
        partials = [v for v in self.vessels_tried if v.status == "Partial"]
        if successes:
            parts.append(f"  Wins: {len(successes)} ({', '.join(v.technique for v in successes)})")
        if partials:
            parts.append(f"  Partials: {len(partials)}")
        if self.current_hypothesis:
            parts.append(f"  Hypothesis: {self.current_hypothesis}")
        if self.notes:
            parts.append(f"  Notes: {'; '.join(self.notes[-3:])}")
        return "\n".join(parts)

    def reset(self, new_cycle: int) -> "WorkingMemory":
        summary = self.summarize_for_carry_forward()
        wm = WorkingMemory(cycle=new_cycle)
        if summary:
            wm.add_note(f"[carry-forward] {summary}")
        return wm
