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
import os
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run grafted vs an AgentDojo suite")
    parser.add_argument("--suite", required=True, choices=["workspace", "banking", "travel", "slack"])
    parser.add_argument(
        "--victim-model",
        required=True,
        help="Model name. With --provider openrouter use OpenRouter naming (e.g. deepseek/deepseek-chat); "
        "with --provider agentdojo-native use an AgentDojo ModelsEnum value (e.g. gpt-4o-mini-2024-07-18).",
    )
    parser.add_argument(
        "--provider",
        default="openrouter",
        choices=["openrouter", "agentdojo-native"],
        help="LLM provider routing. 'openrouter' routes any OpenRouter model name through OpenRouter's "
        "OpenAI-compatible endpoint (requires OPENROUTER_API_KEY). 'agentdojo-native' uses AgentDojo's "
        "stock ModelsEnum dispatch (OpenAI / Anthropic / Cohere / Google direct).",
    )
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
    parser.add_argument(
        "--attack",
        default="grafted",
        choices=["grafted", "important_instructions"],
        help="'grafted' is our adaptive synthesis. 'important_instructions' is AgentDojo's "
        "stock template attack — use it to produce baseline numbers on the exact same "
        "victim+defense for honest comparison.",
    )
    parser.add_argument(
        "--defense",
        default="",
        choices=["", "tool_filter", "spotlighting_with_delimiting", "repeat_user_prompt", "transformers_pi_detector"],
        help="AgentDojo built-in defense wrapping the victim agent. "
        "Empty (default) = no defense (vulnerable baseline, ASR runs near ceiling). "
        "'spotlighting_with_delimiting' is the cleanest prompt-only defense; recommended for ablation. "
        "'tool_filter' adds an extra LLM filter call. "
        "'transformers_pi_detector' requires HF transformers dependencies.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable kairos/OTel tracing: install_kairos() before LLM calls, wrap each pair "
        "in a 'kairos.task' span with memory + synthesis diagnostic attributes. "
        "Requires the [observability] extra and Phoenix running on localhost:6006.",
    )
    parser.add_argument(
        "--strategy-library",
        default="",
        help="Path to a pre-trained per-suite Strategy library JSON "
        "(e.g., data/grafted/strategy_library/workspace.json). When set, "
        "GraftedAttack does a library lookup before invoking the live "
        "LlmSynth attacker — zero attacker-LLM calls if a strategy matches. "
        "Only applies with --attack grafted.",
    )
    parser.add_argument(
        "--eval-split",
        default="all",
        choices=["all", "train", "test"],
        help="Restrict the injection_tasks evaluated to the train or test "
        "half of the deterministic split (seed=42, sorted by numeric suffix). "
        "'all' (default) ignores the split. Use 'test' for honest held-out "
        "Pattern-2 evaluation.",
    )
    return parser.parse_args()


