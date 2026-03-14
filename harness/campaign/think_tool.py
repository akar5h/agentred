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
    get_think_log,
    cycle=None,
    use_stream_writer: bool = True,
    *,
    get_cycle=None,
):
    """Factory that returns a LangChain @tool for structured reasoning.

    Parameters
    ----------
    get_think_log : callable or ThinkLog
        Either a zero-arg callable returning the current ThinkLog, or a
        ThinkLog instance directly (for backward compat / tests).  Using a
        callable avoids stale-closure bugs when MuzzleOrchestrator replaces
        ``self._think_log`` each cycle.
    cycle : int or None
        Static cycle number (backward compat).  Prefer ``get_cycle``.
    get_cycle : callable or None
        Zero-arg callable returning the current cycle number.  Takes
        precedence over ``cycle``.  Defaults to reading
        ``think_log.cycle`` at call time.
    use_stream_writer : bool
        When True, attempts to emit via ``langgraph.config.get_stream_writer()``
        for real-time streaming.  Set False in unit tests.
    """
    # Support both callables and direct objects for backward compat
    if callable(get_think_log) and not isinstance(get_think_log, ThinkLog):
        _resolve_log = get_think_log
    else:
        _log_ref = get_think_log
        _resolve_log = lambda: _log_ref  # noqa: E731

    # Resolve cycle: get_cycle (callable) > cycle (static int) > think_log.cycle
    if get_cycle is not None and callable(get_cycle):
        _resolve_cycle = get_cycle
    elif cycle is not None:
        _static_cycle = int(cycle)
        _resolve_cycle = lambda: _static_cycle  # noqa: E731
    else:
        _resolve_cycle = lambda: _resolve_log().cycle  # noqa: E731

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
        current_log = _resolve_log()
        current_cycle = _resolve_cycle()
        step = ThinkStep(
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            cycle=current_cycle,
            reasoning=reasoning,
            context=context,
            decision=decision,
        )
        current_log.add(step)

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
