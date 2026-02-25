"""UCB1 multi-armed bandit for surface::technique triage."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.core.schemas import JudgeResult, TestSpec


# Maps Status enum values to reward signals
REWARD_MAP: dict[str, float] = {
    "Success": 1.0,
    "Injection": 0.8,
    "Partial": 0.3,
    "Blocked": 0.0,
    "InfraFail": 0.0,
}


@dataclass
class BanditArm:
    arm_id: str
    pulls: int = 0
    total_reward: float = 0.0
    last_pulled_cycle: int = 0

    @property
    def mean_reward(self) -> float:
        if self.pulls == 0:
            return 0.0
        return self.total_reward / self.pulls


class SurfaceBandit:
    """UCB1 bandit over surface::technique arms."""

    def __init__(self, exploration_constant: float = 1.41):
        self.arms: dict[str, BanditArm] = {}
        self.exploration_constant: float = exploration_constant
        self.total_pulls: int = 0

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def update(self, arm_id: str, reward: float, cycle: int) -> None:
        arm = self.arms.setdefault(arm_id, BanditArm(arm_id=arm_id))
        arm.pulls += 1
        arm.total_reward += reward
        arm.last_pulled_cycle = cycle
        self.total_pulls += 1

    def update_from_result(self, result: "JudgeResult", spec: "TestSpec", cycle: int) -> None:
        surface = spec.attack_surface.value if spec.attack_surface else "unknown"
        technique = spec.technique_family or "unknown"
        arm_id = f"{surface}::{technique}"
        status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
        reward = REWARD_MAP.get(status_val, 0.0)
        self.update(arm_id, reward, cycle)

    def ucb1_score(self, arm: BanditArm) -> float:
        if arm.pulls == 0:
            return float("inf")
        if self.total_pulls == 0:
            return float("inf")
        exploit = arm.mean_reward
        explore = self.exploration_constant * math.sqrt(math.log(self.total_pulls) / arm.pulls)
        return exploit + explore

    def scores(self) -> dict[str, float]:
        return {arm_id: self.ucb1_score(arm) for arm_id, arm in self.arms.items()}

    def select(self, k: int = 5) -> list[str]:
        scored = sorted(self.arms.items(), key=lambda x: self.ucb1_score(x[1]), reverse=True)
        return [arm_id for arm_id, _ in scored[:k]]

    def boost_for_arm(self, arm_id: str) -> float:
        arm = self.arms.get(arm_id)
        if arm is None or arm.pulls == 0:
            return 0.0
        # Normalize mean_reward into 0..0.3 range
        return min(arm.mean_reward * 0.3, 0.3)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, engagement_id: str) -> None:
        path = Path("reports") / engagement_id / "memory" / "bandit.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "exploration_constant": self.exploration_constant,
            "total_pulls": self.total_pulls,
            "arms": {
                arm_id: {
                    "pulls": arm.pulls,
                    "total_reward": arm.total_reward,
                    "last_pulled_cycle": arm.last_pulled_cycle,
                }
                for arm_id, arm in self.arms.items()
            },
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, engagement_id: str) -> "SurfaceBandit":
        path = Path("reports") / engagement_id / "memory" / "bandit.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            bandit = cls(exploration_constant=data.get("exploration_constant", 1.41))
            bandit.total_pulls = data.get("total_pulls", 0)
            for arm_id, arm_data in data.get("arms", {}).items():
                bandit.arms[arm_id] = BanditArm(
                    arm_id=arm_id,
                    pulls=arm_data["pulls"],
                    total_reward=arm_data["total_reward"],
                    last_pulled_cycle=arm_data.get("last_pulled_cycle", 0),
                )
            return bandit
        except Exception:
            return cls()
