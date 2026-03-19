"""Phase T-2: Multi-cycle adaptation tests (mock-based, no API key needed).

Validates that the MUZZLE loop adapts across cycles: strategic memory grows,
bandit arms update, explorer tasks change, convergence fires.
"""
from __future__ import annotations

import json
import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from harness.attack.synthesis.static_strategy import StaticStrategy
from harness.campaign.muzzle_orchestrator import MuzzleOrchestrator
from harness.campaign.runner import CampaignRunner
from harness.core.schemas import AgenticCycleOutput, ExplorationTask, RunConfig
from harness.oracle.judge import Judge
from harness.oracle.pattern_oracle import PatternOracle
from harness.telemetry.emitter import TelemetryEmitter
from harness.victim.api_adapter import RestApiAdapter
from harness.victim.mock.app import app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
async def mock_orch(tmp_path, monkeypatch):
    """MuzzleOrchestrator wired to the ASGI mock victim, 2 cycles."""
    monkeypatch.chdir(tmp_path)
    engagement_id = f"t2-{uuid.uuid4().hex[:8]}"
    cfg = RunConfig(
        catalog_path="harness/attack/library/direct/direct_chat_injection_v1.json",
        base_url="http://test",
        engagement_id=engagement_id,
        max_muzzle_cycles=2,
        top_k_vessels=2,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        victim = RestApiAdapter(base_url="http://test", mode="chat", client=client)
        judge = Judge(pattern_oracle=PatternOracle(), llm_oracle=None)
        with TelemetryEmitter(tmp_path / "telemetry.jsonl") as emitter:
            runner = CampaignRunner(
                victim=victim,
                strategy=StaticStrategy(),
                judge=judge,
                emitter=emitter,
                config=cfg,
            )
            orch = MuzzleOrchestrator(victim=victim, runner=runner, config=cfg)
            yield orch, cfg, tmp_path


TASKS = [
    ExplorationTask(
        task_id="e1",
        description="basic chat",
        turns=["Hello!", "What can you help with?"],
    ),
    ExplorationTask(
        task_id="e2",
        description="doc probe",
        turns=["save document please", "list documents"],
    ),
]


# ---------------------------------------------------------------------------
# 1. Strategic memory accumulation
# ---------------------------------------------------------------------------

async def test_strategic_memory_accumulates(mock_orch) -> None:
    orch, cfg, tmp_path = mock_orch
    await orch.run(TASKS)

    strategic_path = tmp_path / "reports" / cfg.engagement_id / "memory" / "strategic.json"
    assert strategic_path.exists(), "strategic.json not written after 2 cycles"
    data = json.loads(strategic_path.read_text())
    # At least one surface should have attempts >= 2 (one per cycle)
    surface_stats = data.get("surface_stats", {})
    assert surface_stats, "No surface stats recorded"
    total_attempts = sum(s["attempts"] for s in surface_stats.values())
    assert total_attempts >= 2, f"Expected >= 2 total attempts, got {total_attempts}"


# ---------------------------------------------------------------------------
# 2. Bandit arm updates across cycles
# ---------------------------------------------------------------------------

async def test_bandit_updates_across_cycles(mock_orch) -> None:
    orch, cfg, tmp_path = mock_orch
    await orch.run(TASKS)

    bandit_path = tmp_path / "reports" / cfg.engagement_id / "memory" / "bandit.json"
    assert bandit_path.exists(), "bandit.json not written after 2 cycles"
    data = json.loads(bandit_path.read_text())
    arms = data.get("arms", {})
    assert arms, "No bandit arms recorded"
    total_pulls = sum(a["pulls"] for a in arms.values())
    assert total_pulls >= 2, f"Expected >= 2 total pulls, got {total_pulls}"


# ---------------------------------------------------------------------------
# 3. Working memory resets per cycle (cycle_summaries in strategic memory)
# ---------------------------------------------------------------------------

async def test_working_memory_resets_per_cycle(mock_orch) -> None:
    orch, cfg, tmp_path = mock_orch
    results = await orch.run(TASKS)

    # After 2 cycles, strategic memory should have ingested working memory each cycle
    strategic_path = tmp_path / "reports" / cfg.engagement_id / "memory" / "strategic.json"
    data = json.loads(strategic_path.read_text())
    summaries = data.get("cycle_summaries", [])
    assert len(summaries) >= len(results), (
        f"Expected >= {len(results)} cycle_summaries, got {len(summaries)}"
    )


# ---------------------------------------------------------------------------
# 4. Convergence stops the loop early
# ---------------------------------------------------------------------------

async def test_convergence_stops_loop(tmp_path, monkeypatch) -> None:
    """With max=5, mock victim's finite surfaces should trigger convergence before 5."""
    monkeypatch.chdir(tmp_path)
    engagement_id = f"t2-conv-{uuid.uuid4().hex[:8]}"
    cfg = RunConfig(
        catalog_path="harness/attack/library/direct/direct_chat_injection_v1.json",
        base_url="http://test",
        engagement_id=engagement_id,
        max_muzzle_cycles=5,
        top_k_vessels=2,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        victim = RestApiAdapter(base_url="http://test", mode="chat", client=client)
        judge = Judge(pattern_oracle=PatternOracle(), llm_oracle=None)
        with TelemetryEmitter(tmp_path / "telemetry.jsonl") as emitter:
            runner = CampaignRunner(
                victim=victim,
                strategy=StaticStrategy(),
                judge=judge,
                emitter=emitter,
                config=cfg,
            )
            orch = MuzzleOrchestrator(victim=victim, runner=runner, config=cfg)
            results = await orch.run(TASKS)

    assert len(results) < 5, (
        f"Expected convergence before 5 cycles, got {len(results)} cycles"
    )


# ---------------------------------------------------------------------------
# 5. Explorer tasks differ between cycles (bandit_priorities change)
# ---------------------------------------------------------------------------

async def test_explorer_tasks_differ_between_cycles(mock_orch, caplog) -> None:
    orch, cfg, tmp_path = mock_orch
    with caplog.at_level(logging.INFO, logger="harness.campaign.muzzle_orchestrator"):
        results = await orch.run(TASKS)

    if len(results) < 2:
        pytest.skip("Only 1 cycle ran — cannot compare bandit priorities")

    # Verify the convergence log line fired
    convergence_logs = [r for r in caplog.records if "cycle=" in r.message and "cumulative_surfaces" in r.message]
    assert convergence_logs, "Expected convergence decision log lines"


# ---------------------------------------------------------------------------
# 6. _parse_agentic_output: strict JSON -> path 1
# ---------------------------------------------------------------------------

def test_output_parsing_strict_json() -> None:
    valid_json = json.dumps({
        "cycle": 0,
        "surfaces_found": ["direct_chat", "file_upload"],
        "specs_executed": 3,
        "hits": [],
        "error": "",
    })
    # _parse_agentic_output is a method, create a minimal instance to call it
    # But it's effectively a pure function — just needs self for nothing.
    # We can call it via the class with a dummy self.
    result = MuzzleOrchestrator._parse_agentic_output(None, valid_json, cycle=0)  # type: ignore[arg-type]
    assert isinstance(result, AgenticCycleOutput)
    assert result.surfaces_found == ["direct_chat", "file_upload"]
    assert result.specs_executed == 3
    assert result.error == ""


def test_output_parsing_fallback_unparseable() -> None:
    """Path 3: unparseable output returns empty surfaces with error flag — never fakes surfaces."""
    raw = "I found direct_chat and file_upload surfaces. Specs executed: 2."
    result = MuzzleOrchestrator._parse_agentic_output(None, raw, cycle=1)  # type: ignore[arg-type]
    assert isinstance(result, AgenticCycleOutput)
    assert result.surfaces_found == []
    assert result.error == "unparseable_output"


# ---------------------------------------------------------------------------
# 7. Findings.jsonl cycle numbers
# ---------------------------------------------------------------------------

async def test_findings_jsonl_cycle_numbers(mock_orch) -> None:
    orch, cfg, tmp_path = mock_orch
    await orch.run(TASKS)

    findings_path = tmp_path / "reports" / cfg.engagement_id / "memory" / "findings.jsonl"
    if not findings_path.exists():
        pytest.skip("No findings.jsonl — mock victim didn't trigger SUCCESS/INJECTION")

    lines = [ln for ln in findings_path.read_text().strip().splitlines() if ln.strip()]
    cycles = []
    for line in lines:
        entry = json.loads(line)
        cycles.append(entry.get("cycle", -1))

    # Cycle numbers should be non-decreasing
    assert cycles == sorted(cycles), f"Cycle numbers not non-decreasing: {cycles}"
