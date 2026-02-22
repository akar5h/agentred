from __future__ import annotations

from harness.core.enums import FailureReason, Status
from harness.core.schemas import JudgeResult
from harness.reflection.controller import ReflectionController


def make_result(status, notes=None, flags=None):
    return JudgeResult(
        run_id="r1",
        scenario_id="LB-01",
        suite_id="direct_chat_injection_v1",
        status=status,
        notes=notes or [],
        hard_flags=flags or {},
    )


def make_obs(responses=None, write_delta=0, canary_token="", response_concat=""):
    return {
        "responses": responses or [],
        "write_delta": write_delta,
        "canary_token": canary_token,
        "response_concat": response_concat or " ".join(responses or []),
    }


rc = ReflectionController()


def test_success_has_no_failure_reason():
    r = make_result(Status.SUCCESS)
    out = rc.reflect(r, make_obs())
    assert out.failure_reason is None


def test_infra_fail_maps_to_not_surfaced():
    r = make_result(Status.INFRA_FAIL)
    out = rc.reflect(r, make_obs())
    assert out.failure_reason == FailureReason.NOT_SURFACED
    assert out.suggested_variant != ""


def test_blocked_with_refusal_is_defense_triggered():
    r = make_result(Status.BLOCKED, notes=["refusal language detected"])
    out = rc.reflect(r, make_obs(responses=["I cannot do that"]))
    assert out.failure_reason == FailureReason.DEFENSE_TRIGGERED


def test_blocked_empty_response_is_not_surfaced():
    r = make_result(Status.BLOCKED)
    out = rc.reflect(r, make_obs(responses=[]))
    assert out.failure_reason == FailureReason.NOT_SURFACED


def test_blocked_response_no_signals_is_ignored():
    r = make_result(Status.BLOCKED)
    out = rc.reflect(r, make_obs(responses=["Understood, how can I help?"]))
    assert out.failure_reason == FailureReason.IGNORED


def test_partial_with_refusal_is_defense_triggered():
    r = make_result(Status.PARTIAL, notes=["refusal language detected"])
    out = rc.reflect(r, make_obs())
    assert out.failure_reason == FailureReason.DEFENSE_TRIGGERED


def test_injection_with_no_write_is_env_constraint():
    r = make_result(Status.INJECTION, flags={"canary_exfiltrated": True})
    out = rc.reflect(r, make_obs(write_delta=0, canary_token="CANARY_abc"))
    assert out.failure_reason == FailureReason.ENV_CONSTRAINT


def test_suggested_variant_is_non_empty_for_all_non_success():
    for status in [Status.BLOCKED, Status.PARTIAL, Status.INJECTION, Status.INFRA_FAIL]:
        r = make_result(status)
        out = rc.reflect(r, make_obs(responses=["ok"]))
        assert out.suggested_variant != "", "empty variant for %s" % status
