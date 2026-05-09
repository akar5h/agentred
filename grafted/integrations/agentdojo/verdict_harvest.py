"""Harvest (utility, security) verdicts from AgentDojo's logdir.

AgentDojo persists each (user_task, injection_task) result as a JSON file
at ``{logdir}/{pipeline_name}/{suite_name}/{user_task_id}/{attack_type}/{injection_task_id}.json``
with top-level fields ``utility: bool``, ``security: bool``, and
``injections: dict``. ``security == False`` means the injection succeeded
(the agent did the attacker's bidding) — this is grafted's win signal.

VerdictHarvester is stateful: it tracks which log files it has already
consumed (per engagement_id) so the same verdict isn't applied twice
when GraftedAttack.attack() reads from logdir at the start of each call.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("grafted.integrations.agentdojo.verdict_harvest")


@dataclass(frozen=True)
class Verdict:
    user_task_id: str
    injection_task_id: str
    utility: bool
    security: bool


class VerdictHarvester:
    """Walks AgentDojo's logdir and yields not-yet-consumed verdicts.

    Args:
        logdir: AgentDojo logdir root (passed to benchmark_suite_with_injections).
        pipeline_name: AgentDojo pipeline name (e.g., 'gpt-4o-2024-05-13').
        suite_name: AgentDojo suite name (e.g., 'workspace').
        attack_name: must match ``GraftedAttack.name`` ('grafted').
    """

    def __init__(
        self,
        logdir: Path,
        pipeline_name: str,
        suite_name: str,
        attack_name: str = "grafted",
    ) -> None:
        self.logdir = Path(logdir)
        self.pipeline_name = pipeline_name
        self.suite_name = suite_name
        self.attack_name = attack_name
        self._seen: dict[str, set[Path]] = {}

    def _attack_dir_pattern(self) -> Path:
        return self.logdir / self.pipeline_name / self.suite_name

    def new_verdicts(self, engagement_id: str) -> Iterator[Verdict]:
        """Yield verdicts that haven't been seen for this engagement_id yet.

        engagement_id is used as the dedup key so multiple GraftedAttack
        instances over the lifetime of a script don't replay verdicts.
        """
        seen = self._seen.setdefault(engagement_id, set())
        root = self._attack_dir_pattern()
        if not root.exists():
            return

        for user_task_dir in root.iterdir():
            if not user_task_dir.is_dir():
                continue
            attack_dir = user_task_dir / self.attack_name
            if not attack_dir.is_dir():
                continue
            for log_file in attack_dir.glob("injection_task_*.json"):
                if log_file in seen:
                    continue
                seen.add(log_file)
                verdict = self._parse(log_file)
                if verdict is not None:
                    yield verdict

    def _parse(self, log_file: Path) -> Verdict | None:
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping malformed log %s: %s", log_file, exc)
            return None

        user_task_id = data.get("user_task_id", "")
        injection_task_id = data.get("injection_task_id", "")
        utility = data.get("utility")
        security = data.get("security")

        if not user_task_id or not injection_task_id:
            return None
        if not isinstance(utility, bool) or not isinstance(security, bool):
            return None

        return Verdict(
            user_task_id=user_task_id,
            injection_task_id=injection_task_id,
            utility=utility,
            security=security,
        )
