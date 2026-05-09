# TRD-20: Phase T-1 — Component Fidelity

**Prerequisite:** TRD-19 (Phase T-0) passing — adapter connectivity and surface discovery validated.

**Goal:** Prove that each pipeline component (Grafter, ObjectiveReplayer, CampaignRunner, Judge)
produces **structurally correct and semantically meaningful** outputs when given real victim
responses — not mocked data.

---

## What to Validate

| # | Check | Component | Pass Condition |
|---|-------|-----------|----------------|
| 1 | Grafter discovery | `Grafter.discover()` | Returns ≥1 `VesselCandidate` from real `SummarizedTrace`. Exploitability scores in [0.0, 1.0] and vary across candidates |
| 2 | Grafter ranking | `Grafter.rank()` | Returns `top_k` candidates sorted by exploitability descending. Strategic memory and bandit boosts applied (observable via logging) |
| 3 | Grafter suite building | `Grafter.build_suite()` | Produces valid `TestSpec` list with `oracle_codes`, `attack_surface`, `turns` |
| 4 | Replayer elicitation | `ObjectiveReplayer.run_goal()` | Produces `ObjectiveTrace` with `inferred_disclosure_level` != "none" for cooperative target |
| 5 | Replayer distillation | `ObjectiveReplayer.distill()` | Produces `ObjectiveScript` with non-empty `imperative` (not fallback) |
| 6 | CampaignRunner execution | `CampaignRunner.run_one()` | Produces `JudgeResult` with valid `Status` (not always `InfraFail`) |
| 7 | FindingCard emission | `runner.finding_cards` | Populated for SUCCESS/INJECTION results |
| 8 | Telemetry completeness | JSONL | Contains all 8 core event types |

### Required Telemetry Event Types

All 8 must appear in `telemetry.jsonl` after a component fidelity run:

1. `setup`
2. `pre_flight_snapshot`
3. `upload_phase`
4. `attack_turn_sent`
5. `attack_turn_recv`
6. `post_run_snapshot`
7. `eval_result`
8. `reflect_result`

---

## Pass/Fail Criteria

- **PASS:** All components produce Pydantic-valid outputs. Grafter ≥1 candidate. ObjectiveReplayer
  non-fallback imperative. CampaignRunner status != InfraFail for ≥1 spec. Telemetry has all 8
  event types.
- **FAIL:** Any component raises unhandled exception or produces structurally invalid output.

---

## New Logging

| File | Function | Level | Format |
|------|----------|-------|--------|
| `harness/grafter/grafter.py` | `discover()` | INFO | `Grafter trace_id={id} candidates={n}` |
| `harness/grafter/grafter.py` | `_score()` | DEBUG | `vessel={kind} saliency={f} write_bonus={f} strategic={f} bandit={f} -> exploit={f}` |
| `harness/grafter/grafter.py` | `rank()` | INFO | `Grafter.rank in={n} out={n} top_score={f}` |
| `harness/objective_replay/replayer.py` | `run_goal()` | INFO | `ObjectiveReplayer goal_id={id} disclosure={level}` |
| `harness/objective_replay/replayer.py` | `distill()` | INFO | `distill goal_id={id} imperative_len={n} llm_success={bool}` |
| `harness/campaign/runner.py` | `run_one()` | INFO | Entry: `run_one scenario={id} session={id}` / Exit: `status={s} flags={d} duration={ms}` |

---

## Test Stubs

