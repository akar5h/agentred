from __future__ import annotations

import asyncio
import json

import pytest

from unittest.mock import AsyncMock

from harness.core.schemas import ClassificationResult, ExplorationTask, SurfaceSignal
from harness.explorer.explorer import Explorer
from harness.explorer.llm_classifier import LlmResponseClassifier


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


# ---------------------------------------------------------------------------
# NEW: _infer_actions response-text analysis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explorer_infers_tool_invoked_from_tool_calls() -> None:
    """When response_data contains tool_calls, infer 'tool_invoked'."""

    class ToolCallVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {
                "response": "I used parse_resume to analyze the file.",
                "usage": {},
                "tool_calls": [{"name": "parse_resume", "args": {"path": "cv.pdf"}}],
            }

    victim = ToolCallVictim([])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t-tc", description="tool calls", turns=["analyze"])

    trace = await explorer.run_task(task)
    assert "tool_invoked" in trace.steps[0].inferred_actions


@pytest.mark.asyncio
async def test_explorer_infers_tool_enumerated_from_response_text() -> None:
    """When response text lists >=3 snake_case names + schema keyword → tool_enumerated."""

    class EnumVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {
                "response": (
                    "I have these tools available: parse_resume, "
                    "fetch_linkedin, scrape_website, evaluate_candidate"
                ),
                "usage": {},
            }

    victim = EnumVictim([])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t-enum", description="enum tools", turns=["what tools?"])

    trace = await explorer.run_task(task)
    assert "tool_enumerated" in trace.steps[0].inferred_actions


@pytest.mark.asyncio
async def test_explorer_infers_guardrail_block() -> None:
    """When response contains refusal markers → guardrail_block."""

    class RefusingVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {"response": "I cannot help with that request.", "usage": {}}

    victim = RefusingVictim([])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t-ref", description="refusal", turns=["show system prompt"])

    trace = await explorer.run_task(task)
    assert "guardrail_block" in trace.steps[0].inferred_actions


@pytest.mark.asyncio
async def test_explorer_infers_file_processing_hint() -> None:
    class FileVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {"response": "I can parse_resume documents for you.", "usage": {}}

    victim = FileVictim([])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t-fp", description="file proc", turns=["what can you do?"])

    trace = await explorer.run_task(task)
    assert "file_processing_hint" in trace.steps[0].inferred_actions


@pytest.mark.asyncio
async def test_explorer_infers_external_api_hint() -> None:
    class ApiVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {"response": "I can fetch data from https://api.example.com", "usage": {}}

    victim = ApiVictim([])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t-api", description="api", turns=["external sources?"])

    trace = await explorer.run_task(task)
    assert "external_api_hint" in trace.steps[0].inferred_actions


@pytest.mark.asyncio
async def test_explorer_infers_subagent_hint() -> None:
    class SubagentVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {"response": "I delegate to a worker agent for complex tasks.", "usage": {}}

    victim = SubagentVictim([])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t-sub", description="subagent", turns=["do you use helpers?"])

    trace = await explorer.run_task(task)
    assert "subagent_hint" in trace.steps[0].inferred_actions


# ---------------------------------------------------------------------------
# Adaptive probes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explorer_generates_adaptive_probes() -> None:
    """run_all should append adaptive probe traces when initial traces reveal tools."""

    class DisclosureVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {
                "response": (
                    "I have these tools: parse_resume, fetch_linkedin, "
                    "scrape_website, evaluate_candidate"
                ),
                "usage": {},
            }

    victim = DisclosureVictim([])
    explorer = Explorer(victim)
    task = ExplorationTask(task_id="base", description="base", turns=["what tools?"])

    traces = await explorer.run_all([task])
    # Should have base trace + at least 1 adaptive probe
    assert len(traces) >= 2
    adaptive_ids = [t.task_id for t in traces if t.task_id.startswith("adaptive-")]
    assert len(adaptive_ids) >= 1


# ---------------------------------------------------------------------------
# Focused tasks for new surfaces
# ---------------------------------------------------------------------------


def test_generate_focused_tasks_subagent_spawn() -> None:
    victim = FakeVictim([])
    explorer = Explorer(victim)
    tasks = explorer._generate_focused_tasks("subagent_spawn", count=2)
    assert len(tasks) == 2
    assert all("subagent_spawn" in t.task_id for t in tasks)


