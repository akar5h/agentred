from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

try:  # optional; MUZZLE scripted flow does not require deepagents at runtime
    from deepagents import SubAgent, create_deep_agent
    from deepagents.middleware import MemoryMiddleware, SummarizationMiddleware
except Exception:  # pragma: no cover - optional dependency
    SubAgent = None
    create_deep_agent = None
    MemoryMiddleware = None
    SummarizationMiddleware = None

from harness.attack.synthesis.chain_strategy import ChainStrategy
from harness.campaign.runner import CampaignRunner
from harness.core.schemas import ExplorationTask, ObjectiveScript, RunConfig, VesselCandidate
from harness.explorer.explorer import Explorer
from harness.explorer.summarizer import Summarizer
from harness.grafter.grafter import Grafter
from harness.objective_replay.replayer import MVP_GOALS, ObjectiveReplayer
from harness.victim.base import VictimAdapter


@dataclass
class MuzzleCycleResult:
    cycle: int
    surfaces_found: list[str]
    vessels_grafted: int
    objective_script: ObjectiveScript | None
    judge_results: list


def make_victim_tools(victim: VictimAdapter, session_id: str):
    try:
        from langchain_core.tools import tool
    except Exception:  # pragma: no cover - optional dependency
        def tool(fn):
            return fn

    @tool
    async def send_turn_tool(message: str) -> str:
        result = await victim.send_turn(session_id, message)
        return str((result or {}).get("response", ""))

    @tool
    async def list_docs_tool() -> list:
        return await victim.list_docs(session_id)

    @tool
    async def reset_session_tool() -> str:
        await victim.reset_session(session_id)
        return "session reset"

    @tool
    async def upload_file_tool(filename: str, content: str, content_type: str = "text/plain") -> str:
        result = await victim.upload_file(session_id, filename, content.encode("utf-8"), content_type)
        return str(result)

    return [send_turn_tool, list_docs_tool, reset_session_tool, upload_file_tool]


class MuzzleOrchestrator:
    """
    Runs MUZZLE adaptive loop (Phase E) on top of CampaignRunner.
    """

    def __init__(
        self,
        victim: VictimAdapter,
        runner: CampaignRunner,
        config: RunConfig,
    ):
        self.victim = victim
        self.runner = runner
        self.config = config
        self.summarizer = Summarizer()
        self.grafter = Grafter(top_k=config.top_k_vessels)
        self._orchestrator = self._build_orchestrator()

    def _build_orchestrator(self):
        if (
            create_deep_agent is None
            or SubAgent is None
            or MemoryMiddleware is None
            or SummarizationMiddleware is None
            or not self.config.engagement_id
        ):
            return None

        memory_path = f"reports/{self.config.engagement_id}/memory/"
        try:
            return create_deep_agent(
                model=None,
                interrupt_on=[
                    "novel_surface",
                    "partial_ambiguous",
                    "agent_confused",
                    "high_confidence_hit",
                    "catalog_enrichment",
                ],
                middleware=[
                    MemoryMiddleware(memory_path=memory_path),
                    SummarizationMiddleware(),
                ],
                subagents=[
                    SubAgent(
                        name="explorer",
                        description="Runs benign tasks against the victim to map attack surfaces",
                        system_prompt="[See TRD-12 §1a — Explorer SubAgent]",
                        tools=[],
                    ),
                    SubAgent(
                        name="attacker",
                        description="Executes adversarial TestSpec payloads against the victim",
                        system_prompt="[See TRD-12 §1b — Attacker SubAgent]",
                        tools=[],
                    ),
                ],
            )
        except Exception:
            return None

    async def run_cycle(
        self,
        exploration_tasks: list[ExplorationTask],
        cycle: int,
        on_result: Optional[Callable[[Any], None]] = None,
        progress_fn: Optional[Callable[[str], None]] = None,
    ) -> MuzzleCycleResult:
        def _progress(msg: str) -> None:
            if progress_fn:
                progress_fn(msg)

        _progress(f"[cycle {cycle}] Explorer: running {len(exploration_tasks)} tasks...")
        explorer = Explorer(self.victim, timeout_seconds=self.config.timeout_seconds)
        traces = await explorer.run_all(exploration_tasks, engagement_id=self.config.engagement_id or None)
        summarized = [self.summarizer.summarize(t) for t in traces]
        surfaces_seen = sorted({s for st in summarized for s in st.inferred_surfaces})
        _progress(f"[cycle {cycle}] Explorer done: {len(traces)} traces, surfaces={surfaces_seen}")

        all_candidates: list[VesselCandidate] = []
        for st in summarized:
            all_candidates.extend(self.grafter.discover(st))
        ranked = self.grafter.rank(all_candidates)
        _progress(f"[cycle {cycle}] Grafter: {len(ranked)} ranked candidates — {[c.vessel_kind.value for c in ranked]}")

        api_key = os.getenv(self.config.analyst_api_key_env, "").strip()
        replayer = ObjectiveReplayer(
            victim=self.victim,
            openrouter_api_key=api_key,
            model=self.config.analyst_model,
        )
        objective_script: ObjectiveScript | None = None
        for goal in MVP_GOALS:
            if goal.goal_id in self.config.objective_goals:
                _progress(f"[cycle {cycle}] ObjectiveReplayer: eliciting goal '{goal.goal_id}'...")
                objective_script = await replayer.run_and_distill(goal, engagement_id=self.config.engagement_id or None)
                if objective_script and objective_script.imperative:
                    _progress(f"[cycle {cycle}] ObjectiveReplayer: imperative='{objective_script.imperative[:80]}'")
                    break

        chain_active = isinstance(self.runner.strategy, ChainStrategy)
        suite = (
            self.grafter.build_suite(ranked, objective_script, chain_strategy_active=chain_active)
            if objective_script and ranked
            else []
        )
        _progress(f"[cycle {cycle}] Grafter suite: {len(suite)} TestSpecs grafted")

        self.runner._cycle = int(cycle)
        results = await self.runner.run_all(suite, on_result=on_result)

        surfaces = sorted({c.vessel_kind.value for c in ranked})
        return MuzzleCycleResult(
            cycle=int(cycle),
            surfaces_found=surfaces,
            vessels_grafted=len(suite),
            objective_script=objective_script,
            judge_results=results,
        )

    async def run(
        self,
        exploration_tasks: list[ExplorationTask],
        on_result: Optional[Callable[[Any], None]] = None,
        progress_fn: Optional[Callable[[str], None]] = None,
    ) -> list[MuzzleCycleResult]:
        all_results: list[MuzzleCycleResult] = []
        seen_surfaces: set[str] = set()

        for cycle in range(max(1, int(self.config.max_muzzle_cycles))):
            result = await self.run_cycle(exploration_tasks, cycle=cycle, on_result=on_result, progress_fn=progress_fn)
            all_results.append(result)

            new_surfaces = set(result.surfaces_found) - seen_surfaces
            seen_surfaces.update(result.surfaces_found)
            if cycle > 0 and not new_surfaces:
                break

        return all_results