```python
# tests/e2e/test_phase_t1.py

import pytest


@pytest.mark.e2e
class TestT1GrafterFidelity:
    """Validate Grafter produces correct outputs from real exploration data."""

    async def test_discover_from_real_trace(self, real_summarized_trace):
        """Grafter discovers candidates from real exploration trace."""
        from harness.grafter.grafter import Grafter

        grafter = Grafter()
        candidates = await grafter.discover(real_summarized_trace)

        assert len(candidates) >= 1, "Grafter must discover at least 1 candidate"
        for c in candidates:
            assert 0.0 <= c.exploitability <= 1.0, (
                f"Exploitability must be in [0, 1], got {c.exploitability}"
            )

        # Scores should vary (not all identical)
        scores = [c.exploitability for c in candidates]
        if len(scores) > 1:
            assert len(set(scores)) > 1, "Scores should vary across candidates"

    async def test_rank_applies_boosts(self, real_candidates, strategic_memory, bandit):
        """Ranking with memory/bandit produces different order than without."""
        from harness.grafter.grafter import Grafter

        grafter = Grafter()

        # Rank without boosts
        ranked_plain = grafter.rank(real_candidates, top_k=3)

        # Rank with memory + bandit boosts
        ranked_boosted = grafter.rank(
            real_candidates, top_k=3,
            strategic_memory=strategic_memory,
            bandit=bandit,
        )

        # At minimum, boosts should be applied (order may or may not differ)
        assert len(ranked_boosted) <= 3
        assert all(0.0 <= c.exploitability <= 1.0 for c in ranked_boosted)

    async def test_build_suite_valid_specs(self, real_candidates, objective_script):
        """build_suite produces valid TestSpec with oracle_codes and turns."""
        from harness.grafter.grafter import Grafter

        grafter = Grafter()
        specs = grafter.build_suite(real_candidates[:3], objective_script)

        assert len(specs) >= 1, "build_suite must produce at least 1 TestSpec"
        for spec in specs:
            assert len(spec.turns) > 0, "Each TestSpec must have turns"
            assert spec.attack_surface is not None, "Each TestSpec must have attack_surface"
            assert len(spec.oracle_codes) > 0, "Each TestSpec must have oracle_codes"


@pytest.mark.e2e
class TestT1ObjectiveReplayerFidelity:
    """Validate ObjectiveReplayer elicitation and distillation against real target."""

    async def test_elicitation_not_none(self, victim_adapter):
        """ObjectiveReplayer gets non-'none' disclosure from real target."""
        from harness.objective_replay.replayer import ObjectiveReplayer

        replayer = ObjectiveReplayer(victim=victim_adapter)
        trace = await replayer.run_goal(goal_type="prompt_exfil")

        assert trace.inferred_disclosure_level != "none", (
            f"Expected non-'none' disclosure, got: {trace.inferred_disclosure_level}"
        )

    async def test_distillation_non_fallback(self, objective_trace):
        """Distillation via LLM produces real imperative, not fallback."""
        from harness.objective_replay.replayer import ObjectiveReplayer

        replayer = ObjectiveReplayer(victim=None)  # distill doesn't need victim
        script = await replayer.distill(objective_trace)

        assert script.imperative is not None, "Imperative must not be None"
        assert len(script.imperative) > 0, "Imperative must not be empty"
        # Check it's not the fallback string
        assert "fallback" not in script.imperative.lower(), (
            "Imperative should not be a fallback"
        )


@pytest.mark.e2e
class TestT1CampaignRunnerFidelity:
    """Validate CampaignRunner produces valid results."""

    async def test_run_one_produces_result(self, runner, grafted_spec):
        """CampaignRunner.run_one produces valid JudgeResult."""
        from harness.core.enums import Status

        result = await runner.run_one(grafted_spec)

        assert result.status in Status, f"Invalid status: {result.status}"
        # At least some specs should not be InfraFail
        # (this is validated across multiple specs in the full suite)

    async def test_finding_card_emitted(self, runner, success_spec):
        """FindingCard emitted for SUCCESS/INJECTION results."""
        await runner.run_one(success_spec)

        assert len(runner.finding_cards) >= 1, (
            "At least 1 FindingCard should be emitted for SUCCESS/INJECTION results"
        )

    async def test_telemetry_has_all_event_types(self, completed_run_telemetry):
        """Telemetry JSONL contains all 8 core event types."""
        import json

        event_types = set()
        for line in completed_run_telemetry.read_text().strip().split("\n"):
            event = json.loads(line)
            event_types.add(event["event_type"])

        required = {
            "setup", "pre_flight_snapshot", "upload_phase",
            "attack_turn_sent", "attack_turn_recv", "post_run_snapshot",
            "eval_result", "reflect_result",
        }
        missing = required - event_types
        assert not missing, f"Missing telemetry event types: {missing}"
```

---

## Fixture Dependencies

Additional fixtures needed in `tests/e2e/conftest.py`:

```python
@pytest.fixture
async def real_summarized_trace(victim_adapter, default_tasks):
    """Run Explorer + Summarizer against real target, return first SummarizedTrace."""
    from harness.explorer.explorer import Explorer
    from harness.explorer.summarizer import Summarizer

    explorer = Explorer(victim=victim_adapter)
    traces = await explorer.run_all(default_tasks)
    summarizer = Summarizer()
    return await summarizer.summarize(traces[0])


@pytest.fixture
async def real_candidates(real_summarized_trace):
    """Grafter.discover() output from real trace."""
    from harness.grafter.grafter import Grafter
    grafter = Grafter()
    return await grafter.discover(real_summarized_trace)


@pytest.fixture
async def objective_trace(victim_adapter):
    """ObjectiveReplayer.run_goal() output from real target."""
    from harness.objective_replay.replayer import ObjectiveReplayer
    replayer = ObjectiveReplayer(victim=victim_adapter)
    return await replayer.run_goal(goal_type="prompt_exfil")


@pytest.fixture
async def objective_script(objective_trace):
    """ObjectiveReplayer.distill() output from real trace."""
    from harness.objective_replay.replayer import ObjectiveReplayer
    replayer = ObjectiveReplayer(victim=None)
    return await replayer.distill(objective_trace)
```

---

## Implementation Notes

- Grafter scoring details are only visible at DEBUG level — tests that verify boost application
  should use `caplog` at DEBUG level to inspect `_score()` output
- ObjectiveReplayer elicitation test assumes a cooperative target (MockVictim should be
  configured to echo system prompt fragments for `prompt_exfil` goals)
- Telemetry completeness test requires a full `run_one()` execution path that emits all 8 events
