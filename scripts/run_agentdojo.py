"""Run grafted's GraftedAttack against an AgentDojo suite.

Wraps AgentDojo's standard ``benchmark_suite_with_injections`` flow with
grafted's adaptive synthesis as the BaseAttack subclass. Cross-pair
memory transfer is enabled by default (``--memory-scope per-suite``);
``--memory-scope per-pair`` is the ablation control.

Usage:
    python scripts/run_agentdojo.py \\
        --suite workspace \\
        --victim-model gpt-4o-mini-2024-07-18 \\
        --benchmark-version v1.2 \\
        --memory-scope per-suite \\
        --logdir reports/agentdojo

Requires the ``agentdojo`` extra:
    pip install -e '.[agentdojo]'
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run grafted vs an AgentDojo suite")
    parser.add_argument("--suite", required=True, choices=["workspace", "banking", "travel", "slack"])
    parser.add_argument("--victim-model", required=True, help="AgentDojo ModelsEnum value, e.g. gpt-4o-mini-2024-07-18")
    parser.add_argument("--benchmark-version", default="v1.2")
    parser.add_argument(
        "--memory-scope",
        default="per-suite",
        choices=["per-suite", "per-model", "per-pair"],
        help="Cross-pair memory policy. 'per-pair' is the ablation control (memory off).",
    )
    parser.add_argument("--memory-dir", default="data/grafted/memory/")
    parser.add_argument("--logdir", default="reports/agentdojo", help="AgentDojo logdir for verdict harvest")
    parser.add_argument("--user-tasks", default="", help="Comma-separated user_task IDs (empty = all)")
    parser.add_argument("--injection-tasks", default="", help="Comma-separated injection_task IDs (empty = all)")
    parser.add_argument("--max-pairs", type=int, default=0, help="Stop after N (user, injection) pairs (0 = no limit)")
    parser.add_argument("--force-rerun", action="store_true")
    parser.add_argument("--attacker-model", default="moonshotai/kimi-k2-0905")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig
        from agentdojo.benchmark import benchmark_suite_with_injections
        from agentdojo.logging import OutputLogger
        from agentdojo.task_suite.load_suites import get_suite
    except ImportError as exc:
        sys.stderr.write(
            "agentdojo is not installed. Run: pip install -e '.[agentdojo]'\n"
            f"Original error: {exc}\n"
        )
        return 1

    from grafted.integrations.agentdojo.attack import GraftedAttack
    from grafted.integrations.agentdojo.verdict_harvest import VerdictHarvester

    suite = get_suite(args.benchmark_version, args.suite)
    pipeline = AgentPipeline.from_config(
        PipelineConfig(llm=args.victim_model, model_id=None, defense=None, tool_delimiter="tool")
    )

    logdir = Path(args.logdir)
    logdir.mkdir(parents=True, exist_ok=True)

    pipeline_name = pipeline.name or args.victim_model
    harvester = VerdictHarvester(
        logdir=logdir,
        pipeline_name=pipeline_name,
        suite_name=args.suite,
        attack_name="grafted",
    )

    attack = GraftedAttack(
        suite,
        pipeline,
        memory_scope=args.memory_scope,
        attacker_model=args.attacker_model,
        memory_dir=Path(args.memory_dir),
        verdict_harvester=harvester,
    )

    user_tasks = tuple(s.strip() for s in args.user_tasks.split(",") if s.strip())
    injection_tasks = tuple(s.strip() for s in args.injection_tasks.split(",") if s.strip())

    if args.max_pairs > 0:
        # Truncate user_tasks to roughly bound the run; AgentDojo runs all
        # injection_tasks per user_task, so this is approximate.
        all_user_ids = list(suite.user_tasks.keys())
        n_inj = len(suite.injection_tasks)
        max_user = max(1, args.max_pairs // max(1, n_inj))
        user_tasks = tuple(all_user_ids[:max_user])
        warnings.warn(f"--max-pairs={args.max_pairs} truncated user_tasks to {len(user_tasks)} (n_inj={n_inj})")

    print(f"Running grafted vs AgentDojo {args.suite} suite")
    print(f"  victim:        {pipeline_name}")
    print(f"  attacker:      {args.attacker_model}")
    print(f"  memory_scope:  {args.memory_scope}")
    print(f"  engagement_id: {attack._engagement_id}")
    print(f"  logdir:        {logdir}")

    with OutputLogger(str(logdir)):
        results = benchmark_suite_with_injections(
            pipeline,
            suite,
            attack,
            user_tasks=user_tasks or None,
            injection_tasks=injection_tasks or None,
            logdir=logdir,
            force_rerun=args.force_rerun,
            benchmark_version=args.benchmark_version,
        )

    sec = results["security_results"].values()
    util = results["utility_results"].values()
    asr = sum(1 for v in sec if not v) / max(1, len(sec))
    avg_util = sum(util) / max(1, len(util))

    print()
    print(f"Suite:        {args.suite}")
    print(f"Pairs:        {len(sec)}")
    print(f"ASR:          {asr * 100:.2f}%  (security == False)")
    print(f"Avg utility:  {avg_util * 100:.2f}%")
    print(f"Memory at:    {attack._memory_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