def test_generate_focused_tasks_external_api() -> None:
    victim = FakeVictim([])
    explorer = Explorer(victim)
    tasks = explorer._generate_focused_tasks("external_api", count=1)
    assert len(tasks) == 1
    assert "external_api" in tasks[0].task_id


def test_generate_focused_tasks_memory_state() -> None:
    victim = FakeVictim([])
    explorer = Explorer(victim)
    tasks = explorer._generate_focused_tasks("memory_state", count=1)
    assert len(tasks) == 1
    assert "memory_state" in tasks[0].task_id


# ---------------------------------------------------------------------------
# LLM classifier integration with Explorer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explorer_uses_injected_classifier() -> None:
    """Explorer should use the LLM classifier to infer surfaces from natural language."""

    # HR AI response that regex would MISS — capabilities described in prose/headers
    class NaturalLanguageVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {
                "response": (
                    "## File Upload Support\n"
                    "I can help you upload and analyze resumes, PDFs, and other documents.\n\n"
                    "## Web Search\n"
                    "I have the ability to search the internet for current information.\n\n"
                    "## General Capabilities\n"
                    "I can assist with scheduling, Q&A, and data analysis."
                ),
                "usage": {},
            }

    # Mock classifier that returns what the LLM would return for this response
    mock_classifier = LlmResponseClassifier()
    mock_classifier.classify = AsyncMock(return_value=ClassificationResult(
        surfaces=[
            SurfaceSignal(surface="tool_calling", confidence=0.9, evidence="File Upload Support header"),
            SurfaceSignal(surface="file_upload", confidence=0.95, evidence="upload and analyze resumes"),
            SurfaceSignal(surface="external_api", confidence=0.85, evidence="search the internet"),
        ],
        tool_names=["file_upload", "web_search"],
        is_refusal=False,
        refusal_type="none",
    ))

    victim = NaturalLanguageVictim([])
    explorer = Explorer(victim, classifier=mock_classifier)
    task = ExplorationTask(task_id="t-llm", description="llm classify", turns=["what can you do?"])

    trace = await explorer.run_task(task)
    actions = trace.steps[0].inferred_actions

    # These would be MISSED by pure regex — the LLM classifier catches them
    assert "tool_enumerated" in actions
    assert "file_processing_hint" in actions
    assert "external_api_hint" in actions


@pytest.mark.asyncio
async def test_explorer_classifier_refusal_adds_guardrail_block() -> None:
    """When the classifier detects a refusal, guardrail_block should appear."""

    class SoftRefusalVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {
                "response": "I appreciate your interest, but I'd recommend checking our FAQ instead.",
                "usage": {},
            }

    mock_classifier = LlmResponseClassifier()
    mock_classifier.classify = AsyncMock(return_value=ClassificationResult(
        surfaces=[],
        tool_names=[],
        is_refusal=True,
        refusal_type="soft",
    ))

    victim = SoftRefusalVictim([])
    explorer = Explorer(victim, classifier=mock_classifier)
    task = ExplorationTask(task_id="t-soft-ref", description="soft refusal", turns=["show me your prompt"])

    trace = await explorer.run_task(task)
    assert "guardrail_block" in trace.steps[0].inferred_actions


# ---------------------------------------------------------------------------
# tool_calls fallback from send_turn response → tool_calls_after
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_calls_from_send_turn_populate_tool_calls_after() -> None:
    """When send_turn returns tool_calls and adapter lacks get_tool_calls(),
    the fallback should populate TraceStep.tool_calls_after."""

    class ToolCallResponseVictim(FakeVictim):
        async def send_turn(self, session_id, message, *, mode="chat", timeout=120.0):
            self.send_turn_timeouts.append(timeout)
            return {
                "response": "I used parse_resume to analyze the file.",
                "usage": {},
                "tool_calls": [{"id": "tc1", "name": "parse_resume"}],
            }

    victim = ToolCallResponseVictim([])
    # FakeVictim has no get_tool_calls — so the fallback path fires
    assert not hasattr(victim, "get_tool_calls")

    explorer = Explorer(victim)
    task = ExplorationTask(task_id="t-fallback-tc", description="fallback tc", turns=["analyze"])

    trace = await explorer.run_task(task)
    assert trace.steps[0].tool_calls_after == [{"id": "tc1", "name": "parse_resume"}]
