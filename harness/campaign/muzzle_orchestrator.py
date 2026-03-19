from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from harness.attack.catalog.loader import load_test_specs
from harness.attack.synthesis.chain_strategy import ChainStrategy
from harness.budget.tool_counter import ToolBudgetStatus, ToolCallCounter
from harness.budget.tracker import BudgetStatus, BudgetTracker
from harness.campaign.runner import CampaignRunner
from harness.campaign.think_tool import ThinkLog, make_think_tool
from harness.campaign.validator import AgentValidator
from harness.core.enums import AttackSurface
from harness.core.schemas import (
    AgenticCycleOutput,
    ExecutionStep,
    ExplorationTask,
    ObjectiveScript,
    RunConfig,
    SummarizedTrace,
    TestSpec,
    VesselCandidate,
)
from harness.explorer.explorer import Explorer
from harness.explorer.summarizer import Summarizer
from harness.explorer.surface_prompts import (
    ATTACKER_SYSTEM_PROMPT,
    EXPLORER_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
)
from harness.grafter.grafter import Grafter
from harness.grafter.surface_router import SurfaceCatalogRouter
from harness.memory.strategic import StrategicMemory
from harness.memory.working import WorkingMemory
from harness.objective_replay.replayer import MVP_GOALS, ObjectiveReplayer
from harness.triage.bandit import SurfaceBandit
from harness.telemetry.langfuse_exporter import LangfuseExporter
from harness.victim.base import VictimAdapter

logger = logging.getLogger("harness.campaign.muzzle_orchestrator")

# Maps surface name strings (as produced by the Explorer) to the step_type recognised by
# the Grafter's discover() method.  Used in run_grafter_tool and cycle grounding context.
_SURFACE_TO_STEP_TYPE: dict[str, str] = {
    "direct_chat": "chat_turn",
    "file_upload": "file_upload",
    "doc_memory": "doc_created",
    "tool_calling": "tool_invoked",
    "memory_state": "memory_write",
    "subagent_spawn": "subagent_invoked",
    "external_api": "external_api_called",
    "tool_schema": "tool_schema_probed",
}


@dataclass
class MuzzleCycleResult:
    cycle: int
    surfaces_found: list[str]
    vessels_grafted: int
    objective_script: ObjectiveScript | None
    judge_results: list
    validation: dict = field(default_factory=dict)
    think_steps: list = field(default_factory=list)


def make_victim_tools(victim: VictimAdapter, session_id: str):
    try:
        from langchain_core.tools import tool
    except Exception:  # pragma: no cover - optional dependency
        def tool(fn):
            return fn

    @tool
    async def send_turn_tool(message: str) -> str:
        """Send one conversational turn to the victim and return its response."""
        try:
            result = await victim.send_turn(session_id, message)
            return str((result or {}).get("response", ""))
        except Exception as exc:
            return f"[INFRA_ERROR] send_turn failed: {exc}"

    @tool
    async def list_docs_tool() -> list:
        """List all documents currently available in the victim session."""
        try:
            return await victim.list_docs(session_id)
        except Exception as exc:
            logger.warning("list_docs_tool failed: %s", exc)
            return []

    @tool
    async def reset_session_tool() -> str:
        """Reset the victim session to a clean state."""
        try:
            await victim.reset_session(session_id)
            return "session reset"
        except Exception as exc:
            return f"reset failed: {exc}"

    @tool
    async def upload_file_tool(filename: str, content: str, content_type: str = "text/plain") -> str:
        """Upload a file to the victim session and return the upload result.
        Only .md, .pdf, and .csv files are supported by the victim."""
        allowed_ext = (".md", ".pdf", ".csv")
        if not any(filename.lower().endswith(ext) for ext in allowed_ext):
            return f"Upload skipped: victim only accepts {', '.join(allowed_ext)} files. Got: {filename}"
        try:
            result = await victim.upload_file(session_id, filename, content.encode("utf-8"), content_type)
            return str(result)
        except Exception as exc:
            return f"Upload failed: {exc}"

    return [send_turn_tool, list_docs_tool, reset_session_tool, upload_file_tool]


