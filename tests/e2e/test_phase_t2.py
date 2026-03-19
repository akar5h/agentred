"""Phase T-2 e2e: live HR AI adaptation tests.

Requires HR AI running at HARNESS_BASE_URL (default localhost:8000).
Think-step test also requires deepagents + API key (agentic path).
"""
from __future__ import annotations

import logging

import pytest

from harness.core.exceptions import InfraError

pytestmark = [pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# 1. Think steps captured on agentic path
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="Requires deepagents + API key (agentic path)", strict=False)
async def test_think_steps_captured_agentic(orchestrator, exploration_tasks) -> None:
    orch, cfg, tmp_path = orchestrator
    cfg.max_muzzle_cycles = 1
    cfg.timeout_seconds = 300.0
    results = await orch.run(exploration_tasks)
    assert len(results) >= 1
    # Think steps are only populated on the agentic path
    assert results[0].think_steps, "Expected non-empty think_steps on agentic path"


# ---------------------------------------------------------------------------
# 2. Explorer adaptation with live HR AI
# ---------------------------------------------------------------------------

async def test_explorer_adaptation_live(orchestrator, exploration_tasks, caplog) -> None:
    orch, cfg, tmp_path = orchestrator
    cfg.max_muzzle_cycles = 3
    cfg.timeout_seconds = 300.0
    try:
        with caplog.at_level(logging.INFO, logger="harness.campaign.muzzle_orchestrator"):
            results = await orch.run(exploration_tasks)
    except InfraError as exc:
        pytest.skip(f"HR AI infra error (timeout/connection): {exc}")

    assert len(results) >= 1, "Expected at least 1 cycle result"

    # Verify the convergence decision log line fired (emitted after every cycle)
    convergence_logs = [
        r for r in caplog.records
        if "cycle=" in r.message and "cumulative_surfaces" in r.message
    ]
    assert convergence_logs, "Expected convergence decision log lines"

    # If convergence stopped the loop early, that itself proves adaptation worked
    if len(results) < 3:
        last_log = convergence_logs[-1].message
        assert "stop" in last_log, f"Loop ended early but last log doesn't say 'stop': {last_log}"

    # Strategic memory should have been persisted
    strategic_path = tmp_path / "reports" / cfg.engagement_id / "memory" / "strategic.json"
    assert strategic_path.exists(), "strategic.json not written after live run"
