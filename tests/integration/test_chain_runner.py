from __future__ import annotations

from collections.abc import Sequence

import pytest

from harness.attack.base import AttackStrategy
from harness.attack.catalog.loader import load_test_specs
from harness.attack.synthesis.static_strategy import StaticStrategy
from harness.campaign.runner import CampaignRunner
from harness.core.schemas import RunConfig, TestSpec
from harness.oracle.pattern_oracle import PatternOracle
from harness.telemetry.emitter import TelemetryEmitter


class FakeVictim:
    async def send_turn(
        self,
        session_id: str,
        message: str,
        *,
        mode: str = "chat",
        timeout: float = 120.0,
    ) -> dict:
        del session_id, message, mode, timeout
        return {"response": "Understood. How can I help you with your documents?"}

    async def upload_file(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        timeout: float = 120.0,
    ) -> dict:
        del session_id, filename, content, content_type, timeout
        return {}

    async def list_docs(self, session_id: str, *, timeout: float = 30.0) -> list[dict]:
        del session_id, timeout
        return []

    async def reset_session(self, session_id: str, *, timeout: float = 10.0) -> None:
        del session_id, timeout
        return None


class MockChainStrategy(AttackStrategy):
    def __init__(self, outputs: Sequence[str]):
        self._outputs = list(outputs)
        self._idx = 0

    @property
    def is_adaptive(self) -> bool:
        return True

    async def next_turn(
        self,
        *,
        scenario_id: str,
        objective: str,
        base_turn: str,
        transcript: list[dict],
        finding_memory=None,
        current_surface=None,
        current_technique=None,
    ) -> str:
        del scenario_id, objective, transcript, finding_memory, current_surface, current_technique
        return base_turn

    async def generate_next_turn(
        self,
        *,
        scenario_id: str,
        objective: str,
        transcript: list[dict],
        finding_memory=None,
    ) -> str:
        del scenario_id, objective, transcript, finding_memory
        if self._idx >= len(self._outputs):
            return "STOP"
        out = self._outputs[self._idx]
        self._idx += 1
        return out


def _config(tmp_path) -> RunConfig:
    return RunConfig(
        catalog_path="harness/attack/library/direct/direct_chat_injection_v1.json",
        base_url="http://test",
        run_dir=str(tmp_path),
    )


def _spec(chain_mode: bool, turns: list[str], max_chain_turns: int = 8) -> TestSpec:
    return TestSpec(
        scenario_id="CHAIN-TEST-01",
        suite_id="deepagent_chain_v1",
        turns=turns,
        chain_mode=chain_mode,
        max_chain_turns=max_chain_turns,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chain_mode_stops_on_stop_signal(tmp_path) -> None:
    strategy = MockChainStrategy(["turn-1", "turn-2", "turn-3", "STOP"])
    with TelemetryEmitter(tmp_path / "telemetry.jsonl") as emitter:
        runner = CampaignRunner(
            victim=FakeVictim(),
            strategy=strategy,
            judge=PatternOracle(),
            emitter=emitter,
            config=_config(tmp_path),
        )
        result = await runner.run_one(_spec(chain_mode=True, turns=["fallback"], max_chain_turns=8))
    assert result.turn_count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chain_mode_respects_max_chain_turns(tmp_path) -> None:
    strategy = MockChainStrategy(["x"] * 20)
    with TelemetryEmitter(tmp_path / "telemetry.jsonl") as emitter:
        runner = CampaignRunner(
            victim=FakeVictim(),
            strategy=strategy,
            judge=PatternOracle(),
            emitter=emitter,
            config=_config(tmp_path),
        )
        result = await runner.run_one(_spec(chain_mode=True, turns=["fallback"], max_chain_turns=5))
    assert result.turn_count == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chain_mode_disabled_uses_static_loop(tmp_path) -> None:
    with TelemetryEmitter(tmp_path / "telemetry.jsonl") as emitter:
        runner = CampaignRunner(
            victim=FakeVictim(),
            strategy=StaticStrategy(),
            judge=PatternOracle(),
            emitter=emitter,
            config=_config(tmp_path),
        )
        result = await runner.run_one(_spec(chain_mode=False, turns=["a", "b", "c"]))
    assert result.turn_count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chain_mode_not_implemented_exits_immediately(tmp_path) -> None:
    with TelemetryEmitter(tmp_path / "telemetry.jsonl") as emitter:
        runner = CampaignRunner(
            victim=FakeVictim(),
            strategy=StaticStrategy(),  # inherits default generate_next_turn -> NotImplementedError
            judge=PatternOracle(),
            emitter=emitter,
            config=_config(tmp_path),
        )
        result = await runner.run_one(_spec(chain_mode=True, turns=["a"], max_chain_turns=5))
    assert result.turn_count == 0


def test_chain_mode_catalog_loads() -> None:
    _, specs = load_test_specs("harness/attack/library/deepagent/deepagent_chain_v1.json")
    assert len(specs) == 8
    assert all(s.chain_mode is True for s in specs)
    assert all(s.max_chain_turns >= 5 for s in specs)