def make_orchestration_tools(
    grafter: "Grafter",
    replayer: "ObjectiveReplayer",
    runner: "CampaignRunner",
    surface_router: "SurfaceCatalogRouter | None",
    config: "RunConfig",
):
    """Build deterministic Python tools split by role.

    Returns:
        (orchestrator_tools, attacker_tools) — orchestrator gets planning/grafting tools,
        Attacker SubAgent gets execute_test_spec_tool.
    """
    try:
        from langchain_core.tools import tool
    except Exception:  # pragma: no cover - optional dependency
        def tool(fn):
            return fn

    @tool
    def run_grafter_tool(surfaces_json: str) -> str:
        """Run the Grafter on a JSON array of surface name strings.

        Pass the surfaces discovered by the Explorer as a JSON array of strings, e.g.:
          '["direct_chat", "file_upload", "tool_calling"]'

        Valid surface names: "direct_chat", "file_upload", "doc_memory", "tool_calling",
        "memory_state", "subagent_spawn", "external_api", "tool_schema".

        Each name is mapped to the correct interaction step type internally.
        Returns a ranked VesselCandidate JSON array.
        """
        try:
            raw = json.loads(surfaces_json)
            items = raw if isinstance(raw, list) else [raw]
            if items and isinstance(items[0], str):
                # Primary path: list of surface name strings from the Explorer
                traces = []
                for name in items:
                    step_type = _SURFACE_TO_STEP_TYPE.get(name, "chat_turn")
                    traces.append(SummarizedTrace(
                        trace_id=f"auto-{name}",
                        steps=[ExecutionStep(step_type=step_type)],
                        inferred_surfaces=[name],
                    ))
            else:
                # Fallback: list of SummarizedTrace dicts
                traces = [SummarizedTrace(**t) for t in items]
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        all_candidates = []
        for t in traces:
            all_candidates.extend(grafter.discover(t))
        ranked = grafter.rank(all_candidates)
        return json.dumps([c.model_dump() for c in ranked])

    @tool
    def distill_objective_tool(goal_id: str) -> str:
        """Run ObjectiveReplayer for a single goal_id and return ObjectiveScript JSON.

        Valid goal_id values (use exactly one of these):
          "prompt_exfil" — extract the victim's system prompt / operational constraints
          "state_exfil"  — extract the victim's runtime state, memory, or session variables
        """
        goal = next((g for g in MVP_GOALS if g.goal_id == goal_id), None)
        if goal is None:
            return json.dumps({"error": f"unknown goal_id: {goal_id!r}. Valid values: 'prompt_exfil', 'state_exfil'"})
        try:
            script = asyncio.run(
                replayer.run_and_distill(goal, engagement_id=config.engagement_id or None)
            )
            return json.dumps(script.model_dump() if script else {})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @tool
    def build_suite_tool(candidates_json: str, objective_json: str) -> str:
        """Build a TestSpec suite from ranked candidates + objective script.

        - candidates_json: raw JSON string returned by run_grafter_tool
        - objective_json: raw JSON string returned by distill_objective_tool (pass through unchanged)
        Returns a JSON array of TestSpec objects. Pass each element to task("attacker").
        """
        try:
            candidates = [VesselCandidate(**c) for c in json.loads(candidates_json)]
            objective = ObjectiveScript(**json.loads(objective_json)) if objective_json.strip() != "{}" else None
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        chain_active = isinstance(runner.strategy, ChainStrategy)
        suite = grafter.build_suite(
            candidates,
            objective,
            chain_strategy_active=chain_active,
            surface_router=surface_router,
        )
        return json.dumps([s.model_dump() for s in suite])

    @tool
    def execute_test_spec_tool(spec_json: str) -> str:
        """Execute a single TestSpec against the victim and return JudgeResult JSON.

        Pass the full JSON of one TestSpec element from build_suite_tool output.
        """
        try:
            spec = TestSpec(**json.loads(spec_json))
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        try:
            result = asyncio.run(runner.run_one(spec))
            return json.dumps(result.model_dump() if result else {})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    orchestrator_tools = [run_grafter_tool, distill_objective_tool, build_suite_tool]
    attacker_tools = [execute_test_spec_tool]
    return orchestrator_tools, attacker_tools


