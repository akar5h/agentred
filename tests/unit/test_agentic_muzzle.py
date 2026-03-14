"""Unit tests for TRD-17 agentic MUZZLE extensions."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from harness.core.enums import AttackSurface, VesselKind
from harness.core.schemas import (
    ExecutionStep,
    ExplorationTask,
    ExplorationTrace,
    RunConfig,
    SummarizedTrace,
    TraceStep,
)
from harness.explorer.explorer import Explorer
from harness.explorer.summarizer import Summarizer
from harness.grafter.grafter import Grafter


# ---------------------------------------------------------------------------
# Phase 1 - enums
# ---------------------------------------------------------------------------


def test_vessel_kind_new_values():
    assert VesselKind.SUBAGENT_OUTPUT.value == "subagent_output"
    assert VesselKind.TOOL_SCHEMA.value == "tool_schema"


def test_attack_surface_new_values():
    assert AttackSurface.SUBAGENT_INJECTION.value == "subagent_injection"
    assert AttackSurface.EXTERNAL_API_EXPLOITATION.value == "external_api_exploitation"
    assert AttackSurface.TOOL_SCHEMA_ENUMERATION.value == "tool_schema_enumeration"


# ---------------------------------------------------------------------------
# Phase 2 - TraceStep debug fields
# ---------------------------------------------------------------------------


def test_trace_step_debug_fields_default():
    step = TraceStep(turn_index=0, message_sent="hi", response="ok")
    assert step.debug_before == {}
    assert step.debug_after == {}


def test_trace_step_debug_fields_set():
    step = TraceStep(
        turn_index=0,
        message_sent="hi",
        response="ok",
        debug_before={"messages": [{"role": "user", "content": "hi"}]},
        debug_after={"subagents": [{"id": "sa1"}]},
    )
    assert step.debug_before["messages"][0]["role"] == "user"
    assert step.debug_after["subagents"][0]["id"] == "sa1"


@pytest.mark.asyncio
async def test_explorer_populates_debug_snapshots():
    victim = MagicMock()
    victim.reset_session = AsyncMock()
    victim.list_docs = AsyncMock(return_value=[])
    victim.send_turn = AsyncMock(return_value={"response": "ok"})
    victim.get_debug_state = AsyncMock(side_effect=[{"subagents": []}, {"subagents": [{"id": "sa1"}]}])
    explorer = Explorer(victim=victim, timeout_seconds=5.0)

    trace = await explorer.run_task(
        ExplorationTask(task_id="debug", description="d", turns=["hello"])
    )
    assert trace.steps[0].debug_before == {"subagents": []}
    assert trace.steps[0].debug_after == {"subagents": [{"id": "sa1"}]}


# ---------------------------------------------------------------------------
# Phase 3 - surface prompts
# ---------------------------------------------------------------------------


def test_surface_prompts_cover_all_7_surfaces():
    from harness.explorer.surface_prompts import EXPLORER_SYSTEM_PROMPT

    for surface in [
        "direct_chat",
        "file_upload",
        "doc_memory",
        "tool_calling",
        "subagent_spawn",
        "external_api",
        "memory_state",
    ]:
        assert surface in EXPLORER_SYSTEM_PROMPT, f"Missing surface: {surface}"


def test_attacker_prompt_has_execute_tool():
    from harness.explorer.surface_prompts import ATTACKER_SYSTEM_PROMPT

    assert "execute_test_spec_tool" in ATTACKER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Phase 8 - Summarizer new step types
# ---------------------------------------------------------------------------


def _make_trace(step: TraceStep) -> ExplorationTrace:
    return ExplorationTrace(task_id="t1", session_id="s1", steps=[step])


def test_summarizer_subagent_invoked():
    summarizer = Summarizer()
    step = TraceStep(
        turn_index=0,
        message_sent="delegate",
        response="done",
        debug_before={"subagents": []},
        debug_after={"subagents": [{"id": "sa1"}]},
    )
    result = summarizer.summarize(_make_trace(step))
    assert result.steps[0].step_type == "subagent_invoked"
    assert "subagent_spawn" in result.inferred_surfaces


def test_summarizer_external_api_called():
    summarizer = Summarizer()
    step = TraceStep(
        turn_index=0,
        message_sent="fetch",
        response="got it",
        debug_before={"external_calls": []},
        debug_after={"external_calls": [{"url": "https://example.com"}]},
    )
    result = summarizer.summarize(_make_trace(step))
    assert result.steps[0].step_type == "external_api_called"
    assert "external_api" in result.inferred_surfaces


def test_summarizer_tool_schema_probed():
    summarizer = Summarizer()
    step = TraceStep(
        turn_index=0,
        message_sent="list tools",
        response="here are my tools",
        debug_before={"tool_schemas": []},
        debug_after={"tool_schemas": [{"name": "search"}]},
    )
    result = summarizer.summarize(_make_trace(step))
    assert result.steps[0].step_type == "tool_schema_probed"
    assert "tool_schema" in result.inferred_surfaces


def test_summarizer_no_debug_state_no_crash():
    """Steps without debug_before/debug_after should not crash."""
    summarizer = Summarizer()
    step = TraceStep(turn_index=0, message_sent="hi", response="hello")
    result = summarizer.summarize(_make_trace(step))
    assert result.steps[0].step_type in {
        "chat_turn", "doc_created", "doc_read_hint", "state_change",
        "tool_invoked", "memory_write", "file_upload",
        "subagent_invoked", "external_api_called", "tool_schema_probed",
    }


# ---------------------------------------------------------------------------
# Phase 9 - Grafter new candidates
# ---------------------------------------------------------------------------


def test_grafter_subagent_invoked_candidate():
    grafter = Grafter(top_k=5)
    trace = SummarizedTrace(
        trace_id="t1",
        steps=[ExecutionStep(step_type="subagent_invoked", turn_index=0)],
    )
    candidates = grafter.discover(trace)
    sa = [c for c in candidates if c.vessel_kind == VesselKind.SUBAGENT_OUTPUT]
    assert len(sa) == 1
    assert sa[0].saliency_score == 0.9
    assert grafter._candidate_attack_surface(sa[0]) == AttackSurface.SUBAGENT_INJECTION


def test_grafter_tool_schema_candidate():
    grafter = Grafter(top_k=5)
    trace = SummarizedTrace(
        trace_id="t2",
        steps=[ExecutionStep(step_type="tool_schema_probed", turn_index=0)],
    )
    candidates = grafter.discover(trace)
    ts = [c for c in candidates if c.vessel_kind == VesselKind.TOOL_SCHEMA]
    assert len(ts) == 1
    assert ts[0].saliency_score == 0.75
    assert grafter._candidate_attack_surface(ts[0]) == AttackSurface.TOOL_SCHEMA_ENUMERATION


def test_grafter_external_api_candidate():
    grafter = Grafter(top_k=5)
    trace = SummarizedTrace(
        trace_id="t3",
        steps=[ExecutionStep(step_type="external_api_called", turn_index=0)],
    )
    candidates = grafter.discover(trace)
    ea = [c for c in candidates if c.vessel_kind == VesselKind.TOOL_OUTPUT]
    assert len(ea) >= 1
    ea_cand = [c for c in ea if abs(c.saliency_score - 0.85) < 0.01]
    assert len(ea_cand) == 1


# ---------------------------------------------------------------------------
# Phase 6 - MuzzleOrchestrator dispatches correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_muzzle_orchestrator_scripted_fallback():
    from harness.campaign.muzzle_orchestrator import MuzzleCycleResult, MuzzleOrchestrator

    config = RunConfig(catalog_path="", engagement_id="")
    victim = MagicMock()
    runner = MagicMock()
    runner.strategy = MagicMock()

    mo = MuzzleOrchestrator(victim=victim, runner=runner, config=config)
    assert mo._orchestrator is None  # no engagement_id

    with patch.object(mo, "_run_cycle_scripted", new_callable=AsyncMock) as mocked:
        mocked.return_value = MuzzleCycleResult(
            cycle=0,
            surfaces_found=["direct_chat"],
            vessels_grafted=1,
            objective_script=None,
            judge_results=[],
        )
        result = await mo.run_cycle([], cycle=0)
    assert result.surfaces_found == ["direct_chat"]
    mocked.assert_called_once()
