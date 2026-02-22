from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, List, Optional, Union

STANDARD_COLUMNS = [
    "scenario_id",
    "suite_id",
    "rep",
    "category",
    "severity",
    "status",
    "failure_reason",
    "attack_surface",
    "prompt_leak",
    "state_leak",
    "schema_leak",
    "behavioral_leak",
    "policy_override",
    "unauthorized_write",
    "canary_exfiltrated",
    "loop_drift",
    "write_delta",
    "turn_count",
    "session_id",
    "error",
    "notes",
]


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    flat = dict(row)

    status = flat.get("status")
    if hasattr(status, "value"):
        flat["status"] = status.value

    failure_reason = flat.get("failure_reason")
    if hasattr(failure_reason, "value"):
        flat["failure_reason"] = failure_reason.value

    attack_surface = flat.get("attack_surface")
    if hasattr(attack_surface, "value"):
        flat["attack_surface"] = attack_surface.value

    notes = flat.get("notes")
    if isinstance(notes, list):
        flat["notes"] = "; ".join(str(n) for n in notes)

    hard_flags = flat.get("hard_flags", {})
    if isinstance(hard_flags, dict):
        for key, value in hard_flags.items():
            flat[key] = bool(value)

    return flat


def write_csv(
    path: Union[str, Path],
    rows: list[dict[str, Any]],
    columns: Optional[List[str]] = None,
) -> None:
    cols = columns or STANDARD_COLUMNS
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(_flatten_row(row))
