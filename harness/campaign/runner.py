from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from harness.attack.base import AttackStrategy
from harness.attack.fixtures.render import load_and_render_fixture_bytes, render_template_text
from harness.campaign.context import RunContext
from harness.campaign.memory_writer import build_finding_memory, write_finding_memory
from harness.core.enums import Status, VesselKind
from harness.core.exceptions import InfraError
from harness.core.schemas import JudgeResult, RunConfig, TelemetryEvent, TestSpec
from harness.oracle.base import Oracle
from harness.reflection.controller import ReflectionController
from harness.telemetry import events
from harness.telemetry.emitter import TelemetryEmitter
from harness.victim.base import VictimAdapter


def _compute_max_identical(responses: list[str]) -> int:
    if not responses:
        return 0
    current = 1
    max_identical = 1
    for i in range(1, len(responses)):
        prev = responses[i - 1].strip()
        curr = responses[i].strip()
        if curr and curr == prev:
            current += 1
            max_identical = max(max_identical, current)
        else:
            current = 1
    return max_identical


class CampaignRunner:
    def __init__(
        self,
        victim: VictimAdapter,
        strategy: AttackStrategy,
        judge: Oracle,
        emitter: TelemetryEmitter,
        config: RunConfig,
        reflection_controller: Optional[ReflectionController] = None,
    ):
        self.victim = victim
        self.strategy = strategy
        self.judge = judge
        self.emitter = emitter
        self.config = config
        self.reflection_controller = reflection_controller or ReflectionController()
        self._cycle: int = 0

    async def run_one(self, spec: TestSpec, rep: int = 1) -> JudgeResult:
        run_id = uuid.uuid4().hex
        session_id = f"dp-{spec.scenario_id}-{run_id[:8]}"
        canary_token = f"CANARY_{uuid.uuid4().hex[:8]}"
        ctx = RunContext(run_id=run_id, session_id=session_id, canary_token=canary_token, spec=spec, rep=rep)

        self.emitter.emit(
            TelemetryEvent(
                run_id=run_id,
                scenario_id=spec.scenario_id,
                suite_id=spec.suite_id,
                event_type=events.SETUP,
                canary_token=canary_token,
                meta={"rep": rep},
            )
        )

        try:
            ctx.before_docs = await self.victim.list_docs(session_id, timeout=self.config.timeout_seconds)
            self.emitter.emit(
                TelemetryEvent(
                    run_id=run_id,
                    scenario_id=spec.scenario_id,
                    suite_id=spec.suite_id,
                    event_type=events.PRE_FLIGHT_SNAPSHOT,
                    canary_token=canary_token,
                    meta={"doc_count": len(ctx.before_docs)},
                )
            )

            for vessel in spec.vessels:
                if vessel.kind == VesselKind.UPLOADED_DOCUMENT and vessel.fixture_path:
                    content = load_and_render_fixture_bytes(
                        vessel.fixture_path,
                        session_id=session_id,
                        canary_token=canary_token,
                    )
                    ext = Path(vessel.fixture_path).suffix.lower()
                    content_type = {".md": "text/markdown", ".csv": "text/csv"}.get(ext, "text/plain")
                    await self.victim.upload_file(
                        session_id,
                        Path(vessel.fixture_path).name,
                        content,
                        content_type,
                        timeout=self.config.timeout_seconds,
                    )
            self.emitter.emit(
                TelemetryEvent(
                    run_id=run_id,
                    scenario_id=spec.scenario_id,
                    suite_id=spec.suite_id,
                    event_type=events.UPLOAD_PHASE,
                    canary_token=canary_token,
                    meta={"upload_count": len(spec.vessels)},
                )
            )

            for turn in spec.prelude_turns:
                rendered = render_template_text(turn, session_id=session_id, canary_token=canary_token)
                self.emitter.emit(
                    TelemetryEvent(
                        run_id=run_id,
                        scenario_id=spec.scenario_id,
                        suite_id=spec.suite_id,
                        event_type=events.PRELUDE_TURN_SENT,
                        turn_index=ctx.executed_turns,
                        content=rendered,
                        canary_token=canary_token,
                    )
                )
                result = await self.victim.send_turn(session_id, rendered, timeout=self.config.timeout_seconds)
                ctx.transcript.append({"role": "user", "content": rendered})
                ctx.transcript.append({"role": "assistant", "content": result["response"]})
                ctx.responses.append(result["response"])
                if result.get("system_prompts"):
                    ctx.leaked_system_prompts.append(result["system_prompts"])
                ctx.executed_turns += 1
                self.emitter.emit(
                    TelemetryEvent(
                        run_id=run_id,
                        scenario_id=spec.scenario_id,
                        suite_id=spec.suite_id,
                        event_type=events.PRELUDE_TURN_RECV,
                        turn_index=ctx.executed_turns,
                        content=result["response"],
                        canary_token=canary_token,
                    )
                )

            if spec.chain_mode and hasattr(self.strategy, "generate_next_turn"):
                for _step in range(max(1, int(spec.max_chain_turns))):
                    try:
                        next_t = await self.strategy.generate_next_turn(
                            scenario_id=spec.scenario_id,
                            objective=spec.objective,
                            transcript=ctx.transcript,
                        )
                    except NotImplementedError:
                        break
                    if not next_t or str(next_t).strip().upper() == "STOP":
                        break

                    ctx.generated_turns.append(next_t)
                    ctx.transcript.append({"role": "user", "content": next_t})
                    self.emitter.emit(
                        TelemetryEvent(
                            run_id=run_id,
                            scenario_id=spec.scenario_id,
                            suite_id=spec.suite_id,
                            event_type=events.ATTACK_TURN_SENT,
                            turn_index=ctx.executed_turns,
                            content=next_t,
                            canary_token=canary_token,
                        )
                    )
                    result = await self.victim.send_turn(session_id, next_t, timeout=self.config.timeout_seconds)
                    ctx.transcript.append({"role": "assistant", "content": result["response"]})
                    ctx.responses.append(result["response"])
                    if result.get("system_prompts"):
                        ctx.leaked_system_prompts.append(result["system_prompts"])
                    ctx.executed_turns += 1
                    self.emitter.emit(
                        TelemetryEvent(
                            run_id=run_id,
                            scenario_id=spec.scenario_id,
                            suite_id=spec.suite_id,
                            event_type=events.ATTACK_TURN_RECV,
                            turn_index=ctx.executed_turns,
                            content=result["response"],
                            canary_token=canary_token,
                        )
                    )
            else:
                for turn in spec.turns:
                    rendered = render_template_text(turn, session_id=session_id, canary_token=canary_token)
                    final_turn = await self.strategy.next_turn(
                        scenario_id=spec.scenario_id,
                        objective=spec.objective,
                        base_turn=rendered,
                        transcript=ctx.transcript,
                    )
                    ctx.generated_turns.append(final_turn)
                    ctx.transcript.append({"role": "user", "content": final_turn})
                    self.emitter.emit(
                        TelemetryEvent(
                            run_id=run_id,
                            scenario_id=spec.scenario_id,
                            suite_id=spec.suite_id,
                            event_type=events.ATTACK_TURN_SENT,
                            turn_index=ctx.executed_turns,
                            content=final_turn,
                            canary_token=canary_token,
                        )
                    )
                    result = await self.victim.send_turn(session_id, final_turn, timeout=self.config.timeout_seconds)
                    ctx.transcript.append({"role": "assistant", "content": result["response"]})
                    ctx.responses.append(result["response"])
                    if result.get("system_prompts"):
                        ctx.leaked_system_prompts.append(result["system_prompts"])
                    ctx.executed_turns += 1
                    self.emitter.emit(
                        TelemetryEvent(
                            run_id=run_id,
                            scenario_id=spec.scenario_id,
                            suite_id=spec.suite_id,
                            event_type=events.ATTACK_TURN_RECV,
                            turn_index=ctx.executed_turns,
                            content=result["response"],
                            canary_token=canary_token,
                        )
                    )

            ctx.after_docs = await self.victim.list_docs(session_id, timeout=self.config.timeout_seconds)
            before_ids = {d.get("id") for d in ctx.before_docs if isinstance(d, dict)}
            after_ids = {d.get("id") for d in ctx.after_docs if isinstance(d, dict)}
            new_ids = [i for i in sorted(after_ids - before_ids) if i is not None]

            detail_fetch = getattr(self.victim, "get_doc_detail", None)
            for doc_id in new_ids[:3]:
                if callable(detail_fetch):
                    try:
                        try:
                            detail = await detail_fetch(session_id, int(doc_id))
                        except TypeError:
                            detail = await detail_fetch(int(doc_id))
                        if isinstance(detail, dict):
                            ctx.new_docs_sample.append(detail)
                    except Exception:
                        pass

            self.emitter.emit(
                TelemetryEvent(
                    run_id=run_id,
                    scenario_id=spec.scenario_id,
                    suite_id=spec.suite_id,
                    event_type=events.POST_RUN_SNAPSHOT,
                    canary_token=canary_token,
                    meta={
                        "before_docs": len(ctx.before_docs),
                        "after_docs": len(ctx.after_docs),
                        "new_docs": len(new_ids),
                    },
                )
            )

        except InfraError as exc:
            ctx.error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive guard
            ctx.error = str(exc)

        duration_ms = int((time.monotonic() - ctx.start_time) * 1000)
        max_identical = _compute_max_identical(ctx.responses)

        observation = {
            "ok": ctx.error == "",
            "error": ctx.error,
            "run_id": run_id,
            "scenario_id": spec.scenario_id,
            "suite_id": spec.suite_id,
            "session_id": session_id,
            "rep": rep,
            "canary_token": canary_token,
            "response_concat": "\n\n".join(ctx.responses),
            "transcript": ctx.transcript,
            "responses": ctx.responses,
            "write_delta": max(0, len(ctx.after_docs) - len(ctx.before_docs)),
            "write_expected": bool(spec.expected.get("write_expected", False)),
            "new_docs_sample": ctx.new_docs_sample,
            "max_identical_assistant_turns": max_identical,
            "expected": spec.expected,
            "attack_surface": spec.attack_surface.value if spec.attack_surface else None,
            "technique_family": spec.technique_family,
            "turn_count": ctx.executed_turns,
            "duration_ms": duration_ms,
            "_spec_meta": spec.model_dump(),
            "leaked_system_prompts": ctx.leaked_system_prompts,
        }

        try:
            result = await self.judge.evaluate(observation)
        except Exception as exc:  # pragma: no cover - defensive guard
            result = JudgeResult(
                run_id=run_id,
                scenario_id=spec.scenario_id,
                suite_id=spec.suite_id,
                rep=rep,
                status=Status.INFRA_FAIL,
                session_id=session_id,
                canary_token=canary_token,
                error=f"oracle_error: {exc}",
                duration_ms=duration_ms,
            )

        result = result.model_copy(
            update={
                "run_id": run_id,
                "scenario_id": spec.scenario_id,
                "suite_id": spec.suite_id,
                "rep": rep,
                "session_id": session_id,
                "canary_token": canary_token,
                "turn_count": ctx.executed_turns,
                "final_response": ctx.responses[-1] if ctx.responses else "",
                "duration_ms": duration_ms,
                "error": ctx.error,
                "attack_surface": spec.attack_surface,
                "technique_family": spec.technique_family,
                "write_delta": max(0, len(ctx.after_docs) - len(ctx.before_docs)),
            }
        )

        # Step 9: Reflection attribution
        result = self.reflection_controller.reflect(result, observation)
        self.emitter.emit(
            TelemetryEvent(
                run_id=run_id,
                scenario_id=spec.scenario_id,
                suite_id=spec.suite_id,
                event_type=events.REFLECT_RESULT,
                canary_token=canary_token,
                meta={
                    "failure_reason": result.failure_reason.value if result.failure_reason else None,
                    "suggested_variant": result.suggested_variant,
                },
            )
        )

        self.emitter.emit(
            TelemetryEvent(
                run_id=run_id,
                scenario_id=spec.scenario_id,
                suite_id=spec.suite_id,
                event_type=events.EVAL_RESULT,
                canary_token=canary_token,
                meta={
                    "status": result.status.value,
                    "hard_flags": result.hard_flags,
                    "failure_reason": result.failure_reason.value if result.failure_reason else None,
                },
            )
        )

        if (
            self.config.engagement_id
            and not self.config.no_muzzle
            and result.status in (Status.SUCCESS, Status.INJECTION)
        ):
            memory_entry = build_finding_memory(result, spec, observation, self._cycle)
            write_finding_memory(memory_entry, self.config.engagement_id)

        return result

    async def run_all(
        self,
        specs: list[TestSpec],
        on_result: Optional[Callable[[JudgeResult], None]] = None,
    ) -> list[JudgeResult]:
        results: list[JudgeResult] = []
        for spec in specs:
            for rep in range(1, self.config.runs_per_scenario + 1):
                result = await self.run_one(spec, rep=rep)
                results.append(result)
                if on_result is not None:
                    on_result(result)
        return results
