from __future__ import annotations

from typing import Any, Optional

from grafted.attack.base import AttackStrategy


class StaticStrategy(AttackStrategy):
    """Returns the base turn unchanged. Used for deterministic runs."""

    async def next_turn(
        self,
        *,
        scenario_id: str,
        objective: str,
        base_turn: str,
        transcript: list[dict],
        finding_memory: Optional[list[Any]] = None,
        current_surface: Optional[str] = None,
        current_technique: Optional[str] = None,
    ) -> str:
        return base_turn

    @property
    def is_adaptive(self) -> bool:
        return False
