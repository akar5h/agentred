from __future__ import annotations

from harness.core.enums import AttackSurface, FailureReason, OracleCode, Status, VesselKind
from harness.core.schemas import JudgeResult, RunConfig, TargetProfile, TelemetryEvent, TestSpec, VesselSpec


def test_status_enum_values() -> None:
    assert Status.SUCCESS == "Success"
    assert Status.BLOCKED == "Blocked"
    assert Status.INFRA_FAIL == "InfraFail"


def test_oracle_code_enum_roundtrip() -> None:
    for code in OracleCode:
        assert OracleCode(code.value) == code


def test_vessel_spec_defaults() -> None:
    v = VesselSpec(kind=VesselKind.DIRECT_PROMPT)
    assert v.delivery_field == "message"
    assert v.fixture_path is None
    assert v.render_template is True


def test_test_spec_minimal() -> None:
    t = TestSpec(scenario_id="LB-01", suite_id="direct_chat_injection_v1", turns=["Hello"])
    assert t.adaptive is False
    assert t.prelude_turns == []
    assert t.vessels == []


def test_judge_result_minimal() -> None:
    jr = JudgeResult(
        run_id="abc123",
        scenario_id="LB-01",
        suite_id="direct_chat_injection_v1",
        status=Status.BLOCKED,
    )
    assert jr.failure_reason is None
    assert jr.soft_success is False


def test_run_config_defaults() -> None:
    rc = RunConfig(catalog_path="some/path.json")
    assert rc.target_mode == "chat"
    assert rc.runs_per_scenario == 1


def test_target_profile_defaults() -> None:
    tp = TargetProfile()
    assert "thread_id" in tp.known_internal_state_keys


def test_telemetry_event_serializes_to_dict() -> None:
    ev = TelemetryEvent(
        run_id="r1",
        scenario_id="LB-01",
        suite_id="direct_chat_injection_v1",
        event_type="turn_sent",
        turn_index=0,
        content="hello",
    )
    d = ev.model_dump()
    assert d["event_type"] == "turn_sent"


def test_failure_reason_values() -> None:
    assert FailureReason.NOT_SURFACED == "NOT_SURFACED"
    assert FailureReason.DEFENSE_TRIGGERED == "DEFENSE_TRIGGERED"


def test_extra_fields_are_allowed() -> None:
    t = TestSpec(
        scenario_id="LB-01",
        suite_id="direct_chat_injection_v1",
        turns=["Hello"],
        unknown_catalog_field="value",
    )
    assert t.model_dump().get("unknown_catalog_field") == "value"


def test_attack_surface_enum() -> None:
    t = TestSpec(
        scenario_id="LB-01",
        suite_id="direct_chat_injection_v1",
        turns=["Hello"],
        attack_surface=AttackSurface.DIRECT_CHAT,
    )
    assert t.attack_surface == AttackSurface.DIRECT_CHAT
