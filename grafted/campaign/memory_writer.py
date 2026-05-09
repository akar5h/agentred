from __future__ import annotations

import json
from pathlib import Path

from grafted.core.schemas import FindingMemory, JudgeResult, TestSpec


def _derive_attack_surface(spec: TestSpec) -> str:
    if spec.attack_surface is not None:
        return str(spec.attack_surface.value if hasattr(spec.attack_surface, "value") else spec.attack_surface)

    vessel_surface_map = {
        "direct_prompt": "direct_chat",
        "uploaded_document": "indirect_upload",
        "memory_entry": "memory",
        "tool_output": "tool",
    }
    if spec.vessels:
        return vessel_surface_map.get(spec.vessels[0].kind.value, "direct_chat")
    return "direct_chat"


def _derive_technique_family(spec: TestSpec) -> str:
    if spec.technique_family:
        return spec.technique_family
    if spec.vessels:
        return f"grafted_{spec.vessels[0].kind.value}"
    return "unknown"


def _extract_winning_turn(spec: TestSpec, observation: dict) -> str:
    transcript = observation.get("transcript", [])
    if not isinstance(transcript, list):
        return ""

    # Prelude contributes alternating user+assistant turns; skip those entries.
    attack_entries = transcript[len(spec.prelude_turns) * 2 :]
    for entry in reversed(attack_entries):
        if isinstance(entry, dict) and entry.get("role") == "user":
            return str(entry.get("content", ""))
    return ""


def build_finding_memory(
    result: JudgeResult,
    spec: TestSpec,
    observation: dict,
    cycle: int,
) -> FindingMemory:
    return FindingMemory(
        scenario_id=result.scenario_id,
        attack_surface=_derive_attack_surface(spec),
        vessel_kind=spec.vessels[0].kind.value if spec.vessels else "",
        technique_family=_derive_technique_family(spec),
        oracle_codes_fired=[k for k, v in (result.hard_flags or {}).items() if bool(v)],
        winning_turn=_extract_winning_turn(spec, observation),
        canary_confirmed=bool((result.hard_flags or {}).get("canary_exfiltrated", False)),
        cycle=int(cycle),
    )


def write_finding_memory(memory: FindingMemory, engagement_id: str) -> None:
    path = Path("reports") / engagement_id / "memory" / "findings.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(memory.model_dump(), ensure_ascii=False) + "\n")