def make_memory_tools(wm: "WorkingMemory", sm: "StrategicMemory"):
    """Build 4 memory tools for the Orchestrator SubAgent."""
    try:
        from langchain_core.tools import tool
    except Exception:  # pragma: no cover - optional dependency
        def tool(fn):
            return fn

    @tool
    def read_working_memory() -> str:
        """Read the current cycle's working memory scratchpad."""
        return json.dumps({
            "cycle": wm.cycle,
            "surfaces_discovered": wm.surfaces_discovered,
            "vessels_tried": len(wm.vessels_tried),
            "hypothesis": wm.current_hypothesis,
            "notes": wm.notes[-5:],
        })

    @tool
    def write_working_note(note: str) -> str:
        """Add an observation note to the current cycle's working memory."""
        wm.add_note(note)
        return f"Note recorded ({len(wm.notes)} total)"

    @tool
    def set_hypothesis(hypothesis: str) -> str:
        """Record your current hypothesis about the victim's vulnerabilities."""
        wm.set_hypothesis(hypothesis)
        return f"Hypothesis set: {hypothesis[:100]}"

    @tool
    def read_strategic_memory() -> str:
        """Read cross-cycle strategic intelligence (win rates, patterns, winning turns)."""
        surface_info = {
            s: {"win_rate": sm.surface_win_rate(s), "attempts": st.attempts, "successes": st.successes}
            for s, st in sm.surface_stats.items()
        }
        technique_info = {
            t: {"effectiveness": sm.technique_effectiveness(t), "attempts": st.attempts}
            for t, st in sm.technique_stats.items()
        }
        return json.dumps({
            "surface_stats": surface_info,
            "technique_stats": technique_info,
            "behavioral_patterns": sm.behavioral_patterns[-5:],
            "cycle_summaries": sm.cycle_summaries[-3:],
        })

    return [read_working_memory, write_working_note, set_hypothesis, read_strategic_memory]


