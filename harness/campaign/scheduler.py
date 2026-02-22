from __future__ import annotations

from collections.abc import Callable
from typing import List, Optional

from harness.campaign.runner import CampaignRunner
from harness.core.enums import Status
from harness.core.schemas import JudgeResult, TestSpec


class Scheduler:
    """
    Wraps CampaignRunner to add filtering, circuit breaking, and cost caps.
    """

    def __init__(
        self,
        runner: CampaignRunner,
        max_cost_usd: float = 10.0,
        max_infra_fail_consecutive: int = 3,
    ):
        self.runner = runner
        self.max_cost_usd = float(max_cost_usd)
        self.max_infra_fail_consecutive = max(1, int(max_infra_fail_consecutive))

    async def run(
        self,
        specs: List[TestSpec],
        runs_per_scenario: int = 1,
        scenario_filter: Optional[List[str]] = None,
        on_result: Optional[Callable[[JudgeResult], None]] = None,
        on_before_run: Optional[Callable[["TestSpec", int], None]] = None,
    ) -> List[JudgeResult]:
        selected = set(scenario_filter or [])
        out: List[JudgeResult] = []

        consecutive_infra = 0
        cost_spent = 0.0

        for spec in specs:
            if selected and spec.scenario_id not in selected:
                continue

            for rep in range(1, max(1, int(runs_per_scenario)) + 1):
                if cost_spent >= self.max_cost_usd:
                    return out

                if on_before_run is not None:
                    on_before_run(spec, rep)

                result = await self.runner.run_one(spec, rep=rep)
                out.append(result)
                if on_result is not None:
                    on_result(result)

                if result.status == Status.INFRA_FAIL:
                    consecutive_infra += 1
                else:
                    consecutive_infra = 0

                if consecutive_infra >= self.max_infra_fail_consecutive:
                    return out

                # Placeholder for future token/cost accounting.
                cost_spent += 0.0

        return out
