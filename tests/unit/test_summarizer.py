from __future__ import annotations

from grafted.core.schemas import ExplorationTrace, TraceStep
from grafted.explorer.summarizer import Summarizer


def _step(
    *,
    turn_index: int,
    response: str,
    docs_before: list[dict],
    docs_after: list[dict],
    inferred_actions: list[str] | None = None,
) -> TraceStep:
    return TraceStep(
        turn_index=turn_index,
        message_sent=f"turn-{turn_index}",
        response=response,
        docs_before=docs_before,
        docs_after=docs_after,
        duration_ms=1,
        inferred_actions=inferred_actions or [],
    )


def test_summarizer_classifies_doc_created() -> None:
    trace = ExplorationTrace(
        task_id="t1",
        session_id="s1",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="saved",
                docs_before=[],
                docs_after=[{"id": 1, "filename": "note.md"}],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "doc_created"
    assert out.steps[0].artifact_ref == "note.md"


def test_summarizer_classifies_doc_read_hint() -> None:
    trace = ExplorationTrace(
        task_id="t2",
        session_id="s2",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I used policy.md to respond.",
                docs_before=[{"id": 1, "filename": "policy.md"}],
                docs_after=[{"id": 1, "filename": "policy.md"}],
                inferred_actions=["doc_read_hint"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "doc_read_hint"
    assert out.steps[0].artifact_ref == "policy.md"


def test_summarizer_classifies_state_change_when_doc_count_shrinks() -> None:
    trace = ExplorationTrace(
        task_id="t3",
        session_id="s3",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="state changed",
                docs_before=[{"id": 1}, {"id": 2}],
                docs_after=[{"id": 1}],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "state_change"


def test_summarizer_classifies_chat_turn_without_state_changes() -> None:
    trace = ExplorationTrace(
        task_id="t4",
        session_id="s4",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="plain chat",
                docs_before=[{"id": 1, "filename": "a.md"}],
                docs_after=[{"id": 1, "filename": "a.md"}],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "chat_turn"


def test_summarizer_infers_surfaces_from_step_types() -> None:
    trace = ExplorationTrace(
        task_id="t5",
        session_id="s5",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="uploaded",
                docs_before=[],
                docs_after=[],
                inferred_actions=["file_upload"],
            ),
            _step(
                turn_index=1,
                response="saved",
                docs_before=[],
                docs_after=[{"id": 1, "filename": "x.md"}],
            ),
            _step(
                turn_index=2,
                response="chat",
                docs_before=[{"id": 1, "filename": "x.md"}],
                docs_after=[{"id": 1, "filename": "x.md"}],
            ),
            _step(
                turn_index=3,
                response="changed",
                docs_before=[{"id": 1}, {"id": 2}],
                docs_after=[{"id": 1}],
            ),
        ],
    )
    out = Summarizer().summarize(trace)
    assert "file_upload" in out.inferred_surfaces
    assert "doc_memory" in out.inferred_surfaces
    assert "chat_direct" in out.inferred_surfaces
    assert "state_unknown_write" in out.inferred_surfaces


# ---------------------------------------------------------------------------
# NEW: text-derived step types
# ---------------------------------------------------------------------------


def test_summarizer_classifies_tool_enumerated() -> None:
    trace = ExplorationTrace(
        task_id="t-te",
        session_id="s-te",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I have parse_resume, fetch_linkedin, scrape_website tools",
                docs_before=[],
                docs_after=[],
                inferred_actions=["tool_enumerated"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "tool_enumerated"
    assert "tool_calling" in out.inferred_surfaces


def test_summarizer_classifies_tool_invoked_from_inferred() -> None:
    trace = ExplorationTrace(
        task_id="t-ti",
        session_id="s-ti",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="Used parse_resume on your file",
                docs_before=[],
                docs_after=[],
                inferred_actions=["tool_invoked"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "tool_invoked"
    assert "tool_calling" in out.inferred_surfaces


def test_summarizer_classifies_file_processing_hint() -> None:
    trace = ExplorationTrace(
        task_id="t-fp",
        session_id="s-fp",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I can process documents for you",
                docs_before=[],
                docs_after=[],
                inferred_actions=["file_processing_hint"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "file_processing_hint"
    assert "file_upload" in out.inferred_surfaces


def test_summarizer_classifies_external_api_hint() -> None:
    trace = ExplorationTrace(
        task_id="t-ea",
        session_id="s-ea",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I can fetch from external APIs",
                docs_before=[],
                docs_after=[],
                inferred_actions=["external_api_hint"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "external_api_hint"
    assert "external_api" in out.inferred_surfaces


def test_summarizer_classifies_subagent_hint() -> None:
    trace = ExplorationTrace(
        task_id="t-sa",
        session_id="s-sa",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I delegate to worker agents",
                docs_before=[],
                docs_after=[],
                inferred_actions=["subagent_hint"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "subagent_hint"
    assert "subagent_spawn" in out.inferred_surfaces


def test_summarizer_classifies_guardrail_block() -> None:
    trace = ExplorationTrace(
        task_id="t-gb",
        session_id="s-gb",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I cannot help with that",
                docs_before=[],
                docs_after=[],
                inferred_actions=["guardrail_block"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "guardrail_block"
    assert "chat_direct" in out.inferred_surfaces


def test_summarizer_all_signals_preserves_multi_signal_steps() -> None:
    """A step with multiple inferred_actions should have all of them in
    all_signals, and all should map to inferred_surfaces."""
    trace = ExplorationTrace(
        task_id="t-multi",
        session_id="s-multi",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I used tools, called APIs, and delegated to sub-agents",
                docs_before=[],
                docs_after=[],
                inferred_actions=[
                    "tool_enumerated",
                    "external_api_hint",
                    "subagent_hint",
                    "memory_state_hint",
                ],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    # step_type is the priority winner (tool_enumerated wins)
    assert out.steps[0].step_type == "tool_enumerated"
    # all_signals preserves every signal
    assert set(out.steps[0].all_signals) == {
        "tool_enumerated",
        "external_api_hint",
        "subagent_hint",
        "memory_state_hint",
    }
    # _infer_surfaces should see all signals, not just step_type
    assert "tool_calling" in out.inferred_surfaces
    assert "external_api" in out.inferred_surfaces
    assert "subagent_spawn" in out.inferred_surfaces
    assert "memory_state" in out.inferred_surfaces


def test_summarizer_classifies_memory_state_hint() -> None:
    trace = ExplorationTrace(
        task_id="t-ms",
        session_id="s-ms",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="I store conversation context in memory",
                docs_before=[],
                docs_after=[],
                inferred_actions=["memory_state_hint"],
            )
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.steps[0].step_type == "memory_state_hint"
    assert "memory_state" in out.inferred_surfaces


def test_summarizer_deduplicates_surfaces() -> None:
    """Both structural tool_invoked and text-based tool_enumerated should emit
    tool_calling only once."""
    trace = ExplorationTrace(
        task_id="t-dedup",
        session_id="s-dedup",
        target_base_url="http://fake",
        steps=[
            _step(
                turn_index=0,
                response="tools listed",
                docs_before=[],
                docs_after=[],
                inferred_actions=["tool_enumerated"],
            ),
            _step(
                turn_index=1,
                response="tool used",
                docs_before=[],
                docs_after=[],
                inferred_actions=["tool_invoked"],
            ),
        ],
    )
    out = Summarizer().summarize(trace)
    assert out.inferred_surfaces.count("tool_calling") == 1
