from __future__ import annotations

import asyncio
import json

import pytest

from harness.core.schemas import ExplorationTask
from harness.explorer.explorer import Explorer


class FakeVictim:
    def __init__(self, scripted: list[dict], base_url: str = "http://fake"):
        self.base_url = base_url
        self._scripted = scripted
        self._step_index: dict[str, int] = {}
        self._docs: dict[str, list[dict]] = {}
        self.list_docs_timeouts: list[float] = []
        self.send_turn_timeouts: list[float] = []

    async def reset_session(self, session_id: str, *, timeout: float = 10.0) -> None:
        del timeout
        self._step_index[session_id] = 0
        self._docs[session_id] = []

    async def list_docs(self, session_id: str, *, timeout: float = 30.0) -> list[dict]:
        self.list_docs_timeouts.append(timeout)
        del timeout
        return [dict(d) for d in self._docs.get(session_id, [])]

    async def send_turn(
        self,
        session_id: str,
        message: str,
        *,
        mode: str = "chat",
        timeout: float = 120.0,
    ) -> dict:
        self.send_turn_timeouts.append(timeout)
        del mode, timeout, message
        index = self._step_index.get(session_id, 0)
        payload = self._scripted[min(index, len(self._scripted) - 1)] if self._scripted else {"response": ""}
        self._step_index[session_id] = index + 1
        await asyncio.sleep(0.002)

        new_doc = payload.get("new_doc")
        if new_doc:
            docs = self._docs.setdefault(session_id, [])
            docs.append({"id": len(docs) + 1, "filename": str(new_doc)})

        return {"response": str(payload.get("response", "")), "usage": {}}

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


@pytest.mark.asyncio
async def test_explorer_infers_doc_created() -> None:
    victim = FakeVictim(
        [
            {"response": "hello"},
            {"response": "saved", "new_doc": "note.md"},
        ]
    )
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t1", description="doc create", turns=["hi", "save this"])

    trace = await explorer.run_task(task)

    assert len(trace.steps) == 2
    assert "doc_created" in trace.steps[1].inferred_actions


@pytest.mark.asyncio
async def test_explorer_infers_doc_read_hint() -> None:
    victim = FakeVictim(
        [
            {"response": "saved", "new_doc": "policy.md"},
            {"response": "I used policy.md to generate the answer."},
        ]
    )
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t2", description="doc read hint", turns=["save", "summarize"])

    trace = await explorer.run_task(task)

    assert "doc_read_hint" in trace.steps[1].inferred_actions


@pytest.mark.asyncio
async def test_explorer_no_side_effects_has_empty_inferred_actions() -> None:
    victim = FakeVictim([{"response": "Understood. How can I help?"}])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t3", description="plain chat", turns=["hello"])

    trace = await explorer.run_task(task)

    assert trace.steps[0].inferred_actions == []


@pytest.mark.asyncio
async def test_explorer_captures_latency() -> None:
    victim = FakeVictim([{"response": "ok"}, {"response": "ok2"}])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t4", description="latency", turns=["a", "b"])

    trace = await explorer.run_task(task)

    assert all(step.duration_ms > 0 for step in trace.steps)


@pytest.mark.asyncio
async def test_explorer_run_all_prepends_memory_biased_tasks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    memory_dir = tmp_path / "reports" / "eng-bias" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "findings.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"scenario_id": "S1", "attack_surface": "direct_chat", "vessel_kind": "direct_prompt", "technique_family": "x", "oracle_codes_fired": [], "winning_turn": "a", "canary_confirmed": False, "cycle": 0}),
                json.dumps({"scenario_id": "S2", "attack_surface": "direct_chat", "vessel_kind": "direct_prompt", "technique_family": "y", "oracle_codes_fired": [], "winning_turn": "b", "canary_confirmed": False, "cycle": 1}),
            ]
        ),
        encoding="utf-8",
    )

    victim = FakeVictim([{"response": "ok"}])
    explorer = Explorer(victim)
    base_task = ExplorationTask(task_id="base-1", description="base", turns=["hello"])

    traces = await explorer.run_all([base_task], engagement_id="eng-bias")

    assert len(traces) >= 3
    assert traces[0].task_id.startswith("focused-direct_chat-")


@pytest.mark.asyncio
async def test_explorer_passes_timeout_to_victim_calls() -> None:
    victim = FakeVictim([{"response": "ok"}])
    explorer = Explorer(victim, timeout_seconds=42.0)
    task = ExplorationTask(task_id="t-timeout", description="timeout", turns=["hello"])

    await explorer.run_task(task)

    assert victim.send_turn_timeouts == [42.0]
    assert victim.list_docs_timeouts == [42.0, 42.0]
