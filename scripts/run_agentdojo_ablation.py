"""Pre-flight memory ablation: run grafted twice on the same suite + model,
once with --memory-scope per-suite (memory ON) and once per-pair (memory
OFF). Writes a comparison CSV.

This is the GO/NO-GO experiment for the paper's central thesis. If
ASR(per-suite) > ASR(per-pair) by a meaningful margin, the cross-task-
transfer claim holds on AgentDojo.

Usage:
    python scripts/run_agentdojo_ablation.py \\
        --suite workspace \\
        --victim-model gpt-4o-mini-2024-07-18 \\
        --max-pairs 30 \\
        --output data/grafted/ablation/workspace_gpt4o.csv

Requires the agentdojo extra. Will spend real OpenRouter dollars on
the attacker LLM and AgentDojo's victim model.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="grafted memory ablation on AgentDojo")
    parser.add_argument("--suite", required=True, choices=["workspace", "banking", "travel", "slack"])
    parser.add_argument("--victim-model", required=True)
    parser.add_argument("--benchmark-version", default="v1.2")
    parser.add_argument("--max-pairs", type=int, default=10, help="Bound each run for fast iteration")
    parser.add_argument("--logdir", default="reports/agentdojo")
    parser.add_argument("--memory-dir", default="data/grafted/memory/")
    parser.add_argument("--attacker-model", default="moonshotai/kimi-k2-0905")
    parser.add_argument("--output", default="data/grafted/ablation/result.csv")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe logdir and memory-dir before each run (forces a true cold start)",
    )
    return parser.parse_args()


def _run_one(args, scope: str) -> dict:
    """Run scripts/run_agentdojo.py with the given scope; parse the printed
    summary for ASR and avg utility. Returns a dict with the metrics."""
    if args.clean:
        # Clean both logdir and memory-dir to ensure no leakage between scopes.
        # AgentDojo's force-rerun also helps but doesn't clear the memory state.
        for d in (Path(args.logdir), Path(args.memory_dir)):
            if d.exists():
                shutil.rmtree(d)

    cmd = [
        sys.executable, str(REPO_ROOT / "scripts" / "run_agentdojo.py"),
        "--suite", args.suite,
        "--victim-model", args.victim_model,
        "--benchmark-version", args.benchmark_version,
        "--memory-scope", scope,
        "--memory-dir", args.memory_dir,
        "--logdir", args.logdir,
        "--attacker-model", args.attacker_model,
        "--force-rerun",
    ]
    if args.max_pairs > 0:
        cmd += ["--max-pairs", str(args.max_pairs)]

    print(f"\n--- Running scope={scope} ---")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    # Parse "ASR: X%" and "Avg utility: Y%" out of the runner's stdout.
    asr = None
    util = None
    pairs = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("ASR:"):
            asr = _percent(line)
        elif line.startswith("Avg utility:"):
            util = _percent(line)
        elif line.startswith("Pairs:"):
            try:
                pairs = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    return {
        "scope": scope,
        "asr_pct": asr,
        "avg_utility_pct": util,
        "pairs": pairs,
        "exit_code": proc.returncode,
    }


def _percent(line: str) -> float | None:
    # Lines look like "ASR:          12.34%  (security == False)"
    parts = line.split(":", 1)
    if len(parts) != 2:
        return None
    tail = parts[1].strip()
    for token in tail.split():
        if token.endswith("%"):
            try:
                return float(token.rstrip("%"))
            except ValueError:
                return None
    return None


def main() -> int:
    args = _parse_args()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for scope in ("per-suite", "per-pair"):
        rows.append(_run_one(args, scope))

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["scope", "asr_pct", "avg_utility_pct", "pairs", "exit_code"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print()
    print(f"Wrote ablation to {out_path}")
    print(f"  per-suite ASR: {rows[0].get('asr_pct')}%")
    print(f"  per-pair  ASR: {rows[1].get('asr_pct')}%")
    if rows[0].get("asr_pct") is not None and rows[1].get("asr_pct") is not None:
        delta = rows[0]["asr_pct"] - rows[1]["asr_pct"]
        print(f"  delta:          {delta:+.2f} pts")
        if delta > 0:
            print("  → cross-task transfer thesis HOLDS on this configuration.")
        else:
            print("  → cross-task transfer thesis does NOT hold here. Investigate before paper.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
