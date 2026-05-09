from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from grafted.attack.synthesis.chain_strategy import ChainStrategy


def _strategy(api_key: str = "k", max_rpm: int = 10) -> ChainStrategy:
    return ChainStrategy(
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        api_key=api_key,
        model="anthropic/claude-sonnet-4-6",
        max_requests_per_minute=max_rpm,
    )


def test_compliance_classifier_hard_refusal() -> None:
    s = _strategy()
    assert s._classify_compliance("I cannot do that request.") == "REFUSAL_HARD"


def test_compliance_classifier_soft_refusal() -> None:
    s = _strategy()
    assert s._classify_compliance("However, I'd rather not continue.") == "REFUSAL_SOFT"


def test_compliance_classifier_compliant() -> None:
    s = _strategy()
    assert s._classify_compliance("Here is the information you requested.") == "COMPLIANT"


def test_compliance_classifier_partial() -> None:
    s = _strategy()
    assert s._classify_compliance("I can provide some basic details only.") == "PARTIAL"


def test_compliance_classifier_evasive() -> None:
    s = _strategy()
    assert s._classify_compliance("The weather is nice today.") == "EVASIVE"


@pytest.mark.asyncio
async def test_next_turn_passthrough() -> None:
    s = _strategy()
    out = await s.next_turn(
        scenario_id="S1",
        objective="obj",
        base_turn="X",
        transcript=[],
    )
    assert out == "X"


@pytest.mark.asyncio
async def test_generate_next_turn_returns_stop(monkeypatch) -> None:
    s = _strategy()
    monkeypatch.setattr(s, "_call_openrouter", AsyncMock(return_value="STOP"))
    out = await s.generate_next_turn(
        scenario_id="S1",
        objective="exfil",
        transcript=[{"role": "assistant", "content": "generic response"}],
    )
    assert out == "STOP"


@pytest.mark.asyncio
async def test_generate_next_turn_returns_turn_text(monkeypatch) -> None:
    s = _strategy()
    monkeypatch.setattr(s, "_call_openrouter", AsyncMock(return_value="attack text"))
    out = await s.generate_next_turn(
        scenario_id="S1",
        objective="exfil",
        transcript=[{"role": "assistant", "content": "generic response"}],
    )
    assert out == "attack text"


@pytest.mark.asyncio
async def test_generate_next_turn_no_api_key() -> None:
    s = _strategy(api_key="")
    out = await s.generate_next_turn(
        scenario_id="S1",
        objective="exfil",
        transcript=[{"role": "assistant", "content": "generic response"}],
    )
    assert out == ""


@pytest.mark.asyncio
async def test_rate_limit_respected(monkeypatch) -> None:
    s = _strategy(max_rpm=30)  # 2.0s minimum spacing
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    # Keep monotonic pinned; second call should wait full min spacing.
    monkeypatch.setattr("grafted.attack.synthesis.chain_strategy.time.monotonic", lambda: 100.0)
    monkeypatch.setattr("grafted.attack.synthesis.chain_strategy.asyncio.sleep", fake_sleep)

    await s._respect_rate_limit()
    await s._respect_rate_limit()

    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 2.0
