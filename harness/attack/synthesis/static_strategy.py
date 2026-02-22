from __future__ import annotations

from harness.attack.base import AttackStrategy


class StaticStrategy(AttackStrategy):
    """Returns the base turn unchanged. Used for deterministic runs."""

    async def next_turn(
        self,
        *,
        scenario_id: str,
        objective: str,
        base_turn: str,
        transcript: list[dict],
    ) -> str:
        return base_turn

    @property
    def is_adaptive(self) -> bool:
        return False
