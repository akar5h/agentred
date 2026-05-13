"""Recompute ASR + utility from existing AgentDojo pair-log JSON files
using the CORRECTED convention (security==True means injection succeeded
per AgentDojo's BaseInjectionTask.security() docstring).

Walks reports/agentdojo*/ trees, groups pair logs by
(logdir_root, pipeline_name, suite, attack_name), and prints a corrected
table. Does NOT touch any existing files — read-only re-derivation.

Use this to recover the truth from data we collected today before the
ASR-direction bug was caught.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def walk_pair_logs(root: Path):
    """Yield pair-log dicts for every valid pair log under root.

    Trusts the JSON contents over the directory structure (some of our
    runs nest under {root}/{tree_name}/{pipeline}/... and others under
    {root}/{pipeline}/...). We just check every JSON for valid
    utility+security+injection_task_id fields and extract suite + attack
    from the json content + parent dir name.
    """
    if not root.exists():
        return
    for json_file in root.rglob("injection_task_*.json"):
        try:
            d = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        u = d.get("utility")
        s = d.get("security")
        inj_id = d.get("injection_task_id")
        if not isinstance(u, bool) or not isinstance(s, bool):
            continue
        if inj_id is None:
            continue
        # Attack name = parent directory name of the JSON file
        attack_name = json_file.parent.name
        if attack_name == "none":
            continue  # baseline runs
        suite = d.get("suite_name", "?")
        pipeline_name = d.get("pipeline_name", "?")
        # Identify which experiment "bucket" this run belongs to by the
        # subdirectory immediately under the root (e.g., the v2 nesting).
        rel_parts = json_file.relative_to(root).parts
        if len(rel_parts) >= 6:
            # Nested: {root}/{tree}/{pipeline}/{suite}/{user_task}/{attack}/{inj}.json
            experiment_tag = rel_parts[0]
        else:
            experiment_tag = ""
        yield {
            "root": str(root),
            "experiment_tag": experiment_tag,
            "pipeline": pipeline_name,
            "suite": suite,
            "user_task": d.get("user_task_id"),
            "attack": attack_name,
            "injection_task": inj_id,
            "utility": u,
            "security": s,
        }


def main() -> int:
    # Walk every reports/agentdojo* tree we have
    candidates = sorted(REPO_ROOT.glob("reports/agentdojo*"))
    all_rows = []
    for root in candidates:
        if not root.is_dir():
            continue
        for row in walk_pair_logs(root):
            all_rows.append(row)

    print(f"\nfound {len(all_rows)} valid attack-pair logs across "
          f"{len(candidates)} report trees\n")

    # Group by (root, experiment_tag, pipeline, suite, attack) so each
    # distinct experimental run gets its own row (don't aggregate across
    # multiple separate runs of the same config).
    groups = defaultdict(list)
    for r in all_rows:
        key = (r["root"], r["experiment_tag"], r["pipeline"], r["suite"], r["attack"])
        groups[key].append(r)

    # Print corrected table
    print(
        f"{'experiment':40s} {'pipeline':40s} {'suite':10s} {'attack':25s} "
        f"{'n':>4s}  {'ASR_correct':>11s}  {'utility':>8s}"
    )
    print("-" * 145)
    for (root, exp_tag, pipeline, suite, attack), rows in sorted(groups.items()):
        n = len(rows)
        asr = sum(1 for r in rows if r["security"]) / max(1, n) * 100
        util = sum(1 for r in rows if r["utility"]) / max(1, n) * 100
        # Friendly label combining root + experiment_tag
        root_short = root.split("/")[-1][:30]
        label = f"{root_short}/{exp_tag}" if exp_tag else root_short
        label = label[:38]
        pl_short = pipeline[:38]
        print(
            f"{label:40s} {pl_short:40s} {suite:10s} {attack:25s} "
            f"{n:>4d}  {asr:>10.2f}%  {util:>7.2f}%"
        )
    print()

    # Save as CSV too for downstream use
    out_path = REPO_ROOT / "data/grafted/ablation/_corrected_asr_all_runs.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["root", "experiment_tag", "pipeline", "suite", "attack",
                    "n", "asr_correct_pct", "utility_pct"])
        for (root, exp_tag, pipeline, suite, attack), rows in sorted(groups.items()):
            n = len(rows)
            asr = sum(1 for r in rows if r["security"]) / max(1, n) * 100
            util = sum(1 for r in rows if r["utility"]) / max(1, n) * 100
            w.writerow([root, exp_tag, pipeline, suite, attack, n,
                        f"{asr:.2f}", f"{util:.2f}"])
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
