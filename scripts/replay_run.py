from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.telemetry.replay import DeterministicReplayer


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a campaign telemetry JSONL offline")
    parser.add_argument("--telemetry", required=True, help="Path to telemetry.jsonl")
    parser.add_argument("--output", default="", help="Output replay JSONL path (default: <telemetry_dir>/replay.jsonl)")
    parser.add_argument("--print-mismatches", action="store_true", help="Print mismatch details to stdout")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    replayer = DeterministicReplayer(args.telemetry)
    results = replayer.replay()

    total = len(results)
    matches = sum(1 for r in results if r.match)
    mismatches = [r for r in results if not r.match]

    print(f"Replayed {total} runs: {matches} match, {len(mismatches)} mismatch")

    if args.print_mismatches:
        for r in mismatches:
            print(f"  MISMATCH {r.scenario_id}: original={r.original_status} replayed={r.replayed_status}")
            for note in r.notes[:3]:
                print(f"    note: {note}")

    out_path = Path(args.output) if args.output else Path(args.telemetry).parent / "replay.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r.to_dict()) + "\n")
    print(f"Replay JSONL: {out_path}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
