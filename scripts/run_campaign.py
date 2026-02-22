from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.attack.catalog.loader import load_test_specs
from harness.attack.synthesis.llm_synth import LlmSynthStrategy
from harness.attack.synthesis.static_strategy import StaticStrategy
from harness.campaign.runner import CampaignRunner
from harness.campaign.scheduler import Scheduler
from harness.core.schemas import RunConfig
from harness.oracle.judge import Judge
from harness.oracle.llm_oracle import LlmOracle
from harness.oracle.pattern_oracle import PatternOracle
from harness.reporting.csv_writer import STANDARD_COLUMNS, write_csv
from harness.reporting.jsonl_writer import append_jsonl
from harness.reporting.markdown_reporter import write_markdown_report
from harness.telemetry.emitter import TelemetryEmitter
from harness.victim.api_adapter import RestApiAdapter


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a harness campaign")
    parser.add_argument("--catalog", required=True, help="Path to attack catalog JSON")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Victim base URL")
    parser.add_argument("--runs-per-scenario", type=int, default=1)
    parser.add_argument("--adaptive", action="store_true")
    parser.add_argument("--attacker-model", default="moonshotai/kimi-k2-0905")
    parser.add_argument("--no-analyst", action="store_true")
    parser.add_argument("--scenario-filter", default="", help="Comma-separated scenario IDs")
    parser.add_argument("--run-dir", default="", help="Output directory")
    parser.add_argument("--target-mode", default="chat", choices=["chat", "stream"])
    return parser.parse_args()


def _default_run_dir(catalog: str, mode: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = Path(catalog).stem
    return Path("reports") / "runs" / f"{ts}_{mode}_{stem}"


async def _run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir) if args.run_dir else _default_run_dir(args.catalog, args.target_mode)
    run_dir.mkdir(parents=True, exist_ok=True)

    config = RunConfig(
        catalog_path=args.catalog,
        base_url=args.base_url,
        target_mode=args.target_mode,
        runs_per_scenario=max(1, int(args.runs_per_scenario)),
        adaptive=bool(args.adaptive),
        attacker_model=str(args.attacker_model),
        analyst_enabled=not bool(args.no_analyst),
        run_dir=str(run_dir),
        scenario_filter=[s.strip() for s in str(args.scenario_filter).split(",") if s.strip()],
    )

    catalog, specs = load_test_specs(config.catalog_path)
    if config.scenario_filter:
        selected = set(config.scenario_filter)
        specs = [s for s in specs if s.scenario_id in selected]

    runs_jsonl = run_dir / "runs.jsonl"
    runs_csv = run_dir / "runs.csv"
    report_md = run_dir / "report.md"
    run_meta = run_dir / "run_meta.json"
    telemetry_jsonl = run_dir / "telemetry.jsonl"

    victim = RestApiAdapter(base_url=config.base_url, mode=config.target_mode)
    if args.adaptive:
        api_key = os.getenv(config.attacker_api_key_env, "").strip()
        if not api_key:
            raise SystemExit(
                "Missing %s env var. Add it to .env or export it in your shell." % config.attacker_api_key_env
            )
        strategy = LlmSynthStrategy(
            endpoint=config.attacker_endpoint,
            api_key=api_key,
            model_name=config.attacker_model,
            fallback_model_name=config.attacker_fallback_model,
            max_requests_per_minute=config.attacker_max_rpm,
            cooldown_seconds=config.attacker_cooldown_seconds,
        )
    else:
        strategy = StaticStrategy()

    llm_oracle = None
    if config.analyst_enabled:
        llm_oracle = LlmOracle(
            model=config.analyst_model,
            endpoint=config.analyst_endpoint,
            api_key_env=config.analyst_api_key_env,
            timeout_seconds=config.timeout_seconds,
        )
    judge = Judge(pattern_oracle=PatternOracle(), llm_oracle=llm_oracle)

    rows: list[dict] = []

    with TelemetryEmitter(telemetry_jsonl) as emitter:
        runner = CampaignRunner(victim=victim, strategy=strategy, judge=judge, emitter=emitter, config=config)
        scheduler = Scheduler(runner=runner, max_cost_usd=config.max_cost_usd)

        def on_result(result):
            row = result.model_dump()
            rows.append(row)
            append_jsonl(runs_jsonl, row)

        await scheduler.run(
            specs=specs,
            runs_per_scenario=config.runs_per_scenario,
            scenario_filter=config.scenario_filter,
            on_result=on_result,
        )

    write_csv(runs_csv, rows, columns=STANDARD_COLUMNS)
    write_markdown_report(
        report_md,
        title="deeppeak-harness Campaign Report",
        rows=rows,
        target_name=config.base_url,
        phase=2 if args.adaptive or config.analyst_enabled else 1,
    )

    run_meta.write_text(
        json.dumps(
            {
                "config": config.model_dump(),
                "catalog": {
                    "suite_id": catalog.get("suite_id", ""),
                    "version": catalog.get("version", ""),
                    "attack_count": len(catalog.get("attacks", [])),
                },
                "selected_scenarios": [s.scenario_id for s in specs],
                "result_count": len(rows),
                "outputs": {
                    "runs_jsonl": str(runs_jsonl),
                    "runs_csv": str(runs_csv),
                    "report_md": str(report_md),
                    "telemetry_jsonl": str(telemetry_jsonl),
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
