"""Phase T-0: Connectivity & Surface Discovery tests against a live HR AI target."""
from __future__ import annotations

import pytest

from harness.core.schemas import ExplorationTask, TelemetryEvent
from harness.explorer import Explorer, Summarizer
from harness.telemetry.emitter import TelemetryEmitter
from harness.victim.hr_api_adapter import HrApiAdapter

pytestmark = pytest.mark.e2e


# ======================================================================
# T-0 Connectivity
# ======================================================================


class TestT0Connectivity:
    """Basic connectivity and adapter lifecycle tests."""

    async def test_health_check(self, victim_adapter: HrApiAdapter):
        result = await victim_adapter.health()
        assert isinstance(result, dict)
        # Health response may be flat {"database": "ok"} or nested {"database": {"status": "ok"}}
        db = result.get("database")
        if isinstance(db, dict):
            assert db.get("status") == "ok"
        else:
            assert db == "ok"

    async def test_send_turn(self, victim_adapter: HrApiAdapter):
        result = await victim_adapter.send_turn("t0-send-turn", "Hello, who are you?")
        assert isinstance(result, dict)
        assert "response" in result
        assert len(result["response"]) > 0

    async def test_session_lifecycle(self, victim_adapter: HrApiAdapter):
        sid = "t0-lifecycle"
        # First reset creates a session
        await victim_adapter.reset_session(sid)
        assert sid in victim_adapter._session_map

        # Send a turn
        r1 = await victim_adapter.send_turn(sid, "Hi")
        assert r1["response"]

        # Reset again — old mapping replaced
        old_server_id = victim_adapter._session_map[sid]
        await victim_adapter.reset_session(sid)
        new_server_id = victim_adapter._session_map[sid]
        assert new_server_id != old_server_id

        # New session still works
        r2 = await victim_adapter.send_turn(sid, "Hi again")
        assert r2["response"]

    async def test_session_isolation(self, victim_adapter: HrApiAdapter):
        sid_a = "t0-isolation-a"
        sid_b = "t0-isolation-b"
        await victim_adapter.reset_session(sid_a)
        await victim_adapter.reset_session(sid_b)

        # Different server session IDs
        assert victim_adapter._session_map[sid_a] != victim_adapter._session_map[sid_b]

        # Each session works independently
        ra = await victim_adapter.send_turn(sid_a, "Session A says hello")
        rb = await victim_adapter.send_turn(sid_b, "Session B says hello")
        assert ra["response"]
        assert rb["response"]

    async def test_upload_file(self, victim_adapter: HrApiAdapter):
        sid = "t0-upload"
        await victim_adapter.reset_session(sid)
        result = await victim_adapter.upload_file(
            sid,
            "test_resume.pdf",
            b"%PDF-1.4 fake resume content",
            "application/pdf",
        )
        assert isinstance(result, dict)
        assert "filename" in result or "path" in result

    async def test_list_docs(self, victim_adapter: HrApiAdapter):
        sid = "t0-list-docs"
        await victim_adapter.reset_session(sid)

        # list_docs maps to GET /history/uploads which returns evaluate-based entries.
        # Verify it returns a list (may include prior uploads from other sessions).
        docs = await victim_adapter.list_docs(sid)
        assert isinstance(docs, list)
        # Each entry should be a dict with expected keys
        for entry in docs:
            assert isinstance(entry, dict)


# ======================================================================
# T-0 Surface Discovery
# ======================================================================


class TestT0SurfaceDiscovery:
    """Explorer + Summarizer integration against live target."""

    async def test_explorer_produces_traces(
        self, victim_adapter: HrApiAdapter, default_tasks: list[ExplorationTask]
    ):
        explorer = Explorer(victim_adapter)
        traces = await explorer.run_all(default_tasks)
        assert len(traces) >= 1
        # At least one trace should have steps
        has_steps = any(len(t.steps) >= 1 for t in traces)
        assert has_steps, "Expected at least one trace with >=1 step"

    async def test_summarizer_infers_surfaces(
        self, victim_adapter: HrApiAdapter, default_tasks: list[ExplorationTask]
    ):
        explorer = Explorer(victim_adapter)
        traces = await explorer.run_all(default_tasks)
        summarizer = Summarizer()
        surfaces_found: set[str] = set()
        for trace in traces:
            if trace.steps:
                summary = summarizer.summarize(trace)
                surfaces_found.update(summary.inferred_surfaces)
        assert len(surfaces_found) >= 1, f"Expected >=1 inferred surface, got {surfaces_found}"

    async def test_telemetry_file_created(
        self, victim_adapter: HrApiAdapter, default_tasks: list[ExplorationTask], tmp_path
    ):
        jsonl_path = tmp_path / "telemetry" / "events.jsonl"
        with TelemetryEmitter(jsonl_path) as emitter:
            explorer = Explorer(victim_adapter)
            traces = await explorer.run_all(default_tasks)
            for trace in traces:
                for step in trace.steps:
                    emitter.emit(TelemetryEvent(
                        run_id="t0-telemetry-test",
                        scenario_id=trace.task_id,
                        suite_id="e2e-t0",
                        event_type="exploration_step",
                        turn_index=step.turn_index,
                        content=step.response[:200],
                    ))
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) >= 1, "Expected at least 1 telemetry event"