def _wrap_tool_with_counter(fn: Any, agent_name: str, counter: "ToolCallCounter"):
    """Wrap a tool function to count invocations and enforce budget."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        status = counter.increment(agent_name)
        if status == ToolBudgetStatus.EXHAUSTED:
            return counter.warning_message(agent_name)
        result = fn(*args, **kwargs)
        # Handle both sync and async tool functions
        if hasattr(result, "__await__"):
            result = await result
        if status == ToolBudgetStatus.WARNING:
            warning = counter.warning_message(agent_name)
            return f"{result}\n\n⚠️ {warning}"
        return result

    return wrapper


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
        self.surface_router = self._load_surface_router(config)

        # Budget subsystem
        self.budget_tracker = BudgetTracker(
            explorer_ceiling=config.explorer_token_ceiling,
            attacker_ceiling=config.attacker_token_ceiling,
            campaign_budget=config.campaign_token_budget,
        )
        self.tool_counter = ToolCallCounter(limits={
            "explorer": config.explorer_tool_limit,
            "attacker": config.attacker_tool_limit,
        })

        # Memory subsystem
        engagement = config.engagement_id or ""
        self.strategic_memory = StrategicMemory.load(engagement) if engagement else StrategicMemory()
        self.working_memory = WorkingMemory(cycle=0)

        # Langfuse observability (optional — None when not configured)
        self._langfuse = LangfuseExporter.from_env()

        # Bandit triage
        self.bandit = SurfaceBandit.load(engagement) if engagement else SurfaceBandit()

        # Think log for structured reasoning capture
        self._think_log = ThinkLog(cycle=0)

        # Wire memory/bandit into grafter scoring
        self.grafter.set_strategic_memory(self.strategic_memory)
        self.grafter.set_bandit(self.bandit)

        self._orchestrator = self._build_orchestrator()

    def _load_surface_router(self, config: RunConfig) -> SurfaceCatalogRouter:
        router = SurfaceCatalogRouter()
        for path_str, surface_str in config.surface_catalog_map.items():
            try:
                surface = AttackSurface(surface_str)
                _, specs = load_test_specs(path_str)
                router.register(surface, specs)
            except Exception as exc:
                logger.debug("Skipping catalog %s: %s", path_str, exc)
        return router

    def _make_llm(self, model_str: str):
        """Construct a LangChain chat model for the given model string.

        For OpenRouter models (containing '/'), creates ChatOpenAI with
        OpenRouter base_url. For provider-prefixed models (e.g. 'anthropic:...'),
        uses init_chat_model directly.

        When Langfuse is configured, a CallbackHandler is attached automatically.
        """
        api_key = os.getenv(self.config.attacker_api_key_env, "").strip()
        callbacks: list = []
        if self._langfuse:
            handler = self._langfuse.get_langchain_handler(
                session_id=self.config.engagement_id or None,
            )
            if handler:
                callbacks.append(handler)

        if "/" in model_str and not model_str.startswith(("openai:", "anthropic:")):
            from langchain_openai import ChatOpenAI  # pragma: no cover - optional dependency
            return ChatOpenAI(
                model=model_str,
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                max_tokens=4096,
                callbacks=callbacks or None,
            )

        from langchain.chat_models import init_chat_model  # pragma: no cover - optional dependency
        llm = init_chat_model(model_str)
        if callbacks:
            llm = llm.with_config({"callbacks": callbacks})
        return llm

    def _build_orchestrator(self):
        if not self.config.engagement_id:
            return None

        api_key = os.getenv(self.config.attacker_api_key_env, "").strip()
        if not api_key:
            logger.warning("No API key found — skipping agentic orchestrator, using scripted mode.")
            return None

        try:
            from deepagents import SubAgent, create_deep_agent  # pragma: no cover - optional dependency
        except Exception as exc:
            logger.warning("deepagents import failed, using scripted mode: %s", exc)
            return None

        # Build a temporary session_id for tool construction (Explorer reuses its own per task)
        session_id = f"orch-{self.config.engagement_id}"
        victim_tools = make_victim_tools(self.victim, session_id)

        analyst_key = os.getenv(self.config.analyst_api_key_env, "").strip() or api_key
        replayer = ObjectiveReplayer(
            victim=self.victim,
            openrouter_api_key=analyst_key,
            model=self.config.analyst_model,
        )
        # orch_tools: planning/grafting only (orchestrator)
        # exec_tools: execute_test_spec_tool (Attacker SubAgent only)
        orch_tools, exec_tools = make_orchestration_tools(
            grafter=self.grafter,
            replayer=replayer,
            runner=self.runner,
            surface_router=self.surface_router,
            config=self.config,
        )
        mem_tools = make_memory_tools(self.working_memory, self.strategic_memory)

        # Think tool for structured reasoning — pass callables to avoid stale closure
        think_tool = make_think_tool(
            lambda: self._think_log,
            get_cycle=lambda: self._think_log.cycle,
            use_stream_writer=True,
        )

        llm = self._make_llm(self.config.attacker_model)

        return create_deep_agent(
            model=llm,
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
            # Orchestrator: think + planning/grafting + memory — NO filesystem, NO execute_test_spec
            tools=[think_tool] + orch_tools + mem_tools,
            interrupt_on={
                "novel_surface": True,
                "partial_ambiguous": True,
                "agent_confused": True,
                "high_confidence_hit": True,
                "catalog_enrichment": True,
            },
            middleware=[],
            subagents=[
                SubAgent(
                    name="explorer",
                    description="Runs benign tasks against the victim to map attack surfaces across all 7 surfaces",
                    system_prompt=EXPLORER_SYSTEM_PROMPT,
                    tools=victim_tools,
                    model=llm,
                ),
                SubAgent(
                    name="attacker",
                    description="Executes adversarial TestSpec payloads against the victim",
                    system_prompt=ATTACKER_SYSTEM_PROMPT,
                    # Attacker: victim tools + execute_test_spec_tool + memory
                    tools=victim_tools + exec_tools + mem_tools,
                    model=llm,
                ),
            ],
        )

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

        # ------------------------------------------------------------------
        # Agentic path: delegate to CompiledStateGraph when available
        # ------------------------------------------------------------------
        if self._orchestrator is not None:
            return await self._run_cycle_agentic(
                exploration_tasks, cycle, on_result=on_result, progress_fn=_progress
            )

        # ------------------------------------------------------------------
        # Scripted fallback: direct Python (unchanged from TRD-16)
        # ------------------------------------------------------------------
        return await self._run_cycle_scripted(
            exploration_tasks, cycle, on_result=on_result, progress_fn=_progress
        )

    def _process_stream_chunk(
        self,
        chunk: dict,
        agent_label: str,
        cycle: int,
    ) -> None:
        """Extract token usage from a stream chunk and record it in the budget tracker."""
        # Path 1: top-level metadata.token_usage
        meta = chunk.get("metadata", {})
        if isinstance(meta, dict) and "token_usage" in meta:
            tu = meta["token_usage"]
            self.budget_tracker.record(
                agent_label,
                tu.get("input_tokens", 0),
                tu.get("output_tokens", 0),
                tu.get("est_cost", 0.0),
            )
            return

        # Path 2: usage_metadata on AIMessage objects in chunk["messages"]
        messages = chunk.get("messages", [])
        if not isinstance(messages, list):
            return
        for msg in messages:
            usage = getattr(msg, "usage_metadata", None)
            if usage and isinstance(usage, dict):
                self.budget_tracker.record(
                    agent_label,
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                    usage.get("total_cost", 0.0),
                )

    async def _run_cycle_agentic(
        self,
        exploration_tasks: list[ExplorationTask],
        cycle: int,
        on_result: Optional[Callable[[Any], None]],
        progress_fn: Callable[[str], None],
    ) -> MuzzleCycleResult:
        # Reset think_log for this cycle
        self._think_log = ThinkLog(cycle=cycle)

        progress_fn(f"[cycle {cycle}] Agentic mode: streaming Orchestrator SubAgent...")
        tasks_json = json.dumps([t.model_dump() for t in exploration_tasks])

        # Surfaces already known across prior cycles (from strategic memory)
        surfaces_already_known = sorted(self.strategic_memory.surface_stats.keys())

        context_block = (
            f"cycle={cycle}\n"
            f"surfaces_already_known={surfaces_already_known}\n"
            f"valid_surface_names={sorted(_SURFACE_TO_STEP_TYPE)}\n"
            f"objective_scope=[\"prompt_exfil\", \"state_exfil\"]\n"
            f"bandit_scores={json.dumps(self.bandit.scores())}\n"
            f"exploration_tasks={tasks_json}\n"
        )

        input_dict = {
            "messages": [
                {
                    "role": "user",
                    "content": context_block,
                }
            ],
            "cycle": cycle,
            "engagement_id": self.config.engagement_id,
            "budget_state": self.budget_tracker.to_telemetry_dict(),
            "bandit_scores": self.bandit.scores(),
            "strategic_memory": json.dumps({
                s: self.strategic_memory.surface_win_rate(s)
                for s in self.strategic_memory.surface_stats
            }),
        }
        last_chunk: dict = {}
        last_orchestrator_content: str = ""
        active_subagent: str | None = None

        async for namespace, chunk in self._orchestrator.astream(  # type: ignore[union-attr]
            input_dict,
            stream_mode="updates",
            subgraphs=True,
        ):
            # Determine agent label from namespace tuple
            if not namespace:
                agent_label = "orchestrator"
            else:
                ns_str = str(namespace)
                if "explorer" in ns_str:
                    agent_label = "explorer"
                elif "attacker" in ns_str:
                    agent_label = "attacker"
                else:
                    agent_label = "orchestrator"

            # Track SubAgent transitions
            if agent_label != "orchestrator" and agent_label != active_subagent:
                if active_subagent is not None:
                    progress_fn(f"[cycle {cycle}] SubAgent '{active_subagent}' ended")
                active_subagent = agent_label
                progress_fn(f"[cycle {cycle}] SubAgent '{agent_label}' started")

            # stream_mode="updates" yields {node_name: state_delta} — unwrap one level
            # Values can be LangGraph Overwrite/Annotated objects, not plain lists — guard all extends
            chunk_messages: list = []
            if isinstance(chunk, dict):
                for node_val in chunk.values():
                    if isinstance(node_val, dict):
                        msgs = node_val.get("messages")
                        if isinstance(msgs, list):
                            chunk_messages.extend(msgs)
                # Also check flat structure (some deepagents versions)
                msgs = chunk.get("messages")
                if isinstance(msgs, list):
                    chunk_messages.extend(msgs)

            # Capture orchestrator's final text response as it streams past
            if not namespace:
                for msg in chunk_messages:
                    _content = getattr(msg, "content", None)
                    _tool_calls = getattr(msg, "tool_calls", None)
                    # Handle Anthropic-style content blocks (list of dicts)
                    if isinstance(_content, list):
                        _content = " ".join(
                            b.get("text", "") for b in _content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    if _content and isinstance(_content, str) and not _tool_calls:
                        last_orchestrator_content = _content

            # Emit intermediate step details
            for msg in chunk_messages:
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                        args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                        args_str = str(args)[:120] + ("..." if len(str(args)) > 120 else "")
                        progress_fn(f"  [{agent_label}] → tool_call: {name}({args_str})")
                if getattr(msg, "type", None) == "tool" or type(msg).__name__ == "ToolMessage":
                    tool_name = getattr(msg, "name", "?")
                    content = str(getattr(msg, "content", ""))[:160]
                    progress_fn(f"  [{agent_label}] ← tool_result: {tool_name}: {content}")
                content = getattr(msg, "content", None)
                if isinstance(content, list):
                    content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                if content and isinstance(content, str) and not tool_calls:
                    snippet = content.strip()[:200].replace("\n", " ")
                    progress_fn(f"  [{agent_label}] 💬 {snippet}")

            # Process token usage from chunk
            if isinstance(chunk, dict):
                self._process_stream_chunk(chunk, agent_label, cycle)
                last_chunk = chunk
                logger.debug("[stream] namespace=%s chunk_keys=%s msgs=%d",
                             namespace, list(chunk.keys())[:5], len(chunk_messages))

            # Mid-stream budget enforcement
            if self.budget_tracker.is_campaign_exhausted():
                progress_fn(f"[cycle {cycle}] Budget EXHAUSTED mid-stream — breaking")
                break

        # Close last subagent
        if active_subagent is not None:
            progress_fn(f"[cycle {cycle}] SubAgent '{active_subagent}' ended")

        # Use the last orchestrator AI message captured during streaming
        last_msg = last_orchestrator_content

        parsed_output = self._parse_agentic_output(last_msg, cycle)
        surfaces_found = parsed_output.surfaces_found
        vessels_grafted = parsed_output.specs_executed

        progress_fn(
            f"[cycle {cycle}] Agentic cycle done: surfaces={surfaces_found}, "
            f"specs_executed={vessels_grafted}, think_steps={len(self._think_log.steps)}"
        )

        validator = AgentValidator()
        report = validator.validate(
            cycle=int(cycle),
            surfaces_explored=surfaces_found,
            surface_stats={
                s: {"attempts": st.attempts, "successes": st.successes}
                for s, st in self.strategic_memory.surface_stats.items()
            },
            total_attempts=sum(st.attempts for st in self.strategic_memory.surface_stats.values()),
            total_successes=sum(st.successes for st in self.strategic_memory.surface_stats.values()),
            surfaces_discovered=len(surfaces_found),
            specs_count=vessels_grafted,
            think_step_count=len(self._think_log.steps),
        )

        return MuzzleCycleResult(
            cycle=int(cycle),
            surfaces_found=surfaces_found,
            vessels_grafted=vessels_grafted,
            objective_script=None,
            judge_results=[],
            validation=report.to_dict(),
            think_steps=self._think_log.to_telemetry_dicts(),
        )

    def _parse_agentic_output(self, raw: str, cycle: int) -> AgenticCycleOutput:
        """Parse LLM output into AgenticCycleOutput with progressive fallbacks."""
        # Strip markdown code fences if present
        stripped = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if fence_match:
            stripped = fence_match.group(1)

        # Path 1: strict Pydantic parse
        if stripped.startswith("{"):
            try:
                result = AgenticCycleOutput.model_validate_json(stripped)
                logger.info("parse_path=1 surfaces=%d specs=%d", len(result.surfaces_found), result.specs_executed)
                return result
            except Exception:
                pass

            # Path 2: json.loads + model_validate (handles partial/extra keys)
            try:
                data = json.loads(stripped)
                result = AgenticCycleOutput.model_validate(data)
                logger.info("parse_path=2 surfaces=%d specs=%d", len(result.surfaces_found), result.specs_executed)
                return result
            except Exception:
                pass

        # Path 3: output is unparseable — return empty, signal the failure
        logger.warning("parse_path=3 cycle=%d raw_len=%d raw_snippet=%r", cycle, len(raw), raw[:200])
        return AgenticCycleOutput(
            cycle=cycle,
            surfaces_found=[],
            specs_executed=0,
            error="unparseable_output" if raw.strip() else "empty_output",
        )

    async def _run_cycle_scripted(
        self,
        exploration_tasks: list[ExplorationTask],
        cycle: int,
        on_result: Optional[Callable[[Any], None]],
        progress_fn: Callable[[str], None],
    ) -> MuzzleCycleResult:
        """Procedural cycle with budget, memory, and bandit integration."""
        # Reset per-cycle state
        self.budget_tracker.reset_cycle()
        self.tool_counter.reset()
        self.working_memory = self.working_memory.reset(cycle)

        # Bandit: select priority surfaces
        bandit_priorities = self.bandit.select(k=5) if self.bandit.arms else None

        # Budget check before Explorer
        explorer_budget = self.budget_tracker.check("explorer")
        if explorer_budget == BudgetStatus.EXHAUSTED:
            progress_fn(f"[cycle {cycle}] Explorer budget EXHAUSTED — skipping exploration")
            return MuzzleCycleResult(cycle=cycle, surfaces_found=[], vessels_grafted=0,
                                     objective_script=None, judge_results=[])

        progress_fn(f"[cycle {cycle}] Explorer: running {len(exploration_tasks)} tasks...")
        explorer = Explorer(self.victim, timeout_seconds=self.config.timeout_seconds)
        traces = await explorer.run_all(
            exploration_tasks,
            engagement_id=self.config.engagement_id or None,
            strategic_memory=self.strategic_memory,
            bandit_priorities=bandit_priorities,
        )
        summarized = [self.summarizer.summarize(t) for t in traces]
        surfaces_seen = sorted({s for st in summarized for s in st.inferred_surfaces})
        progress_fn(f"[cycle {cycle}] Explorer done: {len(traces)} traces, surfaces={surfaces_seen}")

        # Record surfaces in working memory
        for s in surfaces_seen:
            self.working_memory.record_surface(s)

        all_candidates: list[VesselCandidate] = []
        for st in summarized:
            all_candidates.extend(self.grafter.discover(st))
        ranked = self.grafter.rank(all_candidates)
        progress_fn(
            f"[cycle {cycle}] Grafter: {len(ranked)} ranked candidates — "
            f"{[c.vessel_kind.value for c in ranked]}"
        )

        # Budget check before ObjectiveReplayer
        attacker_budget = self.budget_tracker.check("attacker")
        api_key = os.getenv(self.config.analyst_api_key_env, "").strip()
        replayer = ObjectiveReplayer(
            victim=self.victim,
            openrouter_api_key=api_key,
            model=self.config.analyst_model,
        )
        objective_script: ObjectiveScript | None = None
        if attacker_budget != BudgetStatus.EXHAUSTED:
            for goal in MVP_GOALS:
                if goal.goal_id in self.config.objective_goals:
                    progress_fn(f"[cycle {cycle}] ObjectiveReplayer: eliciting goal '{goal.goal_id}'...")
                    objective_script = await replayer.run_and_distill(
                        goal, engagement_id=self.config.engagement_id or None
                    )
                    if objective_script and objective_script.imperative:
                        progress_fn(
                            f"[cycle {cycle}] ObjectiveReplayer: "
                            f"imperative='{objective_script.imperative[:80]}'"
                        )
                        break

        chain_active = isinstance(self.runner.strategy, ChainStrategy)
        suite = (
            self.grafter.build_suite(
                ranked,
                objective_script,
                chain_strategy_active=chain_active,
                surface_router=self.surface_router,
            )
            if objective_script and ranked
            else []
        )
        progress_fn(f"[cycle {cycle}] Grafter suite: {len(suite)} TestSpecs grafted")

        self.runner._cycle = int(cycle)
        results = []
        for spec in suite:
            # Budget gate per spec
            if self.budget_tracker.check("attacker") == BudgetStatus.EXHAUSTED:
                progress_fn(f"[cycle {cycle}] Attacker budget EXHAUSTED — stopping test execution")
                break
            if self.tool_counter.check("attacker") == ToolBudgetStatus.EXHAUSTED:
                progress_fn(f"[cycle {cycle}] Attacker tool budget EXHAUSTED — stopping test execution")
                break

            result = await self.runner.run_one(spec)
            self.tool_counter.increment("attacker")
            if result:
                results.append(result)
                if on_result:
                    on_result(result)
                # Update bandit and strategic memory
                self.bandit.update_from_result(result, spec, cycle)
                self.strategic_memory.update_from_result(result, spec, cycle)
                self.working_memory.record_vessel_outcome(
                    vessel_kind=spec.vessels[0].kind.value if spec.vessels else "unknown",
                    technique=spec.technique_family,
                    status=result.status.value if hasattr(result.status, "value") else str(result.status),
                    oracle_codes=[oc.value if hasattr(oc, "value") else str(oc) for oc in (result.hard_flags or {})],
                    turn_count=result.turn_count,
                )

        # End-of-cycle: persist memory and bandit state
        self.strategic_memory.ingest_working_memory(self.working_memory)
        engagement = self.config.engagement_id
        if engagement:
            self.strategic_memory.save(engagement)
            self.bandit.save(engagement)

        surfaces = sorted({c.vessel_kind.value for c in ranked})

        validator = AgentValidator()
        report = validator.validate(
            cycle=int(cycle),
            surfaces_explored=surfaces,
            surface_stats={
                s: {"attempts": st.attempts, "successes": st.successes}
                for s, st in self.strategic_memory.surface_stats.items()
            },
            total_attempts=sum(st.attempts for st in self.strategic_memory.surface_stats.values()),
            total_successes=sum(st.successes for st in self.strategic_memory.surface_stats.values()),
            surfaces_discovered=len(surfaces_seen),
            specs_count=len(suite),
            think_step_count=0,
        )

        return MuzzleCycleResult(
            cycle=int(cycle),
            surfaces_found=surfaces,
            vessels_grafted=len(suite),
            objective_script=objective_script,
            judge_results=results,
            validation=report.to_dict(),
            think_steps=[],
        )

    async def run(
        self,
        exploration_tasks: list[ExplorationTask],
        on_result: Optional[Callable[[Any], None]] = None,
        progress_fn: Optional[Callable[[str], None]] = None,
    ) -> list[MuzzleCycleResult]:
        all_results: list[MuzzleCycleResult] = []
        seen_surfaces: set[str] = set()

        def _progress(msg: str) -> None:
            if progress_fn:
                progress_fn(msg)

        for cycle in range(max(1, int(self.config.max_muzzle_cycles))):
            # Campaign budget gate
            if self.budget_tracker.is_campaign_exhausted():
                _progress(f"[run] Campaign token budget EXHAUSTED after cycle {cycle - 1} — stopping")
                break

            result = await self.run_cycle(exploration_tasks, cycle=cycle, on_result=on_result, progress_fn=progress_fn)
            all_results.append(result)

            _progress(
                f"[run] Cycle {cycle} budget summary: "
                f"{self.budget_tracker.to_telemetry_dict()}"
            )

            new_surfaces = set(result.surfaces_found) - seen_surfaces
            seen_surfaces.update(result.surfaces_found)
            # Continue if: new surfaces found OR any attack succeeded this cycle
            has_hits = any(
                r.status.value in ("Success", "Injection")
                for r in (result.judge_results or [])
            )
            logger.info(
                "cycle=%d cumulative_surfaces=%s new_surfaces=%s has_hits=%s -> %s",
                cycle, sorted(seen_surfaces), sorted(new_surfaces), has_hits,
                "stop" if (cycle > 0 and not new_surfaces and not has_hits) else "continue",
            )
            if cycle > 0 and not new_surfaces and not has_hits:
                break

        # Flush Langfuse before returning so buffered events aren't lost
        if self._langfuse:
            self._langfuse.flush()

        return all_results
