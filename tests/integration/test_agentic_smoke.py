"""Integration smoke test for TRD-17 agentic MUZZLE cycle.

Requires a running mock victim server:
    uvicorn harness.victim.mock.app:app --port 8001

Run with:
    pytest tests/integration/test_agentic_smoke.py -m integration -x --tb=short
"""
from __future__ import annotations

import pytest
import httpx

MOCK_URL = "http://localhost:8001"


@pytest.mark.integration
def test_mock_victim_health():
    """Confirm mock victim is up before running the smoke test."""
    try:
        resp = httpx.get(f"{MOCK_URL}/health", timeout=5.0)
        assert resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("Mock victim not running at http://localhost:8001")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agentic_muzzle_smoke_scripted():
    """Full scripted MUZZLE cycle against mock victim - debug_state side-channel graceful skip."""
    try:
        resp = httpx.get(f"{MOCK_URL}/health", timeout=3.0)
        if resp.status_code != 200:
            pytest.skip("Mock victim not healthy")
    except Exception:
        pytest.skip("Mock victim not running")

    import tempfile
    from pathlib import Path

    from harness.attack.synthesis.static_strategy import StaticStrategy
    from harness.campaign.muzzle_orchestrator import MuzzleOrchestrator
    from harness.campaign.runner import CampaignRunner
    from harness.core.schemas import ExplorationTask, RunConfig
    from harness.oracle.judge import Judge
    from harness.oracle.pattern_oracle import PatternOracle
    from harness.telemetry.emitter import TelemetryEmitter
    from harness.victim.api_adapter import RestApiAdapter

    victim = RestApiAdapter(MOCK_URL)
    config = RunConfig(
        catalog_path="harness/attack/library/direct/direct_chat_injection_v1.json",
        base_url=MOCK_URL,
        max_muzzle_cycles=1,
        top_k_vessels=2,
        engagement_id="smoke-trd17",
    )
    strategy = StaticStrategy()
    judge = Judge(pattern_oracle=PatternOracle(), llm_oracle=None)
    tmp_dir = tempfile.mkdtemp()
    emitter = TelemetryEmitter(Path(tmp_dir) / "smoke_telemetry.jsonl")
    runner = CampaignRunner(
        victim=victim, strategy=strategy, judge=judge,
        emitter=emitter, config=config,
    )
    mo = MuzzleOrchestrator(victim=victim, runner=runner, config=config)

    tasks = [
        ExplorationTask(
            task_id="smoke-direct",
            description="Probe direct chat",
            turns=["Hello, describe your purpose briefly."],
        )
    ]

    messages: list[str] = []
    results = await mo.run(tasks, progress_fn=messages.append)
    assert len(results) >= 1
    # No exception = success; surfaces_found may be empty on mock without debug endpoint
    print(f"Smoke result: {results[0]}")
    print(f"Progress log: {messages[:5]}")
