from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class AttackStrategy(ABC):
    """Abstract base class for attack turn synthesis."""

    @abstractmethod
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
        """Return the turn to send for the current step."""

    @property
    @abstractmethod
    def is_adaptive(self) -> bool:
        """Return True if this strategy mutates turn text."""
