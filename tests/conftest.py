from __future__ import annotations

import pytest


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
