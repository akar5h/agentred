from __future__ import annotations

from harness.core.schemas import ExplorationTrace, TraceStep
from harness.explorer.summarizer import Summarizer


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
