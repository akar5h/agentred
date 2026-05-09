from __future__ import annotations

import pytest

from grafted.core.enums import AttackSurface, Status
from grafted.core.schemas import JudgeResult, TestSpec


@pytest.fixture
def base_obs():
    """Minimal valid observation dict for oracle tests."""
    return {
        "ok": True,
        "error": "",
        "response_concat": "",
        "write_delta": 0,
        "max_identical_assistant_turns": 0,
        "canary_token": "",
        "suite_id": "",
        "expected": {},
        "new_docs_sample": [],
        "transcript": [],
        "responses": [],
    }


@pytest.fixture
def canary() -> str:
    return "CANARY_deadbeef"


# ---------------------------------------------------------------------------
# Shared test-data factories (used by test_bandit, test_strategic_memory,
# test_finding_card, and potentially E2E tests)
# ---------------------------------------------------------------------------

def make_spec(**overrides) -> TestSpec:
    """Build a TestSpec with sensible defaults. Accepts any TestSpec field override."""
    defaults = dict(
        scenario_id="sc1",
        suite_id="su1",
        turns=["Turn 1", "Turn 2"],
        oracle_codes=[],
        attack_surface=AttackSurface.DIRECT_CHAT,
        technique_family="prompt_injection",
        owasp=["LLM01"],
        atlas=["AML.T0051"],
    )
    defaults.update(overrides)
    return TestSpec(**defaults)


def make_result(status: Status = Status.SUCCESS, **overrides) -> JudgeResult:
    """Build a JudgeResult with sensible defaults. Accepts any JudgeResult field override."""
    defaults = dict(
        run_id="r1",
        scenario_id="sc1",
        suite_id="su1",
        status=status,
        hard_flags={},
        soft_success=False,
        final_response="response text",
        canary_token="CANARY_abc",
    )
    defaults.update(overrides)
    return JudgeResult(**defaults)