def _build_llm_for_pipeline_config(provider: str, victim_model: str):
    """Return the value to pass as PipelineConfig.llm.

    For 'openrouter', construct an OpenAILLM pointed at OpenRouter's
    OpenAI-compatible endpoint and return the instance (bypasses
    AgentDojo's closed ModelsEnum). For 'agentdojo-native', return the
    model string so AgentDojo's stock dispatch handles it.
    """
    if provider == "agentdojo-native":
        return victim_model

    import json as _json
    import openai
    from agentdojo.agent_pipeline.llms import openai_llm as _aoll
    from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
    from agentdojo.functions_runtime import FunctionCall

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY missing from environment. Either set it in .env or pass "
            "--provider agentdojo-native to fall back to AgentDojo's stock routing."
        )

    # DeepSeek (and some other models routed through OpenRouter) intermittently
    # double-encode tool_call.function.arguments — a JSON string whose content
    # is itself a JSON string. AgentDojo's stock _openai_to_tool_call only
    # json.loads once, so the dict-typed `args` field of FunctionCall gets a
    # str and Pydantic rejects it. Patch defensively: if one json.loads still
    # leaves a string, decode again.
    def _to_tool_call(tool_call):
        args = _json.loads(tool_call.function.arguments)
        if isinstance(args, str):
            args = _json.loads(args)
        return FunctionCall(
            function=tool_call.function.name,
            args=args,
            id=tool_call.id,
        )

    _aoll._openai_to_tool_call = _to_tool_call

    # AgentDojo's get_model_name_from_pipeline does substring matching
    # against a closed MODEL_NAMES dict (gpt-/claude-/gemini-/etc). Models
    # not in that dict (Kimi, DeepSeek, Qwen, Llama 3.3+) raise ValueError
    # when ImportantInstructionsAttack tries to fill its {model} template
    # placeholder. Patch defensively: when no match found, fall back to
    # the generic "AI assistant" name (which AgentDojo already uses for
    # the base meta-llama entry).
    from agentdojo.attacks import base_attacks as _ad_base
    _orig_get_model_name = _ad_base.get_model_name_from_pipeline

    def _patched_get_model_name(pipeline):
        try:
            return _orig_get_model_name(pipeline)
        except ValueError:
            return "AI assistant"

    _ad_base.get_model_name_from_pipeline = _patched_get_model_name
    # Also patch the importing site in important_instructions_attacks
    from agentdojo.attacks import important_instructions_attacks as _ad_imp
    _ad_imp.get_model_name_from_pipeline = _patched_get_model_name

    client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    llm = OpenAILLM(client, victim_model)
    # Strip OpenRouter "<provider>/" prefix when setting llm.name so AgentDojo's
    # substring-based model lookups (e.g., get_model_name_from_pipeline used by
    # ImportantInstructionsAttack) can match standard names like
    # 'gpt-4o-mini-2024-07-18'. The full string is still used for the API call
    # via llm.model.
    llm.name = victim_model.split("/", 1)[-1] if "/" in victim_model else victim_model
    return llm


