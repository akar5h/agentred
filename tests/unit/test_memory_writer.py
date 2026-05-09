from __future__ import annotations

import json

from grafted.campaign.memory_writer import build_finding_memory, write_finding_memory
from grafted.core.enums import AttackSurface, Status, VesselKind
from grafted.core.schemas import JudgeResult, TestSpec as HarnessTestSpec, VesselSpec


def _result(status: Status, hard_flags: dict[str, bool]) -> JudgeResult:
    return JudgeResult(
        run_id="run-1",
        scenario_id="S-01",
        suite_id="suite-1",
        status=status,
        hard_flags=hard_flags,
    )


def test_build_finding_memory_prefers_spec_surface_and_technique() -> None:
    spec = HarnessTestSpec(
        scenario_id="S-01",
        suite_id="direct_suite",
        turns=["attack turn A", "attack turn B"],
        prelude_turns=["warmup"],
        vessels=[VesselSpec(kind=VesselKind.DIRECT_PROMPT)],
        attack_surface=AttackSurface.DIRECT_CHAT,
        technique_family="loop_pressure",
    )
    result = _result(Status.SUCCESS, {"canary_exfiltrated": True, "prompt_leak": True})
    observation = {
        "transcript": [
            {"role": "user", "content": "warmup"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "mutated attack 1"},
            {"role": "assistant", "content": "resp1"},
            {"role": "user", "content": "mutated attack 2"},
            {"role": "assistant", "content": "resp2"},
        ]
    }

    memory = build_finding_memory(result, spec, observation, cycle=2)
    assert memory.attack_surface == "direct_chat"
    assert memory.technique_family == "loop_pressure"
    assert memory.vessel_kind == "direct_prompt"
    assert memory.winning_turn == "mutated attack 2"
    assert memory.canary_confirmed is True
    assert memory.oracle_codes_fired == ["canary_exfiltrated", "prompt_leak"]
    assert memory.cycle == 2


def test_build_finding_memory_fallbacks_for_grafted_specs() -> None:
    spec = HarnessTestSpec(
        scenario_id="S-02",
        suite_id="grafted_suite_v1",
        turns=["payload"],
        vessels=[VesselSpec(kind=VesselKind.UPLOADED_DOCUMENT)],
        technique_family="",
        attack_surface=None,
    )
    result = _result(Status.INJECTION, {"canary_exfiltrated": False, "unauthorized_write": True})
    observation = {"transcript": [{"role": "user", "content": "payload"}]}

    memory = build_finding_memory(result, spec, observation, cycle=0)
    assert memory.attack_surface == "indirect_upload"
    assert memory.technique_family == "grafted_uploaded_document"
    assert memory.vessel_kind == "uploaded_document"
    assert memory.oracle_codes_fired == ["unauthorized_write"]


def test_write_finding_memory_appends_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    memory = build_finding_memory(
        _result(Status.SUCCESS, {"canary_exfiltrated": True}),
        HarnessTestSpec(
            scenario_id="S-03",
            suite_id="direct_suite",
            turns=["payload"],
            vessels=[VesselSpec(kind=VesselKind.DIRECT_PROMPT)],
        ),
        {"transcript": [{"role": "user", "content": "payload"}]},
        cycle=1,
    )
    write_finding_memory(memory, "eng-123")
    write_finding_memory(memory, "eng-123")

    path = tmp_path / "reports" / "eng-123" / "memory" / "findings.jsonl"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["scenario_id"] == "S-01"
    assert parsed[0]["cycle"] == 1
