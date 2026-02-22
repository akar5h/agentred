from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from harness.attack.catalog.loader import load_test_specs
from harness.attack.synthesis.static_strategy import StaticStrategy
from harness.campaign.runner import CampaignRunner
from harness.core.schemas import RunConfig
from harness.oracle.pattern_oracle import PatternOracle
from harness.reporting.jsonl_writer import append_jsonl
from harness.reporting.markdown_reporter import write_markdown_report
from harness.telemetry.emitter import TelemetryEmitter
from harness.victim.api_adapter import RestApiAdapter
from harness.victim.mock.app import app


@pytest.mark.asyncio
async def test_campaign_smoke_produces_jsonl(tmp_path) -> None:
    catalog_path = "harness/attack/library/direct/direct_chat_injection_v1.json"
    _, specs = load_test_specs(catalog_path)
    specs = specs[:3]

    runs_path = tmp_path / "runs.jsonl"
    report_path = tmp_path / "report.md"
    telemetry_path = tmp_path / "telemetry.jsonl"

    rows: list[dict] = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adapter = RestApiAdapter(base_url="http://test", mode="chat", client=client)
        config = RunConfig(catalog_path=catalog_path, base_url="http://test", runs_per_scenario=1)
        with TelemetryEmitter(telemetry_path) as emitter:
            runner = CampaignRunner(
                victim=adapter,
                strategy=StaticStrategy(),
                judge=PatternOracle(),
                emitter=emitter,
                config=config,
            )

            def on_result(result):
                row = result.model_dump()
                rows.append(row)
                append_jsonl(runs_path, row)

            await runner.run_all(specs, on_result=on_result)

    assert runs_path.exists()
    lines = [line for line in runs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3

    statuses = [json.loads(line)["status"] for line in lines]
    assert any(s in ("Success", "Injection") for s in statuses)

    write_markdown_report(report_path, title="Smoke", rows=rows)
    assert report_path.exists()


@pytest.mark.asyncio
async def test_campaign_smoke_canary_fires(tmp_path) -> None:
    catalog_path = "harness/attack/library/direct/direct_chat_injection_v1.json"
    _, specs = load_test_specs(catalog_path)
    spec = next(s for s in specs if s.scenario_id == "CI-01")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        adapter = RestApiAdapter(base_url="http://test", mode="chat", client=client)
        config = RunConfig(catalog_path=catalog_path, base_url="http://test", runs_per_scenario=1)
        with TelemetryEmitter(tmp_path / "telemetry.jsonl") as emitter:
            runner = CampaignRunner(
                victim=adapter,
                strategy=StaticStrategy(),
                judge=PatternOracle(),
                emitter=emitter,
                config=config,
            )
            result = await runner.run_one(spec)

    assert result.hard_flags.get("canary_exfiltrated") is True
