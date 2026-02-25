from __future__ import annotations

from harness.core.schemas import ExecutionStep, ExplorationTrace, SummarizedTrace, TraceStep


def _doc_identifier(doc: dict) -> str:
    if not isinstance(doc, dict):
        return ""
    for key in ("name", "filename", "id"):
        value = doc.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


class Summarizer:
    def summarize(self, trace: ExplorationTrace) -> SummarizedTrace:
        steps = [self._classify_step(step) for step in trace.steps]
        surfaces = self._infer_surfaces(steps)
        return SummarizedTrace(
            trace_id=trace.task_id,
            steps=steps,
            inferred_surfaces=surfaces,
        )

    def _classify_step(self, step: TraceStep) -> ExecutionStep:
        before_ids = {_doc_identifier(d) for d in step.docs_before}
        after_ids = {_doc_identifier(d) for d in step.docs_after}
        before_ids.discard("")
        after_ids.discard("")
        new_docs = after_ids - before_ids

        if "file_upload" in step.inferred_actions:
            return ExecutionStep(
                step_type="file_upload",
                artifact_ref=None,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        # Priority order: doc_created > doc_read_hint > state_change > chat_turn
        if new_docs:
            artifact = sorted(new_docs)[0]
            return ExecutionStep(
                step_type="doc_created",
                artifact_ref=artifact,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        if "doc_read_hint" in step.inferred_actions:
            return ExecutionStep(
                step_type="doc_read_hint",
                artifact_ref=self._extract_doc_ref(step.response, step.docs_before),
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        if len(after_ids) != len(before_ids):
            return ExecutionStep(
                step_type="state_change",
                artifact_ref=None,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        # NEW: tool invoked if tool_calls_after has new IDs vs tool_calls_before
        tc_before_ids = {tc.get("id") for tc in (step.tool_calls_before or []) if isinstance(tc, dict)}
        tc_after_ids = {tc.get("id") for tc in (step.tool_calls_after or []) if isinstance(tc, dict)}
        if tc_after_ids - tc_before_ids:
            return ExecutionStep(
                step_type="tool_invoked",
                artifact_ref=None,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        # NEW: memory write if memory_after has more entries than memory_before
        if len(step.memory_after or []) > len(step.memory_before or []):
            return ExecutionStep(
                step_type="memory_write",
                artifact_ref=None,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        # TRD-17: subagent_invoked — new subagents in debug_after vs debug_before
        db_before = step.debug_before if isinstance(step.debug_before, dict) else {}
        db_after = step.debug_after if isinstance(step.debug_after, dict) else {}
        before_subagents = db_before.get("subagents", [])
        after_subagents = db_after.get("subagents", [])
        if len(after_subagents) > len(before_subagents):
            return ExecutionStep(
                step_type="subagent_invoked",
                artifact_ref=None,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        # TRD-17: external_api_called — new entries in external_calls
        before_ext = db_before.get("external_calls", [])
        after_ext = db_after.get("external_calls", [])
        if len(after_ext) > len(before_ext):
            return ExecutionStep(
                step_type="external_api_called",
                artifact_ref=None,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        # TRD-17: tool_schema_probed — tool_schemas appeared or changed
        before_schemas = db_before.get("tool_schemas", [])
        after_schemas = db_after.get("tool_schemas", [])
        if after_schemas and after_schemas != before_schemas:
            return ExecutionStep(
                step_type="tool_schema_probed",
                artifact_ref=None,
                content_preview=step.response[:200],
                turn_index=step.turn_index,
            )

        return ExecutionStep(
            step_type="chat_turn",
            artifact_ref=None,
            content_preview=step.response[:200],
            turn_index=step.turn_index,
        )

    def _infer_surfaces(self, steps: list[ExecutionStep]) -> list[str]:
        kinds = {s.step_type for s in steps}
        surfaces: list[str] = []
        if "file_upload" in kinds:
            surfaces.append("file_upload")
        if "doc_created" in kinds:
            surfaces.append("doc_memory")
        if "chat_turn" in kinds:
            surfaces.append("chat_direct")
        if "state_change" in kinds:
            surfaces.append("state_unknown_write")
        if "tool_invoked" in kinds:
            surfaces.append("tool_calling")
        if "memory_write" in kinds:
            surfaces.append("memory_write")
        if "subagent_invoked" in kinds:
            surfaces.append("subagent_spawn")
        if "external_api_called" in kinds:
            surfaces.append("external_api")
        if "tool_schema_probed" in kinds:
            surfaces.append("tool_schema")
        return surfaces

    def _extract_doc_ref(self, response: str, docs: list[dict]) -> str | None:
        lowered = str(response).lower()
        for doc in docs:
            ref = _doc_identifier(doc)
            if ref and ref.lower() in lowered:
                return ref
        return None
