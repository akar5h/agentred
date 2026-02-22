from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from harness.core.schemas import TelemetryEvent
from harness.oracle.pattern_oracle import classify_observation
from harness.telemetry import events


def _compute_max_identical(responses: list[str]) -> int:
    if not responses:
        return 0
    current = 1
    max_identical = 1
    for i in range(1, len(responses)):
        if responses[i].strip() and responses[i].strip() == responses[i - 1].strip():
            current += 1
            max_identical = max(max_identical, current)
        else:
            current = 1
    return max_identical


@dataclass
class ReplayResult:
    run_id: str
    scenario_id: str
    suite_id: str = ""
    original_status: str = ""
    replayed_status: str = ""
    replayed_flags: dict = field(default_factory=dict)
    match: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "suite_id": self.suite_id,
            "original_status": self.original_status,
            "replayed_status": self.replayed_status,
            "match": self.match,
            "notes": self.notes,
            "replayed_flags": self.replayed_flags,
        }


class DeterministicReplayer:
    """
    Reads a telemetry JSONL file, reconstructs observations,
    and re-scores using PatternOracle only. Fully offline.
    """

    def __init__(self, telemetry_path: str | Path):
        self._path = Path(telemetry_path)
        if not self._path.exists():
            raise FileNotFoundError(f"Telemetry file not found: {self._path}")

    def load_events(self) -> list[TelemetryEvent]:
        telemetry_events = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                telemetry_events.append(TelemetryEvent(**data))
            except Exception:
                continue
        return telemetry_events

    def group_by_run(self, telemetry_events: list[TelemetryEvent]) -> dict[str, list[TelemetryEvent]]:
        groups: dict[str, list[TelemetryEvent]] = {}
        for ev in telemetry_events:
            groups.setdefault(ev.run_id, []).append(ev)
        for run_id in groups:
            groups[run_id].sort(key=lambda e: e.turn_index)
        return groups

    def reconstruct_observation(self, run_events: list[TelemetryEvent]) -> dict | None:
        responses: list[str] = []
        canary_token = ""
        suite_id = ""
        scenario_id = ""
        eval_meta: dict = {}

        for ev in run_events:
            if not canary_token and ev.canary_token:
                canary_token = ev.canary_token
            if not suite_id and ev.suite_id:
                suite_id = ev.suite_id
            if not scenario_id and ev.scenario_id:
                scenario_id = ev.scenario_id
            if ev.event_type in (events.ATTACK_TURN_RECV, events.PRELUDE_TURN_RECV):
                responses.append(ev.content)
            if ev.event_type == events.EVAL_RESULT:
                eval_meta = ev.meta

        if not responses and not eval_meta:
            return None

        return {
            "ok": True,
            "error": "",
            "scenario_id": scenario_id,
            "suite_id": suite_id,
            "canary_token": canary_token,
            "response_concat": "\n\n".join(responses),
            "responses": responses,
            "write_delta": int(eval_meta.get("write_delta", 0)),
            "max_identical_assistant_turns": _compute_max_identical(responses),
            "new_docs_sample": eval_meta.get("new_docs_sample", []),
            "expected": eval_meta.get("expected", {}),
            "tool_calls": eval_meta.get("tool_calls", []),
            "_original_status": eval_meta.get("status", ""),
            "_original_run_id": run_events[0].run_id if run_events else "",
        }

    def replay(self) -> list[ReplayResult]:
        loaded_events = self.load_events()
        groups = self.group_by_run(loaded_events)
        results = []
        for run_id, run_events in groups.items():
            obs = self.reconstruct_observation(run_events)
            if obs is None:
                results.append(ReplayResult(
                    run_id=run_id,
                    scenario_id="unknown",
                    original_status="unknown",
                    replayed_status="reconstruct_failed",
                    match=False,
                    notes=["insufficient telemetry data to reconstruct observation"],
                ))
                continue
            raw = classify_observation(obs)
            original = obs.get("_original_status", "")
            replayed = raw["status"]
            results.append(ReplayResult(
                run_id=run_id,
                scenario_id=obs.get("scenario_id", ""),
                suite_id=obs.get("suite_id", ""),
                original_status=original,
                replayed_status=replayed,
                replayed_flags=raw.get("flags", {}),
                match=(original == replayed),
                notes=raw.get("notes", []),
            ))
        return results
