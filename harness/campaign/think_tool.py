"""ThinkTool — structured reasoning capture for MUZZLE agentic SubAgents."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from harness.core.schemas import ThinkStep


@dataclass
class ThinkLog:
    """Accumulates ThinkStep entries for a single cycle."""

    cycle: int = 0
    steps: list[ThinkStep] = field(default_factory=list)

    def add(self, step: ThinkStep) -> None:
        self.steps.append(step)

    def to_telemetry_dicts(self) -> list[dict[str, Any]]:
        return [s.model_dump() for s in self.steps]

    def summary(self) -> str:
        if not self.steps:
            return f"Cycle {self.cycle}: 0 think steps"
        lines = [f"Cycle {self.cycle}: {len(self.steps)} think step(s)"]
        for i, s in enumerate(self.steps, 1):
            ctx = f" [{s.context}]" if s.context else ""
            decision = f" -> {s.decision}" if s.decision else ""
            lines.append(f"  {i}. {s.reasoning[:80]}{ctx}{decision}")
        return "\n".join(lines)


def make_think_tool(
    think_log: ThinkLog,
    cycle: int = 0,
    use_stream_writer: bool = True,
):
    """Factory that returns a LangChain @tool for structured reasoning.

    Parameters
    ----------
    think_log : ThinkLog
        Accumulator for this cycle's reasoning steps.
    cycle : int
        Current MUZZLE cycle number.
    use_stream_writer : bool
        When True, attempts to emit via ``langgraph.config.get_stream_writer()``
        for real-time streaming.  Set False in unit tests.
    """
    try:
        from langchain_core.tools import tool as _lc_tool
    except Exception:  # pragma: no cover
        def _lc_tool(fn):  # type: ignore[misc]
            return fn

    @_lc_tool
    def think(reasoning: str, context: str = "", decision: str = "") -> str:
        """Pause and reason before acting. Call this before every major decision.

        Args:
            reasoning: Your chain-of-thought reasoning about the current situation.
            context: Phase label — one of pre_exploration, post_grafter,
                     attack_planning, post_attack, hypothesis.
            decision: The decision you reached (if any).
        """
        step = ThinkStep(
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            cycle=cycle,
            reasoning=reasoning,
            context=context,
            decision=decision,
        )
        think_log.add(step)

        # Emit via LangGraph stream writer for real-time visibility
        if use_stream_writer:
            try:
                from langgraph.config import get_stream_writer
                writer = get_stream_writer()
                writer({"type": "think_step", "step": step.model_dump()})
            except Exception:
                pass  # Not inside a streaming graph — swallow silently

        return f"Recorded: {reasoning[:120]}"

    return think
