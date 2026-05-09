from __future__ import annotations

from abc import ABC, abstractmethod

from grafted.core.schemas import JudgeResult


class Oracle(ABC):
    """Abstract base class for all oracles."""

    @abstractmethod
    async def evaluate(self, observation: dict) -> JudgeResult:
        """Evaluate an observation dict and return a JudgeResult."""