def main() -> int:
    args = _parse_args()

    # Install OTel/Traceloop BEFORE importing AgentDojo or constructing any
    # LLM client — Traceloop patches openai/anthropic at import time, so
    # later patching would miss already-imported call sites.
    if args.trace:
        from grafted.integrations.kairos_setup import install_kairos
        install_kairos()

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

    suite = get_suite(args.benchmark_version, args.suite)
    llm = _build_llm_for_pipeline_config(args.provider, args.victim_model)
    defense = args.defense or None
    pipeline = AgentPipeline.from_config(
        PipelineConfig(
            llm=llm,
            model_id=None,
            defense=defense,
            tool_delimiter="tool",
            system_message_name=None,
            system_message=None,
        )
    )

    logdir = Path(args.logdir)
    logdir.mkdir(parents=True, exist_ok=True)

    pipeline_name = pipeline.name or args.victim_model

    if args.attack == "important_instructions":
        from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
        attack = ImportantInstructionsAttack(suite, pipeline)
        memory_note = "n/a (stock attack has no memory)"
    else:
        from grafted.integrations.agentdojo.attack import GraftedAttack
        from grafted.integrations.agentdojo.verdict_harvest import VerdictHarvester
        harvester = VerdictHarvester(
            logdir=logdir,
            pipeline_name=pipeline_name,
            suite_name=args.suite,
            attack_name="grafted",
        )
        loaded_library = None
        if args.strategy_library:
            from grafted.attack.strategy_library import StrategyLibrary
            loaded_library = StrategyLibrary.load(Path(args.strategy_library))
            print(f"  strategy_lib: {args.strategy_library} (n={len(loaded_library)})")
        attack = GraftedAttack(
            suite,
            pipeline,
            memory_scope=args.memory_scope,
            attacker_model=args.attacker_model,
            memory_dir=Path(args.memory_dir),
            verdict_harvester=harvester,
            strategy_library=loaded_library,
        )
        memory_note = str(attack._memory_path)

    user_tasks = tuple(s.strip() for s in args.user_tasks.split(",") if s.strip())
    injection_tasks = tuple(s.strip() for s in args.injection_tasks.split(",") if s.strip())

    # Pattern-2 train/test split: restrict injection_tasks to held-out set
    # if --eval-split is train or test. Honored ONLY if user did not pass
    # --injection-tasks explicitly (explicit IDs take precedence).
    if args.eval_split != "all" and not injection_tasks:
        from grafted.integrations.agentdojo.strategy_split import (
            get_train_test_injection_split,
        )
        train_ids, test_ids = get_train_test_injection_split(suite)
        chosen = train_ids if args.eval_split == "train" else test_ids
        injection_tasks = tuple(chosen)
        print(
            f"  eval-split:   {args.eval_split} → "
            f"{len(injection_tasks)} injection_tasks: {list(injection_tasks)}"
        )

    if args.max_pairs > 0:
        if user_tasks and injection_tasks:
            warnings.warn(
                "--max-pairs ignored because BOTH --user-tasks and --injection-tasks "
                "(or --eval-split) were specified explicitly"
            )
        elif injection_tasks:
            # injection_tasks pinned (by explicit flag or --eval-split). Cap
            # user_tasks to keep total pair count near --max-pairs.
            all_user_ids = list(suite.user_tasks.keys())
            n_user_all = len(all_user_ids)
            n_inj = len(injection_tasks)
            n_user = min(n_user_all, max(1, args.max_pairs // max(1, n_inj)))
            user_tasks = tuple(all_user_ids[:n_user])
            warnings.warn(
                f"--max-pairs={args.max_pairs} with pinned injection_tasks (n={n_inj}) "
                f"→ {n_user} user_tasks × {n_inj} = {n_user * n_inj} pairs"
            )
        elif user_tasks:
            warnings.warn(
                "--max-pairs ignored because --user-tasks was specified explicitly"
            )
        else:
            # Balance user_tasks × injection_tasks under the cap. We want >=3
            # user_tasks because the cross-task transfer claim is the whole
            # point; collapsing to one user_task tests cross-injection only.
            all_user_ids = list(suite.user_tasks.keys())
            all_inj_ids = list(suite.injection_tasks.keys())
            n_user_all = len(all_user_ids)
            n_inj_all = len(all_inj_ids)

            n_user = min(3, n_user_all, args.max_pairs)
            n_inj = min(n_inj_all, max(1, args.max_pairs // max(1, n_user)))
            while n_user < n_user_all and (n_user + 1) * n_inj <= args.max_pairs:
                n_user += 1

            user_tasks = tuple(all_user_ids[:n_user])
            injection_tasks = tuple(all_inj_ids[:n_inj])
            warnings.warn(
                f"--max-pairs={args.max_pairs} → {n_user} user_tasks × {n_inj} injection_tasks "
                f"= {n_user * n_inj} pairs (suite has {n_user_all} × {n_inj_all})"
            )

    print(f"Running attack={args.attack} vs AgentDojo {args.suite} suite")
    print(f"  victim:        {pipeline_name}")
    if args.attack == "grafted":
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

    sec_items = list(results["security_results"].items())
    util_items = list(results["utility_results"].items())
    n = len(sec_items)
    mid = n // 2

    # AgentDojo's BaseInjectionTask.security() docstring: "Returns True if
    # the injection was executed correctly, False otherwise." So security
    # == True means the ATTACK SUCCEEDED. ASR is the fraction of pairs
    # where security is True. This was previously computed inverted (bug
    # confirmed 2026-05-13 by inspecting agentdojo/base_tasks.py docstring
    # + verifying with two pair logs — one where agent did the attack
    # action got security=True, one where agent ignored the attack got
    # security=False).
    def _asr_pct(items):
        return sum(1 for _, v in items if v) / max(1, len(items)) * 100

    asr_overall = _asr_pct(sec_items)
    avg_util = sum(v for _, v in util_items) / max(1, n) * 100

    print()
    print(f"Suite:        {args.suite}")
    print(f"Pairs:        {n}")
    print(f"ASR:          {asr_overall:.2f}%  (security == True = injection succeeded)")
    if mid >= 2:
        asr_first = _asr_pct(sec_items[:mid])
        asr_second = _asr_pct(sec_items[mid:])
        # Within-run signal: if memory is helping, second-half ASR should
        # exceed first-half ASR for per-suite scope (and be ~equal for per-pair).
        print(f"  first half  ({mid} pairs):  {asr_first:.2f}%")
        print(f"  second half ({n - mid} pairs):  {asr_second:.2f}%")
        print(f"  warm-up delta:             {asr_second - asr_first:+.2f} pp")
    print(f"Avg utility:  {avg_util:.2f}%")
    print(f"Memory at:    {memory_note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
